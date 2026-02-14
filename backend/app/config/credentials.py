# backend/app/config/credentials.py
"""Centralized credential loading.

Priority order:
1. Environment variables (Railway, CI/CD, or manually set)
2. .env.test file at project root (local development fallback)

All code and tests should use this module instead of reading env vars directly
or implementing their own .env.test parsers.
"""
from __future__ import annotations

import os
from pathlib import Path

_env_test_loaded = False


def _find_project_root() -> Path:
    """Walk up from this file to find the project root (contains .env.test or tests/)."""
    # backend/app/config/credentials.py -> 3 levels up = project root
    return Path(__file__).resolve().parents[3]


def _load_env_test_once() -> None:
    """Load .env.test once if it exists and hasn't been loaded yet.

    Only sets variables that are NOT already present in the environment,
    so Railway/CI env vars always take priority.
    """
    global _env_test_loaded
    if _env_test_loaded:
        return
    _env_test_loaded = True

    env_path = _find_project_root() / ".env.test"
    if not env_path.exists():
        return

    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Remove surrounding quotes
            if len(value) >= 2 and (
                (value[0] == '"' and value[-1] == '"')
                or (value[0] == "'" and value[-1] == "'")
            ):
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def get_openai_api_key() -> str:
    """Return the OpenAI API key, loading .env.test as fallback if needed."""
    key = os.environ.get("OPENAI_API_KEY", "")
    if key:
        return key
    _load_env_test_once()
    return os.environ.get("OPENAI_API_KEY", "")


def require_openai_api_key() -> str:
    """Return the OpenAI API key or raise RuntimeError if not available."""
    key = get_openai_api_key()
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Set it as an environment variable "
            "or create a .env.test file at the project root."
        )
    return key
