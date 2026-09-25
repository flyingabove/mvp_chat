"""Tests for backend/app/engine/opening_scene.py - the engine-backed welcome party."""
import random

import pytest

from backend.app.engine.opening_scene import (
    WelcomePartyRule,
    character_gender,
    choose_welcome_party,
    opening_scene_brief,
    stage_opening_scene,
)
from backend.app.engine.state import Character, init_state

GENDERS = {"m1": "M", "m2": "M", "m3": "M", "f1": "F", "f2": "F", "f3": "F"}


def _state(player_gender: str, rule: dict | None, locations: dict | None = None):
    state = init_state()
    state.gender = player_gender
    state.location_id = "front_entry"
    state.story_cfg = {
        "opening": {"welcome_party": rule} if rule is not None else {},
        "cast_lifecycle": {"initial_active_location_id": "living_room"},
    }
    state.characters = {
        key: Character.from_dict({"key": key, "name": key.upper(), "gender": gender})
        for key, gender in GENDERS.items()
    }
    state.character_locations = dict(locations or {})
    return state


def test_rule_parsing_defaults_and_validation():
    assert WelcomePartyRule.from_config(None) is None
    rule = WelcomePartyRule.from_config({})
    assert (rule.size, rule.gender, rule.exclusive) == (2, "any", True)
    assert WelcomePartyRule.from_config({"gender": "f"}).gender == "F"
    with pytest.raises(ValueError):
        WelcomePartyRule.from_config({"gender": "tallest"})
    with pytest.raises(ValueError):
        WelcomePartyRule.from_config({"size": 0})


@pytest.mark.parametrize(
    "rule_gender, player, wanted",
    [
        ("opposite_player", "M", "F"),
        ("opposite_player", "F", "M"),
        ("same_as_player", "F", "F"),
        ("any", "M", None),
        ("M", "F", "M"),
        ("opposite_player", None, None),
    ],
)
def test_wanted_gender(rule_gender, player, wanted):
    assert WelcomePartyRule(gender=rule_gender).wanted_gender(player) == wanted


def test_character_gender_reads_authored_json_field():
    assert character_gender(Character.from_dict({"key": "a", "gender": "female"})) == "F"
    assert character_gender(Character.from_dict({"key": "b"})) is None
    assert character_gender(None) is None


@pytest.mark.parametrize("player, expected", [("M", {"f1", "f2", "f3"}), ("F", {"m1", "m2", "m3"})])
def test_choose_opposite_gender_party(player, expected):
    rule = WelcomePartyRule(size=2, gender="opposite_player")
    for seed in range(20):
        party = choose_welcome_party(GENDERS, GENDERS, player, rule, random.Random(seed))
        assert len(party) == 2 and len(set(party)) == 2
        assert set(party) <= expected


def test_choose_fills_from_others_when_too_few_match():
    rule = WelcomePartyRule(size=2, gender="opposite_player")
    party = choose_welcome_party(["f1", "m1", "m2"], GENDERS, "M", rule, random.Random(1))
    assert party[0] == "f1" and len(party) == 2 and party[1] in {"m1", "m2"}


def test_choose_never_picks_player_or_duplicates():
    rule = WelcomePartyRule(size=3)
    party = choose_welcome_party(["player", "m1", "m1", "f1"], GENDERS, "M", rule, random.Random(0))
    assert sorted(party) == ["f1", "m1"]


@pytest.mark.parametrize("player, other", [("M", "F"), ("F", "M")])
def test_stage_places_exactly_the_party_with_the_player(player, other):
    state = _state(
        player,
        {"size": 2, "gender": "opposite_player", "exclusive": True},
        locations={"m1": "front_entry", "f1": "front_entry", "m2": "dining_room"},
    )
    party = stage_opening_scene(state, random.Random(3))

    assert state.opening_cast == party and len(party) == 2
    assert all(GENDERS[key] == other for key in party)
    in_room = {k for k, loc in state.character_locations.items() if loc == "front_entry"}
    assert in_room == set(party)
    # Displaced NPCs go to the fallback room instead of vanishing.
    for key in {"m1", "f1"} - set(party):
        assert state.character_locations[key] == "living_room"
    assert state.character_locations["m2"] == "dining_room"
    assert state.main_character_id == party[0]


def test_stage_non_exclusive_keeps_other_occupants():
    state = _state("M", {"size": 1, "gender": "F", "exclusive": False}, {"m1": "front_entry"})
    party = stage_opening_scene(state, random.Random(0))
    assert state.character_locations["m1"] == "front_entry"
    assert state.character_locations[party[0]] == "front_entry"


def test_stage_is_noop_without_authored_rule():
    state = _state("M", None, {"m1": "front_entry"})
    state.main_character_id = "m1"
    assert stage_opening_scene(state) == []
    assert state.opening_cast == []
    assert state.character_locations == {"m1": "front_entry"}
    assert state.main_character_id == "m1"


def test_brief_names_party_only_before_first_reply():
    state = _state("M", {"size": 2, "gender": "opposite_player"})
    state.opening_cast = ["f1", "f2"]
    brief = opening_scene_brief(state)
    assert "F1 and F2 just greeted the player" in brief
    state.turns = 1
    assert opening_scene_brief(state) == ""
    state.turns = 0
    state.opening_cast = []
    assert opening_scene_brief(state) == ""


def test_stage_never_untracks_residents_when_fallback_is_the_start_room():
    state = _state("M", {"size": 2, "gender": "opposite_player"}, {k: "front_entry" for k in GENDERS})
    state.story_cfg["cast_lifecycle"]["initial_active_location_id"] = "front_entry"
    stage_opening_scene(state, random.Random(0))
    assert set(state.character_locations) == set(GENDERS)
    assert all(loc == "front_entry" for loc in state.character_locations.values())
