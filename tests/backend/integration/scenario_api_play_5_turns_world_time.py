"""Playback-ready scenario for chat API with five turns and time/location checks."""

import os
from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from backend.app.integration_playback.scenario import Scenario, Step
from backend.app.integration_playback.scenario_registry import register_scenario


def _make_assistant_reply(turn: int) -> str:
    # Reply follows dialogue prefix format + state tag; timestamp stripped.
    return (
        "*The air feels colder for a breath.*\n"
        f"IU: \"Turn {turn} acknowledged.\"\n"
        "[[STATE]]{\"iu_emotion\":\"wary\",\"rel_delta\":0}[[/STATE]]"
    )


@dataclass
class ChatFiveTurnContext:
    patchers: List[Any] = field(default_factory=list)
    client: TestClient | None = None
    last_response: Any = None
    old_skip_env: str | None = None


def _init_context() -> ChatFiveTurnContext:
    return ChatFiveTurnContext()


def _set_env(state: ChatFiveTurnContext):
    state.old_skip_env = os.environ.get("SKIP_KNOWLEDGE_INDEX_BUILD")
    os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = "1"


def _patch_retrieval(state: ChatFiveTurnContext):
    from backend.app.api import chat as chat_module

    patcher = patch.object(chat_module, "retrieve_knowledge", lambda msg: ([], {"mocked": True}))
    patcher.start()
    state.patchers.append(patcher)


def _patch_openai_post(state: ChatFiveTurnContext):
    from backend.app.api import chat as chat_module

    async def _fake_post(self, url, headers=None, json=None):
        try:
            sess = chat_module.SESSIONS.get("t1")
            st = sess["state"] if sess else None
            turn = getattr(st, "turns", 0)
        except Exception:
            turn = 0
        return _FakeResponse(_make_assistant_reply(turn))

    patcher = patch.object(httpx.AsyncClient, "post", _fake_post)
    patcher.start()
    state.patchers.append(patcher)


def _create_client(state: ChatFiveTurnContext):
    from backend.app.main import app

    state.client = TestClient(app)


def _post_message(state: ChatFiveTurnContext, message: str):
    assert state.client is not None, "Test client not initialized"
    resp = state.client.post("/api/chat", json={"session_id": "t1", "message": message})
    state.last_response = resp
    assert resp.status_code == 200


def _assert_state(state: ChatFiveTurnContext):
    from backend.app.api import chat as chat_module

    sess = chat_module.SESSIONS["t1"]
    st = sess["state"]

    assert st.location_id == "workplace_lobby"
    assert st.location == "EDAM Entertainment Lobby"

    reply_text = state.last_response.json()["reply"]
    assert not reply_text.startswith("[")
    assert reply_text.lstrip().startswith("*")

    expected_minute = 0 + 2 + (2 + (1 + 2)) + (2 + (1 + 3)) + (2 + (1 + 1)) + (2 + (1 + 15))
    assert st.minute == expected_minute


def _cleanup(state: ChatFiveTurnContext):
    for patcher in reversed(state.patchers):
        patcher.stop()

    if state.old_skip_env is None:
        os.environ.pop("SKIP_KNOWLEDGE_INDEX_BUILD", None)
    else:
        os.environ["SKIP_KNOWLEDGE_INDEX_BUILD"] = state.old_skip_env


class _FakeResponse:
    def __init__(self, content: str):
        self.status_code = 200
        self._content = content

    def json(self):
        return {
            "choices": [{"message": {"content": self._content}}],
            "usage": {"total_tokens": 1},
        }


actions = [
    Step(kind="action", description="Init playback context", fn=_init_context, uses_llm=False),
    Step(kind="action", description="Force deterministic env", fn=_set_env, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Patch retrieval", fn=_patch_retrieval, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Patch OpenAI HTTP", fn=_patch_openai_post, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Create TestClient", fn=_create_client, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Start new IU game", fn=_post_message, kwargs={"state": None, "message": "__cmd_newgame__:iu_murder_mystery|M|Chris"}, uses_llm=False),
    Step(kind="action", description="Turn 1: small talk", fn=_post_message, kwargs={"state": None, "message": "hello"}, uses_llm=False),
    Step(kind="action", description="Turn 2: go to lobby", fn=_post_message, kwargs={"state": None, "message": "go to iu_apartment_lobby"}, uses_llm=False),
    Step(kind="action", description="Turn 3: go to parking garage", fn=_post_message, kwargs={"state": None, "message": "go to apartment_parking_garage"}, uses_llm=False),
    Step(kind="action", description="Turn 4: go to car", fn=_post_message, kwargs={"state": None, "message": "go to my_car"}, uses_llm=False),
    Step(kind="action", description="Turn 5: go to workplace lobby", fn=_post_message, kwargs={"state": None, "message": "go to workplace_lobby"}, uses_llm=False),
    Step(kind="assert", description="Validate state and time", fn=_assert_state, kwargs={"state": None}, uses_llm=False),
    Step(kind="action", description="Cleanup patches", fn=_cleanup, kwargs={"state": None}, uses_llm=False),
]

SCENARIO_API_CHAT_5_TURNS = Scenario(
    id="api_chat_5_turns_time_location",
    title="Chat API five turns with travel + time",
    description="Deterministic API flow that checks travel graph resolution and time accounting over five turns.",
    tags=["integration", "chat", "deterministic"],
    requires_api_key=False,
    requires_cache=False,
    steps=actions,
)

register_scenario(SCENARIO_API_CHAT_5_TURNS)
