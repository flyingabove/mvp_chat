"""Integration tests for user sessions API endpoints."""
import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.auth.jwt_utils import create_token


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def user1_token():
    return create_token(user_id="uid1", email="user1@example.com", name="User One")


@pytest.fixture()
def user2_token():
    return create_token(user_id="uid2", email="user2@example.com", name="User Two")


# ---------------------------------------------------------------------------
# GET /api/user/sessions
# ---------------------------------------------------------------------------

def test_list_sessions_requires_auth(client):
    resp = client.get("/api/user/sessions")
    assert resp.status_code == 401


def test_list_sessions_authenticated(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.list_user_sessions", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"id": "sess1", "story_id": "story_abc", "story_title": "Mystery", "turns": 5}
        ]
        resp = client.get("/api/user/sessions", headers={"Authorization": f"Bearer {user1_token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "sessions" in data
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["story_title"] == "Mystery"


def test_list_sessions_includes_session_id_field(client, user1_token):
    """Bug 3: API response must include session_id alongside id for frontend compat."""
    with patch("backend.app.api.user_sessions.SessionRepo.list_user_sessions", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"id": "sess1", "story_id": "s1", "story_title": "Title", "turns": 1}
        ]
        resp = client.get("/api/user/sessions", headers={"Authorization": f"Bearer {user1_token}"})
    data = resp.json()
    sess = data["sessions"][0]
    assert sess["session_id"] == "sess1"  # new field
    assert sess["id"] == "sess1"          # backward compat


def test_list_sessions_returns_empty_list_if_none(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.list_user_sessions", new_callable=AsyncMock) as mock:
        mock.return_value = []
        resp = client.get("/api/user/sessions", headers={"Authorization": f"Bearer {user1_token}"})
    assert resp.status_code == 200
    assert resp.json()["sessions"] == []


# ---------------------------------------------------------------------------
# GET /api/user/sessions/{id}/history
# ---------------------------------------------------------------------------

def test_history_requires_auth(client):
    resp = client.get("/api/user/sessions/sess1/history")
    assert resp.status_code == 401


def test_history_for_owned_session(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.ConversationRepo.load_page", new_callable=AsyncMock) as hist_mock:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        hist_mock.return_value = [
            {"turn": 1, "role": "user", "content": "Hello", "ts": 1000},
            {"turn": 1, "role": "assistant", "content": "Hi", "ts": 1000},
        ]
        resp = client.get(
            "/api/user/sessions/sess1/history",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "entries" in data
    assert len(data["entries"]) == 2
    assert "has_more" in data


def test_history_for_nonexistent_session_returns_404(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = client.get(
            "/api/user/sessions/nonexistent/history",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 404


def test_history_cross_user_access_denied(client, user2_token):
    """user2 cannot access user1's session."""
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as mock:
        # Returns None because get_session checks WHERE user_id = uid2 and finds nothing
        mock.return_value = None
        resp = client.get(
            "/api/user/sessions/sess_of_user1/history",
            headers={"Authorization": f"Bearer {user2_token}"},
        )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/user/sessions/{id}
# ---------------------------------------------------------------------------

def test_delete_session_requires_auth(client):
    resp = client.delete("/api/user/sessions/sess1")
    assert resp.status_code == 401


def test_delete_owned_session(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.delete_session", new_callable=AsyncMock) as mock:
        mock.return_value = True
        resp = client.delete(
            "/api/user/sessions/sess1",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_delete_nonexistent_session_returns_404(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.delete_session", new_callable=AsyncMock) as mock:
        mock.return_value = False
        resp = client.delete(
            "/api/user/sessions/nonexistent",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 404
