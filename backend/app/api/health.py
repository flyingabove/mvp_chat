from fastapi import APIRouter
import os
import sys
import time

from backend.app.config import settings
from backend.app.config.build_info import get_build_info

router = APIRouter()


def _jev_health_block() -> dict:
    """Non-authoritative `jev` block, per
    JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §6 ("Exposure"). Useful for
    confirming a rollback (TYPESAFE_ENABLED=false, or removing a task from
    JEV_ENABLED_TASKS) took effect without reading logs, and for the
    ship-and-verify step. Deliberately does NOT construct a resolver or
    touch the network — reads the shared breaker's in-memory snapshot only,
    so calling /api/health never itself triggers a Jev call.
    """
    try:
        from backend.app.llm.factory import get_shared_breaker
        snapshot = get_shared_breaker().snapshot()
    except Exception:
        # /api/health must never fail because of Jev-related bookkeeping -
        # this endpoint is what ship-and-verify and uptime checks depend on.
        snapshot = {"state": "unknown", "consecutive_failures": None, "opened_at": None, "cooldown_s": None}
    return {
        "enabled": settings.TYPESAFE_ENABLED,
        "model": settings.TYPESAFE_MODEL,
        **snapshot,
    }


@router.get("/health")
async def health():
    """
    Python equivalent of backend/api/health.php

    Returns:
      {
        "ok": true,
        "php": "<version string>",   # here: Python version, as a stand-in
        "time": <unix timestamp int>,
        "cwd": "<current working directory>",
        "commit": "<deployed git commit sha>",
        "environment": "<railway environment name, or 'local'>",
        "content_schema_version": <int>,
        "jev": {"enabled": bool, "state": "closed"|"open"|"half_open"|"unknown",
                "consecutive_failures": int|None, "opened_at": float|None,
                "cooldown_s": float|None, "model": "<TYPESAFE_MODEL>"}
      }
    """
    return {
        "ok": True,
        # in PHP this was PHP_VERSION; we mirror the idea with Python version
        "php": sys.version.split(" ")[0],
        "time": int(time.time()),
        "cwd": os.getcwd(),
        **get_build_info(),
        "jev": _jev_health_block(),
    }
