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


def test_asking_about_unknown_belief_does_not_write_state():
    from backend.app.engine.world_model.epistemics import belief_for

    model = make_model({"ann": "kitchen"})
    before = model.to_dict()
    assert belief_for(model.epistemics, "ann", "missing").stance == "unknown"
    assert model.to_dict() == before


def test_domain_event_operation_id_dedupes_and_survives_reload():
    model = make_model({"ann": "kitchen"})
    kwargs = dict(minute=5, place="kitchen", participants=("ann", "player"),
                  truth="Ann invited the player", kind="invitation", operation_id="turn-7-invite-ann",
                  payload={"invitee": "player"}, cause_ids=("E-prior",))
    first = model.world.add_event(**kwargs)
    assert model.world.add_event(**kwargs) is first
    restored = model.from_dict(model.to_dict())
    assert restored.world.add_event(**kwargs).id == first.id
    assert len(restored.world.events) == 1
    assert restored.world.events[0].payload == {"invitee": "player"}


def test_legacy_world_snapshot_loads_but_future_version_fails_closed():
    import pytest

    model = make_model({"ann": "kitchen"})
    legacy = model.to_dict()
    legacy["version"] = 1
    legacy.pop("agreements")
    legacy.pop("epistemics")
    legacy.pop("initiative_last_day")
    assert model.from_dict(legacy).agreements.items == []
    future = model.to_dict()
    future["version"] = 999
    with pytest.raises(ValueError, match="version"):
        model.from_dict(future)


def test_rival_initiative_proposes_once_without_assigning_partner_consent():
    from backend.app.engine.world_model.intentions import propose_rival_invitations
    from tests.backend.app.engine.world_model.helpers import FakeRelationships

    model = make_model({"rival": "kitchen", "partner": "kitchen"})
    rel = FakeRelationships({("player", "partner"): {"affection": 0.5},
                             ("rival", "partner"): {"affection": 0.4},
                             ("partner", "rival"): {"affection": 0.2}})
    context = {"enabled": True, "player_gender": "M", "genders": {"rival": "M", "partner": "F"}}
    action = propose_rival_invitations(model, context, rel, minute=0)
    assert action is not None
    assert action.proposer == "rival" and action.counterpart == "partner"
    assert action.status == "proposed" and action.decisions["partner"] == "pending"
    assert propose_rival_invitations(model, context, rel, minute=1) is None
    assert len(model.world.events) == 1
    assert not model.memories.of("player")  # observations, not omniscient recall


def test_rival_initiative_requires_independent_interest_and_presence():
    from backend.app.engine.world_model.intentions import propose_rival_invitations
    from tests.backend.app.engine.world_model.helpers import FakeRelationships

    model = make_model({"rival": "kitchen", "partner": "outside"})
    context = {"enabled": True, "player_gender": "F", "genders": {"rival": "F", "partner": "M"}}
    interested = FakeRelationships({("player", "partner"): {"affection": 0.5},
                                     ("rival", "partner"): {"affection": 0.4}})
    assert propose_rival_invitations(model, context, interested, minute=0) is None
    model.world.move("partner", "kitchen")
    assert propose_rival_invitations(model, context, FakeRelationships(), minute=0) is None
    assert propose_rival_invitations(model, context, interested, minute=0) is not None


def test_extracted_acceptance_resolves_pending_invitation_once():
    from backend.app.engine.world_model.agreements import propose
    from backend.app.engine.world_model.commitments import record_commitment

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    invitation = propose(model.agreements, "ann", "ben", "spend time together", due=100, minute=0)
    first = record_commitment(model, "ben", "ann", "spend time together", "later", 1)
    second = record_commitment(model, "ben", "ann", "spend time together", "later", 2)
    assert first is not None and second is None
    assert invitation.status == "accepted" and len(model.agreements.items) == 1


def test_mutual_departure_needs_both_direct_romantic_decisions():
    from backend.app.engine.world_model.romance import record_departure_decisions, record_relationship_decisions

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    state = SimpleNamespace(world_model=model, gender="M",
                            story_cfg={"mode": {"romance_goal": {"enabled": True,
                                "partner_gender": "opposite_player", "rival_gender": "same_as_player"}},
                                "characters": [{"key": "ann", "gender": "F"},
                                               {"key": "ben", "gender": "M"}]},
                            characters={"ann": object(), "ben": object()}, cast_lifecycle=None)
    assert not record_departure_decisions(state, "Ann and I both agree to leave.",
                                          [{"kind": "dialogue", "speaker_id": "ann",
                                            "text": "That sounds nice."}])
    assert not record_departure_decisions(state,
        "I choose to leave the house with Ann as my romantic partner.", [
            {"kind": "dialogue", "speaker_id": "ann",
             "text": "I choose to leave the house with you as my romantic partner."}])
    assert model.romance_outcome == ""
    record_relationship_decisions(state, "I want to date Ann.", [])
    assert record_relationship_decisions(state, "What do you think?", [
        {"kind": "dialogue", "speaker_id": "ann", "text": "I want to date you too."}])
    assert model.romance_relationship_partner == "ann"
    assert not record_departure_decisions(state,
        "I choose to leave the house with Ann as my romantic partner.", [])
    assert record_departure_decisions(state, "What do you choose?", [
        {"kind": "dialogue", "speaker_id": "ann",
         "text": "I choose to leave the house with you as my romantic partner."}])
    assert model.romance_outcome == "mutual_departure"
    assert model.from_dict(model.to_dict()).romance_outcome == "mutual_departure"


def test_departure_rejects_same_gender_absent_npc_and_narrator_consent():
    from backend.app.engine.world_model.romance import record_departure_decisions

    model = make_model({"ann": "outside", "ben": "kitchen"})
    state = SimpleNamespace(world_model=model, gender="M",
                            story_cfg={"mode": {"romance_goal": {"enabled": True,
                                "partner_gender": "opposite_player", "rival_gender": "same_as_player"}},
                                "characters": [{"key": "ann", "gender": "F"},
                                               {"key": "ben", "gender": "M"}]},
                            characters={"ann": object(), "ben": object()}, cast_lifecycle=None)
    words = "I choose to leave the house with Ann as my romantic partner."
    voice = [{"kind": "dialogue", "speaker_id": "ann",
              "text": "I choose to leave the house with you as my romantic partner."}]
    assert not record_departure_decisions(state, words, voice)
    assert model.romance_outcome == ""
    model.world.move("ann", "kitchen")
    assert not record_departure_decisions(state, "Ann agrees to leave with me.", [
        {"kind": "narration", "speaker_id": None, "text": voice[0]["text"]}])
    assert model.romance_outcome == ""


def test_structured_turn_sets_goal_only_after_prior_mutual_relationship():
    from backend.app.engine.world_model.turn import end_turn
    from backend.app.engine.gameplay import win_condition_detected

    model = make_model({"ann": "kitchen"})
    model.turn = 1
    state = SimpleNamespace(world_model=model, gender="M", over=False,
                            story_cfg={"world_model": {"enabled": True},
                                       "mode": {"romance_goal": {"enabled": True,
                                           "partner_gender": "opposite_player", "rival_gender": "same_as_player"}},
                                       "characters": [{"key": "ann", "gender": "F"}]},
                            characters={"ann": object()}, cast_lifecycle=None)
    end_turn(state, "I want to date Ann.", [
        {"kind": "dialogue", "speaker_id": "ann", "text": "I want to date you too."}])
    assert not win_condition_detected("We will leave together", state)
    model.turn += 1
    end_turn(state, "I choose to leave the house with Ann as my romantic partner.", [
        {"kind": "dialogue", "speaker_id": "ann",
         "text": "I choose to leave the house with you as my romantic partner."}])
    assert win_condition_detected("ordinary dialogue", state)
    assert model.world.place_of("ann") is None
    assert model.world.place_of("player") is None
    assert [event.kind for event in model.world.events] == ["utterance", "romance_relationship",
                                                            "utterance", "relationship_decision",
                                                            "relationship_decision", "romance_ending"]


def test_solo_departure_is_a_valid_nonwinning_ending():
    from backend.app.engine.world_model.romance import record_solo_departure
    from backend.app.engine.gameplay import win_condition_detected

    model = make_model({"ann": "kitchen"})
    state = SimpleNamespace(world_model=model, gender="M", story_cfg={
        "mode": {"romance_goal": {"enabled": True, "partner_gender": "opposite_player"}},
        "characters": [{"key": "ann", "gender": "F"}]},
        characters={"ann": object()}, cast_lifecycle=None)
    assert not record_solo_departure(state, "Maybe I should leave alone.")
    assert record_solo_departure(state, "I choose to leave the house alone.")
    assert model.romance_outcome == "solo_departure"
    assert not win_condition_detected("I leave alone", state)


def test_female_player_can_leave_with_active_male_partner_and_resume_terminal_state():
    from backend.app.engine.world_model.turn import end_turn
    from backend.app.engine.gameplay import win_condition_detected

    model = make_model({"ben": "kitchen", "ann": "kitchen"})
    model.turn = 1
    state = SimpleNamespace(world_model=model, gender="F", story_cfg={
        "world_model": {"enabled": True},
        "mode": {"romance_goal": {"enabled": True, "partner_gender": "opposite_player"}},
        "characters": [{"key": "ann", "gender": "F"}, {"key": "ben", "gender": "M"}]},
        characters={"ann": object(), "ben": object()}, cast_lifecycle=None,
        character_graph=None)
    end_turn(state, "I want to date Ben.", [
        {"kind": "dialogue", "speaker_id": "ben", "text": "I want to date you too."}])
    model.turn += 1
    end_turn(state, "I choose to leave the house with Ben as my romantic partner.", [
        {"kind": "dialogue", "speaker_id": "ben",
         "text": "I choose to leave the house with you as my romantic partner."}])
    assert win_condition_detected("", state)
    assert model.world.place_of("ben") is None
    assert model.world.place_of("ann") == "kitchen"
    state.world_model = model.from_dict(model.to_dict())
    assert win_condition_detected("", state)


def test_partner_withdrawal_clears_old_departure_consent():
    from backend.app.engine.world_model.romance import record_departure_decisions

    model = make_model({"ann": "kitchen"})
    model.romance_relationship_partner = "ann"
    state = SimpleNamespace(world_model=model, gender="M", story_cfg={
        "mode": {"romance_goal": {"enabled": True, "partner_gender": "opposite_player"}},
        "characters": [{"key": "ann", "gender": "F"}]},
        characters={"ann": object()}, cast_lifecycle=None)
    assert not record_departure_decisions(state, "", [
        {"kind": "dialogue", "speaker_id": "ann",
         "text": "I choose to leave the house with you as my romantic partner."}])
    assert model.romance_npc_choice == "ann"
    assert not record_departure_decisions(state, "", [
        {"kind": "dialogue", "speaker_id": "ann", "text": "I don't want to leave with you."}])
    assert not record_departure_decisions(state,
        "I choose to leave the house with Ann as my romantic partner.", [])
    assert model.romance_outcome == ""


def test_relationship_withdrawal_in_final_turn_prevents_stale_victory():
    from backend.app.engine.world_model.turn import end_turn

    model = make_model({"ann": "kitchen"})
    model.romance_relationship_partner = "ann"
    model.romance_relationship_player_choice = "ann"
    model.romance_relationship_npc_choice = "ann"
    model.turn = 3
    state = SimpleNamespace(world_model=model, gender="M", story_cfg={
        "world_model": {"enabled": True},
        "mode": {"romance_goal": {"enabled": True, "partner_gender": "opposite_player"}},
        "characters": [{"key": "ann", "gender": "F"}]},
        characters={"ann": object()}, cast_lifecycle=None, character_graph=None)
    end_turn(state, "I choose to leave the house with Ann as my romantic partner.", [
        {"kind": "dialogue", "speaker_id": "ann", "text": "I don't want to date you. I choose to leave the house with you as my romantic partner."}])
    assert model.romance_relationship_partner == ""
    assert model.romance_outcome == ""


def test_conflict_thread_surfaces_cause_once_and_resolves_after_repair():
    from backend.app.engine.world_model.drama import register_conflict, choose_conflict, repair_conflict

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    conflict = register_conflict(model.drama, ("ann", "ben"), "E-argument", 0,
                                 "Ann and Ben seem distant after an argument")
    assert choose_conflict(model.drama, {"ann", "ben"}, 0) is conflict
    assert choose_conflict(model.drama, {"ann", "ben"}, 0) is None
    repair_conflict(model.drama, conflict.id, "E-apology", 1500)
    assert choose_conflict(model.drama, {"ann", "ben"}, 1500) is None
    restored = model.from_dict(model.to_dict())
    assert restored.drama.get(conflict.id).stage == "resolved"


def test_conflict_cannot_surface_to_absent_player_or_without_witnessable_people():
    from backend.app.engine.world_model.drama import register_conflict, choose_conflict

    model = make_model({"ann": "kitchen", "ben": "outside"})
    register_conflict(model.drama, ("ann", "ben"), "E-argument", 0,
                      "Ann and Ben seem distant")
    assert choose_conflict(model.drama, set(model.present_with_player()), 0) is None


def test_dialogue_observation_proves_speech_only_for_audible_witnesses():
    from backend.app.engine.world_model.turn import end_turn

    model = make_model({"ann": "kitchen", "ben": "kitchen", "cat": "outside"})
    state = SimpleNamespace(world_model=model, story_cfg={"world_model": {"enabled": True}})
    end_turn(state, "", [{"kind": "dialogue", "speaker_id": "ann",
                          "text": "I saw Ben at the station."}])
    assert {item.owner for item in model.epistemics.observations} == {"ann", "ben", "player"}
    assert len(model.world.events) == 1 and model.world.events[0].kind == "utterance"
    assert not model.epistemics.propositions  # hearing a sentence establishes no canonical fact
    assert not model.memories.of("cat")


def test_player_utterance_is_observed_by_present_people_but_confessional_is_not():
    from backend.app.engine.world_model.turn import begin_turn

    model = make_model({"ann": "kitchen", "ben": "outside"})
    state = SimpleNamespace(world_model=model, minute=0, location_id="kitchen", player_name="Paul",
                            story_cfg={"world_model": {"enabled": True}},
                            characters=model.characters, cast_lifecycle=None, character_graph=None)
    begin_turn(state, "I saw Ben at the station.", 0)
    assert {item.owner for item in model.epistemics.observations} == {"ann", "player"}
    assert model.memories.of("ann")[-1].event_id == model.world.events[-1].id
    before = len(model.epistemics.observations)
    begin_turn(state, "[confessional: I distrust Ann.]", 0)
    assert len(model.epistemics.observations) == before


def test_explicit_performance_completes_agreement_but_future_talk_does_not():
    from backend.app.engine.world_model.agreements import propose, decide
    from backend.app.engine.world_model.commitments import complete_actions

    model = make_model({"ann": "kitchen"})
    agreement = propose(model.agreements, "player", "ann", "cook dinner together", 60, 0)
    decide(model.agreements, agreement.id, "ann", "accepted", 1)
    model.world.minute = 60
    assert complete_actions(model, "I plan to cook dinner with Ann.", []) == []
    assert agreement.status == "accepted"
    completed = complete_actions(model, "I cook dinner with Ann.", [])
    assert completed == [agreement.id]
    assert agreement.status == "completed"
    assert complete_actions(model, "I cook dinner with Ann.", []) == []


def test_npc_promise_requires_own_action_not_player_prediction():
    from backend.app.engine.world_model.commitments import add_commitment, complete_actions

    model = make_model({"ann": "kitchen"})
    add_commitment(model, "ann", "player", "cook dinner", 60, 0)
    model.world.minute = 60
    assert complete_actions(model, "Ann will cook dinner for me.", []) == []
    assert complete_actions(model, "", [{"kind": "dialogue", "speaker_id": "ann",
                                          "text": "I cooked dinner for you."}]) == []
    assert {m.status for m in model.memories.open_promises()} == {"open"}


def test_expired_agreement_creates_one_causal_conflict_not_fake_fulfillment():
    from backend.app.engine.world_model.commitments import add_commitment, expire_commitments

    model = make_model({"ann": "kitchen"})
    add_commitment(model, "ann", "player", "cook dinner", 60, 0)
    expired = expire_commitments(model, 60 + 12 * 60)
    assert {m.status for m in expired} == {"expired"}
    assert model.agreements.get("A1").status == "expired"
    assert len(model.drama.threads) == 1


def test_accepted_plan_without_legacy_promise_memory_expires_once():
    from backend.app.engine.world_model.agreements import propose, decide
    from backend.app.engine.world_model.commitments import expire_commitments

    model = make_model({"ann": "kitchen", "ben": "kitchen"})
    plan = propose(model.agreements, "ann", "ben", "spend time together", 60, 0)
    decide(model.agreements, plan.id, "ben", "accepted", 1)
    assert expire_commitments(model, 60 + 12 * 60) == []
    assert plan.status == "expired"
    assert [event.kind for event in model.world.events] == ["agreement_expired"]
    assert expire_commitments(model, 60 + 12 * 60 + 1) == []
    assert len(model.world.events) == 1
    assert model.drama.threads[0].cause_event_id == model.world.events[-1].id
    assert expire_commitments(model, 60 + 12 * 60 + 1) == []
    assert len(model.drama.threads) == 1


def test_conflict_repair_needs_apology_and_other_persons_acceptance():
    from backend.app.engine.world_model.drama import register_conflict, record_repair_dialogue

    model = make_model({"ann": "kitchen"})
    thread = register_conflict(model.drama, ("player", "ann"), "E-expired", 0,
                               "Their dinner plan went unfulfilled")
    assert record_repair_dialogue(model, "I'm sorry I missed our dinner plan.", []) == []
    assert thread.stage == "apology_offered"
    assert record_repair_dialogue(model, "I already apologized.", [
        {"kind": "dialogue", "speaker_id": "ann", "text": "I forgive you."}]) == [thread.id]
    assert thread.stage == "resolved" and thread.resolution_event_id


def test_narrated_or_absent_forgiveness_does_not_resolve():
    from backend.app.engine.world_model.drama import register_conflict, record_repair_dialogue

    model = make_model({"ann": "outside"})
    thread = register_conflict(model.drama, ("player", "ann"), "E-expired", 0,
                               "Their dinner plan went unfulfilled")
    record_repair_dialogue(model, "I'm sorry I missed our dinner plan.", [
        {"kind": "narration", "speaker_id": None, "text": "Ann forgives you."}])
    assert thread.stage == "unresolved"
