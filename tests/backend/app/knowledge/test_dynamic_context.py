"""Behavioral tests for the Jev dynamic optional-memory selector."""
from __future__ import annotations

import pytest

from backend.app.config import settings
from backend.app.knowledge.runtime.dynamic_context import (
    DynamicContextSelector,
    _select_with_power_sampling,
    dynamic_context_enabled,
    retrieve_context_candidates,
)
from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult


def _candidate(chunk_id: str, rank: int, *, text: str | None = None, hidden_from=None):
    return {
        "chunk_id": chunk_id,
        "text": text or f"Memory {chunk_id}",
        "_context_source_rank": rank,
        "not_known_by": hidden_from or [],
    }


class _FakeJev:
    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.batches = []

    async def ask(self, batch, *, timeout_ms):
        self.batches.append(batch)
        answers = {}
        for decision in batch.decisions:
            candidate_id = decision.instructions.split("Candidate ID: ", 1)[1].split(".", 1)[0]
            answers[decision.id] = JevRawAnswer(kind="noul", probability=self.probabilities[candidate_id])
        return JevRawResult(answers=answers, model="jev-1.13.0", usage={"input_tokens": 1}, latency_ms=1)


def _enable_context(monkeypatch):
    monkeypatch.setattr(settings, "TYPESAFE_ENABLED", True)
    monkeypatch.setattr(settings, "JEV_ENABLED_TASKS", "context_selection")
    monkeypatch.setattr(settings, "JEV_CONTEXT_SELECTION_ALPHA", 1.5)
    monkeypatch.setattr(settings, "JEV_CONTEXT_MIN_RELEVANCE", 0.35)
    monkeypatch.setattr(settings, "JEV_CONTEXT_OPTIONAL_LIMIT", 3)
    monkeypatch.setattr(settings, "JEV_MAX_QUESTIONS_PER_BATCH", 60)


def test_context_requires_both_global_and_task_opt_in(monkeypatch):
    monkeypatch.setattr(settings, "TYPESAFE_ENABLED", True)
    monkeypatch.setattr(settings, "JEV_ENABLED_TASKS", "movement")
    assert dynamic_context_enabled() is False
    monkeypatch.setattr(settings, "JEV_ENABLED_TASKS", "context_selection")
    assert dynamic_context_enabled() is True
    monkeypatch.setattr(settings, "TYPESAFE_ENABLED", False)
    assert dynamic_context_enabled() is False


def test_context_candidates_keep_session_memory_even_when_static_is_full(monkeypatch):
    def static(*args, **kwargs):
        return [_candidate("static-1", 1), _candidate("static-2", 2)], {"mode": "hybrid"}

    class Store:
        def query(self, query, top_k):
            return [_candidate("session-1", 1)]

    monkeypatch.setattr("backend.app.knowledge.runtime.dynamic_context.retrieve_knowledge", static)
    monkeypatch.setattr(settings, "JEV_CONTEXT_CANDIDATE_LIMIT", 10)
    candidates, debug = retrieve_context_candidates("remember dinner", namespace="n", session_store=Store())
    assert [c["chunk_id"] for c in candidates] == ["static-1", "static-2", "session-1"]
    assert debug["session_candidates"] == 1


@pytest.mark.asyncio
async def test_jev_scores_then_power_samples_without_private_memory(monkeypatch):
    _enable_context(monkeypatch)
    fake = _FakeJev({"best": 0.8, "other": 0.4, "private": 0.99})
    selector = DynamicContextSelector(jev=fake, breaker=JevCircuitBreaker())
    result = await selector.select(
        query="Do you remember dinner?", scene="Kitchen; Ren is present.", focal_character_id="ren",
        candidates=[_candidate("best", 1), _candidate("other", 2), _candidate("private", 3, hidden_from=["ren"])],
        seed_material="stable",
    )
    assert result.debug["provider"] == "jev"
    assert result.chunks[0]["chunk_id"] == "best", "highest relevance is the deterministic anchor"
    assert "private" not in result.debug["scores"]
    assert all("Candidate text:" in d.instructions for b in fake.batches for d in b.decisions)
    assert all(d.criteria == {"true": "Directly useful and natural in this scene.", "false": "Background, irrelevant, unsafe, or only word-overlap."} for b in fake.batches for d in b.decisions)


def test_power_sampling_uses_alpha_and_never_duplicates():
    candidates = [_candidate("high", 1), _candidate("mid", 2), _candidate("low", 3)]
    scores = {"high": 0.8, "mid": 0.4, "low": 0.2}
    selected = _select_with_power_sampling(candidates, scores=scores, alpha=1.5, limit=3, seed_material="same")
    assert selected[0]["chunk_id"] == "high"
    assert len({item["chunk_id"] for item in selected}) == len(selected)
    # alpha=0 is explicitly uniform after the deterministic relevance anchor.
    uniform = _select_with_power_sampling(candidates, scores=scores, alpha=0, limit=3, seed_material="same")
    assert len(uniform) == 3
