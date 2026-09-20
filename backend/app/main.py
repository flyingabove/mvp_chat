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
from backend.app.api.story import router as story_router
from backend.app.api.stories import router as stories_router
from backend.app.api.integration_playback import router as integration_playback_router
from backend.app.api.debug_engine import router as debug_router, ws_debug
from backend.app.api.auth import router as auth_router
from backend.app.api.user_sessions import router as user_sessions_router
from backend.app.db.database import init_db
from backend.app.db.repos import SessionRepo, FactExtractionOutboxRepo

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
    """Background task: delete guest sessions older than 24 hours. Runs every hour."""
    while True:
        await asyncio.sleep(3600)  # 1 hour
        try:
            cutoff = int(time.time()) - GUEST_TTL_SECONDS
            count = await SessionRepo.delete_expired_guest_sessions(cutoff)
            if count:
                _log.info("Guest cleanup: deleted %d expired guest sessions", count)
                # Also evict from in-memory SESSIONS cache
                from backend.app.api.prompt_engine import SESSIONS
                expired = [
                    sid for sid, sess in SESSIONS.items()
                    if sess.get("user_id", "").startswith("guest:")
                ]
                for sid in expired:
                    SESSIONS.pop(sid, None)
        except Exception:
            _log.exception("Guest cleanup task failed")


async def _fact_extraction_recovery_sweep():
    """BL-01b: one-shot startup sweep that reprocesses any fact-extraction
    outbox rows left 'pending' by a crash between enqueue and completion on
    a prior run (the failure mode this durable outbox exists to close). Also
    prunes 'done' rows older than the retention window so the table doesn't
    grow unbounded on a long-running deploy; 'failed' rows are kept
    indefinitely for diagnosis since volume is low (one row per failure).

    Recovered chunks are attached to the in-memory SESSIONS cache when that
    session happens to still be loaded; right after a fresh process start
    the cache is typically empty (rebuilt lazily on next request), so the
    practical guarantee here is durability - the extraction ran and is
    marked done, so the facts are not silently lost - not necessarily
    immediate re-attachment to a currently-open session."""
    try:
        pending = await FactExtractionOutboxRepo.fetch_pending()
    except Exception:
        _log.exception("Fact-extraction recovery sweep: failed to fetch pending rows")
        return

    if pending:
        _log.info("Fact-extraction recovery: reprocessing %d pending rows", len(pending))
        from backend.app.api.prompt_engine import SESSIONS, extract_facts_from_message

        for row in pending:
            try:
                usr_chunks = await extract_facts_from_message(
                    row["user_msg"], "user", row["user_msg_id"], row["character_id"],
                )
                ai_chunks = await extract_facts_from_message(
                    row["ai_reply"], "assistant", row["ai_msg_id"], row["character_id"],
                )
                sess = SESSIONS.get(row["session_id"])
                if sess is not None and sess.get("state") is not None:
                    store = sess["state"].session_chunk_store
                    if store is not None:
                        store.add_chunks(usr_chunks + ai_chunks)
                await FactExtractionOutboxRepo.mark_done(row["id"])
            except Exception as exc:
                try:
                    await FactExtractionOutboxRepo.mark_failed(row["id"], str(exc))
                except Exception:
                    _log.exception("Fact-extraction recovery: failed to mark row %s failed", row["id"])

    try:
        cutoff = int(time.time()) - FACT_EXTRACTION_OUTBOX_RETENTION_SECONDS
        pruned = await FactExtractionOutboxRepo.prune_done_older_than(cutoff)
        if pruned:
            _log.info("Fact-extraction outbox: pruned %d completed rows older than 7 days", pruned)
    except Exception:
        _log.exception("Fact-extraction outbox: prune step failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _startup_checks()
    await _fact_extraction_recovery_sweep()
    # Start guest cleanup background task
    cleanup_task = asyncio.create_task(_guest_cleanup_loop())
    yield
    cleanup_task.cancel()


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