"""
Unit tests for backend/app/api/prompt_engine.py

The Prompt Engine orchestrates all raw context (state, knowledge, history, flags)
and transforms it into a fully-assembled LLM prompt, then dispatches the API call.

Covers: chat handler flow, debug/truth/map/Chinese/epistemic toggles, name
extraction, canonical projection, epistemic seeding, knowledge-resolution
updates, and Chinese translation mode.
"""

import types
import re
import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.conftest import first_story_id, first_story_folder, all_stories

# Auto-discover the first available story for all tests
STORY_ID = first_story_id()
STORY_FOLDER = first_story_folder()


# ============================================================================
# Shared fixtures
# ============================================================================

@pytest.fixture()
def client(monkeypatch):
    """Create a FastAPI TestClient with network calls mocked."""
    # Import inside fixture so our monkeypatches apply before first use.
    from backend.app.api import prompt_engine as pe_mod

    # Spy to assert when the LLM (OpenAI) is called.
    spy = types.SimpleNamespace(calls=0)
    pe_mod._TEST_OPENAI_POST_SPY = spy

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(pe_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock single-call turn extractor to not call LLM
    from backend.app.engine.extractors.turn_extractor import TurnExtraction
    async def _mock_extract(*args, **kwargs):
        return TurnExtraction()
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_extract, raising=False)

    # Mock httpx.AsyncClient so /api/chat never hits OpenAI.
    class _FakeResp:
        status_code = 200

        def json(self):
            # Reply must include a valid [[STATE]] tag so state parsing passes.
            return {
                "choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            spy.calls += 1
            return _FakeResp()

    monkeypatch.setattr(pe_mod.httpx, "AsyncClient", _FakeAsyncClient)

    # Suppress background dialogue extraction so it doesn't fire extra LLM calls.
    async def _noop_extract(*args, **kwargs):
        return []
    monkeypatch.setattr(pe_mod, "extract_facts_from_message", _noop_extract, raising=False)

    from backend.app import main
    return TestClient(main.app)


@pytest.fixture()
def client_with_translation(monkeypatch):
    """Create a TestClient with translation and prompt engine mocked appropriately."""
    from backend.app.api import prompt_engine as pe_mod

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(pe_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock single-call turn extractor
    from backend.app.engine.extractors.turn_extractor import TurnExtraction
    async def _mock_extract(*args, **kwargs):
        return TurnExtraction()
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_extract, raising=False)

    # Track translation calls
    translation_spy = types.SimpleNamespace(calls=0, last_input=None, return_value="这是翻译的回复")

    async def mock_translate(text: str) -> str:
        translation_spy.calls += 1
        translation_spy.last_input = text
        return translation_spy.return_value

    monkeypatch.setattr(pe_mod, "_translate_to_chinese", mock_translate)

    # Mock httpx.AsyncClient for LLM calls
    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "I understand.\n\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
                "usage": {"total_tokens": 1},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    from backend.app.main import app
    client = TestClient(app)

    return client, translation_spy, pe_mod


# ============================================================================
# Core chat handler flow tests
# ============================================================================

def test_chat_newgame_and_turn(client):
    # Start a new game
    r = client.post("/api/chat", json={"session_id": "s1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data

    # Do a turn (will use mocked OpenAI response)
    r2 = client.post("/api/chat", json={"session_id": "s1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "reply" in data2
    assert "[[STATE]]" not in data2["reply"]  # tag should be stripped
    assert not re.match(r"^\[\d{4}-\d{2}-\d{2} ", data2["reply"])  # no leading timestamp


def test_prompt_debug_not_leaked_to_ordinary_players(client, monkeypatch):
    """Live-verified bug (found manually against the deployed beta site while
    playtesting The Common Room): /api/chat previously returned the FULL
    assembled system prompt (all canonical facts, character secrets,
    retrieval chunk text) to every caller unconditionally, on every turn -
    completely bypassing the A03 operator gate that was supposed to protect
    exactly this kind of data (it only gated separate debug/authoring
    *routes*, not this field on the always-public /chat route). An ordinary
    player's browser devtools Network tab would show it even though the
    frontend UI never renders it. `prompt_debug` must be absent for any
    request that isn't an authenticated operator - even one that has
    toggled the player-facing "[D]" debug_mode command, since that toggle
    has no auth at all and must not be conflated with the real operator
    trust boundary."""
    monkeypatch.delenv("DEBUG_TOOLS_ENABLED", raising=False)
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)

    sid = "leak_check_1"
    r = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200
    assert "prompt_debug" not in r.json()

    # Even with the player-facing "[D]" debug_mode toggle enabled (unauthenticated,
    # anyone can send it), prompt_debug must still be withheld.
    r_toggle = client.post("/api/chat", json={"session_id": sid, "message": "[D]"})
    assert r_toggle.status_code == 200
    r2 = client.post("/api/chat", json={"session_id": sid, "message": "hello"})
    assert r2.status_code == 200
    assert "prompt_debug" not in r2.json()

    # Also withheld when DEBUG_TOOLS_ENABLED is on but no/wrong token supplied.
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "correct-token")
    r3 = client.post("/api/chat", json={"session_id": sid, "message": "hello again"})
    assert "prompt_debug" not in r3.json()
    r4 = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "hello again"},
        headers={"X-Operator-Token": "wrong-token"},
    )
    assert "prompt_debug" not in r4.json()


def test_prompt_debug_present_for_authenticated_operator(client, monkeypatch):
    """The operator/debug/playback tooling (backend/app/api/debug_engine.py)
    legitimately depends on receiving prompt_debug from /api/chat for
    grading and playback inspection - it must still get it when it presents
    a valid operator token, mirroring the token debug_engine.py's own
    internal httpx calls now send."""
    monkeypatch.setenv("DEBUG_TOOLS_ENABLED", "1")
    monkeypatch.setenv("OPERATOR_TOKEN", "correct-token")

    sid = "leak_check_2"
    r = client.post(
        "/api/chat",
        # __cmd_newgame__ just returns the static opening text without an
        # LLM call, so it never produces a prompt_debug (matches the
        # unauthenticated-path behavior too) - only a real turn does.
        json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"},
        headers={"X-Operator-Token": "correct-token"},
    )
    assert r.status_code == 200
    assert "prompt_debug" not in r.json()

    r2 = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "hello"},
        headers={"X-Operator-Token": "correct-token"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert "prompt_debug" in body
    assert "system_prompt_preview" in body["prompt_debug"]


@pytest.mark.parametrize("story", all_stories(), ids=lambda s: s["id"])
def test_every_catalogued_story_initializes_end_to_end(client, story):
    """A05 regression: every story returned by the /api/stories catalogue
    must actually initialize through the runtime loader (discovery -> load
    -> init game state -> opening reply), not just parse as JSON.

    Before the A05 fix, blackout_manor/neon_district/the_last_session were
    advertised by the catalogue (declared `id` read directly from the JSON)
    but failed to load at runtime because load_story() guessed filenames
    instead of using the declared id, and their canonical_facts used a
    `statement` key the seeder didn't read (so even a name-based fix alone
    would have silently produced empty canonical facts).
    """
    story_id = story["id"]
    r = client.post(
        "/api/chat",
        json={"session_id": f"catalogue_{story_id}", "message": f"__cmd_newgame__:{story_id}|M|Chris"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "reply" in data
    assert data["reply"].strip(), f"story {story_id} produced an empty opening reply"

    from backend.app.api import prompt_engine as pe_mod
    sess = pe_mod.SESSIONS.get(f"catalogue_{story_id}")
    assert sess is not None
    state = sess["state"]
    assert state is not None
    assert state.story == story_id

    # If the story declares canonical facts, confirm they actually seeded
    # with non-empty content (guards against the `statement`-vs-`content`
    # key mismatch reproduced above).
    canonical_cfg = (story["config"].get("epistemic_seed") or {}).get("canonical_facts") or []
    if canonical_cfg:
        seeded = getattr(state, "canonical_facts", []) or []
        assert seeded, f"story {story_id} declares canonical_facts but none were seeded"
        assert all((f.content or "").strip() for f in seeded), (
            f"story {story_id} seeded canonical facts with empty content"
        )


def test_master_prompt_engine_orchestration_flow(monkeypatch):
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.extractors.turn_extractor import TurnExtraction, TurnKnowledgeResolution

    spy = types.SimpleNamespace(calls=0)
    pe_mod._TEST_OPENAI_POST_SPY = spy

    def _retrieve_stub(*args, **kwargs):
        return ([{"chunk_id": "c_master", "text": "The red door leads to the kitchen.", "type": "scene"}], {})

    monkeypatch.setattr(pe_mod, "retrieve_knowledge", _retrieve_stub, raising=False)

    async def _extract_stub(*args, **kwargs):
        return TurnExtraction(
            movement_intent="MOVE",
            destination_id="kitchen",
            confidence=0.95,
            previous_reply_location_id="apartment",
            previous_reply_speakers=["jennie"],
            knowledge_updates=[
                TurnKnowledgeResolution(
                    chunk_id="c_master",
                    knows=True,
                    confidence=0.92,
                    reason="speaker directly referenced the door location",
                )
            ],
        )

    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _extract_stub, raising=False)

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "We head to the kitchen.\n\n[[STATE]]{\"emotion\":\"wary\",\"rel_delta\":1}[[/STATE]]"}}],
                "usage": {"total_tokens": 3},
            }

        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            spy.calls += 1
            return _FakeResp()

    monkeypatch.setattr(pe_mod.httpx, "AsyncClient", _FakeAsyncClient)

    from backend.app import main
    client = TestClient(main.app)

    sid = "master_flow"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|F|Master"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "Can we go to the kitchen now?"})
    assert r1.status_code == 200
    body = r1.json()
    assert "reply" in body
    assert "[[STATE]]" not in body["reply"]
    assert spy.calls >= 1

    state = pe_mod.SESSIONS[sid]["state"]
    assert int(getattr(state, "turns", 0)) >= 1
    assert state.last_turn_user_msg == "Can we go to the kitchen now?"
    assert isinstance(state.last_turn_assistant_reply, str)
    assert state.last_turn_assistant_reply

    latest_scene = state.latest_scene_knowledge()
    assert latest_scene is not None
    entries = list(getattr(state, "scene_knowledge_entries", []) or [])
    assert any(
        str(getattr(entry, "payload", {}).get("source", "")) == "single_call_turn_extractor"
        for entry in entries
    )
    assert any("jennie" in (getattr(entry, "speakers", []) or []) for entry in entries)

    retrieved = list(getattr(state, "last_turn_retrieved_chunks", []) or [])
    assert any(str(c.get("chunk_id", "")) == "c_master" for c in retrieved)


def test_debug_mode_toggle_no_llm_on_toggle_and_appends_debug_box(client):
    from backend.app.api import prompt_engine as pe_mod

    # Start a new game so a normal turn hits the LLM mock.
    r = client.post("/api/chat", json={"session_id": "dbg1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r.status_code == 200

    spy = getattr(pe_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Enter debug mode (must NOT call LLM)
    r2 = client.post("/api/chat", json={"session_id": "dbg1", "message": "[D]"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "ENTERING DEBUG MODE" in data2["reply"]
    assert spy.calls == base_calls

    # Normal turn should call LLM and return debug_box as structured data
    r3 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "debug_box" in data3, "debug_box should be in response when debug mode is on"
    assert "timestamp" in data3["debug_box"]
    assert "location" in data3["debug_box"]
    assert "people_present" in data3["debug_box"]
    assert "DEBUG INFO" not in data3["reply"], "debug info should not be in reply text anymore"
    assert not re.match(r"^\[\d{4}-\d{2}-\d{2} ", data3["reply"])  # no leading timestamp
    assert spy.calls == base_calls + 1

    # Exit debug mode (must NOT call LLM)
    r4 = client.post("/api/chat", json={"session_id": "dbg1", "message": "(DEBUG)"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "EXITING DEBUG MODE" in data4["reply"]
    assert spy.calls == base_calls + 1

    # Next normal turn should not have debug_box
    r5 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello again"})
    assert r5.status_code == 200
    data5 = r5.json()
    assert "debug_box" not in data5, "debug_box should not be present when debug mode is off"
    assert spy.calls == base_calls + 2


def test_debug_toggle_strips_leading_gt(client):
    from backend.app.api import prompt_engine as pe_mod

    # Start a new game so the "regular turn" path is active for subsequent messages.
    r0 = client.post("/api/chat", json={"session_id": "gt1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    spy = getattr(pe_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Leading '>' should be scrubbed globally, so this should toggle debug mode.
    r1 = client.post("/api/chat", json={"session_id": "gt1", "message": "> [D]"})
    assert r1.status_code == 200
    data1 = r1.json()
    assert "ENTERING DEBUG MODE" in data1["reply"]
    assert spy.calls == base_calls  # toggle must NOT call OpenAI

    # A normal message should now call the OpenAI mock and return debug_box.
    r2 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "debug_box" in data2, "debug_box should be in response when debug mode is on"
    assert "timestamp" in data2["debug_box"]
    assert spy.calls == base_calls + 1

    # Exit debug mode with a leading '>' as well.
    r3 = client.post("/api/chat", json={"session_id": "gt1", "message": "> (DEBUG)"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "EXITING DEBUG MODE" in data3["reply"]
    assert spy.calls == base_calls + 1  # toggle must NOT call OpenAI

    # Next normal turn should not have debug_box.
    r4 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello again"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "debug_box" not in data4, "debug_box should not be present when debug mode is off"
    assert spy.calls == base_calls + 2


def test_debug_box_speakers_do_not_include_location_as_name(client):
    # Start a new game
    r0 = client.post("/api/chat", json={"session_id": "spk1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode
    r1 = client.post("/api/chat", json={"session_id": "spk1", "message": "[D]"})
    assert r1.status_code == 200

    # Normal turn to get debug_box
    r2 = client.post("/api/chat", json={"session_id": "spk1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()

    assert "debug_box" in data2
    debug_box = data2["debug_box"]
    assert "speakers" in debug_box

    # Ensure the location isn't mistakenly treated as a speaker name.
    if debug_box["speakers"]:
        for name in debug_box["speakers"]:
            assert "Apartment" not in name, f"Location leaked into speakers: {name}"


def test_scene_knowledge_queue_updates_each_turn(client):
    import backend.app.api.prompt_engine as pe_mod

    sid = "sceneq1"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "hello"})
    assert r1.status_code == 200

    st = pe_mod.SESSIONS[sid]["state"]
    assert st.scene_knowledge_entries
    latest = st.latest_scene_knowledge()
    assert latest is not None
    assert isinstance(latest.speakers, list)
    assert isinstance(latest.people_present, list)
    assert "source" in latest.payload


def test_debug_box_rendering_structured(client):
    """Test that debug box is returned as structured data, not ASCII art in reply."""
    r0 = client.post("/api/chat", json={"session_id": "box1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode — toggle notices still use ASCII _box() in reply
    r1 = client.post("/api/chat", json={"session_id": "box1", "message": "[D]"})
    assert r1.status_code == 200
    reply1 = r1.json()["reply"]
    assert "ENTERING DEBUG MODE" in reply1

    # Normal turn should return debug_box as structured data (not in reply text)
    r2 = client.post("/api/chat", json={"session_id": "box1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()

    # debug_box must be a dict with expected keys
    assert "debug_box" in data2
    box = data2["debug_box"]
    assert isinstance(box, dict)
    assert "timestamp" in box
    assert "location" in box
    # Reply text should NOT contain ASCII debug box
    assert "┌" not in data2["reply"]
    assert "DEBUG INFO" not in data2["reply"]


# ============================================================================
# Utility function tests
# ============================================================================

def test_apply_placeholders_and_sanitize_honorific_terms():
    from backend.app.engine.state import init_state
    import backend.app.api.prompt_engine as pe_mod

    st = init_state()
    st.player_name = "Chris"
    st.gender = "M"
    # Language config lives in story_cfg — provide it like a real story would
    st.story_cfg = {"language": {"honorifics": {"M": "oppa", "F": "unnie"}, "forbidden_honorifics": ["oppa", "unni", "unnie", "eonnie"]}}
    out = pe_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st)
    assert "Chris" in out
    assert "oppa" in out  # honorific placeholder is meta-only for opening

    # At low relationship, sanitize should strip forbidden terms
    st.relationship = 0
    st.user.display_name = "Chris"
    cleaned = pe_mod.sanitize_honorific_terms("hello oppa unnie", st)
    assert "oppa" not in cleaned.lower()
    assert "unnie" not in cleaned.lower()

    # Without language config, placeholders produce empty honorific and sanitize is a no-op
    st2 = init_state()
    st2.player_name = "Chris"
    st2.gender = "M"
    st2.story_cfg = {}
    out2 = pe_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st2)
    assert "Chris" in out2
    assert "{{HONORIFIC}}" not in out2  # placeholder replaced even if empty


def test_name_extraction_and_confirmation():
    from backend.app.engine.state import init_state
    import backend.app.api.prompt_engine as pe_mod

    st = init_state()
    name = pe_mod.extract_user_name_from_text("my name is alice")
    assert name == "Alice"

    # confirmation should set names
    st.last_assistant_guess_name = "Bob"
    pe_mod.handle_name_confirmation("yes", st)
    assert st.user.formal_name == "Bob"


# ============================================================================
# Map toggle tests
# ============================================================================

def test_map_toggle_shows_locations_from_world(client):
    """Test that [M] or [MAP] command shows available locations."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map1", "message": "__cmd_newgame__:" + STORY_ID + "|M|Player"})
    assert r0.status_code == 200

    # Toggle map with [M]
    r1 = client.post("/api/chat", json={"session_id": "map1", "message": "[M]"})
    assert r1.status_code == 200
    resp1 = r1.json()
    reply1 = resp1["reply"]

    # Should show World Map box with locations (no LLM call)
    assert "World Map" in reply1
    # Should contain at least one location name from the story world
    assert len(reply1) > 30, "Map should contain location data"

    # Verify no LLM tokens were used (early exit, same as [D])
    assert resp1.get("usage", {}).get("total_tokens", 0) == 0


def test_map_toggle_case_insensitive(client):
    """Test that map toggle is case-insensitive."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map2", "message": "__cmd_newgame__:" + STORY_ID + "|F|Player"})
    assert r0.status_code == 200

    # Test various forms: [MAP], (MAP), [m], (map)
    for msg in ["[MAP]", "(MAP)", "[m]", "(map)"]:
        r = client.post("/api/chat", json={"session_id": "map2", "message": msg})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "World Map" in reply, f"Map toggle failed for: {msg}"


def test_map_toggle_token_detection():
    """Test _is_map_toggle() function directly with various inputs."""
    import backend.app.api.prompt_engine as pe_mod

    # Valid map toggle tokens
    assert pe_mod._is_map_toggle("[M]")
    assert pe_mod._is_map_toggle("[m]")
    assert pe_mod._is_map_toggle("(M)")
    assert pe_mod._is_map_toggle("(m)")
    assert pe_mod._is_map_toggle("[MAP]")
    assert pe_mod._is_map_toggle("[map]")
    assert pe_mod._is_map_toggle("(MAP)")
    assert pe_mod._is_map_toggle("(map)")

    # With surrounding whitespace
    assert pe_mod._is_map_toggle("  [M]  ")
    assert pe_mod._is_map_toggle("\t[MAP]\t")

    # Invalid tokens (should not match)
    assert not pe_mod._is_map_toggle("[D]")  # Debug token
    assert not pe_mod._is_map_toggle("[C]")  # Chinese token
    assert not pe_mod._is_map_toggle("map")  # No brackets
    assert not pe_mod._is_map_toggle("[X]")  # Unknown token
    assert not pe_mod._is_map_toggle("")     # Empty string
    assert not pe_mod._is_map_toggle("hello world")  # Normal message


def test_map_toggle_no_llm_call(client):
    """Verify that MAP toggle does not invoke LLM (0 tokens)."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "__cmd_newgame__:" + STORY_ID + "|M|Test"})
    assert r0.status_code == 200

    # Normal turn should use LLM
    r1 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "hello"})
    assert r1.status_code == 200
    tokens_normal = r1.json().get("usage", {}).get("total_tokens", 0)
    assert tokens_normal > 0, "Normal turn should use LLM tokens"

    # MAP toggle should NOT use LLM
    r2 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "[M]"})
    assert r2.status_code == 200
    tokens_map = r2.json().get("usage", {}).get("total_tokens", 0)
    assert tokens_map == 0, "MAP toggle should not consume LLM tokens"


def test_map_toggle_returns_boxed_format(client):
    """Verify that MAP toggle returns properly formatted box output."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_box", "message": "__cmd_newgame__:" + STORY_ID + "|F|BoxTest"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_box", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    # Verify box structure
    assert "┌" in reply or "World Map" in reply, "Should have box or title"
    assert "World Map" in reply, "Should have title header"
    # Box corners for proper formatting
    if "┌" in reply:
        assert "┐" in reply, "Top right corner missing"
        assert "└" in reply, "Bottom left corner missing"
        assert "┘" in reply, "Bottom right corner missing"


def test_map_toggle_shows_all_locations(client):
    """Verify that MAP toggle lists all world locations."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "__cmd_newgame__:" + STORY_ID + "|M|AllLocs"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    # Should contain multiple locations from the story world
    location_lines = [line for line in reply.split('\n') if line.strip() and '─' not in line and 'World' not in line]
    assert len(location_lines) > 3, f"Should list multiple locations, got: {reply}"


def test_map_toggle_without_world_runtime(client, monkeypatch):
    """Test MAP toggle behavior when world_runtime is not available."""
    import backend.app.api.prompt_engine as pe_mod

    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_world", "message": "__cmd_newgame__:" + STORY_ID + "|F|NoWorld"})
    assert r0.status_code == 200

    # Remove world_runtime from session state
    state = pe_mod.SESSIONS["map_no_world"]["state"]
    state.world_runtime = None

    # Request map - should show "No map available"
    r1 = client.post("/api/chat", json={"session_id": "map_no_world", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]

    assert "World Map" in reply
    assert "No map available" in reply or "not available" in reply.lower()


def test_map_toggle_with_whitespace_variants(client):
    """Test MAP toggle with extra whitespace."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_ws", "message": "__cmd_newgame__:" + STORY_ID + "|M|Whitespace"})
    assert r0.status_code == 200

    # Test with leading/trailing whitespace
    test_cases = [
        "  [M]",
        "[M]  ",
        "  [M]  ",
        "\t[MAP]\t",
        "  (m)  ",
    ]

    for msg in test_cases:
        r = client.post("/api/chat", json={"session_id": "map_ws", "message": msg})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "World Map" in reply, f"MAP toggle failed with whitespace: '{msg}'"


def test_map_toggle_multiple_calls_consistent(client):
    """Test that multiple MAP toggle calls return consistent results."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_consistent", "message": "__cmd_newgame__:" + STORY_ID + "|F|Consistent"})
    assert r0.status_code == 200

    # Request map three times
    replies = []
    for _ in range(3):
        r = client.post("/api/chat", json={"session_id": "map_consistent", "message": "[M]"})
        assert r.status_code == 200
        replies.append(r.json()["reply"])

    # All three should be identical
    assert replies[0] == replies[1], "First and second map calls differ"
    assert replies[1] == replies[2], "Second and third map calls differ"


def test_map_toggle_mixed_with_normal_turns(client):
    """Test MAP toggle interleaved with normal game turns."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "__cmd_newgame__:" + STORY_ID + "|M|Mixed"})
    assert r0.status_code == 200

    # Normal turn
    r1 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "hello"})
    assert r1.status_code == 200
    assert "World Map" not in r1.json()["reply"], "Normal turn should not show map"

    # MAP toggle
    r2 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "[M]"})
    assert r2.status_code == 200
    assert "World Map" in r2.json()["reply"], "MAP toggle should show map"

    # Another normal turn
    r3 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "what happened?"})
    assert r3.status_code == 200
    assert "World Map" not in r3.json()["reply"], "Normal turn should not show map"

    # MAP toggle again
    r4 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "[MAP]"})
    assert r4.status_code == 200
    assert "World Map" in r4.json()["reply"], "Second MAP toggle should show map"


def test_map_toggle_includes_world_map_image_path(client):
    """Test that MAP toggle response includes world_map_image path when available."""
    # Start new game with first discovered story
    r0 = client.post("/api/chat", json={"session_id": "map_img", "message": "__cmd_newgame__:" + STORY_ID + "|M|ImgTest"})
    assert r0.status_code == 200

    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_img", "message": "[M]"})
    assert r1.status_code == 200
    resp = r1.json()

    # Verify response includes world map image path (auto-discovered)
    assert "world_map_image" in resp, "Response should include world_map_image field"
    assert resp["world_map_image"].endswith(".png"), "Image path should be a PNG file"
    assert STORY_FOLDER in resp["world_map_image"], f"Image path should reference story folder {STORY_FOLDER}"


# ============================================================================
# Story loader / world config tests
# ============================================================================

def test_story_loader_finds_story_in_subdirectory(client):
    """Test that story loader can find stories in subdirectories."""
    r = client.post("/api/chat", json={"session_id": "subdir_test", "message": "__cmd_newgame__:" + STORY_ID + "|F|SubdirTest"})
    assert r.status_code == 200
    opening = r.json()

    # Verify story loaded correctly (opening should be present)
    assert "reply" in opening
    assert len(opening["reply"]) > 100, "Opening text should be present and substantial"


def test_story_with_world_config_loads_correctly(client):
    """Test that story with world config loads and initializes world runtime."""
    r0 = client.post("/api/chat", json={"session_id": "world_cfg", "message": "__cmd_newgame__:" + STORY_ID + "|M|WorldCfg"})
    assert r0.status_code == 200

    # Verify world is initialized by checking state
    import backend.app.api.prompt_engine as pe_mod
    state = pe_mod.SESSIONS["world_cfg"]["state"]

    # World should be loaded
    assert state.world_runtime is not None, "World runtime should be loaded from story config"
    assert state.world_runtime.world_graph is not None, "World graph should be initialized"
    assert len(state.world_runtime.world_graph.locations) > 0, "World should have locations"


def test_file_consolidation_single_location(client):
    """Test that all story files are in the expected story folder (auto-discovered).

    A05 note: story JSON filenames are NOT required to match the story's
    declared `id` (e.g. blackout_manor's file is 3_story.json) — resolution
    goes through build_story_registry(), not filename-guessing. This test
    resolves the story's actual path via that registry rather than assuming
    a {id}.json / {id}_story.json naming convention.
    """
    import os
    from backend.app.engine.story_loader import find_story_dir, build_story_registry

    # Verify old duplicate backend/stories directory doesn't exist
    assert not os.path.exists("backend/stories"), "Old backend/stories duplicate should be removed"

    # Auto-discover the first story's folder and verify it exists
    story_dir = find_story_dir(STORY_ID)
    assert story_dir is not None, f"Story folder for {STORY_ID} should exist"

    full_dir = os.path.join("backend", "app", "stories", story_dir)
    assert os.path.isdir(full_dir), f"Story directory {full_dir} should exist"

    # Verify the story JSON resolves via the content registry (by declared id).
    entry = build_story_registry().get(STORY_ID)
    assert entry is not None, f"Story JSON for {STORY_ID} should be in the registry"
    assert os.path.isfile(entry["path"]), f"Story JSON for {STORY_ID} should exist at {entry['path']}"

    # Verify a world JSON exists ({id}_world.json)
    world_json = os.path.join(full_dir, f"{STORY_ID}_world.json")
    assert os.path.isfile(world_json), f"World JSON should exist at {world_json}"

    # Verify a map image exists ({folder}.png convention)
    map_png = os.path.join(full_dir, f"{story_dir}.png")
    assert os.path.isfile(map_png), f"Map image should exist at {map_png}"


# ============================================================================
# Knowledge resolution tests
# ============================================================================

def test_knowledge_resolution_updates_belief_and_transient(client, monkeypatch):
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.extractors.turn_extractor import TurnExtraction, TurnKnowledgeResolution

    async def _mock_turn_extract(*args, **kwargs):
        return TurnExtraction(
            movement_intent="NONE",
            knowledge_updates=[
                TurnKnowledgeResolution(
                    chunk_id="c_unknown",
                    knows=True,
                    confidence=0.88,
                    reason="dialogue indicates familiarity",
                )
            ],
        )

    monkeypatch.setattr(
        pe_mod,
        "retrieve_knowledge",
        lambda *args, **kwargs: ([{"chunk_id": "c_unknown", "text": "The hidden hallway has a red door.", "type": "scene"}], {}),
        raising=False,
    )
    monkeypatch.setattr(pe_mod._TURN_EXTRACTOR, "extract", _mock_turn_extract, raising=False)

    sid = "kr1"
    r0 = client.post("/api/chat", json={"session_id": sid, "message": "__cmd_newgame__:" + STORY_ID + "|M|Chris"})
    assert r0.status_code == 200

    r1 = client.post("/api/chat", json={"session_id": sid, "message": "tell me about the hallway"})
    assert r1.status_code == 200
    r2 = client.post("/api/chat", json={"session_id": sid, "message": "and what else?"})
    assert r2.status_code == 200
    body = r2.json()
    assert "knowledge_resolution_updates" in body
    assert body["knowledge_resolution_updates"][0]["chunk_id"] == "c_unknown"
    assert body["knowledge_resolution_updates"][0]["knows"] is True

    st = pe_mod.SESSIONS[sid]["state"]
    speaker = (st.main_character_id or "").strip().lower()

    claims = st.get_belief_state(speaker).claims
    assert any(getattr(c, "id", "") == f"kr::{speaker}::c_unknown" for c in claims)

    entries = st.transient_entries
    matched = [e for e in entries if "KnowledgeResolution" in (getattr(e, "text", "") or "") and "chunk=c_unknown" in (getattr(e, "text", "") or "")]
    assert matched
    assert matched[-1].turns_remaining == 8


# ============================================================================
# Chinese toggle detection tests
# ============================================================================

def test_is_chinese_toggle_detects_all_formats():
    """Test that _is_chinese_toggle recognizes all toggle formats."""
    import backend.app.api.prompt_engine as pe_mod

    # Test all supported formats (case insensitive)
    assert pe_mod._is_chinese_toggle("[C]")
    assert pe_mod._is_chinese_toggle("(C)")
    assert pe_mod._is_chinese_toggle("[CHINESE]")
    assert pe_mod._is_chinese_toggle("(CHINESE)")
    assert pe_mod._is_chinese_toggle("[c]")  # lowercase
    assert pe_mod._is_chinese_toggle("(c)")  # lowercase
    assert pe_mod._is_chinese_toggle("[chinese]")  # lowercase
    assert pe_mod._is_chinese_toggle("(chinese)")  # lowercase

    # Test false negatives
    assert not pe_mod._is_chinese_toggle("[D]")
    assert not pe_mod._is_chinese_toggle("Chinese")  # no brackets
    assert not pe_mod._is_chinese_toggle("C")  # no brackets
    assert not pe_mod._is_chinese_toggle("hello")
    assert not pe_mod._is_chinese_toggle("")
    assert not pe_mod._is_chinese_toggle(None)


def test_chinese_toggle_is_case_insensitive():
    """Verify that Chinese toggle is case-insensitive."""
    import backend.app.api.prompt_engine as pe_mod

    test_cases = [
        "[C]", "[c]",
        "(C)", "(c)",
        "[CHINESE]", "[chinese]", "[ChInEsE]",
        "(CHINESE)", "(chinese)", "(ChInEsE)",
    ]

    for test_input in test_cases:
        assert pe_mod._is_chinese_toggle(test_input), f"Failed for: {test_input}"


# ============================================================================
# Chinese toggle session state tests
# ============================================================================

def test_chinese_toggle_enters_mode(client_with_translation):
    """Test that [C] command enters Chinese mode."""
    client, _, _ = client_with_translation

    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Toggle Chinese mode on
    resp = client.post("/api/chat", json={
        "session_id": "cn_test1",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should see Chinese mode entrance message
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_chinese_toggle_exits_mode(client_with_translation):
    """Test that [C] command exits Chinese mode when already on."""
    client, _, _ = client_with_translation

    # Start a new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enter Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Exit Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test2",
        "message": "[C]"
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should see exit message
    assert "退出中文模式" in reply or "exit" in reply.lower()


def test_chinese_mode_persists_in_session(client_with_translation):
    """Test that Chinese mode flag persists across turns."""
    client, translation_spy, _ = client_with_translation

    # Start new game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset translation spy
    translation_spy.calls = 0

    # Send a normal message - should trigger translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test3",
        "message": "hello"
    })
    assert resp.status_code == 200

    # Should have called translation function
    assert translation_spy.calls > 0, "Translation should be called when in Chinese mode"


# ============================================================================
# Translation function tests
# ============================================================================

def test_translate_to_chinese_preserves_formatting(monkeypatch):
    """Test that translation preserves formatting markers."""
    from backend.app.api import prompt_engine as pe_mod

    # Create a mock OpenAI response with formatting
    class _FakeResp:
        status_code = 200
        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": "**你好** *世界* 和 \"引号\"\n\n新行文本"
                    }
                }],
                "usage": {"total_tokens": 10},
            }
        @property
        def text(self):
            return "ok"

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    # Run translation
    result = asyncio.run(pe_mod._translate_to_chinese("**Hello** *world* and \"quotes\"\n\nNew line text"))

    # Should preserve structure
    assert "**" in result  # bold markers
    assert "*" in result   # italic markers
    assert "\"" in result  # quotes
    assert "\n\n" in result  # line breaks


def test_translate_to_chinese_handles_empty_text(monkeypatch):
    """Test that translation handles empty or whitespace text."""
    from backend.app.api import prompt_engine as pe_mod

    # Empty string
    result = asyncio.run(pe_mod._translate_to_chinese(""))
    assert result == ""

    # Whitespace only
    result = asyncio.run(pe_mod._translate_to_chinese("   \n  \t  "))
    assert result == "   \n  \t  "


def test_translate_to_chinese_fallback_on_error(monkeypatch):
    """Test that translation falls back to original text on error."""
    from backend.app.api import prompt_engine as pe_mod

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            raise Exception("Network error")

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    original = "Hello world"
    result = asyncio.run(pe_mod._translate_to_chinese(original))

    # Should return original text on error
    assert result == original


def test_translate_to_chinese_http_error_fallback(monkeypatch):
    """Test that translation falls back on HTTP errors."""
    from backend.app.api import prompt_engine as pe_mod

    class _FakeResp:
        status_code = 500
        @property
        def text(self):
            return "Internal Server Error"

    class _FakeAsyncClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, *args, **kwargs):
            return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    original = "Hello world"
    result = asyncio.run(pe_mod._translate_to_chinese(original))

    # Should return original text on HTTP error
    assert result == original


# ============================================================================
# Chinese mode integration tests
# ============================================================================

def test_chinese_mode_translates_opening_on_newgame(client_with_translation):
    """Test that opening prompt is translated when starting game in Chinese mode."""
    client, translation_spy, _ = client_with_translation

    # Manually enable Chinese mode in session first
    from backend.app.api.prompt_engine import SESSIONS
    session_id = "cn_test_opening"
    SESSIONS[session_id] = {
        "state": None,
        "log": [],
        "debug_mode": False,
        "chinese_mode": True,  # Enable Chinese mode BEFORE newgame
    }

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "欢迎来到故事..."

    # Start new game - should translate opening
    resp = client.post("/api/chat", json={
        "session_id": session_id,
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Translation should have been called
    assert translation_spy.calls > 0, "Opening should be translated in Chinese mode"
    reply = resp.json()["reply"]
    assert "欢迎来到故事" in reply


def test_chinese_mode_translates_regular_responses(client_with_translation):
    """Test that regular chat responses are translated in Chinese mode."""
    client, translation_spy, _ = client_with_translation

    # Setup: start game, enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。"

    # Send message - should be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_responses",
        "message": "What happened?"
    })
    assert resp.status_code == 200

    # Verify translation was called
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]
    assert "我理解了" in reply


def test_english_mode_no_translation(client_with_translation):
    """Test that responses are NOT translated when Chinese mode is off."""
    client, translation_spy, _ = client_with_translation

    # Start game (no Chinese mode)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0

    # Send message - should NOT be translated
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_english",
        "message": "Hello"
    })
    assert resp.status_code == 200

    # Translation should NOT have been called
    assert translation_spy.calls == 0, "No translation should occur in English mode"


def test_chinese_toggle_with_special_characters(client_with_translation):
    """Test Chinese toggle with text containing special characters."""
    client, _, _ = client_with_translation

    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Toggle with text around it (edge case)
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_special",
        "message": "  [C]  "  # whitespace around toggle
    })
    assert resp.status_code == 200
    reply = resp.json()["reply"]

    # Should still recognize the toggle
    assert "进入中文模式" in reply or "Chinese mode" in reply.lower()


def test_reset_clears_chinese_mode():
    """Test that reset command clears Chinese mode flag."""
    import backend.app.api.prompt_engine as pe_mod

    session_id = "reset_test"

    # Create session with Chinese mode on
    sess = pe_mod.get_session(session_id)
    sess["chinese_mode"] = True
    assert sess["chinese_mode"] is True

    # After reset, new session should have chinese_mode = False
    pe_mod.SESSIONS[session_id] = {
        "state": pe_mod.init_state(),
        "log": [],
        "debug_mode": False,
        "chinese_mode": False,
    }

    sess = pe_mod.get_session(session_id)
    assert sess["chinese_mode"] is False


def test_chinese_and_debug_modes_can_coexist(client_with_translation):
    """Test that Chinese and Debug modes can both be enabled."""
    client, translation_spy, _ = client_with_translation

    # Start game
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable debug mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[D]"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Reset spy
    translation_spy.calls = 0
    translation_spy.return_value = "我理解了。(Debug box here...)"

    # Send message - should have both debug info AND Chinese translation
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_both",
        "message": "hello"
    })
    assert resp.status_code == 200

    # Translation should be called (Chinese mode on)
    assert translation_spy.calls > 0
    reply = resp.json()["reply"]

    # Should include translated content
    assert "我理解了" in reply


def test_chinese_mode_with_empty_response(client_with_translation):
    """Test Chinese mode handling of empty or very short responses."""
    client, translation_spy, _ = client_with_translation

    # Start game with Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "__cmd_newgame__:" + STORY_ID + "|M|TestPlayer"
    })
    assert resp.status_code == 200

    # Enable Chinese mode
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "[C]"
    })
    assert resp.status_code == 200

    # Set translation to return empty
    translation_spy.return_value = ""

    # This should still work gracefully
    resp = client.post("/api/chat", json={
        "session_id": "cn_test_empty",
        "message": "hi"
    })
    assert resp.status_code == 200


def test_chinese_mode_toggle_formatting():
    """Test that Chinese mode toggle messages are properly formatted."""
    import backend.app.api.prompt_engine as pe_mod

    # Verify the box function works with Chinese text
    box = pe_mod._box("进入中文模式", ["Type [C] to exit"])

    assert "进入中文模式" in box
    assert "┌" in box  # corners exist
    assert "└" in box
    assert "├" in box  # separator exists


# ============================================================================
# Story canonical projection tests
# ============================================================================

def test_canonicalize_story_cfg_keeps_only_generic_runtime_keys():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.story_loader import load_story

    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    cfg = pe_mod._canonicalize_story_cfg(story)

    assert "id" in cfg
    assert "characters" in cfg
    assert "epistemic_seed" in cfg
    assert "world" in cfg
    assert "relationships" in cfg
    assert "setting" not in cfg
    assert "victim" not in cfg
    assert "style" not in cfg
    assert "world_context" not in cfg


def test_noncanonical_story_details_are_seeded_to_transient_buffer():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state
    from backend.app.engine.story_loader import load_story

    story_id = all_stories()[0]["id"]
    story = load_story(story_id)
    assert story is not None

    st = init_state()
    st.story = story_id
    st.user_id = "default_user"
    st.instance = 1

    pe_mod._seed_noncanonical_story_details_to_transient(story, st)

    texts = [e.text for e in st.transient_entries]
    assert texts, "Expected non-canonical story details to be seeded into transient context"
    assert any(t.startswith("story.") or t.startswith("character.") for t in texts)


def test_seed_epistemic_common_knowledge_maps_to_all_characters():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state

    st = init_state()
    cfg = {
        "epistemic_seed": {
            "canonical_facts": [
                {
                    "id": "f_common",
                    "text": "This fact is common knowledge.",
                    "common_knowledge": True,
                    "confidence": 1.0,
                }
            ]
        }
    }

    pe_mod._seed_epistemic_from_story(cfg, st)

    assert len(st.canonical_facts) == 1
    assert st.canonical_facts[0].known_by == ["all_characters"]


def test_seed_epistemic_claim_visibility_metadata_is_preserved():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state

    st = init_state()
    cfg = {
        "epistemic_seed": {
            "belief_seeds": {
                "iu": [
                    {
                        "text": "I might know this detail.",
                        "known_by": ["iu"],
                        "not_known_by": ["player"],
                        "maybe_known_by": ["park_so_jin"],
                        "confidence": 0.7,
                    }
                ]
            }
        }
    }

    pe_mod._seed_epistemic_from_story(cfg, st)

    iu_claims = st.get_belief_state("iu").claims
    assert len(iu_claims) == 1
    assert iu_claims[0].known_by == ["iu"]
    assert iu_claims[0].not_known_by == ["player"]
    assert iu_claims[0].maybe_known_by == ["park_so_jin"]


# ---------------------------------------------------------------------------
# Session persistence & privacy tests (bugs 1, 2, 4)
# ---------------------------------------------------------------------------

import json as _json
import logging


def test_serialize_state_includes_runtime_snapshots():
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.state import init_state
    from backend.app.engine.character_graph import CharacterGraph, RelationshipEdge, RelationshipState, RelationshipType
    from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore

    st = init_state()
    st.story = STORY_ID
    st.gender = "F"
    st.player_name = "Alex"
    st.character_locations = {"iu": "room_a", "player": "room_a"}
    st.last_turn_user_msg = "where are we"
    st.last_turn_assistant_reply = "We are in room A"
    st.last_turn_retrieved_chunks = [{"chunk_id": "k1", "text": "fact"}]

    graph = CharacterGraph()
    graph.edges["iu->player"] = RelationshipEdge(
        id="iu->player",
        from_id="iu",
        to_id="player",
        type=RelationshipType.FRIEND,
        state=RelationshipState(trust=0.8, fear=0.1, affection=0.7, suspicion=0.0, jealousy=0.0),
        narrative="IU now trusts the player",
        narrative_log=["IU greeted the player warmly"],
        met_at=5,
        last_met_at=12,
        meeting_count=2,
        prior_relationship=True,
        in_relationship=True,
    )
    st.character_graph = graph

    st.session_chunk_store = SessionChunkStore()
    st.session_chunk_store.add_chunks([
        {"chunk_id": "usr-1-0", "text": "The key is in the drawer", "type": "dialogue_fact"}
    ])

    saved = _json.loads(pe_mod._serialize_state(st, []))
    assert "character_graph" in saved
    assert "session_chunks" in saved
    assert saved["character_locations"]["iu"] == "room_a"
    assert saved["last_turn_user_msg"] == "where are we"
    assert saved["character_graph"]["edges"]["iu->player"]["state"]["trust"] == pytest.approx(0.8)
    assert saved["session_chunks"][0]["chunk_id"] == "usr-1-0"


def test_try_load_session_restores_runtime_graph_and_session_chunks(monkeypatch):
    from backend.app.api import prompt_engine as pe_mod

    fake_state = {
        "story": STORY_ID,
        "gender": "M",
        "player_name": "ReplayUser",
        "turns": 4,
        "location_id": "room_a",
        "location": "Room A",
        "character_locations": {"iu": "room_b", "player": "room_b"},
        "last_turn_user_msg": "go to room b",
        "last_turn_assistant_reply": "You arrive in Room B",
        "last_turn_retrieved_chunks": [{"chunk_id": "g-1", "text": "room b has a locker"}],
        "character_graph": {
            "edges": {
                "player->iu": {
                    "id": "player->iu",
                    "from_id": "player",
                    "to_id": "iu",
                    "type": "FRIEND",
                    "state": {
                        "trust": 0.6,
                        "fear": 0.0,
                        "affection": 0.4,
                        "suspicion": 0.0,
                        "jealousy": 0.0,
                    },
                    "narrative": "Player feels closer to IU",
                    "narrative_log": ["They shared a clue"],
                    "met_at": 1,
                    "last_met_at": 8,
                    "meeting_count": 3,
                    "prior_relationship": False,
                    "prior_intimacy": False,
                    "in_relationship": False,
                }
            }
        },
        "session_chunks": [
            {"chunk_id": "usr-2-0", "text": "A hidden note mentions studio B", "type": "dialogue_fact"}
        ],
    }

    fake_row = {
        "story_id": STORY_ID,
        "player_name": "ReplayUser",
        "gender": "M",
        "state_json": _json.dumps(fake_state),
        "flags_json": _json.dumps({"debug_mode": True, "epistemic_state": True}),
    }

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_resume_1", "uid_resume")
    assert result is not None
    restored = result["state"]

    assert restored.character_locations.get("iu") == "room_b"
    assert restored.last_turn_user_msg == "go to room b"
    assert restored.last_turn_assistant_reply == "You arrive in Room B"
    assert restored.last_turn_retrieved_chunks[0]["chunk_id"] == "g-1"

    edge = restored.character_graph.get_edge("player", "iu")
    assert edge is not None
    assert edge.state.trust == pytest.approx(0.6)
    assert edge.narrative == "Player feels closer to IU"
    assert edge.meeting_count == 3

    restored_chunks = restored.session_chunk_store.all_chunks()
    assert len(restored_chunks) == 1
    assert restored_chunks[0]["chunk_id"] == "usr-2-0"


def test_try_load_session_from_db_sync_path(monkeypatch):
    """Bug 1: _try_load_session_from_db must work even when called from within a
    running event loop (the normal FastAPI path).  The old implementation used
    asyncio.get_event_loop().run_until_complete() which fails inside async code."""
    from backend.app.api import prompt_engine as pe_mod

    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID, "gender": "M", "player_name": "TestPlayer", "turns": 3,
        }),
        "flags_json": _json.dumps({
            "debug_mode": False, "chinese_mode": False,
            "epistemic_state": True, "truth_mode": False,
        }),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_test1", "user1")
    assert result is not None
    assert result["state"].story == STORY_ID
    assert result["state"].turns == 3
    assert result["user_id"] == "user1"


def test_try_load_session_from_db_works_inside_running_loop(monkeypatch):
    """Bug 1 continued: prove the fix works when an asyncio event loop IS running."""
    from backend.app.api import prompt_engine as pe_mod

    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID, "gender": "F", "player_name": "Alice",
        }),
        "flags_json": "{}",
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    async def _inner():
        return pe_mod._try_load_session_from_db("sess_async", "user2")

    result = asyncio.run(_inner())
    assert result is not None
    assert result["state"].player_name == "Alice"


def test_try_load_session_from_db_returns_none_when_not_found(monkeypatch):
    """If the session doesn't exist in DB, return None (no crash)."""
    from backend.app.api import prompt_engine as pe_mod

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: None),
    )

    result = pe_mod._try_load_session_from_db("nonexistent", "user1")
    assert result is None


def test_restore_then_travel_does_not_roll_clock_backward(monkeypatch):
    """A07 regression: restoring a session at a late minute and then
    traveling must not roll the world clock backward. Before the fix,
    WorldLoader always built a *fresh* WorldClock seeded from the authored
    world's start_minute (0 here); the restored `state.minute` was set
    correctly but the world_runtime's clock was not resynced to it, so the
    first travel action would overwrite state.minute with
    (fresh_start + delta), rolling the clock back from ~2000 to single
    digits."""
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine.gameplay import advance_time

    late_minute = 2000
    fake_row = {
        "state_json": _json.dumps({
            "story": STORY_ID,
            "gender": "M",
            "player_name": "ClockTest",
            "turns": 10,
            "minute": late_minute,
            "location_id": "iu_apartment_room",
            "location": "IU's Apartment",
        }),
        "flags_json": _json.dumps({
            "debug_mode": False, "chinese_mode": False,
            "epistemic_state": True, "truth_mode": False,
        }),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("sess_clock_test", "user_clock")
    assert result is not None
    state = result["state"]
    assert state.minute == late_minute
    assert state.world_runtime is not None
    # The world runtime's own clock must be resynced to the restored value,
    # not left at the authored world's start_minute (0).
    assert state.world_runtime.world_clock.now_minute() == late_minute

    # Now perform a travel action and confirm the clock only ever advances.
    advance_time(state, "go to apartment lobby")
    assert state.minute >= late_minute, (
        f"clock rolled backward on travel after restore: {late_minute} -> {state.minute}"
    )


def test_get_session_rejects_cross_user_cache_hit():
    """Bug 2: If session X is cached for user A, user B must not get user A's data."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_cross_user_sess"
    try:
        # Pre-populate cache with user A's session
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "secret_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "userA",
        }

        # User B requests the same session_id
        sess = pe_mod.get_session(test_session_id, "userB")
        assert sess["user_id"] == "userB"
        assert sess["log"] == []  # fresh, not userA's data
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_anon_caller_cannot_read_owned_cache_hit():
    """A01 regression: the old ownership check exempted callers/owners of
    "anon" from comparison (`cached_owner != "anon" and user_id != "anon"`),
    so an unauthenticated caller (user_id="anon") requesting a session_id
    that happened to be cached for a real owner got that owner's cached
    state/log back verbatim instead of a fresh session."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_anon_reads_owned_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "owner_secret_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "guest:real-owner-uuid",
        }

        # Anonymous caller (no JWT, no guest cookie) guesses/knows the session_id.
        sess = pe_mod.get_session(test_session_id, "anon")
        assert sess["user_id"] == "anon"
        assert sess["log"] == []  # must NOT see the real owner's cached log
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_owner_cannot_be_bypassed_by_anon_owned_cache():
    """A01 regression: a session cached with owner "anon" must not be handed
    to a different real caller just because the cached owner happens to be
    "anon" (the old check also exempted this direction)."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_anon_owned_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "anon_session_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "anon",
        }

        sess = pe_mod.get_session(test_session_id, "guest:someone-else")
        assert sess["user_id"] == "guest:someone-else"
        assert sess["log"] == []
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_get_session_allows_same_user_cache_hit():
    """Same user should get their own cached session back."""
    from backend.app.api import prompt_engine as pe_mod

    test_session_id = "_test_same_user_sess"
    try:
        pe_mod.SESSIONS[test_session_id] = {
            "state": pe_mod.init_state(),
            "log": [{"role": "assistant", "content": "my_data"}],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": "userA",
        }

        sess = pe_mod.get_session(test_session_id, "userA")
        assert sess["user_id"] == "userA"
        assert sess["log"] == [{"role": "assistant", "content": "my_data"}]
    finally:
        pe_mod.SESSIONS.pop(test_session_id, None)


def test_try_load_session_logs_on_db_failure(monkeypatch, caplog):
    """Bug 4: DB failures should be logged, not silently swallowed."""
    from backend.app.api import prompt_engine as pe_mod

    def _explode(session_id, user_id):
        raise RuntimeError("DB connection failed")

    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(_explode),
    )

    with caplog.at_level(logging.ERROR, logger="backend.app.api.prompt_engine"):
        result = pe_mod._try_load_session_from_db("sess_bad", "user1")

    assert result is None
    assert "Failed to load session" in caplog.text


from backend.app.integration_playback.scenarios.scenario_api_chat_five_turns import ChatFiveTurnScenario
from backend.app.integration_playback.scenarios.scenario_iu_identity_correction import IUIdentityCorrectionScenario


@pytest.mark.integration
# ============================================================================
# A12: per-session turn serialization
# ============================================================================

@pytest.mark.asyncio
async def test_chat_handler_serializes_overlapping_calls_for_same_session(monkeypatch):
    """A12 regression: two overlapping /api/chat-style calls for the SAME
    session_id must not run their turn-processing critical sections
    concurrently (which could interleave reads/writes of the shared
    SESSIONS[session_id] cache and double-apply or corrupt a turn)."""
    from backend.app.api import prompt_engine as pe_mod

    state = {"current": 0, "max_concurrent": 0}

    async def _fake_impl(request, data, _auth_user):
        state["current"] += 1
        state["max_concurrent"] = max(state["max_concurrent"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return {"reply": "ok"}

    monkeypatch.setattr(pe_mod, "_chat_handler_impl", _fake_impl)

    same_session = {"session_id": "a12_same_sess", "message": "hi"}
    results = await asyncio.gather(
        pe_mod.chat_handler(request=None, data=dict(same_session), _auth_user=None),
        pe_mod.chat_handler(request=None, data=dict(same_session), _auth_user=None),
    )
    assert all(r == {"reply": "ok"} for r in results)
    assert state["max_concurrent"] == 1, (
        f"overlapping calls for the same session_id ran concurrently: max_concurrent={state['max_concurrent']}"
    )


@pytest.mark.asyncio
async def test_chat_handler_does_not_serialize_different_sessions(monkeypatch):
    """The per-session lock must not become a global lock — two DIFFERENT
    session_ids should still be able to process turns concurrently."""
    from backend.app.api import prompt_engine as pe_mod

    state = {"current": 0, "max_concurrent": 0}

    async def _fake_impl(request, data, _auth_user):
        state["current"] += 1
        state["max_concurrent"] = max(state["max_concurrent"], state["current"])
        await asyncio.sleep(0.05)
        state["current"] -= 1
        return {"reply": "ok"}

    monkeypatch.setattr(pe_mod, "_chat_handler_impl", _fake_impl)

    results = await asyncio.gather(
        pe_mod.chat_handler(request=None, data={"session_id": "a12_sess_x", "message": "hi"}, _auth_user=None),
        pe_mod.chat_handler(request=None, data={"session_id": "a12_sess_y", "message": "hi"}, _auth_user=None),
    )
    assert all(r == {"reply": "ok"} for r in results)
    assert state["max_concurrent"] == 2, (
        f"different sessions were serialized against each other: max_concurrent={state['max_concurrent']}"
    )


def test_api_end_to_end_5_turns_time_and_location():
    ChatFiveTurnScenario.run_as_test()


@pytest.mark.integration
@pytest.mark.xfail(reason="LLM non-deterministic: narration reveals identity but evaluator acceptance varies", strict=False)
def test_iu_identity_correction():
    IUIdentityCorrectionScenario.run_as_test()


# ---------------------------------------------------------------------------
# BL-07: per-character self_knowledge propagation through prompt_engine.py
# (new-game path and restore path build the character roster separately,
# so both are covered here).
# ---------------------------------------------------------------------------

def test_newgame_path_prefers_per_character_self_knowledge_over_story_fallback(client):
    """New-game roster construction: a non-main character (Dae-ho) with his
    own `self_knowledge` gets it verbatim; Mina (the loader-assigned is_main
    fallback) also carries her own per-character self_knowledge now that it's
    authored on her character entry rather than only the top-level key;
    Priya (no scene presence assumed here) still has her own self_knowledge
    parsed onto her Character object regardless of presence -- presence
    gating happens at the prompt_builder injection layer, not at roster
    construction."""
    from backend.app.api import prompt_engine as pe_mod

    sid = "bl07_newgame_common_room"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:common_room|M|Chris"},
    )
    assert r.status_code == 200

    sess = pe_mod.SESSIONS.get(sid)
    assert sess is not None
    state = sess["state"]

    mina = state.characters.get("mina")
    daeho = state.characters.get("daeho")
    priya = state.characters.get("priya")
    assert mina is not None and daeho is not None and priya is not None

    assert mina.self_knowledge, "Mina should carry her own authored self_knowledge"
    assert any("house mom" in e for e in mina.self_knowledge)

    assert daeho.self_knowledge, "Dae-ho should carry his own authored self_knowledge"
    assert any("easygoing" in e.lower() for e in daeho.self_knowledge)

    assert priya.self_knowledge, "Priya should carry her own authored self_knowledge"
    assert any("structure" in e.lower() for e in priya.self_knowledge)


def test_restore_path_prefers_per_character_self_knowledge_over_story_fallback(monkeypatch):
    """Restore roster construction (_try_load_session_from_db) applies the
    same per-character-wins-over-story-fallback rule as the new-game path."""
    from backend.app.api import prompt_engine as pe_mod

    fake_state = {"story": "common_room", "turns": 1, "location_id": "kitchen", "location": "Kitchen"}
    fake_row = {
        "story_id": "common_room",
        "player_name": "ReplayUser",
        "gender": "M",
        "state_json": _json.dumps(fake_state),
        "flags_json": _json.dumps({}),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )

    result = pe_mod._try_load_session_from_db("bl07_restore_common_room", "uid_bl07")
    assert result is not None
    restored = result["state"]

    mina = restored.characters.get("mina")
    daeho = restored.characters.get("daeho")
    priya = restored.characters.get("priya")
    assert mina is not None and daeho is not None and priya is not None

    assert any("house mom" in e for e in mina.self_knowledge)
    assert any("easygoing" in e.lower() for e in daeho.self_knowledge)
    assert any("structure" in e.lower() for e in priya.self_knowledge)


def test_newgame_and_restore_paths_keep_iu_murder_mystery_single_character_fallback(client, monkeypatch):
    """Backward-compat: iu_murder_mystery's suspects have never had their own
    self_knowledge -- only the story-level `character_self_knowledge` array,
    applied via the is_main fallback to `iu`. Both roster-construction sites
    must still produce that exact single-character shape."""
    from backend.app.api import prompt_engine as pe_mod

    # New-game path.
    sid = "bl07_newgame_iu"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]
    assert state.characters["iu"].self_knowledge, "main character (fallback) must still get story-level self_knowledge"
    for key, ch in state.characters.items():
        if key in ("iu", "player"):
            continue
        assert ch.self_knowledge == [], f"suspect {key} unexpectedly has self_knowledge"

    # Restore path.
    fake_state = {"story": "iu_murder_mystery", "turns": 1}
    fake_row = {
        "story_id": "iu_murder_mystery",
        "player_name": "ReplayUser",
        "gender": "M",
        "state_json": _json.dumps(fake_state),
        "flags_json": _json.dumps({}),
    }
    monkeypatch.setattr(
        "backend.app.db.repos.SessionRepo._get",
        staticmethod(lambda session_id, user_id: fake_row),
    )
    result = pe_mod._try_load_session_from_db("bl07_restore_iu", "uid_bl07_iu")
    assert result is not None
    restored = result["state"]
    assert restored.characters["iu"].self_knowledge
    for key, ch in restored.characters.items():
        if key in ("iu", "player"):
            continue
        assert ch.self_knowledge == [], f"suspect {key} unexpectedly has self_knowledge on restore"


def test_backward_compat_iu_murder_mystery_identity_section_unchanged(client):
    """Critical regression guard for BL-07: assembling the full system prompt
    for iu_murder_mystery must still produce exactly ONE
    '### CHARACTER IDENTITY' block (for `iu`, the ghost/main character),
    worded exactly as it was before per-character self_knowledge existed --
    none of the suspects define their own self_knowledge, so the new
    'other present characters' loop in _character_identity_section must
    contribute nothing for this story."""
    from backend.app.api import prompt_engine as pe_mod
    from backend.app.engine import prompt_builder as pb

    sid = "bl07_iu_identity_regression"
    r = client.post(
        "/api/chat",
        json={"session_id": sid, "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"},
    )
    assert r.status_code == 200
    state = pe_mod.SESSIONS[sid]["state"]

    sysmsg = pb.system_prompt(state, current_user_msg="hello")
    assert sysmsg.count("### CHARACTER IDENTITY") == 1
    assert "### CHARACTER IDENTITY — IU" in sysmsg
    assert "- You are the ghost of the previous tenant of this apartment" in sysmsg
    assert "speak them directly in first person" in sysmsg


def test_common_room_mina_and_daeho_present_together_identity_blocks():
    """Common-Room-specific BL-07 coverage: with Mina and Dae-ho both present
    in the same location, the assembled system prompt contains both
    '### CHARACTER IDENTITY' blocks with their respective authored content;
    Priya's block is absent because she isn't present in this scene."""
    from backend.app.engine import prompt_builder as pb
    from backend.app.engine.state import init_state
    from backend.app.engine.story_loader import load_story

    story = load_story("common_room")
    assert story is not None
    by_key = {c.key: c for c in story.characters}
    assert by_key["mina"].self_knowledge
    assert by_key["daeho"].self_knowledge
    assert by_key["priya"].self_knowledge

    st = init_state()
    st.story_cfg = {"meta": story.get("meta", {})}
    st.characters["mina"] = by_key["mina"]
    st.characters["daeho"] = by_key["daeho"]
    st.characters["priya"] = by_key["priya"]
    st.main_character_id = "mina"

    st.add_transient_entry(
        id="pp::mina", namespace="test", scope="scene",
        text="__people_present_marker__:mina", expires_after_turns=4,
    )
    st.add_transient_entry(
        id="pp::daeho", namespace="test", scope="scene",
        text="__people_present_marker__:daeho", expires_after_turns=4,
    )

    sysmsg = pb.system_prompt(st, current_user_msg="hello")
    assert sysmsg.count("### CHARACTER IDENTITY") == 2
    assert "### CHARACTER IDENTITY — Mina" in sysmsg
    assert "### CHARACTER IDENTITY — Dae-ho" in sysmsg
    assert "### CHARACTER IDENTITY — Priya" not in sysmsg
    for entry in by_key["mina"].self_knowledge:
        assert entry in sysmsg
    for entry in by_key["daeho"].self_knowledge:
        assert entry in sysmsg
    for entry in by_key["priya"].self_knowledge:
        assert entry not in sysmsg
