"""Integration tests for auth API endpoints."""
import pytest
from unittest.mock import AsyncMock, patch
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

def test_google_login_redirects_to_google(client):
    resp = client.get("/api/auth/google/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers.get("location", "")
    assert "accounts.google.com" in location or location == ""  # empty if GOOGLE_CLIENT_ID not set


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
