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


def _make_journal_state_with_lifecycle():
    """Like _make_journal_state, but with a cast_lifecycle where one
    character (yuki) is UPCOMING (not yet arrived) and one (makoto) is
    ACTIVE. Used to prove the Phase 1.4 visibility filter actually closes
    the audit's finding: an unarrived character's authored goal history must
    never appear in a real player's journal."""
    from backend.app.engine.state import Character, init_state
    from backend.app.engine.social_traits import EvolvingTrait
    from backend.app.engine.character_graph import CharacterGraph, CharacterType, RelationshipEdge
    from backend.app.engine.cast_lifecycle import CastLifecycleState, CastMemberState, CastStatus

    state = init_state()
    state.character_graph = CharacterGraph()

    makoto = Character(key="makoto", name="Makoto", character_type=CharacterType.NPC)
    makoto.goal = EvolvingTrait(kind="goal", subject_id="makoto")
    makoto.goal.set_initial("win Aiko's trust", minute=0, source="author")
    state.characters = {"makoto": makoto}

    # yuki is authored with a starting goal, exactly like an active
    # character, but has NEVER arrived in this playthrough (UPCOMING).
    yuki = Character(key="yuki", name="Yuki", character_type=CharacterType.NPC)
    yuki.goal = EvolvingTrait(kind="goal", subject_id="yuki")
    yuki.goal.set_initial("secretly plotting to leave the house", minute=0, source="author")
    state.characters["yuki"] = yuki

    edge = RelationshipEdge(id="makoto->yuki", from_id="makoto", to_id="yuki")
    edge.disposition = EvolvingTrait(kind="disposition", subject_id="makoto", target_id="yuki")
    edge.disposition.set_initial("has not met", minute=0, source="author")
    state.character_graph.edges[CharacterGraph._edge_key("makoto", "yuki")] = edge

    state.cast_lifecycle = CastLifecycleState(
        enabled=True,
        arrival_location_id="living_room",
        replacement_policy="same_slot_next",
        departure_policy="committed_intent",
        slot_capacities={"men": 2, "women": 1},
        slot_labels={"men": "Men", "women": "Women"},
        members={
            "makoto": CastMemberState(status=CastStatus.ACTIVE, slot_group="men", sequence=0, activated_minute=0),
            "yuki": CastMemberState(status=CastStatus.UPCOMING, slot_group="women", sequence=0),
        },
    )
    return state


def test_journal_hides_upcoming_character_goal_history(client, user1_token):
    """THE Phase 1.4 regression test: an UPCOMING (unarrived) character's
    authored goal must never appear in the journal, even though it exists in
    state.characters exactly like an active character's goal does."""
    state = _make_journal_state_with_lifecycle()
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

    texts = {e["text"] for e in entries}
    assert "secretly plotting to leave the house" not in texts, (
        "an UPCOMING character's authored goal leaked into the journal"
    )
    assert "win Aiko's trust" in texts, "the ACTIVE character's own goal must still appear"

    character_ids = {e["character_id"] for e in entries}
    assert "yuki" not in character_ids, "the unarrived character's key must not appear at all"


def test_journal_hides_disposition_targeting_an_upcoming_character(client, user1_token):
    """A relationship edge whose TARGET (not subject) is an unarrived
    character must also be hidden — otherwise the unarrived character's
    existence/name leaks through the other side of the edge."""
    state = _make_journal_state_with_lifecycle()
    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.get_session") as engine_get_session:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        engine_get_session.return_value = {"state": state}
        resp = client.get(
            "/api/user/sessions/sess1/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    entries = resp.json()["entries"]
    texts = {e["text"] for e in entries}
    assert "has not met" not in texts, "a disposition targeting an unarrived character leaked"
    target_ids = {e["target_id"] for e in entries}
    assert "yuki" not in target_ids


def test_journal_shows_departed_character_history_not_just_active(client, user1_token):
    """The audit's other half: "currently active" alone is NOT the right
    check. A DEPARTED resident's legitimately-learned history must stay
    visible - only UPCOMING (never met) is hidden."""
    from backend.app.engine.state import Character, init_state
    from backend.app.engine.social_traits import EvolvingTrait
    from backend.app.engine.character_graph import CharacterGraph, CharacterType
    from backend.app.engine.cast_lifecycle import CastLifecycleState, CastMemberState, CastStatus

    state = init_state()
    state.character_graph = CharacterGraph()
    departed_ch = Character(key="uchi", name="Uchi", character_type=CharacterType.NPC)
    departed_ch.goal = EvolvingTrait(kind="goal", subject_id="uchi")
    departed_ch.goal.set_initial("became a hairstylist for the group", minute=50, source="author")
    state.characters = {"uchi": departed_ch}
    state.cast_lifecycle = CastLifecycleState(
        enabled=True,
        arrival_location_id="living_room",
        replacement_policy="same_slot_next",
        departure_policy="committed_intent",
        slot_capacities={"men": 1},
        slot_labels={"men": "Men"},
        members={
            "uchi": CastMemberState(
                status=CastStatus.DEPARTED, slot_group="men", sequence=0,
                activated_minute=0, departed_minute=200, departure_reason="moved out",
            ),
        },
    )

    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.get_session") as engine_get_session:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        engine_get_session.return_value = {"state": state}
        resp = client.get(
            "/api/user/sessions/sess1/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    entries = resp.json()["entries"]
    texts = {e["text"] for e in entries}
    assert "became a hairstylist for the group" in texts, (
        "a DEPARTED character's legitimately-learned history must remain visible, "
        "not just currently-active characters"
    )


def test_journal_hides_goal_history_predating_character_arrival(client, user1_token):
    """A goal history entry timestamped BEFORE the character's own
    activated_minute is pre-authored content that predates the moment they
    actually entered the scene — must be hidden even though the character
    itself is currently active/visible."""
    from backend.app.engine.state import Character, init_state
    from backend.app.engine.social_traits import EvolvingTrait
    from backend.app.engine.character_graph import CharacterGraph, CharacterType
    from backend.app.engine.cast_lifecycle import CastLifecycleState, CastMemberState, CastStatus

    state = init_state()
    state.character_graph = CharacterGraph()
    ch = Character(key="misaki", name="Misaki", character_type=CharacterType.NPC)
    ch.goal = EvolvingTrait(kind="goal", subject_id="misaki")
    # Authored starting value at minute 0 - but misaki doesn't actually
    # arrive until minute 500 (a mid-game replacement arrival).
    ch.goal.set_initial("pre-authored backstory goal", minute=0, source="author")
    ch.goal.propose_change(
        "goal stated after actually arriving", minute=600, reason="post-arrival",
        confidence=0.9, entry_id="misaki_goal_2",
    )
    state.characters = {"misaki": ch}
    state.cast_lifecycle = CastLifecycleState(
        enabled=True,
        arrival_location_id="living_room",
        replacement_policy="same_slot_next",
        departure_policy="committed_intent",
        slot_capacities={"women": 1},
        slot_labels={"women": "Women"},
        members={
            "misaki": CastMemberState(status=CastStatus.ACTIVE, slot_group="women", sequence=1, activated_minute=500),
        },
    )

    with patch("backend.app.api.user_sessions.SessionRepo.get_session", new_callable=AsyncMock) as sess_mock, \
         patch("backend.app.api.user_sessions.get_session") as engine_get_session:
        sess_mock.return_value = {"id": "sess1", "user_id": "uid1"}
        engine_get_session.return_value = {"state": state}
        resp = client.get(
            "/api/user/sessions/sess1/journal",
            headers={"Authorization": f"Bearer {user1_token}"},
        )
    entries = resp.json()["entries"]
    texts = {e["text"] for e in entries}
    assert "pre-authored backstory goal" not in texts, (
        "goal history predating the character's actual arrival minute leaked"
    )
    assert "goal stated after actually arriving" in texts


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
