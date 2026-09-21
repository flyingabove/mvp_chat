# backend/app/config/credentials.py
"""Centralized credential loading.

Priority order:
1. Environment variables (Railway, CI/CD, or manually set)
2. .env.test file at project root (local development fallback)

All code and tests should use this module instead of reading env vars directly
or implementing their own .env.test parsers.

Trigger keys that lazily load .env.test on first read: OPENAI_API_KEY,
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, JWT_SECRET, LANGSMITH_API_KEY,
LANGSMITH_PROJECT.
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


def _get_env_with_fallback(name: str) -> str:
    """Return env var by name, loading .env.test once as a fallback.

    Tolerates case-only key mismatches (e.g. ``google_client_id`` vs
    ``GOOGLE_CLIENT_ID``) the same way the legacy resolver in
    ``google_oauth._resolved_env_var`` did.
    """
    def _scan() -> str:
        direct = os.environ.get(name, "")
        if direct.strip():
            return direct.strip()
        target = name.upper()
        for key, value in os.environ.items():
            if key.upper() == target and (value or "").strip():
                return value.strip()
        return ""

    found = _scan()
    if found:
        return found
    _load_env_test_once()
    return _scan()


def get_google_client_id() -> str:
    """Return GOOGLE_CLIENT_ID, loading .env.test as fallback if needed."""
    return _get_env_with_fallback("GOOGLE_CLIENT_ID")


def get_google_client_secret() -> str:
    """Return GOOGLE_CLIENT_SECRET, loading .env.test as fallback if needed."""
    return _get_env_with_fallback("GOOGLE_CLIENT_SECRET")


def get_jwt_secret() -> str:
    """Return JWT_SECRET, loading .env.test as fallback if needed.

    Falls back to a dev-only sentinel if absolutely nothing is set; production
    must always set this via Railway env vars.
    """
    return _get_env_with_fallback("JWT_SECRET") or "dev-secret-change-in-production"


def get_langsmith_api_key() -> str:
    """Return LANGSMITH_API_KEY, loading .env.test as fallback if needed.

    Returns "" when tracing is not configured; callers must treat LangSmith as
    optional and never fail a turn because tracing is unavailable.
    """
    return _get_env_with_fallback("LANGSMITH_API_KEY")


def get_langsmith_project() -> str:
    """Return the LangSmith project name, defaulting to "storieschat"."""
    return _get_env_with_fallback("LANGSMITH_PROJECT") or "storieschat"


def is_langsmith_enabled() -> bool:
    """True only when a LangSmith key is present AND tracing is opted in.

    Tracing is off unless LANGSMITH_TRACING is truthy, so merely having the key
    in .env.test never silently ships player content to an external service.
    """
    if not get_langsmith_api_key():
        return False
    flag = _get_env_with_fallback("LANGSMITH_TRACING").lower()
    return flag in {"1", "true", "yes", "on"}
