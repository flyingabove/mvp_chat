"""
Dialogue fact extractor.

After each game turn, extracts factual statements from user messages and AI
responses, then packages them as session knowledge chunks with source-encoded IDs.

Chunk ID format:
  usr-{msg_id}-{n}   — fact extracted from a user message
  ai-{msg_id}-{n}    — fact extracted from an AI message

`extract_facts_from_message` never raises — all errors are caught and logged;
callers receive [] on failure. This is the ORIGINAL, still-used contract; many
callers (and tests) depend on a plain List[Dict] return, so it is preserved
unchanged.

Phase 1.2 adds `extract_facts_with_status`, a richer variant that distinguishes
"nothing to extract" from "the provider call failed" — the old `[]`-for-both
contract meant a provider outage was recorded as a successful empty extraction
and never retried. Durable call sites (backend/app/api/prompt_engine.py,
backend/app/main.py's recovery sweep) use this variant so a real failure can be
told apart from a genuinely fact-free message.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

import httpx

logger = logging.getLogger(__name__)

# Phase 1.2: bump this when _EXTRACTION_PROMPT or the chunk schema changes, so
# a re-extraction of the same message is stored as a DISTINCT row
# (extracted_chunks is keyed by (session_id, chunk_id, extractor_version)) —
# old and new-shaped extractions of the same message coexist rather than the
# new one silently overwriting a differently-shaped old one.
EXTRACTOR_VERSION = 1


@dataclass
class ExtractionResult:
    """Distinguishes the three outcomes a durable caller must treat differently.

    - ok=True,  chunks=[...]   -> Extracted: real facts found, store + mark done.
    - ok=True,  chunks=[]      -> EmptySuccess: genuinely nothing to extract from
                                   this message (e.g. "ok", "hi") — mark done,
                                   do NOT retry.
    - ok=False, chunks=[]      -> Failed: the provider call itself failed (HTTP
                                   error, timeout, malformed response) — must be
                                   retried, never marked done.
    """
    ok: bool
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""

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

    try:
        raw_sentences = await _call_extractor_llm(text)
    except Exception as exc:
        logger.debug("dialogue_extractor: _call_extractor_llm raised: %s", exc)
        return []
    return _sentences_to_chunks(raw_sentences, role, msg_id, character_id)


async def _call_extractor_llm(text: str) -> List[str]:
    """Call the LLM extraction endpoint.

    Phase 1.2: RAISES on any failure (HTTP error, timeout, malformed JSON)
    instead of swallowing to []. This is the actual distinguishing signal
    `extract_facts_with_status` needs — a caller that wants the old
    never-raises contract is `extract_facts_from_message`, which wraps this
    in its own try/except below, same effective behavior as before.
    """
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


def _sentences_to_chunks(
    sentences: List[str], role: Literal["user", "assistant"], msg_id: str, character_id: str,
) -> List[Dict[str, Any]]:
    prefix = "usr" if role == "user" else "ai"
    confidence = "player_stated" if role == "user" else "ai_stated"
    chunks: List[Dict[str, Any]] = []
    for n, sentence in enumerate(sentences[:5]):
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


async def extract_facts_with_status(
    text: str,
    role: Literal["user", "assistant"],
    msg_id: str,
    character_id: str,
) -> ExtractionResult:
    """Phase 1.2: like extract_facts_from_message, but distinguishes a
    provider failure from a genuinely fact-free message.

    An empty/whitespace-only message is EmptySuccess (ok=True, chunks=[]) —
    there was never anything to extract, not a failure worth retrying.
    """
    if not text or not text.strip():
        return ExtractionResult(ok=True, chunks=[])

    try:
        raw_sentences = await _call_extractor_llm(text)
    except Exception as exc:
        logger.debug("dialogue_extractor: extraction failed: %s", exc)
        return ExtractionResult(ok=False, chunks=[], error=f"{type(exc).__name__}: {exc}")

    return ExtractionResult(ok=True, chunks=_sentences_to_chunks(raw_sentences, role, msg_id, character_id))
