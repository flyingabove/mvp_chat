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
class RelationshipStateUpdate:
    """Small incremental delta to a directed relationship edge's numeric state.

    Extracted from the CURRENT USER MESSAGE to capture the player's revealed
    attitude toward an NPC.

    Rules enforced at parse time:
    - from_id must be "player" (extractor only captures player's perspective)
    - All deltas are clamped to [-0.10, 0.10] (0..0.10 for fear/suspicion/jealousy)
    - Omit fields that are 0 (save tokens); omit entire entry if message is neutral
    """
    from_id: str          # always "player"
    to_id: str            # NPC character key
    trust_delta: float = 0.0       # negative = distrust expressed, positive = trust shown
    fear_delta: float = 0.0        # 0..0.10 only; player shows fear toward NPC
    affection_delta: float = 0.0   # negative = coldness/anger, positive = warmth
    suspicion_delta: float = 0.0   # 0..0.10 only; player voices suspicion
    jealousy_delta: float = 0.0    # 0..0.10 only; player expresses jealousy
    reason: str = ""               # brief plain-text explanation


@dataclass(frozen=True)
class DepartureSignal:
    """LLM-judged signal that a resident character's own dialogue concerns
    them leaving the house. Categorical, not a numeric confidence: "is this
    a joke or a real decision" is a discrete judgment call, matching how
    movement.intent is MOVE|NONE rather than confidence-gated.

    certainty:
      NONE     - no departure topic present (default).
      WISH     - a passing complaint, joke, or hypothetical ("I wish I
                 could just leave this house").
      DECISION - an explicit, serious, stated intention to actually leave,
                 from the departing character's OWN words only - never
                 inferred from another character's (including the player's)
                 speech about them.
    """
    character_id: str = ""
    certainty: str = "NONE"
    reason: str = ""


@dataclass(frozen=True)
class BehaviorTagUpdate:
    """Cheap, per-turn observable-behavior tag between two characters
    (Phase 3 "Social life"). Raw material accumulated into
    GameState.recent_behavior_log; NOT itself a goal/disposition change -
    just a short characterization of how from_id behaved toward to_id THIS
    turn. Free-text, no enum (stays genre-agnostic: a mystery story's tags
    read "evasive"/"defensive", an ensemble drama's read "warm"/"aggressive",
    same field, no schema change needed either way). from_id/to_id must be
    from allowed character keys (player included)."""
    from_id: str
    to_id: str
    tag: str = ""


@dataclass(frozen=True)
class SocialShiftSignal:
    """LLM judgment that an accumulated behavior pattern (not a single
    message) shows a genuine shift in a character's goal or their
    disposition toward a specific other character. Only ever evaluated when
    the engine has flagged a pair's tag window as "ripe" (see
    prompt_engine.py's ripe-window heuristic) - never a snap judgment from
    one line of dialogue. Categorical, mirroring DepartureSignal's
    precedent, not a numeric confidence: "has this settled into a real
    change" is a discrete call.

    certainty:
      NONE  - default; also used when asked to judge but the pattern is
              still noisy/mixed, not yet a genuine settled shift.
      WISH  - a momentary flicker/one-off outlier, not a real change
              (mirrors DepartureSignal's WISH - "a wish or joke is not
              departure" / one warm moment doesn't undo a pattern).
      SHIFT - the accumulated pattern shows a real, settled change.
    scope: "goal" | "disposition" - which container this shift targets.
    subject_id: character whose goal/disposition is shifting.
    target_id: for scope="disposition" only, the other character; empty
        for scope="goal" (a goal is not about anyone in particular).
    new_value: free-text label for the new current state. Required when
        certainty="SHIFT"; a SHIFT with no new_value is coerced to NONE.
    reason: short phrase citing the pattern that justified the shift.
    """
    certainty: str = "NONE"
    scope: str = ""
    subject_id: str = ""
    target_id: str = ""
    new_value: str = ""
    reason: str = ""


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
    relationship_state_updates: List[RelationshipStateUpdate] = field(default_factory=list)
    departure_signal: Optional[DepartureSignal] = None
    behavior_tags: List[BehaviorTagUpdate] = field(default_factory=list)
    social_shift_signal: Optional[SocialShiftSignal] = None


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

        def _opt_bool(val: Any) -> Optional[bool]:
            return None if val is None else bool(val)

        def _clamp_delta(val: Any, lo: float, hi: float) -> float:
            try:
                return max(lo, min(hi, float(val or 0.0)))
            except Exception:
                return 0.0

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
                if allowed_character_keys:
                    if h_from not in allowed_character_keys and h_from != "player":
                        continue
                    if h_to not in allowed_character_keys and h_to != "player":
                        continue
                relationship_history_updates.append(
                    RelationshipHistoryUpdate(
                        from_id=h_from,
                        to_id=h_to,
                        prior_relationship=_opt_bool(item.get("prior_relationship")),
                        prior_intimacy=_opt_bool(item.get("prior_intimacy")),
                        in_relationship=_opt_bool(item.get("in_relationship")),
                    )
                )

        raw_state = obj.get("relationship_state_updates")
        relationship_state_updates: List[RelationshipStateUpdate] = []
        if isinstance(raw_state, list):
            for item in raw_state:
                if not isinstance(item, dict):
                    continue
                s_from = str(item.get("from_id") or "").strip().lower()
                s_to = str(item.get("to_id") or "").strip().lower()
                if not s_from or not s_to:
                    continue
                # Only player's perspective allowed from the extractor
                if s_from != "player":
                    continue
                if allowed_character_keys and s_to not in allowed_character_keys:
                    continue
                relationship_state_updates.append(
                    RelationshipStateUpdate(
                        from_id=s_from,
                        to_id=s_to,
                        trust_delta=_clamp_delta(item.get("trust_delta", 0.0), -0.10, 0.10),
                        fear_delta=_clamp_delta(item.get("fear_delta", 0.0), 0.0, 0.10),
                        affection_delta=_clamp_delta(item.get("affection_delta", 0.0), -0.10, 0.10),
                        suspicion_delta=_clamp_delta(item.get("suspicion_delta", 0.0), 0.0, 0.10),
                        jealousy_delta=_clamp_delta(item.get("jealousy_delta", 0.0), 0.0, 0.10),
                        reason=str(item.get("reason") or "").strip(),
                    )
                )

        raw_departure = obj.get("departure_signal") if isinstance(obj.get("departure_signal"), dict) else {}
        d_char = str(raw_departure.get("character_id") or "").strip().lower()
        d_certainty = str(raw_departure.get("certainty") or "NONE").strip().upper()
        if d_certainty not in {"NONE", "WISH", "DECISION"}:
            d_certainty = "NONE"
        departure_signal: Optional[DepartureSignal] = None
        if d_char and d_certainty != "NONE":
            if allowed_character_keys and d_char not in allowed_character_keys:
                departure_signal = None
            else:
                departure_signal = DepartureSignal(
                    character_id=d_char,
                    certainty=d_certainty,
                    reason=str(raw_departure.get("reason") or "").strip(),
                )

        raw_tags = obj.get("behavior_tags")
        behavior_tags: List[BehaviorTagUpdate] = []
        if isinstance(raw_tags, list):
            for item in raw_tags:
                if not isinstance(item, dict):
                    continue
                t_from = str(item.get("from_id") or "").strip().lower()
                t_to = str(item.get("to_id") or "").strip().lower()
                tag = str(item.get("tag") or "").strip()[:40]
                if not t_from or not t_to or not tag:
                    continue
                if allowed_character_keys:
                    if t_from not in allowed_character_keys and t_from != "player":
                        continue
                    if t_to not in allowed_character_keys and t_to != "player":
                        continue
                behavior_tags.append(BehaviorTagUpdate(from_id=t_from, to_id=t_to, tag=tag))

        raw_shift = obj.get("social_shift_signal") if isinstance(obj.get("social_shift_signal"), dict) else {}
        sh_certainty = str(raw_shift.get("certainty") or "NONE").strip().upper()
        if sh_certainty not in {"NONE", "WISH", "SHIFT"}:
            sh_certainty = "NONE"
        sh_scope = str(raw_shift.get("scope") or "").strip().lower()
        if sh_scope not in {"goal", "disposition"}:
            sh_scope = ""
        sh_subject = str(raw_shift.get("subject_id") or "").strip().lower()
        sh_target = str(raw_shift.get("target_id") or "").strip().lower()
        sh_new_value = str(raw_shift.get("new_value") or "").strip()[:200]
        sh_reason = str(raw_shift.get("reason") or "").strip()[:200]

        social_shift_signal: Optional[SocialShiftSignal] = None
        if sh_certainty != "NONE" and sh_scope and sh_subject:
            if allowed_character_keys and sh_subject not in allowed_character_keys:
                social_shift_signal = None
            elif sh_scope == "disposition" and allowed_character_keys and sh_target not in allowed_character_keys:
                social_shift_signal = None
            elif sh_scope == "disposition" and not sh_target:
                social_shift_signal = None
            else:
                if sh_certainty == "SHIFT" and not sh_new_value:
                    sh_certainty = "NONE"
                if sh_certainty != "NONE":
                    social_shift_signal = SocialShiftSignal(
                        certainty=sh_certainty,
                        scope=sh_scope,
                        subject_id=sh_subject,
                        target_id=sh_target if sh_scope == "disposition" else "",
                        new_value=sh_new_value,
                        reason=sh_reason,
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
            relationship_state_updates=relationship_state_updates,
            departure_signal=departure_signal,
            behavior_tags=behavior_tags,
            social_shift_signal=social_shift_signal,
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
        behavior_window: Dict[str, Any] | None = None,
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
            "7) relationship_state_updates: ONLY from player's perspective (from_id must be 'player').\n"
            "   Extract small deltas from CURRENT USER MESSAGE when the player's words reveal attitude.\n"
            "   trust_delta: +0.05..+0.10 when player expresses trust; -0.05..-0.10 for distrust.\n"
            "   fear_delta: +0.05..+0.10 when player shows fear. Never negative.\n"
            "   affection_delta: +0.05..+0.10 for warmth/gratitude; -0.05..-0.10 for coldness/anger.\n"
            "   suspicion_delta: +0.05..+0.10 when player voices suspicion. Never negative.\n"
            "   jealousy_delta: +0.05..+0.10 when player expresses jealousy. Never negative.\n"
            "   Omit the entry if player's words are neutral or no attitude change is expressed.\n"
            "   Omit individual delta fields that are 0. Include 'reason' (1 short phrase).\n"
            "8) departure_signal: only set when a resident character's OWN dialogue concerns\n"
            "   THEM leaving the house.\n"
            "   certainty=\"WISH\" for a passing complaint, joke, or hypothetical\n"
            "   (\"I wish I could leave\", \"sometimes I want to just move out\").\n"
            "   certainty=\"DECISION\" ONLY for an explicit, serious, stated intention to\n"
            "   actually leave (\"I'm moving out next week\", \"I've decided to leave the house\").\n"
            "   certainty=\"NONE\" (default) when no departure topic is present.\n"
            "   character_id must be the character who is leaving, from allowed character keys.\n"
            "   Never infer DECISION (or WISH) from the player's speech, or from another\n"
            "   character's speech ABOUT someone else leaving - only from that character's own words.\n"
            "9) behavior_tags: ALWAYS extract, cheaply, for any character (including player) whose\n"
            "   words or actions THIS TURN showed an observable attitude/behavior toward another\n"
            "   character present in the scene. tag is a short free-text phrase (1-3 words, e.g.\n"
            "   \"aggressive\", \"warm\", \"evasive\", \"protective\", \"dismissive\") describing how\n"
            "   from_id behaved toward to_id in this single turn only. Omit if no clear behavior\n"
            "   toward a specific other character is shown. This is NOT a judgment about whether\n"
            "   anything has changed - just a raw observation of this turn.\n"
            "10) social_shift_signal: ONLY produce this when a \"BEHAVIOR PATTERN TO EVALUATE\"\n"
            "    block is present below. If that block is absent, omit social_shift_signal entirely\n"
            "    (or set certainty=\"NONE\"). When the block IS present, judge whether the pattern shown\n"
            "    represents a genuine, settled shift (certainty=\"SHIFT\", with new_value describing the\n"
            "    new state) or is still just a momentary/mixed pattern not yet a real change\n"
            "    (certainty=\"WISH\"). scope is \"goal\" (subject_id's own persistent objective changed)\n"
            "    or \"disposition\" (subject_id's stance toward target_id changed).\n"
            "JSON schema:\n"
            "{\n"
            '  "movement": {"intent": "MOVE|NONE", "destination_id": "string|null", "confidence": 0.0, "destination_text": "string"},\n'
            '  "previous_scene": {"location_id": "string|null", "speakers": ["character_key"]},\n'
            '  "knowledge_updates": [{"chunk_id": "string", "knows": true, "confidence": 0.0, "reason": "string"}],\n'
            '  "relationship_history_updates": [{"from_id": "character_key", "to_id": "character_key", "prior_relationship": true|false|null, "prior_intimacy": true|false|null, "in_relationship": true|false|null}],\n'
            '  "relationship_state_updates": [{"from_id": "player", "to_id": "character_key", "trust_delta": 0.0, "fear_delta": 0.0, "affection_delta": 0.0, "suspicion_delta": 0.0, "jealousy_delta": 0.0, "reason": "string"}],\n'
            '  "departure_signal": {"character_id": "character_key|null", "certainty": "NONE|WISH|DECISION", "reason": "string"},\n'
            '  "behavior_tags": [{"from_id": "character_key", "to_id": "character_key", "tag": "string"}],\n'
            '  "social_shift_signal": {"certainty": "NONE|WISH|SHIFT", "scope": "goal|disposition", "subject_id": "character_key", "target_id": "character_key|null", "new_value": "string", "reason": "string"}\n'
            "}\n"
        )

        behavior_window_block = ""
        if behavior_window:
            pair = str(behavior_window.get("pair") or "")
            tags = behavior_window.get("tags") or []
            behavior_window_block = (
                "\n\nBEHAVIOR PATTERN TO EVALUATE:\n"
                f"{pair} has shown (oldest -> newest): {', '.join(str(t) for t in tags)}.\n"
                "Has this character's goal or disposition genuinely shifted? See rule 10."
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
            + behavior_window_block
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
            "max_tokens": 700,
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
