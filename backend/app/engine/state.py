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

from backend.app.engine.character_graph import CharacterGraph
from backend.app.engine.epistemic_state import (
    BeliefState,
    EpistemicClaim,
    EpistemicFact,
    Observation,
)
from backend.app.engine.transient_buffer import TransientKnowledge, prune_expired
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
# CHARACTER STATE
# ======================================================================

@dataclass
class CharacterState:
    """
    Represents any character in the story world.

    - key: internal ID, e.g. "main"
    - name: human-friendly name e.g. ("Danny")
    - role: "ghost", "victim", "suspect", etc.
    - emotion: emotional descriptor ("wary", "cold", "soft")
    - relationship: relationship metric with player
    """
    key: str
    name: str
    role: str = ""
    emotion: str = EMOTION_START
    relationship: int = REL_START
    uuid: str = ""


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
    characters: Dict[str, CharacterState] = field(default_factory=dict)
    main_character_id: Optional[str] = None

    # ==============================================================
    # Epistemic structures
    # ==============================================================
    canonical_facts: List[EpistemicFact] = field(default_factory=list)
    canonical_truth: List[str] = field(default_factory=list)
    epistemic_log: List[EpistemicClaim] = field(default_factory=list)
    observation_log: List[Observation] = field(default_factory=list)
    beliefs: Dict[str, BeliefState] = field(default_factory=dict)

    # ==============================================================
    # Character relationship graph (multi-dimensional)
    # ==============================================================
    character_graph: Optional[CharacterGraph] = None

    # ==============================================================
    # Transient scene buffer (non-authoritative, short-lived)
    # ==============================================================
    transient_entries: List[TransientKnowledge] = field(default_factory=list)

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
    # BACKWARD COMPAT (deprecated - use direct attribute access instead)
    # ==============================================================
    def __getitem__(self, key):
        """Deprecated: use direct attribute access (state.field) instead."""
        return getattr(self, key)

    def __setitem__(self, key, value):
        """Deprecated: use direct attribute access (state.field = value) instead."""
        setattr(self, key, value)

    @property
    def main_character(self) -> Optional[CharacterState]:
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

    def record_observation(self, **kwargs) -> Observation:
        """Append an observation to the shared observation log."""
        obs = Observation(**kwargs)
        if belief_enabled():
            self.observation_log.append(obs)
        return obs

    # ==============================================================
    # Epistemic helpers (toggle-aware)
    # ==============================================================
    def add_canonical_fact(self, fact: EpistemicFact) -> None:
        """Append to canonical facts if truth layer is enabled."""
        if truth_enabled():
            self.canonical_facts.append(fact)

    def add_epistemic_claims(self, *claims: EpistemicClaim) -> None:
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
