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
# GET /api/user/sessions/{id}/journal
# ---------------------------------------------------------------------------

def _make_journal_state():
    """Build a minimal real GameState with goal/disposition history, mirroring
    what a live session would actually produce (no mocking of engine internals,
    only the DB-ownership + session-lookup boundary)."""
    from backend.app.engine.state import Character, init_state
    from backend.app.engine.social_traits import EvolvingTrait
    from backend.app.engine.character_graph import CharacterGraph, CharacterType, RelationshipEdge

    state = init_state()
    state.character_graph = CharacterGraph()

    makoto = Character(key="makoto", name="Makoto", character_type=CharacterType.NPC)
    makoto.goal = EvolvingTrait(kind="goal", subject_id="makoto")
    makoto.goal.set_initial("win Aiko's trust", minute=0, source="author")
    makoto.goal.propose_change(
        "protect Aiko from the truth", minute=120, reason="turn 4 shift",
        confidence=0.8, entry_id="social_shift_goal_makoto__4",
    )
    state.characters = {"makoto": makoto}

    edge = RelationshipEdge(id="makoto->aiko", from_id="makoto", to_id="aiko")
    edge.disposition = EvolvingTrait(kind="disposition", subject_id="makoto", target_id="aiko")
    edge.disposition.set_initial("guarded", minute=0, source="author")
    edge.narrative_log.append("Makoto avoided eye contact with Aiko at dinner.")
    aiko = Character(key="aiko", name="Aiko", character_type=CharacterType.NPC)
    state.characters["aiko"] = aiko
    state.character_graph.edges[CharacterGraph._edge_key("makoto", "aiko")] = edge

    return state


def test_journal_requires_auth(client):
    resp = client.get("/api/user/sessions/sess1/journal")
    assert resp.status_code == 401


def test_journal_for_nonexistent_session_returns_404(client, user1_token):
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = client.get(
            "/api/user/sessions/nonexistent/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 404


def test_journal_cross_user_access_denied(client, user2_token):
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as mock:
        mock.return_value = None
        resp = client.get(
            "/api/user/sessions/sess_of_user1/journal",
            headers={"Authorization": f"Bearer {user2_token}"},
        )
    assert resp.status_code == 404


def test_journal_returns_goal_and_disposition_history(client, user1_token):
    state = _make_journal_state()
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.get_session") as engine_get_session:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        engine_get_session.return_value = {"state": state}
        resp = client.get(
            "/api/user/sessions/sess1/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 200
    entries = resp.json()["entries"]

    kinds = {(e["kind"], e["text"]) for e in entries}
    assert ("goal", "win Aiko's trust") in kinds
    assert ("goal", "protect Aiko from the truth") in kinds
    assert ("disposition", "guarded") in kinds
    assert ("note", "Makoto avoided eye contact with Aiko at dinner.") in kinds

    # Character names are resolved, not raw keys.
    goal_entries = [e for e in entries if e["kind"] == "goal"]
    assert all(e["character_name"] == "Makoto" for e in goal_entries)
    disposition_entries = [e for e in entries if e["kind"] == "disposition"]
    assert disposition_entries[0]["character_name"] == "Makoto"
    assert disposition_entries[0]["target_name"] == "Aiko"

    # Sorted by minute ascending.
    minutes = [e["minute"] for e in entries if e["kind"] != "note"]
    assert minutes == sorted(minutes)


def test_journal_empty_for_character_with_no_goal(client, user1_token):
    """Legacy/no-goal characters must not error or appear in the journal."""
    from backend.app.engine.state import Character, init_state
    from backend.app.engine.character_graph import CharacterType

    state = init_state()
    state.characters = {"plain": Character(key="plain", name="Plain", character_type=CharacterType.NPC)}

    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.get_session") as engine_get_session:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        engine_get_session.return_value = {"state": state}
        resp = client.get(
            "/api/user/sessions/sess1/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


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


# ---------------------------------------------------------------------------
# Guest (X-Guest-Id) access
# ---------------------------------------------------------------------------

VALID_GUEST_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"


def test_list_sessions_with_guest_id(client):
    """Guest users can list their sessions via X-Guest-Id header."""
    with patch("backend.app.api.user_sessions.SessionRepo.list_user_sessions", new_callable=AsyncMock) as mock:
        mock.return_value = [
            {"id": "gsess1", "story_id": "s1", "story_title": "Guest Game", "turns": 2}
        ]
        resp = client.get(
            "/api/user/sessions",
            headers={"X-Guest-Id": VALID_GUEST_ID},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sessions"]) == 1
    # Verify the repo was called with the prefixed guest user_id
    mock.assert_called_once_with(user_id=f"guest:{VALID_GUEST_ID}", limit=50)


def test_list_sessions_rejects_invalid_guest_id(client):
    """Invalid guest IDs (not UUID format) should be rejected as 401."""
    resp = client.get(
        "/api/user/sessions",
        headers={"X-Guest-Id": "not-a-valid-uuid"},
    )
    assert resp.status_code == 401


def test_guest_history_access(client):
    """Guest users can access their own session history."""
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.ConversationRepo.load_page", new_callable=AsyncMock) as hist_mock:
        sess_mock.return_value = {"id": "gsess1", "user_id": f"guest:{VALID_GUEST_ID}"}
        hist_mock.return_value = [
            {"turn": 1, "role": "user", "content": "Hello", "ts": 1000},
            {"turn": 1, "role": "assistant", "content": "Hi", "ts": 1000},
        ]
        resp = client.get(
            "/api/user/sessions/gsess1/history",
            headers={"X-Guest-Id": VALID_GUEST_ID},
        )
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 2


def test_guest_cannot_access_auth_user_session(client):
    """Guest cannot access a JWT-authenticated user's session."""
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as mock:
        mock.return_value = None  # DB returns nothing because user_id doesn't match
        resp = client.get(
            "/api/user/sessions/uid1_session/history",
            headers={"X-Guest-Id": VALID_GUEST_ID},
        )
    assert resp.status_code == 404
