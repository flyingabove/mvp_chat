"""Step 6: off-screen resolution, NPC<->NPC edges, gossip."""
from backend.app.engine.world_model.gossip import share_memory, to_third_person
from backend.app.engine.world_model.offscreen import MAX_ENCOUNTERS, find_encounters, outcome_weights, resolve_offscreen
from backend.app.engine.world_model.stepper import StepResult, step_world
from tests.backend.app.engine.world_model.helpers import FakeRelationships, make_model


def _timeline(snapshots, player_place="terrace", player_awake=True):
    return StepResult(timeline=[(minute, snap, player_place, player_awake) for minute, snap in snapshots])


def test_encounters_need_colocation_awake_away_from_player_for_30_minutes():
    snap_together = {"a": ("kitchen", "awake"), "b": ("kitchen", "busy"), "c": ("kitchen", "asleep"),
                     "d": ("terrace", "awake")}
    result = _timeline([(0, snap_together), (15, snap_together), (30, snap_together)])
    pairs = {(e.a, e.b) for e in find_encounters(result)}
    assert pairs == {("a", "b")}                        # c asleep, d is with the (awake) player
    short = _timeline([(0, snap_together), (15, snap_together)])
    assert find_encounters(short) == []


def test_player_asleep_means_nobody_is_in_view():
    snap = {"a": ("terrace", "awake"), "b": ("terrace", "awake")}
    asleep = _timeline([(0, snap), (30, snap)], player_place="terrace", player_awake=False)
    assert [(e.a, e.b) for e in find_encounters(asleep)] == [("a", "b")]


def test_encounter_cap():
    people = {f"p{i}": ("hall", "awake") for i in range(8)}
    result = _timeline([(0, people), (40, people)])
    assert len(find_encounters(result)) == MAX_ENCOUNTERS


def test_outcomes_are_deterministic_and_commit_private_memories_and_edge_deltas():
    def run():
        model = make_model({"a": "kitchen", "b": "kitchen", "c": "terrace"}, player_place="terrace")
        rel = FakeRelationships()
        step = step_world(model, 0, 120, scene_present=set())
        return model, rel, resolve_offscreen(model, step, rel)
    m1, rel1, out1 = run()
    m2, _, out2 = run()
    assert [(o.encounter.a, o.encounter.b, o.kind) for o in out1] == [(o.encounter.a, o.encounter.b, o.kind) for o in out2]
    committed = [o for o in out1 if o.kind != "nothing"]
    assert committed, "this seed must exercise the commit path"
    for outcome in committed:
        event = next(e for e in m1.world.events if e.id == outcome.event_id)
        assert set(event.participants) == {"a", "b"} and event.kind == "offscreen"
        assert m1.memories.knows_event("a", event.id) and m1.memories.knows_event("b", event.id)
        assert not m1.memories.knows_event("c", event.id)
        assert rel1.notes and rel1.notes[0][2] and "@" not in rel1.notes[0][2]


def test_hostile_edges_make_conflict_likelier_and_warm_edges_affection():
    model = make_model({"a": "k", "b": "k"})
    snap = {"a": ("k", "awake"), "b": ("k", "awake")}
    enc = find_encounters(_timeline([(0, snap), (30, snap)]))[0]
    cold = FakeRelationships({("a", "b"): {"trust": -0.8, "affection": -0.8, "suspicion": 0.8},
                              ("b", "a"): {"trust": -0.8, "affection": -0.8, "suspicion": 0.8}})
    warm = FakeRelationships({("a", "b"): {"trust": 0.8, "affection": 0.8}, ("b", "a"): {"trust": 0.8, "affection": 0.8}})
    w_cold, w_warm = outcome_weights(model, enc, cold), outcome_weights(model, enc, warm)
    assert w_cold["conflict"] > w_warm["conflict"] and w_warm["affection"] > w_cold["affection"]
    assert w_cold["gossip"] == 0.0                      # nothing to share yet


def test_scorer_hook_can_reweight():
    model = make_model({"a": "k", "b": "k"})
    snap = {"a": ("k", "awake"), "b": ("k", "awake")}
    enc = find_encounters(_timeline([(0, snap), (30, snap)]))[0]
    weights = outcome_weights(model, enc, FakeRelationships(), scorer=lambda e, w: {"chat": 0, "conflict": 10})
    assert weights["chat"] == 0 and weights["conflict"] == 10.0


def test_conflict_leaves_a_trace_visible_only_when_both_are_with_the_player():
    model = make_model({"a": "k", "b": "k"})
    rel = FakeRelationships()
    snap = {"a": ("k", "awake"), "b": ("k", "awake")}
    step = _timeline([(0, snap), (30, snap)])
    resolve_offscreen(model, step, rel, scorer=lambda e, w: {k: (1 if k == "conflict" else 0) for k in w})
    trace = model.traces[-1]
    assert "avoiding each other" in trace.text
    assert trace.visible(60, "anywhere", {"a", "b"}) and not trace.visible(60, "k", {"a"})
    assert rel.state[("a", "b")]["suspicion"] > 0


def test_gossip_passes_a_shareable_memory_with_lower_confidence_and_same_event():
    model = make_model({"a": "k", "b": "k", "c": "t"})
    event = model.world.add_event(1, "park", ("a", "c"), "@a saw @c at the park")
    model.memories.add("a", "I saw @c at the park", "witnessed", 1, event_id=event.id)
    model.memories.add("a", "my secret", "authored", 0, private=True)
    shared = share_memory(model, "a", "b", 5, model.rng("t"))
    assert shared.source == "told_by:a" and shared.confidence == 0.8 and shared.event_id == event.id
    assert shared.text == "@a saw @c at the park"
    assert share_memory(model, "a", "b", 6, model.rng("t")) is None      # already known, secret never shared
    assert not model.memories.of("c")


def test_third_person_rewrite():
    assert to_third_person("I argued with @b about my money", "a") == "@a argued with @b about @a's money"
