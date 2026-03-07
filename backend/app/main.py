from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
import os
import threading
from pathlib import Path

from backend.app.api.prompt_engine import router as chat_router
from backend.app.api.echo import router as echo_router
from backend.app.api.health import router as health_router
from backend.app.api.story import router as story_router
from backend.app.api.stories import router as stories_router
from backend.app.api.integration_playback import router as integration_playback_router
from backend.app.api.debug_engine import router as debug_router, ws_debug

from backend.app.middleware.request_id import request_id_middleware
from backend.app.knowledge.runtime.index_service import IndexService

_DEBUG_HTML_PATH  = Path(__file__).parent.parent.parent / "frontend" / "debug.html"
_INDEX_HTML_PATH  = Path(__file__).parent.parent.parent / "frontend" / "index.html"
_MANIFEST_PATH    = Path(__file__).parent.parent.parent / "frontend" / "manifest.json"
_SW_PATH          = Path(__file__).parent.parent.parent / "frontend" / "sw.js"


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _startup_checks()
    yield


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

# WebSocket for debug UI
app.add_websocket_route("/beta/debug/ws", ws_debug)


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
        "message": "StoriesChat FastAPI backend running"
    }