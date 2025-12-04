# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.echo import router as echo_router
from app.api.health import router as health_router

app = FastAPI(
    title="StoriesChat Backend (Python)",
    version="1.0.0"
)

# -------------------------
# CORS FIX (critical)
# -------------------------
origins = [
    "https://storieschat.ai",
    "https://www.storieschat.ai",
    "https://storieschat.ai/beta",
    "https://beta.storieschat.ai",
    "https://beta-api.storieschat.ai",
    "https://prod-api.storieschat.ai",
    "*",   # ← optional during development, remove later
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# Routers
# -------------------------
app.include_router(chat_router, prefix="/api")
app.include_router(echo_router, prefix="/api")
app.include_router(health_router, prefix="/api")

@app.get("/api/version")
async def version():
    return {
        "status": "ok",
        "backend": "python",
        "message": "StoriesChat FastAPI backend running"
    }
