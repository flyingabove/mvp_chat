# app/engine/state.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.config.settings import (
    START_LOCATION,
    START_MINUTE,
    REL_START,
    EMOTION_START,
    REL_MIN,
    REL_MAX,
)
import json
import re


@dataclass
class UserState:
    """
    Holds information that comes directly from the user
    (or extractors that interpret user input).

    - formal_name: the real/full name IU believes is correct.
    - display_name: what IU actually calls the user in dialogue.
      (Initially empty; later can diverge from formal_name.)
    - gender: 'M' / 'F' / None (user-chosen).
    """
    formal_name: str = ""
    display_name: str = ""
    gender: Optional[str] = None


@dataclass
class CharacterState:
    """
    Generic character slot (used for IU and future characters).
    """
    key: str                     # internal key, e.g. "IU"
    name: str                    # display name, e.g. "IU"
    role: str = ""               # e.g. "ghost", "victim", etc.
    emotion: str = EMOTION_START
    relationship: int = REL_START


@dataclass
class MurderGameState:
    """
    Overall game state container for the murder / ghost story.

    NOTE:
    - We keep attributes roughly aligned with the old dict keys,
      but now strongly typed and grouped.
    - __getitem__/__setitem__ are implemented for backward compat.
    """
    story: Optional[str] = None
    gender: Optional[str] = None          # player-chosen gender ('M'/'F')
    turns: int = 0
    over: bool = False

    minute: int = START_MINUTE
    location: str = START_LOCATION
    evidence: List[str] = field(default_factory=list)

    iu_emotion: str = EMOTION_START
    relationship: int = REL_START

    # Story configuration (loaded JSON).
    story_cfg: Optional[dict] = None

    # Meta player name for narration / nametag, NOT necessarily
    # what IU is allowed to call the user out loud.
    player_name: Optional[str] = None

    # Structured sub-objects
    user: UserState = field(default_factory=UserState)
    characters: Dict[str, CharacterState] = field(default_factory=dict)
    main_character_id: Optional[str] = None  # e.g. "IU"

    # Language / style flags for this turn
    allow_casual_korean: bool = False
    casual_korean_used: List[str] = field(default_factory=list)
    
    # Name Settings:
    last_assistant_guess_name: str = ""

    # Backward-compat: allow dict-style access in older code.
    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    @property
    def main_character(self) -> Optional[CharacterState]:
        if self.main_character_id and self.main_character_id in self.characters:
            return self.characters[self.main_character_id]
        return None


def init_state() -> MurderGameState:
    """
    Factory for a fresh game state.
    """
    return MurderGameState()


def apply_state_tag(state: MurderGameState, tag: dict):
    """
    Apply [[STATE]] tag information coming back from the model.
    Expected format: {"iu_emotion":"...", "rel_delta":-1|0|1}
    """

    # Emotion update
    emotion = tag.get("iu_emotion")
    if isinstance(emotion, str):
        cleaned = emotion.strip() or EMOTION_START
        state.iu_emotion = cleaned
        if state.main_character:
            state.main_character.emotion = cleaned

    # Relationship delta (global + mirror to main_character)
    try:
        rel_delta = int(tag.get("rel_delta", 0))
    except (TypeError, ValueError):
        rel_delta = 0

    rel_delta = max(-1, min(1, rel_delta))
    new_rel = state.relationship + rel_delta
    state.relationship = max(REL_MIN, min(REL_MAX, new_rel))

    if state.main_character:
        state.main_character.relationship = state.relationship


def extract_state_tag(reply: str):
    """
    Extract and strip the [[STATE]]{...}[[/STATE]] tag from the model reply.
    Returns (clean_text, tag_dict_or_None).
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
