"""BL-39 hybrid NPC decisions: rules vs Jev judgment, bounded by the rules.

The switch (rules | jev | compare) never lets Jev loosen consent: hard blocks
stay with the rules, and Jev cannot accept below the required tier. If Jev is
unavailable the rules verdict applies and the reason is recorded.
"""
from types import SimpleNamespace

import pytest

from backend.app.engine.world_model.npc_decision import (
    JevJudgment, MODES, decision_mode, jev_decision, merge, target_view,
)
from backend.app.engine.world_model.social_acts import (
    SocialAct, act_specs, assess, decide,
)
from backend.app.engine.world_model.persona import SelfClaim
from backend.app.engine.world_model.standing import Standing

from tests.backend.app.engine.world_model.helpers import make_model

TRACKS = {"tracks": [{"id": "romance", "daily_gain_cap": 10, "repeat_decay": 0.5, "tiers": [
    {"id": "strangers", "floor": 0, "ceiling": 25},
    {"id": "interested", "floor": 25, "ceiling": 60},
    {"id": "dating", "floor": 60, "ceiling": 100}]}]}
CFG = {"social_tracks": TRACKS, "social_acts": [
    {"kind": "confess", "track": "romance", "requires_tier": "interested", "cooldown_days": 1},
    {"kind": "ask_leave_together", "track": "romance", "requires_tier": "dating", "min_standing": 70,
     "requires_relationship": True},
    {"kind": "withdraw"}],
    "characters": [{"key": "ann", "gender": "F"}]}
SPECS = act_specs(CFG)


def _model(value, closed_by="", partner=""):
    model = make_model({"ann": "kitchen"})
    from backend.app.engine.rules.tracks import social_rules
    model.standing.bind(social_rules(CFG).tracks)
    model.standing.standings[("ann", "player", "romance")] = Standing(value=value, closed_by=closed_by)
    model.romance_relationship_partner = partner
    return model


def _j(choice, confidence=0.9, reason=""):
    return JevJudgment(choice=choice, confidence=confidence, reason=reason)


def test_assessment_separates_hard_blocks_from_room_for_judgment():
    confess = SPECS["confess"]
    act = SocialAct("confess", "ann")
    ready = assess(_model(40), confess, act, {"ann"})
    assert (ready.verdict.answer, ready.hard, ready.can_accept) == ("accept", False, True)
    early = assess(_model(10), confess, act, {"ann"})
    assert (early.verdict.answer, early.hard, early.can_accept) == ("not_yet", False, False)
    closed = assess(_model(40, closed_by="no_smokers"), confess, act, {"ann"})
    assert (closed.verdict.answer, closed.hard) == ("reject", True)
    ask = assess(_model(90), SPECS["ask_leave_together"], SocialAct("ask_leave_together", "ann"), {"ann"})
    assert (ask.verdict.answer, ask.hard) == ("not_yet", True), "not together yet is a hard rule"
    assert assess(_model(40), confess, act, set()) is None
    assert decide(_model(40), confess, act, {"ann"}).answer == "accept", "decide() is unchanged"


def test_cooldown_is_a_hard_block():
    model = _model(40)
    model.act_cooldowns["confess:ann"] = model.world.day_index(model.world.minute)
    result = assess(model, SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    assert (result.verdict.answer, result.hard) == ("not_yet", True)


def test_rules_mode_never_consults_jev():
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "rules", _j("reject"))
    assert verdict.answer == "accept" and record.jev is None and record.final == "accept"


def test_jev_mode_may_be_stricter_than_the_rules():
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "jev", _j("not_yet"))
    assert verdict.answer == "not_yet" and verdict.hint and record.rules == "accept" and record.jev == "not_yet"
    verdict, record = merge(assessment, "jev", _j("reject"))
    assert verdict.answer == "reject" and "clear" in verdict.hint


def test_jev_mode_agrees_and_can_accept_when_the_rules_allow_it():
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "jev", _j("accept"))
    assert verdict.answer == "accept" and record.final == "accept" and not record.clamped


def test_jev_can_never_accept_below_the_required_tier():
    assessment = assess(_model(10), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "jev", _j("accept", confidence=0.99))
    assert verdict.answer == "not_yet" and record.clamped and record.jev == "accept"
    assert "tier" in record.note


def test_hard_blocks_are_not_overridable_by_jev():
    closed = assess(_model(40, closed_by="x"), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(closed, "jev", _j("accept"))
    assert verdict.answer == "reject" and record.note == "hard rule"
    unpartnered = assess(_model(90), SPECS["ask_leave_together"], SocialAct("ask_leave_together", "ann"), {"ann"})
    assert merge(unpartnered, "jev", _j("accept"))[0].answer == "not_yet"


@pytest.mark.parametrize("judgment,expected_note", [
    (None, "jev not consulted"),
    (JevJudgment(None, None, "timeout"), "jev unavailable: timeout"),
    (JevJudgment("accept", 0.2, "below_threshold"), "jev unavailable: below_threshold"),
])
def test_when_jev_is_unavailable_the_rules_verdict_applies(judgment, expected_note):
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "jev", judgment)
    assert verdict.answer == "accept" and record.final == "accept" and record.note == expected_note


def test_compare_mode_applies_the_rules_verdict_and_records_both():
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "compare", _j("reject"))
    assert verdict.answer == "accept", "compare never changes gameplay"
    assert (record.mode, record.rules, record.jev, record.final) == ("compare", "accept", "reject", "accept")
    assert record.agrees is False
    assert merge(assessment, "compare", _j("accept"))[1].agrees is True


def test_target_view_is_the_targets_own_first_person_view():
    model = _model(40)
    model.persona.claim(SelfClaim("player", "height", "178cm", ("ann",), 0, 1))
    model.persona.claim(SelfClaim("player", "smokes", "no", ("ann",), 0, 1))
    model.persona.claim(SelfClaim("player", "smokes", "yes", ("ann",), 5, 2))
    model.standing.standings[("cat", "player", "romance")] = Standing(value=99)
    model.standing.standings[("ann", "ben", "romance")] = Standing(value=77)
    model.memories.add("cat", "secret about cat", "authored", 0, private=True)
    text = target_view(model, SPECS["confess"], SocialAct("confess", "ann"), CFG, {"ann": "Ann"}, graph=None)
    assert "You are Ann" in text and "romantic feelings" in text
    assert "height: 178cm" in text and "smokes: unsure" in text, "disputed claims read as unsure"
    assert "99" not in text and "77" not in text and "secret about cat" not in text
    assert "ben" not in text.lower()


def test_target_view_reports_recent_behavior_toward_the_target_only():
    from backend.app.engine.world_model.standing import Impression
    model = _model(0)
    model.standing.bind({"romance": SimpleNamespace()})   # journal only; not applying
    for n, (owner, tag, delta) in enumerate([("ann", "helpful", 3.0), ("ann", "rude", -3.0), ("cat", "warm", 3.0)]):
        model.standing.journal.append(SimpleNamespace(
            owner=owner, target="player", track="romance", tag=tag, applied=delta, kind="gain" if delta > 0 else "loss",
            day=0, sequence=n))
    text = target_view(model, SPECS["confess"], SocialAct("confess", "ann"), CFG, {"ann": "Ann"}, graph=None)
    assert "helpful" in text and "rude" in text and "warm" not in text.split("What you noticed")[1]


def test_target_view_states_mbti_type_and_gloss_when_authored():
    cfg = {**CFG, "personalities": {"ann": {"type": "entp"}}}
    text = target_view(_model(40), SPECS["confess"], SocialAct("confess", "ann"), cfg, {"ann": "Ann"}, graph=None)
    assert "Your personality type is ENTP: you are" in text


def test_target_view_omits_mbti_line_when_not_authored():
    text = target_view(_model(40), SPECS["confess"], SocialAct("confess", "ann"), CFG, {"ann": "Ann"}, graph=None)
    assert "personality type" not in text


def test_the_jev_question_is_a_bounded_degradable_choice():
    decision = jev_decision("ann", SocialAct("confess", "ann"))
    assert decision.kind == "choice" and decision.allowed == frozenset({"accept", "not_yet", "reject"})
    assert decision.criticality.value == "degradable" and decision.min_confidence
    assert set(decision.criteria) == {"accept", "not_yet", "reject"} and decision.id == "npc_verdict_ann"


@pytest.mark.parametrize("raw,expected", [("rules", "rules"), ("JEV", "jev"), (" compare ", "compare"),
                                          ("", "rules"), ("banana", "rules"), (None, "rules")])
def test_mode_parsing_fails_safe_to_rules(raw, expected):
    assert decision_mode(raw) == expected and set(MODES) == {"rules", "jev", "compare"}


def test_target_view_states_whether_a_yes_is_possible_in_plain_words():
    model = _model(40)
    act = SocialAct("confess", "ann")
    ready = target_view(model, SPECS["confess"], act, CFG, {"ann": "Ann"}, ready=True)
    early = target_view(model, SPECS["confess"], act, CFG, {"ann": "Ann"}, ready=False)
    unknown = target_view(model, SPECS["confess"], act, CFG, {"ann": "Ann"})
    assert "could say yes to this" in ready and "still early" in early
    assert "could say yes" not in unknown and "still early" not in unknown


def test_records_carry_jev_odds_and_survive_a_save():
    from backend.app.engine.world_model.model import WorldModel
    from backend.app.engine.world_model.npc_decision import DecisionRecord, LOG_LIMIT, append_record

    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    judgment = JevJudgment("not_yet", 0.8, "", (("accept", 0.31), ("not_yet", 0.6), ("reject", 0.09)))
    _, record = merge(assessment, "compare", judgment, turn=4)
    assert record.p_accept == 0.31 and record.turn == 4
    assert DecisionRecord.from_dict(record.to_dict()) == record

    model = make_model({"ann": "kitchen"})
    for turn in range(LOG_LIMIT + 5):
        append_record(model, DecisionRecord(turn, "compare", "confess", "ann", "accept", "reject", "accept"))
    assert len(model.decision_log) == LOG_LIMIT and model.decision_log[0]["turn"] == 5
    restored = WorldModel.from_dict(model.to_dict())
    assert restored.decision_log == model.decision_log


def test_compare_mode_keeps_the_reason_when_jev_could_not_answer():
    assessment = assess(_model(40), SPECS["confess"], SocialAct("confess", "ann"), {"ann"})
    verdict, record = merge(assessment, "compare", JevJudgment(None, None, "http_error"))
    assert verdict.answer == "accept" and record.jev is None and record.agrees is None
    assert record.note == "compare: rules applied; jev unavailable: http_error"
    assert merge(assessment, "compare", None)[1].note == "compare: rules applied; jev not consulted"
