"""BL-47: what each character has already said, read from the world model's dialogue memories."""
from types import SimpleNamespace

from backend.app.engine.world_model.turn import begin_turn, end_turn, own_spoken_lines

from tests.backend.app.engine.world_model.helpers import make_model


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                           story_cfg={"world_model": {"enabled": True}}, characters=model.characters,
                           cast_lifecycle=None, character_graph=None)


def _say(state, message, segments):
    begin_turn(state, message, 0)
    end_turn(state, message, segments)


def test_each_character_gets_only_their_own_spoken_lines():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model)
    _say(state, "Hi both.", [{"kind": "dialogue", "speaker_id": "ann", "text": "Hello Paul, lovely to meet you today."},
                              {"kind": "narration", "speaker_id": None, "text": "Ben nods from the corner."},
                              {"kind": "dialogue", "speaker_id": "ben", "text": "Good to see you here, Paul."}])
    lines = own_spoken_lines(state)
    assert lines["ann"] == ["Hello Paul, lovely to meet you today."]
    assert lines["ben"] == ["Good to see you here, Paul."]


def test_the_players_words_and_narration_are_not_anyones_history():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _say(state, "I like the way you cook, Ann.", [{"kind": "narration", "speaker_id": None, "text": "Ann laughs quietly."}])
    assert own_spoken_lines(state).get("ann", []) == []
    assert "player" not in own_spoken_lines(state)


def test_lines_accumulate_across_turns_oldest_first():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _say(state, "One.", [{"kind": "dialogue", "speaker_id": "ann", "text": "This is the very first thing I said."}])
    _say(state, "Two.", [{"kind": "dialogue", "speaker_id": "ann", "text": "And this is the second thing I said."}])
    assert own_spoken_lines(state)["ann"] == ["This is the very first thing I said.",
                                              "And this is the second thing I said."]


def test_a_missing_or_disabled_world_model_gives_no_history():
    assert own_spoken_lines(SimpleNamespace(world_model=None, story_cfg={})) == {}
    assert own_spoken_lines(SimpleNamespace(story_cfg={})) == {}
