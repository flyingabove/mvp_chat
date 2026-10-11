"""Guards found by the 2026-09-25 live run: sleep phrasing and empty-room speakers."""
from types import SimpleNamespace

import pytest

from backend.app.engine.dialogue import dialogue_response_format
from backend.app.engine.state import Character
from backend.app.engine.world_model.model import SpeakerPlan, TurnView
from backend.app.engine.world_model.turn import SLEEP


@pytest.mark.parametrize("message", [
    "I'm going to bed.", "I am going to sleep now", "I'm exhausted. I'm going to bed.", "I go to bed",
    "I'll go to sleep", "I'm heading to bed", "I'm off to bed", "Going to bed now.", "I head to bed.",
    "I'm gonna go to sleep", "time to sleep", "Okay, time for bed.", "I call it a night",
])
def test_first_person_sleep_phrases_trigger_sleep(message):
    assert SLEEP.search(message)


@pytest.mark.parametrize("message", [
    "Did you go to bed late last night?", "When do you usually go to bed?", "Arisa went to bed early.",
    "Are you going to sleep soon?", "I love my bed", "The bed looks comfy",
])
def test_questions_and_mentions_do_not_trigger_sleep(message):
    assert not SLEEP.search(message)


def _state(allowed):
    view = TurnView(plan=SpeakerPlan(), allowed_speakers=allowed)
    return SimpleNamespace(
        characters={"ann": Character(key="ann", name="Ann"), "ben": Character(key="ben", name="Ben")},
        world_model=SimpleNamespace(view=view))


def _enum(state):
    schema = dialogue_response_format(state)["json_schema"]["schema"]
    return schema["properties"]["segments"]["items"]["properties"]["speaker_id"]["enum"]


def test_nobody_present_means_no_named_speaker_is_allowed():
    assert set(_enum(_state([]))) == {"unknown", None}


def test_allowed_speakers_narrow_the_schema():
    assert set(_enum(_state(["ann"]))) == {"ann", "unknown", None}


def test_no_world_model_keeps_the_full_cast():
    state = _state([])
    state.world_model = None
    assert set(_enum(state)) == {"ann", "ben", "unknown", None}
