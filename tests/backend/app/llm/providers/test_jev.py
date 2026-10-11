"""Tests for JevClient (backend/app/llm/providers/jev.py).

No network calls here — mocked httpx, matching the codebase's existing test
convention (see tests/backend/app/api/test_prompt_engine.py's client
fixture). The mocked response bodies below are the EXACT shapes captured
from live jev-1.13.0 responses during design research on 2026-09-22 (see
documentation/design/JEV.md §7 for the full evidence
trail) — this file locks that real behavior into a test rather than
inventing a plausible-looking mock shape.

A real end-to-end call against the live API (outside this test file, not
run in CI) was also verified while building this client: model resolved to
"jev-1.13.0", a coffee/tea/nothing choice question answered "coffee" with
confidence 1.0.
"""
import json

import httpx
import pytest

from backend.app.llm.decisions.types import Decision, DecisionBatch, Criticality
from backend.app.llm.providers.base import (
    ProviderHTTPError, ProviderMalformedResponseError, ProviderTimeoutError,
)
from backend.app.llm.providers.jev import JevClient, _build_criteria, _parse_answer


def _make_batch(*decisions):
    return DecisionBatch(name="test_batch", state="some dialogue state", decisions=tuple(decisions))


def _choice_decision(id_="movement_intent"):
    return Decision(id=id_, task="movement", kind="choice", instructions="i",
                     criteria={"MOVE": "x", "NONE": "y"}, criticality=Criticality.CRITICAL)


# --- _parse_answer: locked to real captured shapes -------------------------

def test_parse_answer_choice_matches_live_shape():
    """Real capture: destination question, six_strangers reachable-location test."""
    raw = {"type": "choice", "choice": "terrace", "confidence": 1.0,
           "probabilities": {"terrace": 1.0, "gotanda_station": 0.0, "kitchen": 0.0,
                              "none_of_these": 0.0, "living_room": 0.0, "boys_bedroom": 0.0}}
    answer = _parse_answer(raw)
    assert answer.kind == "choice"
    assert answer.choice == "terrace"
    assert answer.confidence == 1.0
    assert answer.probabilities["terrace"] == 1.0
    assert answer.score is None and answer.probability is None


def test_parse_answer_score_matches_live_shape_including_legend():
    """Real capture: attitude-strength question. `legend` is what makes the
    level->delta mapping auditable in code (design/JEV.md (extractor redesign)
    TC-11) — must survive parsing, not be dropped."""
    raw = {"type": "score", "score": 1.95, "confidence": 0.93,
           "legend": {"0": "no attitude expressed at all", "1": "mild or passing expression",
                      "2": "strong, emphatic expression"},
           "probabilities": {"0": 0.0, "1": 0.05, "2": 0.95}}
    answer = _parse_answer(raw)
    assert answer.kind == "score"
    assert answer.score == 1.95
    assert answer.confidence == 0.93
    assert answer.legend["2"] == "strong, emphatic expression"


def test_parse_answer_noul_matches_live_shape_and_has_no_confidence_field():
    """Real capture: knowledge-update noul question. TypeSafe's own docs and
    every live observation agree: noul has NO separate confidence field,
    only the probability itself. A parser that expects one would silently
    get None forever - this test pins that it's None BY DESIGN, not a bug."""
    raw = {"type": "noul", "noul": 0.95}
    answer = _parse_answer(raw)
    assert answer.kind == "noul"
    assert answer.probability == 0.95
    assert answer.confidence is None


def test_parse_answer_unknown_type_raises_malformed():
    with pytest.raises(ProviderMalformedResponseError):
        _parse_answer({"type": "something_new"})


# --- _build_criteria ---------------------------------------------------------

def test_build_criteria_choice_stays_a_dict():
    d = Decision(id="q", task="t", kind="choice", instructions="i",
                 criteria={"a": "desc"}, criticality=Criticality.DEGRADABLE)
    assert _build_criteria(d) == {"a": "desc"}


def test_build_criteria_score_becomes_a_list():
    d = Decision(id="q", task="t", kind="score", instructions="i",
                 criteria=["low", "high"], criticality=Criticality.DEGRADABLE)
    result = _build_criteria(d)
    assert isinstance(result, list)
    assert result == ["low", "high"]


# --- BL-18: live Jev rejects `noul` criteria sent as a list (HTTP 422) -------

def _noul_decision(criteria, id_="knows_c1"):
    return Decision(id=id_, task="t", kind="noul", instructions="i", criteria=criteria,
                    criticality=Criticality.DEGRADABLE)


def test_build_criteria_noul_list_becomes_the_documented_true_false_map():
    """Verified live 2026-09-29: a list gets HTTP 422 ("Input should be a valid dictionary"), the map is accepted."""
    result = _build_criteria(_noul_decision(["the character has been told this fact"]))
    assert result == {"true": "the character has been told this fact",
                      "false": "not: the character has been told this fact"}


def test_build_criteria_noul_with_several_lines_joins_them_into_one_condition():
    result = _build_criteria(_noul_decision(["they were told", "they saw it happen"]))
    assert result == {"true": "they were told; or they saw it happen",
                      "false": "not: they were told; or they saw it happen"}


def test_build_criteria_noul_map_is_left_alone():
    assert _build_criteria(_noul_decision({"carried_out": "it happened"})) == {"carried_out": "it happened"}


def test_build_criteria_noul_empty_list_still_yields_a_valid_map():
    assert isinstance(_build_criteria(_noul_decision([])), dict)


def test_every_noul_decision_the_game_builds_sends_a_dict():
    """The request-shape guard for every real noul decision the extractor registry builds."""
    from backend.app.engine.extractors import decision_registry as registry

    decisions = [
        registry.knowledge_decision("chunk1", "a fact"),
        *registry.knowledge_batch_decisions([{"chunk_id": "c1", "text": "a fact"}]),
        *registry.departure_batch_decisions(["ann", "ben"]),
        *registry.relationship_state_batch_decisions(["ann"]),
        *registry.relationship_history_batch_decisions(["ann"]),
    ]
    noul = [d for d in decisions if d.kind == "noul"]
    assert len(noul) >= 3, "expected the registry's noul decisions (knowledge and relationship history) to be built"
    assert any(d.id.startswith("relhist_") for d in noul) and any(d.id.startswith("knows_") for d in noul)
    for decision in noul:
        criteria = _build_criteria(decision)
        assert isinstance(criteria, dict) and set(criteria) == {"true", "false"}, decision.id


# --- JevClient.ask(): request shape + response parsing + error mapping ------

class _FakeResponse:
    def __init__(self, status_code, json_body, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text or json.dumps(json_body)

    def json(self):
        if self._json_body is None:
            raise ValueError("no body")
        return self._json_body


@pytest.mark.asyncio
async def test_ask_sends_correct_request_shape(monkeypatch):
    """Locks the exact request body shape verified against the live API
    (design/JEV.md (provider architecture) §8): model/state/questions,
    each question as {type, instructions, criteria}."""
    captured = {}

    async def _fake_post(self, url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(200, {
            "model": "jev-1.13.0",
            "answers": {"movement_intent": {"type": "choice", "choice": "MOVE", "confidence": 1.0,
                                             "probabilities": {"MOVE": 1.0, "NONE": 0.0}}},
            "usage": {"input_tokens": 10, "output_tokens": 5},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client, api_key="test-key", model="jev-latest")
    batch = _make_batch(_choice_decision())

    result = await jev.ask(batch, timeout_ms=1000)

    assert captured["url"] == "https://api.typesafe.ai/v1/systemone"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "jev-latest"
    assert captured["json"]["state"] == "some dialogue state"
    assert captured["json"]["questions"]["movement_intent"] == {
        "type": "choice", "instructions": "i", "criteria": {"MOVE": "x", "NONE": "y"},
    }
    assert result.model == "jev-1.13.0"
    assert result.answers["movement_intent"].choice == "MOVE"
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_logs_resolved_model_not_the_requested_alias(monkeypatch):
    """The plan requires knowing which version answered, since 'jev-latest'
    is a moving alias — the client must surface what the SERVER resolved,
    not just echo back what was requested."""
    async def _fake_post(self, url, *, headers, json, timeout):
        return _FakeResponse(200, {"model": "jev-1.13.0", "answers": {}, "usage": {}})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client, model="jev-latest")  # request the alias
    result = await jev.ask(_make_batch(), timeout_ms=1000)
    assert result.model == "jev-1.13.0"  # resolved, not the alias
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_raises_provider_timeout_error_on_timeout(monkeypatch):
    async def _fake_post(self, *a, **k):
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client)
    with pytest.raises(ProviderTimeoutError):
        await jev.ask(_make_batch(_choice_decision()), timeout_ms=1000)
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_raises_provider_http_error_on_non_2xx(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(500, {"detail": "internal error"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client)
    with pytest.raises(ProviderHTTPError) as exc_info:
        await jev.ask(_make_batch(_choice_decision()), timeout_ms=1000)
    assert exc_info.value.status_code == 500
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_raises_malformed_on_missing_answers_key(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(200, {"model": "jev-1.13.0", "usage": {}})  # no "answers"

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client)
    with pytest.raises(ProviderMalformedResponseError):
        await jev.ask(_make_batch(_choice_decision()), timeout_ms=1000)
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_raises_malformed_on_non_json_body(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(200, None, text="not json")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    jev = JevClient(client)
    with pytest.raises(ProviderMalformedResponseError):
        await jev.ask(_make_batch(_choice_decision()), timeout_ms=1000)
    await client.aclose()


@pytest.mark.asyncio
async def test_ask_multiple_questions_one_request():
    """Verified live property (design/JEV.md (provider architecture) §1):
    N questions in one DecisionBatch produce exactly ONE HTTP request, not N —
    this is what makes fan-out cheap."""
    call_count = {"n": 0}

    async def _fake_post(self, *a, **k):
        call_count["n"] += 1
        return _FakeResponse(200, {"model": "jev-1.13.0", "answers": {
            "q1": {"type": "noul", "noul": 0.9}, "q2": {"type": "noul", "noul": 0.1},
        }, "usage": {"input_tokens": 50, "output_tokens": 10}})

    import httpx as httpx_mod
    orig = httpx_mod.AsyncClient.post
    httpx_mod.AsyncClient.post = _fake_post
    try:
        client = httpx.AsyncClient()
        jev = JevClient(client)
        d1 = Decision(id="q1", task="t", kind="noul", instructions="i", criteria={}, criticality=Criticality.DEGRADABLE)
        d2 = Decision(id="q2", task="t", kind="noul", instructions="i", criteria={}, criticality=Criticality.DEGRADABLE)
        result = await jev.ask(_make_batch(d1, d2), timeout_ms=1000)
        assert call_count["n"] == 1
        assert len(result.answers) == 2
        await client.aclose()
    finally:
        httpx_mod.AsyncClient.post = orig
