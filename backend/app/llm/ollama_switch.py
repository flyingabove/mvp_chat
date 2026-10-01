"""The Ollama master switch: off unless ``OLLAMA_ENABLED`` is truthy (owner decision 2026-10-01).

Simulations, the debug tools and the arena use Gemini + Jev by default, OpenAI + Jev as the alternative
(``LLM_PROVIDER``); the local Ollama path stays one switch away. Standard library only, so scripts can check it BEFORE
importing settings (settings read the environment once at import).
"""
from __future__ import annotations

import os
from typing import Mapping, Optional

ENV_VAR = "OLLAMA_ENABLED"
_TRUE = frozenset({"1", "true", "yes", "on"})


class OllamaDisabledError(ValueError):
    """Ollama was asked for while the switch is off (a ValueError: an unusable provider choice)."""


def ollama_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return str(env.get(ENV_VAR, "")).strip().lower() in _TRUE


def require_ollama(what: str, env: Optional[Mapping[str, str]] = None) -> None:
    """Raise OllamaDisabledError with one clear message unless the switch is on. `what` names the caller."""
    if not ollama_enabled(env):
        raise OllamaDisabledError(
            f"Ollama is switched off ({what}). Set {ENV_VAR}=1 to use it. "
            "The default providers are Gemini + Jev, or OpenAI + Jev (LLM_PROVIDER=openai).")
