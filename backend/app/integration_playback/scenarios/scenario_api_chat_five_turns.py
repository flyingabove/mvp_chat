import os
from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import patch

import httpx

from backend.app.integration_playback.scenario import IntegrationScenario, step


def _default_story_id() -> str:
    return os.getenv("TEST_STORY_ID", "iu_murder_mystery")


def _make_assistant_reply(turn: int) -> str:
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
    client: Any = None
    last_response: Any = None  # dict returned by _post_chat


class ChatFiveTurnScenario(IntegrationScenario):
    scenario_id = "api_chat_5_turns_time_location"
    title = "Chat API: deterministic five-turn travel run"
    description = "Start game and travel across locations while validating graph resolution and time accounting."
    tags = ["integration", "chat", "deterministic"]
    player_role = "Detective"

    def setup(self):
        from backend.app.api import prompt_engine as chat_module

        ctx = ChatFiveTurnContext()
        self.state = ctx

        p1 = patch.object(
            chat_module,
            "retrieve_knowledge",
            lambda msg, namespace=None, **_: ([], {"mocked": True, "namespace": namespace}),
        )
        p1.start()
        ctx.patchers.append(p1)

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

        ctx.client = self._open_test_client()

        return {
            "reply": "*Booting deterministic chat harness for travel-flow validation.*",
            **self.debug_info(),
        }

    def cleanup(self):
        for patcher in reversed(self.state.patchers):
            patcher.stop()
        self._close_test_client()

    def _post(self, api_message: str, user_line: str = ""):
        data = self._post_chat(self.state.client, "t1", api_message)
        self.state.last_response = data
        reply = data.get("reply", "")
        return [
            self.say_user(user_line or api_message),
            self.say_llm("IU", reply),
            self.debug_info(),
        ]

    @step(kind="action", description="Start new IU game")
    def start_game(self):
        return self._post(f"__cmd_newgame__:{_default_story_id()}|M|Chris", "Start a new case file.")

    @step(kind="action", description="Turn 1")
    def turn1(self):
        return self._post("Hey IU—just checking in before we head out.")

    @step(kind="action", description="Turn 2")
    def turn2(self):
        return self._post("go to iu_apartment_lobby")

    @step(kind="action", description="Turn 3")
    def turn3(self):
        return self._post("go to apartment_parking_garage")

    @step(kind="action", description="Turn 4")
    def turn4(self):
        return self._post("go to my_car")

    @step(kind="action", description="Turn 5")
    def turn5(self):
        return self._post("go to workplace_lobby")

    @step(kind="assert", description="Validate state and time")
    def assert_state(self):
        from backend.app.api import prompt_engine as chat_module

        sess = chat_module.SESSIONS["t1"]
        st = sess["state"]

        assert st.location_id == "workplace_lobby"
        assert st.location == "EDAM Entertainment Lobby"

        reply_text = self.state.last_response["reply"]
        assert not reply_text.startswith("[")
        assert reply_text.lstrip().startswith("*")

        expected_minute = 0 + 3 + (2 + (1 + 2)) + (2 + (1 + 3)) + (2 + (1 + 1)) + (2 + (1 + 15))
        assert st.minute == expected_minute
        return self.debug_info({"location_id": st.location_id, "location": st.location, "minute": st.minute})
