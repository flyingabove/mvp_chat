"""
Dialogue fact extractor.

After each game turn, extracts factual statements from user messages and AI
responses, then packages them as session knowledge chunks with source-encoded IDs.

Chunk ID format:
  usr-{msg_id}-{n}   — fact extracted from a user message
  ai-{msg_id}-{n}    — fact extracted from an AI message

Never raises — all errors are caught and logged; callers receive [] on failure.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Literal

import httpx

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """\
Read the following dialogue turn and extract up to 5 short factual statements.

Rules:
- Each statement must be a single sentence that captures a CLAIM, BELIEF, or ASSERTION made in the text.
- Omit pleasantries, questions, emotional atmosphere, and stage directions.
- If the same fact is repeated, include it only once.
- If nothing factual is asserted, return an empty array.

Return ONLY a valid JSON array of strings. No explanation, no markdown, just the array.

Dialogue:
{text}"""


async def extract_facts_from_message(
    text: str,
    role: Literal["user", "assistant"],
    msg_id: str,
    character_id: str,
) -> List[Dict[str, Any]]:
    """Extract factual statements from a single message and return as chunk dicts.

    Args:
        text:         Raw message content.
        role:         "user" or "assistant" — determines chunk_id prefix.
        msg_id:       UUID hex for this message (12 chars, e.g. "a8f3c2d1b9e4").
        character_id: The active character for this session.

    Returns:
        List of chunk dicts (may be empty). Never raises.
    """
    if not text or not text.strip():
        return []

    prefix = "usr" if role == "user" else "ai"
    confidence = "player_stated" if role == "user" else "ai_stated"

    try:
        raw_sentences = await _call_extractor_llm(text)
    except Exception as exc:
        logger.debug("dialogue_extractor: _call_extractor_llm raised: %s", exc)
        return []
    chunks: List[Dict[str, Any]] = []
    for n, sentence in enumerate(raw_sentences[:5]):
        sentence = sentence.strip()
        if sentence:
            chunks.append({
                "chunk_id": f"{prefix}-{msg_id}-{n}",
                "character_id": character_id,
                "type": "dialogue_fact",
                "text": sentence,
                "confidence": confidence,
                "source_type": prefix,
                "source_msg_id": msg_id,
            })
    return chunks


async def _call_extractor_llm(text: str) -> List[str]:
    """Call the LLM extraction endpoint. Returns [] on any failure."""
    try:
        from backend.app.config.settings import (
            STORY_MASTER_API_KEY,
            STORY_MASTER_BASE_URL,
            OPENAI_MODEL,
        )

        prompt = _EXTRACTION_PROMPT.format(text=text[:2000])  # cap input length
        payload = {
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 300,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                f"{STORY_MASTER_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {STORY_MASTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        raw = data["choices"][0]["message"]["content"].strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(s) for s in parsed if isinstance(s, str) and s.strip()]
        return []

    except Exception as exc:
        logger.debug("dialogue_extractor: extraction failed: %s", exc)
        return []
