from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
import logging
import os
import time
import threading
from pathlib import Path

from backend.app.api.prompt_engine import router as chat_router
from backend.app.api.echo import router as echo_router
from backend.app.api.health import router as health_router
from backend.app.api.eval_capabilities import router as eval_capabilities_router
from backend.app.api.story import router as story_router
from backend.app.api.stories import router as stories_router
from backend.app.api.integration_playback import router as integration_playback_router
from backend.app.api.debug_engine import router as debug_router, ws_debug
from backend.app.api.auth import router as auth_router
from backend.app.api.user_sessions import router as user_sessions_router
from backend.app.db.database import init_db
from backend.app.db.repos import SessionRepo, FactExtractionOutboxRepo, ExtractedChunksRepo

from backend.app.middleware.request_id import request_id_middleware
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.config.build_info import get_build_info

_DEBUG_HTML_PATH  = Path(__file__).parent.parent.parent / "frontend" / "debug.html"
_INDEX_HTML_PATH  = Path(__file__).parent.parent.parent / "frontend" / "index.html"
_MANIFEST_PATH    = Path(__file__).parent.parent.parent / "frontend" / "manifest.json"
_SW_PATH          = Path(__file__).parent.parent.parent / "frontend" / "sw.js"
_IMG_DIR          = Path(__file__).parent.parent.parent / "frontend" / "img"


# --------------------------------------------------
# Index warm-up (lazy, non-blocking, runtime-only)
# --------------------------------------------------
def warm_indexes() -> None:
    """
    Warm retrieval indexes in the background so the first user message
    doesn't pay the load cost.

    - Never runs at import time
    - Safe to disable during tests
    - Does not block app startup
    """
    if os.getenv("DISABLE_INDEX_WARMUP") == "1":
        return

    def _warm():
        try:
            IndexService.get()
            print({"kind": "index_warmup_ok"})
        except Exception as e:
            # Loud logging, but do not crash the app
            print({"kind": "index_warmup_failed", "error": repr(e)})

    threading.Thread(target=_warm, daemon=True).start()


def _startup_checks():
    """Shared startup logic for lifespan and tests."""
    # HARD FAIL MODE (deploy safety)
    if os.getenv("REQUIRE_INDEXES") == "1":
        # This MUST raise if artifacts are missing
        IndexService.get()
        print({"kind": "index_startup_check_ok"})
        return

    # Default behavior (unchanged)
    warm_indexes()


# --------------------------------------------------
# Lifespan (startup/shutdown)
# --------------------------------------------------


_log = logging.getLogger(__name__)

GUEST_TTL_SECONDS = 24 * 60 * 60  # 1 day
FACT_EXTRACTION_OUTBOX_RETENTION_SECONDS = 7 * 24 * 60 * 60  # 7 days


async def _guest_cleanup_loop():
    """Background task: delete guest sessions older than 24 hours. Runs every hour.

    Phase 1.5: evicts EXACTLY the session IDs the DB delete actually removed,
    not every cached guest session. The old code built its eviction list from
    SESSIONS' own contents filtered by user_id prefix - so ANY cached guest
    session was evicted whenever ANY expired guest rows were deleted,
    including one an in-flight turn was actively using at that exact moment
    (evicting mid-turn would not corrupt that turn - it operates on a local
    `state`/`log` reference per Phase 1.1's clone-and-publish, not the
    SESSIONS entry directly - but the NEXT request for that session would
    incorrectly see "session expired" for a session that was in fact still
    within its TTL).

    Each eviction also acquires that session's own per-session lock (the same
    lock chat_handler holds for the full duration of a turn) before popping
    it from SESSIONS. This guarantees eviction cannot interleave with an
    in-flight turn for that specific session: either the turn finishes first
    and this cleanly evicts the (now-idle) cached entry, or this runs first
    and the next request for that session correctly falls through to
    get_session()'s "not in SESSIONS -> try DB restore" path, which correctly
    finds nothing (the DB row is genuinely gone) rather than resurrecting a
    deleted session from a stale in-memory copy."""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            cutoff = int(time.time()) - GUEST_TTL_SECONDS
            deleted_ids = await SessionRepo.delete_expired_guest_sessions(cutoff)
            if deleted_ids:
                _log.info("Guest cleanup: deleted %d expired guest sessions", len(deleted_ids))
                from backend.app.api.prompt_engine import SESSIONS, _SESSION_LOCKS, _get_session_lock
                for sid in deleted_ids:
                    if sid not in SESSIONS:
                        continue
                    async with _get_session_lock(sid):
                        SESSIONS.pop(sid, None)
                    # Retire the lock too, once we're certain nothing else is
                    # waiting on it (we just released it and this session's
                    # data is gone, so no new request should be racing to
                    # acquire it right this instant) - bounds _SESSION_LOCKS'
                    # otherwise-unbounded growth (one entry per session_id
                    # ever seen). `locked()` being False here does not
                    # guarantee zero waiters queued a microsecond earlier, but
                    # a session that no longer exists in SESSIONS will fail
                    # its "session expired" check immediately regardless of
                    # which Lock object it happens to synchronize on, so a
                    # rare miss here just means the lock dict grows by one
                    # entry occasionally, not a correctness issue.
                    lock = _SESSION_LOCKS.get(sid)
                    if lock is not None and not lock.locked():
                        _SESSION_LOCKS.pop(sid, None)
        except Exception:
            _log.exception("Guest cleanup task failed")


FACT_EXTRACTION_LEASE_SECONDS = 300  # 5 minutes
FACT_EXTRACTION_SWEEP_INTERVAL_SECONDS = 600  # 10 minutes


async def _fact_extraction_periodic_sweep_loop():
    """Phase 1.2 (closes BL-01c): the startup sweep in
    _fact_extraction_recovery_sweep only runs once, at process start, so it
    correctly recovers a row left 'pending' by a CRASH/restart but not one
    whose in-process extraction task HUNG (e.g. a network stall) without the
    process itself crashing - that row would stay 'pending' indefinitely
    until the next restart. This loop periodically claims pending rows whose
    lease has expired (claim_pending sets a lease so a row currently being
    worked by the original task is not double-processed) and reprocesses
    them through the same durable path."""
    while True:
        await asyncio.sleep(FACT_EXTRACTION_SWEEP_INTERVAL_SECONDS)
        try:
            claimed = await FactExtractionOutboxRepo.claim_pending(
                limit=200, lease_seconds=FACT_EXTRACTION_LEASE_SECONDS,
            )
            await _reprocess_outbox_rows(claimed, "periodic sweep")
        except Exception:
            _log.exception("Fact-extraction periodic sweep failed")


async def _reprocess_outbox_rows(rows: list[dict], sweep_name: str) -> None:
    """Shared reprocessing body for both the startup sweep and the periodic
    mid-uptime sweep (BL-01c). Phase 1.2: uses extract_facts_with_status so a
    provider failure is retried (mark_failed) instead of being silently
    recorded as a successful empty extraction, and durably persists the
    extracted chunks via mark_done_with_chunks in the SAME transaction as the
    done status - not just the in-memory SessionChunkStore, which is only
    persisted by a LATER turn's session save.

    Recovered chunks are ALSO attached to the in-memory SESSIONS cache when
    that session happens to still be loaded, for immediate availability; the
    durable write above is what actually prevents loss regardless of whether
    the session is loaded right now."""
    if not rows:
        return
    _log.info("Fact-extraction %s: reprocessing %d rows", sweep_name, len(rows))
    from backend.app.api.prompt_engine import SESSIONS, extract_facts_with_status, EXTRACTOR_VERSION

    for row in rows:
        try:
            usr_result = await extract_facts_with_status(
                row["user_msg"], "user", row["user_msg_id"], row["character_id"],
            )
            ai_result = await extract_facts_with_status(
                row["ai_reply"], "assistant", row["ai_msg_id"], row["character_id"],
            )
            if not usr_result.ok or not ai_result.ok:
                err = usr_result.error or ai_result.error or "unknown extraction failure"
                await FactExtractionOutboxRepo.mark_failed(row["id"], err)
                continue

            sess = SESSIONS.get(row["session_id"])
            if sess is not None and sess.get("state") is not None:
                store = sess["state"].session_chunk_store
                if store is not None:
                    store.add_chunks(usr_result.chunks + ai_result.chunks)

            await FactExtractionOutboxRepo.mark_done_with_chunks(
                row["id"], row["session_id"], row["user_id"],
                {row["user_msg_id"]: usr_result.chunks, row["ai_msg_id"]: ai_result.chunks},
                EXTRACTOR_VERSION,
            )
        except Exception as exc:
            try:
                await FactExtractionOutboxRepo.mark_failed(row["id"], str(exc))
            except Exception:
                _log.exception("Fact-extraction %s: failed to mark row %s failed", sweep_name, row["id"])


async def _fact_extraction_recovery_sweep():
    """BL-01b: one-shot startup sweep that reprocesses any fact-extraction
    outbox rows left 'pending' by a crash between enqueue and completion on
    a prior run (the failure mode this durable outbox exists to close). Also
    prunes 'done' rows older than the retention window so the table doesn't
    grow unbounded on a long-running deploy; 'failed' rows are kept
    indefinitely for diagnosis since volume is low (one row per failure)."""
    try:
        pending = await FactExtractionOutboxRepo.fetch_pending()
    except Exception:
        _log.exception("Fact-extraction recovery sweep: failed to fetch pending rows")
        return

    await _reprocess_outbox_rows(pending, "startup recovery")

    try:
        cutoff = int(time.time()) - FACT_EXTRACTION_OUTBOX_RETENTION_SECONDS
        pruned = await FactExtractionOutboxRepo.prune_done_older_than(cutoff)
        if pruned:
            _log.info("Fact-extraction outbox: pruned %d completed rows older than 7 days", pruned)
    except Exception:
        _log.exception("Fact-extraction outbox: prune step failed")


async def _warm_embedder() -> None:
    """Phase 1.3: load the sentence-transformer model off the request path.

    Measured locally: the first `embed_*` call constructs the model in ~15.9s,
    and because retrieval runs synchronously inside the async route that time is
    spent with the event loop fully blocked - every other session, and health
    checks, stall for the whole window, once per deploy.

    Warming it here converts that one-off stall into background work. Two
    deliberate properties:
      * `asyncio.to_thread` - the load is CPU/IO-bound and blocking, so running
        it on the loop would recreate exactly the stall we are removing.
      * NOT awaited by `lifespan` - readiness must not wait on a multi-second
        model load, or deploys would look unhealthy. A request arriving mid-load
        blocks on the embedder's own lock and then reuses the same model, so
        correctness does not depend on the warm-up finishing first.
    """
    try:
        from backend.app.knowledge.build.embedder import warm_up
        ok = await asyncio.to_thread(warm_up)
        _log.info("Embedder warm-up %s", "complete" if ok else "failed (will load lazily)")
    except Exception:
        _log.exception("Embedder warm-up task failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _startup_checks()
    await _fact_extraction_recovery_sweep()
    # Start guest cleanup background task
    cleanup_task = asyncio.create_task(_guest_cleanup_loop())
    # Phase 1.2 (BL-01c): periodic sweep for HUNG (not crashed) extraction tasks.
    extraction_sweep_task = asyncio.create_task(_fact_extraction_periodic_sweep_loop())
    # Fire-and-forget: readiness intentionally does not await the model load.
    warm_task = asyncio.create_task(_warm_embedder())
    yield
    cleanup_task.cancel()
    extraction_sweep_task.cancel()
    warm_task.cancel()


# --------------------------------------------------
# FastAPI app
# --------------------------------------------------
app = FastAPI(
    title="StoriesChat Backend (Python)",
    version="1.0.0",
    lifespan=lifespan,
)


# --------------------------------------------------
# Request ID middleware (logging & traceability)
# --------------------------------------------------
app.middleware("http")(request_id_middleware)


# --------------------------------------------------
# CORS — REQUIRED for browser POST to work
# --------------------------------------------------
origins = [
    "https://storieschat.ai",
    "https://www.storieschat.ai",
    "https://storieschat.ai/beta",
    "https://beta.storieschat.ai",
    "https://beta-api.storieschat.ai",
    "http://localhost:8899",
    "http://127.0.0.1:8899",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Routers
# --------------------------------------------------
app.include_router(chat_router, prefix="/api")
app.include_router(echo_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(eval_capabilities_router, prefix="/api")
app.include_router(story_router, prefix="/api")
app.include_router(stories_router, prefix="/api")
app.include_router(integration_playback_router, prefix="/api")
app.include_router(debug_router, prefix="/beta/debug")
app.include_router(auth_router)
app.include_router(user_sessions_router)

# WebSocket for debug UI
app.add_websocket_route("/beta/debug/ws", ws_debug)

# --------------------------------------------------
# Static assets (game thumbnails etc.)
# --------------------------------------------------
_IMG_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/img", StaticFiles(directory=str(_IMG_DIR)), name="img")


# --------------------------------------------------
# Frontend pages (served by Railway; keeps Namecheap out of the loop)
# --------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def game_ui_prod():
    return _INDEX_HTML_PATH.read_text(encoding="utf-8")


@app.get("/beta/", response_class=HTMLResponse)
@app.get("/beta", response_class=HTMLResponse)
async def game_ui_beta():
    return _INDEX_HTML_PATH.read_text(encoding="utf-8")


@app.get("/debug", response_class=HTMLResponse)
@app.get("/beta/debug", response_class=HTMLResponse)
async def debug_ui_page():
    return _DEBUG_HTML_PATH.read_text(encoding="utf-8")


# --------------------------------------------------
# PWA assets (manifest + service worker)
# --------------------------------------------------
@app.get("/manifest.json")
@app.get("/beta/manifest.json")
async def pwa_manifest():
    return FileResponse(str(_MANIFEST_PATH), media_type="application/manifest+json")


@app.get("/sw.js")
@app.get("/beta/sw.js")
async def service_worker():
    return FileResponse(str(_SW_PATH), media_type="application/javascript")


# --------------------------------------------------
# Version endpoint
# --------------------------------------------------
@app.get("/api/version")
async def version():
    return {
        "status": "ok",
        "backend": "python",
        "message": "StoriesChat FastAPI backend running",
        **get_build_info(),
    }


# version.json — served as a relative asset from both / and /beta/
@app.get("/version.json")
@app.get("/beta/version.json")
async def version_json():
    return get_build_info()

@app.get("/dialogue.js")
@app.get("/beta/dialogue.js")
async def dialogue_script():
    return FileResponse(str(_INDEX_HTML_PATH.parent / "dialogue.js"), media_type="text/javascript")


@app.get("/dialogue.css")
@app.get("/beta/dialogue.css")
async def dialogue_styles():
    return FileResponse(str(_INDEX_HTML_PATH.parent / "dialogue.css"), media_type="text/css")


@app.get("/world-map.js")
@app.get("/beta/world-map.js")
async def world_map_script():
    return FileResponse(str(_INDEX_HTML_PATH.parent / "world-map.js"), media_type="text/javascript")


@app.get("/world-map.css")
@app.get("/beta/world-map.css")
async def world_map_styles():
    return FileResponse(str(_INDEX_HTML_PATH.parent / "world-map.css"), media_type="text/css")
