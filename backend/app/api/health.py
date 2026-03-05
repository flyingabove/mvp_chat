from fastapi import APIRouter
import os
import sys
import time

router = APIRouter()

@router.get("/health")
async def health():
    """
    Python equivalent of backend/api/health.php

    Returns:
      {
        "ok": true,
        "php": "<version string>",   # here: Python version, as a stand-in
        "time": <unix timestamp int>,
        "cwd": "<current working directory>"
      }
    """
    return {
        "ok": True,
        # in PHP this was PHP_VERSION; we mirror the idea with Python version
        "php": sys.version.split(" ")[0],
        "time": int(time.time()),
        "cwd": os.getcwd(),
    }
