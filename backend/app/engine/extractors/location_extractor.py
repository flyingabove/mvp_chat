# backend/app/engine/extractors/location_extractor.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from typing import Optional

import httpx

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_MODEL


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

    async def _should_attempt(self, user_msg: str) -> bool:
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
        
        user = f"User message: {user_msg}\n"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 50,
        }
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
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
            # Keep prompt bounded
            if len(lines) >= 80:
                break
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

    async def extract(self, user_msg: str, *, world_graph) -> LocationExtraction:
        """
        Extract movement intent and a destination_id (from the provided world graph).
        """
        import json as _json
        should_attempt = await self._should_attempt(user_msg)
        print(_json.dumps({
            "kind": "location_extractor_called",
            "user_msg": user_msg,
            "should_attempt": should_attempt,
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
            "If uncertain, return intent NONE.\n"
            "JSON schema:\n"
            "{\n"
            '  "intent": "MOVE" | "NONE",\n'
            '  "destination_id": "string|null",\n'
            '  "confidence": 0.0,\n'
            '  "destination_text": "string"\n'
            "}\n"
        )

        user = (
            "Known locations (id: name):\n"
            f"{locations_block}\n\n"
            "User message:\n"
            f"{user_msg}\n"
        )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 120,
        }

        print(_json.dumps({
            "kind": "location_extractor_calling_llm",
            "user_msg": user_msg,
            "num_locations": num_locations,
        }, ensure_ascii=False))

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
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
