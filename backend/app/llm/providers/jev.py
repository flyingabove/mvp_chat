# backend/app/llm/providers/jev.py
"""Raw TypeSafe AI (Jev) transport client.

Request/response shapes verified against the LIVE API on 2026-09-22 — see
documentation/JEV_EXTRACTOR_REDESIGN_2026_09_22.md §7 for the full evidence
(5 real requests, 21 questions, all answers correct) and
documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §8 for the request
schema this implements exactly.

No policy here: no flags, no circuit breaker, no fallback. That is
DecisionResolver's job (backend/app/llm/decisions/resolver.py, step 3+).
This client does exactly one thing: POST /v1/systemone and parse the
response, or raise a ProviderTransportError subtype.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import httpx

from backend.app.config.settings import TYPESAFE_API_KEY, TYPESAFE_MODEL
from backend.app.llm.decisions.types import DecisionBatch
from backend.app.llm.providers.base import ProviderMalformedResponseError, post_json

JEV_API_URL = "https://api.typesafe.ai/v1/systemone"


@dataclass(frozen=True)
class JevRawAnswer:
    """One question's answer, still in Jev's own shape (not yet validated
    against a Decision's allowed/threshold rules — that is the resolver's
    job). Exactly one of choice/score/probability is populated, matching
    the `type` field.

    Verified live shapes (2026-09-22):
      choice: {"type":"choice","choice":"terrace","confidence":1.0,"probabilities":{...}}
      score:  {"type":"score","score":1.95,"confidence":0.93,"legend":{...},"probabilities":{...}}
      noul:   {"type":"noul","noul":0.99}   <- NO confidence field, verified;
                                                TypeSafe's own docs confirm noul
                                                returns a probability with no
                                                separate confidence.
    """
    kind: str
    choice: str | None = None
    score: float | None = None
    probability: float | None = None          # noul's own value
    confidence: float | None = None            # absent for noul, by design
    probabilities: Mapping[str, float] = field(default_factory=dict)
    legend: Mapping[str, str] = field(default_factory=dict)  # score only


@dataclass(frozen=True)
class JevRawResult:
    answers: Mapping[str, JevRawAnswer]        # decision_id -> answer
    model: str                                 # resolved version, e.g. "jev-1.13.0" —
                                                # NEVER assume this equals the
                                                # requested TYPESAFE_MODEL alias
    usage: Mapping[str, int]                   # {"input_tokens":.., "output_tokens":..}
    latency_ms: float


def _build_criteria(decision) -> dict | list:
    """`criteria` is a MAP for choice/noul (option id -> description) and an
    ARRAY of level descriptions for score. Decision.criteria already carries
    the right shape per its own type hint (Mapping[str,str] | Sequence[str]);
    this just passes it through, converting a Mapping to a plain dict for
    JSON serialization safety (frozen dataclasses may hold a MappingProxyType)."""
    if isinstance(decision.criteria, Mapping):
        return dict(decision.criteria)
    return list(decision.criteria)


def _parse_answer(raw: dict) -> JevRawAnswer:
    kind = str(raw.get("type") or "")
    if kind == "choice":
        return JevRawAnswer(
            kind="choice",
            choice=raw.get("choice"),
            confidence=raw.get("confidence"),
            probabilities=dict(raw.get("probabilities") or {}),
        )
    if kind == "score":
        return JevRawAnswer(
            kind="score",
            score=raw.get("score"),
            confidence=raw.get("confidence"),
            probabilities=dict(raw.get("probabilities") or {}),
            legend=dict(raw.get("legend") or {}),
        )
    if kind == "noul":
        return JevRawAnswer(kind="noul", probability=raw.get("noul"))
    raise ProviderMalformedResponseError(f"unknown answer type: {kind!r}")


class JevClient:
    """Uses an injected httpx.AsyncClient (lifespan-managed per Phase 3 row 1
    once that lands; a fresh one is acceptable for tests/early wiring — see
    the `client` parameter). Never constructs its own client internally, so
    callers control the connection-pooling lifecycle."""

    def __init__(self, client: httpx.AsyncClient, *, api_key: str | None = None, model: str | None = None) -> None:
        self._client = client
        self._api_key = api_key if api_key is not None else TYPESAFE_API_KEY
        self._model = model if model is not None else TYPESAFE_MODEL

    async def ask(self, batch: DecisionBatch, *, timeout_ms: int) -> JevRawResult:
        """POST /v1/systemone for one DecisionBatch (one shared `state`, all
        its Decisions as named questions in one request — billed as one flat
        request regardless of question count, verified 2026-09-22).

        Raises a ProviderTransportError subtype on timeout/connect/non-2xx/
        unparseable body — resolve() catches this and applies fallback
        (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4). Never returns a
        partial result silently; a malformed per-question answer raises
        here rather than producing a half-populated JevRawResult.
        """
        questions = {
            d.id: {
                "type": d.kind,
                "instructions": d.instructions,
                "criteria": _build_criteria(d),
            }
            for d in batch.decisions
        }
        payload = {"model": self._model, "state": batch.state, "questions": questions}

        result = await post_json(
            self._client, JEV_API_URL,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json_body=payload,
            timeout_s=timeout_ms / 1000.0,
        )

        raw_answers = result.body.get("answers")
        if not isinstance(raw_answers, dict):
            raise ProviderMalformedResponseError("response missing 'answers' object")

        answers = {qid: _parse_answer(raw) for qid, raw in raw_answers.items()}

        return JevRawResult(
            answers=answers,
            model=result.model,
            usage=result.usage,
            latency_ms=result.latency_ms,
        )
