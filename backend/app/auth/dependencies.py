"""FastAPI auth dependencies: get_current_user (required) and get_optional_user."""
import os
import re
from fastapi import Request, WebSocket, HTTPException
from backend.app.auth.jwt_utils import decode_token

# Guest IDs must be valid UUIDs (hex, 32-36 chars) to prevent injection
_GUEST_ID_RE = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.I)


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _extract_guest_id(request: Request) -> str | None:
    """Extract and validate X-Guest-Id header. Returns sanitized guest ID or None."""
    raw = (request.headers.get("X-Guest-Id") or "").strip()
    if raw and _GUEST_ID_RE.match(raw):
        return raw.lower()
    return None


async def get_current_user(request: Request) -> dict:
    """Require a valid JWT. Raises 401 if missing or invalid."""
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_optional_user(request: Request) -> dict | None:
    """Return decoded JWT payload if present and valid, else None."""
    token = _extract_token(request)
    if not token:
        return None
    try:
        return decode_token(token)
    except Exception:
        return None


async def get_current_user_or_guest(request: Request) -> dict:
    """Return user info from JWT, or guest identity from X-Guest-Id header.

    Priority: JWT > X-Guest-Id > 401
    Guest users get a synthetic payload with sub="guest:<uuid>".
    """
    token = _extract_token(request)
    if token:
        try:
            return decode_token(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid or expired token")

    guest_id = _extract_guest_id(request)
    if guest_id:
        return {"sub": f"guest:{guest_id}", "email": "", "name": "Guest"}

    raise HTTPException(status_code=401, detail="Not authenticated")


# ---------------------------------------------------------------------------
# Operator/admin authorization (A03)
# ---------------------------------------------------------------------------
# Privileged surfaces (debug engine, playback, story authoring/canonical-fact
# endpoints) must never be reachable by ordinary players. Two independent
# gates are required:
#   1. DEBUG_TOOLS_ENABLED must be explicitly turned on. It defaults OFF, so
#      a prod-like deployment that forgets to configure OPERATOR_TOKEN is
#      still safe by default.
#   2. A matching OPERATOR_TOKEN must be supplied via the X-Operator-Token
#      header (REST) or the operator_token query parameter (WebSocket,
#      since browsers cannot set custom headers on a WS handshake).
def _debug_tools_enabled() -> bool:
    return os.getenv("DEBUG_TOOLS_ENABLED", "").strip().lower() in {"1", "true", "yes"}


def _operator_token_configured() -> str:
    return os.getenv("OPERATOR_TOKEN", "").strip()


def _check_operator_token(supplied: str | None) -> None:
    if not _debug_tools_enabled():
        raise HTTPException(status_code=403, detail="Debug/authoring tools are disabled")
    expected = _operator_token_configured()
    if not expected:
        # Tools enabled but no token configured: fail closed, not open.
        raise HTTPException(status_code=403, detail="Operator access is not configured")
    if not supplied or supplied != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing operator credentials")


async def require_operator(request: Request) -> dict:
    """FastAPI dependency for HTTP routes: require a valid operator token."""
    supplied = request.headers.get("X-Operator-Token") or request.query_params.get("operator_token")
    _check_operator_token(supplied)
    return {"sub": "operator"}


def is_operator_request(request: Request) -> bool:
    """Non-raising operator check for routes that must stay publicly
    reachable (e.g. /api/chat) but should only reveal privileged debug data
    (full system prompt, canonical facts, retrieval internals) to an
    authenticated operator. Unlike require_operator, never raises — callers
    use this to conditionally include/omit a response field, not to reject
    the request. A caller with no/invalid token simply gets False, same as
    an ordinary player."""
    supplied = request.headers.get("X-Operator-Token") or request.query_params.get("operator_token")
    if not supplied or not _debug_tools_enabled():
        return False
    expected = _operator_token_configured()
    return bool(expected) and supplied == expected


async def require_operator_ws(websocket: WebSocket) -> dict:
    """Same check for WebSocket routes (no custom headers from the browser,
    so also accept the token as a query parameter on the connect URL)."""
    supplied = websocket.headers.get("X-Operator-Token") or websocket.query_params.get("operator_token")
    _check_operator_token(supplied)
    return {"sub": "operator"}
