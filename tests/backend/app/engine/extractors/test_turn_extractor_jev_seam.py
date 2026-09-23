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
