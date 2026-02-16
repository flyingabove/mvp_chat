# backend/app/engine/story_schema_v2.py
"""
Story Package v2 schema — enums, dataclasses, and from_dict helpers.

Fixes applied over the original redesign spec:
- CharacterHistory is mutable (not frozen) — experienced_chunk_ids grows at runtime
- OutputPolicy drops allow_second_person (redundant with allow_player_action_narration)
- LocationModel gains speaker_character_ids for location-aware speaker resolution
- MemoryTrigger.condition uses a structured format: "type:value" parsed by evaluate_trigger()
- RelationshipState includes collapse() to map multi-dimensional state to legacy int score
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Canon system enums
# ---------------------------------------------------------------------------

class CanonTier(str, Enum):
    ANCHOR = "ANCHOR"
    CANON = "CANON"
    SECRET_CANON = "SECRET_CANON"
    CLAIM = "CLAIM"
    RUMOR = "RUMOR"


class Visibility(str, Enum):
    PUBLIC = "PUBLIC"
    RESTRICTED = "RESTRICTED"
    PRIVATE = "PRIVATE"
    ENGINE_ONLY = "ENGINE_ONLY"


class ChunkType(str, Enum):
    IDENTITY = "IDENTITY"
    FACT = "FACT"
    EVENT = "EVENT"
    MEMORY = "MEMORY"
    EVIDENCE = "EVIDENCE"
    RULE = "RULE"
    RUMOR = "RUMOR"
    NOTE = "NOTE"


# ---------------------------------------------------------------------------
# KnowledgeChunk sub-objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Content:
    text: str
    data: Dict[str, Any] = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Content":
        d = d or {}
        return cls(
            text=str(d.get("text", "")),
            data=dict(d.get("data") or {}),
            aliases=list(d.get("aliases") or []),
            entities=list(d.get("entities") or []),
        )


@dataclass(frozen=True)
class Provenance:
    source: str = "author"
    confidence: float = 1.0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Provenance":
        d = d or {}
        return cls(
            source=str(d.get("source", "author")),
            confidence=max(0.0, min(1.0, float(d.get("confidence", 1.0)))),
            created_at=d.get("created_at"),
            updated_at=d.get("updated_at"),
        )


@dataclass(frozen=True)
class UnlockRules:
    required_objective_ids: List[str] = field(default_factory=list)
    required_chunk_ids: List[str] = field(default_factory=list)
    required_location_id: Optional[str] = None
    min_world_minute: Optional[int] = None
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UnlockRules":
        d = d or {}
        return cls(
            required_objective_ids=list(d.get("required_objective_ids") or []),
            required_chunk_ids=list(d.get("required_chunk_ids") or []),
            required_location_id=d.get("required_location_id"),
            min_world_minute=d.get("min_world_minute"),
            props=dict(d.get("props") or {}),
        )


@dataclass(frozen=True)
class AccessPolicy:
    visibility: Visibility = Visibility.PUBLIC
    allowed_character_ids: List[str] = field(default_factory=list)
    unlock_rules: UnlockRules = field(default_factory=UnlockRules)
    inject_every_turn: bool = False
    speaker_must_not_deny: bool = False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AccessPolicy":
        d = d or {}
        vis_raw = str(d.get("visibility", "PUBLIC")).upper()
        try:
            vis = Visibility(vis_raw)
        except ValueError:
            vis = Visibility.PUBLIC
        return cls(
            visibility=vis,
            allowed_character_ids=list(d.get("allowed_character_ids") or []),
            unlock_rules=UnlockRules.from_dict(d.get("unlock_rules")),
            inject_every_turn=bool(d.get("inject_every_turn", False)),
            speaker_must_not_deny=bool(d.get("speaker_must_not_deny", False)),
        )


# ---------------------------------------------------------------------------
# KnowledgeChunk
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KnowledgeChunk:
    id: str
    type: ChunkType
    canon_tier: CanonTier
    access: AccessPolicy
    content: Content
    provenance: Provenance = field(default_factory=Provenance)
    tags: List[str] = field(default_factory=list)
    fields: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, chunk_id: str, d: Dict[str, Any]) -> "KnowledgeChunk":
        d = d or {}
        type_raw = str(d.get("type", "NOTE")).upper()
        tier_raw = str(d.get("canon_tier", "CANON")).upper()
        try:
            chunk_type = ChunkType(type_raw)
        except ValueError:
            chunk_type = ChunkType.NOTE
        try:
            canon_tier = CanonTier(tier_raw)
        except ValueError:
            canon_tier = CanonTier.CANON
        return cls(
            id=chunk_id,
            type=chunk_type,
            canon_tier=canon_tier,
            access=AccessPolicy.from_dict(d.get("access")),
            content=Content.from_dict(d.get("content")),
            provenance=Provenance.from_dict(d.get("provenance")),
            tags=list(d.get("tags") or []),
            fields=dict(d.get("fields") or {}),
        )


# ---------------------------------------------------------------------------
# KnowledgeBase
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RetrievalIndexSpec:
    embedder: str = "default"
    chunking: Dict[str, Any] = field(default_factory=dict)
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RetrievalIndexSpec":
        d = d or {}
        return cls(
            embedder=str(d.get("embedder", "default")),
            chunking=dict(d.get("chunking") or {}),
            props=dict(d.get("props") or {}),
        )


@dataclass
class KnowledgeBase:
    chunks: Dict[str, KnowledgeChunk] = field(default_factory=dict)
    retrieval: RetrievalIndexSpec = field(default_factory=RetrievalIndexSpec)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "KnowledgeBase":
        d = d or {}
        raw_chunks = d.get("chunks") or {}
        chunks = {
            cid: KnowledgeChunk.from_dict(cid, cdata)
            for cid, cdata in raw_chunks.items()
        }
        return cls(
            chunks=chunks,
            retrieval=RetrievalIndexSpec.from_dict(d.get("retrieval")),
        )


# ---------------------------------------------------------------------------
# Character system
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Identity:
    display_name: str
    archetype: str = ""
    tags: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Identity":
        d = d or {}
        return cls(
            display_name=str(d.get("display_name", "")),
            archetype=str(d.get("archetype", "")),
            tags=list(d.get("tags") or []),
        )


@dataclass(frozen=True)
class CharacterTraits:
    tone: str = ""
    speech_style: str = ""
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CharacterTraits":
        d = d or {}
        return cls(
            tone=str(d.get("tone", "")),
            speech_style=str(d.get("speech_style", "")),
            props=dict(d.get("props") or {}),
        )


@dataclass(frozen=True)
class MotivationModel:
    primary: str = ""
    secondary: List[str] = field(default_factory=list)
    fears: List[str] = field(default_factory=list)
    needs: List[str] = field(default_factory=list)
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MotivationModel":
        d = d or {}
        return cls(
            primary=str(d.get("primary", "")),
            secondary=list(d.get("secondary") or []),
            fears=list(d.get("fears") or []),
            needs=list(d.get("needs") or []),
            props=dict(d.get("props") or {}),
        )


@dataclass(frozen=True)
class MemoryTrigger:
    """Declarative memory unlock trigger.

    ``condition`` uses the format ``"type:value"`` where type is one of:
    - ``mentions:<keyword>``  — keyword match in player message (case-insensitive)
    - ``location:<location_id>`` — player is at this location
    - ``minute_gte:<N>``      — world minute >= N
    - ``chunk_known:<chunk_id>`` — another chunk is in the character's known set

    ``probability`` (0..1) is evaluated with a seeded RNG for determinism.
    """
    id: str
    condition: str
    unlock_chunk_ids: List[str] = field(default_factory=list)
    probability: float = 1.0
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryTrigger":
        d = d or {}
        return cls(
            id=str(d.get("id", "")),
            condition=str(d.get("condition", "")),
            unlock_chunk_ids=list(d.get("unlock_chunk_ids") or []),
            probability=max(0.0, min(1.0, float(d.get("probability", 1.0)))),
            props=dict(d.get("props") or {}),
        )


@dataclass(frozen=True)
class MemoryRules:
    triggers: List[MemoryTrigger] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MemoryRules":
        d = d or {}
        raw = d.get("triggers") or []
        return cls(triggers=[MemoryTrigger.from_dict(t) for t in raw])


@dataclass
class EpistemicProfile:
    known_chunk_ids: List[str] = field(default_factory=list)
    believed_chunk_ids: List[str] = field(default_factory=list)
    forgotten_chunk_ids: List[str] = field(default_factory=list)
    memory_rules: MemoryRules = field(default_factory=MemoryRules)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EpistemicProfile":
        d = d or {}
        return cls(
            known_chunk_ids=list(d.get("known_chunk_ids") or []),
            believed_chunk_ids=list(d.get("believed_chunk_ids") or []),
            forgotten_chunk_ids=list(d.get("forgotten_chunk_ids") or []),
            memory_rules=MemoryRules.from_dict(d.get("memory_rules")),
        )


@dataclass(frozen=True)
class CharacterAnchors:
    anchor_chunk_ids: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CharacterAnchors":
        d = d or {}
        return cls(anchor_chunk_ids=list(d.get("anchor_chunk_ids") or []))


@dataclass
class CharacterHistory:
    """Mutable — experienced_chunk_ids grows as the game progresses."""
    experienced_chunk_ids: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CharacterHistory":
        d = d or {}
        return cls(experienced_chunk_ids=list(d.get("experienced_chunk_ids") or []))


@dataclass
class CharacterModel:
    id: str
    identity: Identity
    traits: CharacterTraits = field(default_factory=CharacterTraits)
    motivation: MotivationModel = field(default_factory=MotivationModel)
    epistemic: EpistemicProfile = field(default_factory=EpistemicProfile)
    anchors: CharacterAnchors = field(default_factory=CharacterAnchors)
    history: CharacterHistory = field(default_factory=CharacterHistory)
    stats: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, char_id: str, d: Dict[str, Any]) -> "CharacterModel":
        d = d or {}
        return cls(
            id=char_id,
            identity=Identity.from_dict(d.get("identity")),
            traits=CharacterTraits.from_dict(d.get("traits")),
            motivation=MotivationModel.from_dict(d.get("motivation")),
            epistemic=EpistemicProfile.from_dict(d.get("epistemic")),
            anchors=CharacterAnchors.from_dict(d.get("anchors")),
            history=CharacterHistory.from_dict(d.get("history")),
            stats=dict(d.get("stats") or {}),
        )


# ---------------------------------------------------------------------------
# Relationship graph
# ---------------------------------------------------------------------------

class RelationshipType(str, Enum):
    FRIEND = "FRIEND"
    ENEMY = "ENEMY"
    FAMILY = "FAMILY"
    LOVER = "LOVER"
    EMPLOYER = "EMPLOYER"
    EMPLOYEE = "EMPLOYEE"
    SUSPECT = "SUSPECT"
    VICTIM = "VICTIM"
    WITNESS = "WITNESS"
    OTHER = "OTHER"


@dataclass
class RelationshipState:
    trust: float = 0.0       # -1..1
    fear: float = 0.0        # 0..1
    affection: float = 0.0   # -1..1
    suspicion: float = 0.0   # 0..1
    custom: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.trust = max(-1.0, min(1.0, float(self.trust)))
        self.fear = max(0.0, min(1.0, float(self.fear)))
        self.affection = max(-1.0, min(1.0, float(self.affection)))
        self.suspicion = max(0.0, min(1.0, float(self.suspicion)))

    def collapse(self) -> int:
        """Map multi-dimensional state to a legacy integer score (-5..+5).

        Formula: weighted sum of affection (dominant) and trust, reduced by
        fear and suspicion, then scaled to the -5..+5 range.
        """
        raw = (self.affection * 0.5 + self.trust * 0.3
               - self.fear * 0.1 - self.suspicion * 0.1)
        return max(-5, min(5, round(raw * 5)))

    def apply_delta(self, **kwargs: float) -> None:
        for key, delta in kwargs.items():
            if key == "custom":
                continue
            if hasattr(self, key):
                old = getattr(self, key)
                setattr(self, key, old + delta)
        self.__post_init__()  # re-clamp

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RelationshipState":
        d = d or {}
        return cls(
            trust=float(d.get("trust", 0.0)),
            fear=float(d.get("fear", 0.0)),
            affection=float(d.get("affection", 0.0)),
            suspicion=float(d.get("suspicion", 0.0)),
            custom={k: float(v) for k, v in (d.get("custom") or {}).items()},
        )


@dataclass
class RelationshipEdge:
    id: str
    from_character_id: str
    to_character_id: str
    type: RelationshipType = RelationshipType.OTHER
    state: RelationshipState = field(default_factory=RelationshipState)
    supporting_chunk_ids: List[str] = field(default_factory=list)
    symmetric: bool = False
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, edge_id: str, d: Dict[str, Any]) -> "RelationshipEdge":
        d = d or {}
        type_raw = str(d.get("type", "OTHER")).upper()
        try:
            rel_type = RelationshipType(type_raw)
        except ValueError:
            rel_type = RelationshipType.OTHER
        return cls(
            id=edge_id,
            from_character_id=str(d.get("from_character_id") or d.get("from", "")),
            to_character_id=str(d.get("to_character_id") or d.get("to", "")),
            type=rel_type,
            state=RelationshipState.from_dict(d.get("state")),
            supporting_chunk_ids=list(d.get("supporting_chunk_ids") or []),
            symmetric=bool(d.get("symmetric", False)),
            props=dict(d.get("props") or {}),
        )


@dataclass
class RelationshipGraph:
    edges: Dict[str, RelationshipEdge] = field(default_factory=dict)

    def get_edges_from(self, character_id: str) -> List[RelationshipEdge]:
        return [e for e in self.edges.values() if e.from_character_id == character_id]

    def get_edge(self, from_id: str, to_id: str) -> Optional[RelationshipEdge]:
        for e in self.edges.values():
            if e.from_character_id == from_id and e.to_character_id == to_id:
                return e
            if e.symmetric and e.from_character_id == to_id and e.to_character_id == from_id:
                return e
        return None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RelationshipGraph":
        d = d or {}
        raw_edges = d.get("edges") or {}
        # Support both dict-keyed and list-of-dicts with "id" field
        if isinstance(raw_edges, list):
            edges = {}
            for item in raw_edges:
                eid = str(item.get("id", f"edge_{len(edges)}"))
                edges[eid] = RelationshipEdge.from_dict(eid, item)
        else:
            edges = {
                eid: RelationshipEdge.from_dict(eid, edata)
                for eid, edata in raw_edges.items()
            }
        return cls(edges=edges)


# ---------------------------------------------------------------------------
# Objectives / WinConditions
# ---------------------------------------------------------------------------

class ObjectiveType(str, Enum):
    DISCOVER_FACT = "DISCOVER_FACT"
    REACH_LOCATION = "REACH_LOCATION"
    CONVINCE_CHARACTER = "CONVINCE_CHARACTER"
    ESCAPE = "ESCAPE"
    SURVIVE = "SURVIVE"
    CUSTOM = "CUSTOM"


class ObjectiveState(str, Enum):
    LOCKED = "LOCKED"
    ACTIVE = "ACTIVE"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class WinRule(str, Enum):
    ALL_OF = "ALL_OF"
    ANY_OF = "ANY_OF"
    SCORE_THRESHOLD = "SCORE_THRESHOLD"


@dataclass
class Objective:
    id: str
    title: str
    type: ObjectiveType = ObjectiveType.CUSTOM
    state: ObjectiveState = ObjectiveState.LOCKED
    required_chunk_ids: List[str] = field(default_factory=list)
    unlock_rules: UnlockRules = field(default_factory=UnlockRules)
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Objective":
        d = d or {}
        type_raw = str(d.get("type", "CUSTOM")).upper()
        state_raw = str(d.get("state", "LOCKED")).upper()
        try:
            obj_type = ObjectiveType(type_raw)
        except ValueError:
            obj_type = ObjectiveType.CUSTOM
        try:
            obj_state = ObjectiveState(state_raw)
        except ValueError:
            obj_state = ObjectiveState.LOCKED
        return cls(
            id=str(d.get("id", "")),
            title=str(d.get("title", "")),
            type=obj_type,
            state=obj_state,
            required_chunk_ids=list(d.get("required_chunk_ids") or []),
            unlock_rules=UnlockRules.from_dict(d.get("unlock_rules")),
            props=dict(d.get("props") or {}),
        )


@dataclass
class WinConditions:
    objectives: List[Objective] = field(default_factory=list)
    win_rule: WinRule = WinRule.ALL_OF
    props: Dict[str, Any] = field(default_factory=dict)

    def check_complete(self) -> bool:
        active_or_complete = [o for o in self.objectives if o.state != ObjectiveState.LOCKED]
        if not active_or_complete:
            return False
        if self.win_rule == WinRule.ALL_OF:
            return all(o.state == ObjectiveState.COMPLETE for o in active_or_complete)
        if self.win_rule == WinRule.ANY_OF:
            return any(o.state == ObjectiveState.COMPLETE for o in active_or_complete)
        return False

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WinConditions":
        d = d or {}
        rule_raw = str(d.get("win_rule", "ALL_OF")).upper()
        try:
            rule = WinRule(rule_raw)
        except ValueError:
            rule = WinRule.ALL_OF
        return cls(
            objectives=[Objective.from_dict(o) for o in (d.get("objectives") or [])],
            win_rule=rule,
            props=dict(d.get("props") or {}),
        )


# ---------------------------------------------------------------------------
# World model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeModel:
    start_minute: int = 0
    minute_label: str = "minutes_since_start"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TimeModel":
        d = d or {}
        return cls(
            start_minute=int(d.get("start_minute", 0)),
            minute_label=str(d.get("minute_label", "minutes_since_start")),
        )


@dataclass(frozen=True)
class CommunicationRules:
    allows_phone: bool = False
    allows_text: bool = False
    allows_broadcast: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CommunicationRules":
        d = d or {}
        return cls(
            allows_phone=bool(d.get("allows_phone", False)),
            allows_text=bool(d.get("allows_text", False)),
            allows_broadcast=bool(d.get("allows_broadcast", False)),
            extra=dict(d.get("extra") or {}),
        )


@dataclass(frozen=True)
class LocationModel:
    """Location with speaker binding for location-aware speaker resolution."""
    id: str
    name: str
    tags: List[str] = field(default_factory=list)
    description: str = ""
    comms: CommunicationRules = field(default_factory=CommunicationRules)
    props: Dict[str, Any] = field(default_factory=dict)
    default_present_character_ids: List[str] = field(default_factory=list)
    speaker_character_ids: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, loc_id: str, d: Dict[str, Any]) -> "LocationModel":
        d = d or {}
        speakers = d.get("speaker_character_ids") or []
        if isinstance(speakers, str):
            speakers = [speakers]
        return cls(
            id=loc_id,
            name=str(d.get("name", loc_id)),
            tags=list(d.get("tags") or []),
            description=str(d.get("description", "")),
            comms=CommunicationRules.from_dict(d.get("comms")),
            props=dict(d.get("props") or {}),
            default_present_character_ids=list(d.get("default_present_character_ids") or []),
            speaker_character_ids=list(speakers),
        )


@dataclass(frozen=True)
class MovementEdge:
    id: str
    from_location_id: str
    to_location_id: str
    minutes_cost: int = 1
    probability: float = 1.0
    tags: List[str] = field(default_factory=list)
    props: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, edge_id: str, d: Dict[str, Any]) -> "MovementEdge":
        d = d or {}
        return cls(
            id=edge_id,
            from_location_id=str(d.get("from_location_id") or d.get("from", "")),
            to_location_id=str(d.get("to_location_id") or d.get("to", "")),
            minutes_cost=max(1, int(d.get("minutes_cost") or d.get("minutes", 1))),
            probability=max(0.0, min(1.0, float(d.get("probability", 1.0)))),
            tags=list(d.get("tags") or []),
            props=dict(d.get("props") or {}),
        )


@dataclass
class MovementGraph:
    edges: Dict[str, MovementEdge] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "MovementGraph":
        d = d or {}
        raw = d.get("edges") or {}
        if isinstance(raw, list):
            edges = {}
            for i, item in enumerate(raw):
                eid = str(item.get("id", f"move_{i}"))
                edges[eid] = MovementEdge.from_dict(eid, item)
        else:
            edges = {
                eid: MovementEdge.from_dict(eid, edata)
                for eid, edata in raw.items()
            }
        return cls(edges=edges)


@dataclass
class WorldModel:
    time: TimeModel = field(default_factory=TimeModel)
    locations: Dict[str, LocationModel] = field(default_factory=dict)
    movement: MovementGraph = field(default_factory=MovementGraph)
    systems: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "WorldModel":
        d = d or {}
        raw_locs = d.get("locations") or {}
        locations = {
            lid: LocationModel.from_dict(lid, ldata)
            for lid, ldata in raw_locs.items()
        }
        return cls(
            time=TimeModel.from_dict(d.get("time")),
            locations=locations,
            movement=MovementGraph.from_dict(d.get("movement")),
            systems=dict(d.get("systems") or {}),
        )


# ---------------------------------------------------------------------------
# Game config (mode + policies)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExtractorSpec:
    id: str
    purpose: str
    output_keys: List[str] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)
    run_every_turn: bool = True

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ExtractorSpec":
        d = d or {}
        return cls(
            id=str(d.get("id", "")),
            purpose=str(d.get("purpose", "")),
            output_keys=list(d.get("output_keys") or []),
            params=dict(d.get("params") or {}),
            run_every_turn=bool(d.get("run_every_turn", True)),
        )


@dataclass(frozen=True)
class EnforcementPolicy:
    enable_invariant_validator: bool = True
    max_repair_attempts: int = 1
    invariant_types: List[str] = field(default_factory=lambda: [
        "ANCHOR_CONTRADICTION",
        "SPEAKER_IDENTITY_DRIFT",
    ])
    repair_strategy: str = "regen_with_constraints"

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EnforcementPolicy":
        d = d or {}
        return cls(
            enable_invariant_validator=bool(d.get("enable_invariant_validator", True)),
            max_repair_attempts=int(d.get("max_repair_attempts", 1)),
            invariant_types=list(d.get("invariant_types") or [
                "ANCHOR_CONTRADICTION", "SPEAKER_IDENTITY_DRIFT",
            ]),
            repair_strategy=str(d.get("repair_strategy", "regen_with_constraints")),
        )


@dataclass(frozen=True)
class TurnPolicy:
    time_advances_on_reply: bool = True
    min_minutes_per_turn: int = 1
    max_minutes_per_turn: int = 10
    extractors: List[ExtractorSpec] = field(default_factory=list)
    enforcement: EnforcementPolicy = field(default_factory=EnforcementPolicy)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TurnPolicy":
        d = d or {}
        return cls(
            time_advances_on_reply=bool(d.get("time_advances_on_reply", True)),
            min_minutes_per_turn=int(d.get("min_minutes_per_turn", 1)),
            max_minutes_per_turn=int(d.get("max_minutes_per_turn", 10)),
            extractors=[ExtractorSpec.from_dict(e) for e in (d.get("extractors") or [])],
            enforcement=EnforcementPolicy.from_dict(d.get("enforcement")),
        )


@dataclass(frozen=True)
class OutputPolicy:
    """Output formatting policy.

    ``allow_player_action_narration`` controls whether the AI may narrate
    player actions/emotions (e.g. "you lean forward").  Second-person
    indirect references ("your words") are always allowed — no separate
    toggle needed.
    """
    narration_style: str = "cinematic"
    allow_player_action_narration: bool = False
    required_sections: List[str] = field(default_factory=list)
    formatting: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "OutputPolicy":
        d = d or {}
        return cls(
            narration_style=str(d.get("narration_style", "cinematic")),
            allow_player_action_narration=bool(d.get("allow_player_action_narration", False)),
            required_sections=list(d.get("required_sections") or []),
            formatting=dict(d.get("formatting") or {}),
        )


@dataclass(frozen=True)
class GameConfig:
    mode: str = "freeform"
    turn_policy: TurnPolicy = field(default_factory=TurnPolicy)
    output_policy: OutputPolicy = field(default_factory=OutputPolicy)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GameConfig":
        d = d or {}
        return cls(
            mode=str(d.get("mode", "freeform")),
            turn_policy=TurnPolicy.from_dict(d.get("turn_policy")),
            output_policy=OutputPolicy.from_dict(d.get("output_policy")),
        )


# ---------------------------------------------------------------------------
# StoryPackage v2 (root)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Metadata:
    title: str = ""
    theme: str = ""
    disclaimer: str = ""
    tags: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Metadata":
        d = d or {}
        return cls(
            title=str(d.get("title", "")),
            theme=str(d.get("theme", "")),
            disclaimer=str(d.get("disclaimer", "")),
            tags=list(d.get("tags") or []),
            extra=dict(d.get("extra") or {}),
        )


@dataclass
class StoryPackageV2:
    story_id: str
    version: int
    meta: Metadata = field(default_factory=Metadata)
    game: GameConfig = field(default_factory=GameConfig)
    world: WorldModel = field(default_factory=WorldModel)
    characters: Dict[str, CharacterModel] = field(default_factory=dict)
    relationships: RelationshipGraph = field(default_factory=RelationshipGraph)
    knowledge: KnowledgeBase = field(default_factory=KnowledgeBase)
    win_conditions: WinConditions = field(default_factory=WinConditions)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StoryPackageV2":
        d = d or {}
        raw_chars = d.get("characters") or {}
        if isinstance(raw_chars, list):
            characters = {}
            for item in raw_chars:
                cid = str(item.get("id", f"char_{len(characters)}"))
                characters[cid] = CharacterModel.from_dict(cid, item)
        else:
            characters = {
                cid: CharacterModel.from_dict(cid, cdata)
                for cid, cdata in raw_chars.items()
            }
        return cls(
            story_id=str(d.get("story_id", "")),
            version=int(d.get("version", 2)),
            meta=Metadata.from_dict(d.get("meta")),
            game=GameConfig.from_dict(d.get("game")),
            world=WorldModel.from_dict(d.get("world")),
            characters=characters,
            relationships=RelationshipGraph.from_dict(d.get("relationships")),
            knowledge=KnowledgeBase.from_dict(d.get("knowledge")),
            win_conditions=WinConditions.from_dict(d.get("win_conditions")),
        )
