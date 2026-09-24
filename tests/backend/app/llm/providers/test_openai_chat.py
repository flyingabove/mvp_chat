"""Tests for OpenAIChatClient (backend/app/llm/providers/openai_chat.py).

Mocked httpx — no network. This client's request/response shape matches
the pattern already used throughout the codebase (verified against
turn_extractor.py's existing inline call at design time), so these tests
lock that shape, not a newly-invented one.
"""
import httpx
import pytest

from backend.app.llm.providers.base import ProviderHTTPError
from backend.app.llm.providers.openai_chat import OpenAIChatClient


class _FakeResponse:
    def __init__(self, status_code, json_body):
        self.status_code = status_code
        self._json_body = json_body
        self.text = str(json_body)

    def json(self):
        return self._json_body


@pytest.mark.asyncio
async def test_generate_sends_system_then_history_then_reads_content(monkeypatch):
    captured = {}

    async def _fake_post(self, url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse(200, {
            "model": "gpt-4o-mini-2024-07-18",
            "choices": [{"message": {"content": "the generated reply"}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        })

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    provider = OpenAIChatClient(client, base_url="https://api.openai.com/v1", api_key="sk-test")

    result = await provider.generate(
        model="gpt-4o-mini", system="You are a helpful assistant.",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=256, temperature=0.7,
    )

    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["messages"][0] == {"role": "system", "content": "You are a helpful assistant."}
    assert captured["json"]["messages"][1] == {"role": "user", "content": "hello"}
    assert captured["json"]["max_tokens"] == 256
    assert captured["json"]["temperature"] == 0.7
    assert result.text == "the generated reply"
    assert result.model == "gpt-4o-mini-2024-07-18"
    assert result.usage["prompt_tokens"] == 100
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_works_against_a_local_ollama_style_base_url(monkeypatch):
    """The whole point of this being a shared client: the storyteller call
    already supports pointing at a local Ollama instance in dev mode
    (STORY_MASTER_BASE_URL) — this client must work identically against
    that base_url, since it's the same OpenAI-compatible shape."""
    captured = {}

    async def _fake_post(self, url, *, headers, json, timeout):
        captured["url"] = url
        return _FakeResponse(200, {"model": "llama3", "choices": [{"message": {"content": "ok"}}], "usage": {}})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    provider = OpenAIChatClient(client, base_url="http://localhost:11434/v1", api_key="unused")
    await provider.generate(model="llama3", system="s", messages=[], max_tokens=100, temperature=0.0)
    assert captured["url"] == "http://localhost:11434/v1/chat/completions"
    await client.aclose()


@pytest.mark.asyncio
async def test_generate_raises_on_non_2xx(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(503, {"error": "overloaded"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    provider = OpenAIChatClient(client, base_url="https://api.openai.com/v1", api_key="sk-test")
    with pytest.raises(ProviderHTTPError):
        await provider.generate(model="gpt-4o-mini", system="s", messages=[], max_tokens=100, temperature=0.0)
    await client.aclose()
