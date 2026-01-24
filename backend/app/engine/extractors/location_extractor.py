# backend/app/engine/extractors/location_extractor.py
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
import re
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

    @staticmethod
    def _should_attempt(user_msg: str) -> bool:
        """
        To keep cost down, only call the extractor if the message likely expresses movement.
        We intentionally do NOT treat questions like "Can we go to ...?" as movement commands
        unless the user explicitly issues a command.
        """
        s = (user_msg or "").strip().lower()
        if not s:
            return False
        # Strong signals for explicit commands.
        return bool(re.match(r"^\s*(go|move)\s+to\s+\S+", s))

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
        if not self._should_attempt(user_msg):
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")

        locations_block = self._build_locations_block(world_graph)

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

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
        if r.status_code < 200 or r.status_code >= 300:
            return LocationExtraction(intent=LocationIntent.NONE, destination_id=None, confidence=0.0, destination_text="")

        data = r.json()
        content = str(data["choices"][0]["message"]["content"]).strip()
        return self._parse_json(content)
