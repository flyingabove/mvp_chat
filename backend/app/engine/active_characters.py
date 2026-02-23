"""Detect which characters are contextually relevant based on string matching.

No LLM calls -- pure string matching against character names and keys.
Used to filter the character graph and character extras in the prompt
so only relevant data is included.
"""
from __future__ import annotations

from typing import Dict, Set

from backend.app.engine.state import GameState, CharacterState


def detect_mentioned_characters(
    text: str,
    characters: Dict[str, CharacterState],
    main_character_id: str = "",
) -> Set[str]:
    """Scan *text* for mentions of any character by key or display name.

    Always includes ``main_character_id`` and ``"player"`` in the returned set.

    Matching rules (case-insensitive):
    - Exact character key (e.g. ``yoo_min_ho``)
    - Key with underscores replaced by spaces (``yoo min ho``)
    - Full display name (``Yoo Min-ho``)
    - Individual name tokens >= 3 characters (``min-ho`` → ``min``, ``ho`` skipped)
    """
    active: Set[str] = set()

    if main_character_id:
        active.add(main_character_id)
    active.add("player")

    if not text.strip():
        return active

    text_lower = text.lower()

    for key, char in characters.items():
        if key in active:
            continue

        key_lower = key.lower()
        key_spaced = key_lower.replace("_", " ")

        if key_lower in text_lower or key_spaced in text_lower:
            active.add(key)
            continue

        name = (getattr(char, "name", "") or "").strip()
        if not name:
            continue

        name_lower = name.lower()
        if name_lower in text_lower:
            active.add(key)
            continue

        # Match individual name tokens (>= 3 chars to avoid false positives)
        tokens = name_lower.replace("-", " ").split()
        for token in tokens:
            if len(token) >= 3 and token in text_lower:
                active.add(key)
                break

    return active


def get_location_speaker_keys(state: GameState) -> Set[str]:
    """Return character keys designated as speakers at the current location.

    Reads ``story_cfg.world.location_speakers[location_id]`` and maps
    speaker display names back to character keys.
    """
    keys: Set[str] = set()

    cfg = getattr(state, "story_cfg", None)
    if cfg is None:
        return keys
    if hasattr(cfg, "as_dict"):
        cfg = cfg.as_dict()
    if not isinstance(cfg, dict):
        return keys

    world_cfg = cfg.get("world", {}) or {}
    loc_speakers = world_cfg.get("location_speakers") or {}
    loc_id = getattr(state, "location_id", "") or ""

    if not loc_speakers or not loc_id:
        return keys

    mapping = loc_speakers.get(loc_id)
    if not mapping:
        return keys

    if isinstance(mapping, str):
        speaker_names = [mapping.strip()]
    elif isinstance(mapping, (list, tuple)):
        speaker_names = [str(x).strip() for x in mapping if str(x).strip()]
    else:
        return keys

    characters = getattr(state, "characters", {}) or {}
    name_to_key: Dict[str, str] = {}
    for ckey, char in characters.items():
        char_name = (getattr(char, "name", "") or "").strip().lower()
        if char_name:
            name_to_key[char_name] = ckey
        name_to_key[ckey.lower()] = ckey

    for speaker in speaker_names:
        matched = name_to_key.get(speaker.lower())
        if matched:
            keys.add(matched)

    return keys


def get_character_location_index(state: GameState) -> Dict[str, str]:
    """Return a map of character_key -> location_id.

    Precedence:
    1. state.character_locations — runtime-tracked positions (seeded from
       world.character_start_locations and updated as characters move).
    2. world.location_speakers in story_cfg — legacy static mapping (location
       → [character names]); used as fallback for stories that haven't migrated
       to character_start_locations yet.
    """
    # Prefer runtime-tracked locations if populated.
    # Filter out any entries with empty keys or values to avoid polluting the
    # index with stale or partially-written location data.
    runtime_locs = getattr(state, "character_locations", {}) or {}
    if runtime_locs:
        return {k: v for k, v in runtime_locs.items() if k and v}

    # Fallback: derive from location_speakers (legacy static mapping)
    index: Dict[str, str] = {}

    cfg = getattr(state, "story_cfg", None)
    if cfg is None:
        return index
    if hasattr(cfg, "as_dict"):
        cfg = cfg.as_dict()
    if not isinstance(cfg, dict):
        return index

    world_cfg = cfg.get("world", {}) or {}
    loc_speakers = world_cfg.get("location_speakers") or {}
    if not isinstance(loc_speakers, dict):
        return index

    characters = getattr(state, "characters", {}) or {}
    name_to_key: Dict[str, str] = {}
    for ckey, char in characters.items():
        ckey_l = str(ckey).strip().lower()
        if ckey_l:
            name_to_key[ckey_l] = ckey_l
        cname = (getattr(char, "name", "") or "").strip().lower()
        if cname:
            name_to_key[cname] = ckey_l

    for loc_id, mapping in loc_speakers.items():
        if isinstance(mapping, str):
            speakers = [mapping]
        elif isinstance(mapping, (list, tuple)):
            speakers = [str(x) for x in mapping]
        else:
            continue

        for speaker in speakers:
            key = name_to_key.get(str(speaker).strip().lower())
            if key:
                index[key] = str(loc_id or "")

    return index


def get_on_call_character_keys(state: GameState) -> Set[str]:
    """Return character keys currently marked as being on a phone call.

    Markers are transient text entries in the form:
    ``__on_call_character_marker__:<character_key>``
    """
    keys: Set[str] = set()
    for entry in getattr(state, "transient_entries", []) or []:
        txt = (getattr(entry, "text", "") or "").strip()
        if not txt.startswith("__on_call_character_marker__:"):
            continue
        key = txt.split(":", 1)[1].strip().lower()
        if key:
            keys.add(key)
    return keys


def get_people_present_keys(state: GameState) -> Set[str]:
    """Return character keys currently present at player's location.

    Presence source is runtime world location index when available.
    This helper queries the active world graph location id each turn, then
    filters character locations to that id.
    """
    current_loc = str(getattr(state, "location_id", "") or "").strip()
    if not current_loc:
        return set()

    runtime = getattr(state, "world_runtime", None)
    if runtime is not None:
        try:
            # Validate the location exists in world graph for this turn.
            _ = runtime.world_graph.get_location(current_loc)
        except Exception:
            return set()

    location_index = get_character_location_index(state)
    return {key for key, loc in location_index.items() if str(loc or "").strip() == current_loc}


def compute_active_character_set(
    state: GameState,
    user_msg: str,
    recent_log: list | None = None,
    npc_reply: str = "",
    carryover_speakers: Set[str] | None = None,
) -> Set[str]:
    """Compute the full set of active characters for this turn.

    Combines:
    1. main_character + player (always active)
    2. Characters mentioned in the current turn text (*user_msg* + *npc_reply*)
    3. Characters at current location (``location_speakers``)
    4. Characters currently marked as on-call (transient markers)
    """
    characters = getattr(state, "characters", {}) or {}
    main_id = getattr(state, "main_character_id", "") or ""

    text_parts = [user_msg or ""]
    if npc_reply:
        text_parts.append(npc_reply)

    combined_text = "\n".join(text_parts)

    mentioned = detect_mentioned_characters(combined_text, characters, main_id)
    location = get_people_present_keys(state)
    on_call = get_on_call_character_keys(state)
    carryover = set(carryover_speakers or set())

    return mentioned | location | on_call | carryover
