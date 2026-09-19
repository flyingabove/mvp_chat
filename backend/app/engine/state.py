# app/engine/state.py
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.config.settings import (
    START_LOCATION,
    START_MINUTE,
    REL_START,
    EMOTION_START,
    REL_MIN,
    REL_MAX,
    DEFAULT_USER_ID,
    DEFAULT_INSTANCE,
    TRANSIENT_KNOWLEDGE_TURNS,
)

from backend.app.engine.character_graph import CharacterGraph, CharacterType
from backend.app.engine.cast_lifecycle import CastLifecycleState
from backend.app.engine.epistemic_state import BeliefState
from backend.app.engine.knowledge_chunks import KnowledgeChunk
from backend.app.engine.transient_buffer import TransientKnowledge, prune_expired
from backend.app.engine.transient_buffer import (
    SceneKnowledge,
    latest_scene_knowledge,
    upsert_scene_knowledge_fifo,
)
from backend.app.config.epistemic_flags import (
    belief_enabled,
    truth_enabled,
)

import json
import re


# ======================================================================
# USER STATE
# ======================================================================

@dataclass
class UserState:
    """
    Stores all known information about the human player as perceived in-story.

    - formal_name:
        The user's real/full name the character believes is correct.
        Extracted only if the character explicitly learns it (e.g., user tells them).
        This is NOT used automatically for addressing the user.

    - display_name:
        What the character actually calls the user in dialogue.
        Starts empty until learned or chosen.
        Later, user can override this ("Call me Chris").

    - gender:
        'M' or 'F' chosen by user at newgame time.
    """
    formal_name: str = ""
    display_name: str = ""
    gender: Optional[str] = None


# ======================================================================
# CHARACTER (merged from StoryCharacter + CharacterState)
# ======================================================================

@dataclass
class Character:
    """
    Single unified character object — authoring-time identity fields and
    runtime state merged into one class.

    Authoring fields (from story JSON):
    - key: internal ID, e.g. "iu"
    - name: display name, e.g. "IU"
    - role: story role, e.g. "ghost", "ally", "antagonist"
    - is_main: the focal NPC of the session
    - is_suspect: flagged as a story suspect
    - knowledge_character_id: FAISS/BM25 index bundle directory
    - uuid: deterministic UUID for logging/tracing
    - tags: optional category labels (e.g. ["idol", "ghost"])
    - meta: forward-compat bucket for unknown JSON keys
    - self_knowledge: first-person identity facts injected directly into prompt

    Runtime state (set at game init / updated during play):
    - emotion: current emotional descriptor ("wary", "cold", "soft")
    - relationship: relationship metric with player
    """
    key: str
    name: str
    role: str = ""
    character_type: CharacterType = CharacterType.CANONICAL
    is_main: bool = False
    is_suspect: bool = False
    knowledge_character_id: str = ""
    uuid: str = ""
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)
    self_knowledge: List[str] = field(default_factory=list)
    emotion: str = EMOTION_START
    relationship: int = REL_START

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Character":
        data = data or {}
        key = str(data.get("key") or data.get("id") or data.get("name") or "character").strip() or "character"
        name = str(data.get("name") or key).strip() or key
        role = str(data.get("role") or "").strip()
        is_main = bool(data.get("is_main"))
        is_suspect = bool(data.get("is_suspect") or data.get("suspect"))
        knowledge_character_id = str(data.get("knowledge_character_id") or "").strip()
        uuid = str(data.get("uuid") or "").strip()
        tags = list(data.get("tags") or [])
        self_knowledge = [str(x) for x in (data.get("self_knowledge") or []) if str(x).strip()]
        # Determine character_type: is_main → MAIN; else parse from JSON or default CANONICAL
        if is_main:
            character_type = CharacterType.MAIN
        else:
            type_raw = str(data.get("character_type") or "").strip().lower()
            try:
                character_type = CharacterType(type_raw)
            except ValueError:
                character_type = CharacterType.CANONICAL
        known_keys = {
            "key", "id", "name", "role", "is_main", "is_suspect", "suspect",
            "knowledge_character_id", "uuid", "tags", "character_type", "self_knowledge",
        }
        meta = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            key=key,
            name=name,
            role=role,
            character_type=character_type,
            is_main=is_main,
            is_suspect=is_suspect,
            knowledge_character_id=knowledge_character_id,
            uuid=uuid,
            tags=tags,
            meta=meta,
            self_knowledge=self_knowledge,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "role": self.role,
            "character_type": self.character_type.value,
            "is_main": self.is_main,
            "is_suspect": self.is_suspect,
            "knowledge_character_id": self.knowledge_character_id,
            "uuid": self.uuid,
            "tags": self.tags,
            "self_knowledge": self.self_knowledge,
            **(self.meta or {}),
        }


def make_player_character(display_name: str = "Player") -> Character:
    """Create the USER-type Character node representing the human player.

    Always uses key="player" so relationship edges authored in story JSON
    that target "player" resolve correctly.  Call once at game init and store
    in GameState.characters["player"] and CharacterGraph.characters["player"].
    """
    return Character(
        key="player",
        name=display_name,
        character_type=CharacterType.USER,
        role="player",
    )


# Backward-compat alias (deprecated — use Character directly)
CharacterState = Character


# ======================================================================
# GAME STATE (main container)
# ======================================================================

@dataclass
class GameState:
    """
    Main state container for the entire game session.

    Generic and story-type agnostic: supports multiple characters,
    dynamic memory, epistemic layers, world graphs, etc.
    """
    # ==============================================================
    # Basic session progression
    # Note: turns can alternatively be derived from len(log)//2, but
    # keeping explicit counter for clarity and "first turn" detection.
    # ==============================================================
    story: Optional[str] = None
    user_id: str = DEFAULT_USER_ID
    instance: int = DEFAULT_INSTANCE
    gender: Optional[str] = None
    turns: int = 0
    over: bool = False

    # ==============================================================
    # Time & location
    # ==============================================================
    minute: int = START_MINUTE
    location: str = START_LOCATION

    # ==============================================================
    # Emotion & relationship
    # ==============================================================
    emotion: str = EMOTION_START
    relationship: int = REL_START

    # Knowledge retrieval routing (character index bundle id/dirname)
    knowledge_character_id: str = ""

    # Chunk IDs from chunks.jsonl visible to the player at game start.
    # Populated by _seed_player_visibility() in prompt_engine._cmd_newgame.
    # Defaults to all chunks if empty (no filtering applied).
    # Story designers can mark specific chunks hidden via "player_visible": false in chunks.jsonl.
    player_visible_chunk_ids: List[str] = field(default_factory=list)

    # ==============================================================
    # Story metadata
    # ==============================================================
    # StoryDefinition (preferred) or plain dict for legacy/tests
    story_cfg: Optional[Any] = None

    # Meta “nametag” name — not what the character necessarily says in dialogue.
    player_name: Optional[str] = None

    # ==============================================================
    # Structured objects
    # ==============================================================
    user: UserState = field(default_factory=UserState)
    characters: Dict[str, Character] = field(default_factory=dict)
    main_character_id: Optional[str] = None

    # ==============================================================
    # Epistemic structures
    # ==============================================================
    canonical_facts: List[KnowledgeChunk] = field(default_factory=list)
    canonical_truth: List[str] = field(default_factory=list)
    epistemic_log: List[KnowledgeChunk] = field(default_factory=list)
    observation_log: List[KnowledgeChunk] = field(default_factory=list)
    beliefs: Dict[str, BeliefState] = field(default_factory=dict)

    # ==============================================================
    # Character relationship graph (multi-dimensional)
    # ==============================================================
    character_graph: Optional[CharacterGraph] = None

    # Optional authored/runtime cast rotation state. Stories that do not opt in
    # leave this as None and retain the legacy all-characters-active behavior.
    cast_lifecycle: Optional[CastLifecycleState] = None

    # ==============================================================
    # Transient scene buffer (non-authoritative, short-lived)
    # ==============================================================
    transient_entries: List[TransientKnowledge] = field(default_factory=list)
    scene_knowledge_entries: List[SceneKnowledge] = field(default_factory=list)

    # ==============================================================
    # Optional world runtime (graph-based movement)
    # ==============================================================
    world_runtime: Optional[object] = None
    location_id: str = ""
    location_uuid: str = ""

    # ==============================================================
    # Character location tracking
    # Maps character key -> current location_id.
    # Seeded at game start from world.character_start_locations.
    # Update this dict whenever a character moves during gameplay.
    # ==============================================================
    character_locations: Dict[str, str] = field(default_factory=dict)
    world_start_datetime: str = ""
    last_travel_from_id: str = ""
    last_travel_to_id: str = ""
    last_travel_from_uuid: str = ""
    last_travel_to_uuid: str = ""
    last_travel_exposure: Optional[object] = None

    # ==============================================================
    # Korean usage controls
    # ==============================================================
    casual_korean_used: List[str] = field(default_factory=list)

    # ==============================================================
    # Name extraction / learning helpers
    # ==============================================================
    last_assistant_guess_name: str = ""

    # ==============================================================
    # Single-call turn extractor carryover context
    # ==============================================================
    last_turn_user_msg: str = ""
    last_turn_assistant_reply: str = ""
    last_turn_retrieved_chunks: List[Dict[str, Any]] = field(default_factory=list)

    # ==============================================================
    # Session-level dialogue fact store (not serialized to state_json)
    # Holds facts extracted from user/AI messages via dialogue_extractor.
    # chunk IDs: usr-{msg_id}-{n} / ai-{msg_id}-{n}
    # ==============================================================
    session_chunk_store: Any = field(default=None)

    # ==============================================================
    # BACKWARD COMPAT (deprecated - use direct attribute access instead)
    # ==============================================================
    def __getitem__(self, key):
        """Deprecated: use direct attribute access (state.field) instead."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Deprecated: use direct attribute access (state.field = value) instead."""
        setattr(self, key, value)

    @property
    def main_character(self) -> Optional[Character]:
        """Convenience accessor for the primary NPC."""
        if self.main_character_id and self.main_character_id in self.characters:
            return self.characters[self.main_character_id]
        return None

    def get_belief_state(self, character_id: str) -> BeliefState:
        """Fetch (or create) the belief log for a given character."""
        if not belief_enabled():
            # Return empty stub without mutating shared beliefs when disabled
            return BeliefState(character_id=character_id)
        if character_id not in self.beliefs:
            self.beliefs[character_id] = BeliefState(character_id=character_id)
        return self.beliefs[character_id]

    def record_observation(self, **kwargs) -> KnowledgeChunk:
        """Append an observation to the shared observation log."""
        if "kind" not in kwargs:
            kwargs["kind"] = "observation"
        obs = KnowledgeChunk(**kwargs)
        if belief_enabled():
            self.observation_log.append(obs)
        return obs

    # ==============================================================
    # Epistemic helpers (toggle-aware)
    # ==============================================================
    def add_canonical_fact(self, fact: KnowledgeChunk) -> None:
        """Append to canonical facts if truth layer is enabled."""
        if truth_enabled():
            self.canonical_facts.append(fact)

    def add_epistemic_claims(self, *claims: KnowledgeChunk) -> None:
        """Append claims to epistemic log if belief layer is enabled."""
        if belief_enabled():
            self.epistemic_log.extend(claims)

    # ==============================================================
    # Transient buffer helpers
    # ==============================================================
    def add_transient_entry(
        self,
        *,
        id: str,
        namespace: str,
        scope: str,
        text: str,
        expires_after_turns: int | None = TRANSIENT_KNOWLEDGE_TURNS,
        expires_after_minutes: int | None = None,
        promotable: bool = False,
        meta: Optional[Dict[str, str]] = None,
    ) -> None:
        if not text or not text.strip():
            return
        # Use caller-provided TTL if given; fall back to the system default.
        ttl = int(expires_after_turns) if expires_after_turns is not None else TRANSIENT_KNOWLEDGE_TURNS
        self.transient_entries.append(
            TransientKnowledge(text=text.strip(), turns_remaining=ttl)
        )

    def purge_transient_entries(self) -> None:
        self.transient_entries = prune_expired(
            self.transient_entries,
            current_turn=int(self.turns),
            current_minute=int(self.minute),
        )

    def clear_location_transient_entries(self) -> None:
        """Remove location-scoped transient entries on travel.

        Clears all scene context accumulated at the previous location so it
        does not bleed into the next scene.  Only conversation-wide markers
        (e.g., on-call phone markers) are preserved.  Active-character markers
        are intentionally cleared here because they are re-injected at the
        start of every turn by _upsert_active_character_markers.
        """
        _PERSISTENT_PREFIXES = ("__on_call_character_marker__:",)
        self.transient_entries = [
            e for e in self.transient_entries
            if any((getattr(e, "text", "") or "").startswith(p) for p in _PERSISTENT_PREFIXES)
        ]

    def clear_all_transient_entries(self) -> None:
        self.transient_entries = []
        self.scene_knowledge_entries = []

    def upsert_scene_knowledge(
        self,
        *,
        key: str,
        location_id: str,
        speakers: List[str],
        people_present: List[str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        item = SceneKnowledge(
            key=str(key or "").strip() or "scene",
            location_id=str(location_id or "").strip(),
            speakers=[str(s or "").strip().lower() for s in (speakers or []) if str(s or "").strip()],
            people_present=[str(p or "").strip().lower() for p in (people_present or []) if str(p or "").strip()],
            payload=dict(payload or {}),
        )
        self.scene_knowledge_entries = upsert_scene_knowledge_fifo(
            self.scene_knowledge_entries,
            item=item,
            max_items=TRANSIENT_KNOWLEDGE_TURNS,
        )

    def latest_scene_knowledge(self) -> SceneKnowledge | None:
        return latest_scene_knowledge(self.scene_knowledge_entries)


# ======================================================================
# FACTORY
# ======================================================================

def init_state() -> GameState:
    """
    Create a brand-new game state with all defaults.
    """
    return GameState()


# ======================================================================
# STATE TAG APPLICATION
# ======================================================================

def apply_state_tag(state: GameState, tag: dict):
    """
    Apply [[STATE]] tag returned by the model.

    Format expected: {"emotion":"...", "rel_delta": -1|0|1}
    """

    # -----------------------
    # Emotion sync
    # -----------------------
    # Accept neutral key "emotion", legacy "emotion", or any "<name>_emotion" key.
    emotion = tag.get("emotion")
    if emotion is None:
        for k, v in tag.items():
            if isinstance(k, str) and k.endswith("_emotion") and isinstance(v, str):
                emotion = v
                break
    if isinstance(emotion, str):
        cleaned = emotion.strip() or EMOTION_START
        state.emotion = cleaned
        if state.main_character:
            state.main_character.emotion = cleaned

    # -----------------------
    # Relationship update
    # -----------------------
    try:
        rel_delta = int(tag.get("rel_delta", 0))
    except (ValueError, TypeError):
        rel_delta = 0

    rel_delta = max(-1, min(1, rel_delta))
    new_rel = state.relationship + rel_delta

    state.relationship = max(REL_MIN, min(REL_MAX, new_rel))

    if state.main_character:
        state.main_character.relationship = state.relationship

    # Route through character graph (maps rel_delta to affection)
    if state.character_graph and state.main_character_id and rel_delta != 0:
        state.character_graph.apply_rel_delta(
            state.main_character_id, "player", rel_delta
        )


# ======================================================================
# TAG EXTRACTION
# ======================================================================

def extract_state_tag(reply: str):
    """
    Extract and remove:  [[STATE]]{...}[[/STATE]]

    Returns:
        (clean_text, dict or None)
    """
    # Use `.*?` (not `\{.*?\}`) so the capture boundary is the [[/STATE]]
    # delimiter rather than the first closing brace.  This correctly handles
    # STATE payloads that contain nested JSON objects.
    m = re.search(r"\[\[STATE\]\](.*?)\[\[/STATE\]\]", reply, re.S)
    if not m:
        return reply, None

    try:
        tag = json.loads(m.group(1))
    except Exception:
        return reply, None

    clean = reply.replace(m.group(0), "").strip()
    return clean, tag


# Backward-compat alias (deprecated — use GameState directly)
MurderGameState = GameState
