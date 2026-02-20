# app/engine/gameplay.py
import re
import math
from typing import Optional
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
    Determines the character's manifestation state based on story config rules.
    Works with MurderGameState objects.
    """

    # Safe access to story_cfg
    cfg = getattr(state, "story_cfg", {}) or {}

    # Manifestation rules from story JSON (empty list = always manifest)
    manifest_rules = (
        cfg.get("rules", {})
           .get("manifestation", {})
           .get("apartment_location_contains", [])
    )

    # Player location (string or None)
    loc = getattr(state, "location", "") or ""
    loc = loc.lower()

    # No rules defined = always materialize (safe default for new stories)
    if not manifest_rules:
        return "materialize"
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

    # If a world clock is active, keep it in sync with dialog time.
    runtime = getattr(state, "world_runtime", None)
    if runtime is not None:
        try:
            runtime.world_clock.advance(int(delta))
        except Exception:
            pass

    # Movement detection
    # Only treat movement as an explicit command when the *entire message*
    # is a movement instruction.
    # This prevents natural-language questions like "Can we go to ...?" from
    # incorrectly changing the player's location.
    m = re.match(r"^\s*(go|move)\s+to\s+(.{3,}?)\s*$", player_text, re.I)
    if m:
        place = sanitize_location(m.group(2))

        # Prefer authoritative world graph travel when available.
        if runtime is not None and getattr(state, "location_id", ""):
            dest_id = _resolve_destination_id(runtime.world_graph, place)
            if dest_id:
                try:
                    exposure = runtime.travel_resolver.resolve(state.location_id, dest_id)
                    state.last_travel_from_id = state.location_id
                    state.last_travel_to_id = dest_id
                    state.last_travel_exposure = exposure

                    state.location_id = dest_id
                    # Human-readable location string for UI + manifestation heuristics.
                    try:
                        dest_loc = runtime.world_graph.get_location(dest_id)
                        state.location = dest_loc.name
                        state.location_uuid = getattr(dest_loc, "uuid", "")
                        try:
                            state.last_travel_from_uuid = getattr(runtime.world_graph.get_location(state.last_travel_from_id), "uuid", "")
                        except Exception:
                            state.last_travel_from_uuid = ""
                        state.last_travel_to_uuid = getattr(dest_loc, "uuid", "")
                    except Exception:
                        state.location = place
                        state.location_uuid = ""

                    # Sync state.minute from world clock (authoritative)
                    state.minute = runtime.world_clock.minute
                    # Location-scoped transient scene details do not persist across travel.
                    try:
                        state.clear_location_transient_entries()
                    except Exception:
                        pass
                    return
                except Exception:
                    # Travel resolution failed (no route, invalid locations, etc.)
                    # Fall through to legacy location update behavior below
                    pass

        # If a world graph is active but we can't resolve the destination,
        # do NOT change location from arbitrary free-text.
        if runtime is not None:
            pass
        else:
            # Fallback: legacy free-text location
            setattr(state, "location", place)
            delta += travel
            try:
                state.clear_location_transient_entries()
            except Exception:
                pass

    # Update minute (legacy path)
    setattr(state, "minute", getattr(state, "minute", 0) + delta)


def _normalize_token(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _resolve_destination_id(world_graph, place: str) -> Optional[str]:
    """Resolve a user-provided place string to a known location id."""
    want = _normalize_token(place)
    if not want:
        return None

    # Exact id match (normalized)
    for loc_id in getattr(world_graph, "locations", {}).keys():
        if _normalize_token(loc_id) == want:
            return loc_id

    # Name match
    for loc_id, loc in getattr(world_graph, "locations", {}).items():
        if _normalize_token(getattr(loc, "name", "")) == want:
            return loc_id

    return None


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
