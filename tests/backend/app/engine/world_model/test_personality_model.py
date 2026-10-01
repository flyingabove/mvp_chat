"""Personality model (BL-80): a four-letter type and a strategy shape how any character behaves socially.

Generic, any story. `type` (e.g. "ENFP") supplies DEFAULTS for three social dials (sociability, planfulness, candor)
that an author's explicit dials always override; `strategy` scales how hard and how fast someone pursues what they
want. Both feed existing mechanisms (rival aims, affinity signals, the room's energy) rather than adding a parallel one.
"""
from types import SimpleNamespace

import pytest

from backend.app.engine.rules.personality import (
    STRATEGIES, personalities, personality_for, strategy_mods,
)
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model.rivals import seed_rival_aims
from backend.app.engine.world_model.signals import Candidate, choose_signal, DEFAULT_CATALOGUE
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model


def _cfg(**own):
    return {"characters": [{"key": "ann"}], "personalities": {"ann": own}}


def _dials(**own):
    return personality_for(_cfg(**own), {"key": "ann"}).temperament


def test_a_type_supplies_default_dials_for_each_letter_pair():
    extravert_planner = _dials(type="ESTJ")
    assert (extravert_planner.sociability, extravert_planner.planfulness, extravert_planner.candor) == (0.8, 0.75, 0.7)
    reserved_drifter = _dials(type="INFP")
    assert (reserved_drifter.sociability, reserved_drifter.planfulness, reserved_drifter.candor) == (0.25, 0.3, 0.4)
    assert _dials().sociability == 0.5, "no type means neutral, as before"


def test_explicit_dials_always_beat_the_type_and_the_type_is_case_insensitive():
    assert _dials(type="enfp", temperament={"sociability": 0.1}).sociability == 0.1
    assert _dials(type="enfp").sociability == 0.8
    assert personality_for(_cfg(type="infj"), {"key": "ann"}).type == "INFJ"


@pytest.mark.parametrize("bad", ["XNFP", "ENF", "ENFPJ", "1234", 7])
def test_a_malformed_type_is_rejected(bad):
    with pytest.raises(ValueError):
        personality_for(_cfg(type=bad), {"key": "ann"})


def test_strategy_defaults_to_open_and_unknown_strategies_are_rejected():
    assert personality_for(_cfg(), {"key": "ann"}).strategy == "open"
    assert personality_for(_cfg(strategy="scheming"), {"key": "ann"}).strategy == "scheming"
    with pytest.raises(ValueError):
        personality_for(_cfg(strategy="sorcerer"), {"key": "ann"})
    assert set(STRATEGIES) >= {"open", "fast_mover", "patient", "scheming", "safe_pick", "career_first"}


def test_strategies_scale_pursuit_in_the_expected_order():
    scale = {name: strategy_mods(name).aim_scale for name in STRATEGIES}
    assert scale["fast_mover"] > scale["open"] == 1.0 > scale["patient"] > scale["career_first"]
    assert strategy_mods("nonsense").aim_scale == 1.0


# ---- consumers

RULES_CFG = {"social_tracks": {
    "tracks": [{"id": "romance", "daily_gain_cap": 8, "repeat_decay": 0.5, "tiers": [
        {"id": "a", "floor": 0, "ceiling": 50}, {"id": "b", "floor": 50, "ceiling": 100}]}],
    "appraisal": {"track": "romance", "eligible": "opposite_gender"},
    "couples": {"interested_tier": "b", "dating_tier": "b", "committed_tier": "b", "rival_aim": 0.4},
}}
GENDERS = {"rival": "M", "fast": "M", "slow": "M", "girl": "F"}


def _aim(strategy):
    model = make_model({"rival": "kitchen", "girl": "kitchen"})
    people = personalities({"characters": [{"key": "rival"}, {"key": "girl"}],
                            "personalities": {"rival": {"strategy": strategy}}})
    pairs = seed_rival_aims(model, social_rules(RULES_CFG), {"rival": "M", "girl": "F"}, "M", people)
    assert pairs
    return model.agendas["rival"][0].priority


def test_a_rivals_starting_aim_is_scaled_by_their_strategy():
    assert _aim("open") == pytest.approx(0.4)
    assert _aim("fast_mover") > _aim("open") > _aim("patient") > _aim("career_first")
    assert _aim("fast_mover") <= 1.0


def test_sociable_people_signal_more_often_than_reserved_ones():
    def rate(sociability):
        c = [Candidate("a", 0.6, 0.5, 0.5, sociability)]
        return sum(choose_signal(c, t, "s", {}, DEFAULT_CATALOGUE) is not None for t in range(1, 600, 4))
    assert rate(0.9) > rate(0.5) > rate(0.1)


def _state(model, cfg):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)


def _energy(types):
    keys = [f"p{i}" for i in range(len(types))]
    model = make_model({k: "kitchen" for k in keys})
    cfg = {"characters": [{"key": k} for k in keys], "personalities": {k: {"type": t} for k, t in zip(keys, types)}}
    begin_turn(_state(model, cfg), "hello", 0)
    return model.view.energy


def test_the_room_has_an_energy_that_follows_who_is_in_it():
    assert "lively" in _energy(["ENFP", "ESTP", "ESFJ"])
    assert "quiet" in _energy(["INFP", "ISTJ", "INTJ"])
    assert _energy(["ENFP", "INFP"]) == "", "a mixed room gets no label"


def test_the_energy_reaches_the_storyteller_scene_section():
    from backend.app.engine.world_model.projection import render_scene_section
    model = make_model({"a": "kitchen", "b": "kitchen"})
    cfg = {"characters": [{"key": "a"}, {"key": "b"}], "personalities": {"a": {"type": "INFP"}, "b": {"type": "ISTJ"}}}
    begin_turn(_state(model, cfg), "hello", 0)
    assert "quiet" in render_scene_section(model.view)


def test_terrace_gives_every_cast_member_a_type_and_a_strategy():
    from backend.app.engine.story_loader import build_story_registry
    cfg = build_story_registry()["six_strangers"]["raw"]
    people = personalities(cfg)
    assert len(people) == 17 and all(p.type for p in people.values())
    assert {p.strategy for p in people.values()} <= set(STRATEGIES)
    assert len({p.strategy for p in people.values()}) >= 3, "a house of one strategy would play flat"
    dials = {p.temperament.sociability for p in people.values()}
    assert dials == {0.25, 0.8}, "types, not author dials, set sociability here"
