"""Accuracy gate for the Jev promise-completion judge, against LIVE Jev.

Never runs on deployment: it is `@pytest.mark.integration`, and the Docker gate and the CI unit job
deselect that marker (and block LLM hosts). Run it by hand or in the CI integration job:

    pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py -s

It needs TYPESAFE_API_KEY (auto-loaded from `.env.test`). Missing credentials make it FAIL rather than skip
(skips are banned in this repo). Owner rule 2026-09-29: a promise that was carried out must be registered as
kept (miss rate <= 2%), and nothing may be registered as kept that was not done.

The labeled exchanges live in tests/data/promise_judge_cases.json and promise_judge_holdout.json. See
documentation/proposals/PROMISE_COMPLETION_JEV_2026_09_29.md for how they were built and what they measure.
"""
import pytest

from backend.app.engine.world_model import promise_judge
from scripts.eval import promise_judge_eval as evaluation


@pytest.fixture()
def live_jev(monkeypatch):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "TYPESAFE_ENABLED", True)
    promise_judge.reset_resolver_for_tests()
    yield
    promise_judge.reset_resolver_for_tests()


@pytest.mark.integration
def test_the_judge_registers_kept_promises_at_or_above_the_gate(live_jev, capsys):
    items = evaluation.load("all")
    stats = evaluation.measure(items)
    with capsys.disabled():
        evaluation.report(stats, show_misses=True)
    assert stats.total == len(items) and stats.done_total >= 150, "the labeled set went missing or shrank"
    assert stats.unreachable == 0, (
        f"Jev answered {stats.total - stats.unreachable}/{stats.total}; check TYPESAFE_API_KEY, network and the "
        "circuit breaker before trusting any number here")
    assert stats.other_kept == 0, (
        f"{stats.other_kept} exchange(s) that were NOT a kept promise were registered as kept")
    assert stats.miss_rate <= evaluation.GATE, (
        f"kept promises missed: {stats.done_missed}/{stats.done_total} = {stats.miss_rate:.1%} "
        f"(gate {evaluation.GATE:.0%}); misses: {[(m[0]['id'], m[1]) for m in stats.misses]}")
