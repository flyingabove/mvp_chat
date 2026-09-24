# backend/app/llm/factory.py
"""Wiring for the default (production) DecisionResolver.

The circuit breaker and the shared httpx.AsyncClient are process-wide
singletons (the breaker's whole purpose is remembering failures ACROSS
requests — a fresh one per call would never trip). JevConfig is read once at
construction time, matching every other settings.py value in this codebase
(a Railway env var change already requires a redeploy to take effect, same
as TYPESAFE_ENABLED itself).

The `legacy` callable is NOT shared — it's bound per-caller (e.g. to one
TurnExtractor instance's own _call_legacy_raw method), since it may need
that instance's own configuration (self.model). build_default_resolver()
is called once per TurnExtractor instance, not per turn.
"""
from __future__ import annotations

import httpx

from backend.app.llm.decisions.health import JevCircuitBreaker
from backend.app.llm.decisions.resolver import DecisionResolver, JevConfig, LegacyExtractionCallable
from backend.app.llm.providers.jev import JevClient

_shared_httpx_client: httpx.AsyncClient | None = None
_shared_breaker: JevCircuitBreaker | None = None


def get_shared_httpx_client() -> httpx.AsyncClient:
    """Process-wide client for the JevClient used by the default resolver.

    NOTE: this is a temporary, minimal client — Phase 3 row 1
    (PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md §1) specifies a full
    lifespan-managed ClientRegistry with per-provider connection limits and
    clean shutdown. That is not built yet; this getter exists so today's
    wiring has exactly one place to upgrade later, not eighteen.
    """
    global _shared_httpx_client
    if _shared_httpx_client is None:
        _shared_httpx_client = httpx.AsyncClient()
    return _shared_httpx_client


def get_shared_breaker() -> JevCircuitBreaker:
    """The ONE breaker instance for the whole process — see module
    docstring for why this must never be constructed fresh per call."""
    global _shared_breaker
    if _shared_breaker is None:
        _shared_breaker = JevCircuitBreaker.from_settings()
    return _shared_breaker


def reset_shared_state_for_tests() -> None:
    """Test-only: forces fresh singletons on next access. Production code
    never calls this."""
    global _shared_httpx_client, _shared_breaker
    _shared_httpx_client = None
    _shared_breaker = None


def build_default_resolver(legacy: LegacyExtractionCallable) -> DecisionResolver:
    """Constructs a DecisionResolver wired to the real JevClient and the
    shared process-wide breaker, reading current flag/timeout config from
    settings.py. Safe to call even when TYPESAFE_ENABLED=false — the
    resolver's own routing logic (JevConfig.routing_for) makes every
    decision resolve via `legacy` alone in that case; JevClient is
    constructed but never invoked.
    """
    jev = JevClient(get_shared_httpx_client())
    return DecisionResolver(
        jev=jev,
        legacy=legacy,
        health=get_shared_breaker(),
        config=JevConfig.from_settings(),
    )
