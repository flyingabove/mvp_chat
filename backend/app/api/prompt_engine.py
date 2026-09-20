
# app/api/prompt_engine.py
# Prompt Engine: orchestrates all raw context (state, knowledge, history) and
# transforms it into a fully-assembled LLM prompt, then dispatches the API call.

from backend.app.engine.extractors.turn_extractor import (
    TurnExtractor,
    TurnKnowledgeResolution,
)

from fastapi import APIRouter, Depends, Request
from backend.app.auth.dependencies import get_optional_user, _extract_guest_id, is_operator_request
from backend.app.db.repos import SessionRepo, ConversationRepo, FactExtractionOutboxRepo

import asyncio
import dataclasses
import httpx
import json
import logging

import re

import time

import uuid

from typing import Dict, Optional

logger = logging.getLogger(__name__)


from backend.app.knowledge.runtime.retrieve import retrieve_knowledge
from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore
from backend.app.knowledge.runtime.dialogue_extractor import extract_facts_from_message

from backend.app.knowledge.runtime.index_service import IndexService

from backend.app.utils.logging_utils import jlog as _log, truncate as _truncate


from backend.app.config.settings import (

    OPENAI_API_KEY, OPENAI_MODEL,
    STORY_MASTER_BASE_URL, STORY_MASTER_API_KEY, STORY_MASTER_MODEL,

    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS,
    DEFAULT_USER_ID, DEFAULT_INSTANCE,
    TRANSIENT_KNOWLEDGE_TURNS,

)
from backend.app.config.epistemic_flags import set_master


from backend.app.engine.state import (

    init_state,

    apply_state_tag,

    extract_state_tag,

    GameState,

    Character,

)
from backend.app.engine.character_graph import RelationshipEdge, RelationshipState, RelationshipType
from backend.app.engine.cast_lifecycle import CastLifecycleState, CastStatus
from backend.app.engine.world_calendar import PendingEvent, day_number
from backend.app.engine.epistemic_state import EpistemicFact, EpistemicClaim, BeliefState
from backend.app.engine.knowledge_chunks import normalize_parties, KnowledgeChunk
from backend.app.engine.story_loader import load_story, StoryDefinition
from backend.app.engine.gameplay import (

    advance_time,

    win_condition_detected

)
from backend.app.engine.time_utils import WorldTimeFormatter
from backend.app.engine.world.world_loader import WorldLoader
from backend.app.engine.prompt_builder import (

    build_messages,
    _cast_scene_eligible,

)
from backend.app.utils.id_utils import build_deterministic_uuid, build_namespace_key


router = APIRouter()


def _namespace_for_state(state: GameState) -> str:
    return build_namespace_key(
        user_id=getattr(state, "user_id", ""),
        story_id=getattr(state, "story", ""),
        instance=getattr(state, "instance", 1),
    )


def _log_epistemic_event(state: GameState, event: str, **extra) -> None:
    payload = {
        "kind": "epistemic_event",
        "event": event,
        "namespace": _namespace_for_state(state),
        "minute": int(getattr(state, "minute", 0) or 0),
        "location_id": str(getattr(state, "location_id", "") or ""),
    }
    payload.update(extra)
    _log(payload)


def _seed_epistemic_from_story(cfg: dict, state: GameState) -> None:
    """Seed canonical facts and initial beliefs from story config.

    Expected shape in story JSON:
    {
      "epistemic_seed": {
        "canonical_facts": [
          {"id": "fact_1", "content": "...", "subject": "...", "object": "...",
           "provenance": "validated", "confidence": 1.0, "location_ref": "example_location",
           "timestamp_minute": 0, "known_by": ["main", "player"], "source": "system"}
        ],
        "belief_seeds": [
          {"character_id": "player", "claims": [{...EpistemicClaim fields...}]}
        ]
      }
    }
    """

    seed_cfg = (cfg.get("epistemic_seed") or {})

    # Canonical facts (truth layer)
    canonical_facts = seed_cfg.get("canonical_facts") or []
    seeded_texts = []
    for _fact_idx, fact_cfg in enumerate(canonical_facts):
        try:
            fact = EpistemicFact(
                id=str(fact_cfg.get("id") or uuid.uuid4()),
                kind="fact",
                content=str(
                    fact_cfg.get("content")
                    or fact_cfg.get("text")
                    or ""
                ).strip(),
                subject=fact_cfg.get("subject"),
                object=fact_cfg.get("object"),
                source=fact_cfg.get("source", "system"),
                timestamp_minute=fact_cfg.get("timestamp_minute"),
                location_ref=fact_cfg.get("location_ref"),
                confidence=fact_cfg.get("confidence", 1.0),
                provenance=fact_cfg.get("provenance", "validated"),
                known_by=normalize_parties(
                    ["all_characters"] if fact_cfg.get("common_knowledge") else (fact_cfg.get("known_by") or [])
                ),
                not_known_by=normalize_parties(fact_cfg.get("not_known_by") or []),
                maybe_known_by=normalize_parties(fact_cfg.get("maybe_known_by") or []),
            )
            if fact.content:
                state.add_canonical_fact(fact)
                seeded_texts.append(fact.content)
                _log_epistemic_event(
                    state,
                    "seed_canonical_fact",
                    fact_id=fact.id,
                    source=fact.source,
                    provenance=fact.provenance,
                )

                # Mirror as beliefs for characters who already know this fact
                known_by = normalize_parties(
                    ["all_characters"] if fact_cfg.get("common_knowledge") else (fact_cfg.get("known_by") or [])
                )
                for char_id in known_by:
                    if char_id == "all_characters":
                        continue
                    claim = EpistemicClaim(
                        id=f"seed_{fact.id}_{char_id}",
                        kind="claim",
                        content=fact.content,
                        subject=fact.subject,
                        object=fact.object,
                        source=fact.source,
                        timestamp_minute=fact.timestamp_minute,
                        location_ref=fact.location_ref,
                        confidence=fact.confidence,
                        provenance=fact.provenance,
                        known_by=[char_id],
                    )
                    state.get_belief_state(char_id).add_claim(claim)
                    state.add_epistemic_claims(claim)
                    _log_epistemic_event(
                        state,
                        "seed_claim_from_canonical",
                        fact_id=fact.id,
                        claim_id=claim.id,
                        character_id=char_id,
                        source=claim.source,
                        provenance=claim.provenance,
                    )
        except Exception as _fact_exc:
            _log({
                "kind": "canonical_fact_parse_error",
                "fact_index": _fact_idx,
                "fact_id": fact_cfg.get("id") if isinstance(fact_cfg, dict) else None,
                "error": str(_fact_exc),
            })
            continue

    # Additional belief seeds (claims/observations per character)
    belief_seeds_raw = seed_cfg.get("belief_seeds") or []
    # Support both list-of-dicts and mapping-of-character-to-claims shapes
    if isinstance(belief_seeds_raw, dict):
        belief_seeds = [
            {"character_id": cid, "claims": claims}
            for cid, claims in belief_seeds_raw.items()
        ]
    else:
        belief_seeds = belief_seeds_raw

    for bseed in belief_seeds:
        char_id = bseed.get("character_id") or ""
        if not char_id:
            continue
        bs = state.get_belief_state(char_id)
        for claim_cfg in bseed.get("claims", []) or []:
            try:
                claim = EpistemicClaim(
                    id=str(claim_cfg.get("id") or uuid.uuid4()),
                    kind="claim",
                    content=str(
                        claim_cfg.get("content")
                        or claim_cfg.get("text")
                        or ""
                    ).strip(),
                    subject=claim_cfg.get("subject"),
                    object=claim_cfg.get("object"),
                    source=claim_cfg.get("source", char_id),
                    timestamp_minute=claim_cfg.get("timestamp_minute"),
                    location_ref=claim_cfg.get("location_ref"),
                    confidence=claim_cfg.get("confidence", 0.7),
                    provenance=claim_cfg.get("provenance", "testimony"),
                    known_by=normalize_parties(claim_cfg.get("known_by") or [char_id]),
                    not_known_by=normalize_parties(claim_cfg.get("not_known_by") or []),
                    maybe_known_by=normalize_parties(claim_cfg.get("maybe_known_by") or []),
                )
                if claim.content:
                    bs.add_claim(claim)
                    state.add_epistemic_claims(claim)
                    _log_epistemic_event(
                        state,
                        "seed_claim",
                        character_id=char_id,
                        claim_id=claim.id,
                        source=claim.source,
                        provenance=claim.provenance,
                    )
            except Exception:
                continue
        for obs_cfg in bseed.get("observations", []) or []:
            try:
                obs = bs.record_observation(
                    id=str(obs_cfg.get("id") or uuid.uuid4()),
                    content=str(obs_cfg.get("content") or "").strip(),
                    timestamp_minute=obs_cfg.get("timestamp_minute"),
                    location_ref=obs_cfg.get("location_ref"),
                    subject=obs_cfg.get("subject"),
                    object=obs_cfg.get("object"),
                    source=obs_cfg.get("source", char_id),
                    provenance=obs_cfg.get("provenance", "observed"),
                    confidence=obs_cfg.get("confidence", 0.7),
                )
                if obs_cfg.get("log_to_state", True):
                    state.record_observation(**obs.__dict__)
                _log_epistemic_event(
                    state,
                    "seed_observation",
                    character_id=char_id,
                    observation_id=obs.id,
                    source=obs.source,
                    provenance=obs.provenance,
                )
            except Exception:
                continue

    # Backfill canonical_truth strings for truth-mode prompt if not present
    if not cfg.get("canonical_truth") and seeded_texts:
        state.canonical_truth = seeded_texts


def _seed_player_visibility(state: GameState) -> None:
    """Label all knowledge chunks with player visibility at game init.

    Chunks from chunks.jsonl default to player_visible=True (public biographical
    knowledge that a real fan/player would bring to the game). Story designers can
    hide specific chunks by adding ``"player_visible": false`` to a chunk entry in
    chunks.jsonl.

    Populates state.player_visible_chunk_ids with all visible chunk IDs so the
    debug player agent can filter its retrieval to only public knowledge.
    """
    if not state.knowledge_character_id:
        return
    try:
        bundle = IndexService.get(state.knowledge_character_id)
        state.player_visible_chunk_ids = [
            c["chunk_id"]
            for c in bundle.chunks
            if c.get("player_visible", True)
        ]
    except Exception:
        state.player_visible_chunk_ids = []


_BASIC_CHARACTER_KEYS = {
    "key",
    "id",
    "name",
    "role",
    "is_main",
    "is_suspect",
    "suspect",
    "knowledge_character_id",
    "uuid",
    "tags",
}


def _canonicalize_story_cfg(story_obj: StoryDefinition | dict) -> dict:
    src = story_obj.as_dict() if hasattr(story_obj, "as_dict") else (story_obj or {})
    characters = []
    for ch in src.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        characters.append({
            "key": ch.get("key") or ch.get("id") or "",
            "name": ch.get("name") or "",
            "role": ch.get("role") or "",
            "is_main": bool(ch.get("is_main")),
            "is_suspect": bool(ch.get("is_suspect") or ch.get("suspect")),
            "knowledge_character_id": ch.get("knowledge_character_id") or "",
            "uuid": ch.get("uuid") or "",
            "tags": list(ch.get("tags") or []),
        })

    return {
        "id": src.get("id") or "",
        "title": src.get("title") or "",
        "theme": src.get("theme") or "",
        "instance": src.get("instance", DEFAULT_INSTANCE),
        "opening": src.get("opening") or {},
        "world": src.get("world") or {},
        "time": src.get("time") or {},
        "emotion": src.get("emotion") or {},
        "goal": src.get("goal") or {},
        "win_detection": src.get("win_detection") or {},
        "epistemic_seed": src.get("epistemic_seed") or {},
        "canonical_truth": src.get("canonical_truth") or [],
        "characters": characters,
        "relationships": src.get("relationships") or {},
        # Optional ensemble/slice-of-life mode context (see
        # documentation/model_output_docs/SOCIAL_MODE_DESIGN.md). Absent for
        # all pre-existing stories, so this key is simply {} for them and the
        # prompt_builder mode layer emits nothing.
        "mode": src.get("mode") or {},
        "cast_lifecycle": src.get("cast_lifecycle") or {},
    }


def _initialize_cast_lifecycle(state: GameState, snapshot: dict | None = None) -> None:
    """Restore or seed optional rotating-cast state for a story.

    Stories without ``cast_lifecycle.enabled`` retain legacy behavior. A saved
    snapshot is authoritative so departures survive server restarts; older
    saves seed from the authored config on first load.
    """
    config = (getattr(state, "story_cfg", None) or {}).get("cast_lifecycle") or {}
    if snapshot is not None:
        state.cast_lifecycle = CastLifecycleState.from_dict(snapshot)
        return
    if not config or not bool(config.get("enabled", False)):
        state.cast_lifecycle = None
        return
    location_ids = None
    runtime = getattr(state, "world_runtime", None)
    if runtime is not None:
        location_ids = list((getattr(runtime.world_graph, "locations", None) or {}).keys())
    state.cast_lifecycle = CastLifecycleState.from_config(
        config,
        character_ids=(getattr(state, "characters", None) or {}).keys(),
        location_ids=location_ids,
    )


def _cast_roster_payload(state: GameState) -> dict:
    """Return the public roster without exposing upcoming character names."""
    lifecycle = getattr(state, "cast_lifecycle", None)
    if lifecycle is None or not lifecycle.enabled:
        characters = getattr(state, "characters", {}) or {}
        active = [
            {"id": key, "name": ch.name, "role": ch.role}
            for key, ch in characters.items()
        ]
        return {"title": "Cast", "active": active, "vacancies": [], "departed": []}

    characters = getattr(state, "characters", {}) or {}
    active = []
    departed = []
    for key in lifecycle.active_ids():
        ch = characters.get(key)
        if ch is not None:
            active.append({"id": key, "name": ch.name, "role": ch.role})
    for key, member in lifecycle.members.items():
        if member.status is CastStatus.DEPARTED:
            ch = characters.get(key)
            if ch is not None:
                departed.append({"id": key, "name": ch.name, "role": ch.role})
    vacancies = []
    for group, label in lifecycle.slot_labels.items():
        for index in range(lifecycle.vacancies(group)):
            vacancies.append({"id": f"{group}:{index}", "label": label})
    return {
        "title": "Housemates",
        "labels": {"active": "Present", "vacancy": "Room available", "departed": "Moved out"},
        "active": active,
        "vacancies": vacancies,
        "departed": departed,
    }


def _apply_cast_replacement(
    state: GameState,
    departing_id: str,
    *,
    reason: str,
    event_id: str,
    arriving_id: str | None = None,
):
    """Apply one validated replacement and synchronize world-facing state."""
    lifecycle = getattr(state, "cast_lifecycle", None)
    if lifecycle is None:
        raise ValueError("story has no cast lifecycle")
    transition = lifecycle.replace(
        departing_id,
        minute=int(getattr(state, "minute", 0) or 0),
        reason=reason,
        event_id=event_id,
        arriving_id=arriving_id,
    )
    state.character_locations.pop(departing_id, None)
    if transition.arriving_id:
        state.character_locations[transition.arriving_id] = lifecycle.arrival_location_id
    state.transient_entries = [
        entry for entry in (getattr(state, "transient_entries", []) or [])
        if not (getattr(entry, "text", "") or "").strip().endswith(f":{departing_id}")
    ]
    if getattr(state, "main_character_id", None) == departing_id:
        state.main_character_id = transition.arriving_id or next(iter(lifecycle.active_ids()), None)
    return transition


def _seed_noncanonical_story_details_to_transient(story_obj: StoryDefinition | dict, state: GameState) -> None:
    src = story_obj.as_dict() if hasattr(story_obj, "as_dict") else (story_obj or {})
    canonical_top_keys = {
        "id", "title", "theme", "instance", "opening", "world", "time", "emotion",
        "goal", "win_detection", "epistemic_seed", "canonical_truth", "characters", "relationships",
        "character_self_knowledge",  # injected directly into system prompt; not via FAISS
        "mode",  # injected directly via the prompt_builder mode-context layer; not via FAISS
        "cast_lifecycle",  # runtime state; never seed future entrants into transient context
    }

    details: list[str] = []

    for key, value in src.items():
        if key in canonical_top_keys:
            continue
        details.append(f"story.{key}: {json.dumps(value, ensure_ascii=False)}")

    for ch in src.get("characters") or []:
        if not isinstance(ch, dict):
            continue
        ch_key = str(ch.get("key") or ch.get("id") or ch.get("name") or "character")
        extras = {k: v for k, v in ch.items() if k not in _BASIC_CHARACTER_KEYS}
        if extras:
            details.append(f"character.{ch_key}.extras: {json.dumps(extras, ensure_ascii=False)}")

    for i, detail in enumerate(details[:20]):
        text = detail.strip()
        if not text:
            continue
        state.add_transient_entry(
            id=f"story_extra_{i}",
            namespace=_namespace_for_state(state),
            scope="scene",
            text=text[:600],
            expires_after_turns=TRANSIENT_KNOWLEDGE_TURNS,
        )


# In-memory session store (session-scoped: lost on server restart)
# Keys: state (GameState), log (list), debug_mode (bool), chinese_mode (bool)
SESSIONS = {}


# Shared single-call extractor instance (stateless).
_TURN_EXTRACTOR = TurnExtractor()

# Active-character marker TTL (turns without re-mention before expiry)
_ACTIVE_CHAR_TTL_TURNS = TRANSIENT_KNOWLEDGE_TURNS


def _upsert_active_character_markers(state: GameState, active_keys: set[str]) -> None:
    """Create or refresh transient markers for each active character key.

    Removes stale markers for the same keys first (resets TTL), then inserts
    fresh entries. Markers are stored as text values using
    ``__active_character_marker__:<character_key>`` so prompt building can
    read the active set while keeping markers hidden from rendered prompt text.
    """
    # Replace marker set each turn so only currently relevant characters remain.
    state.transient_entries = [
        e for e in state.transient_entries
        if not (
            (getattr(e, "text", "") or "").startswith("__active_character_marker__:")
        )
    ]

    for key in active_keys:
        state.add_transient_entry(
            id=f"active_char::{key}",
            namespace=_namespace_for_state(state),
            scope="scene",
            text=f"__active_character_marker__:{key}",
            expires_after_turns=_ACTIVE_CHAR_TTL_TURNS,
        )


def _upsert_people_present_markers(state: GameState, people_keys: set[str]) -> None:
    """Store current-scene people-present markers for prompt/debug consumption."""
    state.transient_entries = [
        e for e in state.transient_entries
        if not (
            (getattr(e, "text", "") or "").startswith("__people_present_marker__:")
        )
    ]
    for key in people_keys:
        state.add_transient_entry(
            id=f"people_present::{key}",
            namespace=_namespace_for_state(state),
            scope="scene",
            text=f"__people_present_marker__:{key}",
            expires_after_turns=_ACTIVE_CHAR_TTL_TURNS,
        )


def _upsert_scene_speaker_markers(state: GameState, speaker_keys: set[str]) -> None:
    """Store current-turn speaker markers for prompt/debug consumption."""
    state.transient_entries = [
        e for e in state.transient_entries
        if not (
            (getattr(e, "text", "") or "").startswith("__scene_speaker_marker__:")
        )
    ]
    for key in speaker_keys:
        state.add_transient_entry(
            id=f"scene_speaker::{key}",
            namespace=_namespace_for_state(state),
            scope="scene",
            text=f"__scene_speaker_marker__:{key}",
            expires_after_turns=_ACTIVE_CHAR_TTL_TURNS,
        )


def _extract_location_from_reply(state: GameState, reply: str) -> str:
    """Extract best-effort location mention from previous assistant reply.

    Ignores phone-call/off-scene edge cases by design for this iteration.
    """
    runtime = getattr(state, "world_runtime", None)
    if runtime is None:
        return str(getattr(state, "location_id", "") or "")

    text = str(reply or "").strip().lower()
    if not text:
        return str(getattr(state, "location_id", "") or "")

    try:
        for loc_id, loc in (runtime.world_graph.locations or {}).items():
            loc_name = (getattr(loc, "name", "") or "").strip().lower()
            if loc_name and loc_name in text:
                return str(loc_id)
            loc_token = str(loc_id).replace("_", " ").lower()
            if loc_token and loc_token in text:
                return str(loc_id)
    except Exception:
        pass

    return str(getattr(state, "location_id", "") or "")



def _chunk_text(chunk: dict) -> str:
    return str(chunk.get("text") or chunk.get("content") or "").strip()


def _canonical_fact_visibility_for_speaker(state: GameState, speaker_id: str, text: str) -> str:
    txt = (text or "").strip().lower()
    if not txt:
        return "unknown"
    for fact in getattr(state, "canonical_facts", []) or []:
        ftxt = str(getattr(fact, "content", "") or "").strip().lower()
        if not ftxt or ftxt != txt:
            continue
        known_by = normalize_parties(getattr(fact, "known_by", []) or [])
        not_known_by = normalize_parties(getattr(fact, "not_known_by", []) or [])
        if speaker_id in known_by or "all_characters" in known_by:
            return "known"
        if speaker_id in not_known_by:
            return "not_known"
        return "unknown"
    return "unknown"


def _unknown_knowledge_chunks_for_speaker(state: GameState, chunks: list[dict]) -> list[dict]:
    speaker_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
    out: list[dict] = []
    seen = set()
    for c in chunks or []:
        cid = str(c.get("chunk_id") or "").strip()
        text = _chunk_text(c)
        if not cid or not text:
            continue
        if cid in seen:
            continue
        seen.add(cid)
        visibility = _canonical_fact_visibility_for_speaker(state, speaker_id, text)
        if visibility == "unknown":
            out.append({
                "chunk_id": cid,
                "text": text,
                "type": c.get("type"),
                "source": c.get("source"),
            })
    return out


def _upsert_belief_claim_for_resolution(
    *,
    state: GameState,
    speaker_id: str,
    chunk_id: str,
    chunk_text: str,
    knows: bool,
    confidence: float,
    reason: str,
) -> None:
    claim_id = f"kr::{speaker_id}::{chunk_id}"
    bs = state.get_belief_state(speaker_id)

    existing = None
    for c in getattr(bs, "claims", []) or []:
        if getattr(c, "id", "") == claim_id:
            existing = c
            break

    content = (
        f"Knowledge chunk {chunk_id}: speaker {'knows' if knows else 'does_not_know'} this information. "
        f"Chunk text: {chunk_text}"
    )
    if reason:
        content += f" Reason: {reason}"

    if existing is None:
        claim = EpistemicClaim(
            id=claim_id,
            kind="claim",
            content=content,
            source="knowledge_resolution_extractor",
            confidence=confidence,
            provenance="inferred_dialogue",
            known_by=[speaker_id] if knows else [],
            not_known_by=[speaker_id] if not knows else [],
            maybe_known_by=[],
        )
        bs.add_claim(claim)
        state.add_epistemic_claims(claim)
    else:
        existing.content = content
        existing.source = "knowledge_resolution_extractor"
        existing.confidence = confidence
        existing.provenance = "inferred_dialogue"
        existing.known_by = [speaker_id] if knows else []
        existing.not_known_by = [speaker_id] if not knows else []
        existing.maybe_known_by = []


def apply_knowledge_resolution_updates(
    *,
    state: GameState,
    updates: list[TurnKnowledgeResolution],
    candidate_chunks: list[dict],
) -> list[dict]:
    speaker_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
    if not speaker_id:
        return []

    by_id = {str(c.get("chunk_id") or "").strip(): c for c in (candidate_chunks or [])}
    applied: list[dict] = []

    for u in updates or []:
        chunk_id = str(getattr(u, "chunk_id", "") or "").strip()
        if not chunk_id:
            continue
        chunk = by_id.get(chunk_id) or {}
        chunk_text = _chunk_text(chunk)
        if not chunk_text:
            continue

        knows = bool(getattr(u, "knows", False))
        confidence = float(getattr(u, "confidence", 0.0) or 0.0)
        reason = str(getattr(u, "reason", "") or "").strip()

        _upsert_belief_claim_for_resolution(
            state=state,
            speaker_id=speaker_id,
            chunk_id=chunk_id,
            chunk_text=chunk_text,
            knows=knows,
            confidence=confidence,
            reason=reason,
        )

        state.add_transient_entry(
            id=f"kr_transient::{speaker_id}::{chunk_id}",
            namespace=_namespace_for_state(state),
            scope="conversation",
            text=(
                f"KnowledgeResolution chunk={chunk_id} speaker={speaker_id} "
                f"knows={str(knows).lower()} conf={confidence:.2f} text={chunk_text}"
            ),
            expires_after_turns=TRANSIENT_KNOWLEDGE_TURNS,
        )

        applied.append({
            "chunk_id": chunk_id,
            "speaker": speaker_id,
            "knows": knows,
            "confidence": confidence,
            "reason": reason,
        })

    return applied


# ---------------------------------------------------------------------------
# DEBUG MODE TOGGLE
# ---------------------------------------------------------------------------
DEBUG_TOGGLE_TOKENS = {
    "[DEBUG]",
    "(DEBUG)",
    "[D]",
    "(D)",
}


def _is_debug_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in DEBUG_TOGGLE_TOKENS


# ---------------------------------------------------------------------------
# CHINESE MODE TOGGLE
# ---------------------------------------------------------------------------
CHINESE_TOGGLE_TOKENS = {
    "[CHINESE]",
    "(CHINESE)",
    "[C]",
    "(C)",
}


def _is_chinese_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in CHINESE_TOGGLE_TOKENS


# ---------------------------------------------------------------------------
# MAP TOGGLE
# ---------------------------------------------------------------------------
MAP_TOGGLE_TOKENS = {
    "[MAP]",
    "(MAP)",
    "[M]",
    "(M)",
}


def _is_map_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in MAP_TOGGLE_TOKENS


CAST_ROSTER_TOKENS = {"[CAST]", "(CAST)"}


def _is_cast_roster_request(msg: str) -> bool:
    return (msg or "").strip().upper() in CAST_ROSTER_TOKENS


# ---------------------------------------------------------------------------
# TRUTH MODE TOGGLE
# ---------------------------------------------------------------------------
TRUTH_TOGGLE_TOKENS = {
    "[TRUTH]",
    "(TRUTH)",
    "[T]",
    "(T)",
}


def _is_truth_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in TRUTH_TOGGLE_TOKENS


EPISTEMIC_TOGGLE_TOKENS = {
    "[ES]",
    "(ES)",
    "[EPISTEMICSTATE]",
    "(EPISTEMICSTATE)",
}


def _is_epistemic_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in EPISTEMIC_TOGGLE_TOKENS


def _match_world_destination(msg: str, runtime, current_location_id: str = "") -> str:
    """Heuristic location matcher for world-graph travel.

    The LLM-based extractor can miss natural phrasing like "i got to room b".
    This fallback checks for a movement verb plus a known location name/id.
    Returns a destination_id or "" if no confident match.
    """

    text = (msg or "").strip().lower()
    if not text:
        return ""

    verbs = ("go", "got", "move", "head", "walk", "switch", "return", "back", "enter", "step", "run")
    if not any(re.search(rf"\b{v}\b", text) for v in verbs):
        return ""

    try:
        locations = getattr(runtime, "world_graph", None).locations if runtime else {}
    except Exception:
        locations = {}

    for loc_id, loc in (locations or {}).items():
        name = (getattr(loc, "name", "") or "").lower()
        tokens = [name, loc_id.replace("_", " ").lower(), str(loc_id).lower()]
        if any(tok and tok in text for tok in tokens):
            if loc_id == current_location_id:
                return ""  # already there; do nothing
            return loc_id

    return ""


def _debug_speakers(state: GameState) -> list[str]:
    """Return display names of characters marked as current-turn speakers."""
    marker_keys: list[str] = []
    for entry in getattr(state, "transient_entries", []) or []:
        txt = (getattr(entry, "text", "") or "").strip()
        if not txt.startswith("__scene_speaker_marker__:"):
            continue
        marker_keys.append(txt.split(":", 1)[1].strip().lower())

    if marker_keys:
        seen = set()
        marker_keys = [k for k in marker_keys if not (k in seen or seen.add(k))]
        characters = getattr(state, "characters", {}) or {}
        names: list[str] = []
        for key in marker_keys:
            ch = characters.get(key)
            name = (getattr(ch, "name", "") or "").strip() if ch else key.replace("_", " ").title()
            if name:
                names.append(name)
        if names:
            return names

    # Backward-compatible fallback when markers are not available.
    from backend.app.engine.active_characters import get_character_location_index

    loc_id = (getattr(state, "location_id", "") or "").strip()
    if not loc_id:
        return []

    index = get_character_location_index(state)  # {char_key: location_id}
    chars_at_loc = [key for key, loc in index.items() if loc == loc_id]
    if not chars_at_loc:
        return []

    characters = getattr(state, "characters", {}) or {}
    names: list[str] = []
    for key in chars_at_loc:
        ch = characters.get(key)
        name = (getattr(ch, "name", "") or "").strip() if ch else key.replace("_", " ").title()
        if name:
            names.append(name)
    return names


def _debug_people_present(state: GameState) -> list[str]:
    from backend.app.engine.active_characters import get_people_present_keys

    keys = sorted(get_people_present_keys(state))
    if not keys:
        return []
    characters = getattr(state, "characters", {}) or {}
    names: list[str] = []
    for key in keys:
        ch = characters.get(key)
        name = (getattr(ch, "name", "") or "").strip() if ch else key.replace("_", " ").title()
        if name:
            names.append(name)
    return names


def _box(title: str, lines: list[str]) -> str:
    """Render a simple pretty ASCII box."""
    title = (title or "").strip()
    safe_lines = [str(x) for x in (lines or [])]
    inner_width = max([len(title)] + [len(x) for x in safe_lines] + [0])

    top = "┌" + "─" * (inner_width + 2) + "┐"
    mid_title = "│ " + title.ljust(inner_width) + " │" if title else None
    # Render separator if there's a title OR lines (to properly separate title from content)
    sep = "├" + "─" * (inner_width + 2) + "┤" if (title or safe_lines) else None
    body = ["│ " + x.ljust(inner_width) + " │" for x in safe_lines]
    bottom = "└" + "─" * (inner_width + 2) + "┘"

    parts = [top]
    if mid_title:
        parts.append(mid_title)
    if sep:
        parts.append(sep)
    parts.extend(body)
    parts.append(bottom)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CHINESE TRANSLATION
# ---------------------------------------------------------------------------
async def _translate_to_chinese(text: str) -> str:
    """
    Translate English text to Chinese using OpenAI API.
    Preserves formatting: bold, italics, quotes, punctuation, line breaks.
    """
    if not text or not text.strip():
        return text
    
    try:
        prompt = (
            "Translate the following English text to Simplified Chinese. "
            "IMPORTANT: Preserve ALL formatting including: bold (**text**), "
            "italics (*text*), quotes, newlines, punctuation, and special characters. "
            "Keep the layout and structure exactly the same as the original. "
            "Only translate the actual words, not the formatting markers. "
            "Return ONLY the translated text, no explanations.\n\n"
            f"Text to translate:\n{text}"
        )
        
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional translator. Translate English to Simplified Chinese while preserving exact formatting."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Lower temperature for consistent translations
            "max_tokens": len(text) + 200,  # Chinese typically needs fewer characters
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
        
        if r.status_code < 200 or r.status_code >= 300:
            _log({
                "kind": "chinese_translation_error",
                "status": r.status_code,
                "error": _truncate(r.text, 1000),
            })
            return text  # Fallback to English on error
        
        data = r.json()
        translated = str(data["choices"][0]["message"]["content"]).strip()
        return translated
        
    except Exception as e:
        _log({
            "kind": "chinese_translation_exception",
            "error": str(e),
        })
        return text  # Fallback to English on error


# ---------------------------------------------------------------------------
# STATE SERIALIZATION / RESTORATION  (only safe primitive fields)
# ---------------------------------------------------------------------------
def _serialize_character_graph(graph) -> dict:
    if graph is None:
        return {"edges": {}}

    edges: dict[str, dict] = {}
    for key, edge in (getattr(graph, "edges", {}) or {}).items():
        try:
            edges[str(key)] = {
                "id": str(getattr(edge, "id", "") or key),
                "from_id": str(getattr(edge, "from_id", "") or ""),
                "to_id": str(getattr(edge, "to_id", "") or ""),
                "type": str(getattr(getattr(edge, "type", RelationshipType.OTHER), "value", RelationshipType.OTHER.value)),
                "state": {
                    "trust": float(getattr(getattr(edge, "state", None), "trust", 0.0) or 0.0),
                    "fear": float(getattr(getattr(edge, "state", None), "fear", 0.0) or 0.0),
                    "affection": float(getattr(getattr(edge, "state", None), "affection", 0.0) or 0.0),
                    "suspicion": float(getattr(getattr(edge, "state", None), "suspicion", 0.0) or 0.0),
                    "jealousy": float(getattr(getattr(edge, "state", None), "jealousy", 0.0) or 0.0),
                },
                "label": str(getattr(edge, "label", "") or ""),
                "narrative": str(getattr(edge, "narrative", "") or ""),
                "narrative_log": [str(x) for x in (getattr(edge, "narrative_log", []) or [])],
                "met_at": getattr(edge, "met_at", None),
                "last_met_at": getattr(edge, "last_met_at", None),
                "meeting_count": int(getattr(edge, "meeting_count", 0) or 0),
                "prior_relationship": bool(getattr(edge, "prior_relationship", False)),
                "prior_intimacy": bool(getattr(edge, "prior_intimacy", False)),
                "in_relationship": bool(getattr(edge, "in_relationship", False)),
            }
        except Exception:
            continue

    return {"edges": edges}


def _serialize_knowledge_chunk(chunk: KnowledgeChunk) -> dict:
    return dataclasses.asdict(chunk)


def _restore_knowledge_chunk(data: dict) -> Optional[KnowledgeChunk]:
    if not isinstance(data, dict):
        return None
    fields = {f.name for f in dataclasses.fields(KnowledgeChunk)}
    try:
        return KnowledgeChunk(**{k: v for k, v in data.items() if k in fields})
    except Exception:
        return None


def _serialize_beliefs(beliefs: Dict[str, BeliefState]) -> dict:
    out: dict[str, dict] = {}
    for char_id, bs in (beliefs or {}).items():
        out[str(char_id)] = {
            "character_id": str(getattr(bs, "character_id", char_id) or char_id),
            "claims": [_serialize_knowledge_chunk(c) for c in (getattr(bs, "claims", []) or [])],
            "observations": [_serialize_knowledge_chunk(o) for o in (getattr(bs, "observations", []) or [])],
        }
    return out


def _restore_beliefs(saved: dict | None) -> Dict[str, BeliefState]:
    beliefs: Dict[str, BeliefState] = {}
    if not isinstance(saved, dict):
        return beliefs
    for char_id, data in saved.items():
        if not isinstance(data, dict):
            continue
        bs = BeliefState(character_id=str(data.get("character_id") or char_id))
        bs.claims = [c for c in (_restore_knowledge_chunk(x) for x in (data.get("claims") or [])) if c is not None]
        bs.observations = [
            o for o in (_restore_knowledge_chunk(x) for x in (data.get("observations") or [])) if o is not None
        ]
        beliefs[str(char_id)] = bs
    return beliefs


def _serialize_pending_events(events: list) -> list:
    return [e.to_dict() for e in (events or [])]


def _restore_pending_events(saved: list | None) -> list:
    if not isinstance(saved, list):
        return []
    restored = []
    for item in saved:
        if not isinstance(item, dict):
            continue
        try:
            restored.append(PendingEvent.from_dict(item))
        except ValueError:
            continue
    return restored


def _restore_character_graph(state: GameState, graph_snapshot: dict | None) -> None:
    if not isinstance(graph_snapshot, dict):
        return

    graph = getattr(state, "character_graph", None)
    if graph is None:
        return

    raw_edges = graph_snapshot.get("edges") or {}
    if isinstance(raw_edges, list):
        entries = [(str(i), item) for i, item in enumerate(raw_edges) if isinstance(item, dict)]
    elif isinstance(raw_edges, dict):
        entries = [(str(k), v) for k, v in raw_edges.items() if isinstance(v, dict)]
    else:
        return

    for edge_key, data in entries:
        from_id = str(data.get("from_id") or "").strip()
        to_id = str(data.get("to_id") or "").strip()
        if (not from_id or not to_id) and "->" in edge_key:
            from_id, to_id = [x.strip() for x in edge_key.split("->", 1)]
        if not from_id or not to_id:
            continue

        type_raw = str(data.get("type", RelationshipType.OTHER.value)).upper()
        try:
            rel_type = RelationshipType(type_raw)
        except Exception:
            rel_type = RelationshipType.OTHER

        rel_state = RelationshipState.from_dict(data.get("state") or {})
        narrative_log = [str(x) for x in (data.get("narrative_log") or [])]

        existing = graph.get_edge(from_id, to_id)
        if existing is not None:
            existing.type = rel_type
            existing.state = rel_state
            existing.label = str(data.get("label", "") or "")
            existing.narrative = str(data.get("narrative", "") or "")
            existing.narrative_log = narrative_log
            existing.met_at = data.get("met_at")
            existing.last_met_at = data.get("last_met_at")
            existing.meeting_count = int(data.get("meeting_count", 0) or 0)
            existing.prior_relationship = bool(data.get("prior_relationship", False))
            existing.prior_intimacy = bool(data.get("prior_intimacy", False))
            existing.in_relationship = bool(data.get("in_relationship", False))
            continue

        new_edge = RelationshipEdge(
            id=str(data.get("id") or edge_key),
            from_id=from_id,
            to_id=to_id,
            type=rel_type,
            state=rel_state,
            label=str(data.get("label", "") or ""),
            narrative=str(data.get("narrative", "") or ""),
            narrative_log=narrative_log,
            met_at=data.get("met_at"),
            last_met_at=data.get("last_met_at"),
            meeting_count=int(data.get("meeting_count", 0) or 0),
            prior_relationship=bool(data.get("prior_relationship", False)),
            prior_intimacy=bool(data.get("prior_intimacy", False)),
            in_relationship=bool(data.get("in_relationship", False)),
        )
        graph.edges[graph._edge_key(from_id, to_id)] = new_edge


def _serialize_session_chunks(state: GameState) -> list[dict]:
    store = getattr(state, "session_chunk_store", None)
    if store is None:
        return []

    all_chunks = []
    try:
        all_chunks = store.all_chunks() if hasattr(store, "all_chunks") else []
    except Exception:
        return []

    out: list[dict] = []
    for c in all_chunks or []:
        if not isinstance(c, dict):
            continue
        chunk_id = str(c.get("chunk_id") or "").strip()
        text = str(c.get("text") or c.get("content") or "").strip()
        if not chunk_id or not text:
            continue
        out.append(
            {
                "chunk_id": chunk_id,
                "text": text,
                "type": str(c.get("type") or "dialogue_fact"),
                "source": str(c.get("source") or "dialogue_extractor"),
                "character_id": str(c.get("character_id") or ""),
                "timestamp": c.get("timestamp"),
            }
        )
    return out


def _serialize_state(state: GameState, log: list) -> str:
    """Serialize only the fields needed to resume a session after a restart."""
    return json.dumps({
        "story": state.story,
        "gender": state.gender,
        "player_name": state.player_name,
        "minute": state.minute,
        "location": state.location,
        "location_id": getattr(state, "location_id", ""),
        "emotion": state.emotion,
        "relationship": state.relationship,
        "turns": state.turns,
        "over": state.over,
        "instance": state.instance,
        "character_locations": dict(getattr(state, "character_locations", {}) or {}),
        "cast_lifecycle": (
            state.cast_lifecycle.to_dict()
            if getattr(state, "cast_lifecycle", None) is not None else None
        ),
        "pending_events": _serialize_pending_events(getattr(state, "pending_events", []) or []),
        "world_start_datetime": str(getattr(state, "world_start_datetime", "") or ""),
        "last_travel_from_id": str(getattr(state, "last_travel_from_id", "") or ""),
        "last_travel_to_id": str(getattr(state, "last_travel_to_id", "") or ""),
        "last_turn_user_msg": str(getattr(state, "last_turn_user_msg", "") or ""),
        "last_turn_assistant_reply": str(getattr(state, "last_turn_assistant_reply", "") or ""),
        "last_turn_retrieved_chunks": [dict(c) for c in (getattr(state, "last_turn_retrieved_chunks", []) or [])],
        "character_graph": _serialize_character_graph(getattr(state, "character_graph", None)),
        "beliefs": _serialize_beliefs(getattr(state, "beliefs", {}) or {}),
        "observation_log": [_serialize_knowledge_chunk(o) for o in (getattr(state, "observation_log", []) or [])],
        "session_chunks": _serialize_session_chunks(state),
        "user_formal_name": getattr(state.user, "formal_name", "") if state.user else "",
        "user_display_name": getattr(state.user, "display_name", "") if state.user else "",
        "user_persona_mode": getattr(state.user, "persona_mode", "") if state.user else "",
        "user_persona_name": getattr(state.user, "persona_name", "") if state.user else "",
        "user_persona_other": getattr(state.user, "persona_other", "") if state.user else "",
        "log": log,
    })


def _try_load_session_from_db(session_id: str, user_id: str) -> dict | None:
    """
    Try to restore a session from SQLite. Returns a SESSIONS-shaped dict or None.
    Uses the synchronous SessionRepo._get() directly — safe because SQLite indexed
    lookups are sub-millisecond and this avoids async event-loop complications.
    """
    try:
        row = SessionRepo._get(session_id=session_id, user_id=user_id)
    except Exception:
        logger.exception("Failed to load session %s from DB", session_id)
        return None

    if not row:
        logger.info("Session %s not found in DB for user %s", session_id, user_id)
        return None

    try:
        saved = json.loads(row.get("state_json") or "{}")
        flags = json.loads(row.get("flags_json") or "{}")
    except Exception:
        logger.exception("Failed to parse state/flags JSON for session %s", session_id)
        return None

    # If state_json doesn't have story, fall back to the DB row's story_id
    if not saved.get("story"):
        saved["story"] = row.get("story_id", "")
    if not saved.get("story"):
        logger.warning("Session %s has no story in state_json or DB row", session_id)
        return None
    # Populate player_name/gender from DB row if missing from state_json
    if not saved.get("player_name"):
        saved["player_name"] = row.get("player_name", "Player")
    if not saved.get("gender"):
        saved["gender"] = row.get("gender", "M")

    # Rebuild full GameState from saved primitives (mirrors __cmd_newgame__ setup)
    try:
        story_id = saved["story"]
        story_def = load_story(story_id)
        if not story_def:
            return None
        restored = init_state()
        restored.story = story_id
        restored.gender = saved.get("gender", "M")
        restored.player_name = saved.get("player_name", "Player")
        restored.minute = saved.get("minute", 0)
        restored.location = saved.get("location", "")
        restored.location_id = saved.get("location_id", "")
        restored.emotion = saved.get("emotion", "neutral")
        restored.relationship = saved.get("relationship", 0)
        restored.turns = saved.get("turns", 0)
        restored.over = saved.get("over", False)
        restored.instance = saved.get("instance", 1)
        restored.world_start_datetime = saved.get("world_start_datetime", "")
        restored.last_travel_from_id = saved.get("last_travel_from_id", "")
        restored.last_travel_to_id = saved.get("last_travel_to_id", "")
        restored.last_turn_user_msg = saved.get("last_turn_user_msg", "")
        restored.last_turn_assistant_reply = saved.get("last_turn_assistant_reply", "")
        restored.last_turn_retrieved_chunks = [
            dict(c) for c in (saved.get("last_turn_retrieved_chunks") or []) if isinstance(c, dict)
        ]
        restored.story_cfg = _canonicalize_story_cfg(story_def)
        restored.user_id = user_id
        if restored.user:
            restored.user.formal_name = saved.get("user_formal_name", restored.player_name)
            restored.user.display_name = saved.get("user_display_name", restored.player_name)
            restored.user.gender = restored.gender
            # Restore persona metadata if present (persona_mode: 'temp'|'default', persona_name: label/key)
            try:
                restored.user.persona_mode = saved.get("user_persona_mode", restored.user.persona_mode)
                restored.user.persona_name = saved.get("user_persona_name", restored.user.persona_name)
                restored.user.persona_other = saved.get("user_persona_other", restored.user.persona_other)
            except Exception:
                # Be tolerant of missing fields from older saves
                pass

        # Canonical truth (for truth-mode override guidance)
        restored.canonical_truth = story_def.get("canonical_truth", [])

        # --- World runtime (same as newgame) ---
        world_cfg = story_def.get("world", {}) or {}
        seed = int(world_cfg.get("seed", 0))
        world_file = str(world_cfg.get("file", "")).strip()
        if world_file:
            loaded = WorldLoader.load_from_file(
                f"backend/app/stories/{world_file}",
                seed=seed,
                user_id=restored.user_id,
                story_id=story_id,
                instance=restored.instance,
            )
        else:
            loaded = WorldLoader.try_load_story_world(
                story_id,
                stories_dir="backend/app/stories",
                seed=seed,
                user_id=restored.user_id,
                instance=restored.instance,
            )
        if loaded is not None:
            restored.world_runtime = loaded
            # A07 fix: WorldLoader always builds a *fresh* WorldClock seeded
            # from the authored world's start_minute. Resync it to the
            # persisted, authoritative `restored.minute` here so a later
            # travel action advances from the restored game time instead of
            # the freshly-authored start — otherwise travel would silently
            # overwrite state.minute with (authored_start + delta), rolling
            # the clock backward relative to what was saved.
            try:
                restored.world_runtime.world_clock.set_minute(int(restored.minute))
            except Exception:
                logger.exception("Failed to resync world clock on restore for session")
            # Keep saved location rather than overriding with start
            if not restored.location_id:
                start_id = str(world_cfg.get("start_location_id", "")).strip()
                if not start_id:
                    try:
                        start_id = next(iter(loaded.world_graph.locations.keys()), "")
                    except Exception:
                        start_id = ""
                if start_id and start_id in loaded.world_graph.locations:
                    restored.location_id = start_id
                    try:
                        restored.location = loaded.world_graph.locations[start_id].name
                    except Exception:
                        pass
            restored.world_start_datetime = str(world_cfg.get("start_datetime", "")).strip()

        # --- Character roster (same as newgame) ---
        main_char_def = story_def.main_character if isinstance(story_def, StoryDefinition) else None
        characters = list(story_def.characters) if isinstance(story_def, StoryDefinition) else []

        if not characters:
            legacy_main = (story_def.get("main_character", {}) or {}) if hasattr(story_def, "get") else {}
            if legacy_main:
                main_char_def = Character.from_dict({**legacy_main, "is_main": True})
                characters.append(main_char_def)
            for sus in (story_def.get("suspects", []) or []) if hasattr(story_def, "get") else []:
                characters.append(Character.from_dict({**sus, "is_suspect": True}))

        if not characters:
            main_char_def = Character.from_dict({"key": "MAIN", "name": "the character", "role": "npc", "is_main": True})
            characters.append(main_char_def)

        if not main_char_def and characters:
            main_char_def = next((c for c in characters if c.is_main), characters[0])

        story_self_knowledge = list(
            (story_def.get("character_self_knowledge") or []) if hasattr(story_def, "get") else []
        )

        for ch in characters:
            ch_uuid = ch.uuid or build_deterministic_uuid(
                user_id=restored.user_id,
                story_id=story_id,
                instance=restored.instance,
                entity_id=ch.key,
            )
            game_char = Character(
                key=ch.key,
                name=ch.name,
                role=ch.role or "npc",
                is_main=ch.is_main,
                is_suspect=ch.is_suspect,
                knowledge_character_id=ch.knowledge_character_id,
                uuid=ch_uuid,
                tags=list(ch.tags),
                meta=dict(ch.meta),
                self_knowledge=(
                    list(ch.self_knowledge)
                    if ch.self_knowledge
                    else (story_self_knowledge if ch.is_main else [])
                ),
                emotion=restored.emotion,
                relationship=restored.relationship,
            )
            restored.characters[ch.key] = game_char
            if ch.is_main:
                restored.main_character_id = ch.key
            if ch.is_main and ch.knowledge_character_id and not restored.knowledge_character_id:
                restored.knowledge_character_id = ch.knowledge_character_id

        if not restored.main_character_id and main_char_def:
            restored.main_character_id = main_char_def.key

        _initialize_cast_lifecycle(restored, saved.get("cast_lifecycle"))

        # Character start locations
        char_start_locs = world_cfg.get("character_start_locations") or {}
        if isinstance(char_start_locs, dict):
            restored.character_locations = {
                str(k).strip(): str(v).strip()
                for k, v in char_start_locs.items()
                if k and v
            }

        # Persisted runtime character locations override start defaults.
        if isinstance(saved.get("character_locations"), dict):
            restored.character_locations = {
                str(k).strip(): str(v).strip()
                for k, v in (saved.get("character_locations") or {}).items()
                if k and v
            }

        if (
            restored.cast_lifecycle is not None
            and restored.main_character_id
            and not restored.cast_lifecycle.is_scene_eligible(restored.main_character_id)
        ):
            restored.main_character_id = next(iter(restored.cast_lifecycle.active_ids()), None)

        # Character relationship graph
        if isinstance(story_def, StoryDefinition) and story_def.relationships:
            restored.character_graph = story_def.relationships
            _restore_character_graph(restored, saved.get("character_graph"))

        # Fallback knowledge bundle
        if not restored.knowledge_character_id and main_char_def:
            restored.knowledge_character_id = main_char_def.knowledge_character_id

        # Session chunk store
        restored.session_chunk_store = SessionChunkStore()
        restored.session_chunk_store.add_chunks([
            dict(c) for c in (saved.get("session_chunks") or []) if isinstance(c, dict)
        ])

        # Re-seed epistemic and transient knowledge (same as newgame). Canonical
        # facts are static authored content and safe to re-derive every restore.
        # Beliefs/observations are player-driven runtime state: restore the saved
        # values when present, and only fall back to re-seeding belief_seeds for
        # a session that has none saved yet (first restore of an old save, or a
        # session that genuinely has no belief history).
        _seed_epistemic_from_story(restored.story_cfg, restored)
        saved_beliefs = saved.get("beliefs")
        if saved_beliefs:
            restored.beliefs = _restore_beliefs(saved_beliefs)
        saved_observations = saved.get("observation_log")
        if saved_observations:
            restored.observation_log = [
                c for c in (_restore_knowledge_chunk(x) for x in saved_observations) if c is not None
            ]
        saved_pending_events = saved.get("pending_events")
        if saved_pending_events:
            restored.pending_events = _restore_pending_events(saved_pending_events)
        restored.clear_all_transient_entries()
        _seed_noncanonical_story_details_to_transient(story_def, restored)

        # Label knowledge chunks with player visibility
        _seed_player_visibility(restored)

        logger.info("Restored session %s for user %s (story=%s, turns=%d)",
                     session_id, user_id, story_id, restored.turns)

        return {
            "state": restored,
            "log": saved.get("log", []),
            "debug_mode": flags.get("debug_mode", False),
            "chinese_mode": flags.get("chinese_mode", False),
            "epistemic_state": flags.get("epistemic_state", True),
            "truth_mode": flags.get("truth_mode", False),
            "user_id": user_id,
        }
    except Exception:
        logger.exception("Failed to rebuild GameState for session %s", session_id)
        return None


# ---------------------------------------------------------------------------
# SESSION RETRIEVAL
# ---------------------------------------------------------------------------
def get_session(session_id: str, user_id: str = "anon"):
    if session_id not in SESSIONS:
        # Try to restore from DB on cache miss (handles server restarts)
        restored = _try_load_session_from_db(session_id, user_id)
        if restored:
            SESSIONS[session_id] = restored
        else:
            SESSIONS[session_id] = {
                "state": init_state(),
                "log": [],
                "debug_mode": False,
                "chinese_mode": False,
                "epistemic_state": True,
                "truth_mode": False,
                "user_id": user_id,
            }

    # Verify ownership on cache hit to prevent cross-user leaks.
    # IMPORTANT: do NOT exempt "anon" from either side of this comparison.
    # A01 fix: the previous check only compared owners when *both* the
    # cached owner and the requesting caller were non-anonymous, which let
    # an unauthenticated caller (user_id="anon") read any real owner's
    # cached session, and let a session cached under "anon" be handed to a
    # different real caller. Ownership must match exactly, always.
    cached = SESSIONS[session_id]
    cached_owner = cached.get("user_id", "anon")
    if cached_owner != user_id:
        logger.warning(
            "Session %s owned by %s but requested by %s — creating fresh",
            session_id, cached_owner, user_id,
        )
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": user_id,
        }

    return SESSIONS[session_id]


# ---------------------------------------------------------------------------
# PLACEHOLDERS FOR OPENING TEXT ONLY
# ---------------------------------------------------------------------------
def apply_placeholders(text: str, state: GameState) -> str:
    name = state.player_name or "Player"
    cfg = getattr(state, "story_cfg", {}) or {}
    if hasattr(cfg, "get"):
        lang = cfg.get("language", {}) or {}
    else:
        lang = {}
    honorific_map = lang.get("honorifics", {}) or {}
    honorific = honorific_map.get(state.gender, "")
    return (
        text.replace("{{PLAYER_NAME}}", name)
            .replace("{{HONORIFIC}}", honorific)
    )


# ---------------------------------------------------------------------------
# HONORIFIC SANITIZER
# ---------------------------------------------------------------------------
def sanitize_honorific_terms(text: str, state: GameState) -> str:
    """Strip forbidden honorifics when relationship is too low. Terms from story config."""
    rel = state.relationship or 0
    display_name = (state.user.display_name or "").strip()

    cfg = getattr(state, "story_cfg", {}) or {}
    if hasattr(cfg, "get"):
        lang = cfg.get("language", {}) or {}
    else:
        lang = {}
    forbidden = lang.get("forbidden_honorifics") or []

    if rel < 2:
        for term in forbidden:
            pattern = rf"(?i)(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])"
            repl = display_name if display_name else ""
            text = re.sub(pattern, repl, text)

    return text


# ---------------------------------------------------------------------------
# NAME EXTRACTION
# ---------------------------------------------------------------------------
NAME_PATTERNS = [
    r"\bmy name is ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bcall me ([A-Za-z][A-Za-z\s'\-]{0,40})",  # also matches "you can call me", "just call me"
    r"\bit'?s ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bi am ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bim ([A-Za-z][A-Za-z\s'\-]{0,40})",
]


def clean_name(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"[^\w\s'\-]", "", raw)
    return raw.title()[:40]


def extract_user_name_from_text(user_msg: str) -> str:
    txt = user_msg.lower()

    for pat in NAME_PATTERNS:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            return clean_name(m.group(1))

    solo = re.fullmatch(r"[A-Za-z][A-Za-z\s'\-]{0,40}", user_msg.strip())
    if solo:
        return clean_name(solo.group(0))

    return ""


# ---------------------------------------------------------------------------
# NAME CONFIRMATION
# ---------------------------------------------------------------------------
CONFIRM_WORDS = [
    "yes", "yeah", "yea", "yup", "correct",
    "right", "that's right", "mhmm", "mm", "sure"
]


def handle_name_confirmation(user_msg: str, state: GameState):
    guess = (state.last_assistant_guess_name or "").strip()
    if not guess:
        return

    low = user_msg.lower()
    if any(w in low for w in CONFIRM_WORDS):
        state.user.formal_name = guess
        if not state.user.display_name:
            state.user.display_name = guess
        state.last_assistant_guess_name = ""


# ---------------------------------------------------------------------------
# A12: per-session turn serialization
# ---------------------------------------------------------------------------
# The turn pipeline reads/mutates shared mutable state cached in SESSIONS,
# awaits a model call, then persists in a separate step — two overlapping
# calls for the SAME session_id (parallel tabs, a client retry racing the
# original request, etc.) could interleave and double-apply a turn or have
# one overwrite the other's progress. A per-process asyncio.Lock keyed by
# session_id is sufficient here because this service runs a single uvicorn
# worker process (see Dockerfile's `exec uvicorn ... ` with no --workers
# flag, and Railway.toml has no replica/scale config) — if that ever
# changes to multiple worker processes/containers serving the same
# session, this in-process lock stops being sufficient and a DB-level
# revision/optimistic-concurrency check would additionally be needed. Not
# implemented here: request-ID based dedup of an identical retried
# request (the audit's fuller recommendation) — this lock only prevents
# concurrent turns from corrupting each other; a *retried* request for the
# same turn will still serialize and apply a second time. That is a
# smaller, separate piece of work flagged as out of scope for this pass.
_SESSION_LOCKS: dict[str, asyncio.Lock] = {}


def _get_session_lock(session_id: str) -> asyncio.Lock:
    lock = _SESSION_LOCKS.get(session_id)
    if lock is None:
        lock = asyncio.Lock()
        _SESSION_LOCKS[session_id] = lock
    return lock


# ---------------------------------------------------------------------------
# MAIN CHAT ENDPOINT
# ---------------------------------------------------------------------------
@router.post("/chat")
async def chat_handler(request: Request, data: dict, _auth_user: dict | None = Depends(get_optional_user)):
    """Thin, lock-acquiring wrapper around _chat_handler_impl (A12).

    Serializes turn processing per session_id so two overlapping requests
    for the same session (parallel tabs, a racing retry) run one at a time
    instead of interleaving reads/writes of the shared cached session state.
    """
    session_id = data.get("session_id") or "default"
    async with _get_session_lock(session_id):
        return await _chat_handler_impl(request, data, _auth_user)


async def _chat_handler_impl(request: Request, data: dict, _auth_user: dict | None):
    req_id = str(uuid.uuid4())[:8]
    session_id = data.get("session_id") or "default"
    # Priority: JWT user > guest device ID > anonymous
    if _auth_user:
        user_id = _auth_user["sub"]
    else:
        guest_id = _extract_guest_id(request)
        user_id = f"guest:{guest_id}" if guest_id else "anon"

    # Scrub a leading '>' used by the terminal UI for quoting.
    raw_msg = str(data.get("message", "") or "")
    stripped = raw_msg.lstrip()
    if stripped.startswith(">"):
        raw_msg = stripped[1:].lstrip()
    msg = str(raw_msg).strip()

    # Assign a stable UUID hex to this user message (12 chars, e.g. "a8f3c2d1b9e4").
    # Stored in JSONL with the turn; used as chunk ID prefix for extracted facts.
    user_msg_id: str = uuid.uuid4().hex[:12]

    # BL-02: turn retry idempotency. A client resending the same logical turn
    # (network timeout, double-click before the UI disables send) reuses the
    # same request_id; if that request_id matches the last one this session
    # actually completed, replay the exact stored reply instead of
    # reprocessing — reprocessing would double-advance time and double-apply
    # relationship/affection deltas. This check must run before ANY state
    # mutation. Anon sessions never persist (see the `user_id != "anon"`
    # guard at the save point below), so they have no durable identity to
    # dedup against and are skipped here.
    client_request_id = str(data.get("request_id") or "").strip()
    if client_request_id and user_id != "anon":
        try:
            prior_request_id, prior_reply_json = await SessionRepo.get_last_request(session_id, user_id)
        except Exception:
            prior_request_id, prior_reply_json = None, None
        if prior_request_id == client_request_id and prior_reply_json:
            try:
                return json.loads(prior_reply_json)
            except Exception:
                pass  # stored reply corrupt/unparseable - fall through and reprocess

    sess = get_session(session_id, user_id)
    state: GameState = sess["state"]

    # Initialise the per-session dialogue fact store on first turn (state may be
    # None for brand-new sessions before newgame initialises it).
    if state is not None and state.session_chunk_store is None:
        state.session_chunk_store = SessionChunkStore()
    log = sess["log"]

    # Sync epistemic master flag to this session's toggle.
    set_master(bool(sess.get("epistemic_state", True)))

    # DEBUG TOGGLE must be checked FIRST before any LLM calls
    if _is_debug_toggle(msg):
        currently_on = bool(sess.get("debug_mode", False))
        sess["debug_mode"] = not currently_on

        if sess["debug_mode"]:
            notice = _box(
                "ENTERING DEBUG MODE",
                [
                    "Type [D] to exit",
                    "(Debug info will be appended after each reply)",
                ],
            )
        else:
            notice = _box(
                "EXITING DEBUG MODE",
                [
                    "Type [D] to re-enter",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # CHINESE TOGGLE must be checked FIRST before any LLM calls
    if _is_chinese_toggle(msg):
        currently_on = bool(sess.get("chinese_mode", False))
        sess["chinese_mode"] = not currently_on

        if sess["chinese_mode"]:
            notice = _box(
                "进入中文模式",
                [
                    "Type [C] to exit",
                    "(所有回复将被翻译为中文)",
                ],
            )
        else:
            notice = _box(
                "退出中文模式",
                [
                    "Type [C] to return to English",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # MAP TOGGLE - Show available locations
    if _is_map_toggle(msg):
        state: GameState = sess.get("state")
        if not state or not state.world_runtime:
            notice = _box(
                "World Map",
                [
                    "No map available in this story.",
                ],
            )
            map_image = None
        else:
            locations = list(state.world_runtime.world_graph.locations.values())
            location_lines = []
            for loc in locations:
                location_lines.append(f"{loc.name}")
            notice = _box("World Map", location_lines)
            
            # Get world map image path if available
            map_image = None
            if state.story_cfg:
                world_cfg = state.story_cfg.get("world", {}) or {}
                map_image = str(world_cfg.get("world_map_image", "")).strip() or None

        result = {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}
        if map_image:
            result["world_map_image"] = map_image
            try:
                from PIL import Image as _PILImage
                import os as _os
                _stories_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "stories")
                with _PILImage.open(_os.path.join(_stories_dir, map_image)) as _im:
                    result["world_map_image_size"] = {"w": _im.width, "h": _im.height}
            except Exception:
                pass
        return result

    # Read-only, zero-token roster view. Upcoming names are deliberately not
    # returned, so authored future arrivals cannot leak through the UI.
    if _is_cast_roster_request(msg):
        roster = _cast_roster_payload(state)
        return {
            "reply": "",
            "cast_roster": roster,
            "usage": {"total_tokens": 0},
            "character": "default",
        }

    # TRUTH TOGGLE - Force character to answer honestly (debug tool)
    if _is_truth_toggle(msg):
        currently_on = bool(sess.get("truth_mode", False))
        sess["truth_mode"] = not currently_on

        if sess["truth_mode"]:
            notice = _box(
                "ENTERING TRUTH MODE",
                [
                    "Type [T] to exit",
                    "(Character will answer ALL questions honestly — no lies, no omissions)",
                ],
            )
        else:
            notice = _box(
                "EXITING TRUTH MODE",
                [
                    "Type [T] to re-enter",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # EPISTEMIC STATE TOGGLE - Enable/disable epistemic layers for this session
    if _is_epistemic_toggle(msg):
        new_state = not bool(sess.get("epistemic_state", True))
        sess["epistemic_state"] = new_state
        set_master(new_state)

        if new_state:
            notice = _box(
                "EPISTEMIC STATE ON",
                [
                    "Type [ES] to turn off",
                    "Epistemic truth/belief layers are active.",
                ],
            )
        else:
            notice = _box(
                "EPISTEMIC STATE OFF",
                [
                    "Type [ES] to turn on",
                    "Epistemic truth/belief layers are paused.",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    t0 = time.time()

    # RESET
    if msg == "__cmd_reset__":
        # Reset session state/log, but keep debug mode off.
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
            "user_id": user_id,
        }
        try:
            SESSIONS[session_id]["state"].clear_all_transient_entries()
        except Exception:
            pass
        return {"reply": "[memory cleared]", "usage": {"total_tokens": 0}, "character": "default"}

    # NEW GAME
    if msg.startswith("__cmd_newgame__:"):
        payload = msg[len("__cmd_newgame__:"):]
        parts = payload.split("|", 2)

        story_id = parts[0]
        gender = parts[1].strip().upper() if len(parts) > 1 else "M"
        player_name = parts[2].strip() if len(parts) > 2 else ""

        player_name = re.sub(r"[^A-Za-z\s\-']","", player_name)[:40] or "Player"

        story_def = load_story(story_id)
        if not story_def:
            return {"error": f"story not found: {story_id}"}

        new_state: GameState = init_state()
        new_state.story = story_id
        new_state.gender = "F" if gender == "F" else "M"
        new_state.player_name = player_name
        new_state.story_cfg = _canonicalize_story_cfg(story_def)
        new_state.user_id = user_id if user_id != "anon" else DEFAULT_USER_ID
        try:
            new_state.instance = int(getattr(story_def, "instance", DEFAULT_INSTANCE))
        except Exception:
            new_state.instance = DEFAULT_INSTANCE
        # Canonical truths (for truth-mode override guidance)
        new_state.canonical_truth = story_def.get("canonical_truth", [])

        # Seed epistemic base truths and per-character knowledge
        _seed_epistemic_from_story(new_state.story_cfg, new_state)
        new_state.clear_all_transient_entries()
        _seed_noncanonical_story_details_to_transient(story_def, new_state)

        # Optional world graph runtime (does not change gameplay unless movement occurs)
        world_cfg = story_def.get("world", {}) or {}
        seed = int(world_cfg.get("seed", 0))
        world_file = str(world_cfg.get("file", "")).strip()
        if world_file:
            loaded = WorldLoader.load_from_file(
                f"backend/app/stories/{world_file}",
                seed=seed,
                user_id=new_state.user_id,
                story_id=story_id,
                instance=new_state.instance,
            )
        else:
            loaded = WorldLoader.try_load_story_world(
                story_id,
                stories_dir="backend/app/stories",
                seed=seed,
                user_id=new_state.user_id,
                instance=new_state.instance,
            )
        if loaded is not None:
            new_state.world_runtime = loaded
            start_id = str(world_cfg.get("start_location_id", "")).strip()

            # If no explicit start id, choose the first loaded node (JSON order is stable).
            if not start_id:
                try:
                    start_id = next(iter(loaded.world_graph.locations.keys()), "")
                except Exception:
                    start_id = ""

            if start_id and start_id in loaded.world_graph.locations:
                new_state.location_id = start_id
                # Keep a human-readable location string in sync for UI/heuristics.
                try:
                    start_loc = loaded.world_graph.locations[start_id]
                    new_state.location = start_loc.name
                    new_state.location_uuid = getattr(start_loc, "uuid", "")
                except Exception:
                    pass
            else:
                new_state.location_id = ""
                new_state.location_uuid = ""

            # Timestamp start
            new_state.world_start_datetime = str(world_cfg.get("start_datetime", "")).strip()

        new_state.user.gender = new_state.gender
        # Persona selection: support 'temp' (session-only) or 'default'. Frontend may supply persona_mode/persona_name/persona_other in the POST data.
        try:
            persona_mode = str(data.get("persona_mode") or data.get("personaMode") or "").strip()
            persona_name = str(data.get("persona_name") or data.get("personaName") or "").strip()
            persona_other = str(data.get("persona_other") or data.get("personaOther") or "").strip()
            if not persona_mode:
                # Backwards compatible default: 'temp' (temporary per-session persona created from player name)
                persona_mode = "temp"
            new_state.user.persona_mode = persona_mode
            new_state.user.persona_name = persona_name
            new_state.user.persona_other = persona_other
            # Derive display name for the in-story player node: prefer default-persona name, else typed player_name
            try:
                if getattr(new_state.user, "persona_mode", "") == "default" and new_state.user.persona_name:
                    persona_display = new_state.user.persona_name
                else:
                    persona_display = new_state.player_name or "Player"
                new_state.user.display_name = persona_display
                # Create the player Character node for prompt_builder usage
                try:
                    from backend.app.engine.state import make_player_character
                    new_state.characters["player"] = make_player_character(display_name=persona_display)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            # tolerate missing/invalid fields
            new_state.user.persona_mode = "temp"
            new_state.user.persona_name = ""
            new_state.user.persona_other = ""
        # Keep a human-readable location. If the world graph is active we prefer
        # the graph's display name; otherwise fall back to the story's setting string.
        if not getattr(new_state, "location_id", ""):
            new_state.location = new_state.location or "start"
        new_state.emotion = story_def.get("emotion", {}).get("start", new_state.emotion)

        # Main/character roster comes from StoryDefinition (fallbacks handle legacy stories)
        fallback_name = "the character"

        main_char_def = story_def.main_character if isinstance(story_def, StoryDefinition) else None
        characters = list(story_def.characters) if isinstance(story_def, StoryDefinition) else []

        # Legacy fallback: main_character/suspects fields
        if not characters:
            legacy_main = (story_def.get("main_character", {}) or {}) if hasattr(story_def, "get") else {}
            if legacy_main:
                main_char_def = Character.from_dict({**legacy_main, "is_main": True})
                characters.append(main_char_def)
            for sus in (story_def.get("suspects", []) or []) if hasattr(story_def, "get") else []:
                characters.append(Character.from_dict({**sus, "is_suspect": True}))

        if not characters:
            main_char_def = Character.from_dict({"key": "MAIN", "name": fallback_name, "role": "npc", "is_main": True})
            characters.append(main_char_def)

        # Finalize main pointer
        if not main_char_def and characters:
            main_char_def = next((c for c in characters if c.is_main), characters[0])

        # story-level self_knowledge belongs to the main character
        story_self_knowledge = list(
            (story_def.get("character_self_knowledge") or []) if hasattr(story_def, "get") else []
        )

        for ch in characters:
            ch_uuid = ch.uuid or build_deterministic_uuid(
                user_id=new_state.user_id,
                story_id=story_id,
                instance=new_state.instance,
                entity_id=ch.key,
            )
            game_char = Character(
                key=ch.key,
                name=ch.name,
                role=ch.role or "npc",
                is_main=ch.is_main,
                is_suspect=ch.is_suspect,
                knowledge_character_id=ch.knowledge_character_id,
                uuid=ch_uuid,
                tags=list(ch.tags),
                meta=dict(ch.meta),
                self_knowledge=(
                    list(ch.self_knowledge)
                    if ch.self_knowledge
                    else (story_self_knowledge if ch.is_main else [])
                ),
                emotion=new_state.emotion,
                relationship=new_state.relationship,
            )
            new_state.characters[ch.key] = game_char
            if ch.is_main:
                new_state.main_character_id = ch.key
            if ch.is_main and ch.knowledge_character_id and not new_state.knowledge_character_id:
                new_state.knowledge_character_id = ch.knowledge_character_id

        if not new_state.main_character_id and main_char_def:
            new_state.main_character_id = main_char_def.key

        _initialize_cast_lifecycle(new_state)

        # Seed character start locations from world config
        # character_start_locations: {character_key: location_id} — explicit positions at game start
        char_start_locs = world_cfg.get("character_start_locations") or {}
        if isinstance(char_start_locs, dict):
            new_state.character_locations = {
                str(k).strip(): str(v).strip()
                for k, v in char_start_locs.items()
                if k and v
            }

        # Load character relationship graph from story definition
        if isinstance(story_def, StoryDefinition) and story_def.relationships:
            new_state.character_graph = story_def.relationships

        # Fallback knowledge bundle for main
        if not new_state.knowledge_character_id and main_char_def:
            new_state.knowledge_character_id = main_char_def.knowledge_character_id

        # Label all knowledge chunks with player visibility for debug player agent retrieval.
        _seed_player_visibility(new_state)

        opening = story_def.get("opening", {}).get("text", "The room is quiet. A story begins.")
        opening = apply_placeholders(opening, new_state)

        sess["state"] = new_state
        new_state.session_chunk_store = SessionChunkStore()
        sess["log"] = [
            {"role": "system", "content": build_messages(new_state, [], "", [])[0]["content"]},
            {"role": "assistant", "content": opening}
        ]

        # Persist new session to DB (authenticated users only)
        if user_id != "anon":
            try:
                story_title = story_def.get("title", story_id) if hasattr(story_def, "get") else story_id
                await SessionRepo.create_or_update_session(
                    session_id=session_id,
                    user_id=user_id,
                    story_id=story_id,
                    story_title=story_title,
                    player_name=player_name,
                    gender=new_state.gender,
                    state_json=_serialize_state(new_state, []),
                    flags_json=json.dumps({
                        "debug_mode": False,
                        "chinese_mode": False,
                        "epistemic_state": True,
                        "truth_mode": False,
                    }),
                    last_message=opening[:120],
                    turns=0,
                )
            except Exception:
                logger.exception("Failed to persist new session %s for user %s", session_id, user_id)

        # Apply Chinese translation if chinese_mode is enabled
        reply = opening
        if bool(sess.get("chinese_mode", False)):
            reply = await _translate_to_chinese(reply)

        return {"reply": reply, "usage": {"total_tokens": 0}, "character": "default"}

    # REGULAR TURN — auto-reinitialize if game state is missing
    if not state.story or not state.story_cfg:
        # Try to recover: look up the DB row for story_id and rebuild
        db_row = None
        try:
            db_row = SessionRepo._get(session_id=session_id, user_id=user_id)
        except Exception:
            pass
        if db_row and db_row.get("story_id"):
            logger.info("Auto-reinit session %s from DB (story=%s)", session_id, db_row["story_id"])
            restored = _try_load_session_from_db(session_id, user_id)
            if restored:
                SESSIONS[session_id] = restored
                sess = restored
                state = sess["state"]
                log = sess["log"]
        if not state.story or not state.story_cfg:
            return {"reply": "Session expired. Please start a new game from the home screen.", "character": "default"}

    if state.over:
        return {"reply": "This story has ended. Start a new game from the home screen to play again.", "character": "default"}

    # Keep transient scene memory bounded.
    state.purge_transient_entries()

    # --- ACTIVE CHARACTER DETECTION (pre-prompt) ---
    # Detect which characters are mentioned in recent conversation or present
    # at the current location.  Markers stored in the transient buffer let the
    # prompt builder filter graph edges and character extras to only what is
    # contextually relevant.
    from backend.app.engine.active_characters import compute_active_character_set, get_people_present_keys

    _previous_scene = state.latest_scene_knowledge()
    _previous_location_id = str(getattr(_previous_scene, "location_id", "") or "") if _previous_scene else ""
    _current_location_id = str(getattr(state, "location_id", "") or "")
    _location_changed = bool(_previous_location_id and _current_location_id and _previous_location_id != _current_location_id)
    _carryover_speakers = set()
    if _previous_scene and not _location_changed:
        _carryover_speakers = {str(s or "").strip().lower() for s in (getattr(_previous_scene, "speakers", []) or []) if str(s or "").strip()}

    _people_present = get_people_present_keys(state)
    _pre_active_chars = compute_active_character_set(
        state=state,
        user_msg=msg,
        recent_log=log[-4:],
        carryover_speakers=_carryover_speakers,
    )
    _upsert_active_character_markers(state, _pre_active_chars)
    _upsert_people_present_markers(state, _people_present)

    # First-meeting detection: initialize prejudice on edges for pairs meeting for the
    # first time. Tracks last_met_at and meeting_count on each new encounter.
    # is_new_encounter=True when the player just entered a new location (location_changed).
    # Called every turn so NPC walk-ins are also captured.
    _graph = getattr(state, "character_graph", None)
    if _graph is not None:
        _room_ids = set(_pre_active_chars) | {"player"}
        _room_ids.discard("")
        _graph.process_first_meetings(
            room_ids=_room_ids,
            state=state,
            current_minute=int(getattr(state, "minute", 0) or 0),
            is_new_encounter=_location_changed,
        )

    # NOTE: advance_time is called AFTER location extraction (below) so that
    # the canonicalized movement message (e.g. "go to interview_room_bob") is
    # used instead of the raw user text which may not match the strict regex.
    handle_name_confirmation(msg, state)

    extracted = extract_user_name_from_text(msg)
    if extracted:
        state.user.formal_name = extracted
        if not state.user.display_name:
            state.user.display_name = extracted

    # --- KNOWLEDGE RETRIEVAL (must happen BEFORE location extraction) ---
    # This retrieval provides context that helps LocationExtractor disambiguate ambiguous location
    # references. For example, "I'm going to her old studio" needs FAISS knowledge context to
    # resolve "old studio" to the specific location ID (e.g., "downtown_recording_studio").
    try:
        # Route retrieval to the correct character bundle for this story.
        if getattr(state, "knowledge_character_id", ""):
            IndexService.set_active_character(state.knowledge_character_id)
        namespace = build_namespace_key(user_id=getattr(state, "user_id", ""), story_id=getattr(state, "story", ""), instance=getattr(state, "instance", 1))
        retrieved, debug = retrieve_knowledge(
            msg, namespace=namespace,
            session_store=state.session_chunk_store,
        )
    except Exception as e:
        _log({"kind": "retrieval_error", "error": str(e)})
        return {"error": "knowledge retrieval failed", "character": "default"}

    # --- SINGLE-CALL TURN EXTRACTION ---
    # One extractor call handles movement intent, previous-turn scene extraction,
    # and previous-turn knowledge-resolution updates in a single JSON response.
    runtime = getattr(state, "world_runtime", None)
    knowledge_resolution_updates: list[dict] = []
    extraction = None
    extraction_applied = False
    # Travel parsing needs a strict command; narration and memory need the full message.
    movement_msg = msg
    if runtime is not None and getattr(state, "location_id", ""):
        previous_candidate_chunks = _unknown_knowledge_chunks_for_speaker(
            state,
            getattr(state, "last_turn_retrieved_chunks", []) or [],
        )

        world_locations = {
            str(loc_id): str(getattr(loc, "name", "") or str(loc_id))
            for loc_id, loc in (getattr(runtime.world_graph, "locations", {}) or {}).items()
        }
        character_key_to_name = {
            str(key).strip().lower(): str(getattr(ch, "name", "") or key)
            for key, ch in (getattr(state, "characters", {}) or {}).items()
            if str(key).strip() and _cast_scene_eligible(state, str(key).strip().lower())
        }

        try:
            _log({
                "kind": "turn_extraction_attempting",
                "user_msg": msg,
                "current_location_id": state.location_id,
                "current_location_name": state.location,
            })
            extraction = await _TURN_EXTRACTOR.extract(
                user_msg=msg,
                world_locations=world_locations,
                character_key_to_name=character_key_to_name,
                previous_turn_user_msg=str(getattr(state, "last_turn_user_msg", "") or ""),
                previous_turn_assistant_reply=str(getattr(state, "last_turn_assistant_reply", "") or ""),
                previous_turn_candidate_chunks=previous_candidate_chunks,
                conversation_log=log,
            )
            
            _log({
                "kind": "turn_extraction_complete",
                "user_msg": msg,
                "extraction_intent": extraction.movement_intent,
                "extraction_destination_id": extraction.destination_id,
                "extraction_confidence": extraction.confidence,
                "previous_reply_location_id": extraction.previous_reply_location_id,
                "previous_reply_speakers_count": len(extraction.previous_reply_speakers),
                "knowledge_updates_count": len(extraction.knowledge_updates),
            })

            prev_scene_location_id = extraction.previous_reply_location_id or _current_location_id
            prev_scene_speakers = {
                str(s or "").strip().lower()
                for s in (extraction.previous_reply_speakers or [])
                if str(s or "").strip()
            }
            if prev_scene_speakers:
                _upsert_scene_speaker_markers(state, prev_scene_speakers)

            state.upsert_scene_knowledge(
                key=f"turn:{int(getattr(state, 'turns', 0) or 0)}",
                location_id=prev_scene_location_id,
                speakers=sorted(prev_scene_speakers),
                people_present=sorted(_people_present),
                payload={
                    "location_changed_from_previous": _location_changed,
                    "source": "single_call_turn_extractor",
                },
            )

            knowledge_resolution_updates = apply_knowledge_resolution_updates(
                state=state,
                updates=extraction.knowledge_updates,
                candidate_chunks=previous_candidate_chunks,
            )

            # Apply LLM-extracted relationship history updates (prior_relationship, etc.)
            _rel_graph = getattr(state, "character_graph", None)
            if _rel_graph is not None:
                for _hist_update in (extraction.relationship_history_updates or []):
                    _rel_graph.update_edge_history(
                        _hist_update.from_id,
                        _hist_update.to_id,
                        prior_relationship=_hist_update.prior_relationship,
                        prior_intimacy=_hist_update.prior_intimacy,
                        in_relationship=_hist_update.in_relationship,
                    )
                # Apply player attitude deltas (player→npc edges — small increments from user msg)
                for _su in (extraction.relationship_state_updates or []):
                    _rel_graph.update_edge(
                        _su.from_id,
                        _su.to_id,
                        trust_delta=_su.trust_delta,
                        fear_delta=_su.fear_delta,
                        affection_delta=_su.affection_delta,
                        suspicion_delta=_su.suspicion_delta,
                        jealousy_delta=_su.jealousy_delta,
                    )

            if extraction.movement_intent == "MOVE" and extraction.destination_id:
                if extraction.destination_id in runtime.world_graph.locations:
                    movement_msg = f"go to {extraction.destination_id}"
                    extraction_applied = True
                    _log({
                        "kind": "turn_extraction_movement_applied",
                        "original_msg": msg,
                        "canonicalized_msg": movement_msg,
                        "destination_id": extraction.destination_id,
                    })
                else:
                    _log({
                        "kind": "turn_extraction_invalid_destination",
                        "user_msg": msg,
                        "destination_id": extraction.destination_id,
                    })

            # Phase 2 cast-cycling: a resident's own stated DECISION to leave
            # schedules a deferred replacement (never immediate - "a decision
            # to leave next week is not immediate removal"). The hard guard
            # against "a player cannot evict somebody merely by asserting
            # they left" is here, not just in the extractor's prompt rules:
            # only DECISION-certainty signals naming a character CURRENTLY
            # in lifecycle.active_ids() are ever acted on.
            _lifecycle = getattr(state, "cast_lifecycle", None)
            _signal = extraction.departure_signal
            if _lifecycle is not None and _lifecycle.enabled and _signal is not None:
                _already_pending = any(
                    ev.event_type == "cast_departure_replacement"
                    and ev.status == "pending"
                    and ev.payload.get("departing_id") == _signal.character_id
                    for ev in (getattr(state, "pending_events", []) or [])
                )
                if (
                    _signal.certainty == "DECISION"
                    and _signal.character_id in _lifecycle.active_ids()
                    and not _already_pending
                ):
                    _propose_event_id = f"departure_propose_{_signal.character_id}_{state.turns}"
                    try:
                        _lifecycle.propose_departure(
                            _signal.character_id,
                            minute=int(getattr(state, "minute", 0) or 0),
                            reason=_signal.reason or "stated intention to leave",
                            event_id=_propose_event_id,
                        )
                        _due_day = day_number(int(getattr(state, "minute", 0) or 0)) + (
                            1 if _lifecycle.replacement_timing == "next_day" else 0
                        )
                        state.pending_events.append(PendingEvent(
                            event_id=f"departure_replace_{_signal.character_id}_{state.turns}",
                            event_type="cast_departure_replacement",
                            scheduled_day=_due_day,
                            payload={"departing_id": _signal.character_id, "reason": _signal.reason},
                            created_minute=int(getattr(state, "minute", 0) or 0),
                        ))
                        _log({
                            "kind": "cast_departure_proposed",
                            "character_id": _signal.character_id,
                            "scheduled_day": _due_day,
                        })
                    except ValueError as _dep_exc:
                        _log({
                            "kind": "cast_departure_proposal_rejected",
                            "character_id": _signal.character_id,
                            "error": str(_dep_exc),
                        })
        except Exception as e:
            _log({
                "kind": "turn_extraction_error",
                "error": str(e),
                "user_msg": msg,
            })

        # Heuristic fallback when the classifier misses obvious movement phrasing
        if not extraction_applied:
            dest = _match_world_destination(msg, runtime, getattr(state, "location_id", ""))
            if dest:
                movement_msg = f"go to {dest}"
                extraction_applied = True
                _log({
                    "kind": "turn_extraction_heuristic_applied",
                    "original_msg": msg,
                    "canonicalized_msg": movement_msg,
                    "destination_id": dest,
                })
    else:
        if runtime is None:
            _log({"kind": "turn_extraction_skipped", "reason": "no_world_runtime"})
        elif not getattr(state, "location_id", ""):
            _log({"kind": "turn_extraction_skipped", "reason": "no_location_id"})

    # Only travel/time consumes the command; preserve player dialogue everywhere else.
    advance_time(state, movement_msg)

    if str(getattr(state, "location_id", "") or "") != _current_location_id:
        # Travel clears location markers. Rebuild them and the FIFO fallback from
        # the destination, including empty rooms, before assembling this turn's prompt.
        _location_changed = True
        _carryover_speakers = set()
        _people_present = get_people_present_keys(state)
        _pre_active_chars = compute_active_character_set(
            state=state, user_msg=msg, recent_log=[], carryover_speakers=set(),
        )
        _upsert_active_character_markers(state, _pre_active_chars)
        _upsert_people_present_markers(state, _people_present)
        _upsert_scene_speaker_markers(state, set())
        state.upsert_scene_knowledge(
            key=f"turn:{int(getattr(state, 'turns', 0) or 0)}",
            location_id=state.location_id,
            speakers=[],
            people_present=sorted(_people_present),
            payload={"location_changed_from_previous": True, "source": "movement_destination"},
        )

    # Record short-lived conversational scene context for current turn.
    try:
        state.add_transient_entry(
            id=str(uuid.uuid4()),
            namespace=_namespace_for_state(state),
            scope="conversation",
            text=f"Player said: {msg}",
            expires_after_turns=TRANSIENT_KNOWLEDGE_TURNS,
        )
    except Exception:
        pass

    from backend.app.engine.prompt_builder import PromptInput

    prompt_input = PromptInput(
        state=state,
        log=log,
        user_msg=msg,
        knowledge_chunks=retrieved,
        truth_mode=bool(sess.get("truth_mode", False)),
        retrieval_debug=debug,
        canonicalized_user_msg=msg,
    )

    messages, prompt_debug = build_messages(prompt_input, return_debug=True)
    state.turns += 1

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    _log({
        "kind": "chat_request",
        "req_id": req_id,
        "session_id": session_id,
        "turn": state.turns,
        "user_msg": msg,
        "retrieval_debug": debug,
        "prompt_debug": prompt_debug,
        "retrieved_chunk_ids": [c.get("chunk_id") for c in retrieved],
    })

    # Story master call — uses configurable base URL/model so the same code
    # works against OpenAI (online) or a local Ollama instance (local dev).
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{STORY_MASTER_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {STORY_MASTER_API_KEY}"},
            json={**payload, "model": STORY_MASTER_MODEL},
        )

    if r.status_code < 200 or r.status_code >= 300:
        _log({
            "kind": "chat_upstream_error",
            "req_id": req_id,
            "status": r.status_code,
            "body": _truncate(r.text, 4000),
        })
        return {"error": f"upstream HTTP {r.status_code}: {r.text}", "character": "default"}

    data = r.json()
    reply = str(data["choices"][0]["message"]["content"])

    guess_match = re.search(
        r"\bis your name\s+([A-Za-z][A-Za-z\s'\-]{0,40})\??",
        reply,
        re.IGNORECASE
    )
    if guess_match:
        state.last_assistant_guess_name = clean_name(guess_match.group(1))

    clean, tag = extract_state_tag(reply)
    clean = sanitize_honorific_terms(clean, state)

    # UUID for the AI message — generated here so it's available for JSONL persistence below.
    ai_msg_id: str = uuid.uuid4().hex[:12]

    if not isinstance(tag, dict):
        tag = {"emotion": state.emotion, "rel_delta": 0}

    apply_state_tag(state, tag)

    log.append({"role": "user", "content": msg})
    log.append({"role": "assistant", "content": clean})
    sess["log"] = log[-MEMORY_TURNS:]

    try:
        state.add_transient_entry(
            id=str(uuid.uuid4()),
            namespace=_namespace_for_state(state),
            scope="conversation",
            text=f"NPC replied: {clean}",
            expires_after_turns=TRANSIENT_KNOWLEDGE_TURNS,
        )
    except Exception:
        pass

    # --- POST-REPLY ACTIVE CHARACTER DETECTION ---
    # Scan the NPC reply for character mentions so active set stays aligned with
    # current context (mentioned + scene-present), not stale prior turns.
    try:
        _post_active_chars = compute_active_character_set(
            state=state,
            user_msg="",
            recent_log=[],
            npc_reply=clean,
            carryover_speakers=_carryover_speakers,
        )
        _upsert_active_character_markers(state, _post_active_chars)

        _scene_speakers = set(_post_active_chars)
        main_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
        if main_id:
            _scene_speakers.add(main_id)
        _upsert_scene_speaker_markers(state, _scene_speakers)

        _narrative_location_id = _extract_location_from_reply(state, clean)
        state.upsert_scene_knowledge(
            key=f"turn:{int(getattr(state, 'turns', 0) or 0)}",
            location_id=_narrative_location_id,
            speakers=sorted(_scene_speakers),
            people_present=sorted(_people_present),
            payload={
                "location_changed_from_previous": _location_changed,
                "source": "scene_presence_extractor",
            },
        )
    except Exception:
        pass

    if win_condition_detected(clean, state):
        state.over = True
        clean += f"\n\nEND GAME YOU WIN -- turns: {state.turns}"

    # Persist this completed turn for next turn's single-call extractor analysis.
    # These must be set BEFORE the session save below so the persisted row
    # reflects the turn just completed, not the prior one (see BL-01).
    state.last_turn_user_msg = msg
    state.last_turn_assistant_reply = clean
    state.last_turn_retrieved_chunks = [dict(c) for c in (retrieved or [])]

    # Persist state + raw log after every turn (authenticated users only).
    # All in-memory mutations for this turn (including `over` and
    # `last_turn_*` above) must happen before this single save point so the
    # persisted snapshot is atomic with respect to the turn just completed.
    if user_id != "anon":
        try:
            story_title = ""
            if hasattr(state, "story_cfg") and state.story_cfg:
                cfg = state.story_cfg
                story_title = cfg.get("title", state.story) if hasattr(cfg, "get") else state.story
            await SessionRepo.create_or_update_session(
                session_id=session_id,
                user_id=user_id,
                story_id=state.story or "",
                story_title=story_title,
                player_name=state.player_name or "",
                gender=state.gender or "M",
                state_json=_serialize_state(state, sess["log"]),
                flags_json=json.dumps({
                    "debug_mode": bool(sess.get("debug_mode", False)),
                    "chinese_mode": bool(sess.get("chinese_mode", False)),
                    "epistemic_state": bool(sess.get("epistemic_state", True)),
                    "truth_mode": bool(sess.get("truth_mode", False)),
                }),
                last_message=clean[:120],
                turns=state.turns,
            )
            await ConversationRepo.append_turns(
                user_id=user_id,
                session_id=session_id,
                user_msg=msg,
                assistant_reply=clean,
                turn=state.turns,
                user_msg_id=user_msg_id,
                ai_msg_id=ai_msg_id,
            )
        except Exception:
            logger.exception("Failed to persist turn for session %s user %s", session_id, user_id)

    # Fire background fact extraction (non-blocking).
    # Extracted facts are stored in state.session_chunk_store with IDs:
    #   usr-{user_msg_id}-{n}  (from user message)
    #   ai-{ai_msg_id}-{n}     (from AI reply)
    # BL-01b: for non-anon sessions, durably enqueue this extraction attempt
    # BEFORE firing the in-process task, so a crash between enqueue and
    # completion leaves a 'pending' row a startup recovery sweep
    # (backend/app/main.py) can find and reprocess, instead of the facts
    # being silently lost with no record they were ever attempted. Anon
    # sessions have no durable identity (they never persist to SQLite at
    # all - see the `user_id != "anon"` guard above), so they keep the
    # legacy best-effort fire-and-forget path unchanged.
    character_id = str(getattr(state, "knowledge_character_id", "") or state.story or "unknown")
    if state.session_chunk_store is not None:
        import asyncio as _asyncio

        async def _extract_and_store(
            _user_msg: str, _user_id: str, _ai_reply: str, _ai_id: str,
            _char_id: str, _store: "SessionChunkStore", _outbox_row_id: int | None,
        ) -> None:
            try:
                usr_chunks = await extract_facts_from_message(_user_msg, "user", _user_id, _char_id)
                ai_chunks = await extract_facts_from_message(_ai_reply, "assistant", _ai_id, _char_id)
                _store.add_chunks(usr_chunks + ai_chunks)
                if _outbox_row_id is not None:
                    await FactExtractionOutboxRepo.mark_done(_outbox_row_id)
            except Exception as exc:
                if _outbox_row_id is not None:
                    try:
                        await FactExtractionOutboxRepo.mark_failed(_outbox_row_id, str(exc))
                    except Exception:
                        pass

        if user_id != "anon":
            try:
                outbox_row_id = await FactExtractionOutboxRepo.enqueue(
                    session_id, user_id, msg, user_msg_id, clean, ai_msg_id, character_id,
                )
                _asyncio.ensure_future(_extract_and_store(
                    msg, user_msg_id, clean, ai_msg_id,
                    character_id, state.session_chunk_store, outbox_row_id,
                ))
            except Exception:
                logger.exception("Failed to enqueue fact-extraction outbox row for session %s", session_id)
        else:
            try:
                _asyncio.ensure_future(_extract_and_store(
                    msg, user_msg_id, clean, ai_msg_id,
                    character_id, state.session_chunk_store, None,
                ))
            except Exception:
                pass

    _log({
        "kind": "chat_response",
        "req_id": req_id,
        "session_id": session_id,
        "latency_ms": int((time.time() - t0) * 1000),
        "usage": data.get("usage", {}),
        "assistant_reply_preview": _truncate(clean, 1200),
    })

    # Timestamp is only shown in DEBUG INFO now (no longer prepended to the reply).
    ts = WorldTimeFormatter.compute(getattr(state, "world_start_datetime", ""), getattr(state, "minute", 0)).display

    # Start with clean reply (no timestamp prefix).
    reply = clean

    # Build debug_box as structured data for frontend rendering (never added to LLM context).
    debug_box = None
    if bool(sess.get("debug_mode", False)):
        user_loc = (getattr(state, "location", "") or "").strip() or "(unknown)"
        speakers = _debug_speakers(state)

        raw_entries = getattr(state, "transient_entries", []) or []
        debug_box = {
            "timestamp": ts,
            "location": user_loc,
            "location_uuid": getattr(state, "location_uuid", ""),
            "speakers": speakers if speakers else None,
            "people_present": _debug_people_present(state) or None,
            "transient_count": len(raw_entries),
            "transient_entries": [
                {"text": e.text, "turns_remaining": e.turns_remaining}
                for e in raw_entries
            ],
        }

    # Apply Chinese translation if chinese_mode is enabled
    if bool(sess.get("chinese_mode", False)):
        reply = await _translate_to_chinese(reply)

    result = {"reply": reply, "usage": data.get("usage"), "character": "default"}
    # prompt_debug carries the FULL assembled system prompt (all canonical
    # facts, character secrets, retrieval chunk text) and is only for the
    # operator-facing debug/playback tooling (backend/app/api/debug_engine.py,
    # which authenticates its own internal /api/chat calls with the same
    # operator token). It must never reach an ordinary player: unlike the
    # `debug_mode` toggle below, which is a harmless player-facing "[D]"
    # bracket command, is_operator_request() checks the real trust boundary
    # (DEBUG_TOOLS_ENABLED + a matching X-Operator-Token/operator_token),
    # so typing "[D]" alone cannot unlock it.
    if is_operator_request(request):
        result["prompt_debug"] = prompt_debug
    if knowledge_resolution_updates:
        result["knowledge_resolution_updates"] = knowledge_resolution_updates
    if debug_box is not None:
        if knowledge_resolution_updates:
            debug_box["knowledge_resolution_updates"] = knowledge_resolution_updates
        result["debug_box"] = debug_box

    # BL-02: record this turn's dedup token now that `result` (the exact
    # client-facing reply) is fully built, so a retry with the same
    # request_id can replay it verbatim instead of reprocessing. A separate
    # lightweight UPDATE rather than folding into the main session save
    # above, so the existing atomic-turn-save ordering (over/last_turn_*
    # must precede that save - see BL-01) is untouched.
    if client_request_id and user_id != "anon":
        try:
            await SessionRepo.update_last_request(session_id, user_id, client_request_id, json.dumps(result))
        except Exception:
            logger.exception("Failed to persist request-id dedup token for session %s", session_id)

    return result
