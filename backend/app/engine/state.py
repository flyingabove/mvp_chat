# app/engine/state.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from backend.app.config.settings import (
    START_LOCATION,
    START_MINUTE,
    REL_START,
    EMOTION_START,
    REL_MIN,
    REL_MAX,
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
    - name: human-friendly name ("Yuna")
    - role: "ghost", "victim", "suspect", etc.
    - emotion: emotional descriptor ("wary", "cold", "soft")
    - relationship: relationship metric with player
    """
    key: str
    name: str
    role: str = ""
    emotion: str = EMOTION_START
    relationship: int = REL_START


# ======================================================================
# GAME STATE (main container)
# ======================================================================

@dataclass
class MurderGameState:
    """
    Main state container for the entire game session.

    Replaces the old dict-based state. This class is future-proof:
    new story types, multiple characters, dynamic memory, etc.
    """
    # ==============================================================
    # Basic session progression
    # ==============================================================
    story: Optional[str] = None
    gender: Optional[str] = None
    turns: int = 0
    over: bool = False

    # ==============================================================
    # Time & location
    # ==============================================================
    minute: int = START_MINUTE
    location: str = START_LOCATION

    # ==============================================================
    # Evidence (unused but future-ready)
    # ==============================================================
    evidence: List[str] = field(default_factory=list)

    # ==============================================================
    # Emotion & relationship
    # ==============================================================
    iu_emotion: str = EMOTION_START
    relationship: int = REL_START

    # Knowledge retrieval routing (character index bundle id/dirname)
    knowledge_character_id: str = ""

    # ==============================================================
    # Story metadata
    # ==============================================================
    story_cfg: Optional[dict] = None

    # Meta “nametag” name — not what the character necessarily says in dialogue.
    player_name: Optional[str] = None

    # ==============================================================
    # Structured objects
    # ==============================================================
    user: UserState = field(default_factory=UserState)
    characters: Dict[str, CharacterState] = field(default_factory=dict)
    main_character_id: Optional[str] = None

    # ==============================================================
    # Optional world runtime (graph-based movement)
    # ==============================================================
    world_runtime: Optional[object] = None
    location_id: str = ""
    world_start_datetime: str = ""
    last_travel_from_id: str = ""
    last_travel_to_id: str = ""
    last_travel_exposure: Optional[object] = None

    # ==============================================================
    # Korean usage controls
    # ==============================================================
    allow_casual_korean: bool = False
    casual_korean_used: List[str] = field(default_factory=list)

    # ==============================================================
    # Name extraction / learning helpers
    # ==============================================================
    last_assistant_guess_name: str = ""

    # ==============================================================
    # BACKWARD COMPAT
    # ==============================================================
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    @property
    def main_character(self) -> Optional[CharacterState]:
        """Convenience accessor for the primary NPC."""
        if self.main_character_id and self.main_character_id in self.characters:
            return self.characters[self.main_character_id]
        return None


# ======================================================================
# FACTORY
# ======================================================================

def init_state() -> MurderGameState:
    """
    Create a brand-new game state with all defaults.
    """
    return MurderGameState()


# ======================================================================
# STATE TAG APPLICATION
# ======================================================================

def apply_state_tag(state: MurderGameState, tag: dict):
    """
    Apply [[STATE]] tag returned by the model.

    Format expected: {"emotion":"...", "rel_delta": -1|0|1}
    """

    # -----------------------
    # Emotion sync
    # -----------------------
    # Accept neutral key "emotion", legacy "iu_emotion", or any "<name>_emotion" key.
    emotion = tag.get("emotion")
    if emotion is None:
        emotion = tag.get("iu_emotion")
    if emotion is None:
        for k, v in tag.items():
            if isinstance(k, str) and k.endswith("_emotion") and isinstance(v, str):
                emotion = v
                break
    if isinstance(emotion, str):
        cleaned = emotion.strip() or EMOTION_START
        state.iu_emotion = cleaned
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


# ======================================================================
# TAG EXTRACTION
# ======================================================================

def extract_state_tag(reply: str):
    """
    Extract and remove:  [[STATE]]{...}[[/STATE]]

    Returns:
        (clean_text, dict or None)
    """
    m = re.search(r"\[\[STATE\]\](\{.*?\})\[\[/STATE\]\]", reply, re.S)
    if not m:
        return reply, None

    try:
        tag = json.loads(m.group(1))
    except Exception:
        return reply, None

    clean = reply.replace(m.group(0), "").strip()
    return clean, tag
