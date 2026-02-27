from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, Dict, List, Optional

import httpx

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_MODEL, EXTRACTOR_TURNS


@dataclass(frozen=True)
class TurnKnowledgeResolution:
    chunk_id: str
    knows: bool
    confidence: float
    reason: str = ""


@dataclass(frozen=True)
class RelationshipHistoryUpdate:
    """LLM-extracted update to a relationship edge's history fields.

    Only set fields that dialogue explicitly confirms — omit or leave None for ambiguous cases.
    prior_relationship: characters mention a past romantic relationship.
    prior_intimacy:     characters confirm or strongly imply past sexual intimacy.
    in_relationship:    characters explicitly state they are currently together.
    """
    from_id: str
    to_id: str
    prior_relationship: Optional[bool] = None
    prior_intimacy: Optional[bool] = None
    in_relationship: Optional[bool] = None


@dataclass(frozen=True)
class TurnExtraction:
    movement_intent: str = "NONE"
    destination_id: str = ""
    confidence: float = 0.0
    destination_text: str = ""
    previous_reply_location_id: str = ""
    previous_reply_speakers: List[str] = field(default_factory=list)
    knowledge_updates: List[TurnKnowledgeResolution] = field(default_factory=list)
    relationship_history_updates: List[RelationshipHistoryUpdate] = field(default_factory=list)


class TurnExtractor:
    """Single-call extractor for movement, previous-scene signals, and knowledge updates."""

    def __init__(self, model: str | None = None):
        self.model = model or OPENAI_MODEL

    @staticmethod
    def _parse_json(content: str, allowed_location_ids: set[str], allowed_character_keys: set[str]) -> TurnExtraction:
        try:
            obj = json.loads(content)
        except Exception:
            return TurnExtraction()

        if not isinstance(obj, dict):
            return TurnExtraction()

        movement = obj.get("movement") if isinstance(obj.get("movement"), dict) else {}
        previous_scene = obj.get("previous_scene") if isinstance(obj.get("previous_scene"), dict) else {}

        intent = str(movement.get("intent") or "NONE").strip().upper()
        if intent not in {"MOVE", "NONE"}:
            intent = "NONE"

        destination_id = str(movement.get("destination_id") or "").strip()
        if destination_id and allowed_location_ids and destination_id not in allowed_location_ids:
            destination_id = ""
            intent = "NONE"

        destination_text = str(movement.get("destination_text") or "").strip()

        try:
            confidence = float(movement.get("confidence", 0.0))
        except Exception:
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        previous_loc = str(previous_scene.get("location_id") or "").strip()
        if previous_loc and allowed_location_ids and previous_loc not in allowed_location_ids:
            previous_loc = ""

        raw_speakers = previous_scene.get("speakers")
        speakers: List[str] = []
        if isinstance(raw_speakers, list):
            for value in raw_speakers:
                key = str(value or "").strip().lower()
                if not key:
                    continue
                if allowed_character_keys and key not in allowed_character_keys:
                    continue
                if key not in speakers:
                    speakers.append(key)

        raw_updates = obj.get("knowledge_updates")
        knowledge_updates: List[TurnKnowledgeResolution] = []
        if isinstance(raw_updates, list):
            for item in raw_updates:
                if not isinstance(item, dict):
                    continue
                chunk_id = str(item.get("chunk_id") or "").strip()
                if not chunk_id:
                    continue
                knows = bool(item.get("knows", False))
                try:
                    update_confidence = float(item.get("confidence", 0.0))
                except Exception:
                    update_confidence = 0.0
                update_confidence = max(0.0, min(1.0, update_confidence))
                reason = str(item.get("reason") or "").strip()
                knowledge_updates.append(
                    TurnKnowledgeResolution(
                        chunk_id=chunk_id,
                        knows=knows,
                        confidence=update_confidence,
                        reason=reason,
                    )
                )

        raw_history = obj.get("relationship_history_updates")
        relationship_history_updates: List[RelationshipHistoryUpdate] = []
        if isinstance(raw_history, list):
            for item in raw_history:
                if not isinstance(item, dict):
                    continue
                h_from = str(item.get("from_id") or "").strip().lower()
                h_to = str(item.get("to_id") or "").strip().lower()
                if not h_from or not h_to:
                    continue
                # Validate both IDs are in the allowed character set (or "player")
                if allowed_character_keys:
                    if h_from not in allowed_character_keys and h_from != "player":
                        continue
                    if h_to not in allowed_character_keys and h_to != "player":
                        continue
                # Parse each optional bool field — None means "not mentioned in dialogue"
                def _parse_opt_bool(val: Any) -> Optional[bool]:
                    if val is None:
                        return None
                    return bool(val)
                relationship_history_updates.append(
                    RelationshipHistoryUpdate(
                        from_id=h_from,
                        to_id=h_to,
                        prior_relationship=_parse_opt_bool(item.get("prior_relationship")),
                        prior_intimacy=_parse_opt_bool(item.get("prior_intimacy")),
                        in_relationship=_parse_opt_bool(item.get("in_relationship")),
                    )
                )

        return TurnExtraction(
            movement_intent=intent,
            destination_id=destination_id,
            confidence=confidence,
            destination_text=destination_text,
            previous_reply_location_id=previous_loc,
            previous_reply_speakers=speakers,
            knowledge_updates=knowledge_updates,
            relationship_history_updates=relationship_history_updates,
        )

    async def extract(
        self,
        *,
        user_msg: str,
        world_locations: Dict[str, str],
        character_key_to_name: Dict[str, str],
        previous_turn_user_msg: str = "",
        previous_turn_assistant_reply: str = "",
        previous_turn_candidate_chunks: List[Dict[str, str]] | None = None,
        conversation_log: List[Dict[str, str]] | None = None,
    ) -> TurnExtraction:
        allowed_location_ids = set((world_locations or {}).keys())
        allowed_character_keys = {str(k).strip().lower() for k in (character_key_to_name or {}).keys() if str(k).strip()}

        location_lines = []
        for loc_id, loc_name in (world_locations or {}).items():
            location_lines.append(f"- {loc_id}: {str(loc_name or '').strip()}")
            if len(location_lines) >= 120:
                break

        character_lines = []
        for key, name in (character_key_to_name or {}).items():
            character_lines.append(f"- {str(key).strip().lower()}: {str(name or '').strip()}")
            if len(character_lines) >= 80:
                break

        candidate_lines: List[str] = []
        for chunk in (previous_turn_candidate_chunks or [])[:12]:
            cid = str(chunk.get("chunk_id") or "").strip()
            ctext = str(chunk.get("text") or "").strip()
            if not cid or not ctext:
                continue
            candidate_lines.append(f"- {cid}: {ctext[:500]}")

        system = (
            "You are a strict JSON extractor for a narrative game engine.\n"
            "Return ONE JSON object only. No prose, no markdown.\n"
            "Use only allowed IDs from provided lists.\n"
            "Rules:\n"
            "1) movement.intent is MOVE only for explicit movement commands. Otherwise NONE.\n"
            "2) movement.destination_id must be one of allowed location ids or null.\n"
            "3) previous_scene extracts from PREVIOUS TURN ASSISTANT REPLY only.\n"
            "4) previous_scene.speakers must be character keys from allowed list.\n"
            "5) knowledge_updates must only reference provided candidate chunk_ids. Omit uncertain updates.\n"
            "6) relationship_history_updates: only add entries when dialogue EXPLICITLY confirms a fact.\n"
            "   prior_relationship=true only if characters confirm a past romantic relationship.\n"
            "   prior_intimacy=true only if characters explicitly confirm past sexual intimacy.\n"
            "   in_relationship=true only if characters explicitly state they are currently together.\n"
            "   Omit the field (or use null) if dialogue is ambiguous or does not address it.\n"
            "   Use from_id and to_id from allowed character keys.\n"
            "JSON schema:\n"
            "{\n"
            '  "movement": {"intent": "MOVE|NONE", "destination_id": "string|null", "confidence": 0.0, "destination_text": "string"},\n'
            '  "previous_scene": {"location_id": "string|null", "speakers": ["character_key"]},\n'
            '  "knowledge_updates": [{"chunk_id": "string", "knows": true, "confidence": 0.0, "reason": "string"}],\n'
            '  "relationship_history_updates": [{"from_id": "character_key", "to_id": "character_key", "prior_relationship": true|false|null, "prior_intimacy": true|false|null, "in_relationship": true|false|null}]\n'
            "}\n"
        )

        user_content = (
            "CURRENT USER MESSAGE:\n"
            f"{str(user_msg or '').strip()}\n\n"
            "PREVIOUS TURN USER MESSAGE:\n"
            f"{str(previous_turn_user_msg or '').strip()}\n\n"
            "PREVIOUS TURN ASSISTANT REPLY:\n"
            f"{str(previous_turn_assistant_reply or '').strip()}\n\n"
            "ALLOWED LOCATIONS (id: name):\n"
            + "\n".join(location_lines)
            + "\n\nALLOWED CHARACTERS (key: name):\n"
            + "\n".join(character_lines)
            + "\n\nPREVIOUS TURN CANDIDATE KNOWLEDGE CHUNKS:\n"
            + ("\n".join(candidate_lines) if candidate_lines else "- none")
        )

        messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
        history = [m for m in (conversation_log or []) if m.get("role") in {"user", "assistant"}]
        history = history[-EXTRACTOR_TURNS:] if len(history) > EXTRACTOR_TURNS else history
        messages.extend({"role": str(m.get("role")), "content": str(m.get("content", ""))} for m in history)
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": 560,
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                    json=payload,
                )
        except Exception:
            return TurnExtraction()

        if r.status_code < 200 or r.status_code >= 300:
            return TurnExtraction()

        try:
            data = r.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
        except Exception:
            return TurnExtraction()

        return self._parse_json(content, allowed_location_ids, allowed_character_keys)
