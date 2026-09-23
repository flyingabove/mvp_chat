"""Tests for backend/app/llm/protocols.py.

DecisionProvider/TextProvider are Protocols (structural typing) — the tests
here check that the concrete pieces built so far (LegacyExtractionRequest,
TextResult) actually satisfy the shapes the protocols require, and that a
minimal fake implementation is accepted without inheritance, which is the
whole point of using Protocol instead of an ABC.
"""
import pytest

from backend.app.llm.decisions.types import DecisionBatch, DecisionOutcome, Provider
from backend.app.llm.protocols import DecisionProvider, LegacyExtractionRequest, TextProvider, TextResult


def test_legacy_extraction_request_defaults_match_turn_extractor_optionals():
    """TurnExtractor.extract()'s optional kwargs (previous_turn_user_msg="",
    previous_turn_candidate_chunks=None, etc.) must have equivalent safe
    defaults here, since a batch builder that omits one of these fields
    should not need to pass every field explicitly."""
    req = LegacyExtractionRequest(
        user_msg="hello",
        world_locations={"kitchen": "Kitchen"},
        character_key_to_name={"makoto": "Makoto"},
    )
    assert req.previous_turn_user_msg == ""
    assert req.previous_turn_assistant_reply == ""
    assert req.previous_turn_candidate_chunks == ()
    assert req.conversation_log == ()
    assert req.behavior_window is None
    assert req.invoke is None


def test_text_result_carries_model_and_usage():
    result = TextResult(text="hello there", model="gpt-4o-mini-2024-07-18", usage={"prompt_tokens": 10})
    assert result.text == "hello there"
    assert result.usage["prompt_tokens"] == 10


@pytest.mark.asyncio
async def test_a_minimal_fake_satisfies_decision_provider_protocol_structurally():
    """No inheritance required — this is the point of Protocol over ABC:
    the resolver (built in a later step) can be swapped for any object
    with a matching resolve() method, including a test double."""

    class _FakeProvider:
        async def resolve(self, batches, legacy_request):
            return DecisionOutcome(
                answers={}, legacy_raw=None, provider_used=Provider.DEFAULT,
                jev_latency_ms=None, legacy_latency_ms=None, jev_usage=None,
                fallback_reasons={}, shadow_disagreements={},
            )

    provider: DecisionProvider = _FakeProvider()
    outcome = await provider.resolve([], LegacyExtractionRequest(user_msg="x", world_locations={}, character_key_to_name={}))
    assert outcome.provider_used is Provider.DEFAULT


@pytest.mark.asyncio
async def test_a_minimal_fake_satisfies_text_provider_protocol_structurally():
    class _FakeTextProvider:
        async def generate(self, *, model, system, messages, max_tokens, temperature):
            return TextResult(text="fake reply", model=model, usage={})

    provider: TextProvider = _FakeTextProvider()
    result = await provider.generate(model="m", system="s", messages=[], max_tokens=10, temperature=0.0)
    assert result.text == "fake reply"


def test_legacy_extraction_request_invoke_is_awaitable_callable():
    async def _invoke():
        return {"movement": {"intent": "MOVE"}}

    req = LegacyExtractionRequest(
        user_msg="x", world_locations={}, character_key_to_name={}, invoke=_invoke,
    )
    assert req.invoke is _invoke
