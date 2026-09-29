"""Through the real turn pipeline: Jev closes a kept promise before the scene is built (2026-09-29 tea loop)."""
import asyncio

from backend.app.engine.world_model import npc_decision, promise_judge
from backend.app.engine.world_model.commitments import add_commitment
from backend.app.engine.world_model.model import PLAYER
from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult

from tests.backend.app.api.test_terrace_campaigns import _new_game, _say, campaign  # noqa: F401


class FakeJev:
    def __init__(self, choice):
        self.choice, self.asked = choice, []

    async def ask(self, batch, *, timeout_ms):
        self.asked.append(batch)
        answers = {d.id: (JevRawAnswer(kind="noul", probability=0.9 if self.choice == "done" else 0.05)
                          if d.kind == "noul" else
                          JevRawAnswer(kind="choice", choice=self.choice, confidence=0.95, probabilities={}))
                   for d in batch.decisions}
        return JevRawResult(answers=answers, model="jev-test", usage={"input_tokens": 1}, latency_ms=1.0)


def _install(monkeypatch, choice):
    from backend.app.config import settings
    monkeypatch.setattr(settings, "PROMISE_JUDGE_ENABLED", True)
    jev = FakeJev(choice)
    config = JevConfig(enabled=True, enabled_tasks=frozenset({promise_judge.TASK}), shadow_tasks=frozenset(),
                       shadow_sample_rate=0.0, timeout_ms=1000, max_questions_per_batch=60)
    monkeypatch.setattr(promise_judge, "default_resolver", lambda: DecisionResolver(
        jev=jev, legacy=npc_decision._no_language_model, health=JevCircuitBreaker.from_settings(), config=config))
    return jev


def _promise_with_someone_here(campaign, sid):
    state = _new_game(campaign, sid, "M")
    model = state.world_model
    here = model.present_with_player()
    assert here, "the opening house has a resident in the room"
    add_commitment(model, PLAYER, here[0], "make her tea", due=model.world.minute, minute=model.world.minute)
    return model.memories.open_promises()[0].id


def _promises(campaign, sid):
    """The live session's promises: the state object is replaced during a turn, so never hold an old one."""
    model = campaign.pe.SESSIONS[sid]["state"].world_model
    return model, {m.id: m for m in model.memories.memories if m.kind == "promise"}


def test_a_kept_promise_is_closed_by_jev_before_the_scene_and_never_raised(campaign, monkeypatch):
    jev = _install(monkeypatch, "done")
    promise_id = _promise_with_someone_here(campaign, "kept")
    _say(campaign, "kept", "Here you go, how do you take your tea?")
    model, promises = _promises(campaign, "kept")
    assert jev.asked and promises[promise_id].status == "kept"
    assert not [line for line in model.view.must_address if "promised" in line.lower()]


def test_an_unsettled_promise_is_still_raised_once_then_left_alone(campaign, monkeypatch):
    _install(monkeypatch, "pending")
    promise_id = _promise_with_someone_here(campaign, "pending")
    _say(campaign, "pending", "So, what shall we talk about?")
    model, promises = _promises(campaign, "pending")
    assert promises[promise_id].status == "open"
    assert promises[promise_id].reminded is True
    _say(campaign, "pending", "And after that?")
    model, _ = _promises(campaign, "pending")
    assert not [line for line in model.view.must_address if "promised" in line.lower()]


def test_the_judge_is_off_by_default_and_never_calls_jev(campaign, monkeypatch):
    jev = _install(monkeypatch, "done")
    from backend.app.config import settings
    monkeypatch.setattr(settings, "PROMISE_JUDGE_ENABLED", False)
    promise_id = _promise_with_someone_here(campaign, "off")
    _say(campaign, "off", "Here you go, how do you take your tea?")
    _, promises = _promises(campaign, "off")
    assert jev.asked == [] and promises[promise_id].status == "open"
