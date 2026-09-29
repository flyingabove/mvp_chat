"""Jev decides whether a promise was carried out; every uncertain path closes quietly, none invents a kept promise.

Real resolver + fake Jev transport: no network, no language model.
"""
import asyncio

from backend.app.engine.world_model import npc_decision, promise_judge
from backend.app.engine.world_model.commitments import add_commitment
from backend.app.engine.world_model.model import PLAYER
from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig
from backend.app.llm.providers.base import ProviderTimeoutError
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult

from tests.backend.app.engine.world_model.helpers import FakeRelationships, make_model


class FakeJev:
    def __init__(self, choice=None, confidence=0.9, error=None, by_id=None, probs=None, yes_no=0.05):
        self.choice, self.confidence, self.error, self.by_id, self.asked = choice, confidence, error, by_id or {}, []
        self.probs, self.yes_no = probs or {}, yes_no

    async def ask(self, batch, *, timeout_ms):
        self.asked.append(batch)
        if self.error:
            raise self.error
        answers = {}
        for d in batch.decisions:
            if d.kind == "noul":
                answers[d.id] = JevRawAnswer(kind="noul", probability=self.yes_no)
            else:
                answers[d.id] = JevRawAnswer(kind="choice", choice=self.by_id.get(d.id, self.choice),
                                             confidence=self.confidence, probabilities=self.probs)
        return JevRawResult(answers=answers, model="jev-test", usage={"input_tokens": 5}, latency_ms=3.0)


def _resolver(jev, enabled=True):
    config = JevConfig(enabled=enabled, enabled_tasks=frozenset({promise_judge.TASK}), shadow_tasks=frozenset(),
                       shadow_sample_rate=0.0, timeout_ms=1000, max_questions_per_batch=60)
    return DecisionResolver(jev=jev, legacy=npc_decision._no_language_model,
                            health=JevCircuitBreaker.from_settings(), config=config)


def _review(model, jev, message="Here you go, Riko. How do you take your tea?", enabled=True, relationships=None):
    return asyncio.run(promise_judge.review(model, "I will make us some tea.", "Riko smiles.", message, 30,
                                            relationships, _resolver(jev, enabled)))


def _tea():
    model = make_model({"ann": "kitchen"})
    own, other = add_commitment(model, PLAYER, "ann", "make her tea", due=0, minute=0)
    return model, own, other


def test_a_kept_promise_is_closed_for_both_sides_with_a_trust_gain():
    model, own, other = _tea()
    graph = FakeRelationships()
    rulings = _review(model, FakeJev("done"), relationships=graph)
    assert [r.action for r in rulings] == ["kept"]
    assert own.status == other.status == "kept"
    assert model.agreements.get(own.agreement_id).status == "completed"
    assert graph.notes and graph.notes[0][0] == "ann" and graph.notes[0][1] == PLAYER
    assert [e.kind for e in model.world.events] == ["agreement_completed"]


def test_the_judge_sees_the_promise_and_the_exchange_in_plain_words():
    model, own, _ = _tea()
    jev = FakeJev("pending")
    _review(model, jev)
    state = jev.asked[0].state
    assert "Paul promised Ann: make her tea" in state
    assert "I will make us some tea." in state and "Riko smiles." in state and "Here you go, Riko." in state
    assert jev.asked[0].name == promise_judge.TASK


def test_a_confident_pending_keeps_the_promise_open():
    model, own, other = _tea()
    _review(model, FakeJev("pending"))
    assert own.status == other.status == "open"


def test_cancelled_and_unclear_close_the_promise_quietly_without_credit():
    for choice in ("cancelled", "unclear"):
        model, own, other = _tea()
        graph = FakeRelationships()
        _review(model, FakeJev(choice), relationships=graph)
        assert own.status == other.status == "dropped"
        assert model.agreements.get(own.agreement_id).status == "cancelled"
        assert graph.notes == [] and model.world.events == [] and model.drama.threads == []


def test_done_is_registered_even_from_a_shaky_answer():
    """Owner rule: missing a kept promise is the bug; a false kept only forgets one."""
    model, own, _ = _tea()
    _review(model, FakeJev("done", confidence=0.3))
    assert own.status == "kept"


def test_a_modest_probability_of_done_beats_a_confident_looking_pending():
    model, own, _ = _tea()
    _review(model, FakeJev("pending", confidence=0.6, probs={"pending": 0.62, "done": 0.34, "unclear": 0.04}))
    assert own.status == "kept"


def test_staying_open_needs_a_confident_pending():
    model, own, _ = _tea()
    _review(model, FakeJev("pending", confidence=0.5, probs={"pending": 0.55, "unclear": 0.4, "done": 0.05}))
    assert own.status == "dropped"                       # not sure it is still to come: stop reminding
    model, own, _ = _tea()
    _review(model, FakeJev("pending", confidence=0.7, probs={"pending": 0.7, "unclear": 0.25, "done": 0.05}))
    assert own.status == "open"


def test_either_question_saying_done_registers_it():
    """The two questions miss on different phrasings; doubt goes toward registering (a false kept only forgets)."""
    for jev in (FakeJev("unclear", yes_no=0.6),
                FakeJev("pending", probs={"pending": 0.9, "done": 0.05}, yes_no=0.3),
                FakeJev("cancelled", yes_no=0.45)):
        model, own, _ = _tea()
        _review(model, jev)
        assert own.status == "kept", jev.choice


def test_neither_question_reaching_done_leaves_it_unregistered():
    model, own, _ = _tea()
    _review(model, FakeJev("pending", probs={"pending": 0.9, "done": 0.05}, yes_no=0.29))
    assert own.status == "open"


def test_both_questions_go_in_one_request():
    model, _, _ = _tea()
    jev = FakeJev("pending")
    _review(model, jev)
    assert len(jev.asked) == 1 and [d.kind for d in jev.asked[0].decisions] == ["choice", "noul"]


def test_an_option_outside_the_set_closes_quietly():
    model, own, _ = _tea()
    _review(model, FakeJev("maybe"))
    assert own.status == "dropped"


def test_jev_unreachable_leaves_the_promise_untouched():
    for jev, enabled in ((FakeJev(error=ProviderTimeoutError("slow")), True), (FakeJev("done"), False)):
        model, own, _ = _tea()
        rulings = _review(model, jev, enabled=enabled)
        assert [r.action for r in rulings] == ["skip"]
        assert own.status == "open"


def test_only_promises_between_people_who_are_here_are_judged():
    model = make_model({"ann": "kitchen", "ben": "garden"})
    add_commitment(model, PLAYER, "ben", "lend him a book", due=0, minute=0)
    jev = FakeJev("done")
    assert _review(model, jev) == [] and jev.asked == []


def test_an_npcs_own_promise_to_the_player_is_judged_too():
    model = make_model({"ann": "kitchen"})
    own, _ = add_commitment(model, "ann", PLAYER, "save you a plate", due=0, minute=0)
    _review(model, FakeJev("done"))
    assert own.status == "kept"


def test_at_most_four_newest_promises_are_asked_per_turn():
    model = make_model({"ann": "kitchen"})
    for i in range(6):
        add_commitment(model, PLAYER, "ann", f"do errand number {i}", due=100, minute=i)
    jev = FakeJev("pending")
    _review(model, jev)
    assert len(jev.asked) == promise_judge.MAX_CASES
    asked = " ".join(b.state for b in jev.asked)
    assert "number 5" in asked and "number 0" not in asked


def test_one_answer_per_promise_when_several_are_open():
    model = make_model({"ann": "kitchen"})
    tea, _ = add_commitment(model, PLAYER, "ann", "make her tea", due=0, minute=0)
    walk, _ = add_commitment(model, PLAYER, "ann", "take her for a walk", due=100, minute=1)
    _review(model, FakeJev(by_id={f"promise_status_{tea.id}": "done", f"promise_status_{walk.id}": "pending"}))
    assert tea.status == "kept" and walk.status == "open"


def test_a_closed_promise_is_not_judged_again():
    model, own, _ = _tea()
    _review(model, FakeJev("done"))
    jev = FakeJev("done")
    assert _review(model, jev) == [] and jev.asked == []
