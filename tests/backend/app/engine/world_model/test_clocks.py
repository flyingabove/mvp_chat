"""BL-39 phase H: the director's clock warns at two other couples and cuts at three."""
from types import SimpleNamespace

import pytest

from backend.app.engine.rules.clocks import clocks_for, due_beats
from backend.app.engine.rules.endings import endings_for, resolve_outcome
from backend.app.engine.story_loader import build_story_registry
from backend.app.engine.world_model.turn import begin_turn

from tests.backend.app.engine.world_model.helpers import make_model

TERRACE = build_story_registry()["six_strangers"]["raw"]


def _state(model, cfg=TERRACE):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=cfg,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=9, outcome=None)


def _director_lines(model):
    return [line for line in model.view.must_address if "director" in line]


def test_the_director_warns_once_at_two_and_cuts_once_at_three():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    model.counters["couples_left"] = 1
    begin_turn(state, "Hi.", 0)
    assert _director_lines(model) == []
    model.counters["couples_left"] = 2
    begin_turn(state, "Hi.", 0)
    assert len(_director_lines(model)) == 1 and "one more" in _director_lines(model)[0]
    begin_turn(state, "Hi.", 0)
    assert _director_lines(model) == [], "the warning is delivered once"
    assert resolve_outcome(state, "") is None

    model.counters["couples_left"] = 3
    begin_turn(state, "Hi.", 0)
    assert len(_director_lines(model)) == 1 and "cut from the show" in _director_lines(model)[0]
    outcome = resolve_outcome(state, "")
    assert (outcome.ending_id, outcome.kind) == ("cut_by_director", "loss")


def test_a_player_win_takes_precedence_over_the_cut_in_the_same_turn():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    model.counters["couples_left"] = 3
    model.romance_outcome, model.romance_relationship_partner = "mutual_departure", "ann"
    assert resolve_outcome(state, "").ending_id == "left_together"


def test_jumping_past_the_warning_still_delivers_only_the_trigger():
    clocks = clocks_for(TERRACE)
    assert [k for k, _ in due_beats(clocks, {"couples_left": 3})] == ["clock:director_patience:trigger"]


def test_the_player_couples_departure_does_not_count():
    """Only other couples' `couple_departure` increments couples_left (phase G);
    the player's own leaving is a romance_ending, never counted."""
    model = make_model({"ann": "kitchen"})
    from backend.app.engine.world_model.romance import commit_mutual_departure
    commit_mutual_departure(_state(model), "ann")
    assert model.counters.get("couples_left", 0) == 0


@pytest.mark.parametrize("bad", [
    [{"id": "", "counter": "c", "trigger_at": 3}],
    [{"id": "x", "counter": "c", "trigger_at": 0}],
    [{"id": "x", "counter": "c", "warn_at": 3, "trigger_at": 3}],
    [{"id": "x", "counter": "c", "trigger_at": 2}, {"id": "x", "counter": "c", "trigger_at": 2}],
])
def test_invalid_clocks_fail_loudly(bad):
    with pytest.raises(ValueError):
        clocks_for({"clocks": bad})


def test_terrace_declares_the_director_clock_and_its_two_endings():
    assert [(c.warn_at, c.trigger_at, c.counter) for c in clocks_for(TERRACE)] == [(2, 3, "couples_left")]
    assert [(e.id, e.kind) for e in endings_for(TERRACE)] == [
        ("left_together", "win"), ("cut_by_director", "loss")]


def test_stories_without_clocks_get_no_beats():
    assert clocks_for({}) == [] and due_beats([], {"couples_left": 9}) == []
