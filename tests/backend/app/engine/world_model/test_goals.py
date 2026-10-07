"""P-07: goals on the character - weighted, shifting by the holder's own view, visible on the scene card."""
from types import SimpleNamespace

import pytest

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.rules.personality import Personality, personalities
from backend.app.engine.world_model.goals import (
    GOAL_KINDS, Goal, GoalBook, active_goal, agenda_scale, card_note, parse_goals)
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.person import Cast
from tests.backend.app.engine.world_model.helpers import make_model

TRUST_SHIFT = {"when": {"kind": "feeling", "dimension": "suspicion", "op": ">=", "value": 0.5}, "delta": 0.3,
               "reason": "she has stopped trusting him"}


def _cfg(goals, extra_char=None):
    chars = [{"key": "ann"}, {"key": "ben"}] + ([extra_char] if extra_char else [])
    return {"characters": chars, "personalities": {"ann": {"goals": goals}}}


def _graph(**state):
    return CharacterGraph.from_dict({"edges": [{"from_id": "ann", "to_id": "ben", "state": state}]})


# ---------------------------------------------------------------- loading and validation
def test_goals_load_with_weights_targets_and_shifts():
    goals = personalities(_cfg([
        {"id": "g1", "kind": "love", "target": "ben", "weight": 0.8, "text": "win Ben over", "shifts": [TRUST_SHIFT]},
        {"id": "g2", "kind": "career", "weight": 0.6}]))["ann"].goals
    assert [g.id for g in goals] == ["g1", "g2"] and goals[0].target == "ben" and goals[0].weight == 0.8
    assert goals[0].shifts[0].delta == 0.3 and goals[0].shifts[0].id == "g1#0"
    assert personalities(_cfg([]))["ben"].goals == () and Personality().goals == ()


@pytest.mark.parametrize("bad, why", [
    ([{"id": "g", "kind": "world_peace", "weight": 0.5}], "unknown goal kind"),
    ([{"id": "g", "kind": "love", "weight": 1.2}], "within 0..1"),
    ([{"id": "g", "kind": "love", "weight": -0.1}], "within 0..1"),
    ([{"id": "g", "kind": "love"}], "needs a numeric weight"),
    ([{"kind": "love", "weight": 0.5}], "needs an id"),
    ([{"id": "g", "kind": "love", "weight": 0.5}, {"id": "g", "kind": "career", "weight": 0.5}], "duplicate goal id"),
    ([{"id": "g", "kind": "love", "weight": 0.5, "target": "nobody"}], "unknown character"),
    ([{"id": "g", "kind": "love", "weight": 0.5, "shifts": [{"when": {"kind": "vibes"}, "delta": 0.1}]}], "unknown condition"),
    ([{"id": "g", "kind": "love", "weight": 0.5, "shifts": [{"when": TRUST_SHIFT["when"], "delta": 2}]}], "within -1..1"),
    ("love", "must be a list"),
])
def test_a_bad_goal_fails_loudly_at_story_load(bad, why):
    with pytest.raises(ValueError, match=why):
        personalities(_cfg(bad))


def test_a_story_may_add_its_own_goal_kind_but_not_use_an_undeclared_one():
    cfg = _cfg([{"id": "g", "kind": "tradition", "weight": 0.5}])
    with pytest.raises(ValueError, match="unknown goal kind"):
        personalities(cfg)
    cfg["goal_kinds"] = ["tradition"]
    assert personalities(cfg)["ann"].goals[0].kind == "tradition"
    assert "chaos" in GOAL_KINDS and "love" in GOAL_KINDS


# ---------------------------------------------------------------- shifts: holder's own view, once, with history
def _people(goals):
    return personalities(_cfg(goals))


def test_a_shift_fires_from_the_holders_own_view_only():
    people = _people([{"id": "g1", "kind": "love", "target": "ben", "weight": 0.5, "shifts": [TRUST_SHIFT]}])
    book, model = GoalBook(), make_model({"ann": "kitchen", "ben": "kitchen"})
    # Ben's feeling about Ann is irrelevant to Ann's goal: only Ann's own suspicion of Ben counts.
    other_way = CharacterGraph.from_dict({"edges": [{"from_id": "ben", "to_id": "ann", "state": {"suspicion": 0.9}}]})
    assert book.apply_shifts(model, people, other_way, minute=10) == []
    assert book.weight("ann", people["ann"].goals[0]) == 0.5
    changed = book.apply_shifts(model, people, _graph(suspicion=0.7), minute=20)
    assert [(c.owner, c.goal_id, c.old, c.new) for c in changed] == [("ann", "g1", 0.5, 0.8)]


def test_a_shift_fires_once_and_keeps_provenanced_history():
    people = _people([{"id": "g1", "kind": "love", "target": "ben", "weight": 0.5, "shifts": [TRUST_SHIFT]}])
    book, model, graph = GoalBook(), make_model({"ann": "kitchen", "ben": "kitchen"}), _graph(suspicion=0.7)
    book.apply_shifts(model, people, graph, minute=20)
    assert book.apply_shifts(model, people, graph, minute=30) == []          # not applied twice
    assert book.weight("ann", people["ann"].goals[0]) == pytest.approx(0.8)
    history = book.trait("ann", "g1").history
    assert [h.content for h in history] == ["0.5", "0.8"]
    assert history[1].provenance == "she has stopped trusting him" and history[1].timestamp_minute == 20


def test_weights_stay_within_zero_and_one():
    up = {"when": TRUST_SHIFT["when"], "delta": 0.9, "reason": "x"}
    down = {"when": TRUST_SHIFT["when"], "delta": -0.9, "reason": "y"}
    people = _people([{"id": "hi", "kind": "love", "target": "ben", "weight": 0.5, "shifts": [up]},
                      {"id": "lo", "kind": "career", "target": "ben", "weight": 0.5, "shifts": [down]}])
    book, model = GoalBook(), make_model({"ann": "kitchen"})
    book.apply_shifts(model, people, _graph(suspicion=0.9), minute=1)
    goals = {g.id: g for g in people["ann"].goals}
    assert book.weight("ann", goals["hi"]) == 1.0 and book.weight("ann", goals["lo"]) == 0.0


def test_a_goal_with_no_shift_never_creates_state():
    people = _people([{"id": "g1", "kind": "career", "weight": 0.6}])
    book = GoalBook()
    assert book.apply_shifts(make_model({"ann": "kitchen"}), people, _graph(), minute=5) == [] and book.to_dict() == {}


def test_the_book_round_trips_and_an_old_save_without_goals_loads():
    people = _people([{"id": "g1", "kind": "love", "target": "ben", "weight": 0.5, "shifts": [TRUST_SHIFT]}])
    book, model = GoalBook(), make_model({"ann": "kitchen", "ben": "kitchen"})
    book.apply_shifts(model, people, _graph(suspicion=0.7), minute=20)
    again = GoalBook.from_dict(book.to_dict())
    assert again.weight("ann", people["ann"].goals[0]) == pytest.approx(0.8) and again.to_dict() == book.to_dict()
    assert again.apply_shifts(model, people, _graph(suspicion=0.7), minute=40) == []     # the latch survives a save
    assert GoalBook.from_dict(None).to_dict() == {} and GoalBook.from_dict({}).to_dict() == {}
    legacy = make_model({"ann": "kitchen"}).to_dict()
    legacy.pop("goals", None)
    assert WorldModel.from_dict(legacy).goals.to_dict() == {}
    saved = model.to_dict()
    model.goals = book
    assert WorldModel.from_dict(model.to_dict()).goals.to_dict() == book.to_dict() and "goals" in model.to_dict()
    assert "goals" in saved


# ---------------------------------------------------------------- the active goal, the card, the person
def test_the_active_goal_is_the_heaviest_with_a_stable_tie_break():
    people = _people([{"id": "b", "kind": "career", "weight": 0.6}, {"id": "a", "kind": "love", "weight": 0.6},
                      {"id": "c", "kind": "status", "weight": 0.2}])
    assert active_goal(GoalBook(), "ann", people["ann"]).id == "a"            # tie on weight: lowest id
    assert active_goal(GoalBook(), "ben", people["ben"]) is None
    zero = _people([{"id": "z", "kind": "love", "weight": 0.0}])
    assert active_goal(GoalBook(), "ann", zero["ann"]) is None                 # a dead goal is not an aim


def test_the_card_shows_the_goal_privately_and_names_its_target():
    names = {"ann": "Ann", "ben": "Ben"}
    love = Goal("g", "love", "ben", 0.8, ())
    assert card_note(love, 0.8, names) == "private aim: love, toward Ben (strong); never announce it"
    assert card_note(Goal("g", "career", "", 0.5, (), "win the show"), 0.5, names) == \
        "private aim: win the show; never announce it"
    assert "(faint)" in card_note(Goal("g", "chaos", "", 0.2, ()), 0.2, names) and "chaos" in card_note(
        Goal("g", "chaos", "", 0.2, ()), 0.2, names)


def test_a_person_exposes_their_goals_with_live_weights():
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    cfg = _cfg([{"id": "g1", "kind": "love", "target": "ben", "weight": 0.5, "shifts": [TRUST_SHIFT]}])
    state = SimpleNamespace(world_model=model, character_graph=_graph(suspicion=0.7), characters={}, story_cfg=cfg)
    cast = Cast(state)
    assert [(g.id, g.weight) for g in cast.get("ann").goals()] == [("g1", 0.5)]
    model.goals.apply_shifts(model, personalities(cfg), state.character_graph, minute=3)
    assert cast.get("ann").goals()[0].weight == pytest.approx(0.8) and cast.get("ann").active_goal().id == "g1"
    assert cast.get("ben").goals() == [] and cast.get("ben").active_goal() is None and cast.player().goals() == []


# ---------------------------------------------------------------- behaviour: agenda priority
def test_goals_scale_romantic_priority_and_a_sparse_character_is_exactly_neutral():
    people = _people([{"id": "l", "kind": "love", "weight": 0.9}, {"id": "c", "kind": "career", "weight": 0.3}])
    career = _people([{"id": "c", "kind": "career", "weight": 0.9}])
    book = GoalBook()
    assert agenda_scale(book, "ann", people["ann"]) == pytest.approx(1.3)
    assert agenda_scale(book, "ann", career["ann"]) == pytest.approx(0.55)
    assert agenda_scale(book, "ben", people["ben"]) == 1.0                    # no goals: unchanged, bit for bit
    only_love = _people([{"id": "l", "kind": "love", "weight": 1.0}])
    assert agenda_scale(book, "ann", only_love["ann"]) == pytest.approx(1.5)


def test_refresh_agendas_applies_the_goal_scale_and_defaults_to_none():
    from backend.app.engine.rules.tracks import social_rules
    from backend.app.engine.world_model.standing import Standing
    from backend.app.engine.world_model.agenda import SocialContext
    from tests.backend.app.engine.world_model.test_agenda import TRACKS, refresh_all

    def run(**kwargs):
        model = make_model({"ann": "k", "ben": "k"})
        model.standing.bind(social_rules({"social_tracks": TRACKS}).tracks)
        model.standing.standings[("ann", "ben", "romance")] = Standing(value=40)
        any_gender = {**TRACKS, "appraisal": {**TRACKS["appraisal"], "eligible": "any"}}
        refresh_all(model, SocialContext(social_rules({"social_tracks": any_gender}), {}), 0, **kwargs)
        return [i.priority for i in model.agendas["ann"]]
    assert run() == [0.4] and run(scale=lambda cid: 1.0) == [0.4]
    assert run(scale=lambda cid: 0.5) == [0.2] and run(scale=lambda cid: 1.5) == [pytest.approx(0.6)]


# ---------------------------------------------------------------- through the real turn pipeline
def _turn_state(model, cfg, graph=None):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=graph, gender="M", turns=5, outcome=None)


def _card(model, cid):
    return next(c for c in model.view.cards if c.startswith(model.characters[cid].name))


def test_the_scene_card_carries_the_active_goal_and_a_sparse_person_has_none():
    from backend.app.engine.world_model.turn import begin_turn
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    cfg = _cfg([{"id": "g1", "kind": "love", "target": "ben", "weight": 0.8}, {"id": "g2", "kind": "career", "weight": 0.4}])
    begin_turn(_turn_state(model, cfg), "hello", 0)
    assert "private aim: love, toward Ben (strong); never announce it" in _card(model, "ann")
    assert "private aim" not in _card(model, "ben")


def test_a_shift_during_a_turn_changes_which_goal_the_card_shows():
    from backend.app.engine.world_model.turn import begin_turn
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    cfg = _cfg([{"id": "love", "kind": "love", "target": "ben", "weight": 0.7},
                {"id": "pride", "kind": "revenge", "target": "ben", "weight": 0.4,
                 "shifts": [{"when": TRUST_SHIFT["when"], "delta": 0.5, "reason": "he humiliated her"}]}])
    graph = _graph()
    state = _turn_state(model, cfg, graph)
    begin_turn(state, "hello", 0)
    assert "love, toward Ben" in _card(model, "ann")
    graph.update_edge("ann", "ben", suspicion_delta=0.8)
    begin_turn(state, "again", 0)
    assert "revenge, toward Ben (strong)" in _card(model, "ann")
    assert [h.provenance for h in model.goals.trait("ann", "pride").history][-1] == "he humiliated her"


def test_a_story_with_goals_configured_loads_in_the_real_registry_and_terrace_is_valid():
    from backend.app.engine.story_loader import build_story_registry
    for story_id, story in build_story_registry().items():
        personalities(story["raw"])                                   # raises on any bad goal, for every shipped story
