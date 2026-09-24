"""Tests for LLMDecisionClient: a generative model answering a DecisionBatch
in the same shape as JevClient, so the arena judge works unchanged."""
import json

import httpx
import pytest

from backend.app.evaluation.evidence import build_packet
from backend.app.evaluation.fakes import make_arm, tiny_bundle
from backend.app.evaluation.judge import JevPairwiseJudge, build_decisions
from backend.app.evaluation.pipeline import judge_arms
from backend.app.evaluation.rubric import DEFAULT_RUBRIC
from backend.app.llm.decisions.types import DecisionBatch
from backend.app.llm.providers.base import ProviderMalformedResponseError
from backend.app.llm.providers.llm_decisions import LLMDecisionClient

REPLIES = ["Mina waves.", "Jun hands you tea."]


def transport(answer_fn, seen=None):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if seen is not None:
            seen.append(body)
        questions = json.loads(body["messages"][1]["content"].split("QUESTIONS:\n", 1)[1])
        answers = answer_fn(questions, body["messages"][1]["content"])
        return httpx.Response(200, json={"model": "gpt-4o-mini-2024-07-18",
                                         "choices": [{"message": {"content": json.dumps({"answers": answers})}}],
                                         "usage": {"prompt_tokens": 1200, "completion_tokens": 300}})
    return httpx.MockTransport(handler)


def prefer_side_without(marker):
    def answer(questions, content):
        state = content.split("QUESTIONS:\n", 1)[0]
        a, b = state.find("=== TRANSCRIPT A"), state.find("=== TRANSCRIPT B")
        bad = {s for s, text in (("A", state[a:b]), ("B", state[b:])) if marker in text}
        out = {}
        for qid, q in questions.items():
            if q["type"] == "choice" and qid.startswith("cmp_"):
                out[qid] = {"choice": "tie" if len(bad) != 1 else ("B" if "A" in bad else "A"), "confidence": 0.8}
            elif q["type"] == "choice":
                out[qid] = {"choice": "none", "confidence": 0.9}
            elif q["type"] == "score":
                out[qid] = {"score": 1 if qid.split("_")[1] in bad else 3}
            else:
                out[qid] = {"probability": 0.9 if qid.split("_")[1] in bad else 0.05}
        return out
    return answer


def batch():
    packet = build_packet(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", REPLIES), 0, 4)
    return DecisionBatch("t", packet.state, build_decisions(DEFAULT_RUBRIC, packet))


@pytest.mark.asyncio
async def test_one_request_per_batch_in_json_mode_with_all_questions():
    seen = []
    async with httpx.AsyncClient(transport=transport(prefer_side_without("BAD"), seen)) as c:
        result = await LLMDecisionClient(c, base_url="https://x/v1", api_key="k", model="gpt-4o-mini").ask(
            batch(), timeout_ms=1000)
    assert len(seen) == 1 and seen[0]["response_format"] == {"type": "json_object"}
    assert set(result.answers) == {d.id for d in batch().decisions}
    assert result.usage == {"input_tokens": 1200, "output_tokens": 300}


@pytest.mark.asyncio
async def test_choice_distribution_is_synthesized_from_stated_confidence():
    async with httpx.AsyncClient(transport=transport(prefer_side_without("BAD"))) as c:
        result = await LLMDecisionClient(c, base_url="https://x/v1", api_key="k", model="m").ask(batch(), timeout_ms=1000)
    probs = result.answers["cmp_canon"].probabilities
    assert probs["tie"] == pytest.approx(0.8) and sum(probs.values()) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_unusable_answers_are_left_out_for_the_judge_to_fail_closed():
    def junk(questions, content):
        return {"cmp_canon": {"choice": "A"}, "score_A_canon": {"score": "high"}, "probe_A_secret_leak": "yes"}

    async with httpx.AsyncClient(transport=transport(junk)) as c:
        result = await LLMDecisionClient(c, base_url="https://x/v1", api_key="k", model="m").ask(batch(), timeout_ms=1000)
    assert "cmp_canon" in result.answers
    assert "score_A_canon" not in result.answers and "probe_A_secret_leak" not in result.answers


@pytest.mark.asyncio
async def test_non_json_content_raises_malformed():
    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "I think A is better."}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(ProviderMalformedResponseError):
            await LLMDecisionClient(c, base_url="https://x/v1", api_key="k", model="m").ask(batch(), timeout_ms=1000)


@pytest.mark.asyncio
async def test_reuses_the_jev_judge_end_to_end_including_order_swap():
    """The whole Jev pipeline runs unchanged on top of the LLM client; a dated
    resolved model name (gpt-4o-mini-2024-07-18) is not a pin mismatch."""
    async with httpx.AsyncClient(transport=transport(prefer_side_without("BAD"))) as c:
        judge = JevPairwiseJudge(LLMDecisionClient(c, base_url="https://x/v1", api_key="k", model="gpt-4o-mini"),
                                 DEFAULT_RUBRIC, model="gpt-4o-mini", backoff_s=0)
        res = await judge_arms(tiny_bundle(), make_arm("beta", REPLIES), make_arm("prod", ["BAD"] + REPLIES[1:]),
                               judge, DEFAULT_RUBRIC, 8)
    assert all(not c.error for c in res.calls) and len(res.calls) == 2
    assert {v["value"] for v in res.windows[0]["dimensions"].values()} == {1.0}
