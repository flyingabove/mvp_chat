import types

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

    # Mock httpx.AsyncClient so /api/chat never hits OpenAI.

    class _FakeResp:
        status_code = 200

        def json(self):
            # Reply must include a valid [[STATE]] tag so state parsing passes.
            return {
                "choices": [{"message": {"content": "*ok*\n\n**\"hi\"**\n[[STATE]]{\"iu_emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"}}],
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
