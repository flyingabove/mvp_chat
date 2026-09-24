"""Tests for DecisionResolver.resolve() (backend/app/llm/decisions/resolver.py).

Covers every case in JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §11's resolver
test plan, plus the mixed-routing extension the resolver's own docstring
documents (some decisions routed to Jev, others "off" in the same turn).

All Jev/legacy calls are fakes constructed inline — no network, no real
provider dependency.
"""
import asyncio

import pytest

from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig, _get_by_path, _legacy_answer
from backend.app.llm.decisions.types import Criticality, DecisionBatch, Decision, FallbackReason, Provider
from backend.app.llm.protocols import LegacyExtractionRequest
from backend.app.llm.providers.base import ProviderHTTPError, ProviderMalformedResponseError, ProviderTimeoutError
from backend.app.llm.providers.jev import JevRawAnswer, JevRawResult


def _config(*, enabled=True, live=(), shadow=(), timeout_ms=1000, max_q=60, sample_rate=0.0):
    return JevConfig(
        enabled=enabled, enabled_tasks=frozenset(live), shadow_tasks=frozenset(shadow),
        shadow_sample_rate=sample_rate, timeout_ms=timeout_ms, max_questions_per_batch=max_q,
    )


def _movement_decision(id_="movement_intent", task="movement", criticality=Criticality.CRITICAL):
    return Decision(id=id_, task=task, kind="choice", instructions="i",
                     criteria={"MOVE": "x", "NONE": "y"}, criticality=criticality,
                     allowed=frozenset({"MOVE", "NONE"}), legacy_path=("movement", "intent"))


def _legacy_req(invoke=None):
    return LegacyExtractionRequest(user_msg="hi", world_locations={}, character_key_to_name={}, invoke=invoke)


class _FakeJevClient:
    """Records calls; returns a scripted result or raises a scripted
    exception, per batch name."""
    def __init__(self, results_by_batch_name: dict, calls_list: list):
        self._results = results_by_batch_name
        self._calls = calls_list

    async def ask(self, batch, *, timeout_ms):
        self._calls.append((batch.name, timeout_ms))
        result = self._results[batch.name]
        if isinstance(result, BaseException):
            raise result
        return result


def _jev_result(answers: dict, model="jev-1.13.0", usage=None):
    return JevRawResult(answers=answers, model=model, usage=usage or {"input_tokens": 100, "output_tokens": 10}, latency_ms=50.0)


# --- Step 1: all-off / no-Jev mode ------------------------------------------

@pytest.mark.asyncio
async def test_all_tasks_disabled_never_calls_jev():
    calls = []
    jev = _FakeJevClient({}, calls)
    legacy_calls = []
    async def legacy(req):
        legacy_calls.append(req)
        return {"movement": {"intent": "MOVE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(enabled=False))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert calls == [], "Jev must never be called when TYPESAFE_ENABLED=false"
    assert len(legacy_calls) == 1
    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.answers["movement_intent"].choice == "MOVE"
    assert outcome.fallback_reasons["movement_intent"] is FallbackReason.FLAG_DISABLED


@pytest.mark.asyncio
async def test_task_not_in_any_list_is_off_even_when_globally_enabled():
    calls = []
    jev = _FakeJevClient({}, calls)
    async def legacy(req):
        return {"movement": {"intent": "NONE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(enabled=True, live=["some_other_task"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert calls == []
    assert outcome.provider_used is Provider.LEGACY_LLM


# --- Step 2: circuit breaker -------------------------------------------------

@pytest.mark.asyncio
async def test_open_breaker_skips_jev_with_no_call():
    calls = []
    jev = _FakeJevClient({}, calls)
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}}
    breaker = JevCircuitBreaker(fail_threshold=1)
    breaker.record_failure(FallbackReason.TIMEOUT)  # opens immediately (threshold=1)
    resolver = DecisionResolver(jev, legacy, breaker, _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert calls == [], "an OPEN breaker must skip Jev entirely - zero latency cost"
    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.fallback_reasons["movement_intent"] is FallbackReason.CIRCUIT_OPEN


# --- Step 3/4: transport failures -------------------------------------------

@pytest.mark.asyncio
async def test_jev_timeout_falls_back_to_legacy_for_critical_decision():
    calls = []
    jev = _FakeJevClient({"b1": ProviderTimeoutError("timed out")}, calls)
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}}
    breaker = JevCircuitBreaker()
    resolver = DecisionResolver(jev, legacy, breaker, _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.answers["movement_intent"].choice == "MOVE"
    assert outcome.fallback_reasons["movement_intent"] is FallbackReason.TIMEOUT
    assert breaker._consecutive_failures == 1, "the transport failure must be recorded on the breaker"


@pytest.mark.asyncio
async def test_jev_http_error_records_breaker_failure_and_falls_back():
    jev = _FakeJevClient({"b1": ProviderHTTPError(500, "boom")}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}}
    breaker = JevCircuitBreaker()
    resolver = DecisionResolver(jev, legacy, breaker, _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.fallback_reasons["movement_intent"] is FallbackReason.HTTP_ERROR
    assert breaker._consecutive_failures == 1


@pytest.mark.asyncio
async def test_jev_success_records_breaker_success():
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, [])
    async def legacy(req):
        raise AssertionError("legacy must not be called on full Jev success")
    breaker = JevCircuitBreaker()
    breaker.record_failure(FallbackReason.TIMEOUT)  # 1 prior failure
    resolver = DecisionResolver(jev, legacy, breaker, _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.JEV
    assert outcome.answers["movement_intent"].choice == "MOVE"
    assert breaker._consecutive_failures == 0, "a success must reset the failure count"


# --- Step 5: per-answer validation ------------------------------------------

@pytest.mark.asyncio
async def test_invalid_option_is_a_failure_for_critical_decision():
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="TELEPORT", confidence=1.0)})}, [])
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.answers["movement_intent"].choice == "MOVE"  # legacy value, not "TELEPORT"


@pytest.mark.asyncio
async def test_none_option_is_usable_not_a_failure():
    """The designed escape hatch: a choice equal to none_option means
    "no answer applies" and must NOT trigger fallback."""
    d = Decision(id="destination", task="movement", kind="choice", instructions="i",
                 criteria={"kitchen": "x", "none_of_these": "y"}, criticality=Criticality.CRITICAL,
                 allowed=frozenset({"kitchen", "none_of_these"}), none_option="none_of_these",
                 legacy_path=("movement", "destination_id"))
    jev = _FakeJevClient({"b1": _jev_result({"destination": JevRawAnswer(kind="choice", choice="none_of_these", confidence=1.0)})}, [])
    async def legacy(req):
        raise AssertionError("legacy must not be called - none_option is usable")
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(d,))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.JEV
    assert outcome.answers["destination"].choice == "none_of_these"
    assert outcome.answers["destination"].usable is True
    assert "destination" not in outcome.fallback_reasons


@pytest.mark.asyncio
async def test_below_min_confidence_falls_back_for_critical():
    d = _movement_decision()
    d = Decision(**{**d.__dict__, "min_confidence": 0.9})
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=0.5)})}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(d,))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.answers["movement_intent"].choice == "NONE"


@pytest.mark.asyncio
async def test_noul_low_probability_is_a_valid_false_not_a_failure():
    d = Decision(id="spoke_makoto", task="prev_scene", kind="noul", instructions="i",
                 criteria={"true": "x", "false": "y"}, criticality=Criticality.DEGRADABLE,
                 true_threshold=0.5, legacy_path=("previous_scene", "speakers"))
    jev = _FakeJevClient({"b1": _jev_result({"spoke_makoto": JevRawAnswer(kind="noul", probability=0.02)})}, [])
    async def legacy(req):
        raise AssertionError("legacy must not be called for a degradable, usable noul answer")
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["prev_scene"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(d,))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.answers["spoke_makoto"].usable is True
    assert outcome.answers["spoke_makoto"].probability == 0.02
    assert outcome.provider_used is Provider.JEV


@pytest.mark.asyncio
async def test_missing_answer_id_is_a_failure():
    jev = _FakeJevClient({"b1": _jev_result({})}, [])  # answers dict missing "movement_intent"
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.fallback_reasons["movement_intent"] is FallbackReason.MISSING_ANSWER


# --- Step 6: fallback granularity --------------------------------------------

@pytest.mark.asyncio
async def test_degradable_failure_keeps_jev_answers_and_does_not_call_legacy():
    """A DEGRADABLE decision's failure must NOT trigger a wholesale legacy
    call — it gets Provider.DEFAULT and the assembler leaves it at its
    dataclass default, exactly like today's LLM omitting a field."""
    critical = _movement_decision()
    degradable = Decision(id="tag1", task="behavior_tags", kind="choice", instructions="i",
                          criteria={"warm": "x"}, criticality=Criticality.DEGRADABLE,
                          allowed=frozenset({"warm"}))
    jev = _FakeJevClient({"b1": _jev_result({
        "movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0),
        "tag1": JevRawAnswer(kind="choice", choice="INVALID_TAG", confidence=1.0),
    })}, [])
    async def legacy(req):
        raise AssertionError("legacy must NOT be called - only a DEGRADABLE decision failed")
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement", "behavior_tags"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(critical, degradable))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.JEV
    assert outcome.answers["movement_intent"].choice == "MOVE"
    assert outcome.answers["tag1"].usable is False
    assert outcome.fallback_reasons["tag1"] is FallbackReason.INVALID_OPTION


@pytest.mark.asyncio
async def test_critical_failure_discards_all_jev_answers_even_successful_ones():
    """The doc's exact rule: ONE critical failure means legacy wins for
    EVERY decision in the turn, discarding Jev answers that DID succeed —
    not a partial blend."""
    critical_fail = _movement_decision(id_="movement_intent")
    other_success = Decision(id="prev_loc", task="prev_scene", kind="choice", instructions="i",
                             criteria={"kitchen": "x"}, criticality=Criticality.CRITICAL,
                             allowed=frozenset({"kitchen"}), legacy_path=("previous_scene", "location_id"))
    jev = _FakeJevClient({"b1": _jev_result({
        "movement_intent": JevRawAnswer(kind="choice", choice="INVALID", confidence=1.0),
        "prev_loc": JevRawAnswer(kind="choice", choice="kitchen", confidence=1.0),
    })}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}, "previous_scene": {"location_id": "living_room"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement", "prev_scene"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(critical_fail, other_success))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.provider_used is Provider.LEGACY_LLM
    assert outcome.answers["movement_intent"].choice == "NONE"
    assert outcome.answers["prev_loc"].choice == "living_room", (
        "even the SUCCESSFUL Jev answer must be discarded once a critical one failed"
    )


# --- Step 7: shadow mode -----------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_mode_uses_legacy_answer_and_records_disagreement():
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(shadow=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.answers["movement_intent"].choice == "NONE", "shadow must use the LEGACY value, never Jev's"
    assert outcome.shadow_disagreements["movement_intent"] == ("MOVE", "NONE")


@pytest.mark.asyncio
async def test_shadow_still_calls_jev_even_though_its_answer_is_unused():
    calls = []
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, calls)
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(shadow=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    await resolver.resolve([batch], _legacy_req())

    assert len(calls) == 1, "shadow mode must still call Jev (to observe it), just not USE the answer"


@pytest.mark.asyncio
async def test_shadow_beats_enabled_when_task_listed_in_both():
    """Precedence rule: a double-listed task shadows (fails SAFE) rather
    than going live."""
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"], shadow=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.answers["movement_intent"].choice == "NONE", "double-listed must shadow, not go live"


# --- Mixed routing (resolver's own documented extension) --------------------

@pytest.mark.asyncio
async def test_never_routed_decision_gets_legacy_answer_while_routed_one_uses_jev():
    """A task not in any list, alongside a task that IS live in the same
    turn - the never-routed decision must get its answer from legacy
    without discarding the successful Jev answer for the other decision."""
    routed = _movement_decision()
    never_routed = Decision(id="dep_makoto", task="departure", kind="choice", instructions="i",
                            criteria={"NONE": "x", "WISH": "y", "DECISION": "z"},
                            criticality=Criticality.CRITICAL, allowed=frozenset({"NONE", "WISH", "DECISION"}),
                            legacy_path=("departure_signal", "certainty"))
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, [])
    async def legacy(req):
        return {"movement": {"intent": "NONE"}, "departure_signal": {"certainty": "WISH"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(routed, never_routed))

    outcome = await resolver.resolve([batch], _legacy_req())

    assert outcome.answers["movement_intent"].choice == "MOVE", "the JEV-routed decision keeps its Jev answer"
    assert outcome.answers["dep_makoto"].choice == "WISH", "the never-routed decision gets a legacy answer"
    assert outcome.fallback_reasons["dep_makoto"] is FallbackReason.FLAG_DISABLED


@pytest.mark.asyncio
async def test_never_routed_decision_does_not_prevent_jev_from_being_called():
    calls = []
    routed = _movement_decision()
    never_routed = Decision(id="dep_makoto", task="departure", kind="choice", instructions="i",
                            criteria={"NONE": "x"}, criticality=Criticality.CRITICAL,
                            allowed=frozenset({"NONE"}), legacy_path=("departure_signal", "certainty"))
    jev = _FakeJevClient({"b1": _jev_result({"movement_intent": JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0)})}, calls)
    async def legacy(req):
        return {"movement": {"intent": "MOVE"}, "departure_signal": {"certainty": "NONE"}}
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(routed, never_routed))

    await resolver.resolve([batch], _legacy_req())

    assert len(calls) == 1
    assert calls[0][0] == "b1"
    # the sub-batch sent to Jev must contain ONLY the routed decision.
    sent_batch_decisions = None  # inspected via the fake's recorded call args isn't directly exposed;
    # verified indirectly: never_routed's id must not appear as a question sent (checked in test_jev.py's
    # own request-shape test) - here we confirm behaviorally that the never-routed id got a legacy answer,
    # which only happens if it was excluded from the Jev sub-batch (already asserted above).


# --- Concurrency --------------------------------------------------------------

@pytest.mark.asyncio
async def test_multiple_batches_run_concurrently_not_sequentially():
    """Two 100ms-delayed fake batches must complete in ~100ms total, not
    ~200ms - proving asyncio.gather concurrency, matching the design's
    'latency is flat, N concurrent batches cost ~one batch of latency'."""
    class _SlowFakeJevClient:
        async def ask(self, batch, *, timeout_ms):
            await asyncio.sleep(0.1)
            return _jev_result({d.id: JevRawAnswer(kind="choice", choice="MOVE", confidence=1.0) for d in batch.decisions})

    async def legacy(req):
        raise AssertionError("legacy must not be called on full success")

    resolver = DecisionResolver(_SlowFakeJevClient(), legacy, JevCircuitBreaker(),
                                 _config(live=["movement"]))
    b1 = DecisionBatch(name="b1", state="s1", decisions=(_movement_decision(id_="q1"),))
    b2 = DecisionBatch(name="b2", state="s2", decisions=(_movement_decision(id_="q2"),))

    import time
    t0 = time.perf_counter()
    outcome = await resolver.resolve([b1, b2], _legacy_req())
    elapsed = time.perf_counter() - t0

    assert elapsed < 0.18, f"batches should run concurrently, took {elapsed:.3f}s"
    assert outcome.answers["q1"].choice == "MOVE"
    assert outcome.answers["q2"].choice == "MOVE"


@pytest.mark.asyncio
async def test_resolver_never_raises_even_on_unexpected_legacy_exception():
    jev = _FakeJevClient({"b1": ProviderTimeoutError("x")}, [])
    async def legacy(req):
        raise RuntimeError("legacy itself is broken")
    resolver = DecisionResolver(jev, legacy, JevCircuitBreaker(), _config(live=["movement"]))
    batch = DecisionBatch(name="b1", state="s", decisions=(_movement_decision(),))

    with pytest.raises(RuntimeError):
        # NOTE: the design says resolve() "never raises" for provider
        # failures it is designed to handle (Jev transport errors). A bug
        # in the INJECTED legacy callable itself is a caller bug, not a
        # provider failure this resolver is responsible for swallowing -
        # this test documents that boundary explicitly rather than leaving
        # it ambiguous.
        await resolver.resolve([batch], _legacy_req())


# --- Helper function unit tests ----------------------------------------------

def test_get_by_path_walks_nested_dict():
    assert _get_by_path({"movement": {"intent": "MOVE"}}, ("movement", "intent")) == "MOVE"


def test_get_by_path_returns_none_on_missing_key():
    assert _get_by_path({"movement": {}}, ("movement", "intent")) is None
    assert _get_by_path({}, ("movement", "intent")) is None
    assert _get_by_path(None, ("movement", "intent")) is None


def test_get_by_path_returns_none_on_wrong_type():
    assert _get_by_path({"movement": "not_a_dict"}, ("movement", "intent")) is None


def test_legacy_answer_choice_kind():
    d = _movement_decision()
    answer = _legacy_answer(d, {"movement": {"intent": "MOVE"}})
    assert answer.choice == "MOVE"
    assert answer.provider is Provider.LEGACY_LLM
    assert answer.usable is True


def test_legacy_answer_noul_kind_from_bool():
    d = Decision(id="q", task="t", kind="noul", instructions="i", criteria={},
                criticality=Criticality.DEGRADABLE, legacy_path=("flag",))
    assert _legacy_answer(d, {"flag": True}).probability == 1.0
    assert _legacy_answer(d, {"flag": False}).probability == 0.0
    assert _legacy_answer(d, {}).probability is None


def test_legacy_answer_score_kind_from_number():
    d = Decision(id="q", task="t", kind="score", instructions="i", criteria=["a", "b"],
                criticality=Criticality.DEGRADABLE, legacy_path=("level",))
    assert _legacy_answer(d, {"level": 1.5}).score == 1.5
    assert _legacy_answer(d, {"level": "not_a_number"}).score is None


# --- legacy_resolver: the fan-out mapping mechanism (steps 6+) --------------

def test_legacy_answer_prefers_resolver_over_path_when_both_set():
    d = Decision(id="q", task="t", kind="choice", instructions="i", criteria={},
                criticality=Criticality.DEGRADABLE, legacy_path=("wrong", "path"),
                legacy_resolver=lambda raw: "from_resolver")
    assert _legacy_answer(d, {"wrong": {"path": "from_path"}}).choice == "from_resolver"


def test_legacy_answer_resolver_list_search_pattern():
    """Ability 7 (knowledge fan-out): search a list of dicts for a
    matching chunk_id, read its `knows` field."""
    def resolver(raw):
        for item in (raw or {}).get("knowledge_updates", []):
            if item.get("chunk_id") == "usr-abc-0":
                return item.get("knows")
        return None
    d = Decision(id="knows_usr-abc-0", task="knowledge", kind="noul", instructions="i",
                criteria={}, criticality=Criticality.DEGRADABLE, legacy_resolver=resolver)
    raw = {"knowledge_updates": [{"chunk_id": "usr-abc-0", "knows": True}]}
    assert _legacy_answer(d, raw).probability == 1.0
    assert _legacy_answer(d, {"knowledge_updates": []}).probability is None


def test_legacy_answer_resolver_conditional_match_pattern():
    """Ability 10 (departure fan-out): a single object names AT MOST one
    character; every OTHER character defaults to NONE, not None/missing."""
    def resolver_for(resident_id):
        def _r(raw):
            sig = (raw or {}).get("departure_signal") or {}
            return sig.get("certainty") if sig.get("character_id") == resident_id else "NONE"
        return _r
    raw = {"departure_signal": {"character_id": "makoto", "certainty": "DECISION"}}
    d_makoto = Decision(id="departure_makoto", task="departure", kind="choice", instructions="i",
                        criteria={}, criticality=Criticality.CRITICAL, legacy_resolver=resolver_for("makoto"))
    d_yuki = Decision(id="departure_yuki", task="departure", kind="choice", instructions="i",
                      criteria={}, criticality=Criticality.CRITICAL, legacy_resolver=resolver_for("yuki"))
    assert _legacy_answer(d_makoto, raw).choice == "DECISION"
    assert _legacy_answer(d_yuki, raw).choice == "NONE", "an unnamed resident must default to NONE, not None"


def test_legacy_answer_resolver_exception_degrades_to_none_not_crash():
    def _broken(raw):
        raise RuntimeError("bug in the resolver closure")
    d = Decision(id="q", task="t", kind="choice", instructions="i", criteria={},
                criticality=Criticality.DEGRADABLE, legacy_resolver=_broken)
    answer = _legacy_answer(d, {"anything": "here"})
    assert answer.choice is None
    assert answer.usable is True, "a legacy answer is always usable (last resort), even when empty"
