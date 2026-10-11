"""P-08 slice 1: stances derived from each holder's own view, with rules, causes, privacy and persistence."""
import pytest

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.rules.conditions import Viewpoint, parse
from backend.app.engine.rules.personality import personalities
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.stances import (
    Stance, StanceBook, parse_rules, refresh_stances, refresh_stances_for_state, stance_rules)
from tests.backend.app.engine.world_model.helpers import make_model
from tests.backend.app.engine.world_model.test_agenda import GENDERS, TRACKS, _ctx, _set

VARS = {"track": "romance", "interested": "interested", "dating": "dating"}


def _graph(*edges):
    return CharacterGraph.from_dict({"edges": [{"from_id": a, "to_id": b, "state": s} for a, b, s in edges]})


def _state(model, graph=None, cfg=None):
    from types import SimpleNamespace
    return SimpleNamespace(world_model=model, story_cfg={"social_tracks": TRACKS, **(cfg or {})},
                           character_graph=graph or _graph(), gender="M")


def _refresh(model, graph=None, cfg=None):
    refresh_stances_for_state(_state(model, graph, cfg), model, _ctx_from(model, cfg), 0)
    return model.stances


def _ctx_from(model, cfg=None):
    return _ctx()


# ---------------------------------------------------------------- the generic pack
def test_a_crush_needs_the_holders_own_standing_and_an_eligible_pair():
    model = make_model({"ann": "k", "cat": "k", "ben": "k"})
    _set(model, "ann", "ben", 30)               # Ann is drawn to Ben
    _set(model, "ben", "ann", 5)                # Ben is not drawn to Ann
    _set(model, "ann", "cat", 40)               # ... and the rule's eligibility excludes same-gender pairs
    book = _refresh(model)
    assert book.has("ann", "crush", "ben") and not book.has("ben", "crush", "ann")
    assert not book.has("ann", "crush", "cat") or GENDERS["ann"] != GENDERS["cat"]
    stance = book.of("ann", "crush")[0]
    assert stance.target == "ben" and stance.strength >= 0.8 and "crush#0" in stance.cause_ids and stance.since_day == 0


def test_two_crushes_on_the_same_person_make_a_rival_from_each_holders_own_crush():
    model = make_model({"ann": "k", "cat": "k", "ben": "k"})
    _set(model, "ann", "ben", 30)
    _set(model, "cat", "ben", 45)
    book = _refresh(model)
    assert book.has("ann", "rival", "cat", about="ben") and book.has("cat", "rival", "ann", about="ben")
    assert not book.has("ben", "rival", "ann", about="cat"), "Ben has no crush, so he is nobody's rival"


def test_a_rule_reads_only_the_holders_view_so_a_hidden_feeling_of_someone_else_changes_nothing():
    model = make_model({"ann": "k", "ben": "k"})
    suspicious = _graph(("ann", "ben", {"suspicion": 0.7}))
    assert _refresh(model, suspicious).has("ann", "suspects", "ben")
    hidden = _graph(("ann", "ben", {"suspicion": 0.7}), ("ben", "ann", {"suspicion": 0.9, "trust": -0.9}))
    book = _refresh(model, hidden)
    assert book.has("ann", "suspects", "ben") and book.strength("ann", "distrusts", "ben") == 0.0, \
        "Ben's own feelings are his: they never reach Ann's opinion"
    assert not _refresh(model, _graph(("ben", "ann", {"suspicion": 0.9}))).has("ann", "suspects", "ben")


def test_stances_are_recomputed_each_turn_keep_their_start_day_and_vanish_when_the_cause_does():
    model = make_model({"ann": "k", "ben": "k"})
    ctx = _ctx()
    graph = _graph(("ann", "ben", {"trust": 0.6, "affection": 0.4}))
    state = _state(model, graph)
    refresh_stances_for_state(state, model, ctx, 0)
    assert model.stances.has("ann", "ally", "ben") and model.stances.of("ann")[0].since_day == 0
    model.world.minute = 3 * 24 * 60
    refresh_stances_for_state(state, model, ctx, model.world.minute)
    assert model.stances.of("ann", "ally")[0].since_day == 0, "an unchanged stance keeps the day it began"
    state.character_graph = _graph(("ann", "ben", {"trust": 0.1, "affection": 0.4}))
    refresh_stances_for_state(state, model, ctx, model.world.minute)
    assert not model.stances.has("ann", "ally", "ben")


def test_a_story_without_social_tracks_has_no_stances_and_old_saves_load():
    model = make_model()
    refresh_stances_for_state(_state(model), model, None, 0)
    assert model.stances.items == {}
    data = model.to_dict()
    data.pop("stances")
    assert WorldModel.from_dict(data).stances.items == {}


def test_stances_persist_with_their_causes():
    model = make_model({"ann": "k", "ben": "k"})
    _refresh(model, _graph(("ann", "ben", {"suspicion": 0.8})))
    again = WorldModel.from_dict(model.to_dict())
    assert again.stances.to_dict() == model.stances.to_dict() and again.stances.items


def test_a_story_overrides_adds_and_disables_rules_by_id():
    cfg = {"stances": {"rules": [
        {"id": "suspects", "kind": "suspects", "min_strength": 0.5,
         "when": [{"weight": 0.5, "if": {"kind": "feeling", "dimension": "suspicion", "op": ">=", "value": 0.9}}]},
        {"id": "ally", "disabled": True},
        {"id": "envies", "kind": "envies", "min_strength": 0.5,
         "when": [{"weight": 0.5, "if": {"kind": "feeling", "dimension": "jealousy", "op": ">=", "value": 0.5}}]}]}}
    ids = {r.id for r in stance_rules(cfg, VARS)}
    assert "ally" not in ids and {"envies", "suspects", "crush", "rival"} <= ids
    model = make_model({"ann": "k", "ben": "k"})
    book = _refresh(model, _graph(("ann", "ben", {"suspicion": 0.7, "jealousy": 0.6})), cfg)
    assert book.has("ann", "envies", "ben") and not book.has("ann", "suspects", "ben"), "the override is stricter"


def test_a_default_rule_that_needs_a_missing_story_variable_does_not_apply_but_the_authors_rule_must_be_complete():
    assert "crush" not in {r.id for r in stance_rules({}, {"track": "romance"})}
    own = {"stances": {"rules": [{"id": "x", "kind": "x", "min_strength": 0.1,
                                  "when": [{"weight": 1, "if": {"kind": "tier_reached", "track": "$nope", "tier": "a"}}]}]}}
    with pytest.raises(ValueError, match=r"\$nope"):
        stance_rules(own, VARS)


# ---------------------------------------------------------------- rule validation
@pytest.mark.parametrize("bad, why", [
    ({"kind": "k", "min_strength": 0.5, "when": [{"weight": 1, "if": {"kind": "eligible"}}]}, "needs an id"),
    ({"id": "r", "min_strength": 0.5, "when": [{"weight": 1, "if": {"kind": "eligible"}}]}, "needs a kind"),
    ({"id": "r", "kind": "k", "scope": "many", "min_strength": 0.5, "when": [{"weight": 1, "if": {"kind": "eligible"}}]},
     "scope must be"),
    ({"id": "r", "kind": "k", "scope": "triple", "min_strength": 0.5,
      "when": [{"weight": 1, "if": {"kind": "eligible"}}]}, "needs about_has"),
    ({"id": "r", "kind": "k", "when": [{"weight": 1, "if": {"kind": "eligible"}}]}, "numeric min_strength"),
    ({"id": "r", "kind": "k", "min_strength": 0.5, "when": []}, "at least one term"),
    ({"id": "r", "kind": "k", "min_strength": 0.5, "when": [{"if": {"kind": "eligible"}}]}, "numeric weight"),
    ({"id": "r", "kind": "k", "min_strength": 0.5, "when": [{"weight": 1, "if": {"kind": "vibes"}}]}, "unknown condition"),
])
def test_a_bad_stance_rule_fails_loudly(bad, why):
    with pytest.raises(ValueError, match=why):
        parse_rules([bad], VARS)


def test_duplicate_rule_ids_are_refused():
    rule = {"id": "r", "kind": "k", "min_strength": 0.5, "when": [{"weight": 1, "if": {"kind": "eligible"}}]}
    with pytest.raises(ValueError, match="duplicate"):
        parse_rules([rule, rule], VARS)


# ---------------------------------------------------------------- the new conditions
def _vp(model, holder="ann", subject="ben", third=None, graph=None, **kw):
    return Viewpoint(model=model, holder=holder, subject=subject, third=third, graph=graph, **kw)


def test_trait_strategy_and_goal_weight_read_the_named_roles_character():
    model = make_model({"ann": "k", "ben": "k"})
    people = personalities({"characters": [{"key": "ann"}, {"key": "ben"}], "personalities": {
        "ann": {"temperament": {"jealousy": 0.9}, "strategy": "scheming",
                "goals": [{"id": "g", "kind": "love", "target": "ben", "weight": 0.8}]},
        "ben": {"temperament": {"jealousy": 0.1}}}})
    vp = _vp(model, people=people)
    assert parse({"kind": "trait", "dial": "jealousy", "op": ">=", "value": 0.7}).evaluate(vp) is True
    assert parse({"kind": "trait", "dial": "jealousy", "op": ">=", "value": 0.7, "of": "subject"}).evaluate(vp) is False
    assert parse({"kind": "strategy", "values": ["scheming", "patient"]}).evaluate(vp) is True
    assert parse({"kind": "strategy", "values": ["open"], "of": "subject"}).evaluate(vp) is True
    assert parse({"kind": "goal_weight", "goal_kind": "love", "op": ">=", "value": 0.5, "about": "subject"}).evaluate(vp) is True
    assert parse({"kind": "goal_weight", "goal_kind": "love", "op": ">=", "value": 0.5, "of": "subject"}).evaluate(vp) is False
    assert parse({"kind": "trait", "dial": "jealousy", "op": ">=", "value": 0.7}).evaluate(_vp(model)) is None


@pytest.mark.parametrize("raw, why", [
    ({"kind": "trait", "dial": "swagger", "value": 0.5}, "unknown temperament dial"),
    ({"kind": "strategy", "values": ["nonsense"]}, "unknown strategy"),
    ({"kind": "strategy", "values": []}, "non-empty"),
    ({"kind": "trait", "dial": "pride", "value": 0.5, "of": "nobody"}, "unknown role"),
    ({"kind": "has_stance"}, "needs 'stance'"),
    ({"kind": "goal_weight", "goal_kind": "love", "value": 0.5, "about": "elsewhere"}, "unknown role"),
    ({"kind": "acquaintance_at_least"}, "needs 'level'"),
])
def test_new_condition_kinds_validate_at_parse_time(raw, why):
    with pytest.raises(ValueError, match=why):
        parse(raw)


def test_in_couple_and_eligible_and_has_stance():
    model = make_model({"ann": "k", "ben": "k"})
    model.npc_couples["ann|ben"] = 0
    assert parse({"kind": "in_couple"}).evaluate(_vp(model)) is True
    assert parse({"kind": "in_couple", "of": "third"}).evaluate(_vp(model, third="cat")) is False
    assert parse({"kind": "eligible"}).evaluate(_vp(model)) is None
    vp = _vp(model, eligible=lambda a, b: (a, b) == ("ann", "ben"))
    assert parse({"kind": "eligible"}).evaluate(vp) is True
    assert parse({"kind": "eligible", "a": "subject", "b": "holder"}).evaluate(vp) is False
    model.stances.add(Stance("crush", "ann", "ben", 0.9))
    assert parse({"kind": "has_stance", "stance": "crush"}).evaluate(vp) is True
    assert parse({"kind": "has_stance", "stance": "crush", "min": 0.95}).evaluate(vp) is False
    assert parse({"kind": "has_stance", "stance": "crush", "by": "subject"}).evaluate(vp) is False


def test_acquaintance_at_least_counts_days_and_turns_with_the_player_and_never_blocks_residents():
    from backend.app.engine.rules.acquaintance import acquaintance_levels
    levels = acquaintance_levels({"acquaintance": {"levels": [
        {"id": "strangers", "min_days": 0, "min_turns": 0, "conduct": "stiff"},
        {"id": "familiar", "min_days": 1, "min_turns": 5, "conduct": "easy"}]}})
    model = make_model({"ann": "k"})
    cond = parse({"kind": "acquaintance_at_least", "level": "familiar"})
    assert cond.evaluate(_vp(model, subject="player", levels=levels)) is False, "they have not met"
    model.first_met_day["ann"], model.turns_together["ann"] = 0, 6
    assert cond.evaluate(_vp(model, subject="player", levels=levels)) is False, "same day"
    model.world.minute = 24 * 60
    assert cond.evaluate(_vp(model, subject="player", levels=levels)) is True
    assert cond.evaluate(_vp(model, subject="cat", levels=levels)) is True
    assert cond.evaluate(_vp(model, subject="player")) is True, "a story with no levels has nothing to gate on"


def test_witnessed_needs_the_holder_there_and_event_count_can_look_back_a_few_days():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    event = model.world.add_event(0, "k", ("ben", "cat"), "@ben snapped at @cat", kind="snap",
                                  payload={"witnesses": ["ann"]})
    saw = parse({"kind": "witnessed", "event_kind": "snap"})
    assert saw.evaluate(_vp(model, subject="ben")) is True and saw.causes(_vp(model, subject="ben")) == (event.id,)
    event.payload["witnesses"] = []
    assert saw.evaluate(_vp(model, subject="ben")) is False, "remove the witness and the opinion stops following"
    assert saw.evaluate(_vp(model, holder="cat", subject="ben")) is True, "a participant saw it"
    recent = parse({"kind": "event_count", "event_kind": "snap", "min": 1, "within_days": 2, "with_subject": False})
    assert recent.evaluate(_vp(model, holder="ben")) is True
    model.world.minute = 3 * 24 * 60
    assert recent.evaluate(_vp(model, holder="ben")) is False
    assert parse({"kind": "event_count", "event_kind": "snap", "min": 1, "with_subject": False}).evaluate(
        _vp(model, holder="ben")) is True


def test_existing_conditions_can_look_at_the_third_party():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    graph = _graph(("ann", "cat", {"suspicion": 0.8}))
    cond = parse({"kind": "feeling", "dimension": "suspicion", "op": ">=", "value": 0.5, "toward": "third"})
    assert cond.evaluate(_vp(model, third="cat", graph=graph)) is True
    assert cond.evaluate(_vp(model, third="ben", graph=graph)) is None


def test_stance_book_queries_and_ordering():
    book = StanceBook()
    book.add(Stance("crush", "ann", "ben", 0.9))
    book.add(Stance("crush", "ann", "dan", 1.0))
    book.add(Stance("rival", "cat", "ann", 1.0, about="ben"))
    assert [s.target for s in book.of("ann")] == ["dan", "ben"]
    assert [s.holder for s in book.toward("ann")] == ["cat"]
    assert book.has("cat", "rival", "ann", "ben") and not book.has("cat", "rival", "ann")
    assert StanceBook.from_dict(book.to_dict()).to_dict() == book.to_dict()


# ---------------------------------------------------------------- intensity: a family of stances scales with the story's knob
def test_a_stance_family_is_scaled_by_the_story_intensity_and_vanishes_at_zero():
    from backend.app.engine.rules.tracks import Intensity
    from backend.app.engine.world_model.stances import stance_rules as rules_for

    def book(intensity):
        model = make_model({"ann": "k", "cat": "k", "ben": "k"})
        _set(model, "ann", "ben", 30)
        _set(model, "cat", "ben", 45)
        refresh_stances(model, rules_for({}, VARS), graph=_graph(), people=personalities({}), eligible=_ctx().eligible,
                        levels=(), day=0, intensity=intensity)
        return model.stances
    full, half, off = book(None), book(Intensity(romance=0.5, rivalry=1.0)), book(Intensity(romance=0.0, rivalry=1.0))
    assert full.strength("ann", "crush", "ben") >= 0.8
    assert half.strength("ann", "crush", "ben") == pytest.approx(full.strength("ann", "crush", "ben") * 0.5)
    assert half.has("ann", "rival", "cat", about="ben"), "rivalry is its own knob, untouched by the romance one"
    assert not off.of("ann", "crush") and not off.of("ann", "rival"), "no crush means no rival either"
    quiet = book(Intensity(romance=1.0, rivalry=0.0))
    assert quiet.has("ann", "crush", "ben") and not quiet.of("ann", "rival")


def test_a_rule_family_must_be_known():
    with pytest.raises(ValueError, match="family"):
        parse_rules([{"id": "x", "kind": "x", "min_strength": 0.1, "family": "gossip",
                      "when": [{"weight": 1, "if": {"kind": "eligible"}}]}], VARS)


@pytest.mark.parametrize("kind, feeling, absent", [
    ("resents", {"affection": -0.5, "trust": -0.4}, {"affection": -0.5}),
    ("protective_of", {"affection": 0.7, "trust": 0.5}, {"affection": 0.7}),
    ("admires", {"trust": 0.8, "affection": 0.4}, {"trust": 0.8}),
])
def test_feeling_based_stance_kinds_need_every_part_of_their_rule(kind, feeling, absent):
    model = make_model({"ann": "k", "ben": "k"})
    assert _refresh(model, _graph(("ann", "ben", feeling))).has("ann", kind, "ben")
    assert not _refresh(model, _graph(("ann", "ben", absent))).has("ann", kind, "ben")


def test_ex_follows_a_committed_romance_ending_and_is_private_to_those_in_it():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    model.world.add_event(0, "k", ("ann", "ben"), "@ann and @ben broke up", kind="romance_ending")
    book = _refresh(model)
    assert book.has("ann", "ex", "ben") and book.has("ben", "ex", "ann") and not book.has("cat", "ex", "ben")


def test_owes_needs_a_completed_agreement_between_the_two_and_some_trust():
    from backend.app.engine.world_model.agreements import Agreement
    model = make_model({"ann": "k", "ben": "k"})
    model.agreements.items.append(Agreement(id="a1", proposer="ben", counterpart="ann", activity="help", due=None, created=0, status="completed"))
    trusting = _graph(("ann", "ben", {"trust": 0.5}))
    assert _refresh(model, trusting).has("ann", "owes", "ben")
    assert not _refresh(model, _graph()).has("ann", "owes", "ben"), "a favour from a stranger is not a debt"
