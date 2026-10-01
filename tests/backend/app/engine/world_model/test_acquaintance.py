"""Acquaintance: closeness comes from time together, not from the model's default warmth (BL-76 / BL-84).

Simulation on Ollama (2026-09-30) showed a resident using the player's name on turn 3 and blushing and inventing a
shared past on turn 5. The relationship numbers were slow; the storyteller just never knew how well they knew each
other. Each present resident's scene line now carries the conduct of the acquaintance level they have reached.
"""
from types import SimpleNamespace

import pytest

from backend.app.engine.rules.acquaintance import acquaintance_levels, level_for
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.projection import render_header, render_scene_section
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

LEVELS = {"acquaintance": {"levels": [
    {"id": "strangers", "min_days": 0, "min_turns": 0, "conduct": "STRANGER-CONDUCT", "reminder": "STRANGER-REMINDER"},
    {"id": "acquaintances", "min_days": 0, "min_turns": 10, "conduct": "ACQUAINTED-CONDUCT"},
    {"id": "familiar", "min_days": 1, "min_turns": 30, "conduct": "FAMILIAR-CONDUCT"},
]}}


def test_a_level_needs_both_enough_days_and_enough_turns():
    levels = acquaintance_levels(LEVELS)
    assert level_for(levels, 0, 0).id == "strangers"
    assert level_for(levels, 0, 9).id == "strangers"
    assert level_for(levels, 0, 10).id == "acquaintances"
    assert level_for(levels, 0, 500).id == "acquaintances", "many turns on day 0 never make anyone familiar"
    assert level_for(levels, 3, 5).id == "strangers", "days alone do not either"
    assert level_for(levels, 1, 30).id == "familiar"
    assert level_for((), 9, 9) is None


@pytest.mark.parametrize("levels", [
    [{"id": "a", "min_days": 1, "min_turns": 0, "conduct": "x"}],                                    # must start at 0/0
    [{"id": "a", "min_days": 0, "min_turns": 0, "conduct": "x"}, {"id": "a", "min_days": 1, "min_turns": 1, "conduct": "y"}],
    [{"id": "a", "min_days": 0, "min_turns": 0, "conduct": "x"}, {"id": "b", "min_days": 0, "min_turns": 0, "conduct": "y"}],
    [{"id": "a", "min_days": 0, "min_turns": 5, "conduct": "x"}, {"id": "b", "min_days": 1, "min_turns": 2, "conduct": "y"}],
    [{"id": "a", "min_days": 0, "min_turns": 0, "conduct": ""}],
])
def test_bad_level_declarations_are_rejected(levels):
    with pytest.raises(ValueError):
        acquaintance_levels({"acquaintance": {"levels": levels}})


def test_stories_without_levels_are_unchanged():
    assert acquaintance_levels({}) == ()
    assert acquaintance_levels({"acquaintance": {}}) == ()


def _state(model, cfg):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)


def _card(model, cid):
    return next(c for c in model.view.cards if c.startswith(model.characters[cid].name))


def test_the_scene_line_carries_the_conduct_of_the_level_reached_and_it_loosens_with_time():
    model = make_model({"ann": "kitchen", "ben": "living_room"})
    state = _state(model, LEVELS)
    begin_turn(state, "hello", 0)
    assert "STRANGER-CONDUCT" in _card(model, "ann")
    for _ in range(9):
        begin_turn(state, "and so on", 0)
    assert "ACQUAINTED-CONDUCT" in _card(model, "ann") and "STRANGER-CONDUCT" not in _card(model, "ann")
    assert model.turns_together["ann"] == 10
    assert "ben" not in model.turns_together, "someone in another room does not get closer to the player"


def test_turns_together_survive_a_save_and_load():
    model = make_model({"ann": "kitchen"})
    begin_turn(_state(model, LEVELS), "hello", 0)
    restored = type(model).from_dict(model.to_dict())
    assert restored.turns_together == {"ann": 1}


def test_terrace_authors_a_valid_ladder_that_starts_with_strangers():
    levels = acquaintance_levels(build_story_registry()["six_strangers"]["raw"])
    assert levels and levels[0].id == "strangers"
    assert "no shared" in levels[0].conduct.lower() or "never" in levels[0].conduct.lower()


def test_the_header_beside_the_players_message_carries_a_short_reminder_per_person():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    begin_turn(_state(model, LEVELS), "hello", 0)
    header = render_header(model.view)
    assert "Ann: STRANGER-REMINDER" in header and "Ben: STRANGER-REMINDER" in header


def test_residents_who_have_not_heard_the_name_are_told_not_to_use_it_until_it_is_said():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = _state(model, LEVELS)
    begin_turn(state, "hello there", 0)
    assert set(model.view.not_told_name) == {"ann", "ben"}
    header, scene = render_header(model.view), render_scene_section(model.view)
    assert "have not heard the player's name" in header and "Ann" in header
    assert "or by name" not in scene, "the scene section no longer invites the name for people who have not heard it"
    begin_turn(state, "I'm Paul, by the way.", 0)
    assert model.view.not_told_name == [], "once it is said in their hearing they may use it"
    assert "have not heard the player's name" not in render_header(model.view)
