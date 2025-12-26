# app/engine/gameplay.py
import re
import math
from backend.app.config.settings import (
    MINS_PER_WORD,
    BASE_TURN_MINS,
    TRAVEL_MINS,
)


def word_count(s: str) -> int:
    s = " ".join(s.split())
    return len(s.split()) if s else 0


def sanitize_location(loc: str) -> str:
    loc = re.sub(r"<.*?>", "", loc)
    loc = re.sub(r"[\r\n]+", " ", loc)
    return loc.strip()


def manifest_mode(state) -> str:
    """
    Determines IU's manifestation state.
    Previously relied on dict.get(); now works with MurderGameState objects.
    """

    # Safe access to story_cfg
    cfg = getattr(state, "story_cfg", {}) or {}

    # Manifestation rules from story JSON
    manifest_rules = (
        cfg.get("rules", {})
           .get("manifestation", {})
           .get("apartment_location_contains", [
                "unit 302", "baeknam villa", "nonhyeon-dong",
                "officetel", "hakdong", "studio"
           ])
    )

    # Player location (string or None)
    loc = getattr(state, "location", "") or ""
    loc = loc.lower()

    inside = any(k.lower() in loc for k in manifest_rules)
    return "materialize" if inside else "whisper"


def advance_time(state, player_text: str):
    """
    Updates the state's minute counter based on message length and movement.
    Works with MurderGameState.
    """

    cfg = getattr(state, "story_cfg", {}) or {}

    per_word = float(cfg.get("time", {}).get("mins_per_word", MINS_PER_WORD))
    base = int(cfg.get("time", {}).get("base_turn_mins", BASE_TURN_MINS))
    travel = int(cfg.get("time", {}).get("travel_mins", TRAVEL_MINS))

    # Basic time progression
    delta = base + math.ceil(word_count(player_text) * per_word)

    # Movement detection
    m = re.search(r"\b(go|move)\s+to\s+(.{3,})", player_text, re.I)
    if m:
        place = sanitize_location(m.group(2))
        # state["location"] is invalid for dataclasses → use setattr
        setattr(state, "location", place)
        delta += travel

    # Update minute
    setattr(state, "minute", getattr(state, "minute", 0) + delta)


def confession_detected(text: str, state) -> bool:
    """
    Detects win conditions based on regex patterns from story config.
    Works with MurderGameState.
    """

    cfg = getattr(state, "story_cfg", {}) or {}

    patterns = cfg.get("win_detection", {}).get("regex", [
        r"\bi am (the )?mastermind\b",
        r"\bi (ordered|arranged|hired|paid).*(kill|murder)\b",
        r"\bit was me (who )?(planned|orchestrated)( it| the murder)\b",
        r"\bi told .* to do it\b",
        r"\bi made .* (kill|strangle) (her|him|them)\b",
    ])

    return any(re.search(p, text, re.I) for p in patterns)
