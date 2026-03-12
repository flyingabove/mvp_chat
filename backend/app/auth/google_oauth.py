"""Google OAuth 2.0 helpers (manual httpx, no authlib)."""
import json
import os
import urllib.parse
import httpx
from backend.app.config.settings import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
SCOPES = "openid email profile"

# Public OAuth client ID is not a secret. Keep env vars as primary source and
# use this as a fail-safe so hosted beta login does not break if client_id env
# is temporarily missing.
DEFAULT_PUBLIC_GOOGLE_CLIENT_ID = "580998794588-otq7o0btdle48qoch385a019rjt5pce8.apps.googleusercontent.com"


def _parse_google_web_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    web = data.get("web")
    if isinstance(web, dict):
        return web
    return data


def _json_web_config_from_env() -> dict:
    candidates = [
        "GOOGLE_OAUTH_WEB_JSON",
        "GOOGLE_OAUTH_CLIENT_JSON",
        "GOOGLE_CLIENT_CONFIG_JSON",
        "GOOGLE_AUTH_CONFIG_JSON",
    ]
    for key in candidates:
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        parsed = _parse_google_web_json(raw)
        if parsed:
            return parsed
    return {}


def _resolved_google_client_id() -> str:
    for value in (
        GOOGLE_CLIENT_ID,
        os.getenv("GOOGLE_CLIENT_ID", ""),
        os.getenv("GOOGLE_WEB_CLIENT_ID", ""),
        os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
    ):
        value = str(value or "").strip()
        if value:
            return value

    web_cfg = _json_web_config_from_env()
    from_json = str(web_cfg.get("client_id", "")).strip()
    if from_json:
        return from_json

    return DEFAULT_PUBLIC_GOOGLE_CLIENT_ID


def _resolved_google_client_secret() -> str:
    for value in (
        GOOGLE_CLIENT_SECRET,
        os.getenv("GOOGLE_CLIENT_SECRET", ""),
        os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
    ):
        value = str(value or "").strip()
        if value:
            return value

    web_cfg = _json_web_config_from_env()
    return str(web_cfg.get("client_secret", "")).strip()


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
