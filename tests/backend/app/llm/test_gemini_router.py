"""call_gemini: use every free Gemini model's budget in quality order and never hit a limit (fake clock, fake client)."""
import asyncio
import json

import httpx
import pytest

from backend.app.llm import gemini_router as gr
from backend.app.llm.gemini_router import GeminiRouter, ModelSpec, call_gemini, llm_post

URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
BIG = ModelSpec("big", rpm=5, tpm=250_000, rpd=20, thinking=True)          # usable: 4 per minute, 19 a day
LITE = ModelSpec("lite", rpm=15, tpm=250_000, rpd=500)
SMALL = ModelSpec("small", rpm=30, tpm=16_000, rpd=14_400)


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


class FakeClient:
    """Answers per model from a script: status codes by model name, default 200."""

    def __init__(self, script=None, tokens=100):
        self.script, self.calls, self.tokens = script or {}, [], tokens

    async def post(self, url, headers=None, json=None, **kwargs):
        self.calls.append(json)
        outcome = self.script.get(json["model"], 200)
        outcome = outcome.pop(0) if isinstance(outcome, list) else outcome
        if isinstance(outcome, Exception):
            raise outcome
        status, body = outcome if isinstance(outcome, tuple) else (outcome, None)
        body = body if body is not None else ({"choices": [{"message": {"content": "ok"}}],
                                               "usage": {"total_tokens": self.tokens}} if status == 200 else {"error": "x"})
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))


def _body(model="big", content="hi", max_tokens=100):
    return {"model": model, "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": content}],
            "max_tokens": max_tokens}


def _run(client, body, router, clock, **kwargs):
    return asyncio.run(call_gemini(client, URL, headers={}, json=body, router=router, sleep=clock.sleep, **kwargs))


def _router(clock, *models, path=None):
    return GeminiRouter(models or (BIG, LITE), clock=clock, state_path=path)


def _models_used(client):
    return [c["model"] for c in client.calls]


def test_the_best_model_is_used_first_then_the_next_when_its_minute_is_full():
    clock = Clock()
    router, client = _router(clock), FakeClient()
    for _ in range(6):
        assert _run(client, _body(), router, clock).status_code == 200
    assert _models_used(client) == ["big"] * 4 + ["lite"] * 2          # 5 RPM keeps one slot of margin


def test_a_full_minute_frees_up_and_the_better_model_is_used_again():
    clock = Clock()
    router, client = _router(clock), FakeClient()
    for _ in range(5):
        _run(client, _body(), router, clock)
    clock.now += 61
    _run(client, _body(), router, clock)
    assert _models_used(client)[-1] == "big"


def test_the_daily_budget_moves_to_the_next_model_and_a_new_pacific_day_resets_it():
    clock = Clock()
    router, client = _router(clock, BIG, LITE), FakeClient()
    for _ in range(19):
        _run(client, _body(), router, clock)
        clock.now += 20                                                  # stay under the minute limit
    assert set(_models_used(client)) == {"big"}
    _run(client, _body(), router, clock)
    assert _models_used(client)[-1] == "lite" and router.snapshot()["big"]["used_today"] == 19
    clock.now += 86_400
    _run(client, _body(), router, clock)
    assert _models_used(client)[-1] == "big" and router.snapshot()["big"]["used_today"] == 1


def test_a_request_for_a_lite_model_never_climbs_to_a_bigger_one():
    clock = Clock()
    router, client = _router(clock, BIG, LITE), FakeClient()
    _run(client, _body(model="lite"), router, clock)
    assert _models_used(client) == ["lite"]
    assert router.start_index("not-a-known-model") == 0 and router.start_index("gemini-3-flash") == 0


def test_a_429_blocks_the_model_and_the_call_succeeds_on_the_next():
    clock = Clock()
    per_minute = (429, {"error": {"details": [{"retryDelay": "23s"}]}})
    router, client = _router(clock), FakeClient({"big": [per_minute]})
    assert _run(client, _body(), router, clock).status_code == 200
    assert _models_used(client) == ["big", "lite"]
    assert 20 < router.snapshot()["big"]["blocked_for_s"] <= 23 and not router.snapshot()["big"]["exhausted"]
    _run(client, _body(), router, clock)
    assert _models_used(client)[-1] == "lite"                            # still cooling


def test_a_per_day_429_turns_the_model_off_until_the_reset():
    clock = Clock()
    daily = (429, {"error": {"message": "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier"}})
    router, client = _router(clock), FakeClient({"big": [daily]})
    _run(client, _body(), router, clock)
    assert router.snapshot()["big"]["exhausted"] is True
    for _ in range(3):
        _run(client, _body(), router, clock)
    assert _models_used(client) == ["big", "lite", "lite", "lite", "lite"][:len(client.calls)] and "big" not in _models_used(client)[1:]


def test_5xx_and_missing_models_are_skipped_and_cooled():
    clock = Clock()
    router, client = _router(clock, BIG, LITE), FakeClient({"big": [503]})
    assert _run(client, _body(), router, clock).status_code == 200
    assert 0 < router.snapshot()["big"]["blocked_for_s"] <= gr.COOLDOWN_5XX_S
    router, client = _router(clock, BIG, LITE), FakeClient({"big": [404]})
    _run(client, _body(), router, clock)
    assert router.snapshot()["big"]["blocked_for_s"] > 3000


def test_when_every_model_is_only_momentarily_full_it_waits_instead_of_failing():
    clock = Clock()
    router, client = _router(clock, BIG), FakeClient()
    for _ in range(4):
        _run(client, _body(), router, clock)
    clock.now += 55                                                      # the oldest call leaves the window in ~5 s
    before = clock.now
    assert _run(client, _body(), router, clock).status_code == 200
    assert 0 < clock.now - before <= gr.MAX_WAIT_S and len(client.calls) == 5


def test_it_gives_up_with_a_429_when_the_wait_is_too_long_or_the_day_is_spent():
    clock = Clock()
    router, client = _router(clock, BIG), FakeClient()
    for _ in range(4):
        _run(client, _body(), router, clock)
    response = _run(client, _body(), router, clock, max_wait_s=1.0)
    assert response.status_code == 429 and "limit" in response.text and len(client.calls) == 4
    router.block_for_day("big")
    assert _run(client, _body(), router, clock).status_code == 429


def test_token_budgets_count_the_estimate_then_the_real_usage():
    clock = Clock()
    router, client = _router(clock, SMALL, LITE), FakeClient(tokens=15_000)
    _run(client, _body(model="small"), router, clock)
    _run(client, _body(model="small"), router, clock)                  # 15K already used of its 14.4K: next goes on
    assert _models_used(client) == ["small", "lite"]
    huge = _body(model="small", content="x" * 100_000)                 # bigger than its whole minute: lite takes it
    _run(client, huge, router, clock)
    assert _models_used(client)[-1] == "lite"


def test_the_callers_body_is_never_changed_and_the_model_is_swapped_in():
    body = _body()
    sent = gr._prepare(body, LITE)
    assert sent["model"] == "lite" and body["model"] == "big" and sent["messages"] is body["messages"]


def test_a_refused_request_stops_after_two_models_and_an_auth_error_stops_at_once():
    clock = Clock()
    router, client = _router(clock, BIG, LITE, SMALL), FakeClient({"big": 400, "lite": 400, "small": 400})
    assert _run(client, _body(), router, clock).status_code == 400 and len(client.calls) == 2
    router, client = _router(clock, BIG, LITE), FakeClient({"big": 403})
    assert _run(client, _body(), router, clock).status_code == 403 and len(client.calls) == 1


def test_a_dropped_connection_is_refunded_and_tried_on_the_next_model():
    clock = Clock()
    router, client = _router(clock), FakeClient({"big": [httpx.ReadTimeout("slow")]})
    assert _run(client, _body(), router, clock).status_code == 200
    assert router.snapshot()["big"]["used_today"] == 0 and router.snapshot()["big"]["blocked_for_s"] > 0
    router, client = _router(clock, BIG), FakeClient({"big": [httpx.ReadTimeout("slow")]})
    with pytest.raises(httpx.TransportError):
        _run(client, _body(), router, clock)


def test_day_counters_survive_a_restart_but_not_a_new_day(tmp_path):
    clock, path = Clock(), tmp_path / "state.json"
    router = _router(clock, path=path)
    for _ in range(3):
        _run(FakeClient(), _body(), router, clock)
        clock.now += 20
    assert GeminiRouter((BIG, LITE), clock=clock, state_path=path).snapshot()["big"]["used_today"] == 3
    clock.now += 86_400
    assert GeminiRouter((BIG, LITE), clock=clock, state_path=path).snapshot()["big"]["used_today"] == 0
    path.write_text("not json", encoding="utf-8")
    assert GeminiRouter((BIG,), clock=clock, state_path=path).snapshot()["big"]["used_today"] == 0


def test_llm_post_routes_only_gemini_urls_and_can_be_switched_off(monkeypatch):
    clock = Clock()
    monkeypatch.setenv("GEMINI_ROUTER", "on")
    gemini, other = FakeClient(), FakeClient()
    monkeypatch.setattr(gr, "_router", _router(clock))
    asyncio.run(llm_post(gemini, URL, headers={}, json=_body(model="lite")))
    assert _models_used(gemini) == ["lite"]
    asyncio.run(llm_post(other, "https://api.openai.com/v1/chat/completions", headers={}, json=_body(model="gpt-4o-mini")))
    assert _models_used(other) == ["gpt-4o-mini"]
    monkeypatch.setenv("GEMINI_ROUTER", "off")
    off = FakeClient()
    asyncio.run(llm_post(off, URL, headers={}, json=_body(model="whatever")))
    assert _models_used(off) == ["whatever"]


def test_the_shipped_table_is_ordered_best_first_with_unique_names_and_sane_limits():
    names = [m.name for m in gr.MODELS]
    assert len(set(names)) == len(names) and names[0] == "gemini-3.8-flash"
    assert all(m.rpm > 0 and m.tpm > 0 and m.rpd > 0 for m in gr.MODELS)
    assert gr.pacific_day(1_800_000_000.0) != gr.pacific_day(1_800_000_000.0 + 86_400)


def test_reasoning_models_get_low_effort_unless_the_caller_chose_one_and_others_never():
    assert gr._prepare(_body(), BIG)["reasoning_effort"] == "low"
    assert "reasoning_effort" not in gr._prepare(_body(), LITE)
    assert gr._prepare({**_body(), "reasoning_effort": "high"}, BIG)["reasoning_effort"] == "high"
    assert all(m.thinking for m in gr.MODELS if "lite" not in m.name) and not any(m.thinking for m in gr.MODELS if "lite" in m.name)


def _cut(content, finish="length"):
    return (200, {"choices": [{"message": {"content": content}, "finish_reason": finish}], "usage": {"total_tokens": 50}})


def test_a_reply_cut_off_by_max_tokens_is_retried_on_the_next_model_when_a_whole_answer_was_needed():
    clock = Clock()
    schema = {**_body(), "response_format": {"type": "json_schema"}}
    router, client = _router(clock), FakeClient({"big": [_cut('{"segments": [{"kind": "narr')]})
    response = _run(client, schema, router, clock)
    assert _models_used(client) == ["big", "lite"] and response.json()["choices"][0]["message"]["content"] == "ok"
    router, client = _router(clock), FakeClient({"big": [_cut("")]})                     # empty and cut off: also retried
    _run(client, _body(), router, clock)
    assert _models_used(client) == ["big", "lite"]


def test_plain_text_cut_at_the_callers_limit_and_complete_json_are_returned_as_is():
    clock = Clock()
    router, client = _router(clock), FakeClient({"big": [_cut("a long answer that just ran out")]})
    _run(client, _body(), router, clock)
    assert _models_used(client) == ["big"]                                               # plain text cut at max_tokens is the caller's limit
    router, client = _router(clock), FakeClient({"big": [_cut('{"ok": true}')]})
    _run(client, {**_body(), "response_format": {"type": "json_object"}}, router, clock)
    assert _models_used(client) == ["big"]                                               # complete JSON is fine even at the limit
