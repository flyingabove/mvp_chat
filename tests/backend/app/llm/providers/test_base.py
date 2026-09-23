"""Tests for shared transport plumbing (backend/app/llm/providers/base.py)."""
import httpx
import pytest

from backend.app.llm.providers.base import (
    ProviderHTTPError, ProviderMalformedResponseError, ProviderTimeoutError,
    ProviderTransportError, post_json,
)


class _FakeResponse:
    def __init__(self, status_code, json_body, text=None):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if text is not None else str(json_body)

    def json(self):
        if self._json_body is None:
            raise ValueError("invalid json")
        return self._json_body


@pytest.mark.asyncio
async def test_post_json_returns_model_usage_and_latency(monkeypatch):
    async def _fake_post(self, url, *, headers, json, timeout):
        return _FakeResponse(200, {"model": "m1", "usage": {"input_tokens": 5}, "other": "field"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    result = await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    assert result.model == "m1"
    assert result.usage == {"input_tokens": 5}
    assert result.latency_ms >= 0.0
    assert result.body["other"] == "field"
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_defaults_missing_model_and_usage_gracefully():
    async def _fake_post(self, url, *, headers, json, timeout):
        return _FakeResponse(200, {"answers": {}})  # no "model", no "usage"

    import httpx as httpx_mod
    orig = httpx_mod.AsyncClient.post
    httpx_mod.AsyncClient.post = _fake_post
    try:
        client = httpx.AsyncClient()
        result = await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
        assert result.model == ""
        assert result.usage == {}
        await client.aclose()
    finally:
        httpx_mod.AsyncClient.post = orig


@pytest.mark.asyncio
async def test_post_json_raises_timeout_error_subclass_of_transport_error(monkeypatch):
    async def _fake_post(self, *a, **k):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderTransportError):
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_timeout_is_specifically_provider_timeout_error(monkeypatch):
    """A caller catching ProviderTimeoutError specifically (e.g. to
    distinguish TIMEOUT from HTTP_ERROR in the resolver's FallbackReason
    mapping) must be able to."""
    async def _fake_post(self, *a, **k):
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderTimeoutError):
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_raises_http_error_with_status_code_on_4xx(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(429, {"error": "rate limited"})

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderHTTPError) as exc_info:
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    assert exc_info.value.status_code == 429
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_raises_malformed_on_unparseable_body(monkeypatch):
    async def _fake_post(self, *a, **k):
        return _FakeResponse(200, None, text="not json at all")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderMalformedResponseError):
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_raises_malformed_on_non_dict_body(monkeypatch):
    """A JSON array or scalar at the top level is technically valid JSON
    but not a valid provider response — must still raise, not return a
    RawCallResult with a broken .body."""
    async def _fake_post(self, *a, **k):
        return _FakeResponse(200, ["not", "a", "dict"])

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderMalformedResponseError):
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    await client.aclose()


@pytest.mark.asyncio
async def test_post_json_never_retries_internally(monkeypatch):
    """Per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4: zero in-turn retries
    at the transport layer — the circuit breaker is the retry mechanism,
    across requests, not within one call."""
    call_count = {"n": 0}

    async def _fake_post(self, *a, **k):
        call_count["n"] += 1
        raise httpx.TimeoutException("boom")

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
    client = httpx.AsyncClient()
    with pytest.raises(ProviderTransportError):
        await post_json(client, "https://example.test/x", headers={}, json_body={}, timeout_s=1.0)
    assert call_count["n"] == 1
    await client.aclose()
