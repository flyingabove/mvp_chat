# backend/app/engine/extractors/location_extractor.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Optional

import httpx

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, EXTRACTOR_TURNS


class LocationIntent(str, Enum):
    NONE = "NONE"
    MOVE = "MOVE"


@dataclass(frozen=True)
class LocationExtraction:
    intent: LocationIntent
    destination_id: Optional[str]
    confidence: float
    destination_text: str = ""  # raw text span the user typed (for logs only)


class LocationExtractor:
    """
    Lightweight, schema-validated location intent extractor.

    Returns a LocationExtraction object (never dict/list).
    """

    def __init__(self, model: str | None = None):
        self.model = model or OPENAI_MODEL

    async def _should_attempt(self, user_msg: str, conversation_log: list = None) -> bool:
        """
        Use LLM to determine if the message expresses a movement intent.
        This is more robust than regex and handles natural language variations.
        """
        s = (user_msg or "").strip()
        if not s:
            return False

        system = (
            "You are a classifier for movement intents in a text adventure game.\n"
            "Return ONLY valid JSON and nothing else.\n"
            "Determine if the user message is expressing an intent to move/travel to a location.\n"
            "Only return true for explicit movement commands like 'go to X', 'move to X', 'travel to X', 'head to X', etc.\n"
            "Return false for questions or hypotheticals like 'can we go to X?' or 'should I go to X?'.\n"
            'JSON schema: {"is_movement_intent": true|false}\n'
        )

        # Build messages with conversation history
        messages = [{"role": "system", "content": system}]

        # Add conversation history (limited to EXTRACTOR_TURNS)
        if conversation_log:
            history = [m for m in conversation_log if m.get("role") != "system"]
            history = history[-EXTRACTOR_TURNS:] if len(history) > EXTRACTOR_TURNS else history
            messages.extend(history)

        # Add current user message
        messages.append({"role": "user", "content": f"User message: {user_msg}\n"})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 50,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # Deferred per test_engine_purity: engine/ keeps llm/ imports function-local.
                from backend.app.llm.retry import post_with_retry
                r = await post_with_retry(
                    client,
                    f"{OPENAI_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
            
            if r.status_code < 200 or r.status_code >= 300:
                return False
            
            data = r.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
            
            try:
                obj = json.loads(content)
                return bool(obj.get("is_movement_intent", False))
            except Exception:
                return False
        except Exception:
            return False

    @staticmethod
    def _build_locations_block(world_graph) -> str:
        """
        Build a compact list of known locations (id + name) for disambiguation.
        No arrays are returned; this is just prompt text.
        """
        lines: list[str] = []
        locs = getattr(world_graph, "locations", {}) or {}
        for loc_id, loc in locs.items():
            name = getattr(loc, "name", "")
            name = (name or "").strip()
            if name:
                lines.append(f"- {loc_id}: {name}")
            else:
                lines.append(f"- {loc_id}")
            # Include every authored destination. A fixed node-count cap silently
            # made later locations unreachable to the extractor in larger worlds.
        return "\n".join(lines)

    @staticmethod
    def _parse_json(content: str) -> LocationExtraction:
        try:
            obj = json.loads(content)
        except Exception:
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")

        action = str(obj.get("intent") or obj.get("action") or "NONE").strip().upper()
        if action not in ("MOVE", "NONE"):
            action = "NONE"

        dest_id = obj.get("destination_id")
        if dest_id is not None:
            dest_id = str(dest_id).strip() or None

        conf = obj.get("confidence")
        try:
            conf_f = float(conf)
        except Exception:
            conf_f = 0.0
        conf_f = max(0.0, min(1.0, conf_f))

        dest_text = str(obj.get("destination_text") or "").strip()

        return LocationExtraction(
            intent=LocationIntent.MOVE if action == "MOVE" else LocationIntent.NONE,
            destination_id=dest_id,
            confidence=conf_f,
            destination_text=dest_text,
        )

    async def extract(self, user_msg: str, *, world_graph, knowledge_chunks: list = None, conversation_log: list = None) -> LocationExtraction:
        """
        Extract movement intent and a destination_id (from the provided world graph).

        Args:
            user_msg: The user's message
            world_graph: The world graph to resolve location IDs against
            knowledge_chunks: Optional list of knowledge chunks for disambiguation context
            conversation_log: Optional conversation history for context
        """
        import json as _json
        should_attempt = await self._should_attempt(user_msg, conversation_log)
        print(_json.dumps({
            "kind": "location_extractor_called",
            "user_msg": user_msg,
            "should_attempt": should_attempt,
            "has_knowledge_context": knowledge_chunks is not None and len(knowledge_chunks) > 0,
        }, ensure_ascii=False))
        
        if not should_attempt:
            result = LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")
            print(_json.dumps({
                "kind": "location_extractor_skipped",
                "reason": "llm_classification_negative",
                "user_msg": user_msg,
            }, ensure_ascii=False))
            return result

        locations_block = self._build_locations_block(world_graph)
        num_locations = len([l for l in locations_block.split("\n") if l.strip()])

        system = (
            "You are an information extractor for a text adventure engine.\n"
            "Return ONLY valid JSON and nothing else.\n"
            "Your job: decide whether the user is issuing an explicit movement command.\n"
            "Only output intent MOVE if the message is an explicit command like 'go to X' or 'move to X'.\n"
            "Do NOT output MOVE for questions like 'can we go to X?' or hypotheticals.\n"
            "If intent is MOVE, choose the single best destination_id from the provided location list.\n"
            "Use the knowledge context to disambiguate location references (e.g., 'old workplace' might refer to a specific known location).\n"
            "If uncertain, return intent NONE.\n"
            "JSON schema:\n"
            "{\n"
            '  "intent": "MOVE" | "NONE",\n'
            '  "destination_id": "string|null",\n'
            '  "confidence": 0.0,\n'
            '  "destination_text": "string"\n'
            "}\n"
        )

        user_parts = [
            "Known locations (id: name):\n",
            f"{locations_block}\n",
        ]
        
        # Add knowledge context if available
        if knowledge_chunks and len(knowledge_chunks) > 0:
            user_parts.append("\nKnowledge context for disambiguation:\n")
            for i, chunk in enumerate(knowledge_chunks[:5], 1):  # Limit to top 5 chunks
                content = chunk.get("content") or chunk.get("text") or ""
                chunk_id = chunk.get("chunk_id", f"chunk_{i}")
                user_parts.append(f"[{chunk_id}]: {content[:500]}\n")
            user_parts.append("\n")
        
        user_parts.extend([
            "User message:\n",
            f"{user_msg}\n"
        ])

        user = "".join(user_parts)

        # Build messages with conversation history
        messages = [{"role": "system", "content": system}]

        # Add conversation history (limited to EXTRACTOR_TURNS)
        if conversation_log:
            history = [m for m in conversation_log if m.get("role") != "system"]
            history = history[-EXTRACTOR_TURNS:] if len(history) > EXTRACTOR_TURNS else history
            messages.extend(history)

        # Add current extraction request
        messages.append({"role": "user", "content": user})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 120,
        }

        print(_json.dumps({
            "kind": "location_extractor_calling_llm",
            "user_msg": user_msg,
            "num_locations": num_locations,
            "num_knowledge_chunks": len(knowledge_chunks) if knowledge_chunks else 0,
        }, ensure_ascii=False))

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Deferred per test_engine_purity: engine/ keeps llm/ imports function-local.
                from backend.app.llm.retry import post_with_retry
                r = await post_with_retry(
                    client,
                    f"{OPENAI_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
        except Exception as e:
            print(_json.dumps({
                "kind": "location_extractor_network_error",
                "user_msg": user_msg,
                "error": str(e),
            }, ensure_ascii=False))
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")
        
        if r.status_code < 200 or r.status_code >= 300:
            print(_json.dumps({
                "kind": "location_extractor_llm_error",
                "user_msg": user_msg,
                "status_code": r.status_code,
            }, ensure_ascii=False))
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")

        try:
            data = r.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
        except Exception as e:
            print(_json.dumps({
                "kind": "location_extractor_parse_error",
                "user_msg": user_msg,
                "error": str(e),
            }, ensure_ascii=False))
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")
        
        print(_json.dumps({
            "kind": "location_extractor_llm_response",
            "user_msg": user_msg,
            "raw_response": content,
        }, ensure_ascii=False))
        
        result = self._parse_json(content)
        
        print(_json.dumps({
            "kind": "location_extractor_result",
            "user_msg": user_msg,
            "intent": result.intent.value,
            "destination_id": result.destination_id,
            "confidence": result.confidence,
        }, ensure_ascii=False))
        
        return result
