# backend/app/engine/turn_contract.py
"""
TurnContract — per-turn runtime constraints for the current speaker.

The contract builder collects:
- Identity anchors that must be injected every turn
- Allowed knowledge (known + believed chunks the speaker may reference)
- Forbidden knowledge (SECRET_CANON not yet unlocked)
- Output policy (narration style, player action rules)
- Invariants the validator must check post-generation
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.engine.story_schema_v2 import (
    CanonTier,
    ChunkType,
    KnowledgeChunk,
    OutputPolicy,
    StoryPackageV2,
    Visibility,
)


@dataclass
class Invariant:
    type: str
    description: str
    chunk_id: Optional[str] = None
    props: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TurnContract:
    speaker_character_id: str
    injected_anchors: List[KnowledgeChunk] = field(default_factory=list)
    allowed_knowledge: List[KnowledgeChunk] = field(default_factory=list)
    forbidden_knowledge: List[KnowledgeChunk] = field(default_factory=list)
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)
    invariants: List[Invariant] = field(default_factory=list)
    location_id: Optional[str] = None
    world_minute: int = 0


def build_contract(
    pkg: StoryPackageV2,
    speaker_id: str,
    *,
    location_id: Optional[str] = None,
    world_minute: int = 0,
) -> TurnContract:
    """Build a TurnContract for the given speaker on this turn.

    Rules:
    1. Inject all anchor chunks listed in CharacterAnchors.
    2. Inject any chunk with access.inject_every_turn that allows the speaker.
    3. Allowed knowledge = known ∪ believed, filtered by access policy.
    4. Forbidden = SECRET_CANON chunks not in known/believed.
    5. Add invariants for each anchor (must not contradict).
    6. Add identity drift invariant when identity-type anchors exist.
    """
    character = pkg.characters.get(speaker_id)
    if character is None:
        return TurnContract(speaker_character_id=speaker_id, output_policy=pkg.game.output_policy)

    chunks = pkg.knowledge.chunks
    anchors: List[KnowledgeChunk] = []
    allowed: List[KnowledgeChunk] = []
    forbidden: List[KnowledgeChunk] = []
    invariants: List[Invariant] = []

    # 1. Collect anchor chunks
    for aid in character.anchors.anchor_chunk_ids:
        chunk = chunks.get(aid)
        if chunk is not None:
            anchors.append(chunk)

    # 2. Collect inject_every_turn chunks accessible to this speaker
    for chunk in chunks.values():
        if not chunk.access.inject_every_turn:
            continue
        if chunk in anchors:
            continue
        if _speaker_can_access(chunk, speaker_id):
            anchors.append(chunk)

    # 3. Allowed = known ∪ believed
    accessible_ids = set(character.epistemic.known_chunk_ids) | set(character.epistemic.believed_chunk_ids)
    for cid in accessible_ids:
        chunk = chunks.get(cid)
        if chunk is not None and chunk not in anchors:
            if _speaker_can_access(chunk, speaker_id):
                allowed.append(chunk)

    # 4. Forbidden = SECRET_CANON not in known/believed
    for chunk in chunks.values():
        if chunk.canon_tier == CanonTier.SECRET_CANON:
            if chunk.id not in accessible_ids:
                forbidden.append(chunk)

    # 5. Invariants for each anchor
    has_identity_anchor = False
    for anchor in anchors:
        invariants.append(Invariant(
            type="ANCHOR_CONTRADICTION",
            description=f"Must not contradict: {anchor.content.text}",
            chunk_id=anchor.id,
        ))
        if anchor.type == ChunkType.IDENTITY:
            has_identity_anchor = True

    # 6. Identity drift invariant
    if has_identity_anchor:
        invariants.append(Invariant(
            type="SPEAKER_IDENTITY_DRIFT",
            description="Must not refer to self in third person or imply a different identity",
        ))

    return TurnContract(
        speaker_character_id=speaker_id,
        injected_anchors=anchors,
        allowed_knowledge=allowed,
        forbidden_knowledge=forbidden,
        output_policy=pkg.game.output_policy,
        invariants=invariants,
        location_id=location_id,
        world_minute=world_minute,
    )


def evaluate_triggers(
    pkg: StoryPackageV2,
    character_id: str,
    *,
    player_message: str = "",
    location_id: str = "",
    world_minute: int = 0,
    seed: Optional[int] = None,
) -> List[str]:
    """Evaluate memory triggers for a character, returning newly unlocked chunk IDs.

    Trigger condition format: "type:value"
    - mentions:<keyword>       — case-insensitive keyword in player_message
    - location:<location_id>   — player at this location
    - minute_gte:<N>           — world_minute >= N
    - chunk_known:<chunk_id>   — chunk is in character's known set

    Modifies character.epistemic in place (moves chunks from forgotten to known).
    """
    character = pkg.characters.get(character_id)
    if character is None:
        return []

    rng = random.Random(seed) if seed is not None else random.Random()
    unlocked: List[str] = []

    for trigger in character.epistemic.memory_rules.triggers:
        if not _condition_met(trigger.condition, player_message, location_id, world_minute, character):
            continue
        if trigger.probability < 1.0 and rng.random() > trigger.probability:
            continue

        for chunk_id in trigger.unlock_chunk_ids:
            if chunk_id in character.epistemic.known_chunk_ids:
                continue
            # Move from forgotten to known
            if chunk_id in character.epistemic.forgotten_chunk_ids:
                character.epistemic.forgotten_chunk_ids.remove(chunk_id)
            character.epistemic.known_chunk_ids.append(chunk_id)
            unlocked.append(chunk_id)

    return unlocked


def _speaker_can_access(chunk: KnowledgeChunk, speaker_id: str) -> bool:
    if chunk.access.visibility == Visibility.PUBLIC:
        return True
    if chunk.access.visibility == Visibility.ENGINE_ONLY:
        return False
    if chunk.access.allowed_character_ids:
        return speaker_id in chunk.access.allowed_character_ids
    return chunk.access.visibility == Visibility.RESTRICTED


def _condition_met(
    condition: str,
    player_message: str,
    location_id: str,
    world_minute: int,
    character: Any,
) -> bool:
    """Parse and evaluate a trigger condition string."""
    if ":" not in condition:
        return False
    ctype, cvalue = condition.split(":", 1)
    ctype = ctype.strip().lower()
    cvalue = cvalue.strip()

    if ctype == "mentions":
        return bool(re.search(re.escape(cvalue), player_message, re.IGNORECASE))
    if ctype == "location":
        return location_id == cvalue
    if ctype == "minute_gte":
        try:
            return world_minute >= int(cvalue)
        except ValueError:
            return False
    if ctype == "chunk_known":
        return cvalue in character.epistemic.known_chunk_ids

    return False
