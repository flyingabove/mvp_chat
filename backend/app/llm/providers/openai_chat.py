# backend/app/llm/providers/openai_chat.py
"""Raw OpenAI-compatible chat/completions transport client.

Extracts the pattern duplicated across today's call sites (turn_extractor.py,
the storyteller call and Chinese translation call in prompt_engine.py,
location_extractor.py, dialogue_extractor.py, knowledge_resolution_extractor.py)
into one client, per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §5's
"Before/After" description: each of those sites builds its own
httpx.AsyncClient and hardcodes its own URL today; this is the shared
implementation they migrate to, one at a time, in later steps.

"OpenAI-compatible" because this same client (with a different base_url) is
what already lets the storyteller call point at a local Ollama instance in
local dev mode (STORY_MASTER_BASE_URL) — nothing here is OpenAI-specific
beyond the request/response shape, which Ollama's OpenAI-compatible endpoint
also speaks.

Step 2 note: this class is not wired to any existing call site yet. It
implements the TextProvider protocol (backend/app/llm/protocols.py) so a
future call site can be switched to it by construction, not by inheritance.
"""
from __future__ import annotations

import httpx

from backend.app.llm.protocols import TextResult
from backend.app.llm.providers.base import post_json


class OpenAIChatClient:
    """Implements TextProvider. One instance per (base_url, api_key) pair —
    e.g. one for OpenAI directly, one for the story-master endpoint (which
    may be Ollama in local dev). Uses an injected httpx.AsyncClient, never
    constructs its own (same lifecycle discipline as JevClient)."""

    def __init__(self, client: httpx.AsyncClient, *, base_url: str, api_key: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def generate(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> TextResult:
        """`messages` here means the conversation-history messages that come
        AFTER the system prompt — matching every existing call site's
        pattern of `[{"role": "system", ...}, *history, {"role": "user", ...}]`.
        This method prepends the system message itself, so callers pass the
        `system` string once instead of building the dict themselves.
        """
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        result = await post_json(
            self._client, f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json_body=payload,
            timeout_s=30.0,
        )
        content = str(result.body["choices"][0]["message"]["content"])
        return TextResult(text=content, model=result.model or model, usage=result.usage)
