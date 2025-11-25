from fastapi import APIRouter
import time, os

router = APIRouter()

@router.get("/health")
async def health():
    return {
        "ok": True,
        "python_version": os.sys.version,
        "time": time.time(),
        "cwd": os.getcwd(),
    }
