import types

import re

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    """Create a FastAPI TestClient with network calls mocked."""
    # Import inside fixture so our monkeypatches apply before first use.
    from backend.app.api import chat as chat_mod

    # Spy to assert when the LLM (OpenAI) is called.
    spy = types.SimpleNamespace(calls=0)
    chat_mod._TEST_OPENAI_POST_SPY = spy

    # Prevent retrieval from doing any IO during tests.
    monkeypatch.setattr(chat_mod, "retrieve_knowledge", lambda *args, **kwargs: ([], {}), raising=False)

    # Mock location extractor to not call LLM (return NONE intent)
    from backend.app.engine.extractors.location_extractor import LocationExtraction, LocationIntent
    async def _mock_extract(*args, **kwargs):
        return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text=None)
    monkeypatch.setattr(chat_mod._LOCATION_EXTRACTOR, "extract", _mock_extract, raising=False)

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

    monkeypatch.setattr(chat_mod.httpx, "AsyncClient", _FakeAsyncClient)

    from backend.app import main
    return TestClient(main.app)


def test_chat_newgame_and_turn(client):
    # Start a new game
    r = client.post("/api/chat", json={"session_id": "s1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
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


def test_debug_mode_toggle_no_llm_on_toggle_and_appends_debug_box(client):
    from backend.app.api import chat as chat_mod

    # Start a new game so a normal turn hits the LLM mock.
    r = client.post("/api/chat", json={"session_id": "dbg1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r.status_code == 200

    spy = getattr(chat_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Enter debug mode (must NOT call LLM)
    r2 = client.post("/api/chat", json={"session_id": "dbg1", "message": "[D]"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "ENTERING DEBUG MODE" in data2["reply"]
    assert spy.calls == base_calls

    # Normal turn should call LLM and append debug box
    r3 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "DEBUG INFO" in data3["reply"]
    assert "Timestamp:" in data3["reply"]
    assert not re.match(r"^\[\d{4}-\d{2}-\d{2} ", data3["reply"])  # no leading timestamp
    assert spy.calls == base_calls + 1

    # Exit debug mode (must NOT call LLM)
    r4 = client.post("/api/chat", json={"session_id": "dbg1", "message": "(DEBUG)"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "EXITING DEBUG MODE" in data4["reply"]
    assert spy.calls == base_calls + 1

    # Next normal turn should not have debug box
    r5 = client.post("/api/chat", json={"session_id": "dbg1", "message": "hello again"})
    assert r5.status_code == 200
    data5 = r5.json()
    assert "DEBUG INFO" not in data5["reply"]
    assert spy.calls == base_calls + 2
def test_debug_toggle_strips_leading_gt(client):
    from backend.app.api import chat as chat_mod

    # Start a new game so the "regular turn" path is active for subsequent messages.
    r0 = client.post("/api/chat", json={"session_id": "gt1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r0.status_code == 200

    spy = getattr(chat_mod, "_TEST_OPENAI_POST_SPY")
    base_calls = spy.calls

    # Leading '>' should be scrubbed globally, so this should toggle debug mode.
    r1 = client.post("/api/chat", json={"session_id": "gt1", "message": "> [D]"})
    assert r1.status_code == 200
    data1 = r1.json()
    assert "ENTERING DEBUG MODE" in data1["reply"]
    assert spy.calls == base_calls  # toggle must NOT call OpenAI

    # A normal message should now call the OpenAI mock and append debug box.
    r2 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello"})
    assert r2.status_code == 200
    data2 = r2.json()
    assert "DEBUG INFO" in data2["reply"]
    assert "Timestamp:" in data2["reply"]
    assert spy.calls == base_calls + 1

    # Exit debug mode with a leading '>' as well.
    r3 = client.post("/api/chat", json={"session_id": "gt1", "message": "> (DEBUG)"})
    assert r3.status_code == 200
    data3 = r3.json()
    assert "EXITING DEBUG MODE" in data3["reply"]
    assert spy.calls == base_calls + 1  # toggle must NOT call OpenAI

    # Next normal turn should not have debug info.
    r4 = client.post("/api/chat", json={"session_id": "gt1", "message": "hello again"})
    assert r4.status_code == 200
    data4 = r4.json()
    assert "DEBUG INFO" not in data4["reply"]
    assert spy.calls == base_calls + 2


def test_debug_box_speakers_do_not_include_location_as_name(client):
    # Start a new game
    r0 = client.post("/api/chat", json={"session_id": "spk1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode
    r1 = client.post("/api/chat", json={"session_id": "spk1", "message": "[D]"})
    assert r1.status_code == 200

    # Normal turn to get debug info appended
    r2 = client.post("/api/chat", json={"session_id": "spk1", "message": "hello"})
    assert r2.status_code == 200
    reply = r2.json()["reply"]

    assert "DEBUG INFO" in reply
    assert "Speakers:" in reply

    # Ensure the location isn't mistakenly treated as a speaker name.
    assert "- IU’s Apartment" not in reply

def test_debug_box_rendering_pretty_separator(client):
    """Test that debug box has proper title/content separator."""
    r0 = client.post("/api/chat", json={"session_id": "box1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r0.status_code == 200

    # Enable debug mode
    r1 = client.post("/api/chat", json={"session_id": "box1", "message": "[D]"})
    assert r1.status_code == 200
    reply1 = r1.json()["reply"]

    # Debug toggle boxes should have proper separator
    assert "├" in reply1  # separator line must exist
    assert "ENTERING DEBUG MODE" in reply1
    lines = reply1.split("\n")
    # Find title line and verify next line is separator
    for i, line in enumerate(lines):
        if "ENTERING DEBUG MODE" in line:
            assert i + 1 < len(lines)
            next_line = lines[i + 1]
            assert "├" in next_line, f"Expected separator after title, got: {next_line}"
            break
    else:
        assert False, "Could not find ENTERING DEBUG MODE in output"

    # Normal turn should append debug box with proper formatting
    r2 = client.post("/api/chat", json={"session_id": "box1", "message": "hello"})
    assert r2.status_code == 200
    reply2 = r2.json()["reply"]

    assert "DEBUG INFO" in reply2
    assert "├" in reply2  # separator for debug box
    # Verify box has corners
    assert "┌" in reply2 and "┐" in reply2
    assert "└" in reply2 and "┘" in reply2
# ============================================================================
# Chat utility function tests
# ============================================================================


def test_apply_placeholders_and_sanitize_korean_terms():
    from backend.app.engine.state import init_state
    import backend.app.api.chat as chat_mod

    st = init_state()
    st.player_name = "Chris"
    st.gender = "M"
    out = chat_mod.apply_placeholders("Hi {{PLAYER_NAME}} {{HONORIFIC}}", st)
    assert "Chris" in out
    assert "oppa" in out  # honorific placeholder is meta-only for opening

    # At low relationship, sanitize should strip forbidden terms
    st.relationship = 0
    st.user.display_name = "Chris"
    cleaned = chat_mod.sanitize_korean_terms("hello oppa unnie", st)
    assert "oppa" not in cleaned.lower()
    assert "unnie" not in cleaned.lower()


def test_name_extraction_and_confirmation():
    from backend.app.engine.state import init_state
    import backend.app.api.chat as chat_mod

    st = init_state()
    name = chat_mod.extract_user_name_from_text("my name is alice")
    assert name == "Alice"

    # confirmation should set names
    st.last_assistant_guess_name = "Bob"
    chat_mod.handle_name_confirmation("yes", st)
    assert st.user.formal_name == "Bob"


def test_map_toggle_shows_locations_from_world(client):
    """Test that [M] or [MAP] command shows available locations."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map1", "message": "__cmd_newgame__:iu_murder_mystery|M|Player"})
    assert r0.status_code == 200
    opening = r0.json()

    # Toggle map with [M]
    r1 = client.post("/api/chat", json={"session_id": "map1", "message": "[M]"})
    assert r1.status_code == 200
    resp1 = r1.json()
    reply1 = resp1["reply"]

    # Should show World Map box with locations (no LLM call)
    assert "World Map" in reply1
    # Should contain at least one location name from the IU story world
    # (IU's Apartment is the starting location)
    assert "Apartment" in reply1 or "Location" in reply1

    # Verify no LLM tokens were used (early exit, same as [D])
    assert resp1.get("usage", {}).get("total_tokens", 0) == 0


def test_map_toggle_case_insensitive(client):
    """Test that map toggle is case-insensitive."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map2", "message": "__cmd_newgame__:iu_murder_mystery|F|Player"})
    assert r0.status_code == 200

    # Test various forms: [MAP], (MAP), [m], (map)
    for msg in ["[MAP]", "(MAP)", "[m]", "(map)"]:
        r = client.post("/api/chat", json={"session_id": "map2", "message": msg})
        assert r.status_code == 200
        reply = r.json()["reply"]
        assert "World Map" in reply, f"Map toggle failed for: {msg}"


def test_map_toggle_token_detection():
    """Test _is_map_toggle() function directly with various inputs."""
    import backend.app.api.chat as chat_mod
    
    # Valid map toggle tokens
    assert chat_mod._is_map_toggle("[M]")
    assert chat_mod._is_map_toggle("[m]")
    assert chat_mod._is_map_toggle("(M)")
    assert chat_mod._is_map_toggle("(m)")
    assert chat_mod._is_map_toggle("[MAP]")
    assert chat_mod._is_map_toggle("[map]")
    assert chat_mod._is_map_toggle("(MAP)")
    assert chat_mod._is_map_toggle("(map)")
    
    # With surrounding whitespace
    assert chat_mod._is_map_toggle("  [M]  ")
    assert chat_mod._is_map_toggle("\t[MAP]\t")
    
    # Invalid tokens (should not match)
    assert not chat_mod._is_map_toggle("[D]")  # Debug token
    assert not chat_mod._is_map_toggle("[C]")  # Chinese token
    assert not chat_mod._is_map_toggle("map")  # No brackets
    assert not chat_mod._is_map_toggle("[X]")  # Unknown token
    assert not chat_mod._is_map_toggle("")     # Empty string
    assert not chat_mod._is_map_toggle("hello world")  # Normal message


def test_map_toggle_no_llm_call(client):
    """Verify that MAP toggle does not invoke LLM (0 tokens)."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_llm", "message": "__cmd_newgame__:iu_murder_mystery|M|Test"})
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
    r0 = client.post("/api/chat", json={"session_id": "map_box", "message": "__cmd_newgame__:iu_murder_mystery|F|BoxTest"})
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
    r0 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "__cmd_newgame__:iu_murder_mystery|M|AllLocs"})
    assert r0.status_code == 200
    
    # Request map
    r1 = client.post("/api/chat", json={"session_id": "map_all_locs", "message": "[M]"})
    assert r1.status_code == 200
    reply = r1.json()["reply"]
    
    # Should contain multiple locations from the IU world
    # We know from iu_murder_mystery_world.json there are 11 locations
    # At minimum, verify we see some key locations
    assert "Apartment" in reply or "apartment" in reply, "Should mention apartment location"
    # Count newlines to verify multiple entries (locations are on separate lines in the box)
    location_lines = [line for line in reply.split('\n') if line.strip() and '─' not in line and 'World' not in line]
    assert len(location_lines) > 3, f"Should list multiple locations, got: {reply}"


def test_map_toggle_without_world_runtime(client, monkeypatch):
    """Test MAP toggle behavior when world_runtime is not available."""
    import backend.app.api.chat as chat_mod
    
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_no_world", "message": "__cmd_newgame__:iu_murder_mystery|F|NoWorld"})
    assert r0.status_code == 200
    
    # Remove world_runtime from session state
    state = chat_mod.SESSIONS["map_no_world"]["state"]
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
    r0 = client.post("/api/chat", json={"session_id": "map_ws", "message": "__cmd_newgame__:iu_murder_mystery|M|Whitespace"})
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
    r0 = client.post("/api/chat", json={"session_id": "map_consistent", "message": "__cmd_newgame__:iu_murder_mystery|F|Consistent"})
    assert r0.status_code == 200
    
    # Request map three times
    replies = []
    for i in range(3):
        r = client.post("/api/chat", json={"session_id": "map_consistent", "message": "[M]"})
        assert r.status_code == 200
        replies.append(r.json()["reply"])
    
    # All three should be identical
    assert replies[0] == replies[1], "First and second map calls differ"
    assert replies[1] == replies[2], "Second and third map calls differ"


def test_map_toggle_mixed_with_normal_turns(client):
    """Test MAP toggle interleaved with normal game turns."""
    # Start new game
    r0 = client.post("/api/chat", json={"session_id": "map_mixed", "message": "__cmd_newgame__:iu_murder_mystery|M|Mixed"})
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

