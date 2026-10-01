# backend/app/llm/chat.py
"""The one place that decides WHICH LLM the game talks to.

Three interchangeable sources, all speaking the OpenAI chat/completions shape
(Gemini via Google's OpenAI-compatibility endpoint, Ollama via its /v1 API):

    gemini  - Google Gemini, free tier (the default)
    openai  - OpenAI GPT
    ollama  - local Ollama, no key, no cloud calls

Selection is one env var, ``LLM_PROVIDER`` (default ``gemini``); ``LLM_MODEL``
overrides the provider's default model. ``settings.py`` resolves this once at
import and exposes the result as OPENAI_BASE_URL / OPENAI_API_KEY /
OPENAI_MODEL (the names every existing call site already imports), so flipping
the provider re-points the whole game. New code should call ``get_chat`` (or
``resolve_chat_config``) instead of building its own httpx request.

If gemini is selected but GEMINI_API_KEY is missing, resolution falls back to
openai (when its key exists) with a warning, so a missing Railway variable
degrades to the old behaviour instead of taking chat down.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Callable, Mapping

from backend.app.config.credentials import get_gemini_api_key, get_openai_api_key
from backend.app.llm.protocols import TextResult

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER = "gemini"
# Owner decision 2026-09-30: Gemini 3.8 Flash is the default. It is a thinking
# model whose hidden reasoning counts against max_tokens: at 50 tokens it
# returned empty content, at the game's 512 it answers fine. Don't lower
# max_tokens for Gemini calls; set LLM_MODEL=gemini-3.5-flash-lite for a
# cheaper non-reasoning-heavy alternative.
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
# Used only when the default model is overloaded (503/429) - see
# retry.post_with_model_fallback.
GEMINI_FALLBACK_MODEL = "gemini-3.5-flash-lite"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_DEFAULT_MODEL = "llama3.1:8b"


@dataclass(frozen=True)
class ChatConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    fallback_model: str = ""


@dataclass(frozen=True)
class _Spec:
    base_url: str
    model: str
    key: Callable[[], str]


_PROVIDERS: dict[str, _Spec] = {
    "gemini": _Spec(GEMINI_BASE_URL, GEMINI_DEFAULT_MODEL, get_gemini_api_key),
    "openai": _Spec(OPENAI_BASE_URL, OPENAI_DEFAULT_MODEL, get_openai_api_key),
    # Ollama ignores the bearer token but the transport always sends one.
    "ollama": _Spec(OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL, lambda: "ollama"),
}


def provider_names() -> list[str]:
    return sorted(_PROVIDERS)


def resolve_chat_config(
    provider: str | None = None,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
) -> ChatConfig:
    """Resolve (provider, base_url, api_key, model).

    Precedence for provider: argument > LLM_PROVIDER > gemini. For model:
    argument > LLM_MODEL (only when no explicit provider argument was given,
    so an explicit per-call provider never inherits another provider's model
    name) > the provider's default. OLLAMA_BASE_URL relocates Ollama.
    """
    env = os.environ if env is None else env
    name = (provider or env.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider {name!r}; choose one of {provider_names()}")

    spec = _PROVIDERS[name]
    api_key = spec.key()
    if name == "gemini" and not api_key:
        fallback_key = _PROVIDERS["openai"].key()
        if fallback_key:
            logger.warning("LLM_PROVIDER=gemini but GEMINI_API_KEY is not set; falling back to openai")
            name, spec, api_key = "openai", _PROVIDERS["openai"], fallback_key

    base_url = spec.base_url
    if name == "ollama":
        base_url = (env.get("OLLAMA_BASE_URL") or base_url)
    env_model = "" if provider else (env.get("LLM_MODEL") or "")
    return ChatConfig(
        provider=name,
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=(model or env_model or spec.model).strip(),
        fallback_model=GEMINI_FALLBACK_MODEL if name == "gemini" else "",
    )


async def get_chat(
    system: str,
    messages: list[dict],
    *,
    provider: str | None = None,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.8,
) -> TextResult:
    """Single chat entry point: send `system` + `messages` to the selected
    source and return its text. `messages` are the turns AFTER the system
    prompt. Raises ProviderTransportError subclasses on failure."""
    # Imported here so settings.py can import this module without pulling httpx
    # plumbing (and the factory's shared client) in at config time.
    from backend.app.llm.factory import get_shared_httpx_client
    from backend.app.llm.providers.openai_chat import OpenAIChatClient

    cfg = resolve_chat_config(provider, model)
    client = OpenAIChatClient(get_shared_httpx_client(), base_url=cfg.base_url, api_key=cfg.api_key)
    return await client.generate(
        model=cfg.model, system=system, messages=messages,
        max_tokens=max_tokens, temperature=temperature,
    )
