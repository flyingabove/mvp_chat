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
