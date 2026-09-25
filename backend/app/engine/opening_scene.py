"""Engine-backed opening scene: who physically greets the player at game start.

A story may author ``opening.welcome_party`` to decide which NPCs are in the
player's starting location when the game begins::

    "opening": {
      "welcome_party": {"size": 2, "gender": "opposite_player", "exclusive": true}
    }

- ``size``: how many NPCs greet the player (default 2).
- ``gender``: ``any`` | ``opposite_player`` | ``same_as_player`` | ``M`` | ``F``.
  Character gender comes from the authored ``gender`` field ("M"/"F") on each
  character. If too few candidates match, the party is filled from the rest
  so the opening never loses its greeters.
- ``exclusive``: move every other NPC out of the player's start location, so
  the people present are exactly the welcome party (default true).
- ``fallback_location_id``: where displaced NPCs go (default: the story's
  ``cast_lifecycle.initial_active_location_id``). If that is the start room
  itself, nobody is displaced - NPCs are never left without a location.

Staging writes real engine state — ``character_locations``, the focal
``main_character_id`` and ``opening_cast`` — so the opening prose, the SCENE
BRIEF's people-present list and the first storyteller reply all describe the
same room. Stories without ``welcome_party`` keep their previous behavior.
"""
from __future__ import annotations

import random
import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Optional

if TYPE_CHECKING:
    from backend.app.engine.state import GameState

GENDER_RULES = {"any", "opposite_player", "same_as_player", "M", "F"}


@dataclass(frozen=True)
class WelcomePartyRule:
    size: int = 2
    gender: str = "any"
    exclusive: bool = True
    fallback_location_id: str = ""

    @classmethod
    def from_config(cls, cfg: Any) -> Optional["WelcomePartyRule"]:
        """Parse ``opening.welcome_party``; None when the story doesn't author one."""
        if not isinstance(cfg, Mapping):
            return None
        gender = str(cfg.get("gender") or "any").strip()
        if gender.upper() in {"M", "F"}:
            gender = gender.upper()
        if gender not in GENDER_RULES:
            raise ValueError(f"opening.welcome_party.gender must be one of {sorted(GENDER_RULES)}, got {gender!r}")
        size = int(cfg.get("size", 2))
        if size < 1:
            raise ValueError("opening.welcome_party.size must be >= 1")
        return cls(
            size=size,
            gender=gender,
            exclusive=bool(cfg.get("exclusive", True)),
            fallback_location_id=str(cfg.get("fallback_location_id") or "").strip(),
        )

    def wanted_gender(self, player_gender: Optional[str]) -> Optional[str]:
        """The NPC gender this rule prefers for a player, or None for no preference."""
        player = normalize_gender(player_gender)
        if self.gender in {"M", "F"}:
            return self.gender
        if self.gender == "any" or player is None:
            return None
        if self.gender == "same_as_player":
            return player
        return "F" if player == "M" else "M"


def normalize_gender(value: Any) -> Optional[str]:
    text = str(value or "").strip().upper()
    if text in {"M", "MALE", "MAN"}:
        return "M"
    if text in {"F", "FEMALE", "WOMAN"}:
        return "F"
    return None


def character_gender(character: Any) -> Optional[str]:
    """Authored gender of a Character ("M"/"F"), stored in its JSON ``gender`` key."""
    if character is None:
        return None
    direct = getattr(character, "gender", None)
    if direct:
        return normalize_gender(direct)
    meta = getattr(character, "meta", None) or {}
    return normalize_gender(meta.get("gender"))


def choose_welcome_party(
    candidates: Iterable[str],
    genders: Mapping[str, Optional[str]],
    player_gender: Optional[str],
    rule: WelcomePartyRule,
    rng: Optional[random.Random] = None,
) -> list[str]:
    """Pick ``rule.size`` greeters, preferring the rule's gender, in random order."""
    rng = rng or secrets.SystemRandom()
    pool = [key for key in dict.fromkeys(candidates) if key and key != "player"]
    wanted = rule.wanted_gender(player_gender)
    preferred = [key for key in pool if wanted is None or genders.get(key) == wanted]
    others = [key for key in pool if key not in preferred]
    chosen = rng.sample(preferred, min(rule.size, len(preferred)))
    if len(chosen) < rule.size:
        chosen += rng.sample(others, min(rule.size - len(chosen), len(others)))
    return chosen


def stage_opening_scene(state: "GameState", rng: Optional[random.Random] = None) -> list[str]:
    """Apply the story's welcome party to a freshly created game state.

    Returns the chosen greeter keys (also stored on ``state.opening_cast``);
    an empty list when the story authors no welcome party.
    """
    story_cfg = getattr(state, "story_cfg", None) or {}
    rule = WelcomePartyRule.from_config((story_cfg.get("opening") or {}).get("welcome_party"))
    if rule is None:
        return []
    characters = getattr(state, "characters", None) or {}
    lifecycle = getattr(state, "cast_lifecycle", None)
    candidates = list(lifecycle.active_ids()) if lifecycle else [k for k in characters if k != "player"]
    party = choose_welcome_party(
        candidates,
        {key: character_gender(characters.get(key)) for key in candidates},
        getattr(state, "gender", None),
        rule,
        rng,
    )
    start = str(getattr(state, "location_id", "") or "")
    if start:
        locations = dict(getattr(state, "character_locations", None) or {})
        fallback = rule.fallback_location_id or str(
            (story_cfg.get("cast_lifecycle") or {}).get("initial_active_location_id") or ""
        )
        # Without a distinct room to send them to, others stay put: an
        # untracked resident would make whereabouts unanswerable.
        if rule.exclusive and fallback and fallback != start:
            for key, location in list(locations.items()):
                if key != "player" and key not in party and location == start:
                    locations[key] = fallback
        for key in party:
            locations[key] = start
        state.character_locations = locations
    if party:
        # The focal lens must be someone actually in the room.
        state.main_character_id = party[0]
    state.opening_cast = list(party)
    return party


def opening_scene_brief(state: "GameState") -> str:
    """First-reply guidance so the storyteller continues the staged welcome."""
    party = [key for key in (getattr(state, "opening_cast", None) or []) if key]
    if not party or int(getattr(state, "turns", 0) or 0) != 0:
        return ""
    characters = getattr(state, "characters", None) or {}
    names = [(getattr(characters.get(key), "name", None) or key).strip() for key in party]
    who = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
    return (
        f"Opening scene: {who} just greeted the player as the story opened, and they are "
        "the characters with the player right now. Continue this first conversation with "
        "them; everyone else is elsewhere and should only appear if someone actually goes "
        "to them or they plausibly walk in.\n\n"
    )
