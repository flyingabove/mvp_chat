"""BL-39 phase F: typed social acts, target-owned verdicts, explicit consent."""
from types import SimpleNamespace

import pytest

from backend.app.engine.extractors.turn_extractor import SocialActUpdate, TurnExtractor
from backend.app.engine.rules.endings import resolve_outcome
from backend.app.engine.world_model.romance import record_relationship_decisions
from backend.app.engine.world_model.social_acts import act_specs
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import answer_choice, begin_turn, end_turn, record_social_act

from tests.backend.app.engine.world_model.helpers import make_model

TRACKS = {"tracks": [{"id": "romance", "daily_gain_cap": 10, "repeat_decay": 0.5, "tiers": [
    {"id": "strangers", "floor": 0, "ceiling": 25},
    {"id": "interested", "floor": 25, "ceiling": 60},
    {"id": "dating", "floor": 60, "ceiling": 100}]}]}
ACTS = [{"kind": "confess", "track": "romance", "requires_tier": "interested", "cooldown_days": 1},
        {"kind": "ask_leave_together", "track": "romance", "requires_tier": "dating", "min_standing": 70,
         "requires_relationship": True},
        {"kind": "withdraw"}]
CFG = {"world_model": {"enabled": True}, "social_tracks": TRACKS, "social_acts": ACTS,
       "mode": {"romance_goal": {"enabled": True, "partner_gender": "opposite_player"}},
       "characters": [{"key": "ann", "gender": "F"}, {"key": "cat", "gender": "F"}, {"key": "ben", "gender": "M"}]}


def _state(model):
    return SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul", story_cfg=CFG,
                           characters={c: SimpleNamespace(name=c.title(), tells=[]) for c in model.characters},
                           cast_lifecycle=None, character_graph=None, gender="M", turns=5, outcome=None)


def _set(model, cid, value):
    model.standing.standings[(cid, "player", "romance")] = Standing(value=value)


def _turn(state, message, act=None, segments=()):
    if act is not None:
        record_social_act(state, act)
    begin_turn(state, message, 0)
    segments = [dict(s) for s in segments]
    end_turn(state, message, segments)
    return segments


def test_a_confession_below_the_tier_is_not_yet_and_the_prose_cannot_say_yes():
    model = make_model({"ann": "kitchen", "cat": "kitchen"})
    state = _state(model)
    _set(model, "ann", 10)
    record_social_act(state, SocialActUpdate("confess", "ann"))
    view = begin_turn(state, "Ann, I really like you.", 0)
    line = next(l for l in view.must_address if "confession" in l)
    assert "does not say yes yet" in line and "must not say yes" in line and "score" in line
    assert "ann" in view.plan.speakers
    segments = [{"kind": "dialogue", "speaker_id": "ann", "text": "Yes! I feel the same."}]
    end_turn(state, "Ann, I really like you.", segments)
    assert segments[0] == {"kind": "narration", "text": "Ann hesitates and does not say yes."}
    assert model.view.verdict_repairs == 1
    assert model.romance_relationship_partner == ""
    declined = [e for e in model.world.events if e.kind == "confess_declined"][-1]
    assert declined.visibility == "public" and "cat" in declined.participants, "witnessed, not secret"


def test_a_declined_act_has_a_cooldown_then_can_be_tried_again():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _set(model, "ann", 10)
    _turn(state, "I like you, Ann.", SocialActUpdate("confess", "ann"))
    _set(model, "ann", 30)
    verdict = record_social_act(state, SocialActUpdate("confess", "ann"))
    assert verdict.answer == "not_yet" and "time" in verdict.hint
    model.pending_verdicts = []
    model.world.minute += 24 * 60
    assert record_social_act(state, SocialActUpdate("confess", "ann")).answer == "accept"


def test_an_accepted_confession_creates_the_relationship_with_a_cause():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _set(model, "ann", 30)
    _turn(state, "Ann, will you date me?", SocialActUpdate("confess", "ann"),
          [{"kind": "dialogue", "speaker_id": "ann", "text": "Yes. I'd like that."}])
    assert model.romance_relationship_partner == "ann"
    rel = [e for e in model.world.events if e.kind == "romance_relationship"][-1]
    accepted = [e for e in model.world.events if e.kind == "confess_accepted"][-1]
    assert rel.cause_ids == (accepted.id,)


def test_a_closed_track_rejects_even_at_a_high_score():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    model.standing.standings[("ann", "player", "romance")] = Standing(value=50, closed_by="no_smokers")
    assert record_social_act(state, SocialActUpdate("confess", "ann")).answer == "reject"


def test_high_standing_alone_never_ends_the_game_leaving_needs_the_explicit_ask():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    _set(model, "ann", 90)
    _turn(state, "Nice day.")
    assert resolve_outcome(state, "") is None
    assert record_social_act(state, SocialActUpdate("ask_leave_together", "ann")).answer == "not_yet", \
        "not together yet"
    model.pending_verdicts = []
    model.romance_relationship_partner = "ann"
    _set(model, "ann", 65)
    assert record_social_act(state, SocialActUpdate("ask_leave_together", "ann")).answer == "not_yet"
    model.pending_verdicts = []
    _set(model, "ann", 80)
    _turn(state, "Ann, let's leave the house together.", SocialActUpdate("ask_leave_together", "ann"),
          [{"kind": "dialogue", "speaker_id": "ann", "text": "Let's go."}])
    assert model.romance_outcome == "" and resolve_outcome(state, "") is None, "a yes only opens the choice card"
    assert model.pending_choice["partner"] == "ann"
    cue = answer_choice(state, "__choice__:leave_together:leave_now")
    assert "leave the house together" in cue
    _turn(state, cue)
    assert model.romance_outcome == "mutual_departure" and model.pending_choice == {}
    assert resolve_outcome(state, "").ending_id == "left_together"


def test_withdrawing_is_the_players_own_decision_and_leaving_alone_is_gone():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    model.romance_relationship_partner = "ann"
    _turn(state, "I'm ending this, Ann.", SocialActUpdate("withdraw"))
    assert model.romance_relationship_partner == ""
    assert any(e.kind == "relationship_withdrawn" for e in model.world.events)
    assert record_social_act(state, SocialActUpdate("leave_alone")) is None, "BL-46: the player cannot end the run alone"
    assert model.romance_outcome == ""


def test_acts_need_an_eligible_present_target():
    model = make_model({"ann": "garden", "ben": "kitchen"})
    state = _state(model)
    assert record_social_act(state, SocialActUpdate("confess", "ann")) is None, "absent"
    assert record_social_act(state, SocialActUpdate("confess", "ben")) is None, "same gender under this story"
    assert record_social_act(state, SocialActUpdate("dance_off", "ben")) is None, "undeclared act"
    assert record_social_act(state, None) is None
    assert model.pending_verdicts == []


def test_typed_act_stories_turn_off_the_regex_adapters():
    model = make_model({"ann": "kitchen"})
    state = _state(model)
    begin_turn(state, "I want to date Ann.", 0)
    assert record_relationship_decisions(state, "I want to date Ann.",
                                         [{"kind": "dialogue", "speaker_id": "ann", "text": "I want to date you."}]) is False
    assert model.romance_relationship_partner == ""


def test_act_specs_validate_story_content():
    assert set(act_specs(CFG)) == {"confess", "ask_leave_together", "withdraw"}
    for bad in ([{"kind": "elope"}], [{"kind": "confess"}], [{"kind": "leave_alone"}],
                [{"kind": "withdraw"}, {"kind": "withdraw"}]):
        with pytest.raises(ValueError):
            act_specs({"social_acts": bad})


def test_extractor_parses_a_social_act_and_drops_unknown_targets():
    parse = TurnExtractor._parse_dict
    assert parse({"social_act": {"kind": "Confess", "target": "Ann"}}, set(), {"ann"}).social_act == \
        SocialActUpdate("confess", "ann")
    assert parse({"social_act": {"kind": "none"}}, set(), {"ann"}).social_act is None
    assert parse({"social_act": {"kind": "confess", "target": "zed"}}, set(), {"ann"}).social_act == \
        SocialActUpdate("confess", "")
