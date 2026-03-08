"""FastAPI auth dependencies: get_current_user (required) and get_optional_user."""
from fastapi import Request, HTTPException
from backend.app.auth.jwt_utils import decode_token


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
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
