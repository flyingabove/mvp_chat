import asyncio

import pytest
from fastapi.testclient import TestClient


class _FakeResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self._content = content

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"total_tokens": 1},
        }


def _make_assistant_reply(turn: int) -> str:
    # Reply follows your required dialogue prefix format + state tag.
    # The API will prepend a timestamp line.
    return (
        "*The air feels colder for a breath.*\n"
        f"IU: \"Turn {turn} acknowledged.\"\n"
        "[[STATE]]{\"iu_emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"
    )


@pytest.mark.integration
def test_api_end_to_end_5_turns_time_and_location(monkeypatch):
    # Avoid optional index build from the session fixture.
    monkeypatch.setenv("SKIP_KNOWLEDGE_INDEX_BUILD", "1")

    # Mock retrieval to keep this test pure + deterministic.
    from backend.app.api import chat as chat_module

    monkeypatch.setattr(chat_module, "retrieve_knowledge", lambda msg: ([], {"mocked": True}))

    # Mock OpenAI HTTP call.
    import httpx

    async def _fake_post(self, url, headers=None, json=None):
        # Turn counter is stored on session state; use it to vary output.
        # The endpoint increments state.turns before calling OpenAI.
        # We'll read it from the session in the module.
        # If session doesn't exist yet, default to 0.
        try:
            # grab the only session for this test
            sess = chat_module.SESSIONS.get("t1")
            st = sess["state"] if sess else None
            turn = getattr(st, "turns", 0)
        except Exception:
            turn = 0

        return _FakeResponse(_make_assistant_reply(turn))

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post, raising=True)

    from backend.app.main import app

    client = TestClient(app)

    # Start new game with IU story (includes world graph)
    r = client.post("/api/chat", json={"session_id": "t1", "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"})
    assert r.status_code == 200

    # Turn 1: normal talk
    r = client.post("/api/chat", json={"session_id": "t1", "message": "hello"})
    assert r.status_code == 200

    # Turn 2: travel from apartment room -> apartment lobby
    r = client.post("/api/chat", json={"session_id": "t1", "message": "go to iu_apartment_lobby"})
    assert r.status_code == 200

    # Turn 3: travel lobby -> parking garage
    r = client.post("/api/chat", json={"session_id": "t1", "message": "go to apartment_parking_garage"})
    assert r.status_code == 200

    # Turn 4: travel garage -> my car
    r = client.post("/api/chat", json={"session_id": "t1", "message": "go to my_car"})
    assert r.status_code == 200

    # Turn 5: travel car -> workplace lobby
    r = client.post("/api/chat", json={"session_id": "t1", "message": "go to workplace_lobby"})
    assert r.status_code == 200

    # Validate internal state (time + location)
    sess = chat_module.SESSIONS["t1"]
    st = sess["state"]

    # Ensure graph-based location tracking is active and ended where we asked.
    assert st.location_id == "workplace_lobby"
    assert st.location == "EDAM Entertainment Lobby"

    # Check timestamp prefix exists in reply payload
    reply_text = r.json()["reply"]
    assert reply_text.startswith("[") and "]" in reply_text.splitlines()[0]

    # Now validate deterministic time math:
    # Dialogue cost per turn: base(1) + ceil(words*0.25)
    # "hello" -> 1 word => ceil(0.25)=1 => +2
    # Each "go to X" -> 4 words => ceil(1.0)=1 => +2 dialog, then travel resolver adds exit(1)+edge.minutes
    # Travel edges (from the story world json):
    # iu_apartment_room -> iu_apartment_lobby = 2
    # iu_apartment_lobby -> apartment_parking_garage = 3
    # apartment_parking_garage -> my_car = 1
    # my_car -> workplace_lobby = 15
    # Total:
    # hello: +2
    # each travel turn: +2 dialog + (exit 1 + edge minutes)
    expected_minute = 0 + 2 + (2 + (1 + 2)) + (2 + (1 + 3)) + (2 + (1 + 1)) + (2 + (1 + 15))
    assert st.minute == expected_minute
