"""P-06: the real-model Writer, driven by a scripted chat so no model is called."""
import asyncio
import re
import threading
from types import SimpleNamespace

import pytest

from backend.app.sim import llm_writer
from backend.app.sim.llm_writer import CallCapReached, LLMWriter, bridge_chat, parse_json_object
from backend.app.sim.runner import SeasonRunner
from backend.app.sim.story_loader import build_season


class ScriptedChat:
    """Replies in order; records every (system, user, temperature, max_tokens)."""

    def __init__(self, *replies):
        self.replies, self.seen = list(replies), []

    def __call__(self, system, user, temperature, max_tokens):
        self.seen.append((system, user, temperature, max_tokens))
        return self.replies.pop(0)


@pytest.fixture()
def setup():
    return build_season("six_strangers", "w1")


def _pair(setup):
    a, b = sorted(setup.cast)[:2]
    return a, b, f"Present: {a}, {b}\nPlace: living_room\nMinute: 90\nWrite what happens between them."


def test_the_scene_prompt_carries_names_roles_place_and_clock_and_no_drama_nudge(setup):
    a, b, prompt = _pair(setup)
    chat = ScriptedChat("They talked.")
    text = LLMWriter(chat, setup, max_calls=4).write_scene(prompt)
    system, user, temperature, tokens = chat.seen[0]
    assert text == "They talked." and tokens >= 1000
    assert setup.name(a) in user and setup.name(b) in user and setup.cast[a].role in user
    assert "Wednesday 16:30" in user and setup.place("living_room") in user
    assert setup.title in system and "dramatic" not in (system + user).lower()


def test_extraction_reads_the_summary_and_clamps_feeling_changes(setup):
    a, b, prompt = _pair(setup)
    reply = ('```json\n{"summary": "A cooled toward B.", "relationship_deltas": [{"a": "%s", "b": "%s", "trust": -0.9, '
             '"affection": 0.1}, {"a": "%s", "b": "%s"}]}\n```' % (a, b, b, a))
    chat = ScriptedChat("scene text", reply)
    writer = LLMWriter(chat, setup, max_calls=4)
    update = writer.extract(writer.write_scene(prompt) and "scene text")
    assert update.summary == "A cooled toward B." and len(update.relationship_deltas) == 1
    delta = update.relationship_deltas[0]
    assert (delta.a, delta.b) == (a, b) and delta.trust_delta == -0.3 and delta.affection_delta == 0.1
    assert setup.name(a) in chat.seen[1][1] and f"id {a}" in chat.seen[1][1]


def test_unusable_extraction_becomes_a_summary_only_update_and_is_counted(setup):
    _, _, prompt = _pair(setup)
    writer = LLMWriter(ScriptedChat("First sentence here. Second one.", "I cannot do that."), setup, max_calls=4)
    update = writer.extract(writer.write_scene(prompt))
    assert update.summary == "First sentence here." and update.relationship_deltas == () and writer.unparsed == 1


def test_text_the_writer_did_not_just_write_is_never_attributed_to_anyone(setup):
    chat = ScriptedChat()
    update = LLMWriter(chat, setup, max_calls=4).extract("Some other scene entirely. It ends.")
    assert update.summary == "Some other scene entirely." and update.relationship_deltas == () and chat.seen == []


def test_the_call_cap_refuses_before_the_call_is_made(setup):
    _, _, prompt = _pair(setup)
    chat = ScriptedChat("scene", "{}")
    writer = LLMWriter(chat, setup, max_calls=1)
    text = writer.write_scene(prompt)
    with pytest.raises(CallCapReached):
        writer.extract(text)
    assert writer.calls == 1 and len(chat.seen) == 1


def test_a_season_on_the_llm_writer_rejects_feelings_about_people_who_were_not_there(setup):
    def chat(system, user, temperature, max_tokens):
        if system.startswith("You write"):
            return "They sat and talked for a while."
        first, second = re.findall(r"\(id (\w+)\)", user)
        return ('{"summary": "They talked.", "relationship_deltas": [{"a": "%s", "b": "%s", "trust": 0.1}, '
                '{"a": "%s", "b": "stranger", "fear": 0.2}]}' % (first, second, first))
    writer = LLMWriter(chat, setup, max_calls=20)
    result = SeasonRunner(setup.story, "w1", writer, days=1, scenes_per_day=2).run()
    assert result.calls_used == 2 and writer.calls == 4
    assert len(result.all_rejections) == 2 and all("stranger" in r for r in result.all_rejections)
    assert all(s.text == "They sat and talked for a while." for s in result.days[0].scenes)
    assert setup.story.relationships.state            # the grounded delta was applied, the invented one was not


def test_parse_json_object_finds_the_object_or_says_none():
    assert parse_json_object('Sure! {"a": 1} hope that helps') == {"a": 1}
    assert parse_json_object("no json") is None and parse_json_object("{broken") is None
    assert parse_json_object("[1, 2]") is None


def test_the_bridge_runs_each_call_on_the_main_loop_and_retries_once(monkeypatch):
    calls = []

    async def fake_get_chat(system, messages, **kwargs):
        calls.append((threading.current_thread().name, kwargs["provider"], kwargs["max_tokens"]))
        if len(calls) == 1:
            raise RuntimeError("transient")
        return SimpleNamespace(text="hello")

    monkeypatch.setattr("backend.app.llm.chat.get_chat", fake_get_chat)

    async def go():
        chat = bridge_chat(asyncio.get_running_loop(), provider="gemini")
        return await asyncio.to_thread(chat, "sys", "user", 0.5, 100)

    assert asyncio.run(go()) == "hello"
    assert len(calls) == 2 and calls[0][1:] == ("gemini", 100)
    assert calls[0][0] == threading.main_thread().name       # ran on the loop's thread, not the worker's


def test_the_bridge_gives_up_after_its_retries(monkeypatch):
    async def always_down(system, messages, **kwargs):
        raise RuntimeError("down")

    monkeypatch.setattr("backend.app.llm.chat.get_chat", always_down)

    async def go():
        return await asyncio.to_thread(bridge_chat(asyncio.get_running_loop(), retries=1), "s", "u", 0.5, 10)

    with pytest.raises(RuntimeError):
        asyncio.run(go())
