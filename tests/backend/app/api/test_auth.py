"""Integration tests for auth API endpoints."""
import pytest
import urllib.parse
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth.jwt_utils import create_token


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def valid_token():
    return create_token(user_id="gid_123", email="test@example.com", name="Test User")


# ---------------------------------------------------------------------------
# /api/auth/me
# ---------------------------------------------------------------------------

def test_me_with_valid_token(client, valid_token):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {valid_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "gid_123"
    assert data["email"] == "test@example.com"
    assert data["name"] == "Test User"


def test_me_without_token_returns_401(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer totally.invalid.token"})
    assert resp.status_code == 401


def test_me_with_malformed_header_returns_401(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Basic abc123"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /api/auth/logout
# ---------------------------------------------------------------------------

def test_logout_returns_ok(client):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ---------------------------------------------------------------------------
# /api/auth/google/login redirect
# ---------------------------------------------------------------------------

def test_google_login_redirects_to_google(client, monkeypatch):
    monkeypatch.setattr("backend.app.auth.google_oauth.GOOGLE_CLIENT_ID", "test-client-id")
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers.get("location", "")
    assert "accounts.google.com" in location

    parsed = urllib.parse.urlparse(location)
    query = urllib.parse.parse_qs(parsed.query)
    client_ids = query.get("client_id", [])
    assert client_ids and client_ids[0].strip()


def test_google_login_sets_oauth_state_cookie(client, monkeypatch):
    """A04: /login must bind the `state` value it sends Google to a
    short-lived cookie so /callback can verify it later."""
    monkeypatch.setattr("backend.app.auth.google_oauth.GOOGLE_CLIENT_ID", "test-client-id")
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    location = resp.headers.get("location", "")
    parsed = urllib.parse.urlparse(location)
    query = urllib.parse.parse_qs(parsed.query)
    sent_state = query.get("state", [""])[0]
    assert sent_state

    cookie_state = resp.cookies.get("storieschat_oauth_state")
    assert cookie_state == sent_state


# ---------------------------------------------------------------------------
# /api/auth/google/callback — A04 CSRF state validation
# ---------------------------------------------------------------------------

def _mock_oauth_backend(monkeypatch):
    """Mock the Google token exchange + userinfo + DB upsert so callback
    tests never make network/DB calls; only state validation is exercised."""
    async def _fake_exchange_code(code, redirect_uri):
        return {"access_token": "fake-access-token"}

    async def _fake_get_userinfo(access_token):
        return {"id": "gid_999", "email": "csrf@example.com", "name": "CSRF Test"}

    async def _fake_upsert_user(*args, **kwargs):
        return None

    async def _fake_transfer_sessions(*args, **kwargs):
        return 0

    monkeypatch.setattr("backend.app.api.auth.exchange_code", _fake_exchange_code)
    monkeypatch.setattr("backend.app.api.auth.get_userinfo", _fake_get_userinfo)
    monkeypatch.setattr("backend.app.api.auth.UserRepo.upsert_user", _fake_upsert_user)
    monkeypatch.setattr("backend.app.api.auth.SessionRepo.transfer_sessions", _fake_transfer_sessions)


def test_google_callback_rejects_missing_state_cookie(client, monkeypatch):
    """No oauth_state cookie at all (e.g. attacker-crafted callback link
    visited directly) must be rejected, not silently accepted."""
    _mock_oauth_backend(monkeypatch)
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "any-code", "state": "attacker-supplied-state"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_state"


def test_google_callback_rejects_mismatched_state(client, monkeypatch):
    """A cookie is present but doesn't match the state param — must reject
    (this is the classic OAuth login-CSRF: attacker's own code+state paired
    with a link that doesn't carry the victim's real cookie)."""
    _mock_oauth_backend(monkeypatch)
    client.cookies.set("storieschat_oauth_state", "real-state-from-login")
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "any-code", "state": "different-attacker-state"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_state"


def test_google_callback_clears_state_cookie_on_success(client, monkeypatch):
    """Single-use: a successful callback must instruct the browser to delete
    the state cookie (Max-Age=0), so a real browser can never replay it on a
    second request. (We assert on the Set-Cookie header directly rather than
    the test client's cookie jar, since httpx's stdlib-cookiejar-based
    TestClient has known quirks reconciling Starlette's quoted-empty-string
    delete_cookie() value — the wire-level Set-Cookie header is what an
    actual browser obeys.)"""
    _mock_oauth_backend(monkeypatch)
    client.cookies.set("storieschat_oauth_state", "one-time-state")
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "any-code", "state": "one-time-state"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    set_cookie_headers = (
        resp.headers.get_list("set-cookie")
        if hasattr(resp.headers, "get_list")
        else [resp.headers.get("set-cookie", "")]
    )
    assert any(
        "storieschat_oauth_state=" in h and "Max-Age=0" in h for h in set_cookie_headers
    ), f"expected a Max-Age=0 delete for the oauth state cookie, got: {set_cookie_headers}"


def test_google_callback_rejects_replay_with_no_cookie(client, monkeypatch):
    """Simulates the browser state *after* the cookie above was deleted: a
    second callback request reusing the same state param but carrying no
    cookie (exactly what a real browser sends once Max-Age=0 expires it)
    must be rejected, same as any other missing-cookie case."""
    _mock_oauth_backend(monkeypatch)
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "any-code", "state": "one-time-state"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_state"


def test_google_callback_accepts_valid_matching_state(client, monkeypatch):
    """A correctly bound, single-use state must still let login succeed."""
    _mock_oauth_backend(monkeypatch)
    client.cookies.set("storieschat_oauth_state", "valid-state-123")
    resp = client.get(
        "/api/auth/google/callback",
        params={"code": "any-code", "state": "valid-state-123"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers.get("location", "")
    assert "token=" in location


# ---------------------------------------------------------------------------
# Optional auth: /api/chat works without token
# ---------------------------------------------------------------------------

def test_chat_without_token_uses_anon_user(client):
    """Chat endpoint should be accessible without JWT (anon user)."""
    # We don't make a real LLM call — just verify the endpoint accepts the request
    resp = client.post("/api/chat", json={"message": "__cmd_reset__", "session_id": "test-anon"})
    assert resp.status_code == 200


def test_chat_with_valid_token_accepted(client, valid_token):
    resp = client.post(
        "/api/chat",
        json={"message": "__cmd_reset__", "session_id": "test-auth"},
        headers={"Authorization": f"Bearer {valid_token}"},
    )
    assert resp.status_code == 200


def test_debug_config_reports_runtime_metadata(client, monkeypatch):
    monkeypatch.setenv("DEBUG_MODE", "TRUE")
    monkeypatch.setenv("RUN_TESTS", "1")
    monkeypatch.setenv("JWT_SECRET", "jwt-secret-value")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid-abc")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "secret-xyz")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "beta")
    monkeypatch.setenv("RAILWAY_ENVIRONMENT_ID", "env-123")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "dep-123")
    monkeypatch.setenv("RAILWAY_GIT_BRANCH", "beta")
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", "abc123")

    resp = client.get("/api/auth/debug-config", headers={"host": "beta-api.storieschat.ai"})
    assert resp.status_code == 200

    data = resp.json()
    assert data["client_id_set"] is True
    assert data["client_secret_set"] is True
    assert data["live_env_secret_set"] is True
    assert "GOOGLE_CLIENT_SECRET" in data["google_env_keys"]
    assert "GOOGLE_CLIENT_SECRET" in data["normalized_secret_key_matches"]
    assert data["app_env_presence"]["DEBUG_MODE"]["set"] is True
    assert data["app_env_presence"]["RUN_TESTS"]["set"] is True
    assert data["app_env_presence"]["JWT_SECRET"]["set"] is True
    assert data["app_env_presence"]["GOOGLE_CLIENT_SECRET"]["set"] is True
    assert isinstance(data["non_railway_env_keys_sample"], list)
    assert data["railway_environment_name"] == "beta"
    assert data["railway_environment_id"] == "env-123"
    assert data["railway_deployment_id"] == "dep-123"
    assert data["railway_git_branch"] == "beta"
    assert data["railway_git_commit_sha"] == "abc123"
