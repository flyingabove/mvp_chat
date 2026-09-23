# backend/app/llm/decisions/resolver.py
"""DecisionResolver.resolve() — the call_jev()-with-fallback core.

Exact 8-step control flow from
documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4. This is
deliberately the ONLY place in the codebase that decides between Jev and
the legacy generative extractor — no call site ever branches on "is Jev up".

Generalization beyond the doc's two literal cases: the doc's step 1/6
explicitly describe "zero decisions route to Jev" and "all routed decisions
succeed or one critical one fails". It does not spell out a THIRD case that
becomes possible once decision_registry.py (step 5+) grows to contain
decisions from multiple tasks where only SOME tasks are currently enabled —
e.g. "movement" is JEV_ENABLED_TASKS but "departure" decisions also exist in
the same batch and are not. That case is handled here as: any decision
never routed to Jev (its task isn't in JEV_ENABLED_TASKS or
JEV_SHADOW_TASKS) always needs a legacy-sourced answer, exactly as if it
were degraded — this is a natural extension of the doc's own rules, not a
deviation, and is exercised by tests below since it will become the live
scenario once step 6+ adds more tasks to the registry.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Sequence

from backend.app.llm.decisions.health import BreakerState, JevCircuitBreaker
from backend.app.llm.decisions.types import (
    Decision, DecisionAnswer, DecisionBatch, DecisionOutcome, FallbackReason, Provider,
)
from backend.app.llm.protocols import LegacyExtractionRequest
from backend.app.llm.providers.base import (
    ProviderHTTPError, ProviderMalformedResponseError, ProviderTimeoutError, ProviderTransportError,
)
from backend.app.llm.providers.jev import JevClient, JevRawAnswer, JevRawResult

# Type alias matching JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4's constructor
# signature exactly: the legacy one-shot LLM call, injected so the resolver
# never imports TurnExtractor (would create an engine <-> llm import cycle).
LegacyExtractionCallable = Callable[[LegacyExtractionRequest], Awaitable[dict[str, Any] | None]]


@dataclass(frozen=True)
class JevConfig:
    """Wraps the rollout flags from settings.py. Constructed once per
    process via from_settings(); tests construct it directly with explicit
    values instead of monkeypatching module-level settings.
    """
    enabled: bool
    enabled_tasks: frozenset[str]
    shadow_tasks: frozenset[str]
    shadow_sample_rate: float
    timeout_ms: int
    max_questions_per_batch: int

    @classmethod
    def from_settings(cls) -> "JevConfig":
        from backend.app.config import settings
        return cls(
            enabled=settings.TYPESAFE_ENABLED,
            enabled_tasks=_parse_task_csv(settings.JEV_ENABLED_TASKS),
            shadow_tasks=_parse_task_csv(settings.JEV_SHADOW_TASKS),
            shadow_sample_rate=settings.JEV_SHADOW_SAMPLE_RATE,
            timeout_ms=settings.JEV_TIMEOUT_MS,
            max_questions_per_batch=settings.JEV_MAX_QUESTIONS_PER_BATCH,
        )

    def routing_for(self, task: str) -> str:
        """Returns "shadow" | "live" | "off" for a task.

        Precedence per §7: TYPESAFE_ENABLED=false beats everything.
        JEV_SHADOW_TASKS beats JEV_ENABLED_TASKS for the same task (a
        double-listing fails SAFE — shadows rather than goes live).
        "*" in either CSV means every task.
        """
        if not self.enabled:
            return "off"
        if "*" in self.shadow_tasks or task in self.shadow_tasks:
            return "shadow"
        if "*" in self.enabled_tasks or task in self.enabled_tasks:
            return "live"
        return "off"


def _parse_task_csv(raw: str) -> frozenset[str]:
    return frozenset(t.strip() for t in raw.split(",") if t.strip())


def _get_by_path(raw: dict[str, Any] | None, path: tuple[str, ...]) -> Any:
    """Walks a Decision.legacy_path (e.g. ("movement", "intent")) into the
    legacy call's raw parsed JSON. Returns None on any missing key or wrong
    type — matches the existing legacy parser's own tolerant style
    (turn_extractor.py's _parse_json never raises on a missing field)."""
    if raw is None:
        return None
    node: Any = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _legacy_answer(decision: Decision, legacy_raw: dict[str, Any] | None) -> DecisionAnswer:
    """Builds a DecisionAnswer from the legacy call's raw JSON via
    Decision.legacy_path. A legacy answer is always considered "usable" —
    it's the fallback of last resort, there is nothing further to fall
    back to, so it never carries a FallbackReason other than NONE."""
    value = _get_by_path(legacy_raw, decision.legacy_path)
    if decision.kind == "choice":
        return DecisionAnswer(decision_id=decision.id, provider=Provider.LEGACY_LLM,
                               choice=str(value) if value is not None else None)
    if decision.kind == "score":
        try:
            score = float(value) if value is not None else None
        except (TypeError, ValueError):
            score = None
        return DecisionAnswer(decision_id=decision.id, provider=Provider.LEGACY_LLM, score=score)
    if decision.kind == "noul":
        prob = 1.0 if bool(value) else (0.0 if value is not None else None)
        return DecisionAnswer(decision_id=decision.id, provider=Provider.LEGACY_LLM, probability=prob)
    return DecisionAnswer(decision_id=decision.id, provider=Provider.LEGACY_LLM)


def _validate_jev_answer(decision: Decision, raw: JevRawAnswer | None) -> DecisionAnswer:
    """Step 5 of resolve()'s control flow: per-answer validation.

    missing question id                  -> MISSING_ANSWER
    choice not in decision.allowed       -> INVALID_OPTION
    choice == decision.none_option       -> USABLE (the designed escape hatch)
    confidence < decision.min_confidence -> BELOW_THRESHOLD
    noul probability -> bool via true_threshold (never a failure by itself)
    """
    if raw is None:
        return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                               fallback_reason=FallbackReason.MISSING_ANSWER)

    if decision.kind == "choice":
        choice = raw.choice
        if choice is None:
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                                   fallback_reason=FallbackReason.MISSING_ANSWER)
        if decision.allowed is not None and choice not in decision.allowed:
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, choice=choice,
                                   confidence=raw.confidence, probabilities=raw.probabilities,
                                   fallback_reason=FallbackReason.INVALID_OPTION)
        # none_option is the designed escape hatch: a valid, USABLE answer
        # meaning "no answer applies here" (e.g. destination not reachable).
        if choice == decision.none_option:
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, choice=choice,
                                   confidence=raw.confidence, probabilities=raw.probabilities)
        if (decision.min_confidence is not None and raw.confidence is not None
                and raw.confidence < decision.min_confidence):
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, choice=choice,
                                   confidence=raw.confidence, probabilities=raw.probabilities,
                                   fallback_reason=FallbackReason.BELOW_THRESHOLD)
        return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, choice=choice,
                               confidence=raw.confidence, probabilities=raw.probabilities)

    if decision.kind == "score":
        if raw.score is None:
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                                   fallback_reason=FallbackReason.MISSING_ANSWER)
        if (decision.min_confidence is not None and raw.confidence is not None
                and raw.confidence < decision.min_confidence):
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, score=raw.score,
                                   confidence=raw.confidence, probabilities=raw.probabilities,
                                   fallback_reason=FallbackReason.BELOW_THRESHOLD)
        return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV, score=raw.score,
                               confidence=raw.confidence, probabilities=raw.probabilities)

    if decision.kind == "noul":
        if raw.probability is None:
            return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                                   fallback_reason=FallbackReason.MISSING_ANSWER)
        # A low probability is a valid False, never a failure by itself —
        # per the doc's explicit rule. true_threshold only affects how a
        # CONSUMER later interprets probability as a bool; it does not
        # gate usability here.
        return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                               probability=raw.probability)

    return DecisionAnswer(decision_id=decision.id, provider=Provider.JEV,
                           fallback_reason=FallbackReason.MALFORMED_RESPONSE)


def _map_transport_exception(exc: BaseException) -> FallbackReason:
    if isinstance(exc, ProviderTimeoutError):
        return FallbackReason.TIMEOUT
    if isinstance(exc, ProviderHTTPError):
        return FallbackReason.HTTP_ERROR
    if isinstance(exc, ProviderMalformedResponseError):
        return FallbackReason.MALFORMED_RESPONSE
    if isinstance(exc, ProviderTransportError):
        return FallbackReason.HTTP_ERROR
    # An unexpected exception type (a bug in JevClient, not a documented
    # failure mode) — treat conservatively as a transport failure so the
    # turn still falls back safely rather than propagating.
    return FallbackReason.HTTP_ERROR


class DecisionResolver:
    """Resolves bounded decisions via Jev with automatic fallback to the
    existing legacy generative call. See module docstring and
    JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4 for the exact control flow.
    """

    def __init__(
        self,
        jev: JevClient,
        legacy: LegacyExtractionCallable,
        health: JevCircuitBreaker,
        config: JevConfig,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._jev = jev
        self._legacy = legacy
        self._health = health
        self._config = config
        self._clock = clock

    async def resolve(
        self,
        batches: Sequence[DecisionBatch],
        legacy_request: LegacyExtractionRequest,
    ) -> DecisionOutcome:
        """ALWAYS returns a usable DecisionOutcome. Never raises. Never
        surfaces provider state to the caller."""
        all_decisions: list[Decision] = [d for b in batches for d in b.decisions]

        # --- Step 1: partition by flag ---------------------------------
        routing = {d.id: self._config.routing_for(d.task) for d in all_decisions}
        jev_routed = [d for d in all_decisions if routing[d.id] in ("live", "shadow")]
        never_routed = [d for d in all_decisions if routing[d.id] == "off"]

        if not jev_routed:
            # No-Jev mode: byte-identical to today. Legacy path is the ONLY
            # path, never touches the breaker or Jev at all.
            return await self._legacy_only_outcome(
                legacy_request, all_decisions,
                fallback_reasons={d.id: FallbackReason.FLAG_DISABLED for d in never_routed},
            )

        # --- Step 2: circuit check --------------------------------------
        if not self._health.allow_request():
            fallback_reasons = {d.id: FallbackReason.CIRCUIT_OPEN for d in jev_routed}
            fallback_reasons.update({d.id: FallbackReason.FLAG_DISABLED for d in never_routed})
            return await self._legacy_only_outcome(legacy_request, all_decisions, fallback_reasons)

        # --- Step 3: call Jev, all sub-batches concurrently -------------
        # Sub-batches restricted to jev-routed decisions only — a decision
        # whose task is "off" is never sent to Jev at all (saves tokens,
        # and gives it a real FLAG_DISABLED "never tried" reason).
        sub_batches: list[DecisionBatch] = []
        for b in batches:
            routed_in_batch = tuple(d for d in b.decisions if routing[d.id] in ("live", "shadow"))
            if routed_in_batch:
                sub_batches.append(DecisionBatch(name=b.name, state=b.state, decisions=routed_in_batch))

        jev_t0 = self._clock()
        raw_results = await asyncio.gather(
            *[self._jev.ask(sb, timeout_ms=self._config.timeout_ms) for sb in sub_batches],
            return_exceptions=True,
        )
        jev_latency_ms = (self._clock() - jev_t0) * 1000.0

        # --- Step 4 + 5: per-batch outcome, then per-answer validation --
        answers: dict[str, DecisionAnswer] = {}
        fallback_reasons: dict[str, FallbackReason] = {}
        jev_usage_total: dict[str, int] = {}
        jev_model: str | None = None

        for sub_batch, raw_result in zip(sub_batches, raw_results):
            if isinstance(raw_result, BaseException):
                reason = _map_transport_exception(raw_result)
                self._health.record_failure(reason)
                for d in sub_batch.decisions:
                    answers[d.id] = DecisionAnswer(decision_id=d.id, provider=Provider.JEV, fallback_reason=reason)
                    fallback_reasons[d.id] = reason
                continue

            self._health.record_success()
            jev_result: JevRawResult = raw_result
            jev_model = jev_result.model or jev_model
            for key, val in jev_result.usage.items():
                jev_usage_total[key] = jev_usage_total.get(key, 0) + int(val or 0)

            for d in sub_batch.decisions:
                answer = _validate_jev_answer(d, jev_result.answers.get(d.id))
                answers[d.id] = answer
                if not answer.usable:
                    fallback_reasons[d.id] = answer.fallback_reason

        for d in never_routed:
            fallback_reasons[d.id] = FallbackReason.FLAG_DISABLED

        # --- Step 6: decide fallback granularity ------------------------
        unusable_critical = [
            d for d in jev_routed
            if d.id in answers and not answers[d.id].usable and d.criticality.value == "critical"
        ]

        shadow_ids = {d.id for d in jev_routed if routing[d.id] == "shadow"}
        needs_legacy = bool(unusable_critical) or bool(never_routed) or bool(shadow_ids)

        legacy_raw: dict[str, Any] | None = None
        legacy_latency_ms: float | None = None
        if needs_legacy:
            legacy_t0 = self._clock()
            legacy_raw = await self._legacy(legacy_request)
            legacy_latency_ms = (self._clock() - legacy_t0) * 1000.0

        shadow_disagreements: dict[str, tuple[Any, Any]] = {}

        if unusable_critical:
            # A CRITICAL decision failed: legacy wins for EVERY decision,
            # discard all Jev answers entirely (per §4 step 6's rationale —
            # one known-good call beats a partial blend).
            final_answers = {d.id: _legacy_answer(d, legacy_raw) for d in all_decisions}
            provider_used = Provider.LEGACY_LLM
        else:
            final_answers = dict(answers)
            for d in never_routed:
                final_answers[d.id] = _legacy_answer(d, legacy_raw)
            # Shadow reconciliation (step 7): both ran: return legacy,
            # record disagreement, never let the shadow answer reach game
            # state.
            for d in jev_routed:
                if d.id not in shadow_ids:
                    continue
                jev_value = _answer_display_value(final_answers.get(d.id))
                legacy_answer = _legacy_answer(d, legacy_raw)
                legacy_value = _answer_display_value(legacy_answer)
                shadow_disagreements[d.id] = (jev_value, legacy_value)
                final_answers[d.id] = legacy_answer
            provider_used = Provider.JEV if any(
                final_answers[d.id].provider is Provider.JEV for d in jev_routed if d.id not in shadow_ids
            ) else Provider.LEGACY_LLM

        return DecisionOutcome(
            answers=final_answers,
            legacy_raw=legacy_raw,
            provider_used=provider_used,
            jev_latency_ms=jev_latency_ms,
            legacy_latency_ms=legacy_latency_ms,
            jev_usage=jev_usage_total or None,
            fallback_reasons={k: v for k, v in fallback_reasons.items() if v is not FallbackReason.NONE},
            shadow_disagreements=shadow_disagreements,
        )

    async def _legacy_only_outcome(
        self,
        legacy_request: LegacyExtractionRequest,
        all_decisions: list[Decision],
        fallback_reasons: dict[str, FallbackReason],
    ) -> DecisionOutcome:
        legacy_t0 = self._clock()
        legacy_raw = await self._legacy(legacy_request)
        legacy_latency_ms = (self._clock() - legacy_t0) * 1000.0
        return DecisionOutcome(
            answers={d.id: _legacy_answer(d, legacy_raw) for d in all_decisions},
            legacy_raw=legacy_raw,
            provider_used=Provider.LEGACY_LLM,
            jev_latency_ms=None,
            legacy_latency_ms=legacy_latency_ms,
            jev_usage=None,
            fallback_reasons={k: v for k, v in fallback_reasons.items() if v is not FallbackReason.NONE},
            shadow_disagreements={},
        )


def _answer_display_value(answer: DecisionAnswer | None) -> Any:
    """For shadow_disagreements logging — one representative value per
    answer, whichever field its kind populated."""
    if answer is None:
        return None
    if answer.choice is not None:
        return answer.choice
    if answer.score is not None:
        return answer.score
    if answer.probability is not None:
        return answer.probability
    return None
