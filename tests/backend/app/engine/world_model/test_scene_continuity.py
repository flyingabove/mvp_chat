"""BL-39 O11: who the player is, who knows their name, and who has met them."""
from types import SimpleNamespace

from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.projection import render_scene_section
from backend.app.engine.world_model.turn import begin_turn, end_turn

from tests.backend.app.engine.world_model.helpers import make_model


def _state(model, **extra):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                           story_cfg={"world_model": {"enabled": True}},
                           characters=model.characters, cast_lifecycle=None, character_graph=None, **extra)


def _card(model, cid):
    name = model.characters[cid].name
    return next(card for card in model.view.cards if card.startswith(f"{name} ("))


def test_scene_section_says_who_the_player_is_and_how_to_address_them():
    model = make_model({"ann": "kitchen"})
    view = begin_turn(_state(model), "Hi.", 0)
    section = render_scene_section(view)
    assert "The player is Paul." in section
    assert 'address the player directly as "you"' in section


def test_a_speakers_memory_names_the_player_as_the_player():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    begin_turn(state, "I found a key under the mat.", 0)
    model.world.minute = 5
    state.minute = 5
    view = begin_turn(state, "Ann, what do you think about the key under the mat?", 0)
    lines = view.perspectives.get("ann") or []
    assert lines, "Ann should recall what the player told her"
    assert any("the player (Paul) said" in line for line in lines)
    assert not any(line.startswith("Paul said") or "heard from Paul)" in line for line in lines)


def test_characters_learn_the_players_name_from_hearing_it():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "garden"})
    state = _state(model)
    begin_turn(state, "Hi everyone, I'm Paul.", 0)
    assert set(model.knows_player_name) == {"ann", "ben"}, "only people who heard it"
    assert "knows the player's name" in _card(model, "ann")

    model.world.move("cat", "kitchen")
    begin_turn(state, "So, anyway.", 0)
    assert "has not learned the player's name" in _card(model, "cat")
    end_turn(state, "So, anyway.", [{"kind": "dialogue", "speaker_id": "ann", "text": "Cat, this is Paul."}])
    assert "cat" in model.knows_player_name


def test_first_meeting_versus_continuous_company_versus_reunion():
    model = make_model({"ann": "kitchen", "ben": "living_room"})
    state = _state(model)
    begin_turn(state, "Hello.", 0)
    assert "first time meeting the player" in _card(model, "ann")

    begin_turn(state, "Nice kitchen.", 0)
    assert "has been with the player; no greeting or 'welcome back'" in _card(model, "ann")

    model.world.move("ann", "garden")
    begin_turn(state, "Where did everyone go?", 0)
    model.world.move("ann", "kitchen")
    begin_turn(state, "Oh, hi again.", 0)
    assert "apart from the player since earlier" in _card(model, "ann")


def test_the_opening_welcome_party_has_already_met_the_player():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    begin_turn(_state(model, opening_cast=["ann"]), "Thanks for the welcome.", 0)
    assert "has been with the player" in _card(model, "ann")
    assert "first time meeting the player" in _card(model, "ben")


def test_name_and_encounter_knowledge_survive_a_save():
    model = make_model({"ann": "kitchen"})
    begin_turn(_state(model), "I'm Paul.", 0)
    restored = WorldModel.from_dict(model.to_dict())
    assert restored.knows_player_name == ["ann"]
    assert restored.last_with_player == {"ann": 1}
