"""Affinity signals: liking leaks out as small, ambiguous behaviour, never as a stated feeling (generic, any story).

The owner's rule (2026-09-30): show, don't tell, and keep it ambiguous. The player never gets a reliable read: the
person who likes them most asks one more question than anyone else, but a polite person sometimes does the same.
These tests prove the mechanism on a story-free model; Terrace only supplies standings and (optionally) wording.
"""
import random
from types import SimpleNamespace

import pytest

from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.signals import (
    Candidate, DEFAULT_CATALOGUE, choose_signal, interest_of, signal_catalogue,
)
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]
ALL_TEXTS = {t for texts in DEFAULT_CATALOGUE.values() for t in texts}


def _picks(candidates, turns=400, last=None, catalogue=DEFAULT_CATALOGUE):
    out = []
    for turn in range(1, turns + 1):
        out.append(choose_signal(candidates, turn, "seed", last or {}, catalogue))
    return out


def test_the_signal_is_deterministic_for_a_seed_and_at_most_one_per_turn():
    people = [Candidate("ann", 0.5, 0.5, 0.5), Candidate("ben", 0.1, 0.5, 0.5)]
    assert _picks(people) == _picks(people)
    assert all(pick is None or pick[1] in ALL_TEXTS for pick in _picks(people))


def test_the_person_who_likes_the_player_most_signals_far_more_often_but_others_sometimes_do_too():
    people = [Candidate("ann", 0.5, 0.5, 0.5), Candidate("ben", 0.1, 0.5, 0.5), Candidate("cat", 0.1, 0.5, 0.5)]
    who = [p[0] for p in _picks(people) if p]
    assert who.count("ann") > 3 * max(who.count("ben"), who.count("cat")), "the leader signals most"
    assert who.count("ben") + who.count("cat") > 0, "decoys exist, so a signal is never a reliable read"


def test_nobody_signals_when_no_one_likes_the_player_at_all():
    leader_only = _picks([Candidate("ann", 0.0, 0.5, 0.5)])
    assert sum(p is not None for p in leader_only) < 0.2 * len(leader_only), "only the rare polite decoy"


def test_intensity_grows_with_interest_and_is_capped_by_how_open_the_person_is():
    def levels(cand):
        picks = [p for p in _picks([cand], turns=600) if p]
        return {lvl for lvl, texts in DEFAULT_CATALOGUE.items() for p in picks if p[1] in texts}

    assert levels(Candidate("a", 0.2, 0.5, 0.5)) <= {1}, "early liking is only ever the subtlest behaviour"
    assert max(levels(Candidate("a", 0.5, 0.5, 0.5))) == 2
    assert max(levels(Candidate("a", 0.9, 0.5, 0.5))) == 3
    assert max(levels(Candidate("a", 0.9, 0.1, 0.5))) == 2, "a reserved person never goes past the middle"
    assert max(levels(Candidate("a", 0.5, 0.9, 0.5))) == 3, "an open person shows a notch more"


def test_a_proud_person_signals_less_and_a_signal_has_a_cooldown():
    humble, proud = Candidate("a", 0.5, 0.5, 0.0), Candidate("a", 0.5, 0.5, 1.0)
    assert sum(p is not None for p in _picks([humble])) > sum(p is not None for p in _picks([proud]))
    assert choose_signal([humble], 10, "s", {"a": 9}, DEFAULT_CATALOGUE) is None, "not twice in a row"
    assert all(choose_signal([humble], 10, "s", {"a": 8}, DEFAULT_CATALOGUE) is None for _ in range(3)), "or within 3 turns"


def test_interest_is_standing_relative_to_the_track_below_its_last_tier():
    spec = SimpleNamespace(tiers=[SimpleNamespace(ceiling=25), SimpleNamespace(ceiling=75), SimpleNamespace(ceiling=100)])
    assert interest_of(0, spec) == 0.0 and interest_of(37.5, spec) == 0.5 and interest_of(99, spec) == 1.0
    one = SimpleNamespace(tiers=[SimpleNamespace(ceiling=10)])
    assert interest_of(5, one) == 0.5


def test_a_story_may_replace_the_wording_but_not_break_the_levels():
    custom = signal_catalogue({"signals": {"catalogue": {"1": ["glances over twice"], "2": ["hums"], "3": ["waits by the door"]}}})
    assert custom[1] == ("glances over twice",) and set(custom) == {1, 2, 3}
    assert signal_catalogue({}) == DEFAULT_CATALOGUE
    with pytest.raises(ValueError):
        signal_catalogue({"signals": {"catalogue": {"1": ["only one level"]}}})


# ---------------------------------------------------------------------------------------- through the turn


def _state(model, gender="M"):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=TERRACE,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender=gender, turns=5, outcome=None)


def _signal_lines(model):
    return [line for line in model.view.must_address if "Show it only as behaviour" in line]


def _run(model, state, turns=60):
    seen = []
    for _ in range(turns):
        begin_turn(state, "and then", 0)
        seen.append(_signal_lines(model))
    return seen


def test_through_a_turn_the_resident_who_likes_the_player_most_signals_and_never_more_than_one_at_once():
    model = make_model({"arisa": "kitchen", "minori": "kitchen"})
    model.standing.standings[("arisa", "player", "romance")] = Standing(value=40.0)
    model.standing.standings[("minori", "player", "romance")] = Standing(value=2.0)
    seen = _run(model, _state(model))
    assert all(len(lines) <= 1 for lines in seen)
    flat = [line for lines in seen for line in lines]
    assert flat and sum("Arisa" in line for line in flat) > sum("Minori" in line for line in flat)
    assert all("could be politeness or interest" in line for line in flat), "always framed as ambiguous"
    assert not any(word in line.lower() for line in flat for word in ("blush", "in love", "feelings for"))


def test_same_gender_residents_are_not_covered_by_a_romance_track_and_never_signal():
    model = make_model({"makoto": "kitchen"})                      # a man, with a man as the player
    model.standing.standings[("makoto", "player", "romance")] = Standing(value=60.0)
    assert not any(_run(model, _state(model, gender="M")))


def test_a_story_without_a_standing_track_has_no_signals_and_the_cooldown_survives_a_save():
    model = make_model({"arisa": "kitchen"})
    model.standing.standings[("arisa", "player", "romance")] = Standing(value=60.0)
    state = _state(model)
    _run(model, state, turns=30)
    assert model.last_signal_turn, "who last signalled is remembered"
    restored = type(model).from_dict(model.to_dict())
    assert restored.last_signal_turn == model.last_signal_turn
    bare = make_model({"arisa": "kitchen"})
    plain = _state(bare)
    plain.story_cfg = {}
    assert not any(_run(bare, plain, turns=20))
