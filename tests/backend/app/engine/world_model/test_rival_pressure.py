"""BL-98: a rival's pursuit moves the target's standing, so rivalry is pressure and not only flavour."""
from dataclasses import replace

import pytest

from backend.app.engine.rules.tracks import DramaTuning, Intensity, social_rules
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.agenda import add_intention
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.rival_move import apply_rival_pressure
from backend.app.engine.world_model.stances import Stance
from backend.app.engine.world_model.standing import Standing
from tests.backend.app.engine.world_model.helpers import make_model

RULES = social_rules(build_story_registry()["six_strangers"]["raw"])
TRACK = RULES.appraisal.track
CAP = RULES.tracks[TRACK].daily_gain_cap          # a gain never beats the track's own daily cap


def _scene(player_crush=True, aim=0.5):
    model = make_model({"rival": "k", "target": "k", "other": "k"})
    model.standing.bind(RULES.tracks)
    for owner, other, value in (("target", "player", 50.0), ("target", "rival", 10.0)):
        model.standing.standings[(owner, other, TRACK)] = Standing(value=value)
    if player_crush:
        model.stances.add(Stance("crush", "target", "player", 1.0, "", (), 0))
    add_intention(model, "rival", Intention("pursue", "target", aim, "drawn to them", 99))
    return model


def _value(model, owner, target):
    return model.standing.get(owner, target, TRACK).value


def test_a_pursued_target_warms_to_the_rival_and_cools_toward_the_player():
    model = _scene()
    apply_rival_pressure(model, RULES, 0, 0)
    assert _value(model, "target", "rival") == pytest.approx(10.0 + min(CAP, 20.0 * 0.5))
    assert _value(model, "target", "player") == pytest.approx(50.0 - 20.0 * 0.5)


def test_pressure_is_once_a_day_and_returns_the_next_day():
    model = _scene()
    apply_rival_pressure(model, RULES, 0, 0)
    after_first = (_value(model, "target", "rival"), _value(model, "target", "player"))
    apply_rival_pressure(model, RULES, 0, 0)
    assert (_value(model, "target", "rival"), _value(model, "target", "player")) == after_first
    apply_rival_pressure(model, RULES, 1, 24 * 60)
    assert _value(model, "target", "player") < after_first[1]


def test_a_target_who_is_not_drawn_to_the_player_is_only_pulled_toward_the_rival():
    model = _scene(player_crush=False)
    apply_rival_pressure(model, RULES, 0, 0)
    assert _value(model, "target", "player") == 50.0 and _value(model, "target", "rival") > 10.0


def test_a_coupled_target_and_a_coupled_rival_are_left_alone_and_aims_at_the_player_are_not_pressure():
    for couple in ("rival|other", "target|other"):
        model = _scene()
        model.npc_couples[couple] = 0
        apply_rival_pressure(model, RULES, 0, 0)
        assert _value(model, "target", "player") == 50.0 and _value(model, "target", "rival") == 10.0
    model = make_model({"rival": "k", "target": "k"})
    model.standing.bind(RULES.tracks)
    model.standing.standings[(("target"), "player", TRACK)] = Standing(value=50.0)
    add_intention(model, "rival", Intention("pursue", "player", 0.5, "x", 99))
    apply_rival_pressure(model, RULES, 0, 0)
    assert _value(model, "target", "player") == 50.0


def test_rivalry_intensity_scales_pressure_and_off_removes_it():
    half = replace(RULES, intensity=Intensity(1.0, 0.5))
    model = _scene()
    apply_rival_pressure(model, half, 0, 0)
    assert _value(model, "target", "player") == pytest.approx(50.0 - 5.0)
    off = replace(RULES, intensity=Intensity(1.0, 0.0))
    model = _scene()
    apply_rival_pressure(model, off, 0, 0)
    assert _value(model, "target", "player") == 50.0


def test_the_story_tunes_the_pressure_and_a_story_without_a_track_has_none():
    strong = replace(RULES, tuning=DramaTuning(rival_pull=40.0, rival_cost=0.0))
    model = _scene()
    apply_rival_pressure(model, strong, 0, 0)
    assert _value(model, "target", "rival") == pytest.approx(10.0 + min(CAP, 40.0 * 0.5)) and _value(model, "target", "player") == 50.0
    apply_rival_pressure(_scene(), None, 0, 0)


def test_a_player_standing_never_goes_below_zero_under_pressure():
    model = _scene(aim=1.0)
    model.standing.standings[("target", "player", TRACK)] = Standing(value=3.0)
    apply_rival_pressure(model, RULES, 0, 0)
    assert _value(model, "target", "player") == 0.0
