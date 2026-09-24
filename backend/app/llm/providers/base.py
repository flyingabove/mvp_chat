# backend/app/llm/providers/base.py
"""Shared transport plumbing for provider clients.

Deliberately minimal at this step. The full lifespan-scoped ClientRegistry
(one persistent httpx.AsyncClient per provider, replacing today's 18
per-call `httpx.AsyncClient(...)` construction sites) is
Phase 3 row 1's own scope — see
documentation/PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md §1 — and is
NOT built here. This module only defines the exception hierarchy and a tiny
shared POST helper both JevClient and OpenAIChatClient use, so error mapping
is consistent between them without duplicating boilerplate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx


class ProviderTransportError(Exception):
    """Base for any provider transport failure: timeout, connect error,
    non-2xx, or an unparseable body. Callers (the resolver) catch this one
    type regardless of which provider raised it."""


class ProviderTimeoutError(ProviderTransportError):
    pass


class ProviderHTTPError(ProviderTransportError):
    def __init__(self, status_code: int, body_preview: str) -> None:
        super().__init__(f"HTTP {status_code}: {body_preview[:200]}")
        self.status_code = status_code


class ProviderMalformedResponseError(ProviderTransportError):
    pass


@dataclass(frozen=True)
class RawCallResult:
    """What every provider client's raw call returns on success: the parsed
    body, resolved model id (never trust a moving alias — always read what
    the provider actually resolved), latency, and token usage."""
    body: dict
    model: str
    latency_ms: float
    usage: dict[str, int]


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json_body: dict,
    timeout_s: float,
) -> RawCallResult:
    """Shared POST + parse + error-mapping used by both JevClient and
    OpenAIChatClient. No retries here — retry policy (or lack of it, per
    JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4: zero in-turn retries for
    Jev, the circuit breaker is the retry mechanism ACROSS requests) is the
    resolver's decision, not this transport layer's.
    """
    t0 = time.perf_counter()
    try:
        r = await client.post(url, headers=headers, json=json_body, timeout=timeout_s)
    except httpx.TimeoutException as exc:
        raise ProviderTimeoutError(str(exc)) from exc
    except httpx.HTTPError as exc:
        raise ProviderTransportError(str(exc)) from exc
    latency_ms = (time.perf_counter() - t0) * 1000.0

    if r.status_code < 200 or r.status_code >= 300:
        raise ProviderHTTPError(r.status_code, r.text)

    try:
        body = r.json()
    except Exception as exc:
        raise ProviderMalformedResponseError(f"non-JSON body: {exc}") from exc

    if not isinstance(body, dict):
        raise ProviderMalformedResponseError(f"expected a JSON object, got {type(body).__name__}")

    return RawCallResult(
        body=body,
        model=str(body.get("model") or ""),
        latency_ms=latency_ms,
        usage=dict(body.get("usage") or {}),
    )
