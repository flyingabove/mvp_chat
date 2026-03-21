"""FastAPI auth dependencies: get_current_user (required) and get_optional_user."""
import re
from fastapi import Request, HTTPException
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
