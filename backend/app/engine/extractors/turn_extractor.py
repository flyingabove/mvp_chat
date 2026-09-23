from __future__ import annotations

from dataclasses import dataclass, field, replace as _dataclass_replace
import json
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_MODEL, EXTRACTOR_TURNS
from backend.app.utils.logging_utils import jlog
from backend.app.engine.extractors.decision_registry import (
    NONE_OF_THESE,
    REL_HISTORY_FIELDS,
    REL_STATE_DIMENSIONS,
    REL_STATE_SYMMETRIC,
    behavior_tag_batch_decisions,
    departure_batch_decisions,
    knowledge_batch_decisions,
    movement_destination_decision,
    movement_intent_decision,
    prev_scene_location_decision,
    relationship_history_batch_decisions,
    relationship_state_batch_decisions,
    rel_state_score_to_delta,
    social_shift_certainty_decision,
)
from backend.app.llm.decisions.types import DecisionBatch, DecisionOutcome, FallbackReason, Provider
from backend.app.llm.protocols import DecisionProvider, LegacyExtractionRequest

# Step 3 of documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §12:
# httpx is NO LONGER imported here. The legacy HTTP call moved to
# TurnExtractor._call_legacy_raw, which is injected into the resolver as a
# LegacyExtractionCallable rather than living inline in extract(). This is
# what makes the import-direction test in test_engine_purity.py pass for
# this file (location_extractor.py and knowledge_resolution_extractor.py
# still import httpx directly and remain on that test's documented
# allowlist — see JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §2).


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
    """Single-call extractor for movement, previous-scene signals, and knowledge updates.

    Step 3 of JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §12: internally
    restructured into batch builder (_build_batches) -> resolver
    (DecisionResolver, injected via `resolver`) -> assembler
    (_parse_dict + _apply_decision_overrides). extract()'s signature and
    return type are UNCHANGED — every existing caller and all 30 existing
    extraction tests in test_prompt_engine.py continue to work unmodified.
    With TYPESAFE_ENABLED=false (the shipped default), behaviour is
    byte-identical to before this refactor: the resolver's own routing
    logic (JevConfig.routing_for) resolves every registered decision via
    the legacy path alone.
    """

    def __init__(self, model: str | None = None, resolver: "DecisionProvider | None" = None):
        self.model = model or OPENAI_MODEL
        # Deferred imports: avoids constructing network clients / reading
        # settings at MODULE import time (matters for test collection and
        # for any process that imports turn_extractor.py without needing
        # Jev at all).
        from backend.app.llm.factory import build_default_resolver, get_shared_httpx_client
        from backend.app.llm.providers.openai_chat import OpenAIChatClient
        self._legacy_client = OpenAIChatClient(
            get_shared_httpx_client(), base_url="https://api.openai.com/v1", api_key=OPENAI_API_KEY,
        )
        self._resolver: DecisionProvider = (
            resolver if resolver is not None else build_default_resolver(self._call_legacy_raw)
        )

    @staticmethod
    def _parse_json(
        content: str, allowed_location_ids: set[str], allowed_character_keys: set[str],
        allowed_behavior_tags: set[str] | None = None,
    ) -> TurnExtraction:
        """UNCHANGED public entry point: parses a raw JSON string. Delegates
        to _parse_dict, which is the piece the assembler (extract(), below)
        also calls directly with an already-parsed dict — avoids
        re-serializing/re-parsing JSON that the legacy call already parsed."""
        try:
            obj = json.loads(content)
        except Exception:
            return TurnExtraction()
        if not isinstance(obj, dict):
            return TurnExtraction()
        return TurnExtractor._parse_dict(obj, allowed_location_ids, allowed_character_keys, allowed_behavior_tags)

    @staticmethod
    def _parse_dict(
        obj: dict, allowed_location_ids: set[str], allowed_character_keys: set[str],
        allowed_behavior_tags: set[str] | None = None,
    ) -> TurnExtraction:
        """The exact body _parse_json always had, unchanged — every
        existing validation rule (unknown location -> NONE, from_id must be
        'player', departure/shift coercion rules, etc.) is retained here,
        untouched by the Jev integration. Jev choosing something never
        bypasses this — see JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §9's
        'Two invariants that are code's job, not Jev's'.

        BL-16 fix: `allowed_behavior_tags` is the story's closed vocabulary
        (default/empty = accept-anything, matching pre-fix behavior
        byte-for-byte for every story that hasn't authored one yet)."""
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

        # BL-16 fix: lowercase-keyed lookup onto the vocabulary's canonical
        # casing, so an LLM that returns "Warm" still matches "warm" in the
        # authored list. Empty vocabulary => accept-anything (unchanged).
        _tag_vocab_lookup = {
            str(t).strip().lower(): str(t).strip() for t in (allowed_behavior_tags or ())
        }

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
                if _tag_vocab_lookup:
                    canonical = _tag_vocab_lookup.get(tag.lower())
                    if canonical is None:
                        # Not in the authored vocabulary - omit rather than
                        # guess a nearest match, matching every other
                        # "unknown -> drop" rule in this parser.
                        continue
                    tag = canonical
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

    def _build_batches(
        self,
        *,
        user_msg: str,
        world_locations: Dict[str, str],
        previous_turn_assistant_reply: str,
        character_key_to_name: Dict[str, str] | None = None,
        previous_turn_candidate_chunks: List[Dict[str, str]] | None = None,
        allowed_behavior_tags: List[str] | None = None,
        behavior_window: Dict[str, Any] | None = None,
    ) -> List[DecisionBatch]:
        """Step 3/5/6/7/8/9 batch builder — pure, no I/O. All 11 of the 12
        abilities are now Jev-eligible (ability 12's `new_value` free text
        still needs legacy — see social_shift_certainty_decision's
        docstring). NOTE the still-unresolved "hybrid trap"
        (JEV_EXTRACTOR_REDESIGN_2026_09_22.md): extract()'s "legacy_raw is
        None" branch below still unconditionally calls legacy whenever the
        resolver itself didn't need to (e.g. a sparse turn where every
        registered decision resolved via Jev) — shrinking the legacy prompt
        once that's safe is deliberately out of scope here, same as when
        this note was first written for steps 1-5."""
        batches: List[DecisionBatch] = [
            DecisionBatch(
                name="current_message",
                state="CURRENT PLAYER MESSAGE:\n" + str(user_msg or "").strip(),
                decisions=(
                    movement_intent_decision(),
                    movement_destination_decision(world_locations or {}),
                ),
            ),
        ]
        if str(previous_turn_assistant_reply or "").strip():
            batches.append(DecisionBatch(
                name="previous_reply",
                state="PREVIOUS TURN ASSISTANT REPLY:\n" + str(previous_turn_assistant_reply).strip(),
                decisions=(prev_scene_location_decision(world_locations or {}),),
            ))

        # Both fan-outs share the same "what just happened" context: current
        # message + previous reply, since either can carry the signal
        # (a resident's departure line, or a fact revealed in either turn).
        context_state = (
            "CURRENT PLAYER MESSAGE:\n" + str(user_msg or "").strip()
            + "\n\nPREVIOUS TURN ASSISTANT REPLY:\n" + str(previous_turn_assistant_reply or "").strip()
        )

        knowledge_decisions = knowledge_batch_decisions(previous_turn_candidate_chunks or [])
        if knowledge_decisions:
            batches.append(DecisionBatch(
                name="knowledge", state=context_state, decisions=knowledge_decisions,
            ))

        departure_decisions = departure_batch_decisions((character_key_to_name or {}).keys())
        if departure_decisions:
            batches.append(DecisionBatch(
                name="departure_check", state=context_state, decisions=departure_decisions,
            ))

        # Step 7. Gated on character_key_to_name (every known character),
        # anchored to the player per both abilities' legacy-schema scope —
        # see relationship_state_decision/relationship_history_decision's
        # docstrings for the NPC-to-NPC limitation this carries forward.
        rel_state_decisions = relationship_state_batch_decisions((character_key_to_name or {}).keys())
        if rel_state_decisions:
            batches.append(DecisionBatch(
                name="rel_state", state="CURRENT PLAYER MESSAGE:\n" + str(user_msg or "").strip(),
                decisions=rel_state_decisions,
            ))

        rel_history_decisions = relationship_history_batch_decisions((character_key_to_name or {}).keys())
        if rel_history_decisions:
            batches.append(DecisionBatch(
                name="rel_history", state=context_state, decisions=rel_history_decisions,
            ))

        # Step 8. BL-16-gated: only registered once the story has authored
        # a closed behavior_tag_vocabulary (a free-text tag has no fixed
        # option set for Jev's `choice` kind).
        behavior_tag_decisions = behavior_tag_batch_decisions(
            (character_key_to_name or {}).keys(), allowed_behavior_tags or [],
        )
        if behavior_tag_decisions:
            batches.append(DecisionBatch(
                name="behavior_tag", state=context_state, decisions=behavior_tag_decisions,
            ))

        # Step 9. Gated on behavior_window being present - matches the
        # legacy prompt's own rule 10 ("only produce this when a BEHAVIOR
        # PATTERN TO EVALUATE block is present"); at most one ripe pair is
        # ever evaluated per turn (prompt_engine.py's _ripe_behavior_pairs),
        # so this is a single decision, not a fan-out.
        if behavior_window and "->" in str(behavior_window.get("pair") or ""):
            subject_id, target_id = str(behavior_window["pair"]).split("->", 1)
            batches.append(DecisionBatch(
                name="social_shift",
                state="CURRENT PLAYER MESSAGE:\n" + str(user_msg or "").strip(),
                decisions=(social_shift_certainty_decision(
                    subject_id, target_id, behavior_window.get("tags") or [],
                ),),
            ))

        return batches

    def _apply_decision_overrides(
        self, base: TurnExtraction, outcome: DecisionOutcome, allowed_location_ids: set[str],
        behavior_window: Dict[str, Any] | None = None,
    ) -> TurnExtraction:
        """The assembler's override step. Only applies a Jev answer when the
        resolver actually used Jev for it (Provider.JEV) — in shadow mode,
        legacy-only mode, or any fallback, `base` (already built from
        legacy_raw) is left exactly as-is, so this is a strict no-op in
        every state except a genuinely live, successful Jev answer.

        Every existing validation from _parse_dict is re-applied here, not
        bypassed: an out-of-range/none_of_these destination coerces intent
        back to NONE, matching _parse_dict's own
        `if destination_id and allowed_location_ids and destination_id not
        in allowed_location_ids: destination_id = ""; intent = "NONE"` rule
        exactly (JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §9 invariant #2)."""
        intent = base.movement_intent
        destination_id = base.destination_id
        confidence = base.confidence
        previous_loc = base.previous_reply_location_id

        mi = outcome.answers.get("movement_intent")
        if mi is not None and mi.usable and mi.provider is Provider.JEV:
            intent = mi.choice or "NONE"
            if mi.confidence is not None:
                confidence = mi.confidence

        md = outcome.answers.get("movement_destination")
        if md is not None and md.usable and md.provider is Provider.JEV:
            chosen = md.choice
            if chosen and chosen != NONE_OF_THESE and chosen in allowed_location_ids:
                destination_id = chosen
            else:
                destination_id = ""
                intent = "NONE"

        psl = outcome.answers.get("prev_scene_location")
        if psl is not None and psl.usable and psl.provider is Provider.JEV:
            chosen = psl.choice
            previous_loc = chosen if (chosen and chosen != NONE_OF_THESE and chosen in allowed_location_ids) else ""

        knowledge_updates = self._apply_knowledge_overrides(base.knowledge_updates, outcome)
        departure_signal = self._apply_departure_override(base.departure_signal, outcome)
        relationship_state_updates = self._apply_rel_state_overrides(base.relationship_state_updates, outcome)
        relationship_history_updates = self._apply_rel_history_overrides(base.relationship_history_updates, outcome)
        behavior_tags = self._apply_behavior_tag_overrides(base.behavior_tags, outcome)
        social_shift_signal = self._apply_social_shift_override(base.social_shift_signal, outcome, behavior_window)

        return _dataclass_replace(
            base, movement_intent=intent, destination_id=destination_id,
            confidence=confidence, previous_reply_location_id=previous_loc,
            knowledge_updates=knowledge_updates, departure_signal=departure_signal,
            relationship_state_updates=relationship_state_updates,
            relationship_history_updates=relationship_history_updates,
            behavior_tags=behavior_tags, social_shift_signal=social_shift_signal,
        )

    @staticmethod
    def _apply_knowledge_overrides(
        base_updates: List[TurnKnowledgeResolution], outcome: DecisionOutcome,
    ) -> List[TurnKnowledgeResolution]:
        """Ability 7 override. Only chunks Jev actually, usably answered are
        replaced; every other chunk keeps whatever the legacy call produced
        (including chunks Jev was never asked about, e.g. no candidates)."""
        by_chunk: dict[str, TurnKnowledgeResolution] = {u.chunk_id: u for u in base_updates}
        order: List[str] = [u.chunk_id for u in base_updates]
        for decision_id, answer in outcome.answers.items():
            if not decision_id.startswith("knows_"):
                continue
            if not (answer.usable and answer.provider is Provider.JEV):
                continue
            chunk_id = decision_id[len("knows_"):]
            probability = answer.probability if answer.probability is not None else 0.0
            by_chunk[chunk_id] = TurnKnowledgeResolution(
                chunk_id=chunk_id, knows=probability >= 0.5, confidence=probability,
                reason=by_chunk.get(chunk_id).reason if chunk_id in by_chunk else "",
            )
            if chunk_id not in order:
                order.append(chunk_id)
        return [by_chunk[cid] for cid in order]

    @staticmethod
    def _apply_departure_override(
        base_signal: Optional[DepartureSignal], outcome: DecisionOutcome,
    ) -> Optional[DepartureSignal]:
        """Ability 10 override. Jev covers this ability only when EVERY
        resident's departure_<key> decision was usably answered by Jev
        (the fan-out batch is all-or-nothing per turn — a partial batch
        means the resolver already fell back that batch to legacy, so
        `provider is Provider.JEV` will simply be false for all its
        decisions and this is a no-op). Among a fully-Jev-covered batch, at
        most one resident should answer non-NONE (matches the legacy
        prompt's own single-object shape); the first non-NONE wins."""
        jev_departure_answers = {
            decision_id: answer for decision_id, answer in outcome.answers.items()
            if decision_id.startswith("departure_") and answer.usable and answer.provider is Provider.JEV
        }
        if not jev_departure_answers:
            return base_signal
        for decision_id, answer in jev_departure_answers.items():
            certainty = answer.choice or "NONE"
            if certainty != "NONE":
                return DepartureSignal(
                    character_id=decision_id[len("departure_"):], certainty=certainty, reason="",
                )
        return None

    @staticmethod
    def _apply_rel_state_overrides(
        base_updates: List[RelationshipStateUpdate], outcome: DecisionOutcome,
    ) -> List[RelationshipStateUpdate]:
        """Ability 9 override. Decision ids are `relstate_<dimension>_<target>`
        — one per (dimension, target) pair. Per-dimension: a usable Jev
        score overrides that one dimension's delta; every other dimension
        for that target keeps its legacy value. A target left with all 5
        deltas at 0.0 is OMITTED entirely, matching the legacy prompt's own
        "omit the entry if neutral" rule (rule 7) rather than emitting a
        no-op entry Jev never would have."""
        jev_deltas: dict[str, dict[str, float]] = {}
        for decision_id, answer in outcome.answers.items():
            if not decision_id.startswith("relstate_"):
                continue
            if not (answer.usable and answer.provider is Provider.JEV):
                continue
            rest = decision_id[len("relstate_"):]
            dimension = next((d for d in REL_STATE_DIMENSIONS if rest.startswith(d + "_")), None)
            if dimension is None:
                continue
            target_id = rest[len(dimension) + 1:]
            score = answer.score if answer.score is not None else (0.5 if dimension in REL_STATE_SYMMETRIC else 0.0)
            jev_deltas.setdefault(target_id, {})[dimension] = rel_state_score_to_delta(dimension, score)

        if not jev_deltas:
            return base_updates

        by_target = {u.to_id: u for u in base_updates if u.from_id == "player"}
        ordered_targets = [u.to_id for u in base_updates if u.from_id == "player"]
        for target_id in jev_deltas:
            if target_id not in ordered_targets:
                ordered_targets.append(target_id)

        result: List[RelationshipStateUpdate] = [u for u in base_updates if u.from_id != "player"]
        for target_id in ordered_targets:
            existing = by_target.get(target_id)
            deltas = jev_deltas.get(target_id, {})
            trust = deltas.get("trust", existing.trust_delta if existing else 0.0)
            affection = deltas.get("affection", existing.affection_delta if existing else 0.0)
            fear = deltas.get("fear", existing.fear_delta if existing else 0.0)
            suspicion = deltas.get("suspicion", existing.suspicion_delta if existing else 0.0)
            jealousy = deltas.get("jealousy", existing.jealousy_delta if existing else 0.0)
            if trust == 0.0 and affection == 0.0 and fear == 0.0 and suspicion == 0.0 and jealousy == 0.0:
                continue
            result.append(RelationshipStateUpdate(
                from_id="player", to_id=target_id, trust_delta=trust, fear_delta=fear,
                affection_delta=affection, suspicion_delta=suspicion, jealousy_delta=jealousy,
                reason=existing.reason if existing else "",
            ))
        return result

    @staticmethod
    def _apply_rel_history_overrides(
        base_updates: List[RelationshipHistoryUpdate], outcome: DecisionOutcome,
    ) -> List[RelationshipHistoryUpdate]:
        """Ability 8 override. Decision ids are `relhist_<field>_<target>`.
        A field Jev never usably answered keeps its legacy value (including
        None = "not addressed" — never coerced to False). A target left
        with all 3 fields at None is OMITTED, matching the legacy prompt's
        own omission rule for ambiguous/unaddressed facts."""
        jev_fields: dict[str, dict[str, Optional[bool]]] = {}
        for decision_id, answer in outcome.answers.items():
            if not decision_id.startswith("relhist_"):
                continue
            if not (answer.usable and answer.provider is Provider.JEV):
                continue
            rest = decision_id[len("relhist_"):]
            field_name = next((f for f in REL_HISTORY_FIELDS if rest.startswith(f + "_")), None)
            if field_name is None:
                continue
            target_id = rest[len(field_name) + 1:]
            value = None if answer.probability is None else (answer.probability >= 0.5)
            jev_fields.setdefault(target_id, {})[field_name] = value

        if not jev_fields:
            return base_updates

        by_target = {u.to_id: u for u in base_updates if u.from_id == "player"}
        ordered_targets = [u.to_id for u in base_updates if u.from_id == "player"]
        for target_id in jev_fields:
            if target_id not in ordered_targets:
                ordered_targets.append(target_id)

        result: List[RelationshipHistoryUpdate] = [u for u in base_updates if u.from_id != "player"]
        for target_id in ordered_targets:
            existing = by_target.get(target_id)
            fields = jev_fields.get(target_id, {})
            prior_relationship = fields.get("prior_relationship", existing.prior_relationship if existing else None)
            prior_intimacy = fields.get("prior_intimacy", existing.prior_intimacy if existing else None)
            in_relationship = fields.get("in_relationship", existing.in_relationship if existing else None)
            if prior_relationship is None and prior_intimacy is None and in_relationship is None:
                continue
            result.append(RelationshipHistoryUpdate(
                from_id="player", to_id=target_id, prior_relationship=prior_relationship,
                prior_intimacy=prior_intimacy, in_relationship=in_relationship,
            ))
        return result

    @staticmethod
    def _apply_behavior_tag_overrides(
        base_tags: List[BehaviorTagUpdate], outcome: DecisionOutcome,
    ) -> List[BehaviorTagUpdate]:
        """Ability 11 override. Decision ids are `behtag_<from>_<to>`. A
        usable Jev NONE for a pair means "keep whatever legacy had for that
        pair" is WRONG to assume - Jev's NONE is itself an answer (no
        behavior shown), so a Jev-covered pair with NONE must NOT keep a
        stale legacy tag for that same pair. Only pairs Jev never usably
        answered keep their legacy value."""
        jev_by_pair: dict[tuple[str, str], str] = {}
        for decision_id, answer in outcome.answers.items():
            if not decision_id.startswith("behtag_"):
                continue
            if not (answer.usable and answer.provider is Provider.JEV):
                continue
            rest = decision_id[len("behtag_"):]
            parts = rest.split("_", 1)
            if len(parts) != 2:
                continue
            from_id, to_id = parts
            jev_by_pair[(from_id, to_id)] = answer.choice or "NONE"

        if not jev_by_pair:
            return base_tags

        result: List[BehaviorTagUpdate] = [
            u for u in base_tags if (u.from_id, u.to_id) not in jev_by_pair
        ]
        for (from_id, to_id), tag in jev_by_pair.items():
            if tag == "NONE":
                continue
            result.append(BehaviorTagUpdate(from_id=from_id, to_id=to_id, tag=tag))
        return result

    @staticmethod
    def _apply_social_shift_override(
        base_signal: Optional[SocialShiftSignal], outcome: DecisionOutcome,
        behavior_window: Dict[str, Any] | None,
    ) -> Optional[SocialShiftSignal]:
        """Ability 12 override. Jev only judges `certainty` - `new_value`
        (free text, required when certainty="SHIFT") can only come from the
        legacy generative call. NONE/WISH need no new_value and can be
        fully Jev-sourced; a Jev SHIFT can only be applied when legacy's
        OWN social_shift_signal already corroborates the same (subject,
        target) pair with a non-empty new_value - otherwise this degrades
        to `base_signal` unchanged rather than ever writing a SHIFT with no
        description of the new state."""
        if not behavior_window or "->" not in str(behavior_window.get("pair") or ""):
            return base_signal
        subject_id, target_id = str(behavior_window["pair"]).split("->", 1)
        subject_id = subject_id.strip().lower()
        target_id = target_id.strip().lower()

        answer = outcome.answers.get("social_shift_certainty")
        if answer is None or not (answer.usable and answer.provider is Provider.JEV):
            return base_signal

        certainty = answer.choice or "NONE"
        base_matches = (
            base_signal is not None and base_signal.scope == "disposition"
            and base_signal.subject_id == subject_id and base_signal.target_id == target_id
        )

        if certainty == "NONE":
            return None
        if certainty == "WISH":
            return SocialShiftSignal(
                certainty="WISH", scope="disposition", subject_id=subject_id, target_id=target_id,
                new_value="", reason=base_signal.reason if base_matches else "",
            )
        # certainty == "SHIFT"
        if base_matches and base_signal.new_value:
            return SocialShiftSignal(
                certainty="SHIFT", scope="disposition", subject_id=subject_id, target_id=target_id,
                new_value=base_signal.new_value, reason=base_signal.reason,
            )
        return base_signal

    @staticmethod
    def _log_jev_outcome(outcome: DecisionOutcome) -> None:
        """Surfaces the resolver's telemetry (provider_used,
        shadow_disagreements, latencies, usage) to Railway deploy logs via
        jlog - this is the ONLY thing that makes "gather comparison data"
        (shadow mode: Jev runs alongside legacy, doesn't affect output,
        just compares) actually observable. Before this, DecisionOutcome's
        telemetry fields were computed by resolve() and then silently
        discarded by extract() - shadow mode ran for nothing. Logs nothing
        when Jev was never attempted at all (flag off, or every decision
        skipped for lack of registered decisions in a sparse turn) to keep
        default-off production log volume at zero, matching the shipped
        default of TYPESAFE_ENABLED=false."""
        attempted = outcome.provider_used is Provider.JEV or bool(outcome.shadow_disagreements) or any(
            reason not in (FallbackReason.NONE, FallbackReason.FLAG_DISABLED)
            for reason in outcome.fallback_reasons.values()
        )
        if not attempted:
            return
        try:
            jlog({
                "kind": "jev_turn_outcome",
                "provider_used": outcome.provider_used.value,
                "jev_latency_ms": outcome.jev_latency_ms,
                "legacy_latency_ms": outcome.legacy_latency_ms,
                "jev_usage": dict(outcome.jev_usage) if outcome.jev_usage else None,
                "fallback_reasons": {k: v.value for k, v in outcome.fallback_reasons.items()},
                "shadow_disagreement_count": len(outcome.shadow_disagreements),
                "shadow_disagreements": {
                    k: [str(jev_v), str(legacy_v)] for k, (jev_v, legacy_v) in outcome.shadow_disagreements.items()
                },
                "answer_count": len(outcome.answers),
            })
        except Exception:
            pass

    async def _call_legacy_raw(self, request: "LegacyExtractionRequest") -> Dict[str, Any] | None:
        """The legacy one-shot LLM call. Matches LegacyExtractionCallable's
        signature exactly — this IS the `legacy` callable injected into
        DecisionResolver's constructor (see __init__). Returns the parsed
        JSON dict (matching the schema _parse_dict expects), or None on any
        failure — the SAME never-raises contract extract() always had.

        Prompt-building logic is otherwise byte-for-byte identical to what
        used to live inline in extract() before this refactor — only the
        transport changed (OpenAIChatClient via the shared httpx client,
        replacing a per-call httpx.AsyncClient(...) construction; no
        httpx import remains in this file)."""
        user_msg = request.user_msg
        world_locations = request.world_locations
        character_key_to_name = request.character_key_to_name
        previous_turn_user_msg = request.previous_turn_user_msg
        previous_turn_assistant_reply = request.previous_turn_assistant_reply
        previous_turn_candidate_chunks = request.previous_turn_candidate_chunks
        conversation_log = request.conversation_log
        behavior_window = request.behavior_window
        allowed_behavior_tags = [str(t).strip() for t in (request.allowed_behavior_tags or ()) if str(t or "").strip()]

        # BL-16 fix: a closed vocabulary makes behavior_tags a strict-choice
        # extraction instead of free text, which is what makes
        # _ripe_behavior_pairs' exact-string majority vote meaningful. A
        # story that hasn't authored one yet keeps the original free-text
        # rule (accept-anything), byte-for-byte.
        if allowed_behavior_tags:
            vocab_list = ", ".join(f'"{t}"' for t in allowed_behavior_tags)
            behavior_tag_rule = (
                "9) behavior_tags: ALWAYS extract, cheaply, for any character (including player) whose\n"
                "   words or actions THIS TURN showed an observable attitude/behavior toward another\n"
                f"   character present in the scene. tag MUST be exactly one of: {vocab_list}.\n"
                "   Pick the closest matching tag from that list - never invent a new word. Omit if no\n"
                "   clear behavior toward a specific other character is shown, or if none of the allowed\n"
                "   tags fit. This is NOT a judgment about whether anything has changed - just a raw\n"
                "   observation of this turn."
            )
        else:
            behavior_tag_rule = (
                "9) behavior_tags: ALWAYS extract, cheaply, for any character (including player) whose\n"
                "   words or actions THIS TURN showed an observable attitude/behavior toward another\n"
                "   character present in the scene. tag is a short free-text phrase (1-3 words, e.g.\n"
                "   \"aggressive\", \"warm\", \"evasive\", \"protective\", \"dismissive\") describing how\n"
                "   from_id behaved toward to_id in this single turn only. Omit if no clear behavior\n"
                "   toward a specific other character is shown. This is NOT a judgment about whether\n"
                "   anything has changed - just a raw observation of this turn."
            )

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
            f"{behavior_tag_rule}\n"
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

        # OpenAIChatClient.generate() prepends the system message itself
        # (see backend/app/llm/providers/openai_chat.py), so `messages` here
        # is history + the final user turn only — matching every other
        # TextProvider call site's convention, not a behavior change (the
        # combined [system, *history, user] sequence sent over the wire is
        # byte-identical to before this refactor).
        messages: List[Dict[str, str]] = []
        history = [m for m in (conversation_log or []) if m.get("role") in {"user", "assistant"}]
        history = history[-EXTRACTOR_TURNS:] if len(history) > EXTRACTOR_TURNS else history
        messages.extend({"role": str(m.get("role")), "content": str(m.get("content", ""))} for m in history)
        messages.append({"role": "user", "content": user_content})

        try:
            result = await self._legacy_client.generate(
                model=self.model, system=system, messages=messages,
                max_tokens=700, temperature=0,
            )
        except Exception:
            return None

        try:
            obj = json.loads(result.text)
        except Exception:
            return None
        if not isinstance(obj, dict):
            return None
        return obj

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
        allowed_behavior_tags: List[str] | None = None,
    ) -> TurnExtraction:
        """Internally: batch builder -> resolver -> assembler (see class
        docstring and JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §12 step 3).
        `allowed_behavior_tags` is new (BL-16 fix) and optional/keyword-only
        with an empty default, so every existing caller is unaffected."""
        allowed_location_ids = set((world_locations or {}).keys())
        allowed_character_keys = {
            str(k).strip().lower() for k in (character_key_to_name or {}).keys() if str(k).strip()
        }

        # `_invoke` closes over `legacy_request`, which is defined below it —
        # safe via ordinary Python closure late-binding: `_invoke` is only
        # ever CALLED after `legacy_request` has been assigned, never at
        # definition time. Used by extract()'s own fallback path below when
        # the resolver decides it didn't need to call legacy (see that
        # branch's comment for why that can still happen and needs covering
        # here for the 9 not-yet-Jev-eligible fields).
        async def _invoke() -> Dict[str, Any] | None:
            return await self._call_legacy_raw(legacy_request)

        legacy_request = LegacyExtractionRequest(
            user_msg=user_msg,
            world_locations=world_locations or {},
            character_key_to_name=character_key_to_name or {},
            previous_turn_user_msg=previous_turn_user_msg,
            previous_turn_assistant_reply=previous_turn_assistant_reply,
            previous_turn_candidate_chunks=tuple(previous_turn_candidate_chunks or []),
            conversation_log=tuple(conversation_log or []),
            behavior_window=behavior_window,
            allowed_behavior_tags=tuple(allowed_behavior_tags or ()),
            invoke=_invoke,
        )

        batches = self._build_batches(
            user_msg=user_msg, world_locations=world_locations,
            previous_turn_assistant_reply=previous_turn_assistant_reply,
            character_key_to_name=character_key_to_name,
            previous_turn_candidate_chunks=previous_turn_candidate_chunks,
            allowed_behavior_tags=allowed_behavior_tags,
            behavior_window=behavior_window,
        )

        outcome = await self._resolver.resolve(batches, legacy_request)
        self._log_jev_outcome(outcome)

        legacy_raw = outcome.legacy_raw
        if legacy_raw is None:
            # See _build_batches' docstring: ability 12's new_value free
            # text always needs legacy, so a legacy call is still always
            # required somewhere ("hybrid trap", not yet closed) - ensure
            # it happens even when the resolver itself didn't need to call
            # it for any of the now fully-registered choice/score/noul
            # decisions.
            legacy_raw = await legacy_request.invoke()

        base = self._parse_dict(
            legacy_raw or {}, allowed_location_ids, allowed_character_keys,
            set(allowed_behavior_tags or ()),
        )
        return self._apply_decision_overrides(base, outcome, allowed_location_ids, behavior_window)
