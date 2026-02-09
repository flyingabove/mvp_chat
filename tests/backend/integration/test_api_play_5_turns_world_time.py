"""Playback-ready scenario for chat API with five turns and time/location checks."""

import os
from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.integration_playback.scenario import IntegrationScenario, step


def _make_assistant_reply(turn: int) -> str:
    # Reply follows dialogue prefix format + state tag; timestamp stripped.
    return (
        "*The air feels colder for a breath.*\n"
        f"IU: \"Turn {turn} acknowledged.\"\n"
        "[[STATE]]{\"iu_emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"
    )


class _FakeResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self._content = content

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"total_tokens": 1},
        }


@dataclass
class ChatFiveTurnContext:
    patchers: List[Any] = field(default_factory=list)
    client: TestClient | None = None
    last_response: Any = None
    old_skip_env: str | None = None


class ChatFiveTurnScenario(IntegrationScenario):
    scenario_id = "api_chat_5_turns_time_location"
    title = "Chat API: a quick five-message 'leave home and arrive at EDAM' run"
    description = (
        "A short, human-feeling chat that still stays fully deterministic: start a new game, say hi, then walk out "
        "to the lobby, garage, car, and finally the EDAM lobby. The assertions remain the same: travel graph "
        "resolution and time accounting must match exactly."
    )
    tags = ["integration", "chat", "deterministic"]

    def setup(self):
        from backend.app.api import chat as chat_module
        from backend.app.main import app

        ctx = ChatFiveTurnContext()
        self.state = ctx

        # Set env
        ctx.old_skip_env = os.environ.get("SKIP_KNOWLEDGE_INDEX_BUILD")
        os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = "1"

        # Patch retrieval
        p1 = patch.object(chat_module, "retrieve_knowledge", lambda msg: ([], {"mocked": True}))
        p1.start()
        ctx.patchers.append(p1)

        # Patch OpenAI HTTP
        async def _fake_post(self_client, url, headers=None, json=None):
            try:
                sess = chat_module.SESSIONS.get("t1")
                st = sess["state"] if sess else None
                turn = getattr(st, "turns", 0)
            except Exception:
                turn = 0
            return _FakeResponse(_make_assistant_reply(turn))

        p2 = patch.object(httpx.AsyncClient, "post", _fake_post)
        p2.start()
        ctx.patchers.append(p2)

        # Create client
        ctx.client = TestClient(app)

        return {
            "reply": "*Booting a deterministic chat harness so we can rehearse a short, realistic travel flow.*",
            **self.debug_info(),
        }

    def cleanup(self):
        for patcher in reversed(self.state.patchers):
            patcher.stop()

        if self.state.old_skip_env is None:
            os.environ.pop("SKIP_KNOWLEDGE_INDEX_BUILD", None)
        else:
            os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = self.state.old_skip_env

    # -- Helper --

    def _post(self, message: str):
        assert self.state.client is not None, "Test client not initialized"
        resp = self.state.client.post("/api/chat", json={"session_id": "t1", "message": message})
        self.state.last_response = resp
        assert resp.status_code == 200
        payload = resp.json()
        reply = payload.get("reply", "")
        return {
            "user": message,
            "reply": reply,
            **self.debug_info(),
        }

    # -- Steps --

    @step(kind="action", description="Start new IU game")
    def start_game(self):
        return self._post("__cmd_newgame__:iu_murder_mystery|M|Chris")

    @step(kind="action", description="Turn 1: quick check-in")
    def turn1(self):
        return self._post("Hey IU\u2014just checking in before we head out.")

    @step(kind="action", description="Turn 2: go to lobby")
    def turn2(self):
        return self._post("go to iu_apartment_lobby")

    @step(kind="action", description="Turn 3: go to parking garage")
    def turn3(self):
        return self._post("go to apartment_parking_garage")

    @step(kind="action", description="Turn 4: go to car")
    def turn4(self):
        return self._post("go to my_car")

    @step(kind="action", description="Turn 5: go to workplace lobby")
    def turn5(self):
        return self._post("go to workplace_lobby")

    @step(kind="assert", description="Validate state and time")
    def assert_state(self):
        from backend.app.api import chat as chat_module

        sess = chat_module.SESSIONS["t1"]
        st = sess["state"]

        assert st.location_id == "workplace_lobby"
        assert st.location == "EDAM Entertainment Lobby"

        reply_text = self.state.last_response.json()["reply"]
        assert not reply_text.startswith("[")
        assert reply_text.lstrip().startswith("*")

        expected_minute = 0 + 3 + (2 + (1 + 2)) + (2 + (1 + 3)) + (2 + (1 + 1)) + (2 + (1 + 15))
        assert st.minute == expected_minute
        return {
            "reply": (
                f"*Quick time audit: we ended up at {st.location} and the clock reads minute {expected_minute}.*\n\n"
                f"*(Travel graph and time accounting verified.)*"
            ),
            **self.debug_info({"location_id": st.location_id, "location": st.location, "minute": st.minute}),
        }


# -- Pytest entry point --
import pytest  # noqa: E402

@pytest.mark.integration
def test_api_end_to_end_5_turns_time_and_location():
    ChatFiveTurnScenario.run_as_test()
