"""BL-39 phase C: standing tracks, requirements and the ordered effect journal."""
import pytest

from backend.app.engine.rules.conditions import (
    All, Any_, Not, Viewpoint, parse,
)
from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model import standing as standing_mod
from backend.app.engine.world_model.agreements import decide, propose
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.standards import (
    apply_impression, enforce_dealbreakers, failing_requirements, viewpoint,
)
from backend.app.engine.world_model.standing import Impression

from tests.backend.app.engine.world_model.helpers import make_model

TRACKS = {
    "tracks": [{
        "id": "romance", "daily_gain_cap": 10, "repeat_decay": 0.5, "neglect_decay_per_day": 2,
        "tiers": [
            {"id": "stranger", "floor": 0, "ceiling": 20},
            {"id": "friend", "floor": 20, "ceiling": 50,
             "gate": {"kind": "agreement_count", "activity": "coffee", "status": "completed", "min": 1}},
            {"id": "dating", "floor": 50, "ceiling": 100},
        ],
    }],
    "requirements": {
        "default": [],
        "ann": [
            {"id": "no_smokers", "track": "romance", "tier": "stranger", "on_fail": "dealbreaker",
             "condition": {"kind": "not", "condition": {"kind": "knows", "proposition": "the player smokes"}}},
            {"id": "trust_first", "track": "romance", "tier": "dating", "on_fail": "cap",
             "condition": {"kind": "feeling", "dimension": "trust", "op": ">=", "value": 0.5}},
        ],
    },
}


class Graph:
    def __init__(self, trust=0.0):
        self.edge = type("E", (), {"state": type("S", (), {"trust": trust, "affection": 0.0, "suspicion": 0.0,
                                                            "fear": 0.0, "jealousy": 0.0})()})()

    def get_edge(self, a, b):
        return self.edge if (a, b) == ("ann", "player") else None


def _setup():
    model = make_model({"ann": "kitchen"})
    return model, social_rules({"social_tracks": TRACKS})


def _imp(n, delta, tag="kind_word", day=0, owner="ann"):
    return Impression(f"e{n}", owner, "player", "romance", tag, delta, f"ev{n}", n, day)


def test_same_tag_same_day_has_diminishing_returns_and_daily_cap():
    model, rules = _setup()
    applied = [apply_impression(model, rules, _imp(i, 6)).applied for i in range(3)]
    assert applied == [6, 3, 1], "6, then 6*0.5=3, then capped by the 10/day allowance"
    assert model.standing.get("ann", "player", "romance").value == 10
    assert apply_impression(model, rules, _imp(9, 6, day=1)).applied == 6, "a new day has a fresh allowance"


def test_surplus_past_a_closed_gate_is_discarded_not_banked():
    model, rules = _setup()
    for day in range(3):
        apply_impression(model, rules, _imp(day, 10, tag=f"t{day}", day=day))
    assert model.standing.get("ann", "player", "romance").value == 20, "friend tier gated by a completed coffee"
    agreement = propose(model.agreements, "ann", "player", "coffee", 60, 0)
    decide(model.agreements, agreement.id, "player", "accepted", 0)
    agreement.status = "completed"
    effect = apply_impression(model, rules, _imp(7, 10, tag="t7", day=5))
    assert effect.applied == 10 and model.standing.tier("ann", "player", "romance").id == "friend"


def test_cap_requirement_uses_the_holders_feelings_and_unknown_stays_closed():
    model, rules = _setup()
    apply_impression(model, rules, Impression("seed", "ann", "player", "romance", "x", 0, "", 0, 0))
    st = model.standing.get("ann", "player", "romance")
    st.value = 50.0  # top of friend tier; dating needs trust >= 0.5
    assert apply_impression(model, rules, _imp(1, 5, day=9), graph=Graph(trust=0.2)).applied == 0
    assert apply_impression(model, rules, _imp(2, 5, day=9), graph=None).applied == 0, "no graph = unknown = closed"
    assert apply_impression(model, rules, _imp(3, 5, tag="other", day=9), graph=Graph(trust=0.6)).applied == 5


def test_dealbreaker_closes_only_when_established_false_and_losses_still_apply():
    model, rules = _setup()
    apply_impression(model, rules, _imp(1, 8))
    assert enforce_dealbreakers(model, rules, "ann", "player", "ev0") == [], "unknown smoking: stays open"
    from backend.app.engine.world_model.epistemics import assert_claim
    assert_claim(model.epistemics, "ann", "the player smokes", 0)
    closed = enforce_dealbreakers(model, rules, "ann", "player", "ev_smoke")
    assert [e.closed_by for e in closed] == ["no_smokers"]
    assert enforce_dealbreakers(model, rules, "ann", "player", "ev_smoke") == [], "closing is once"
    assert apply_impression(model, rules, _imp(2, 5, tag="gift", day=1)).applied == 0
    assert apply_impression(model, rules, _imp(3, -3, tag="rude", day=1)).applied == -3
    assert model.standing.get("ann", "player", "romance").value == 5


def test_effects_are_idempotent_and_replay_matches_across_save_and_checkpoint(monkeypatch):
    monkeypatch.setattr(standing_mod, "JOURNAL_LIMIT", 3)
    model, rules = _setup()
    for i in range(6):
        apply_impression(model, rules, _imp(i, 4, tag=f"t{i}", day=i))
    apply_impression(model, rules, _imp(2, 4, tag="t2", day=2))
    model.standing.decay("ann", "player", "romance", day=10, days=2, minute=999)
    assert len(model.standing.journal) == 3 and model.standing.checkpoint["sequence"] > 0
    assert model.standing.replay() == model.standing.standings
    restored = WorldModel.from_dict(model.to_dict()).standing
    assert restored.replay() == model.standing.standings
    assert restored.to_dict() == model.standing.to_dict()
    restored.bind(rules.tracks)
    assert restored.apply(_imp(0, 4, tag="t0", day=0)).kind == "duplicate", "folded effect ids stay deduplicated"


def test_decay_is_explicit_ordered_and_can_drop_a_tier():
    model, rules = _setup()
    apply_impression(model, rules, _imp(1, 10))
    effect = model.standing.decay("ann", "player", "romance", day=3, days=3, minute=100)
    assert effect.applied == -6 and model.standing.get("ann", "player", "romance").value == 4
    assert model.standing.decay("ann", "player", "romance", day=3, days=3, minute=100).applied == -6
    assert model.standing.get("ann", "player", "romance").value == 4, "same decay event applies once"


def test_tier_conditions_evaluate_through_the_holder():
    model, rules = _setup()
    apply_impression(model, rules, _imp(1, 10))
    vp = viewpoint(model, "ann", "player")
    assert parse({"kind": "standing_at_least", "track": "romance", "value": 10}).evaluate(vp) is True
    assert parse({"kind": "tier_reached", "track": "romance", "tier": "friend"}).evaluate(vp) is False
    assert parse({"kind": "tier_reached", "track": "romance", "tier": "nope"}).evaluate(vp) is None


def test_tri_state_logic_never_turns_unknown_into_a_verdict():
    t, f, u = (parse({"kind": "counter_at_least", "counter": "c", "value": 1}),
               parse({"kind": "counter_at_least", "counter": "c", "value": 5}),
               parse({"kind": "feeling", "dimension": "trust", "op": ">=", "value": 0}))
    model = make_model({"ann": "kitchen"})
    model.counters = {"c": 2}
    vp = Viewpoint(model=model, holder="ann", subject="ben")
    assert (t.evaluate(vp), f.evaluate(vp), u.evaluate(vp)) == (True, False, None)
    assert Not(u).evaluate(vp) is None
    assert All((t, u)).evaluate(vp) is None and All((f, u)).evaluate(vp) is False
    assert Any_((f, u)).evaluate(vp) is None and Any_((t, u)).evaluate(vp) is True


def test_knows_uses_the_holders_own_belief_not_the_truth():
    from backend.app.engine.world_model.epistemics import assert_claim
    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    assert_claim(model.epistemics, "ben", "the fridge is broken", 0)
    knows = parse({"kind": "knows", "proposition": "the fridge is broken"})
    assert knows.evaluate(Viewpoint(model=model, holder="ann")) is False
    assert knows.evaluate(Viewpoint(model=model, holder="ben")) is True
    assert knows.evaluate(Viewpoint(model=model, holder=None)) is True


def test_failing_requirements_are_reported_for_tells():
    model, rules = _setup()
    vp = viewpoint(model, "ann", "player", Graph(trust=0.1))
    assert [r.id for r in failing_requirements(rules, "ann", "romance", vp)] == ["trust_first"]


@pytest.mark.parametrize("bad", [
    {"tracks": [{"id": "r", "tiers": []}]},
    {"tracks": [{"id": "r", "tiers": [{"id": "a", "floor": 0, "ceiling": 10},
                                       {"id": "b", "floor": 15, "ceiling": 20}]}]},
    {"tracks": [{"id": "r", "tiers": [{"id": "a", "floor": 0, "ceiling": 10,
                                       "gate": {"kind": "counter_at_least", "counter": "c", "value": 1}}]}]},
    {"tracks": [{"id": "r", "repeat_decay": 2, "tiers": [{"id": "a", "floor": 0, "ceiling": 10}]}]},
    {"tracks": [{"id": "r", "tiers": [{"id": "a", "floor": 0, "ceiling": 10}]}],
     "requirements": {"ann": [{"id": "x", "track": "r", "tier": "zzz",
                               "condition": {"kind": "counter_at_least", "counter": "c", "value": 1}}]}},
    {"tracks": [{"id": "r", "tiers": [{"id": "a", "floor": 0, "ceiling": 10}]}],
     "requirements": {"ann": [{"id": "x", "track": "r", "tier": "a",
                               "condition": {"kind": "height_above", "value": 180}}]}},
])
def test_invalid_track_declarations_fail_loudly(bad):
    with pytest.raises(Exception):
        social_rules({"social_tracks": bad})


def test_stories_without_tracks_have_no_social_rules():
    assert social_rules({}) is None
