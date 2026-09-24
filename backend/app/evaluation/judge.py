# backend/app/evaluation/judge.py
"""Pairwise judge (JEV_GAME_ARENA_DESIGN.md §3, §7, §10).

A judge answers ONE evidence packet (one window, one A/B order). Order
swapping, remapping to releases and aggregation happen in pipeline.py, so a
judge never knows which release it is looking at.

Policy is deliberately different from the gameplay DecisionResolver:
  * no fallback to another model (a secondary judge would need its own
    calibration and provenance);
  * bounded transport retry on the SAME stored input only; a valid answer
    is never re-sampled, whatever it says;
  * strict validation that FAILS CLOSED: a malformed/missing distribution
    makes that question unresolved, never a default vote.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Protocol

from backend.app.evaluation.evidence import EvidencePacket
from backend.app.evaluation.rubric import CHOICE_OPTIONS, Rubric
from backend.app.llm.decisions.types import Criticality, Decision, DecisionBatch
from backend.app.llm.providers.base import (
    ProviderHTTPError, ProviderMalformedResponseError, ProviderTimeoutError, ProviderTransportError,
)

JUDGE_TASK = "arena_judge"
DEFAULT_JUDGE_MODEL = "jev-1.13.0"   # pinned, never an alias (§3 Models)
MAX_EVIDENCE_OPTIONS = 254           # choice limit is 255 incl. "none"
NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 404, 422})


def cmp_id(dim: str) -> str:
    return f"cmp_{dim}"


def score_id(side: str, dim: str) -> str:
    return f"score_{side}_{dim}"


def evidence_id(dim: str) -> str:
    return f"ev_{dim}"


def probe_id(side: str, probe: str) -> str:
    return f"probe_{side}_{probe}"


@dataclass(frozen=True)
class ValidatedAnswer:
    question_id: str
    valid: bool
    kind: str = ""
    choice: str | None = None
    score: float | None = None
    probability: float | None = None
    confidence: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    reason: str = ""


@dataclass
class JudgeCall:
    """One judge request's full record (input hash, attempts, cost, answers)."""
    window_index: int
    orientation: str                       # which release was shown as A, e.g. "beta_as_A"
    answers: dict[str, ValidatedAnswer]
    model: str = ""
    attempts: int = 0
    input_tokens: int = 0
    latency_ms: float = 0.0
    error: str = ""
    estimated_state_tokens: int = 0

    @property
    def failed(self) -> bool:
        return bool(self.error) and not self.answers

    def answer(self, question_id: str) -> ValidatedAnswer:
        return self.answers.get(question_id) or ValidatedAnswer(question_id, False, reason="missing_answer")

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        return data


class PairwiseJudge(Protocol):
    model: str

    async def judge(self, packet: EvidencePacket, *, orientation: str) -> JudgeCall: ...


def build_decisions(rubric: Rubric, packet: EvidencePacket) -> tuple[Decision, ...]:
    decisions: list[Decision] = []
    span_options = list(packet.span_ids[:MAX_EVIDENCE_OPTIONS])
    for dim in rubric.dimensions:
        decisions.append(Decision(
            id=cmp_id(dim.id), task=JUDGE_TASK, kind="choice",
            instructions=dim.choice_instructions(), criteria=dim.choice_criteria(),
            criticality=Criticality.CRITICAL, allowed=frozenset(CHOICE_OPTIONS),
        ))
        for side in ("A", "B"):
            decisions.append(Decision(
                id=score_id(side, dim.id), task=JUDGE_TASK, kind="score",
                instructions=dim.score_instructions(side), criteria=list(dim.bands),
                criticality=Criticality.DEGRADABLE,
            ))
        if span_options:
            decisions.append(Decision(
                id=evidence_id(dim.id), task=JUDGE_TASK, kind="choice",
                instructions=dim.evidence_instructions(),
                criteria={**{s: f"span [{s}]" for s in span_options}, "none": "no span is relevant"},
                criticality=Criticality.DEGRADABLE, allowed=frozenset(span_options + ["none"]),
            ))
    for probe in rubric.critical_probes:
        for side in ("A", "B"):
            decisions.append(Decision(
                id=probe_id(side, probe.id), task=JUDGE_TASK, kind="noul",
                instructions=probe.instructions(side), criteria=probe.criteria(side),
                criticality=Criticality.CRITICAL,
            ))
    return tuple(decisions)


def validate_answer(decision: Decision, raw: Any) -> ValidatedAnswer:
    """Fail closed on anything that is not a well-formed answer of the
    decision's kind. `raw` is a JevRawAnswer (or anything duck-typed like it)."""
    qid = decision.id
    if raw is None:
        return ValidatedAnswer(qid, False, reason="missing_answer")
    kind = getattr(raw, "kind", "")
    if kind != decision.kind:
        return ValidatedAnswer(qid, False, kind=kind, reason=f"wrong_kind:{kind}")
    probs = {str(k): float(v) for k, v in (getattr(raw, "probabilities", None) or {}).items()
             if isinstance(v, (int, float)) and math.isfinite(float(v))}
    confidence = getattr(raw, "confidence", None)

    if kind == "choice":
        choice = getattr(raw, "choice", None)
        allowed = decision.allowed or frozenset()
        if choice not in allowed:
            return ValidatedAnswer(qid, False, kind=kind, reason=f"invalid_option:{choice}")
        if not probs:
            return ValidatedAnswer(qid, False, kind=kind, reason="missing_distribution")
        if not set(probs) <= set(allowed) or any(p < 0 or p > 1 for p in probs.values()):
            return ValidatedAnswer(qid, False, kind=kind, reason="bad_distribution")
        if abs(sum(probs.values()) - 1.0) > 0.05:
            return ValidatedAnswer(qid, False, kind=kind, reason="distribution_not_normalized")
        return ValidatedAnswer(qid, True, kind=kind, choice=choice, confidence=confidence, probabilities=probs)

    if kind == "score":
        score = getattr(raw, "score", None)
        top = len(list(decision.criteria)) - 1
        if not isinstance(score, (int, float)) or not math.isfinite(score) or score < 0 or score > top:
            return ValidatedAnswer(qid, False, kind=kind, reason=f"score_out_of_range:{score}")
        return ValidatedAnswer(qid, True, kind=kind, score=float(score), confidence=confidence, probabilities=probs)

    if kind == "noul":
        p = getattr(raw, "probability", None)
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p < 0 or p > 1:
            return ValidatedAnswer(qid, False, kind=kind, reason=f"probability_out_of_range:{p}")
        return ValidatedAnswer(qid, True, kind=kind, probability=float(p))

    return ValidatedAnswer(qid, False, kind=kind, reason=f"unknown_kind:{kind}")


def is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ProviderHTTPError):
        return exc.status_code not in NON_RETRYABLE_STATUS
    return isinstance(exc, (ProviderTimeoutError, ProviderMalformedResponseError, ProviderTransportError))


class JevPairwiseJudge:
    """Wraps backend.app.llm.providers.jev.JevClient (transport reuse) with
    the judge policy above."""

    def __init__(self, client, rubric: Rubric, *, model: str = DEFAULT_JUDGE_MODEL,
                 timeout_ms: int = 120_000, max_attempts: int = 3, backoff_s: float = 2.0) -> None:
        self.client = client
        self.rubric = rubric
        self.model = model
        self.timeout_ms = timeout_ms
        self.max_attempts = max_attempts
        self.backoff_s = backoff_s

    async def judge(self, packet: EvidencePacket, *, orientation: str) -> JudgeCall:
        decisions = build_decisions(self.rubric, packet)
        batch = DecisionBatch(name=f"arena_w{packet.window_index}", state=packet.state, decisions=decisions)
        call = JudgeCall(window_index=packet.window_index, orientation=orientation, answers={},
                         estimated_state_tokens=packet.estimated_tokens)
        last_error = ""
        for attempt in range(1, self.max_attempts + 1):
            call.attempts = attempt
            try:
                result = await self.client.ask(batch, timeout_ms=self.timeout_ms)
            except Exception as exc:  # noqa: BLE001 - classified below
                last_error = f"{type(exc).__name__}: {exc}"
                if not is_retryable(exc) or attempt == self.max_attempts:
                    break
                await asyncio.sleep(self.backoff_s * attempt)
                continue
            call.model = result.model
            call.input_tokens = int((result.usage or {}).get("input_tokens") or 0)
            call.latency_ms = float(result.latency_ms)
            call.answers = {d.id: validate_answer(d, result.answers.get(d.id)) for d in decisions}
            if result.model and result.model != self.model:
                call.error = f"model_mismatch:{result.model}"
            return call
        call.error = last_error or "judge_failed"
        return call


def answers_to_json(answers: Mapping[str, ValidatedAnswer]) -> dict[str, Any]:
    return {k: asdict(v) for k, v in answers.items()}
