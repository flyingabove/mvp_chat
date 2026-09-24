"""Tests for backend/app/evaluation/judge.py: fail-closed validation, retry
policy and request shape (JEV_GAME_ARENA_DESIGN.md §3, §7, §10)."""
import pytest

from backend.app.evaluation.evidence import build_packet
from backend.app.evaluation.fakes import FakeJevClient, make_arm, tiny_bundle
from backend.app.evaluation.judge import (
    JevPairwiseJudge, build_decisions, cmp_id, probe_id, score_id, validate_answer,
)
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.llm.providers.base import ProviderHTTPError
from backend.app.llm.providers.jev import JevRawAnswer


def packet():
    b = tiny_bundle()
    return build_packet(b, make_arm("beta", ["Mina smiles."]), make_arm("prod", ["Jun nods."]), 0, 4)


def decision(qid):
    return next(d for d in build_decisions(DEFAULT_RUBRIC, packet()) if d.id == qid)


def test_every_dimension_gets_cmp_scores_evidence_and_probes_for_both_sides():
    ids = {d.id for d in build_decisions(DEFAULT_RUBRIC, packet())}
    for dim in DEFAULT_RUBRIC.dimensions:
        assert {cmp_id(dim.id), score_id("A", dim.id), score_id("B", dim.id), f"ev_{dim.id}"} <= ids
    for probe in DEFAULT_RUBRIC.critical_probes:
        assert {probe_id("A", probe.id), probe_id("B", probe.id)} <= ids


def test_noul_criteria_is_a_true_false_map():
    """The live API rejects list criteria for noul with HTTP 422 (verified
    2026-09-23)."""
    d = decision(probe_id("A", "secret_leak"))
    assert set(d.criteria) == {"true", "false"}


def test_choice_criteria_include_tie_and_insufficient_evidence():
    d = decision(cmp_id("canon"))
    assert set(d.criteria) == {"A", "B", "tie", "insufficient_evidence"}


@pytest.mark.parametrize("raw,reason", [
    (None, "missing_answer"),
    (JevRawAnswer(kind="score", score=2.0), "wrong_kind:score"),
    (JevRawAnswer(kind="choice", choice="C", probabilities={"C": 1.0}), "invalid_option:C"),
    (JevRawAnswer(kind="choice", choice="A", probabilities={}), "missing_distribution"),
    (JevRawAnswer(kind="choice", choice="A", probabilities={"A": 0.5, "Z": 0.5}), "bad_distribution"),
    (JevRawAnswer(kind="choice", choice="A", probabilities={"A": 0.5, "B": 0.1}), "distribution_not_normalized"),
])
def test_malformed_choice_answers_fail_closed(raw, reason):
    ans = validate_answer(decision(cmp_id("canon")), raw)
    assert not ans.valid
    assert ans.reason == reason


def test_valid_choice_keeps_full_distribution():
    probs = {"A": 0.7, "B": 0.2, "tie": 0.08, "insufficient_evidence": 0.02}
    ans = validate_answer(decision(cmp_id("canon")),
                          JevRawAnswer(kind="choice", choice="A", confidence=0.7, probabilities=probs))
    assert ans.valid and ans.probabilities == probs


def test_score_out_of_band_range_fails_closed():
    d = decision(score_id("A", "canon"))
    assert not validate_answer(d, JevRawAnswer(kind="score", score=4.5)).valid
    assert validate_answer(d, JevRawAnswer(kind="score", score=3.68)).valid


def test_noul_probability_must_be_in_unit_interval():
    d = decision(probe_id("A", "secret_leak"))
    assert not validate_answer(d, JevRawAnswer(kind="noul", probability=1.2)).valid
    assert validate_answer(d, JevRawAnswer(kind="noul", probability=0.3)).valid


@pytest.mark.asyncio
async def test_transient_failure_is_retried_on_the_same_input():
    client = FakeJevClient(fail_times=1)
    judge = JevPairwiseJudge(client, DEFAULT_RUBRIC, backoff_s=0)
    call = await judge.judge(packet(), orientation="beta_as_A")
    assert call.attempts == 2 and not call.error
    assert client.calls[0].state == client.calls[1].state   # same stored input


@pytest.mark.asyncio
async def test_schema_errors_are_not_retried():
    class Rejecting:
        calls = 0

        async def ask(self, batch, *, timeout_ms):
            Rejecting.calls += 1
            raise ProviderHTTPError(422, "bad schema")

    call = await JevPairwiseJudge(Rejecting(), DEFAULT_RUBRIC, backoff_s=0).judge(packet(), orientation="beta_as_A")
    assert Rejecting.calls == 1
    assert call.failed and "422" in call.error


@pytest.mark.asyncio
async def test_exhausted_retries_leave_call_failed_without_answers():
    judge = JevPairwiseJudge(FakeJevClient(fail_times=9), DEFAULT_RUBRIC, backoff_s=0, max_attempts=3)
    call = await judge.judge(packet(), orientation="beta_as_A")
    assert call.failed and call.attempts == 3 and call.answers == {}


@pytest.mark.asyncio
async def test_resolved_model_other_than_pinned_is_flagged():
    judge = JevPairwiseJudge(FakeJevClient(model="jev-2.0.0"), DEFAULT_RUBRIC, model="jev-1.13.0")
    call = await judge.judge(packet(), orientation="beta_as_A")
    assert call.error.startswith("model_mismatch")
