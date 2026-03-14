"""Google OAuth 2.0 login flow + JWT auth endpoints."""
import logging
import secrets
from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse

log = logging.getLogger(__name__)

from backend.app.auth.google_oauth import build_auth_url, exchange_code, get_userinfo
from backend.app.auth.jwt_utils import create_token
from backend.app.auth.dependencies import get_current_user
from backend.app.db.repos import UserRepo

router = APIRouter()


def _build_redirect_uri(request: Request) -> str:
    """Build the OAuth callback URL based on the incoming host.

    Canonical callback path is /auth/google/callback to match Google Console
    redirect URI registration. /api/auth/google/callback remains available as a
    compatibility alias route.
    """
    host = request.headers.get("host", "")
    scheme = "https" if not host.startswith("localhost") else "http"
    return f"{scheme}://{host}/auth/google/callback"


def _build_frontend_base(request: Request) -> str:
    """Return the frontend base path (/ or /beta/) based on host."""
    host = request.headers.get("host", "")
    # beta-api.storieschat.ai serves the beta frontend at /beta/
    if "beta" in host or request.url.path.startswith("/beta"):
        return "/beta/"
    return "/"


@router.get("/api/auth/google/login")
@router.get("/auth/google/login")
async def google_login(request: Request):
    """Redirect browser to Google OAuth consent screen."""
    state = secrets.token_urlsafe(16)
    redirect_uri = _build_redirect_uri(request)
    url = build_auth_url(redirect_uri=redirect_uri, state=state)
    log.info("OAuth redirect_uri=%s  auth_url=%s", redirect_uri, url[:200])
    return RedirectResponse(url=url)


@router.get("/api/auth/google/callback")
@router.get("/auth/google/callback")
async def google_callback(code: str, state: str, request: Request):
    """
    Handle Google OAuth callback:
    - exchange code for tokens
    - fetch user info
    - upsert user in SQLite
    - create JWT
    - redirect to frontend with ?token=<jwt>
    """
    redirect_uri = _build_redirect_uri(request)
    token_data = await exchange_code(code=code, redirect_uri=redirect_uri)
    access_token = token_data.get("access_token", "")
    user_info = await get_userinfo(access_token)

    user_id = user_info.get("id") or user_info.get("sub", "")
    email = user_info.get("email", "")
    name = user_info.get("name", "")
    avatar_url = user_info.get("picture")

    await UserRepo.upsert_user(user_id=user_id, email=email, name=name, avatar_url=avatar_url)

    jwt_token = create_token(user_id=user_id, email=email, name=name)

    frontend_base = _build_frontend_base(request)
    return RedirectResponse(url=f"{frontend_base}?token={jwt_token}")


@router.get("/api/auth/me")
@router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user's info."""
    return {
        "id": user.get("sub"),
        "email": user.get("email"),
        "name": user.get("name"),
    }


@router.post("/api/auth/logout")
@router.post("/auth/logout")
async def logout():
    """Stateless logout — client clears the JWT from localStorage."""
    return {"ok": True}


@router.get("/api/auth/debug-config")
async def debug_config(request: Request):
    """Diagnostic: show resolved OAuth config (no secrets)."""
    from backend.app.auth.google_oauth import _resolved_google_client_id
    client_id = _resolved_google_client_id()
    redirect_uri = _build_redirect_uri(request)
    return {
        "client_id_set": bool(client_id),
        "client_id_prefix": client_id[:20] + "..." if client_id else "(empty)",
        "redirect_uri": redirect_uri,
        "host_header": request.headers.get("host", "(missing)"),
    }
