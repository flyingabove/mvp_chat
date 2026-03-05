from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, List

import httpx

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_MODEL, EXTRACTOR_TURNS


@dataclass(frozen=True)
class KnowledgeResolution:
    chunk_id: str
    knows: bool
    confidence: float
    reason: str = ""


class KnowledgeResolutionExtractor:
    """LLM extractor that resolves whether an NPC knows an ambiguously-labeled chunk."""

    def __init__(self, model: str | None = None):
        self.model = model or OPENAI_MODEL

    @staticmethod
    def _parse_json(content: str) -> List[KnowledgeResolution]:
        try:
            obj = json.loads(content)
        except Exception:
            return []

        rows = obj.get("updates") if isinstance(obj, dict) else None
        if not isinstance(rows, list):
            return []

        out: List[KnowledgeResolution] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            chunk_id = str(item.get("chunk_id") or "").strip()
            if not chunk_id:
                continue
            knows = bool(item.get("knows", False))
            try:
                confidence = float(item.get("confidence", 0.0))
            except Exception:
                confidence = 0.0
            confidence = max(0.0, min(1.0, confidence))
            reason = str(item.get("reason") or "").strip()
            out.append(KnowledgeResolution(
                chunk_id=chunk_id,
                knows=knows,
                confidence=confidence,
                reason=reason,
            ))
        return out

    async def extract(
        self,
        *,
        speaker_id: str,
        user_msg: str,
        assistant_reply: str,
        candidate_chunks: List[Dict[str, Any]],
        conversation_log: List[Dict[str, str]] | None = None,
    ) -> List[KnowledgeResolution]:
        if not candidate_chunks:
            return []

        system = (
            "You are an epistemic-state extractor for a narrative game engine.\n"
            "Given recent dialogue and candidate knowledge chunks, decide if the active NPC speaker appears to KNOW each chunk after this turn.\n"
            "Use best reasonable inference from role, statements, and user corrections.\n"
            "Return ONLY JSON.\n"
            "If confidence is low or unknown, omit the chunk from updates.\n"
            "JSON schema:\n"
            "{\n"
            '  "updates": [\n'
            "    {\n"
            '      "chunk_id": "string",\n'
            '      "knows": true|false,\n'
            '      "confidence": 0.0,\n'
            '      "reason": "short explanation"\n'
            "    }\n"
            "  ]\n"
            "}\n"
        )

        history: List[Dict[str, str]] = []
        for m in (conversation_log or []):
            role = str(m.get("role", "")).strip()
            if role not in {"user", "assistant"}:
                continue
            history.append({"role": role, "content": str(m.get("content", ""))})
        history = history[-EXTRACTOR_TURNS:]

        candidates_text = []
        for c in candidate_chunks[:12]:
            cid = str(c.get("chunk_id") or "").strip()
            ctext = str(c.get("text") or "").strip()
            if not cid or not ctext:
                continue
            candidates_text.append(f"- {cid}: {ctext[:500]}")

        if not candidates_text:
            return []

        user_content = (
            f"Speaker id: {speaker_id}\n"
            f"Latest player message: {user_msg}\n"
            f"Latest assistant reply: {assistant_reply}\n\n"
            "Candidate chunks:\n"
            + "\n".join(candidates_text)
        )

        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 300,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
        except Exception:
            return []

        if r.status_code < 200 or r.status_code >= 300:
            return []

        try:
            data = r.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            return []

        return self._parse_json(content)
