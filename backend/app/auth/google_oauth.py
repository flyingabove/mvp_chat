"""Google OAuth 2.0 helpers (manual httpx, no authlib)."""
import os
import urllib.parse
import httpx
from backend.app.config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
SCOPES = "openid email profile"


def _resolved_env_var(name: str) -> str:
    """Resolve an env var by exact key first, then normalized key fallback.

    Tolerates case-only key mismatches, but never accepts whitespace-padded keys.
    """
    direct = os.getenv(name, "")
    if direct.strip():
        return direct.strip()

    target = name.upper()
    for key, value in os.environ.items():
        if key.upper() == target and (value or "").strip():
            return value.strip()

    return ""


def _resolved_google_client_id() -> str:
    """Return GOOGLE_CLIENT_ID from settings. Must be set via env var."""
    return _resolved_env_var("GOOGLE_CLIENT_ID") or (GOOGLE_CLIENT_ID or "").strip()


def _resolved_google_client_secret() -> str:
    """Return GOOGLE_CLIENT_SECRET from settings. Must be set via env var."""
    return _resolved_env_var("GOOGLE_CLIENT_SECRET") or (GOOGLE_CLIENT_SECRET or "").strip()


def build_auth_url(redirect_uri: str, state: str) -> str:
    """Return the Google OAuth consent-screen URL."""
    client_id = _resolved_google_client_id()
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "access_type": "online",
    }
    return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"


async def exchange_code(code: str, redirect_uri: str) -> dict:
    """Exchange OAuth authorization code for tokens."""
    client_id = _resolved_google_client_id()
    client_secret = _resolved_google_client_secret()
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    r.raise_for_status()
    return r.json()


async def get_userinfo(access_token: str) -> dict:
    """Fetch user info from Google using the access token."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
    r.raise_for_status()
    return r.json()
