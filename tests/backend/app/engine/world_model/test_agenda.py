"""BL-39 phase G: agendas from each character's own view, off-screen life, NPC couples."""
from types import SimpleNamespace

from backend.app.engine.rules.tracks import social_rules
from backend.app.engine.world_model.agenda import (
    SocialContext, add_intention, agenda_weight, couples_ready, intentions, next_beat, refresh_agendas,
)
from backend.app.engine.world_model.intent import Intention
from backend.app.engine.world_model.intentions import propose_agenda_invitations
from backend.app.engine.world_model.model import WorldModel
from backend.app.engine.world_model.offscreen import Encounter, _commit, outcome_weights
from backend.app.engine.world_model.standing import Standing
from backend.app.engine.world_model.turn import advance_npc_life, begin_turn

from tests.backend.app.engine.world_model.helpers import FakeRelationships, make_model

TRACKS = {
    "tracks": [{"id": "romance", "daily_gain_cap": 50, "repeat_decay": 1.0, "tiers": [
        {"id": "strangers", "floor": 0, "ceiling": 25}, {"id": "interested", "floor": 25, "ceiling": 60},
        {"id": "dating", "floor": 60, "ceiling": 75}, {"id": "committed", "floor": 75, "ceiling": 100}]}],
    "appraisal": {"track": "romance", "gain_scale": 3, "eligible": "opposite_gender"},
    "couples": {"interested_tier": "interested", "dating_tier": "dating", "committed_tier": "committed",
                "days_together": 2},
}
GENDERS = {"player": "M", "ann": "F", "cat": "F", "ben": "M", "dan": "M"}


def _ctx():
    return SocialContext(social_rules({"social_tracks": TRACKS}), GENDERS)


def refresh_all(model, ctx=None, day=0, **kwargs):
    """Refresh the stances the way a turn does, then the agendas derived from them."""
    from backend.app.engine.rules.personality import personalities
    from backend.app.engine.world_model.stances import refresh_stances, stance_rules
    ctx = ctx or _ctx()
    rules, policy = ctx.rules, ctx.rules.couples
    variables = {"track": rules.appraisal.track, "interested": policy.interested_tier, "dating": policy.dating_tier}
    refresh_stances(model, stance_rules({}, variables), graph=None, people=personalities({}), eligible=ctx.eligible,
                    levels=(), day=day, intensity=rules.intensity)
    refresh_agendas(model, rules.appraisal.track, day, intensity=rules.intensity, **kwargs)


def _set(model, a, b, value):
    model.standing.bind(_ctx().rules.tracks)
    model.standing.standings[(a, b, "romance")] = Standing(value=value)


def test_agendas_come_from_each_characters_own_standing():
    model = make_model({"ann": "k", "cat": "k", "ben": "k"})
    ctx = _ctx()
    _set(model, "ann", "ben", 30)
    _set(model, "ben", "ann", 5)
    refresh_all(model, ctx)
    assert [(i.kind, i.target) for i in intentions(model, "ann", 0)] == [("pursue", "ben")]
    assert intentions(model, "ben", 0) == [], "ben is not drawn to ann: his own standing decides"
    _set(model, "cat", "ben", 40)
    refresh_all(model, ctx)
    assert {i.kind for i in intentions(model, "cat", 0)} == {"pursue", "compete_for"}
    assert intentions(model, "ann", 9) == [], "intentions expire"


def test_offscreen_life_weighs_agendas_and_moves_eligible_pairs_both_ways():
    model = make_model({"ann": "k", "ben": "k", "dan": "k"})
    ctx = _ctx()
    rel = FakeRelationships()
    enc = Encounter("ann", "ben", "k", 60, 60)
    plain = outcome_weights(model, enc, rel, social=ctx)
    add_intention(model, "ann", Intention("pursue", "ben", 0.5, "x", 5))
    assert outcome_weights(model, enc, rel, social=ctx)["affection"] == plain["affection"] * 1.5
    _commit(model, enc, "affection", rel, ctx)
    assert model.standing.get("ann", "ben", "romance").value == 3.0
    assert model.standing.get("ben", "ann", "romance").value == 3.0
    _commit(model, Encounter("ben", "dan", "k", 90, 60), "affection", rel, ctx)
    assert model.standing.get("ben", "dan", "romance") is None, "not eligible under this story"


def test_couples_form_only_when_both_qualify_and_pursue_each_other():
    model = make_model({"ann": "k", "ben": "k"})
    ctx = _ctx()
    _set(model, "ann", "ben", 65)
    _set(model, "ben", "ann", 20)
    refresh_all(model, ctx)
    assert couples_ready(model, "romance", "dating", ctx.eligible, 0) == [], "one-sided is not a couple"
    _set(model, "ben", "ann", 62)
    refresh_all(model, ctx)
    assert couples_ready(model, "romance", "dating", ctx.eligible, 0) == [("ann", "ben")]


def test_nobody_is_in_two_couples_at_once():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    ctx = _ctx()
    for a, b in (("ann", "ben"), ("ben", "ann"), ("cat", "ben"), ("ben", "cat")):
        _set(model, a, b, 65)
    refresh_all(model, ctx)
    assert couples_ready(model, "romance", "dating", ctx.eligible, 0) == [("ann", "ben")]
    model.npc_couples["ann|ben"] = 0
    assert couples_ready(model, "romance", "dating", ctx.eligible, 0) == [], "ben is already taken"


def test_someone_in_a_couple_pursues_only_their_partner():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    ctx = _ctx()
    _set(model, "ben", "ann", 50)
    _set(model, "ben", "cat", 50)
    refresh_all(model, ctx)
    assert {i.target for i in intentions(model, "ben", 0)} == {"ann", "cat"}
    model.npc_couples["ann|ben"] = 0
    refresh_all(model, ctx)
    assert {i.target for i in intentions(model, "ben", 0)} == {"ann"}


class Lifecycle:
    enabled = True

    def __init__(self, ids):
        self.ids, self.proposed = list(ids), []

    def active_ids(self):
        return list(self.ids)

    def propose_departure(self, cid, *, minute, reason, event_id):
        self.proposed.append((cid, event_id))


def test_a_committed_couple_leaves_through_the_cast_scheduler_and_counts():
    model = make_model({"ann": "k", "ben": "k", "cat": "k"})
    ctx = _ctx()
    state = SimpleNamespace(cast_lifecycle=Lifecycle(["ann", "ben", "cat"]), pending_events=[])
    _set(model, "ann", "ben", 80)
    _set(model, "ben", "ann", 80)
    advance_npc_life(state, model, ctx, 0)
    assert model.npc_couples == {"ann|ben": 0} and model.counters == {}
    advance_npc_life(state, model, ctx, 24 * 60)
    assert model.counters == {}, "not together long enough"
    advance_npc_life(state, model, ctx, 2 * 24 * 60)
    assert model.counters == {"couples_left": 1} and model.departed_couples == ["ann|ben"]
    assert [p[0] for p in state.cast_lifecycle.proposed] == ["ann", "ben"]
    assert {e.payload["departing_id"] for e in state.pending_events} == {"ann", "ben"}
    advance_npc_life(state, model, ctx, 3 * 24 * 60)
    assert model.counters == {"couples_left": 1}, "a couple leaves once"


def test_a_scene_beat_goes_to_whoever_waited_longest_and_questions_come_first():
    model = make_model({"ann": "k", "cat": "k"})
    add_intention(model, "ann", Intention("pursue", "player", 0.9, "x", 5))
    add_intention(model, "cat", Intention("test_loyalty", "player", 0.8, "x", 5))
    first = next_beat(model, {"ann", "cat"}, 0)
    model.initiative_last_day[f"beat:{first[0]}"] = 0
    second = next_beat(model, {"ann", "cat"}, 0)
    assert {first[0], second[0]} == {"ann", "cat"}, "the other one gets the next beat"

    state = SimpleNamespace(world_model=model, minute=0, location_id="k", player_name="Paul",
                            story_cfg={"world_model": {"enabled": True}}, characters=model.characters,
                            cast_lifecycle=None, character_graph=None)
    from backend.app.engine.extractors.turn_extractor import QuestionAsked
    from backend.app.engine.world_model.turn import record_questions
    record_questions(state, [QuestionAsked("ann", "Where were you?")], [], message="Ann, where were you?")
    begin_turn(state, "Ann, where were you?", 0)
    assert not any("drawn to the player" in l or "where they stand" in l for l in model.view.must_address)


def test_agenda_invitations_come_from_intentions_once_a_day():
    model = make_model({"ann": "k", "ben": "k"}, player_place="k")
    add_intention(model, "ben", Intention("compete_for", "ann", 0.6, "x", 5))
    first = propose_agenda_invitations(model, 60)
    assert (first.proposer, first.counterpart, first.status) == ("ben", "ann", "proposed")
    assert propose_agenda_invitations(model, 120) is None


def test_agendas_couples_and_counters_survive_a_save():
    model = make_model({"ann": "k"})
    add_intention(model, "ann", Intention("pursue", "player", 0.4, "x", 3))
    model.npc_couples, model.departed_couples, model.counters = {"a|b": 1}, ["a|b"], {"couples_left": 1}
    restored = WorldModel.from_dict(model.to_dict())
    assert restored.agendas == model.agendas and restored.npc_couples == {"a|b": 1}
    assert restored.counters == {"couples_left": 1} and restored.departed_couples == ["a|b"]


def test_terrace_declares_couples():
    from backend.app.engine.story_loader import build_story_registry
    rules = social_rules(build_story_registry()["six_strangers"]["raw"])
    assert rules.couples.committed_tier == "committed"


def test_agenda_weight_is_neutral_without_intentions():
    model = make_model({"ann": "k", "ben": "k"})
    assert agenda_weight(model, "ann", "ben", 0) == 1.0
