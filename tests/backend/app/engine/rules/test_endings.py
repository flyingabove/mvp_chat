"""BL-39 phase A: typed endings evaluated from committed decisions."""
from types import SimpleNamespace

import pytest

from backend.app.engine.rules.endings import (
    Ending, EndingFacts, Outcome, endings_for, evaluate, goal_payload, resolve_outcome,
)
from backend.app.engine.story_loader import build_story_registry, get_active_story_ids

ROMANCE = {"mode": {"romance_goal": {"enabled": True}}, "goal": {"win_text_rule": "Leave together."}}


def _state(cfg, outcome="", partner="", reply_outcome=None):
    model = SimpleNamespace(romance_outcome=outcome, romance_relationship_partner=partner)
    return SimpleNamespace(story_cfg=cfg, world_model=model, outcome=reply_outcome, turns=14, minute=900,
                           characters={"mako": SimpleNamespace(name="Mako")})


def test_mutual_departure_is_a_win_naming_the_partner():
    outcome = resolve_outcome(_state(ROMANCE, "mutual_departure", "mako"), "They walk out together.")
    assert (outcome.ending_id, outcome.kind, outcome.partner_id) == ("left_together", "win", "mako")
    assert outcome.summary == "You and Mako both chose to leave the house together."
    assert outcome.payload() == {"id": "left_together", "kind": "win", "label": "You won",
                                 "title": "You left together", "summary": outcome.summary,
                                 "turns": 14, "ends_run": True}


def test_there_is_no_solo_exit_ending_any_more():
    """BL-46: the player cannot end the run by leaving alone; only the director's clock ends a losing run."""
    assert resolve_outcome(_state(ROMANCE, "solo_departure"), "You pack your bag.") is None


def test_no_committed_decision_means_no_ending_even_with_winning_words():
    assert resolve_outcome(_state(ROMANCE, "", "mako"), "We should leave together, you win!") is None


def test_an_ending_fires_only_once():
    state = _state(ROMANCE, "mutual_departure", "mako", reply_outcome={"ending_id": "left_together"})
    assert resolve_outcome(state, "") is None


def test_legacy_mystery_confession_is_an_explicit_regex_condition():
    cfg = {"win_detection": {"regex": [r"(?i)\bi ordered .* to kill\b"]}}
    endings = endings_for(cfg)
    assert [(e.id, e.kind, e.condition["kind"]) for e in endings] == [("confession", "win", "legacy_reply_regex")]
    assert evaluate(endings, EndingFacts(reply="Fine. I ordered him to kill her.")).id == "confession"
    assert evaluate(endings, EndingFacts(reply="I did not kill anyone.")) is None


def test_declared_endings_keep_order_and_counters_work():
    cfg = {"endings": [
        {"id": "cut", "kind": "loss", "title": "Cut", "summary": "",
         "when": {"kind": "counter_at_least", "counter": "couples_left", "value": 3}},
        {"id": "left_together", "kind": "win", "title": "Together", "summary": "",
         "when": {"kind": "world_outcome", "equals": "mutual_departure"}},
    ]}
    endings = endings_for(cfg)
    facts = EndingFacts(world_outcome="mutual_departure", counters={"couples_left": 3})
    assert evaluate(endings, facts).id == "cut", "declared order decides a tie"
    assert evaluate(endings, EndingFacts(counters={"couples_left": 2})) is None


@pytest.mark.parametrize("bad", [
    {"id": "x", "kind": "victory", "when": {"kind": "world_outcome", "equals": "a"}},
    {"id": "", "kind": "win", "when": {"kind": "world_outcome", "equals": "a"}},
    {"id": "x", "kind": "win", "when": {"kind": "score_above", "value": 90}},
    {"id": "x", "kind": "win", "when": {"kind": "legacy_reply_regex", "patterns": ["("]}},
    {"id": "x", "kind": "win", "when": {"kind": "counter_at_least", "counter": "c", "value": 0}},
])
def test_invalid_declared_endings_fail_loudly(bad):
    with pytest.raises(Exception):
        endings_for({"endings": [bad]})


def test_duplicate_ending_ids_are_rejected():
    item = {"id": "x", "kind": "win", "when": {"kind": "world_outcome", "equals": "a"}}
    with pytest.raises(ValueError):
        endings_for({"endings": [item, item]})


def test_outcome_round_trips():
    outcome = Outcome("left_alone", "neutral", "You left alone", "Bye.", 3, 60, True, "")
    assert Outcome.from_dict(outcome.to_dict()) == outcome


def test_goal_card_shows_real_progress_only():
    assert goal_payload(_state(ROMANCE)) == {"text": "Leave together.", "status": "No mutual relationship yet."}
    card = goal_payload(_state(ROMANCE, partner="mako"))
    assert card["status"] == "You and Mako are together. Now you both need to choose to leave."
    assert goal_payload(_state({})) is None


@pytest.mark.parametrize("story_id", get_active_story_ids())
def test_every_active_story_has_valid_endings(story_id):
    endings = endings_for(build_story_registry()[story_id]["raw"])
    assert endings and any(e.kind == "win" for e in endings)
