
# app/api/prompt_engine.py
# Prompt Engine: orchestrates all raw context (state, knowledge, history) and
# transforms it into a fully-assembled LLM prompt, then dispatches the API call.

from backend.app.engine.extractors.turn_extractor import (
    TurnExtractor,
    TurnKnowledgeResolution,
)

from fastapi import APIRouter, Depends, Request, HTTPException
from backend.app.auth.dependencies import get_optional_user, _extract_guest_id, is_operator_request
from backend.app.db.repos import SessionRepo, ConversationRepo, FactExtractionOutboxRepo, ExtractedChunksRepo

import asyncio
import copy
import dataclasses
import httpx
import json
import logging

import re

import secrets

import time

import uuid

from typing import Dict, Optional

logger = logging.getLogger(__name__)


from backend.app.knowledge.runtime.retrieve import retrieve_knowledge
from backend.app.knowledge.runtime.dynamic_context import (
    DynamicContextSelector,
    dynamic_context_enabled,
    retrieve_context_candidates,
)
from backend.app.knowledge.runtime.session_chunk_store import SessionChunkStore
from backend.app.knowledge.runtime.dialogue_extractor import (
    extract_facts_from_message, extract_facts_with_status, EXTRACTOR_VERSION,
)

from backend.app.knowledge.runtime.index_service import IndexService

from backend.app.utils.logging_utils import jlog as _log, truncate as _truncate


from backend.app.config.settings import (

    OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
    STORY_MASTER_BASE_URL, STORY_MASTER_API_KEY, STORY_MASTER_MODEL,

    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS,
    DEFAULT_USER_ID, DEFAULT_INSTANCE,
    TRANSIENT_KNOWLEDGE_TURNS,
    BEHAVIOR_LOG_RIPE_THRESHOLD, BEHAVIOR_LOG_WINDOW_SIZE, BEHAVIOR_LOG_RECENT_SPAN,

)
from backend.app.config.epistemic_flags import set_master


from backend.app.engine.world_model.model import WorldModel
from backend.app.llm.retry import post_with_retry
from backend.app.engine.world_model import turn as world_turn
from backend.app.engine.state import (

    init_state,

    apply_state_tag,

    extract_state_tag,

    GameState,

    Character,

    LanguageTheme,

)
from backend.app.engine.dialogue import (
    present_dialogue, encode_dialogue, dialogue_transcript, drop_player_echo, drop_repeated_lines, only_repeats,
    dialogue_response_format, decode_dialogue_response,
    has_unmarked_quotes, attribute_unmarked_quotes, ground_social_scene,
)
from backend.app.engine.character_graph import RelationshipEdge, RelationshipState, RelationshipType
from backend.app.engine.social_traits import EvolvingTrait
from backend.app.engine.cast_lifecycle import CastLifecycleState, CastStatus
from backend.app.engine.opening_scene import stage_opening_scene
from backend.app.engine.world_calendar import PendingEvent, day_number
from backend.app.engine.epistemic_state import EpistemicFact, EpistemicClaim, BeliefState
from backend.app.engine.knowledge_chunks import normalize_parties, KnowledgeChunk
from backend.app.engine.story_loader import load_story, StoryDefinition
from backend.app.engine.gameplay import (

    advance_time,

    advance_time_by,

    win_condition_detected,

    process_pending_events,

)
from backend.app.engine.time_utils import WorldTimeFormatter
from backend.app.engine.world.world_loader import WorldLoader
from backend.app.engine.prompt_builder import (

    build_messages,
    _cast_scene_eligible,

)
from backend.app.utils.id_utils import build_deterministic_uuid, build_namespace_key
from backend.app.utils.stage_timer import StageTimer


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


def _world_place_names(state: GameState) -> dict[str, str]:
    runtime = getattr(state, "world_runtime", None)
    locations = getattr(getattr(runtime, "world_graph", None), "locations", None) or {}
    names = {loc_id: getattr(loc, "name", loc_id) for loc_id, loc in locations.items()}
    # Off-map routine places ("school", a suspect's home) named by the story.
    cfg = getattr(state, "story_cfg", None) or {}
    extra = ((cfg.get("world_model") or {}).get("place_names") or {}) if isinstance(cfg, dict) else {}
    return {**{str(k): str(v) for k, v in extra.items()}, **names}


def _lore_chunks_for(state: GameState) -> list[dict]:
    """Authored knowledge-bundle chunks for the world model's per-character memory."""
    bundle_id = str(getattr(state, "knowledge_character_id", "") or "")
    if not bundle_id:
        return []
    try:
        return list(IndexService.get(bundle_id).chunks or [])
    except Exception:
        logger.exception("lore bundle %s unavailable for world model", bundle_id)
        return []


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
    "gender",
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
            "gender": str(ch.get("gender") or "").upper(),
            # Phase 3 "Social life": preserve author-time goal content for
            # any consumer of story_cfg["characters"] - previously silently
            # dropped here even though Character.from_dict (the primary
            # newgame character-construction path) already preserves them.
            "motive": ch.get("motive") or "",
            "tells": list(ch.get("tells") or []),
        })

    return {
        "id": src.get("id") or "",
        "title": src.get("title") or "",
        "theme": src.get("theme") or "",
        # This is an authored setting, not an inference from a handful of
        # vocabulary words.  It survives the deliberately narrow runtime
        # story config used by sessions and prompts.
        "language_theme": src.get("language_theme") or LanguageTheme.ENGLISH_US.value,
        "language": src.get("language") or {},
        "instance": src.get("instance", DEFAULT_INSTANCE),
        "opening": src.get("opening") or {},
        "world": src.get("world") or {},
        "time": src.get("time") or {},
        "emotion": src.get("emotion") or {},
        "goal": src.get("goal") or {},
        "win_detection": src.get("win_detection") or {},
        "epistemic_seed": src.get("epistemic_seed") or {},
        "canonical_truth": src.get("canonical_truth") or [],
        # BL-16 fix: a closed, story-authored vocabulary for behavior_tags
        # (see turn_extractor.py's BehaviorTagUpdate and
        # _ripe_behavior_pairs' docstring in this file). Empty list for
        # every pre-existing story until authored - the extractor and
        # _ripe_behavior_pairs both treat an empty vocabulary as "accept
        # anything", so this is a strictly additive, opt-in change.
        "behavior_tag_vocabulary": [str(t).strip() for t in (src.get("behavior_tag_vocabulary") or []) if str(t or "").strip()],
        "characters": characters,
        "relationships": src.get("relationships") or {},
        # Optional ensemble/slice-of-life mode context (see
        # documentation/model_output_docs/SOCIAL_MODE_DESIGN.md). Absent for
        # all pre-existing stories, so this key is simply {} for them and the
        # prompt_builder mode layer emits nothing.
        "mode": src.get("mode") or {},
        "cast_lifecycle": src.get("cast_lifecycle") or {},
        # Character & world model data: routines, threads, evidence, homes.
        "world_model": src.get("world_model") or {},
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
        _reserve_player_resident_slot(state, config)
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
    if config.get("randomize_initial_roster"):
        group = config["player_slot_groups"][state.gender]
        state.cast_lifecycle.choose_initial_roster(group)
    _reserve_player_resident_slot(state, config)


def _reserve_player_resident_slot(state: GameState, config: dict) -> None:
    lifecycle = state.cast_lifecycle
    if lifecycle is None or not lifecycle.enabled or config.get("player_mode") != "resident_slot":
        return
    group = config["player_slot_groups"][state.gender]
    lifecycle.reserve_player_slot(group)
    lifecycle.require_replacement = bool(config.get("require_replacement", False))


def _sync_resident_locations(state: GameState) -> None:
    lifecycle = state.cast_lifecycle
    if lifecycle is None or not lifecycle.player_slot_group:
        return
    state.character_locations = {
        key: location for key, location in state.character_locations.items()
        if key == "player" or lifecycle.is_scene_eligible(key)
    }
    # Older saves can still point at the removed guest room.
    config = state.story_cfg["cast_lifecycle"]
    bedroom = config["player_bedrooms"][lifecycle.player_slot_group]
    if state.location_id == "player_bedroom":
        state.location_id = bedroom
        if state.world_runtime:
            location = state.world_runtime.world_graph.locations[bedroom]
            state.location = location.name
            state.location_uuid = location.uuid
    for key, location in state.character_locations.items():
        if location == "player_bedroom":
            state.character_locations[key] = bedroom


def _gather_opening_residents(state: GameState) -> None:
    """Place the opening cast where the opening scene happens.

    Every active NPC starts at ``initial_active_location_id``. In
    ``resident_slot`` mode the opening welcomes the player into that same
    gathering (dinner in the Six Strangers house), so the player starts there
    too: all six residents are home and physically present on turn 1. Before
    this, the player stayed at the front entry while the NPCs sat in the
    living room, the scene brief said "People present: none", and the model
    invented whereabouts ("Yuto should be back from practice soon").
    """
    lifecycle = state.cast_lifecycle
    config = (getattr(state, "story_cfg", None) or {}).get("cast_lifecycle") or {}
    gathering = str(config.get("initial_active_location_id") or "living_room")
    for key in lifecycle.active_ids():
        state.character_locations.setdefault(key, gathering)
    runtime = getattr(state, "world_runtime", None)
    if config.get("player_mode") != "resident_slot" or runtime is None:
        return
    location = runtime.world_graph.locations.get(gathering)
    if location is None:
        return
    state.location_id = gathering
    state.location = location.name
    state.location_uuid = getattr(location, "uuid", "")
    for key in lifecycle.active_ids():
        state.character_locations[key] = gathering


def _remove_upcoming_relationships(state: GameState) -> None:
    lifecycle = state.cast_lifecycle
    graph = state.character_graph
    if lifecycle is None or not lifecycle.player_slot_group or graph is None:
        return
    upcoming = {key for key, member in lifecycle.members.items() if member.status is CastStatus.UPCOMING}
    graph.edges = {
        key: edge for key, edge in graph.edges.items()
        if edge.from_id not in upcoming and edge.to_id not in upcoming
    }


def _seed_initial_active_relationships(state: GameState) -> None:
    """Give every randomized opening resident a real first-meeting edge.

    Authored story graphs can describe a particular premiere cast, while a
    lifecycle-enabled game may draw any eligible residents into its opening
    roster.  Preserve authored edges where they exist and let the generic
    graph first-meeting rule fill only the missing ones.
    """
    lifecycle = getattr(state, "cast_lifecycle", None)
    graph = getattr(state, "character_graph", None)
    if lifecycle is None or graph is None:
        return
    participant_ids = set(lifecycle.active_ids()) | {"player"}
    for key in participant_ids:
        character = (getattr(state, "characters", {}) or {}).get(key)
        if character is not None and key not in graph.characters:
            graph.add_character(character)
    graph.process_first_meetings(participant_ids, state, int(getattr(state, "minute", 0) or 0), is_new_encounter=True)


def player_visible_character_ids(state: GameState) -> set[str] | None:
    """Phase 1.4: the ONE policy for which character IDs a player-facing view
    (roster, journal, or any future public projection) may ever mention.

    Returns None when cast lifecycle isn't enabled for this story - callers
    should treat that as "no filtering; every authored character is visible"
    (matches _cast_roster_payload's existing no-lifecycle fallback).

    The audit's finding: "is this character currently active" is NOT
    sufficient — a departed resident the player actually met must stay
    visible (their journal history is legitimately learned), while an
    unarrived UPCOMING resident must never appear at all, even though they
    are fully authored in story content (goals, dialogue hooks, etc. for
    characters the player hasn't met yet). The three lifecycle statuses that
    mean "the player has, at some point, actually been in scene with this
    character" are ACTIVE, INACTIVE (deactivated but not via the full
    departure/replacement flow - still someone the player met), and
    DEPARTED (replaced out through the normal flow). UPCOMING is the one
    status that must never leak, in any view.
    """
    lifecycle = getattr(state, "cast_lifecycle", None)
    if lifecycle is None or not lifecycle.enabled:
        return None
    visible = {
        key for key, member in lifecycle.members.items()
        if member.status is not CastStatus.UPCOMING
    }
    if lifecycle.player_slot_group:
        visible.add("player")
    return visible


def player_visible_arrival_minute(state: GameState, character_id: str) -> int | None:
    """Phase 1.4: earliest minute a player-facing view may show content
    attributed to `character_id`, or None if there is no lower bound (no
    lifecycle, or the character has no recorded activation - e.g. an
    original day-one resident who was never activate()'d through the
    lifecycle machinery because they started active).

    Closes the second half of the audit's finding: a character's `goal` can
    carry AUTHORED history entries (e.g. their starting motivation) whose
    `timestamp_minute` may be 0 or otherwise predate the moment they actually
    entered the scene as a mid-game arrival. A public view must not surface
    that as something the player has "learned" before it was ever shown to
    them in play.
    """
    lifecycle = getattr(state, "cast_lifecycle", None)
    if lifecycle is None or not lifecycle.enabled:
        return None
    member = lifecycle.members.get(character_id)
    if member is None:
        return None
    return member.activated_minute


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
    if lifecycle.player_slot_group:
        active.append({"id": "player", "name": state.user.display_name or state.player_name or "Player", "role": "Housemate (you)"})
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


# ---------------------------------------------------------------------------
# TIME SKIP — player-triggered jump forward in world time.
# ---------------------------------------------------------------------------
# Named presets only (no free-form minute counts from the client) so every
# value is validated and the narration cue text stays predictable.
TIME_SKIP_PRESETS: dict[str, tuple[int, str]] = {
    "HOURS": (4 * 60, "A few hours pass"),
    "OVERNIGHT": (8 * 60, "The night passes"),
    "DAY": (24 * 60, "A full day passes"),
}
TIME_SKIP_PREFIX = "__cmd_skip__:"


def _parse_time_skip(msg: str) -> Optional[tuple[int, str]]:
    """Returns (minutes, narration_cue) if msg is a valid time-skip command,
    else None. Unknown preset keys are treated as not-a-command (safe no-op),
    matching the tolerant-parsing convention used elsewhere in this file."""
    text = (msg or "").strip()
    if not text.startswith(TIME_SKIP_PREFIX):
        return None
    preset_key = text[len(TIME_SKIP_PREFIX):].strip().upper()
    return TIME_SKIP_PRESETS.get(preset_key)


def _parse_natural_wait(msg: str, state: GameState) -> Optional[tuple[int, str]]:
    """Resolve an explicit first-person wait until tomorrow's clock time.

    Keep this narrow: a question, wish, or plan about waiting must not move
    the world. A fully general time intent needs the typed action extractor.
    """
    from datetime import datetime, timedelta

    match = re.search(
        r"(?:^I\s+wait|\bthen\s+(?:I\s+)?wait)\s+until\s+tomorrow\s+at\s+"
        r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", str(msg or ""), re.I,
    )
    if match is None:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    if not 1 <= hour <= 12 or not 0 <= minute < 60:
        return None
    now = datetime.fromisoformat(WorldTimeFormatter.compute(
        getattr(state, "world_start_datetime", ""), getattr(state, "minute", 0),
    ).iso)
    target = (now + timedelta(days=1)).replace(
        hour=hour % 12 + (12 if match.group(3).lower() == "pm" else 0),
        minute=minute, second=0, microsecond=0,
    )
    elapsed = int((target - now).total_seconds() // 60)
    return (elapsed, "The player waited until the requested time") if elapsed > 0 else None


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
            "Preserve [SPEAKER:id] and [/SPEAKER] markers and their IDs EXACTLY. "
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
                f"{OPENAI_BASE_URL}/chat/completions",
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
                "disposition": (
                    getattr(edge, "disposition").to_dict()
                    if getattr(edge, "disposition", None) is not None else None
                ),
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


def _serialize_character_goals(characters: dict) -> dict:
    """Phase 3 'Social life': state.characters is otherwise always rebuilt
    fresh from story data on every restore (nothing else about a Character
    persists across a restart today), which would silently discard any
    runtime goal evolution from propose_change(). Persist just the `goal`
    field per character key - everything else about a Character is safe to
    re-derive from the story definition every time."""
    out: dict[str, dict] = {}
    for key, ch in (characters or {}).items():
        goal = getattr(ch, "goal", None)
        if goal is not None:
            out[str(key)] = goal.to_dict()
    return out


def _restore_character_goals(state: GameState, saved: dict | None) -> None:
    if not isinstance(saved, dict):
        return
    for key, data in saved.items():
        ch = state.characters.get(str(key))
        if ch is not None and isinstance(data, dict):
            ch.goal = EvolvingTrait.from_dict(data)


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


def _serialize_behavior_log(log: dict) -> dict:
    return {str(k): [str(t) for t in (v or [])] for k, v in (log or {}).items()}


def _restore_behavior_log(saved: dict | None) -> dict:
    if not isinstance(saved, dict):
        return {}
    return {str(k): [str(t) for t in (v or []) if isinstance(v, list)] for k, v in saved.items() if isinstance(v, list)}


def _migrate_behavior_log_to_vocabulary(log: dict, vocabulary: list[str]) -> dict:
    """BL-16 fix: a session saved BEFORE a story authored a
    behavior_tag_vocabulary may hold free-text tags that no longer match
    it. Dropping unknown tags (rather than fuzzy-mapping them) is the
    simplest correct choice - the window is capped at
    BEHAVIOR_LOG_WINDOW_SIZE entries per pair, so a few stale entries lost
    on the first load after authoring a vocabulary is a small, one-time
    cost. A pair left with zero matching tags is dropped entirely."""
    if not vocabulary:
        return log
    allowed = {str(t).strip().lower() for t in vocabulary}
    migrated: dict[str, list[str]] = {}
    for pair_key, tags in (log or {}).items():
        kept = [t for t in tags if str(t).strip().lower() in allowed]
        if kept:
            migrated[pair_key] = kept
    return migrated


def _ripe_behavior_pairs(state: GameState) -> dict[str, list[str]]:
    """Phase 3 'Social life': pure function, no LLM. Decides which pairs in
    state.recent_behavior_log have accumulated enough tags to be worth an
    expensive LLM shift judgment on the NEXT extractor call - most turns,
    this returns {} and zero extra prompt tokens are spent. A pair is
    "ripe" when it has at least BEHAVIOR_LOG_RIPE_THRESHOLD tags AND the
    majority tag in the most recent BEHAVIOR_LOG_RECENT_SPAN entries
    differs from the majority tag in the entries before that recent span -
    i.e. a genuine swing, not just noise or a single outlier tag.
    """
    from collections import Counter

    ripe: dict[str, list[str]] = {}
    for pair_key, tags in (getattr(state, "recent_behavior_log", {}) or {}).items():
        if len(tags) < BEHAVIOR_LOG_RIPE_THRESHOLD:
            continue
        recent = tags[-BEHAVIOR_LOG_RECENT_SPAN:]
        earlier = tags[:-BEHAVIOR_LOG_RECENT_SPAN]
        if not earlier:
            continue
        recent_majority = Counter(recent).most_common(1)[0][0]
        earlier_majority = Counter(earlier).most_common(1)[0][0]
        if recent_majority != earlier_majority:
            ripe[pair_key] = list(tags)
    return ripe


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
        raw_disposition = data.get("disposition")
        disposition = EvolvingTrait.from_dict(raw_disposition) if isinstance(raw_disposition, dict) else None

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
            existing.disposition = disposition
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
            disposition=disposition,
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
        "language_theme": (
            state.language_theme.value
            if isinstance(getattr(state, "language_theme", None), LanguageTheme)
            else str(getattr(state, "language_theme", LanguageTheme.ENGLISH_US.value))
        ),
        "character_locations": dict(getattr(state, "character_locations", {}) or {}),
        "main_character_id": str(getattr(state, "main_character_id", "") or ""),
        "opening_cast": list(getattr(state, "opening_cast", []) or []),
        "world_model": (state.world_model.to_dict() if getattr(state, "world_model", None) is not None else None),
        "cast_lifecycle": (
            state.cast_lifecycle.to_dict()
            if getattr(state, "cast_lifecycle", None) is not None else None
        ),
        "pending_events": _serialize_pending_events(getattr(state, "pending_events", []) or []),
        "character_goals": _serialize_character_goals(getattr(state, "characters", {}) or {}),
        "recent_behavior_log": _serialize_behavior_log(getattr(state, "recent_behavior_log", {}) or {}),
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
        # Restore the persisted choice when possible; older sessions derive it
        # from the authored story definition.
        try:
            restored.language_theme = LanguageTheme(saved.get("language_theme"))
        except Exception:
            restored.language_theme = _derive_language_theme_from_story_cfg(restored.story_cfg)
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
                goal=ch.goal,
                tells=list(ch.tells),
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

        _sync_resident_locations(restored)

        restored.opening_cast = [str(k) for k in (saved.get("opening_cast") or []) if k]
        # Character & world model: restore when saved; older saves rebuild it
        # lazily on their next turn (world_model.turn.ensure_model).
        if isinstance(saved.get("world_model"), dict):
            try:
                restored.world_model = WorldModel.from_dict(saved["world_model"])
            except Exception:
                logger.exception("world_model restore failed; it will be rebuilt")
                restored.world_model = None
        # The runtime focal lens (e.g. an opening greeter, or a replacement
        # arrival) outranks the authored is_main default.
        saved_main = str(saved.get("main_character_id") or "").strip()
        if saved_main and saved_main in (restored.characters or {}):
            restored.main_character_id = saved_main

        if (
            restored.cast_lifecycle is not None
            and restored.main_character_id
            and not restored.cast_lifecycle.is_scene_eligible(restored.main_character_id)
        ):
            restored.main_character_id = next(iter(restored.cast_lifecycle.active_ids()), None)

        # Character relationship graph
        if isinstance(story_def, StoryDefinition) and story_def.relationships:
            restored.character_graph = copy.deepcopy(story_def.relationships)
            _restore_character_graph(restored, saved.get("character_graph"))
        _remove_upcoming_relationships(restored)
        _seed_initial_active_relationships(restored)

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
        _restore_character_goals(restored, saved.get("character_goals"))
        restored.recent_behavior_log = _migrate_behavior_log_to_vocabulary(
            _restore_behavior_log(saved.get("recent_behavior_log")),
            (restored.story_cfg or {}).get("behavior_tag_vocabulary") or [],
        )
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
    lifecycle_cfg = cfg.get("cast_lifecycle", {}) or {}
    bedroom_id = (lifecycle_cfg.get("player_bedrooms", {}) or {}).get(
        getattr(state, "cast_lifecycle", None).player_slot_group
        if getattr(state, "cast_lifecycle", None) else "",
        "",
    )
    bedroom = bedroom_id.replace("_", " ") if bedroom_id else "shared bedroom"
    return (
        text.replace("{{PLAYER_NAME}}", name)
            .replace("{{HONORIFIC}}", honorific)
            .replace("{{PLAYER_BEDROOM}}", bedroom)
            .replace("{{HOUSEMATE_MIX}}", _housemate_mix(state))
    )


_COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six")


def _housemate_mix(state: GameState) -> str:
    """Describe the opening's gathered housemates, e.g. "two other men and three women".

    The opening shows only two speakers; without this line the model assumed
    the rest of the house was out and invented where they were.
    """
    lifecycle = getattr(state, "cast_lifecycle", None)
    if lifecycle is None or not lifecycle.player_slot_group:
        return "the whole household"
    parts = []
    for group, noun in (("men", "men"), ("women", "women")):
        count = len(lifecycle.active_ids(group))
        if not count:
            continue
        other = "other " if group == lifecycle.player_slot_group else ""
        word = _COUNT_WORDS[count] if count < len(_COUNT_WORDS) else str(count)
        singular = {"men": "man", "women": "woman"}[noun]
        parts.append(f"{word} {other}{noun if count != 1 else singular}")
    return " and ".join(parts) or "the whole household"


def _opening_for_new_game(story_def: StoryDefinition, state: GameState) -> str:
    """Choose an authored opening variant without making story text procedural.

    A story may author ordered JSON narration/speech segments. Runtime roles
    resolve to residents actually present in this randomized opening cast.
    Older stories retain their text/variant path unchanged. Placeholders are
    resolved afterwards.
    """
    opening_cfg = story_def.get("opening", {}) or {}
    authored = opening_cfg.get("segments") or []
    if authored:
        lifecycle = getattr(state, "cast_lifecycle", None)
        active_ids = list(lifecycle.active_ids()) if lifecycle else [
            key for key in (getattr(state, "characters", {}) or {}) if key != "player"
        ]
        # Prefer the engine-staged welcome party; legacy stories draw at random.
        chosen = [key for key in (getattr(state, "opening_cast", None) or []) if key in active_ids]
        if not chosen:
            chosen = secrets.SystemRandom().sample(active_ids, min(2, len(active_ids)))
        role_ids = {
            "@greeter": chosen[0] if chosen else "unknown",
            "@second": chosen[1] if len(chosen) > 1 else (chosen[0] if chosen else "unknown"),
        }
        parts = []
        for segment in authored:
            if not isinstance(segment, dict) or not str(segment.get("text") or "").strip():
                continue
            body = str(segment["text"]).strip()
            if segment.get("kind") == "dialogue":
                speaker_id = role_ids.get(segment.get("speaker_id"), segment.get("speaker_id"))
                if speaker_id not in active_ids:
                    speaker_id = "unknown"
                parts.append(f"[SPEAKER:{speaker_id}]{body}[/SPEAKER]")
            else:
                parts.append(body)
        return "\n\n".join(parts)
    variants = [str(item) for item in (opening_cfg.get("variants") or []) if str(item).strip()]
    opening = secrets.choice(variants) if variants else str(
        opening_cfg.get("text", "The room is quiet. A story begins.")
    )
    lifecycle = getattr(state, "cast_lifecycle", None)
    active_ids = lifecycle.active_ids() if lifecycle else []
    if active_ids:
        # The welcome belongs to a resident who is actually in this draw, not
        # a fixed authored host who may be waiting in the replacement queue.
        return f"{opening}\n\n[SPEAKER:{secrets.choice(active_ids)}]Welcome — we're glad you're here."
    return opening


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
# LANGUAGE THEME DERIVATION & MIXING
# ---------------------------------------------------------------------------

def _derive_language_theme_from_story_cfg(cfg: dict) -> LanguageTheme:
    """Infer the session LanguageTheme from a story config dict.

    The explicit ``language_theme`` field is authoritative.  The legacy
    Korean flag and Japanese vocabulary heuristic remain only for old story
    files that have not yet been migrated.
    """
    try:
        if not cfg or not isinstance(cfg, dict):
            return LanguageTheme.ENGLISH_US
        explicit = cfg.get("language_theme")
        if explicit:
            try:
                return LanguageTheme(str(explicit))
            except ValueError:
                pass
        rules = (cfg.get("rules") or {}).get("dialogue") or {}
        if rules.get("mix_korean_phrases"):
            return LanguageTheme.ENGLISH_KOREAN
        lang = cfg.get("language") or {}
        # Heuristic: if honorifics include common Japanese suffixes or casual_terms include Japanese words
        honorifics = lang.get("honorifics") or {}
        casual = lang.get("casual_terms") or []
        # Look for 'san' or 'kun' in honorifics or casual terms
        if any("san" in str(v).lower() or "kun" in str(v).lower() for v in list(honorifics.values()) + list(casual)):
            return LanguageTheme.ENGLISH_JAPANESE
    except Exception:
        pass
    return LanguageTheme.ENGLISH_US


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

# Stable, provider-agnostic message shown to players when the story master call
# fails upstream. Deliberately says nothing about which provider, model, quota or
# account was involved - operators correlate via req_id in the JSONL log instead.
_PUBLIC_UPSTREAM_ERROR = (
    "The story master is unavailable right now. Please try that again in a moment."
)


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

    # TIME SKIP — jump the world clock forward, then fall through into the
    # normal turn pipeline with a short narration-cue message so the story
    # master narrates what's changed (consistent with the North Star's
    # "events continue off-screen" principle — a skip is not a silent no-op,
    # the next reply must acknowledge time has passed). advance_time_by()
    # runs here (once, for the full jump) instead of relying on the
    # per-turn advance_time() call later, which is sized for dialogue-length
    # deltas, not multi-hour/day jumps.
    # World model: the interval this turn consumes is (minute_before, minute_after].
    _wm_minute_before = int(getattr(state, "minute", 0) or 0) if state is not None else 0
    _wm_player_words = msg
    _wm_sleeping = False
    _time_skip = _parse_time_skip(msg) or (_parse_natural_wait(msg, state) if state is not None else None)
    _is_time_skip_turn = False
    if _time_skip is not None and state is not None:
        _skip_minutes, _skip_cue = _time_skip
        advance_time_by(state, _skip_minutes)
        # Embed the resulting clock time directly in the cue the story master
        # reads. The world clock is otherwise never surfaced in the prompt
        # (only in the debug box) - live-verified this turn silently narrates
        # the OLD time/scene ("dinner should be ready soon") if the cue is
        # left generic, because nothing else in the prompt tells the model
        # time has moved. Stating the new time explicitly, in the one place
        # the model reliably reads every turn (the user message), fixes this
        # without a broader prompt-builder change.
        _new_ts = WorldTimeFormatter.compute(
            getattr(state, "world_start_datetime", ""), getattr(state, "minute", 0)
        ).display
        msg = f"{msg}\n[Time skip] {_skip_cue}. It is now {_new_ts}."
        _is_time_skip_turn = True
        _wm_player_words = ""

    # "I go to sleep": sleep until the next morning; the world keeps moving
    # (routines, off-screen life) through the skipped hours. Turn-based: the
    # whole night resolves in this one turn.
    if not _is_time_skip_turn and state is not None and world_turn.enabled(state):
        world_turn.ensure_model(state, lore=_lore_chunks_for(state))
        _sleep_for = world_turn.sleep_minutes(state, msg)
        if _sleep_for > 0:
            _home = getattr(state.world_model, "home_of_player", "")
            _runtime = getattr(state, "world_runtime", None)
            if _home and _runtime is not None and _home in _runtime.world_graph.locations:
                state.location_id = _home
                state.location = _runtime.world_graph.locations[_home].name
                state.location_uuid = getattr(_runtime.world_graph.locations[_home], "uuid", "")
            advance_time_by(state, _sleep_for)
            _new_ts = WorldTimeFormatter.compute(
                getattr(state, "world_start_datetime", ""), getattr(state, "minute", 0)
            ).display
            msg = f"{msg}\n[Time skip] The night passes; the player slept and wakes up. It is now {_new_ts}."
            _is_time_skip_turn = True
            _wm_sleeping = True

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

    # MAP TOGGLE - keep chat clear; the client owns the full-screen artwork.
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
            notice = _box("World Map", ["Open the map from the game menu."])
            
            # Get world map image path if available
            map_image = None
            if state.story_cfg:
                world_cfg = state.story_cfg.get("world", {}) or {}
                map_image = str(world_cfg.get("world_map_image", "")).strip() or None

        result = {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}
        if state and state.world_runtime:
            from backend.app.engine.world.map_model import world_map_payload
            result["world_map"] = world_map_payload(state.world_runtime.world_graph)
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
    stage_timer = StageTimer()  # Phase 0B: per-turn stage ledger

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
        # Derive language theme from authored story config (English US default)
        try:
            new_state.language_theme = _derive_language_theme_from_story_cfg(new_state.story_cfg)
        except Exception:
            new_state.language_theme = LanguageTheme.ENGLISH_US
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
                goal=ch.goal,
                tells=list(ch.tells),
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

        _sync_resident_locations(new_state)

        # A randomly selected opening cast may not include the authored focal
        # character. Keep the focal lens inside the current five-NPC roster.
        if new_state.cast_lifecycle and not new_state.cast_lifecycle.is_scene_eligible(new_state.main_character_id):
            new_state.main_character_id = next(iter(new_state.cast_lifecycle.active_ids()), None)

        if new_state.cast_lifecycle:
            _gather_opening_residents(new_state)

        # Engine-backed opening: put the story's welcome party (if authored)
        # in the player's start room so opening prose, people-present and the
        # first storyteller reply all describe the same scene.
        stage_opening_scene(new_state)

        # Load character relationship graph from story definition
        if isinstance(story_def, StoryDefinition) and story_def.relationships:
            new_state.character_graph = copy.deepcopy(story_def.relationships)
        _remove_upcoming_relationships(new_state)
        _seed_initial_active_relationships(new_state)

        # Fallback knowledge bundle for main
        if not new_state.knowledge_character_id and main_char_def:
            new_state.knowledge_character_id = main_char_def.knowledge_character_id

        # Label all knowledge chunks with player visibility for debug player agent retrieval.
        _seed_player_visibility(new_state)

        # Character & world model: seeded from the staged opening positions,
        # canonical facts and the authored lore bundle (docs: CHARACTER_WORLD_MODEL_*).
        world_turn.ensure_model(new_state, lore=_lore_chunks_for(new_state))

        opening = _opening_for_new_game(story_def, new_state)
        opening = apply_placeholders(opening, new_state)
        opening, segments = present_dialogue(opening, new_state)
        opening = dialogue_transcript(segments)

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
                # A new-game command replaces the prior playthrough.  Its
                # next turn must not be mistaken for a network retry of the
                # old playthrough's final request.
                await SessionRepo.clear_last_request(session_id, new_state.user_id)
            except Exception:
                logger.exception("Failed to persist new session %s for user %s", session_id, user_id)

        # Apply Chinese translation if chinese_mode is enabled
        reply = opening
        if bool(sess.get("chinese_mode", False)):
            reply, segments = present_dialogue(await _translate_to_chinese(encode_dialogue(segments)), new_state)

        return {"reply": reply, "segments": segments, "usage": {"total_tokens": 0}, "character": "default"}

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

    # Phase 1.1: isolate this turn's mutations from the live cached session.
    #
    # Problem this closes: `state` below is a LIVE reference into
    # SESSIONS[session_id]["state"] (see `state = sess["state"]` above and in
    # get_session()), mutated in place, not copy-on-write. Every mutation from
    # here on (advance_time, relationship deltas, cast lifecycle, state.turns
    # += 1, scene knowledge) was applied directly to that shared object BEFORE
    # the storyteller call. If the storyteller call then fails (see the
    # retrieval/upstream/decode `return` points below) or the process is
    # killed mid-turn, the live session was left permanently mutated with no
    # completed reply and no BL-02 dedup token — a client retry would
    # reprocess from already-advanced state and double-apply everything.
    #
    # Fix: clone the state into an isolated working copy up front. All
    # mutation below operates on the clone. The clone is written back to
    # SESSIONS only at the single success point (alongside the BL-02 dedup
    # token, in the same block) — see `_publish_turn_state` below. Every
    # failure `return` between here and there discards the clone; the live
    # session is untouched by construction, so a retry sees exactly the
    # pre-turn state it would have seen if this turn had never been attempted.
    #
    # Cost: measured ~30ms for a full GameState clone (world graph, cast
    # lifecycle, character graph, session chunk store all included) against a
    # multi-second storyteller call — not a meaningful tax on turn latency.
    working_state = copy.deepcopy(state)
    state = working_state
    # `log` (recent dialogue turns, used for MEMORY_TURNS context) is a
    # separate mutable structure hanging off `sess`, not off `state` — clone
    # it too so its mutation below (log.append(...) further down) is subject
    # to the same discard-on-failure / publish-on-success rule.
    working_log = list(log)
    log = working_log

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
    # Skip on a time-skip turn: the narration cue ("A few hours pass") is
    # narrator framing, not player dialogue, but its shape (a short bare
    # phrase of letters/spaces) matches extract_user_name_from_text()'s
    # "solo name" fallback pattern and would otherwise overwrite the
    # player's real name with the cue text.
    if not _is_time_skip_turn:
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
        with stage_timer.stage("retrieval"):
            # Route retrieval to the correct character bundle for this story.
            if getattr(state, "knowledge_character_id", ""):
                IndexService.set_active_character(state.knowledge_character_id)
            namespace = build_namespace_key(user_id=getattr(state, "user_id", ""), story_id=getattr(state, "story", ""), instance=getattr(state, "instance", 1))
            if dynamic_context_enabled():
                retrieved, debug = retrieve_context_candidates(
                    msg, namespace=namespace, session_store=state.session_chunk_store,
                )
            else:
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
            # Phase 3 "Social life": only ever ask the extractor to judge a
            # social shift when the cheap, no-LLM heuristic has flagged a
            # pair's accumulated behavior as ripe - most turns this is
            # empty and the extractor prompt is byte-identical to before
            # this feature existed. Evaluate at most one pair per turn to
            # keep the added prompt small and the judgment focused.
            _ripe_pairs = _ripe_behavior_pairs(state)
            _behavior_window = None
            if _ripe_pairs:
                _ripe_pair_key = next(iter(_ripe_pairs))
                _behavior_window = {"pair": _ripe_pair_key, "tags": _ripe_pairs[_ripe_pair_key]}

            _log({
                "kind": "turn_extraction_attempting",
                "user_msg": msg,
                "current_location_id": state.location_id,
                "current_location_name": state.location,
            })
            # Step 1 of the Jev provider architecture (see
            # documentation/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §1): the
            # stage ledger instrumented retrieval/storyteller/commit but NOT
            # extraction, so production extractor latency was an inference
            # rather than a recorded fact. Locally this call measured ~3.6s
            # p50, which is NOT reconcilable with Phase 0B's measured 3.1-3.9s
            # TOTAL turn time - meaning production is faster than the local
            # measurement and the real number was unknown. This stage makes it
            # observable before anyone quotes a Jev speedup ratio as a
            # production figure.
            with stage_timer.stage("extraction"):
                extraction = await _TURN_EXTRACTOR.extract(
                    user_msg=msg,
                    world_locations=world_locations,
                    character_key_to_name=character_key_to_name,
                    previous_turn_user_msg=str(getattr(state, "last_turn_user_msg", "") or ""),
                    previous_turn_assistant_reply=str(getattr(state, "last_turn_assistant_reply", "") or ""),
                    previous_turn_candidate_chunks=previous_candidate_chunks,
                    conversation_log=log,
                    behavior_window=_behavior_window,
                    allowed_behavior_tags=(state.story_cfg or {}).get("behavior_tag_vocabulary") or [],
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
            # World model: promises made in the previous exchange (the extractor
            # reads it whole, so accepted requests count, plain plans do not).
            if extraction.commitments and world_turn.enabled(state):
                world_turn.ensure_model(state, lore=_lore_chunks_for(state))
                world_turn.record_commitments(state, extraction.commitments)

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

            # Phase 3 "Social life": accumulate cheap per-turn behavior tags
            # unconditionally (raw material only - never itself a change).
            for _tag in (extraction.behavior_tags or []):
                _pair_key = f"{_tag.from_id}->{_tag.to_id}"
                _log_list = state.recent_behavior_log.setdefault(_pair_key, [])
                _log_list.append(_tag.tag)
                del _log_list[:-BEHAVIOR_LOG_WINDOW_SIZE]

            # Apply a genuine SHIFT (never a WISH - "a wish or joke is not
            # departure" applies here too: a momentary flicker must not
            # rewrite a character's goal/disposition). Re-validate
            # subject_id/target_id against current live state - never trust
            # the extractor's earlier allowed_character_keys check alone,
            # same double-validation discipline as the destination_id path.
            _shift = extraction.social_shift_signal
            if _shift is not None and _shift.certainty == "SHIFT" and _shift.new_value:
                _shift_entry_id = f"social_shift_{_shift.scope}_{_shift.subject_id}_{_shift.target_id}_{state.turns}"
                if _shift.scope == "goal":
                    _shift_char = (getattr(state, "characters", {}) or {}).get(_shift.subject_id)
                    if _shift_char is not None:
                        if _shift_char.goal is None:
                            _shift_char.goal = EvolvingTrait(kind="goal", subject_id=_shift.subject_id)
                        _shift_applied = _shift_char.goal.propose_change(
                            _shift.new_value,
                            minute=int(getattr(state, "minute", 0) or 0),
                            reason=_shift.reason or "behavior shift observed over several turns",
                            confidence=0.7,
                            entry_id=_shift_entry_id,
                        )
                        if _shift_applied:
                            state.recent_behavior_log.pop(f"{_shift.subject_id}->{_shift.target_id}", None)
                            _log({
                                "kind": "social_goal_shift_applied",
                                "character_id": _shift.subject_id,
                                "new_value": _shift.new_value,
                            })
                elif _shift.scope == "disposition" and _rel_graph is not None and _shift.target_id:
                    _shift_edge = _rel_graph.get_edge(_shift.subject_id, _shift.target_id)
                    if _shift_edge is not None:
                        if _shift_edge.disposition is None:
                            _shift_edge.disposition = EvolvingTrait(
                                kind="disposition", subject_id=_shift.subject_id, target_id=_shift.target_id,
                            )
                        _shift_applied = _shift_edge.disposition.propose_change(
                            _shift.new_value,
                            minute=int(getattr(state, "minute", 0) or 0),
                            reason=_shift.reason or "behavior shift observed over several turns",
                            confidence=0.7,
                            entry_id=_shift_entry_id,
                        )
                        if _shift_applied:
                            # Reset this pair's window so the next shift
                            # needs fresh evidence, not the same window twice.
                            state.recent_behavior_log.pop(f"{_shift.subject_id}->{_shift.target_id}", None)
                            _log({
                                "kind": "social_disposition_shift_applied",
                                "from_id": _shift.subject_id,
                                "to_id": _shift.target_id,
                                "new_value": _shift.new_value,
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
    # Skip the normal per-turn advance on a time-skip turn: advance_time_by()
    # already jumped the clock by the exact preset amount above, and the
    # narration-cue text ("A few hours pass") is not real player dialogue -
    # running it through advance_time()'s word-count delta would add a few
    # stray extra minutes on top of an otherwise-exact jump.
    if not _is_time_skip_turn:
        advance_time(state, movement_msg)

    # Phase 2 cast-cycling scheduler: execute any departure replacement whose
    # authored availability window (day boundary) has now arrived. Must run
    # after advance_time so this turn's elapsed minutes are already reflected
    # in state.minute/day_number.
    _fired_events = process_pending_events(state, apply_cast_replacement=_apply_cast_replacement)
    for _fired_event, _fired_transition in _fired_events:
        _log({
            "kind": "cast_departure_replacement_applied",
            "event_id": _fired_event.event_id,
            "departing_id": _fired_transition.departing_id,
            "arriving_id": _fired_transition.arriving_id,
        })
        if _fired_transition.arriving_id and state.character_graph is not None:
            _arrival_room_ids = {
                cid for cid, loc in (getattr(state, "character_locations", {}) or {}).items()
                if loc == getattr(state.cast_lifecycle, "arrival_location_id", "")
            }
            _arrival_room_ids.add(_fired_transition.arriving_id)
            _arrival_room_ids.add("player")
            # process_first_meetings() can only create a new edge for a pair
            # with no authored relationship (the arriving character has none
            # - they were upcoming) when both sides are registered in
            # graph.characters. Nothing else in the codebase ever calls
            # add_character(), so ensure the room's participants are present
            # here (state.characters already has them from story load/newgame).
            for _room_key in _arrival_room_ids:
                _room_char = (getattr(state, "characters", {}) or {}).get(_room_key)
                if _room_char is not None and _room_key not in state.character_graph.characters:
                    state.character_graph.add_character(_room_char)
            state.character_graph.process_first_meetings(
                _arrival_room_ids, state, int(getattr(state, "minute", 0) or 0), is_new_encounter=True,
            )
            state.add_transient_entry(
                id=f"cast_arrival_intro_{_fired_transition.arriving_id}",
                namespace=_namespace_for_state(state),
                scope="scene",
                text=f"__cast_arrival_intro__:{_fired_transition.arriving_id}",
                expires_after_turns=1,
            )

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

    # Context selection intentionally happens after validated movement/state
    # updates. It may vary optional memory emphasis, but canonical facts and
    # speaker knowledge still enter the prompt through their deterministic
    # prompt-builder layers.
    if dynamic_context_enabled():
        try:
            with stage_timer.stage("context_selection"):
                scene = (
                    f"Location: {getattr(state, 'location', '') or getattr(state, 'location_id', '')}. "
                    f"Present: {', '.join(sorted(_people_present))}. "
                    f"Turn: {int(getattr(state, 'turns', 0) or 0)}."
                )
                selection = await DynamicContextSelector().select(
                    query=msg,
                    candidates=retrieved,
                    scene=scene,
                    focal_character_id=str(getattr(state, "main_character_id", "") or ""),
                    seed_material=f"{session_id}|{int(getattr(state, 'turns', 0) or 0)}|{msg}",
                )
                retrieved = selection.chunks
                debug = dict(debug or {})
                debug["dynamic_context"] = selection.debug
        except Exception as exc:
            # Optional contextual variety must never make a valid turn fail.
            _log({"kind": "dynamic_context_selection_error", "error": str(exc)})

    # Character & world model: step the world through this turn's interval,
    # mirror locations, plan speakers, and build the per-turn view the prompt
    # builder renders. Presence markers are refreshed from the moved cast.
    _wm_view = world_turn.begin_turn(
        state, _wm_player_words, _wm_minute_before,
        place_names=_world_place_names(state), sleeping=_wm_sleeping,
    )
    if _wm_view is not None:
        _people_present = get_people_present_keys(state)
        _upsert_people_present_markers(state, _people_present)

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
        "response_format": dialogue_response_format(state),
        "temperature": TEMPERATURE,
        # Reserve room for per-speaker metadata as well as the existing prose budget.
        "max_tokens": max(1024, MAX_TOKENS * 2),
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
    with stage_timer.stage("storyteller"):
        async with httpx.AsyncClient(timeout=30.0) as client:
            # One bounded retry on 429/5xx (arena gates saturate the shared
            # rate limit; OpenAI says "try again in 322ms").
            r = await post_with_retry(
                client,
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
        # Phase 0A.6: never return the provider's raw response body to the
        # client. It can carry provider org/project identifiers, quota and
        # billing details, model names, and internal request IDs. The full body
        # is already in the operator log above (kind=chat_upstream_error) with
        # req_id for correlation; the player gets a stable, generic message.
        return {"error": _PUBLIC_UPSTREAM_ERROR, "character": "default"}

    data = r.json()
    try:
        reply = decode_dialogue_response(str(data["choices"][0]["message"]["content"]), state)
    except ValueError:
        return {"error": "The scene response was incomplete. Please try again.", "character": "default"}

    # A draft made only of recent lines (live 2026-09-24: turn 1 re-sent the
    # whole opening) or with nothing presentable left (local arena 2026-09-24:
    # an empty segment list, or only an echo of the player) gets one
    # regeneration; the filters below cannot fix it without leaving the
    # player an empty reply.
    _recent_replies = [m.get("content", "") for m in log if m.get("role") == "assistant"][-3:]
    _draft_segments = drop_player_echo(present_dialogue(extract_state_tag(reply)[0], state)[1], msg)
    _draft_empty = not any(str(seg.get("text") or "").strip() for seg in _draft_segments)
    if _draft_empty or only_repeats(_draft_segments, _recent_replies):
        _log({"kind": "storyteller_repeat_regenerated", "req_id": req_id, "empty": _draft_empty})
        retry_messages = payload["messages"] + [
            {"role": "assistant", "content": reply},
            {"role": "user", "content": (
                "That draft had no new lines for the player." if _draft_empty else
                "That draft only repeated lines that were already said."
            ) + " Write a new beat that responds to the player's latest message; "
                "do not repeat earlier lines or the player's own words."},
        ]
        with stage_timer.stage("storyteller"):
            async with httpx.AsyncClient(timeout=30.0) as client:
                retry = await post_with_retry(
                    client,
                    f"{STORY_MASTER_BASE_URL}/chat/completions",
                    headers={"Authorization": f"Bearer {STORY_MASTER_API_KEY}"},
                    json={**payload, "messages": retry_messages, "model": STORY_MASTER_MODEL},
                )
        if 200 <= retry.status_code < 300:
            try:
                reply = decode_dialogue_response(str(retry.json()["choices"][0]["message"]["content"]), state)
                data = retry.json()
            except (ValueError, KeyError, IndexError):
                pass  # keep the first draft; the repeat filter below still applies

    guess_match = re.search(
        r"\bis your name\s+([A-Za-z][A-Za-z\s'\-]{0,40})\??",
        reply,
        re.IGNORECASE
    )
    if guess_match:
        state.last_assistant_guess_name = clean_name(guess_match.group(1))

    clean, tag = extract_state_tag(reply)
    clean = sanitize_honorific_terms(clean, state)
    # The structured storyteller response is authoritative. Jev is a bounded
    # fallback only for quoted speech left in narration by an older adapter or
    # a malformed speaker segment; it never rewrites already tagged dialogue.
    if has_unmarked_quotes(clean):
        from backend.app.config import settings as jev_settings
        if jev_settings.TYPESAFE_ENABLED and jev_settings.TYPESAFE_API_KEY:
            from backend.app.llm.providers.jev import JevClient
            async with httpx.AsyncClient() as jev_http:
                clean = await attribute_unmarked_quotes(
                    clean, state, JevClient(jev_http),
                    timeout_ms=jev_settings.JEV_TIMEOUT_MS,
                )
    clean, segments = present_dialogue(clean, state)
    # The player already sees their own message; never let the scene hand it
    # to an NPC (arena-found beta regression, 2026-09-23).
    segments = drop_player_echo(segments, msg)
    # Nor re-send recent beats: copied opening lines snowballed on live prod
    # because each copy re-entered the history (2026-09-24).
    segments = drop_repeated_lines(
        segments, [m.get("content", "") for m in log if m.get("role") == "assistant"][-3:])
    segments = ground_social_scene(segments, state)
    world_turn.end_turn(state, _wm_player_words, segments)
    clean = dialogue_transcript(segments)
    # UUID for the AI message — generated here so it's available for JSONL persistence below.
    ai_msg_id: str = uuid.uuid4().hex[:12]

    if not isinstance(tag, dict):
        tag = {"emotion": state.emotion, "rel_delta": 0}

    apply_state_tag(state, tag)

    log.append({"role": "user", "content": msg})
    log.append({"role": "assistant", "content": clean})
    # Phase 1.1: trim the WORKING clone only; do not publish to `sess` yet —
    # that happens once, atomically with `state`, at the success point below.
    log = log[-MEMORY_TURNS:]

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

    if getattr(getattr(state, "world_model", None), "romance_outcome", "") == "solo_departure":
        state.over = True
        clean += f"\n\nEND GAME -- You chose to leave the house alone. Turns: {state.turns}"
    elif win_condition_detected(clean, state):
        state.over = True
        clean += f"\n\nEND GAME YOU WIN -- turns: {state.turns}"

    # Persist this completed turn for next turn's single-call extractor analysis.
    # These must be set BEFORE the session save below so the persisted row
    # reflects the turn just completed, not the prior one (see BL-01).
    state.last_turn_user_msg = msg
    state.last_turn_assistant_reply = clean
    state.last_turn_retrieved_chunks = [dict(c) for c in (retrieved or [])]

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
        reply, segments = present_dialogue(await _translate_to_chinese(encode_dialogue(segments)), state)

    result = {"reply": reply, "segments": segments, "usage": data.get("usage"), "character": "default"}
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

    # Persist state + raw log after every turn (authenticated users only).
    # All in-memory mutations for this turn (including `over` and
    # `last_turn_*` above) must happen before this single save point so the
    # persisted snapshot is atomic with respect to the turn just completed.
    if user_id != "anon":
        try:
            with stage_timer.stage("commit"):
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
                    state_json=_serialize_state(state, log),  # Phase 1.1: working clone, not stale sess["log"]
                    flags_json=json.dumps({
                        "debug_mode": bool(sess.get("debug_mode", False)),
                        "chinese_mode": bool(sess.get("chinese_mode", False)),
                        "epistemic_state": bool(sess.get("epistemic_state", True)),
                        "truth_mode": bool(sess.get("truth_mode", False)),
                    }),
                    last_message=clean[:120],
                    turns=state.turns,
                    last_request_id=client_request_id or "",
                    last_reply_json=json.dumps(result) if client_request_id else "",
                )
                await ConversationRepo.append_turns(
                    user_id=user_id,
                    session_id=session_id,
                    user_msg=msg,
                    assistant_reply=clean,
                    turn=state.turns,
                    user_msg_id=user_msg_id,
                    ai_msg_id=ai_msg_id,
                    segments=segments,
                )
        except Exception as exc:
            logger.exception("Failed to persist turn for session %s user %s", session_id, user_id)
            raise HTTPException(status_code=503, detail="Your turn could not be saved. Please try again.") from exc

    # Include the completed save in the per-stage ledger.
    _log(stage_timer.as_ledger({
        "kind": "turn_stage_ledger",
        "req_id": req_id,
        "session_id": session_id,
        "user_id": user_id,
        "story": state.story or "",
        "turn": state.turns,
        "model": STORY_MASTER_MODEL,
        "prompt_tokens": (data.get("usage") or {}).get("prompt_tokens"),
        "completion_tokens": (data.get("usage") or {}).get("completion_tokens"),
        "cached_tokens": ((data.get("usage") or {}).get("prompt_tokens_details") or {}).get("cached_tokens"),
    }))

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
    #
    # Phase 1.2: for non-anon sessions, ALSO make the extraction OUTPUT
    # durable, not just the attempt. The old `_extract_and_store` wrote
    # chunks only into the in-memory SessionChunkStore, then called plain
    # `mark_done` - a crash between those two lines left a 'done' row with no
    # actual chunks anywhere durable (the in-memory store is only persisted
    # by a LATER turn's session save, which hasn't happened yet at this
    # point). It also used extract_facts_from_message, which collapses
    # "provider failed" and "genuinely nothing to extract" to the same []
    # and always marked done either way - a real outage was silently
    # recorded as a successful empty extraction and never retried.
    character_id = str(getattr(state, "knowledge_character_id", "") or state.story or "unknown")
    if state.session_chunk_store is not None:
        import asyncio as _asyncio

        async def _extract_and_store_durable(
            _user_msg: str, _user_msg_id: str, _ai_reply: str, _ai_msg_id: str,
            _char_id: str, _store: "SessionChunkStore", _session_id: str, _user_id: str,
            _outbox_row_id: int,
        ) -> None:
            usr_result = await extract_facts_with_status(_user_msg, "user", _user_msg_id, _char_id)
            ai_result = await extract_facts_with_status(_ai_reply, "assistant", _ai_msg_id, _char_id)
            # Either half failing means the OUTPUT is incomplete for this
            # turn - must retry, never mark done. (A retry re-runs both
            # halves; INSERT OR REPLACE on the chunk table means a half that
            # already durably succeeded is simply overwritten with the same
            # content, not duplicated.)
            if not usr_result.ok or not ai_result.ok:
                err = usr_result.error or ai_result.error or "unknown extraction failure"
                try:
                    await FactExtractionOutboxRepo.mark_failed(_outbox_row_id, err)
                except Exception:
                    logger.exception(
                        "Failed to mark fact-extraction outbox row %s failed for session %s",
                        _outbox_row_id, _session_id,
                    )
                return
            all_chunks = usr_result.chunks + ai_result.chunks
            _store.add_chunks(all_chunks)
            try:
                await FactExtractionOutboxRepo.mark_done_with_chunks(
                    _outbox_row_id, _session_id, _user_id,
                    {_user_msg_id: usr_result.chunks, _ai_msg_id: ai_result.chunks},
                    EXTRACTOR_VERSION,
                )
            except Exception:
                logger.exception(
                    "Failed to durably persist extracted chunks for session %s (row %s) - "
                    "chunks are in the in-memory store but NOT marked done, so a "
                    "recovery sweep will retry rather than silently lose them",
                    _session_id, _outbox_row_id,
                )

        async def _extract_and_store_best_effort(
            _user_msg: str, _user_id: str, _ai_reply: str, _ai_id: str,
            _char_id: str, _store: "SessionChunkStore",
        ) -> None:
            # Anon path, unchanged: no durable identity to persist chunks or
            # an outbox row against, so this stays fire-and-forget.
            try:
                usr_chunks = await extract_facts_from_message(_user_msg, "user", _user_id, _char_id)
                ai_chunks = await extract_facts_from_message(_ai_reply, "assistant", _ai_id, _char_id)
                _store.add_chunks(usr_chunks + ai_chunks)
            except Exception:
                pass

        if user_id != "anon":
            try:
                outbox_row_id = await FactExtractionOutboxRepo.enqueue(
                    session_id, user_id, msg, user_msg_id, clean, ai_msg_id, character_id,
                )
                _asyncio.ensure_future(_extract_and_store_durable(
                    msg, user_msg_id, clean, ai_msg_id,
                    character_id, state.session_chunk_store, session_id, user_id,
                    outbox_row_id,
                ))
            except Exception:
                logger.exception("Failed to enqueue fact-extraction outbox row for session %s", session_id)
        else:
            try:
                _asyncio.ensure_future(_extract_and_store_best_effort(
                    msg, user_msg_id, clean, ai_msg_id,
                    character_id, state.session_chunk_store,
                ))
            except Exception:
                pass

    # Phase 1.1: publish the working clone back to the live session cache.
    # This is the ONE place `SESSIONS[session_id]` is updated for a regular
    # turn — every mutation since the clone point above happened on
    # `working_state`/`working_log`, never on the object other requests could
    # see. Every failure `return` between the clone point and here skipped
    # this line, so a failed/interrupted turn leaves the live session exactly
    # as it was before this request started. This must run BEFORE the BL-02
    # dedup token write immediately below, so a retry that finds the token can
    # also find the state it describes (both true-together, not just the
    # token alone).
    sess["state"] = state
    sess["log"] = log

    return result
