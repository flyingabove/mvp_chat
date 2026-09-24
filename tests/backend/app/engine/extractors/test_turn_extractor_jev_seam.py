"""Tests for TurnExtractor's Jev integration seam (step 3 of
JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §12): _build_batches,
_apply_decision_overrides, _call_legacy_raw, and extract()'s orchestration.

The pre-existing test_turn_extractor.py continues to cover _parse_json /
_parse_dict's validation logic directly and unmodified — this file covers
only what step 3 ADDED.
"""
import pytest

from backend.app.engine.extractors.turn_extractor import TurnExtractor, TurnExtraction
from backend.app.llm.decisions.types import (
    Criticality, DecisionAnswer, DecisionOutcome, Provider,
)
from backend.app.llm.protocols import LegacyExtractionRequest


class _FakeResolver:
    """Records the batches/request it was called with; returns a scripted
    DecisionOutcome."""
    def __init__(self, outcome: DecisionOutcome):
        self.outcome = outcome
        self.calls = []

    async def resolve(self, batches, legacy_request):
        self.calls.append((batches, legacy_request))
        return self.outcome


def _extractor_with_fake_resolver(outcome: DecisionOutcome) -> tuple[TurnExtractor, _FakeResolver]:
    resolver = _FakeResolver(outcome)
    ex = TurnExtractor(resolver=resolver)
    return ex, resolver


def _default_outcome(**overrides) -> DecisionOutcome:
    defaults = dict(
        answers={}, legacy_raw=None, provider_used=Provider.LEGACY_LLM,
        jev_latency_ms=None, legacy_latency_ms=None, jev_usage=None,
        fallback_reasons={}, shadow_disagreements={},
    )
    defaults.update(overrides)
    return DecisionOutcome(**defaults)


# --- _build_batches -----------------------------------------------------

def test_build_batches_current_message_always_present():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    batches = ex._build_batches(user_msg="hello", world_locations={"kitchen": "Kitchen"}, previous_turn_assistant_reply="")
    names = [b.name for b in batches]
    assert "current_message" in names
    current = next(b for b in batches if b.name == "current_message")
    decision_ids = {d.id for d in current.decisions}
    assert decision_ids == {"movement_intent", "movement_destination"}


def test_build_batches_previous_reply_only_when_non_empty():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    no_prev = ex._build_batches(user_msg="hi", world_locations={}, previous_turn_assistant_reply="")
    assert not any(b.name == "previous_reply" for b in no_prev)

    with_prev = ex._build_batches(user_msg="hi", world_locations={"kitchen": "Kitchen"}, previous_turn_assistant_reply="Makoto waves.")
    prev_batch = next(b for b in with_prev if b.name == "previous_reply")
    assert {d.id for d in prev_batch.decisions} == {"prev_scene_location"}
    assert "Makoto waves." in prev_batch.state


def test_build_batches_current_message_state_includes_user_msg():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    batches = ex._build_batches(user_msg="I walk to the terrace.", world_locations={}, previous_turn_assistant_reply="")
    current = next(b for b in batches if b.name == "current_message")
    assert "I walk to the terrace." in current.state


# --- _apply_decision_overrides -------------------------------------------

def _base_extraction(**overrides) -> TurnExtraction:
    defaults = dict(movement_intent="NONE", destination_id="", confidence=0.0, previous_reply_location_id="")
    defaults.update(overrides)
    return TurnExtraction(**defaults)


def test_apply_overrides_noop_when_no_jev_answers():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="NONE")
    outcome = _default_outcome(answers={})
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.movement_intent == "NONE"
    assert result is not base  # dataclasses.replace always returns a new instance
    assert result == base  # but with identical field values


def test_apply_overrides_uses_jev_movement_intent_when_provider_is_jev():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="NONE", confidence=0.0)
    outcome = _default_outcome(answers={
        "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.JEV, choice="MOVE", confidence=0.95),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.movement_intent == "MOVE"
    assert result.confidence == 0.95


def test_apply_overrides_ignores_legacy_provider_answer_shadow_mode():
    """Shadow mode: the resolver already returned the LEGACY value with
    provider=LEGACY_LLM even for a decision that was shadow-tested against
    Jev - the assembler must not treat this as a Jev override (it already
    matches `base`, since base was built from the same legacy_raw)."""
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="NONE")
    outcome = _default_outcome(answers={
        "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.LEGACY_LLM, choice="MOVE"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.movement_intent == "NONE", "a LEGACY_LLM-provider answer must not override base"


def test_apply_overrides_unusable_jev_answer_does_not_override():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="NONE")
    outcome = _default_outcome(answers={
        "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.JEV,
                                           choice="MOVE", fallback_reason=__import__(
                                               "backend.app.llm.decisions.types", fromlist=["FallbackReason"]
                                           ).FallbackReason.BELOW_THRESHOLD),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.movement_intent == "NONE", "an unusable Jev answer (even with a choice set) must not override"


def test_apply_overrides_destination_in_allowed_set_is_applied():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(destination_id="")
    outcome = _default_outcome(answers={
        "movement_destination": DecisionAnswer(decision_id="movement_destination", provider=Provider.JEV, choice="terrace"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids={"terrace", "kitchen"})
    assert result.destination_id == "terrace"


def test_apply_overrides_none_of_these_coerces_intent_to_none():
    """Existing invariant, retained: an unreachable/none destination
    coerces intent back to NONE, matching _parse_dict's own rule."""
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="MOVE", destination_id="kitchen")
    outcome = _default_outcome(answers={
        "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.JEV, choice="MOVE"),
        "movement_destination": DecisionAnswer(decision_id="movement_destination", provider=Provider.JEV, choice="none_of_these"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids={"kitchen"})
    assert result.destination_id == ""
    assert result.movement_intent == "NONE"


def test_apply_overrides_destination_not_in_allowed_set_coerces_to_none():
    """Defense in depth: even if a resolver bug let an out-of-range choice
    through, the existing allowed_location_ids re-check still catches it -
    Jev choosing something does not make it legal (design doc §9 invariant)."""
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(movement_intent="MOVE", destination_id="kitchen")
    outcome = _default_outcome(answers={
        "movement_destination": DecisionAnswer(decision_id="movement_destination", provider=Provider.JEV, choice="nonexistent_room"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids={"kitchen"})
    assert result.destination_id == ""
    assert result.movement_intent == "NONE"


def test_apply_overrides_prev_scene_location():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = _base_extraction(previous_reply_location_id="")
    outcome = _default_outcome(answers={
        "prev_scene_location": DecisionAnswer(decision_id="prev_scene_location", provider=Provider.JEV, choice="living_room"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids={"living_room"})
    assert result.previous_reply_location_id == "living_room"


def test_apply_overrides_preserves_untouched_fields():
    """The 9 fields Jev doesn't cover must pass through completely
    untouched - this is the whole point of building `base` from the full
    legacy parse first."""
    from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(
        movement_intent="NONE", destination_id="",
        behavior_tags=[BehaviorTagUpdate(from_id="player", to_id="makoto", tag="warm")],
    )
    outcome = _default_outcome(answers={
        "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.JEV, choice="MOVE"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.behavior_tags == base.behavior_tags


# --- extract() orchestration: the "legacy_raw is None" fallback ----------

@pytest.mark.asyncio
async def test_extract_falls_back_to_legacy_invoke_when_outcome_legacy_raw_is_none():
    """The concrete scenario this branch exists for: all 3 registered
    decisions succeed via Jev, so the resolver never needed to call
    legacy (legacy_raw=None) - but the other 9 TurnExtraction fields still
    need SOME source. extract() must notice and call legacy_request.invoke()
    itself."""
    outcome = _default_outcome(
        legacy_raw=None,
        answers={
            "movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.JEV, choice="MOVE"),
        },
        provider_used=Provider.JEV,
    )
    ex, resolver = _extractor_with_fake_resolver(outcome)

    invoke_calls = {"n": 0}
    async def fake_call_legacy_raw(request):
        invoke_calls["n"] += 1
        return {"movement": {"intent": "NONE"}, "behavior_tags": [{"from_id": "player", "to_id": "makoto", "tag": "warm"}]}
    ex._call_legacy_raw = fake_call_legacy_raw

    result = await ex.extract(
        user_msg="I walk to the terrace.", world_locations={"terrace": "Terrace"}, character_key_to_name={"makoto": "Makoto"},
    )

    assert invoke_calls["n"] == 1, "legacy must be called once to fill the 9 non-Jev fields"
    assert result.movement_intent == "MOVE", "the Jev answer must still win for the registered ability"
    assert len(result.behavior_tags) == 1, "the legacy-sourced field must be populated from the fallback invoke"
    assert result.behavior_tags[0].tag == "warm"


@pytest.mark.asyncio
async def test_extract_does_not_double_call_legacy_when_resolver_already_did():
    """The common case: resolver already called legacy (e.g. because
    movement_destination also needed it, or because no task is enabled) -
    extract() must use outcome.legacy_raw directly, NOT call invoke() again."""
    outcome = _default_outcome(
        legacy_raw={"movement": {"intent": "NONE"}},
        answers={"movement_intent": DecisionAnswer(decision_id="movement_intent", provider=Provider.LEGACY_LLM, choice="NONE")},
        provider_used=Provider.LEGACY_LLM,
    )
    ex, resolver = _extractor_with_fake_resolver(outcome)

    invoke_calls = {"n": 0}
    async def fake_call_legacy_raw(request):
        invoke_calls["n"] += 1
        return {"movement": {"intent": "SHOULD_NOT_BE_USED"}}
    ex._call_legacy_raw = fake_call_legacy_raw

    result = await ex.extract(user_msg="hi", world_locations={}, character_key_to_name={})

    assert invoke_calls["n"] == 0, "legacy must not be called a second time - outcome.legacy_raw already had it"
    assert result.movement_intent == "NONE"


@pytest.mark.asyncio
async def test_extract_passes_the_same_legacy_request_object_the_resolver_received():
    """Sanity check that the batch/legacy_request plumbing actually
    connects extract() to the resolver correctly."""
    outcome = _default_outcome(legacy_raw={"movement": {"intent": "NONE"}})
    ex, resolver = _extractor_with_fake_resolver(outcome)
    ex._call_legacy_raw = lambda request: _default_outcome().legacy_raw  # unused in this path

    await ex.extract(
        user_msg="test message", world_locations={"kitchen": "Kitchen"}, character_key_to_name={"makoto": "Makoto"},
        previous_turn_user_msg="earlier", previous_turn_assistant_reply="Makoto nods.",
    )

    assert len(resolver.calls) == 1
    batches, legacy_request = resolver.calls[0]
    assert isinstance(legacy_request, LegacyExtractionRequest)
    assert legacy_request.user_msg == "test message"
    assert legacy_request.previous_turn_assistant_reply == "Makoto nods."
    batch_names = {b.name for b in batches}
    assert "current_message" in batch_names
    assert "previous_reply" in batch_names  # non-empty previous_turn_assistant_reply triggers this batch


# --- _call_legacy_raw: mocked transport --------------------------------

@pytest.mark.asyncio
async def test_call_legacy_raw_returns_parsed_dict_on_success(monkeypatch):
    from backend.app.llm.providers.openai_chat import OpenAIChatClient
    from backend.app.llm.protocols import TextResult

    async def fake_generate(self, *, model, system, messages, max_tokens, temperature):
        return TextResult(text='{"movement": {"intent": "MOVE"}}', model="gpt-4o-mini", usage={})

    monkeypatch.setattr(OpenAIChatClient, "generate", fake_generate)
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    req = LegacyExtractionRequest(user_msg="x", world_locations={}, character_key_to_name={})

    result = await ex._call_legacy_raw(req)
    assert result == {"movement": {"intent": "MOVE"}}


@pytest.mark.asyncio
async def test_call_legacy_raw_returns_none_on_transport_exception(monkeypatch):
    from backend.app.llm.providers.openai_chat import OpenAIChatClient

    async def fake_generate(self, *, model, system, messages, max_tokens, temperature):
        raise RuntimeError("network down")

    monkeypatch.setattr(OpenAIChatClient, "generate", fake_generate)
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    req = LegacyExtractionRequest(user_msg="x", world_locations={}, character_key_to_name={})

    result = await ex._call_legacy_raw(req)
    assert result is None


@pytest.mark.asyncio
async def test_call_legacy_raw_returns_none_on_invalid_json(monkeypatch):
    from backend.app.llm.providers.openai_chat import OpenAIChatClient
    from backend.app.llm.protocols import TextResult

    async def fake_generate(self, *, model, system, messages, max_tokens, temperature):
        return TextResult(text="not valid json", model="gpt-4o-mini", usage={})

    monkeypatch.setattr(OpenAIChatClient, "generate", fake_generate)
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    req = LegacyExtractionRequest(user_msg="x", world_locations={}, character_key_to_name={})

    result = await ex._call_legacy_raw(req)
    assert result is None


@pytest.mark.asyncio
async def test_call_legacy_raw_returns_none_on_non_dict_json(monkeypatch):
    from backend.app.llm.providers.openai_chat import OpenAIChatClient
    from backend.app.llm.protocols import TextResult

    async def fake_generate(self, *, model, system, messages, max_tokens, temperature):
        return TextResult(text="[1, 2, 3]", model="gpt-4o-mini", usage={})

    monkeypatch.setattr(OpenAIChatClient, "generate", fake_generate)
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    req = LegacyExtractionRequest(user_msg="x", world_locations={}, character_key_to_name={})

    result = await ex._call_legacy_raw(req)
    assert result is None


# --- _build_batches: knowledge + departure fan-outs (step 6) ------------

def test_build_batches_knowledge_batch_only_when_candidates_present():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    no_chunks = ex._build_batches(user_msg="hi", world_locations={}, previous_turn_assistant_reply="")
    assert not any(b.name == "knowledge" for b in no_chunks)

    with_chunks = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        previous_turn_candidate_chunks=[{"chunk_id": "c1", "text": "Makoto's secret."}],
    )
    kb = next(b for b in with_chunks if b.name == "knowledge")
    assert {d.id for d in kb.decisions} == {"knows_c1"}


def test_build_batches_departure_batch_only_when_residents_present():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    no_residents = ex._build_batches(user_msg="hi", world_locations={}, previous_turn_assistant_reply="")
    assert not any(b.name == "departure_check" for b in no_residents)

    with_residents = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        character_key_to_name={"makoto": "Makoto", "player": "You"},
    )
    dep = next(b for b in with_residents if b.name == "departure_check")
    assert {d.id for d in dep.decisions} == {"departure_makoto"}, "player must be excluded from departure fan-out"


# --- _apply_decision_overrides: knowledge fan-out ------------------------

def test_apply_overrides_knowledge_jev_answer_overrides_matching_chunk():
    from backend.app.engine.extractors.turn_extractor import TurnKnowledgeResolution
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(knowledge_updates=[TurnKnowledgeResolution(chunk_id="c1", knows=False, confidence=0.2)])
    outcome = _default_outcome(answers={
        "knows_c1": DecisionAnswer(decision_id="knows_c1", provider=Provider.JEV, probability=0.91),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert len(result.knowledge_updates) == 1
    assert result.knowledge_updates[0].knows is True
    assert result.knowledge_updates[0].confidence == 0.91


def test_apply_overrides_knowledge_jev_answer_below_threshold_is_knows_false():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(knowledge_updates=[])
    outcome = _default_outcome(answers={
        "knows_c1": DecisionAnswer(decision_id="knows_c1", provider=Provider.JEV, probability=0.1),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.knowledge_updates[0].knows is False


def test_apply_overrides_knowledge_unusable_jev_answer_leaves_legacy_value():
    from backend.app.engine.extractors.turn_extractor import TurnKnowledgeResolution
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(knowledge_updates=[TurnKnowledgeResolution(chunk_id="c1", knows=True, confidence=0.8)])
    from backend.app.llm.decisions.types import FallbackReason
    outcome = _default_outcome(answers={
        "knows_c1": DecisionAnswer(decision_id="knows_c1", provider=Provider.JEV, probability=0.1,
                                    fallback_reason=FallbackReason.BELOW_THRESHOLD),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.knowledge_updates[0].knows is True, "unusable answer must not override legacy value"


def test_apply_overrides_knowledge_preserves_chunks_jev_never_answered():
    from backend.app.engine.extractors.turn_extractor import TurnKnowledgeResolution
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(knowledge_updates=[
        TurnKnowledgeResolution(chunk_id="c1", knows=True, confidence=0.9),
        TurnKnowledgeResolution(chunk_id="c2", knows=False, confidence=0.4),
    ])
    outcome = _default_outcome(answers={
        "knows_c1": DecisionAnswer(decision_id="knows_c1", provider=Provider.JEV, probability=0.95),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    ids = {u.chunk_id for u in result.knowledge_updates}
    assert ids == {"c1", "c2"}
    c2 = next(u for u in result.knowledge_updates if u.chunk_id == "c2")
    assert c2.knows is False and c2.confidence == 0.4


# --- _apply_decision_overrides: departure fan-out -------------------------

def test_apply_overrides_departure_jev_full_coverage_no_signal_is_none():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(departure_signal=None)
    outcome = _default_outcome(answers={
        "departure_makoto": DecisionAnswer(decision_id="departure_makoto", provider=Provider.JEV, choice="NONE"),
        "departure_mizuki": DecisionAnswer(decision_id="departure_mizuki", provider=Provider.JEV, choice="NONE"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.departure_signal is None


def test_apply_overrides_departure_jev_finds_the_signaling_resident():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(departure_signal=None)
    outcome = _default_outcome(answers={
        "departure_makoto": DecisionAnswer(decision_id="departure_makoto", provider=Provider.JEV, choice="NONE"),
        "departure_mizuki": DecisionAnswer(decision_id="departure_mizuki", provider=Provider.JEV, choice="DECISION"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.departure_signal is not None
    assert result.departure_signal.character_id == "mizuki"
    assert result.departure_signal.certainty == "DECISION"


def test_apply_overrides_departure_no_jev_answers_leaves_legacy_signal():
    from backend.app.engine.extractors.turn_extractor import DepartureSignal
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(departure_signal=DepartureSignal(character_id="makoto", certainty="WISH", reason="joked"))
    outcome = _default_outcome(answers={})
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.departure_signal == base.departure_signal


# --- extract() orchestration: fan-outs wired end to end -------------------

@pytest.mark.asyncio
async def test_extract_wires_candidate_chunks_and_characters_into_batches():
    outcome = _default_outcome(legacy_raw={"movement": {"intent": "NONE"}})
    ex, resolver = _extractor_with_fake_resolver(outcome)

    await ex.extract(
        user_msg="hi", world_locations={}, character_key_to_name={"makoto": "Makoto"},
        previous_turn_candidate_chunks=[{"chunk_id": "c1", "text": "a fact"}],
    )

    batches, _ = resolver.calls[0]
    batch_names = {b.name for b in batches}
    assert "knowledge" in batch_names
    assert "departure_check" in batch_names


# --- _build_batches: rel_state + rel_history fan-outs (step 7) -----------

def test_build_batches_rel_state_batch_dimensions_x_targets():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    batches = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        character_key_to_name={"makoto": "Makoto", "player": "You"},
    )
    rs = next(b for b in batches if b.name == "rel_state")
    ids = {d.id for d in rs.decisions}
    assert ids == {
        "relstate_trust_makoto", "relstate_affection_makoto", "relstate_fear_makoto",
        "relstate_suspicion_makoto", "relstate_jealousy_makoto",
    }


def test_build_batches_rel_history_batch_fields_x_targets():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    batches = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        character_key_to_name={"makoto": "Makoto"},
    )
    rh = next(b for b in batches if b.name == "rel_history")
    ids = {d.id for d in rh.decisions}
    assert ids == {
        "relhist_prior_relationship_makoto", "relhist_prior_intimacy_makoto", "relhist_in_relationship_makoto",
    }


# --- _apply_decision_overrides: rel_state fan-out -------------------------

def test_apply_overrides_rel_state_jev_score_overrides_one_dimension():
    from backend.app.engine.extractors.turn_extractor import RelationshipStateUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(relationship_state_updates=[
        RelationshipStateUpdate(from_id="player", to_id="makoto", trust_delta=0.05, reason="legacy"),
    ])
    outcome = _default_outcome(answers={
        "relstate_trust_makoto": DecisionAnswer(decision_id="relstate_trust_makoto", provider=Provider.JEV, score=1.0),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert len(result.relationship_state_updates) == 1
    u = result.relationship_state_updates[0]
    assert u.to_id == "makoto"
    assert round(u.trust_delta, 4) == 0.10, "score=1.0 (max positive) must map to +max_abs"
    assert u.reason == "legacy", "untouched fields (reason) must be preserved from the legacy entry"


def test_apply_overrides_rel_state_all_neutral_omits_entry():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(relationship_state_updates=[])
    outcome = _default_outcome(answers={
        "relstate_trust_makoto": DecisionAnswer(decision_id="relstate_trust_makoto", provider=Provider.JEV, score=0.5),
        "relstate_affection_makoto": DecisionAnswer(decision_id="relstate_affection_makoto", provider=Provider.JEV, score=0.5),
        "relstate_fear_makoto": DecisionAnswer(decision_id="relstate_fear_makoto", provider=Provider.JEV, score=0.0),
        "relstate_suspicion_makoto": DecisionAnswer(decision_id="relstate_suspicion_makoto", provider=Provider.JEV, score=0.0),
        "relstate_jealousy_makoto": DecisionAnswer(decision_id="relstate_jealousy_makoto", provider=Provider.JEV, score=0.0),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.relationship_state_updates == [], "an all-neutral target must be omitted, matching legacy's own rule"


def test_apply_overrides_rel_state_no_jev_answers_leaves_legacy_untouched():
    from backend.app.engine.extractors.turn_extractor import RelationshipStateUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(relationship_state_updates=[
        RelationshipStateUpdate(from_id="player", to_id="makoto", trust_delta=0.08),
    ])
    result = ex._apply_decision_overrides(base, _default_outcome(answers={}), allowed_location_ids=set())
    assert result.relationship_state_updates == base.relationship_state_updates


# --- _apply_decision_overrides: rel_history fan-out -----------------------

def test_apply_overrides_rel_history_jev_confirms_one_field():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(relationship_history_updates=[])
    outcome = _default_outcome(answers={
        "relhist_in_relationship_makoto": DecisionAnswer(
            decision_id="relhist_in_relationship_makoto", provider=Provider.JEV, probability=0.9),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert len(result.relationship_history_updates) == 1
    u = result.relationship_history_updates[0]
    assert u.to_id == "makoto"
    assert u.in_relationship is True
    assert u.prior_relationship is None
    assert u.prior_intimacy is None


def test_apply_overrides_rel_history_all_unconfirmed_omits_entry():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(relationship_history_updates=[])
    outcome = _default_outcome(answers={
        "relhist_in_relationship_makoto": DecisionAnswer(
            decision_id="relhist_in_relationship_makoto", provider=Provider.JEV, probability=None),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.relationship_history_updates == []


# --- _build_batches: behavior_tag + social_shift (step 8/9) --------------

def test_build_batches_behavior_tag_batch_gated_on_vocabulary():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    no_vocab = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        character_key_to_name={"makoto": "Makoto", "mizuki": "Mizuki"},
    )
    assert not any(b.name == "behavior_tag" for b in no_vocab), "no vocabulary -> no behavior_tag batch at all"

    with_vocab = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        character_key_to_name={"makoto": "Makoto", "mizuki": "Mizuki"},
        allowed_behavior_tags=["warm", "evasive"],
    )
    bt = next(b for b in with_vocab if b.name == "behavior_tag")
    ids = {d.id for d in bt.decisions}
    assert ids == {"behtag_makoto_mizuki", "behtag_mizuki_makoto"}, "every ordered pair, self-pairs excluded"


def test_build_batches_social_shift_batch_gated_on_behavior_window():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    no_window = ex._build_batches(user_msg="hi", world_locations={}, previous_turn_assistant_reply="")
    assert not any(b.name == "social_shift" for b in no_window)

    with_window = ex._build_batches(
        user_msg="hi", world_locations={}, previous_turn_assistant_reply="",
        behavior_window={"pair": "makoto->mizuki", "tags": ["warm", "warm", "evasive"]},
    )
    ss = next(b for b in with_window if b.name == "social_shift")
    assert {d.id for d in ss.decisions} == {"social_shift_certainty"}


# --- _apply_decision_overrides: behavior_tag fan-out ----------------------

def test_apply_overrides_behavior_tag_jev_answer_overrides_pair():
    from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(behavior_tags=[BehaviorTagUpdate(from_id="makoto", to_id="mizuki", tag="aggressive")])
    outcome = _default_outcome(answers={
        "behtag_makoto_mizuki": DecisionAnswer(decision_id="behtag_makoto_mizuki", provider=Provider.JEV, choice="warm"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert len(result.behavior_tags) == 1
    assert result.behavior_tags[0].tag == "warm"


def test_apply_overrides_behavior_tag_jev_none_removes_stale_legacy_tag():
    """A usable Jev NONE is itself an answer for that pair - it must not
    leave a stale legacy tag in place."""
    from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(behavior_tags=[BehaviorTagUpdate(from_id="makoto", to_id="mizuki", tag="aggressive")])
    outcome = _default_outcome(answers={
        "behtag_makoto_mizuki": DecisionAnswer(decision_id="behtag_makoto_mizuki", provider=Provider.JEV, choice="NONE"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    assert result.behavior_tags == []


def test_apply_overrides_behavior_tag_preserves_pairs_jev_never_answered():
    from backend.app.engine.extractors.turn_extractor import BehaviorTagUpdate
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(behavior_tags=[
        BehaviorTagUpdate(from_id="makoto", to_id="mizuki", tag="aggressive"),
        BehaviorTagUpdate(from_id="player", to_id="makoto", tag="warm"),
    ])
    outcome = _default_outcome(answers={
        "behtag_makoto_mizuki": DecisionAnswer(decision_id="behtag_makoto_mizuki", provider=Provider.JEV, choice="evasive"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set())
    pairs = {(u.from_id, u.to_id): u.tag for u in result.behavior_tags}
    assert pairs == {("makoto", "mizuki"): "evasive", ("player", "makoto"): "warm"}


# --- _apply_decision_overrides: social_shift ------------------------------

def test_apply_overrides_social_shift_jev_none_clears_signal():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(social_shift_signal=None)
    outcome = _default_outcome(answers={
        "social_shift_certainty": DecisionAnswer(decision_id="social_shift_certainty", provider=Provider.JEV, choice="NONE"),
    })
    result = ex._apply_decision_overrides(
        base, outcome, allowed_location_ids=set(),
        behavior_window={"pair": "makoto->mizuki", "tags": ["warm"]},
    )
    assert result.social_shift_signal is None


def test_apply_overrides_social_shift_jev_wish_applies_without_new_value():
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(social_shift_signal=None)
    outcome = _default_outcome(answers={
        "social_shift_certainty": DecisionAnswer(decision_id="social_shift_certainty", provider=Provider.JEV, choice="WISH"),
    })
    result = ex._apply_decision_overrides(
        base, outcome, allowed_location_ids=set(),
        behavior_window={"pair": "makoto->mizuki", "tags": ["warm"]},
    )
    assert result.social_shift_signal is not None
    assert result.social_shift_signal.certainty == "WISH"
    assert result.social_shift_signal.subject_id == "makoto"
    assert result.social_shift_signal.target_id == "mizuki"


def test_apply_overrides_social_shift_jev_shift_uses_legacy_new_value_when_corroborated():
    from backend.app.engine.extractors.turn_extractor import SocialShiftSignal
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(social_shift_signal=SocialShiftSignal(
        certainty="SHIFT", scope="disposition", subject_id="makoto", target_id="mizuki",
        new_value="grown distant", reason="legacy reason",
    ))
    outcome = _default_outcome(answers={
        "social_shift_certainty": DecisionAnswer(decision_id="social_shift_certainty", provider=Provider.JEV, choice="SHIFT"),
    })
    result = ex._apply_decision_overrides(
        base, outcome, allowed_location_ids=set(),
        behavior_window={"pair": "makoto->mizuki", "tags": ["warm"]},
    )
    assert result.social_shift_signal.certainty == "SHIFT"
    assert result.social_shift_signal.new_value == "grown distant"


def test_apply_overrides_social_shift_jev_shift_without_legacy_corroboration_keeps_base():
    """Jev says SHIFT but legacy's own social_shift_signal didn't produce a
    matching, non-empty new_value for this pair - must NOT fabricate a
    SHIFT with no description; falls back to whatever base already was."""
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(social_shift_signal=None)  # legacy said NONE
    outcome = _default_outcome(answers={
        "social_shift_certainty": DecisionAnswer(decision_id="social_shift_certainty", provider=Provider.JEV, choice="SHIFT"),
    })
    result = ex._apply_decision_overrides(
        base, outcome, allowed_location_ids=set(),
        behavior_window={"pair": "makoto->mizuki", "tags": ["warm"]},
    )
    assert result.social_shift_signal is None, "must degrade to base rather than write an empty-new_value SHIFT"


def test_apply_overrides_social_shift_no_behavior_window_is_noop():
    from backend.app.engine.extractors.turn_extractor import SocialShiftSignal
    ex = TurnExtractor(resolver=_FakeResolver(_default_outcome()))
    base = TurnExtraction(social_shift_signal=SocialShiftSignal(
        certainty="WISH", scope="disposition", subject_id="makoto", target_id="mizuki",
    ))
    outcome = _default_outcome(answers={
        "social_shift_certainty": DecisionAnswer(decision_id="social_shift_certainty", provider=Provider.JEV, choice="NONE"),
    })
    result = ex._apply_decision_overrides(base, outcome, allowed_location_ids=set(), behavior_window=None)
    assert result.social_shift_signal == base.social_shift_signal, "no behavior_window -> no pair to match, no-op"


# --- _log_jev_outcome: shadow-mode/live telemetry visibility -------------

def test_log_jev_outcome_silent_when_jev_never_attempted(monkeypatch):
    """The default-off case (TYPESAFE_ENABLED=false, or a sparse turn with
    no registered decisions) must produce zero log volume."""
    from backend.app.llm.decisions.types import FallbackReason
    calls = []
    monkeypatch.setattr("backend.app.engine.extractors.turn_extractor.jlog", lambda e: calls.append(e))
    outcome = _default_outcome(provider_used=Provider.LEGACY_LLM, fallback_reasons={
        "movement_intent": FallbackReason.FLAG_DISABLED,
    })
    TurnExtractor._log_jev_outcome(outcome)
    assert calls == []


def test_log_jev_outcome_logs_when_provider_used_is_jev(monkeypatch):
    calls = []
    monkeypatch.setattr("backend.app.engine.extractors.turn_extractor.jlog", lambda e: calls.append(e))
    outcome = _default_outcome(provider_used=Provider.JEV, jev_latency_ms=180.0, jev_usage={"input_tokens": 50})
    TurnExtractor._log_jev_outcome(outcome)
    assert len(calls) == 1
    assert calls[0]["kind"] == "jev_turn_outcome"
    assert calls[0]["provider_used"] == "jev"
    assert calls[0]["jev_latency_ms"] == 180.0


def test_log_jev_outcome_logs_shadow_disagreements():
    """The actual comparison-data path: shadow mode ran, Jev and legacy
    disagreed on at least one decision - this must be visible in the log,
    not silently discarded (the gap this method exists to close)."""
    calls = []
    outcome = _default_outcome(
        provider_used=Provider.LEGACY_LLM,
        shadow_disagreements={"movement_intent": ("MOVE", "NONE")},
    )
    import backend.app.engine.extractors.turn_extractor as te_mod
    original_jlog = te_mod.jlog
    te_mod.jlog = lambda e: calls.append(e)
    try:
        TurnExtractor._log_jev_outcome(outcome)
    finally:
        te_mod.jlog = original_jlog
    assert len(calls) == 1
    assert calls[0]["shadow_disagreement_count"] == 1
    assert calls[0]["shadow_disagreements"]["movement_intent"] == ["MOVE", "NONE"]


def test_log_jev_outcome_never_raises_on_bad_data():
    """jlog itself already swallows exceptions (logging_utils.py), but this
    method's own try/except is the belt-and-suspenders guarantee that a
    telemetry call can never break a real turn."""
    class _Unserializable:
        def __repr__(self):
            raise RuntimeError("boom")
    outcome = _default_outcome(provider_used=Provider.JEV, jev_usage={"bad": _Unserializable()})
    TurnExtractor._log_jev_outcome(outcome)  # must not raise
