from fastapi import FastAPI
from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.echo import router as echo_router
from app.api.game_logic import router as game_logic_router

app = FastAPI(
    title="StoriesChat Backend (Python)",
    version="1.0.0"
)

# Register routers
app.include_router(chat_router, prefix="/api")
app.include_router(health_router, prefix="/api")
app.include_router(echo_router, prefix="/api")
app.include_router(game_logic_router, prefix="/api")

@app.get("/api/version")
async def version():
    return {
        "status": "ok",
        "backend": "python",
        "message": "StoriesChat FastAPI backend running"
    }
