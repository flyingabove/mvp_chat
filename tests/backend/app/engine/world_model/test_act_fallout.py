"""Fallout of a turned-down high-stakes act (BL-82): witnesses think less of the asker, rivals see an opening.

Generic, any story with social acts. Nothing is scripted: the effects follow from who was in the room, their own
temperament and the story's tracks. A yes has no fallout; a private act (nobody else present) has none either.
Also: a "not yet" can mean "I am drawn to someone else too", derived from the target's own standings and aims.
"""
from types import SimpleNamespace

import pytest

from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.social_acts import (
    ActSpec, SocialAct, Verdict, act_specs, assess, commit,
)
from backend.app.engine.world_model.standing import Standing

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
SPECS = act_specs(TERRACE)
CONFESS = SPECS["confess"]


def _state(model, gender="M"):
    cfg = dict(TERRACE)
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender=gender, turns=5, outcome=None)


def _scene():
    # minori is confessed to; arisa watches (a woman: covered by the romance track); makoto (a man) is a rival.
    return make_model({"minori": "kitchen", "arisa": "kitchen", "makoto": "kitchen"})


def _bind(model, state):
    from backend.app.engine.rules.tracks import social_rules
    model.standing.bind(social_rules(state.story_cfg).tracks)


def _confess(model, state, answer, witnesses=("arisa", "makoto")):
    verdict = Verdict(SocialAct("confess", "minori"), answer, "hint")
    commit(state, CONFESS, verdict, tuple(witnesses))
    return verdict


def _standing(model, owner, target="player"):
    s = model.standing.get(owner, target, "romance")
    return s.value if s else 0.0


def _setup(value_arisa=30.0, value_minori=30.0):
    model = _scene()
    state = _state(model)
    _bind(model, state)
    model.standing.standings[("arisa", "player", "romance")] = Standing(value=value_arisa)
    model.standing.standings[("minori", "player", "romance")] = Standing(value=value_minori)
    return model, state


def test_a_refusal_in_front_of_others_lowers_what_the_witnesses_think_of_the_player():
    model, state = _setup()
    _confess(model, state, "reject")
    assert _standing(model, "arisa") < 30.0, "a woman who watched the refusal thinks less of the player"
    assert _standing(model, "makoto") == 0.0, "the romance track does not cover a man toward a man"


def test_the_one_who_refused_cools_only_on_a_clear_no_not_on_not_yet():
    model, state = _setup()
    _confess(model, state, "not_yet")
    assert _standing(model, "minori") == 30.0
    model.turn += 1
    _confess(model, state, "reject")
    assert _standing(model, "minori") < 30.0


def test_a_yes_and_a_private_act_have_no_fallout():
    model, state = _setup()
    _confess(model, state, "accept")
    assert _standing(model, "arisa") == 30.0
    model, state = _setup()
    _confess(model, state, "reject", witnesses=())
    assert _standing(model, "arisa") == 30.0 and not model.agendas.get("makoto")


def test_a_rival_who_saw_it_gets_an_aim_on_the_person_who_refused():
    model, state = _setup()
    _confess(model, state, "reject")
    aims = [i for i in model.agendas.get("makoto", []) if i.kind == "pursue"]
    assert [i.target for i in aims] == ["minori"] and aims[0].reason == "saw an opening"
    assert not model.agendas.get("arisa"), "only same-gender rivals are emboldened"


def test_skeptical_witnesses_think_less_of_a_failed_attempt_than_forgiving_ones():
    results = {}
    for label, skepticism in (("harsh", 0.9), ("soft", 0.1)):
        model, state = _setup()
        state.story_cfg = dict(TERRACE, personalities={**TERRACE["personalities"],
                                                       "arisa": {"temperament": {"skepticism": skepticism}}})
        _confess(model, state, "reject")
        results[label] = 30.0 - _standing(model, "arisa")
    assert results["harsh"] > results["soft"] > 0


def test_the_fallout_is_recorded_once_per_event():
    model, state = _setup()
    _confess(model, state, "reject")
    losses = [e for e in model.standing.journal if e.tag == "failed_confession"]
    assert {e.owner for e in losses} == {"arisa", "minori"}, "witness and refuser; the man is not covered"
    assert len({e.effect_id for e in losses}) == len(losses)


def test_a_not_yet_can_mean_drawn_to_someone_else_and_stays_unsaid():
    model, state = _setup(value_minori=10.0)
    model.standing.standings[("minori", "makoto", "romance")] = Standing(value=40.0)
    model.agendas["minori"] = [Intention("pursue", "makoto", 0.5, "drawn to them", 99)]
    assessment = assess(model, CONFESS, SocialAct("confess", "minori"), {"minori"})
    assert assessment.verdict.answer == "not_yet"
    assert "drawn to someone else" in assessment.verdict.hint
    assert "makoto" not in assessment.verdict.hint.lower(), "she never says who"


def test_a_plain_not_yet_keeps_the_ordinary_hint():
    model, state = _setup(value_minori=10.0)
    assessment = assess(model, CONFESS, SocialAct("confess", "minori"), {"minori"})
    assert assessment.verdict.hint == "they want to know you better first"
