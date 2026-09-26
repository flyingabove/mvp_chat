"""Scenario gates for causal social memory and promises."""
from types import SimpleNamespace

from backend.app.engine.world_model.gossip import share_memory
from backend.app.engine.world_model.turn import _build_view, end_turn
from tests.backend.app.engine.world_model.helpers import make_model


def test_due_promise_is_not_fulfilled_merely_by_building_a_scene():
    from backend.app.engine.world_model.commitments import add_commitment

    model = make_model({"ann": "kitchen"})
    own, counterpart = add_commitment(model, "ann", "player", "cook together", due=0, minute=0)
    state = SimpleNamespace(cast_lifecycle=None, characters=model.characters, character_graph=None)
    first = _build_view(model, state, "What are we doing?", None, {})
    second = _build_view(model, state, "What are we doing?", None, {})
    assert first.must_address and second.must_address
    assert own.status == "open" and counterpart.status == "open"


def test_gossip_keeps_root_source_across_repeated_tellings_and_save():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "kitchen"})
    original = model.memories.add("ann", "@player and @dana went on a date", "witnessed", 1, kind="fact")
    relayed = share_memory(model, "ann", "ben", 2, model.rng("gossip-a"))
    again = share_memory(model, "ben", "cat", 3, model.rng("gossip-b"))
    assert relayed is not None and again is not None
    assert relayed.root_source_id == original.id
    assert again.root_source_id == original.id
    assert again.source == "told_by:ben"
    assert model.from_dict(model.to_dict()).memories.of("cat")[-1].root_source_id == original.id
    assert again.assertion_id == relayed.assertion_id
    assert model.epistemics.transmissions[-1].parent_id == relayed.transmission_id
    assert len(model.epistemics.assertions) == 1


def test_same_event_can_be_heard_from_a_second_independent_witness():
    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "kitchen"})
    event = model.world.add_event(1, "kitchen", ("ann", "ben"), "they left together")
    model.memories.add("ann", "@ann and @ben left together", "witnessed", 1,
                       kind="fact", event_id=event.id)
    model.memories.add("ben", "@ann and @ben left together", "witnessed", 1,
                       kind="fact", event_id=event.id)
    one = share_memory(model, "ann", "cat", 2, model.rng("one"))
    two = share_memory(model, "ben", "cat", 3, model.rng("two"))
    assert one is not None and two is not None
    assert one.root_source_id != two.root_source_id
    assert {m.source for m in model.memories.of("cat")} == {"told_by:ann", "told_by:ben"}


def test_private_confessional_does_not_enter_housemate_memory():
    model = make_model({"ann": "kitchen"})
    state = SimpleNamespace(cast_lifecycle=None, characters=model.characters, character_graph=None)
    _build_view(model, state, "[confessional: I think Ann is lying.]", None, {})
    assert model.memories.of("ann") == []


def test_remote_callers_words_are_not_heard_by_local_housemates():
    model = make_model({"ann": "kitchen", "ben": "outside"})
    state = SimpleNamespace(world_model=model, story_cfg={"world_model": {"enabled": True}})
    end_turn(state, "", [{"kind": "dialogue", "speaker_id": "ben", "text": "I know a secret."}])
    assert model.memories.of("ann") == []
    assert model.memories.of("ben")[-1].text.endswith("I know a secret.")


def test_agreement_requires_counterpart_acceptance_and_reschedule_confirmation():
    from backend.app.engine.world_model.agreements import propose, decide, reschedule, conflicts

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    book = model.agreements
    cooking = propose(book, "player", "ann", "cook dinner", due=60, minute=0)
    assert cooking.status == "proposed" and cooking.decisions == {"player": "accepted", "ann": "pending"}
    assert not conflicts(book, "player", 60)
    decide(book, cooking.id, "ann", "accepted", 1)
    assert cooking.status == "accepted"
    concert = propose(book, "ben", "player", "concert", due=60, minute=2)
    decide(book, concert.id, "player", "accepted", 3)
    assert {a.id for a in conflicts(book, "player", 60)} == {cooking.id, concert.id}
    revised = reschedule(book, cooking.id, "player", 90, 4)
    assert revised.status == "proposed" and revised.decisions["ann"] == "pending"
    assert cooking.status == "accepted"
    assert {a.id for a in conflicts(book, "player", 60)} == {cooking.id, concert.id}
    decide(book, revised.id, "ann", "accepted", 5)
    assert cooking.status == "superseded"
    assert {a.id for a in conflicts(book, "player", 60)} == {concert.id}
    restored = model.from_dict(model.to_dict())
    assert restored.agreements.get(revised.id).decisions["ann"] == "accepted"


def test_attendance_does_not_equal_fulfillment():
    from backend.app.engine.world_model.agreements import propose, decide, resolve

    model = make_model({"ann": "kitchen"})
    agreement = propose(model.agreements, "player", "ann", "cooking lesson", due=60, minute=0)
    decide(model.agreements, agreement.id, "ann", "accepted", 1)
    model.world.minute = 60
    assert model.present_with_player() == ["ann"]
    assert agreement.status == "accepted"
    resolve(model.agreements, agreement.id, "completed", 61, evidence_event_id="E-cooked")
    assert agreement.status == "completed" and agreement.outcome_event_id == "E-cooked"


def test_epistemic_claim_and_transmission_do_not_change_world_truth():
    from backend.app.engine.world_model.epistemics import assert_claim, transmit, belief_for

    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "kitchen"})
    truth_count = len(model.world.events)
    assertion = assert_claim(model.epistemics, "ann", "player dating someone", 1, stance="affirm")
    first = transmit(model.epistemics, assertion.id, "ann", "ben", 2)
    second = transmit(model.epistemics, assertion.id, "ben", "cat", 3, parent_id=first.id)
    assert first.root_id == second.root_id == assertion.id
    assert belief_for(model.epistemics, "cat", assertion.proposition_id).support_roots == {assertion.id}
    assert len(model.world.events) == truth_count
    loaded = model.from_dict(model.to_dict())
    assert belief_for(loaded.epistemics, "cat", assertion.proposition_id).support_roots == {assertion.id}


def test_independent_source_and_contradiction_remain_distinct():
    from backend.app.engine.world_model.epistemics import assert_claim, transmit, belief_for

    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "kitchen"})
    positive = assert_claim(model.epistemics, "ann", "player dating someone", 1, stance="affirm")
    negative = assert_claim(model.epistemics, "ben", "player dating someone", 2, stance="deny")
    transmit(model.epistemics, positive.id, "ann", "cat", 3)
    transmit(model.epistemics, negative.id, "ben", "cat", 4)
    view = belief_for(model.epistemics, "cat", positive.proposition_id)
    assert view.support_roots == {positive.id}
    assert view.opposing_roots == {negative.id}
    assert view.stance == "disputed"
