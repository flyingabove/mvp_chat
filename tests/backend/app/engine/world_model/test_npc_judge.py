"""The Jev judge for NPC verdicts: real resolver + fake Jev transport, no network, no language model."""
import asyncio

import pytest

from backend.app.engine.world_model import npc_decision
from backend.app.engine.world_model.npc_decision import JevJudgment, jev_decision, judge
from backend.app.engine.world_model.social_acts import SocialAct
from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig
from backend.app.llm.providers.base import ProviderTimeoutError
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult


class FakeJev:
    def __init__(self, choice=None, confidence=0.9, error=None):
        self.choice, self.confidence, self.error, self.asked = choice, confidence, error, []

    async def ask(self, batch, *, timeout_ms):
        self.asked.append(batch)
        if self.error:
            raise self.error
        answers = {d.id: JevRawAnswer(kind="choice", choice=self.choice, confidence=self.confidence,
                                      probabilities={"accept": 0.3, "not_yet": 0.6, "reject": 0.1})
                   for d in batch.decisions}
        return JevRawResult(answers=answers, model="jev-test", usage={"input_tokens": 5}, latency_ms=3.0)


def _resolver(jev, enabled=True):
    config = JevConfig(enabled=enabled, enabled_tasks=frozenset({npc_decision.TASK}), shadow_tasks=frozenset(),
                       shadow_sample_rate=0.0, timeout_ms=1000, max_questions_per_batch=60)
    return DecisionResolver(jev=jev, legacy=npc_decision._no_language_model, health=JevCircuitBreaker.from_settings(),
                            config=config)


def _run(jev, enabled=True):
    decision = jev_decision("ann", SocialAct("confess", "ann"))
    return asyncio.run(judge(decision, "You are Ann.", resolver=_resolver(jev, enabled)))


def test_a_usable_answer_comes_back_with_its_confidence():
    jev = FakeJev("not_yet", 0.8)
    result = _run(jev)
    assert result == JevJudgment("not_yet", 0.8, "", (("accept", 0.3), ("not_yet", 0.6), ("reject", 0.1)))
    assert jev.asked[0].state == "You are Ann." and jev.asked[0].name == npc_decision.TASK


def test_low_confidence_is_reported_as_unavailable_not_used():
    result = _run(FakeJev("accept", 0.2))
    assert result.reason == "below_threshold" and result.choice == "accept"
    assert dict(result.probabilities)["accept"] == 0.3, "odds are kept for review even when unusable"


def test_a_timeout_is_a_reason_not_an_exception():
    result = _run(FakeJev(error=ProviderTimeoutError("slow")))
    assert result == JevJudgment(None, None, "timeout")


def test_an_option_outside_the_allowed_set_is_rejected():
    assert _run(FakeJev("maybe")).reason == "invalid_option"


def test_jev_off_means_flag_disabled_and_the_fake_is_never_asked():
    jev = FakeJev("accept")
    result = _run(jev, enabled=False)
    assert result.choice is None and result.reason == "flag_disabled" and jev.asked == []


def test_the_production_resolver_can_never_reach_a_language_model():
    """The two-LLM-call budget: this task's fallback is a callable that returns nothing."""
    npc_decision.reset_resolver_for_tests()
    resolver = npc_decision.default_resolver()
    assert resolver._legacy is npc_decision._no_language_model
    assert asyncio.run(npc_decision._no_language_model(object())) is None
    npc_decision.reset_resolver_for_tests()


def test_a_resolver_bug_is_contained():
    class Broken:
        async def resolve(self, *a, **k):
            raise RuntimeError("boom")
    result = asyncio.run(judge(jev_decision("ann", SocialAct("confess", "ann")), "x", resolver=Broken()))
    assert result.choice is None and result.reason == "error:RuntimeError"
