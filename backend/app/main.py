from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.echo import router as echo_router
from app.api.health import router as health_router
from app.api.story import router as story_router

from app.middleware.request_id import request_id_middleware


app = FastAPI(
    title="StoriesChat Backend (Python)",
    version="1.0.0"
)

# --------------------------------------------------
# Request ID middleware (for logging & traceability)
# --------------------------------------------------
app.middleware("http")(request_id_middleware)

# --------------------------------------------------
# CORS FIX — REQUIRED for browser POST to work
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
    allow_methods=["*"],           # allow POST, OPTIONS, etc.
    allow_headers=["*"],           # allow Content-Type, etc.
)

# --------------------------------------------------
# Routers
# --------------------------------------------------
app.include_router(chat_router, prefix="/api")
app.include_router(echo_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(story_router, prefix="/api")


@app.get("/api/version")
async def version():
    return {
        "status": "ok",
        "backend": "python",
        "message": "StoriesChat FastAPI backend running"
    }
