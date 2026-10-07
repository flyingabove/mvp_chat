"""Courtship and intensity: who can court or compete comes from the story's data, never a literal gender (P-08 slice 2)."""
import pytest

from backend.app.engine.rules.tracks import INTENSITY_PRESETS, AppraisalPolicy, Intensity, _intensity, social_rules
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.agenda import intentions
from backend.app.engine.world_model.courtship import Courtship
from backend.app.engine.world_model.intentions import propose_rival_invitations
from backend.app.engine.world_model.offscreen import find_encounters, outcome_weights
from backend.app.engine.world_model.rivals import seed_rival_aims
from backend.app.engine.world_model.stepper import StepResult
from tests.backend.app.engine.world_model.helpers import FakeRelationships, make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
GENDERS = {"ben": "M", "dan": "M", "ann": "F", "cat": "F", "player": "M"}


def _policy(eligible):
    return AppraisalPolicy("romance", 3.0, 0.3, 0.02, frozenset(), "", eligible)


def _rules(eligible="opposite_gender", intensity=Intensity(), rival_aim=0.3):
    base = social_rules(TERRACE)
    couples = type(base.couples)(base.couples.interested_tier, base.couples.dating_tier, base.couples.committed_tier,
                                 base.couples.days_together, rival_aim)
    return type(base)(base.tracks, base.requirements, _policy(eligible), couples, intensity)


# ---------------------------------------------------------------- the intensity knob
def test_intensity_defaults_to_the_old_full_strength_and_reads_presets_numbers_and_each_knob():
    assert _intensity(None) == Intensity(1.0, 1.0) and social_rules(TERRACE).intensity == Intensity(1.0, 1.0)
    assert _intensity("low") == Intensity(INTENSITY_PRESETS["low"], INTENSITY_PRESETS["low"])
    assert _intensity({"romance": "off", "rivalry": 0.8}) == Intensity(0.0, 0.8)
    assert _intensity({"romance": "medium"}) == Intensity(INTENSITY_PRESETS["medium"], 1.0)


@pytest.mark.parametrize("bad", ["fierce", 1.5, -0.1, {"romnce": "low"}])
def test_a_bad_intensity_is_refused_at_load(bad):
    with pytest.raises(ValueError):
        _intensity(bad)


def test_terrace_runs_romance_on_high_by_saying_so():
    assert TERRACE["social_tracks"]["intensity"] == "high"


# ---------------------------------------------------------------- who can court and who competes
def test_competition_follows_the_story_policy_not_a_literal_gender():
    opposite = Courtship(_policy("opposite_gender"), GENDERS)
    assert opposite.competes("dan", "player", "ann") and not opposite.competes("cat", "player", "ann")
    assert not opposite.competes("dan", "player", "ben"), "same-gender partner is not courted under this track"
    anyone = Courtship(_policy("any"), GENDERS)
    assert anyone.competes("cat", "player", "ann") and anyone.competes("dan", "player", "ben")
    assert not Courtship(None, GENDERS).eligible("ben", "ann"), "a story with no romance track has no courtship"
    assert not opposite.competes("dan", "dan", "ann") and not opposite.competes("dan", "player", "dan")


def test_unknown_genders_court_nobody_under_an_opposite_gender_track_but_anyone_under_any():
    unknown = {"a": "", "b": "", "player": ""}
    assert not Courtship(_policy("opposite_gender"), unknown).competes("a", "player", "b")
    assert Courtship(_policy("any"), unknown).competes("a", "player", "b")


# ---------------------------------------------------------------- the mechanics read it, scaled by intensity
def _aims(rules, genders=GENDERS, player_gender="M"):
    model = make_model({"ben": "k", "dan": "k", "ann": "k", "cat": "k"})
    model.standing.bind(rules.tracks)
    added = seed_rival_aims(model, rules, {k: v for k, v in genders.items() if k != "player"}, player_gender)
    priorities = {c: [i.priority for i in intentions(model, c, 0)] for c in ("ben", "dan", "ann", "cat")}
    return added, priorities


def test_rival_aims_scale_with_rivalry_intensity_and_vanish_at_zero():
    full_added, full = _aims(_rules())
    assert {r for r, _ in full_added} == {"ben", "dan"} and full["ben"] == [0.3]
    _, half = _aims(_rules(intensity=Intensity(1.0, 0.5)))
    assert half["ben"] == [pytest.approx(0.15)]
    assert _aims(_rules(intensity=Intensity(1.0, 0.0)))[0] == []


def test_rival_aims_work_for_any_gender_setup_when_the_story_says_any():
    added, _ = _aims(_rules("any"), genders={"ben": "", "dan": "", "ann": "", "cat": ""}, player_gender="")
    assert {r for r, _ in added} == {"ben", "dan", "ann", "cat"}, "with no gender rule everyone is a possible rival"


def _enc():
    snap = {"rival": ("k", "awake"), "partner": ("k", "awake")}
    result = StepResult(timeline=[(0, snap, "terrace", True), (30, snap, "terrace", True)])
    return make_model({"rival": "k", "partner": "k"}), find_encounters(result)[0]


def test_offscreen_contest_boost_scales_with_rivalry_intensity():
    model, enc = _enc()
    rel = FakeRelationships({("player", "partner"): {"affection": 0.4}, ("rival", "partner"): {"affection": 0.3}})
    genders = {"rival": "M", "partner": "F", "player": "M"}
    base = outcome_weights(model, enc, rel)

    def boosted(strength):
        context = {"enabled": True, "courtship": Courtship(_policy("opposite_gender"), genders, Intensity(1.0, strength))}
        return outcome_weights(model, enc, rel, rivalry=context)
    full, half, none = boosted(1.0), boosted(0.5), boosted(0.0)
    assert full["plan"] == pytest.approx(base["plan"] * 2.0) and full["affection"] == pytest.approx(base["affection"] * 1.5)
    assert half["plan"] == pytest.approx(base["plan"] * 1.5) and half["affection"] == pytest.approx(base["affection"] * 1.25)
    assert none == base


def test_rival_invitations_stop_when_rivalry_is_off():
    model = make_model({"rival": "k", "partner": "k"})
    model.world.move("player", "k")
    rel = FakeRelationships({("player", "partner"): {"affection": 0.5}, ("rival", "partner"): {"affection": 0.4},
                             ("partner", "rival"): {"affection": 0.2}})
    genders = {"rival": "M", "partner": "F", "player": "M"}

    def invite(strength):
        context = {"enabled": True, "courtship": Courtship(_policy("opposite_gender"), genders, Intensity(1.0, strength))}
        return propose_rival_invitations(model, context, rel, 600)
    assert invite(1.0) is not None
    model.initiative_last_day.clear()
    assert invite(0.0) is None


# ---------------------------------------------------------------- fallout of a refused confession
def _fallout(intensity):
    import copy
    from tests.backend.app.engine.world_model import test_act_fallout as fx
    from backend.app.engine.world_model.standing import Standing
    model = fx._scene()
    state = fx._state(model)
    cfg = copy.deepcopy(state.story_cfg)
    cfg["social_tracks"]["intensity"] = intensity
    state.story_cfg = cfg
    fx._bind(model, state)
    for owner in ("arisa", "minori"):
        model.standing.standings[(owner, "player", "romance")] = Standing(value=30.0)
    fx._confess(model, state, "reject")
    return model, fx._standing(model, "arisa"), fx._standing(model, "minori")


def test_a_refused_confession_costs_the_asker_in_proportion_to_romance_intensity_and_rivals_need_rivalry():
    model, witness_full, refuser_full = _fallout("high")
    _, witness_half, refuser_half = _fallout({"romance": 0.5, "rivalry": 1.0})
    _, witness_off, refuser_off = _fallout({"romance": "off", "rivalry": 1.0})
    assert (30 - witness_half) == pytest.approx((30 - witness_full) / 2, rel=0.05)
    assert (30 - refuser_half) == pytest.approx((30 - refuser_full) / 2, rel=0.05)
    assert witness_off == 30.0 and refuser_off == 30.0
    assert any(i.kind == "pursue" and i.target == "minori" for i in intentions(model, "makoto", 0))
    quiet, _, _ = _fallout({"romance": 1.0, "rivalry": "off"})
    assert not any(i.kind == "pursue" for i in intentions(quiet, "makoto", 0)), "no rivalry, no rival taking an opening"


# ---------------------------------------------------------------- tuning numbers are story data
def test_tuning_defaults_to_the_engine_numbers_and_refuses_bad_data():
    from backend.app.engine.rules.tracks import DramaTuning, _tuning
    assert _tuning(None) == DramaTuning(2.0, 2.5, 0.5, 1.0, 0.5)
    assert _tuning({"witness_loss": 4}).witness_loss == 4.0 and _tuning({"witness_loss": 4}).refuser_loss == 2.5
    for bad in ({"witnes_loss": 1}, {"rival_aim": -1}, {"rival_aim": "lots"}, [1]):
        with pytest.raises(ValueError):
            _tuning(bad)


def test_tuning_scales_a_refused_confession_and_the_offscreen_contest_boost():
    from backend.app.engine.rules.tracks import DramaTuning
    base = _fallout("high")
    import copy
    from tests.backend.app.engine.world_model import test_act_fallout as fx
    model = fx._scene()
    state = fx._state(model)
    cfg = copy.deepcopy(state.story_cfg)
    cfg["social_tracks"]["tuning"] = {"witness_loss": 4.0, "refuser_loss": 5.0}
    state.story_cfg = cfg
    fx._bind(model, state)
    from backend.app.engine.world_model.standing import Standing
    for owner in ("arisa", "minori"):
        model.standing.standings[(owner, "player", "romance")] = Standing(value=30.0)
    fx._confess(model, state, "reject")
    assert (30 - fx._standing(model, "minori")) == pytest.approx(2 * (30 - base[2]), rel=0.05)
    mdl, enc = _enc()
    rel = FakeRelationships({("player", "partner"): {"affection": 0.4}, ("rival", "partner"): {"affection": 0.3}})
    context = {"enabled": True, "courtship": Courtship(
        _policy("opposite_gender"), {"rival": "M", "partner": "F", "player": "M"}, Intensity(), DramaTuning(contest_plan=3.0))}
    plain = outcome_weights(mdl, enc, rel)
    assert outcome_weights(mdl, enc, rel, rivalry=context)["plan"] == pytest.approx(plain["plan"] * 4.0)
