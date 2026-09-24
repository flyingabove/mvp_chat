"""Tests for the core decision contract (backend/app/llm/decisions/types.py).

These types are pure data — the tests exist to lock the exact contract from
JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §3, since every later step (the
resolver, the circuit breaker, the decision registry) depends on this shape
being exactly right.
"""
import pytest

from backend.app.llm.decisions.types import (
    Criticality, DecisionAnswer, DecisionBatch, DecisionOutcome,
    Decision, FallbackReason, Provider,
)


def test_criticality_has_exactly_two_values():
    """Only CRITICAL and DEGRADABLE — no third granularity was designed,
    and adding one silently would change resolve()'s fallback behavior
    without anyone noticing at the call site."""
    assert {c.value for c in Criticality} == {"critical", "degradable"}


def test_provider_has_exactly_three_values():
    assert {p.value for p in Provider} == {"jev", "legacy_llm", "default"}


def test_fallback_reason_none_means_usable():
    answer = DecisionAnswer(decision_id="q1", provider=Provider.JEV, choice="MOVE")
    assert answer.fallback_reason is FallbackReason.NONE
    assert answer.usable is True


@pytest.mark.parametrize("reason", [
    FallbackReason.TIMEOUT, FallbackReason.HTTP_ERROR, FallbackReason.MALFORMED_RESPONSE,
    FallbackReason.MISSING_ANSWER, FallbackReason.INVALID_OPTION, FallbackReason.BELOW_THRESHOLD,
    FallbackReason.CIRCUIT_OPEN, FallbackReason.FLAG_DISABLED, FallbackReason.SHADOW_MODE,
])
def test_any_non_none_fallback_reason_means_unusable(reason):
    answer = DecisionAnswer(decision_id="q1", provider=Provider.JEV, fallback_reason=reason)
    assert answer.usable is False


def test_decision_is_frozen_pure_data():
    """No I/O capability on this type — verified by immutability, which
    also means a Decision is safe to share across concurrent batches."""
    d = Decision(
        id="movement_intent", task="movement", kind="choice",
        instructions="...", criteria={"MOVE": "x", "NONE": "y"},
        criticality=Criticality.CRITICAL,
    )
    with pytest.raises(Exception):
        d.id = "changed"  # frozen dataclass -> raises FrozenInstanceError


def test_decision_criteria_accepts_mapping_for_choice():
    d = Decision(id="q", task="t", kind="choice", instructions="i",
                 criteria={"a": "desc a", "b": "desc b"}, criticality=Criticality.DEGRADABLE)
    assert d.criteria == {"a": "desc a", "b": "desc b"}


def test_decision_criteria_accepts_sequence_for_score():
    """score's criteria is an ARRAY of level descriptions, not a map —
    verified against the live API shape in JEV_EXTRACTOR_REDESIGN's TC-11."""
    d = Decision(id="q", task="t", kind="score", instructions="i",
                 criteria=["low", "mid", "high"], criticality=Criticality.DEGRADABLE)
    assert d.criteria == ["low", "mid", "high"]


def test_decision_batch_groups_decisions_under_one_shared_state():
    batch = DecisionBatch(
        name="current_message", state="the shared state blob",
        decisions=(
            Decision(id="q1", task="t", kind="noul", instructions="i", criteria={}, criticality=Criticality.DEGRADABLE),
            Decision(id="q2", task="t", kind="noul", instructions="i", criteria={}, criticality=Criticality.DEGRADABLE),
        ),
    )
    assert len(batch.decisions) == 2
    assert batch.state == "the shared state blob"


def test_decision_outcome_carries_shadow_disagreements_separately_from_answers():
    """Shadow-mode answers must never be mistaken for the live answers used
    to mutate game state — kept in a clearly separate field."""
    outcome = DecisionOutcome(
        answers={"q1": DecisionAnswer(decision_id="q1", provider=Provider.LEGACY_LLM, choice="MOVE")},
        legacy_raw={"movement": {"intent": "MOVE"}},
        provider_used=Provider.LEGACY_LLM,
        jev_latency_ms=210.0,
        legacy_latency_ms=None,
        jev_usage={"input_tokens": 100, "output_tokens": 10},
        fallback_reasons={},
        shadow_disagreements={"q1": ("MOVE", "MOVE")},
    )
    assert outcome.answers["q1"].choice == "MOVE"
    assert outcome.shadow_disagreements["q1"] == ("MOVE", "MOVE")
