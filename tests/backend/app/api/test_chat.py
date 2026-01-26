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