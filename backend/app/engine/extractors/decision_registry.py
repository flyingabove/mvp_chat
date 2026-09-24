# backend/app/engine/extractors/decision_registry.py
"""Pure-data Decision definitions for TurnExtractor's Jev-eligible abilities.

Per JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §9 and §12 step 5 ("smallest
slice first"): only the abilities that are pure `choice`, need no fan-out,
no vocabulary authoring, and no arithmetic mapping are registered here.
Ability numbers refer to JEV_EXTRACTOR_REDESIGN_2026_09_22.md's chart:

  ability 1 (movement_intent)         -> movement_intent
  ability 2 (destination_id)          -> movement_destination
  ability 5 (previous_reply_location) -> prev_scene_location

Ability 3 (confidence) needs no Decision of its own — it's read natively
from whichever provider answered (JevRawAnswer.confidence, or the legacy
extractor's self-reported float), per the redesign doc's finding that a
dedicated field was never reliable anyway.

No engine/-purity violation: this module is pure data (dataclasses, no I/O,
no httpx import) even though it lives under engine/extractors/ alongside
turn_extractor.py, matching the package layout in
JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §2.

KNOWN SCOPE LIMITATION, documented rather than silently worked around:
`movement_destination`'s `allowed` set is built from the FULL
`world_locations` dict passed into TurnExtractor.extract(), not a
reachable-from-current-position subset. The provider architecture doc's §5
recommends prefiltering to reachable locations (cheaper, and per Jev's own
docs, more accurate) — but computing reachability needs the current
location id and the world graph's travel rules, neither of which
TurnExtractor.extract()'s existing signature carries today. Adding that
would be a signature change beyond step 3's "behaviour byte-identical"
scope, so it is deferred rather than risked here. The `none_of_these`
option and the existing allowed-id re-validation still make an
unreachable answer safe — it is only less efficient, not less correct.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from backend.app.llm.decisions.types import Criticality, Decision

MOVEMENT_TASK = "movement"
PREV_SCENE_TASK = "prev_scene"
KNOWLEDGE_TASK = "knowledge"
DEPARTURE_TASK = "departure"
REL_STATE_TASK = "rel_state"
REL_HISTORY_TASK = "rel_history"
BEHAVIOR_TAG_TASK = "behavior_tag"
SOCIAL_SHIFT_TASK = "social_shift"

NONE_OF_THESE = "none_of_these"
DEPARTURE_CERTAINTIES = frozenset({"NONE", "WISH", "DECISION"})
BEHAVIOR_TAG_NONE = "NONE"
SOCIAL_SHIFT_CERTAINTIES = frozenset({"NONE", "WISH", "SHIFT"})

# Ability 9 (step 7): each relationship-state dimension's legacy delta range,
# per turn_extractor.py's _clamp_delta bounds. Jev answers a "score" kind
# (a single 0.0-1.0 float) which is then mapped onto this range — symmetric
# dimensions (trust/affection) treat 0.5 as "no change"; asymmetric ones
# (fear/suspicion/jealousy, which the legacy prompt never allows negative)
# treat 0.0 as "no change". Same map used in reverse by each dimension's
# `legacy_resolver`, so a Jev score and a legacy delta are always compared
# apples-to-apples in shadow mode.
REL_STATE_DIMENSIONS: dict[str, float] = {
    "trust": 0.10,
    "affection": 0.10,
    "fear": 0.10,
    "suspicion": 0.10,
    "jealousy": 0.10,
}
REL_STATE_SYMMETRIC = frozenset({"trust", "affection"})


def movement_intent_decision() -> Decision:
    """Ability 1. Two-option choice, no fan-out, no dependency on scene
    content beyond the current player message."""
    return Decision(
        id="movement_intent",
        task=MOVEMENT_TASK,
        kind="choice",
        instructions=(
            "Does the CURRENT PLAYER MESSAGE contain an explicit, sincere "
            "intention to move to a different location right now? Sarcastic "
            "or ironic statements that actually REFUSE movement, and any "
            "hypothetical/past-tense mention of movement, must be NONE."
        ),
        criteria={
            "MOVE": "the player sincerely states they are going somewhere now",
            "NONE": "no sincere, explicit movement intent right now",
        },
        criticality=Criticality.CRITICAL,
        allowed=frozenset({"MOVE", "NONE"}),
        legacy_path=("movement", "intent"),
    )


def movement_destination_decision(world_locations: Mapping[str, str]) -> Decision:
    """Ability 2. Options built from the currently-known location set (see
    module docstring for the reachable-prefilter limitation)."""
    criteria = {
        str(loc_id): f"{str(loc_id)} ({str(name or '').strip()})"
        for loc_id, name in (world_locations or {}).items()
    }
    criteria[NONE_OF_THESE] = "no movement, or the destination is not in this list"
    return Decision(
        id="movement_destination",
        task=MOVEMENT_TASK,
        kind="choice",
        instructions=(
            "If the player is moving (per the movement_intent question), which "
            "of these known locations are they moving to? If there is no "
            "movement, or the stated destination is not one of these known "
            "locations, answer none_of_these."
        ),
        criteria=criteria,
        criticality=Criticality.CRITICAL,
        allowed=frozenset(criteria.keys()),
        none_option=NONE_OF_THESE,
        legacy_path=("movement", "destination_id"),
    )


def prev_scene_location_decision(world_locations: Mapping[str, str]) -> Decision:
    """Ability 5. Asks where the PREVIOUS assistant reply's scene took
    place — not reachability-filtered (the scene could be anywhere already
    established), matching the redesign doc's table ("all location ids +
    none_of_these")."""
    criteria = {
        str(loc_id): f"{str(loc_id)} ({str(name or '').strip()})"
        for loc_id, name in (world_locations or {}).items()
    }
    criteria[NONE_OF_THESE] = "the previous reply does not clearly establish a location"
    return Decision(
        id="prev_scene_location",
        task=PREV_SCENE_TASK,
        kind="choice",
        instructions=(
            "Which of these known locations does the PREVIOUS TURN ASSISTANT "
            "REPLY establish as the scene's location? Extract from that reply "
            "only, not from the current player message. If unclear, answer "
            "none_of_these."
        ),
        criteria=criteria,
        criticality=Criticality.CRITICAL,
        allowed=frozenset(criteria.keys()),
        none_option=NONE_OF_THESE,
        legacy_path=("previous_scene", "location_id"),
    )


def knowledge_decision(chunk_id: str, chunk_text: str) -> Decision:
    """Ability 7 (fan-out, step 6). One `noul` question PER CANDIDATE
    CHUNK — "does this character now know this fact, given what was just
    said?" `legacy_path` cannot express this: the legacy JSON's
    `knowledge_updates` is a LIST of {chunk_id, knows, ...} objects, so the
    id-keyed field this Decision needs (`knows_<chunk_id>`) must SEARCH
    that list for a matching chunk_id, hence `legacy_resolver` (see
    Decision's docstring in llm/decisions/types.py). Missing from the list
    entirely -> None (unusable, not "False") — matches the legacy prompt's
    own rule 5 ("omit uncertain updates"): omission is not evidence of
    knows=False, so this must be a fallback, not a legacy answer."""
    chunk_id = str(chunk_id).strip()
    chunk_text = str(chunk_text or "").strip()

    def _resolver(raw):
        for item in (raw or {}).get("knowledge_updates") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("chunk_id") or "").strip() == chunk_id:
                return bool(item.get("knows", False))
        return None

    return Decision(
        id=f"knows_{chunk_id}",
        task=KNOWLEDGE_TASK,
        kind="noul",
        instructions=(
            f"Given the dialogue, does the character now know this fact: "
            f"{chunk_text[:400]!r}? Judge only from what was just said or "
            f"witnessed this turn."
        ),
        criteria=["the character has been told or has witnessed this fact"],
        criticality=Criticality.DEGRADABLE,
        true_threshold=0.5,
        legacy_resolver=_resolver,
    )


def departure_decision(character_id: str) -> Decision:
    """Ability 10 (fan-out, step 6). One `choice` question PER RESIDENT —
    at most one resident's own dialogue can carry a departure signal per
    turn, so every OTHER resident's Decision must resolve to NONE, not an
    absent/None answer. `legacy_path` cannot express "check whether THIS
    resident is the one named in a single shared object, else NONE" — see
    Decision.legacy_resolver's docstring. CRITICAL: an engine invariant
    (character leaves the house) depends on this, same criticality as the
    legacy extractor's departure_signal always had."""
    character_id = str(character_id).strip().lower()

    def _resolver(raw):
        signal = (raw or {}).get("departure_signal")
        if not isinstance(signal, dict):
            return "NONE"
        if str(signal.get("character_id") or "").strip().lower() != character_id:
            return "NONE"
        certainty = str(signal.get("certainty") or "NONE").strip().upper()
        return certainty if certainty in DEPARTURE_CERTAINTIES else "NONE"

    return Decision(
        id=f"departure_{character_id}",
        task=DEPARTURE_TASK,
        kind="choice",
        instructions=(
            f"Does {character_id}'s OWN dialogue (not the player's or "
            f"another character's speech about them) concern {character_id} "
            "leaving the house? WISH = a passing complaint/joke/hypothetical. "
            "DECISION = an explicit, serious, stated intention to actually "
            "leave. NONE = no departure topic from this character."
        ),
        criteria={
            "NONE": "no departure topic present from this character's own words",
            "WISH": "a passing complaint, joke, or hypothetical about leaving",
            "DECISION": "an explicit, serious, stated intention to actually leave",
        },
        criticality=Criticality.CRITICAL,
        allowed=frozenset(DEPARTURE_CERTAINTIES),
        none_option="NONE",
        legacy_resolver=_resolver,
    )


def knowledge_batch_decisions(candidate_chunks: Sequence[Mapping[str, str]]) -> tuple[Decision, ...]:
    """Builds one knowledge_decision() per candidate chunk with both a
    chunk_id and text, deduping by chunk_id (first occurrence wins) — a
    thin, pure-data fan-out helper so callers don't repeat the filtering
    logic TurnExtractor's own candidate-chunk truncation already applies."""
    seen: set[str] = set()
    decisions: list[Decision] = []
    for chunk in candidate_chunks or []:
        cid = str((chunk or {}).get("chunk_id") or "").strip()
        text = str((chunk or {}).get("text") or "").strip()
        if not cid or not text or cid in seen:
            continue
        seen.add(cid)
        decisions.append(knowledge_decision(cid, text))
    return tuple(decisions)


def departure_batch_decisions(resident_character_keys: Sequence[str]) -> tuple[Decision, ...]:
    """One departure_decision() per resident, excluding 'player' (the
    player cannot depart the house via this mechanic) and deduping."""
    seen: set[str] = set()
    decisions: list[Decision] = []
    for key in resident_character_keys or []:
        key = str(key).strip().lower()
        if not key or key == "player" or key in seen:
            continue
        seen.add(key)
        decisions.append(departure_decision(key))
    return tuple(decisions)


def rel_state_score_to_delta(dimension: str, score: float) -> float:
    """0.0-1.0 Jev score -> a delta in the legacy dimension's range. Public
    (not `_`-prefixed) because TurnExtractor's override step needs the same
    mapping in the forward direction."""
    max_abs = REL_STATE_DIMENSIONS[dimension]
    score = max(0.0, min(1.0, score))
    if dimension in REL_STATE_SYMMETRIC:
        return (score - 0.5) * 2 * max_abs
    return score * max_abs


def _rel_state_delta_to_score(dimension: str, delta: float | None) -> float | None:
    """The inverse map, used only by legacy_resolver closures so a legacy
    delta and a Jev score answer live in the same comparable space."""
    if delta is None:
        return None
    max_abs = REL_STATE_DIMENSIONS[dimension]
    if max_abs <= 0:
        return 0.5
    if dimension in REL_STATE_SYMMETRIC:
        score = 0.5 + (float(delta) / (2 * max_abs))
    else:
        score = float(delta) / max_abs
    return max(0.0, min(1.0, score))


def relationship_state_decision(target_id: str, dimension: str) -> Decision:
    """Ability 9 (fan-out, step 7). One `score` question per (dimension,
    target) pair, anchored to the player — matches the legacy prompt's own
    restriction (relationship_state_updates.from_id must always be
    "player", enforced in turn_extractor.py's _parse_dict). NPC-to-NPC
    state deltas are not extracted by the legacy path either, so there is
    no coverage gap introduced here."""
    target_id = str(target_id).strip().lower()
    dimension = str(dimension).strip().lower()
    if dimension not in REL_STATE_DIMENSIONS:
        raise ValueError(f"unknown relationship-state dimension: {dimension!r}")

    def _resolver(raw):
        for item in (raw or {}).get("relationship_state_updates") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("from_id") or "").strip().lower() != "player":
                continue
            if str(item.get("to_id") or "").strip().lower() != target_id:
                continue
            return _rel_state_delta_to_score(dimension, item.get(f"{dimension}_delta"))
        return _rel_state_delta_to_score(dimension, 0.0)  # absent entry == no shift, not "unknown"

    direction = (
        "-1.0 (strong negative shift) through 0.5 (no change) to 1.0 (strong positive shift)"
        if dimension in REL_STATE_SYMMETRIC
        else "0.0 (no signal) to 1.0 (strong signal); this dimension is never negative"
    )
    return Decision(
        id=f"relstate_{dimension}_{target_id}",
        task=REL_STATE_TASK,
        kind="score",
        instructions=(
            f"How much did the PLAYER's expressed {dimension} toward {target_id} shift in the "
            f"CURRENT USER MESSAGE? Answer as a score from {direction}. Score exactly 0.5 (or 0.0 "
            "for a never-negative dimension) when the message expresses no relevant attitude change."
        ),
        criteria=[f"player's {dimension} toward {target_id} in this message"],
        criticality=Criticality.DEGRADABLE,
        legacy_resolver=_resolver,
    )


def relationship_state_batch_decisions(target_character_keys: Sequence[str]) -> tuple[Decision, ...]:
    """5 dimensions x N targets, excluding 'player' (can't hold an
    attitude-delta toward itself) and deduping targets."""
    seen: set[str] = set()
    decisions: list[Decision] = []
    for key in target_character_keys or []:
        key = str(key).strip().lower()
        if not key or key == "player" or key in seen:
            continue
        seen.add(key)
        for dimension in REL_STATE_DIMENSIONS:
            decisions.append(relationship_state_decision(key, dimension))
    return tuple(decisions)


REL_HISTORY_FIELDS = ("prior_relationship", "prior_intimacy", "in_relationship")


def relationship_history_decision(target_id: str, field_name: str) -> Decision:
    """Ability 8 (gated fan-out, step 7). One `noul` question per (field,
    target) pair, anchored to the player, same NPC-to-NPC scope limitation
    as ability 9 above (the legacy schema allows NPC-to-NPC pairs, but the
    combinatorics of an O(n^2) fan-out are not worth it for a fact this
    rare — see JEV_EXTRACTOR_REDESIGN_2026_09_22.md's cost analysis).
    "Gated": the caller (relationship_history_batch_decisions) only builds
    these for characters actually present in the current exchange, not
    every known character — these are rare, explicitly-confirmed facts, not
    something worth asking about every turn for every character."""
    target_id = str(target_id).strip().lower()
    field_name = str(field_name).strip().lower()
    if field_name not in REL_HISTORY_FIELDS:
        raise ValueError(f"unknown relationship-history field: {field_name!r}")

    def _resolver(raw):
        for item in (raw or {}).get("relationship_history_updates") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("from_id") or "").strip().lower() != "player":
                continue
            if str(item.get("to_id") or "").strip().lower() != target_id:
                continue
            value = item.get(field_name)
            return None if value is None else bool(value)
        return None  # absent == "not addressed", never coerced to False

    field_prose = field_name.replace("_", " ")
    return Decision(
        id=f"relhist_{field_name}_{target_id}",
        task=REL_HISTORY_TASK,
        kind="noul",
        instructions=(
            f"Does dialogue between the player and {target_id} EXPLICITLY confirm: {field_prose}? "
            "Only answer true from an explicit statement, never an inference or a vague hint."
        ),
        criteria=[f"player and {target_id} explicitly confirm {field_prose}"],
        criticality=Criticality.DEGRADABLE,
        true_threshold=0.5,
        legacy_resolver=_resolver,
    )


def relationship_history_batch_decisions(target_character_keys: Sequence[str]) -> tuple[Decision, ...]:
    """3 fields x N gated targets, excluding 'player', deduping."""
    seen: set[str] = set()
    decisions: list[Decision] = []
    for key in target_character_keys or []:
        key = str(key).strip().lower()
        if not key or key == "player" or key in seen:
            continue
        seen.add(key)
        for field_name in REL_HISTORY_FIELDS:
            decisions.append(relationship_history_decision(key, field_name))
    return tuple(decisions)


def behavior_tag_decision(from_id: str, to_id: str, vocabulary: Sequence[str]) -> Decision:
    """Ability 11 (fan-out, step 8 - BL-16-gated). One `choice` question
    per ordered (from, to) character pair, over the story's closed
    behavior_tag_vocabulary plus a NONE option. Only meaningful once a
    vocabulary exists (see decision_registry callers: this is never
    registered for a vocabulary-less story) - a free-text tag has no fixed
    option set for Jev's `choice` kind to select from."""
    from_id = str(from_id).strip().lower()
    to_id = str(to_id).strip().lower()
    vocab = [str(t).strip() for t in vocabulary if str(t or "").strip()]
    criteria = {t: f'from_id behaved "{t}" toward to_id this turn' for t in vocab}
    criteria[BEHAVIOR_TAG_NONE] = "no clear behavior from from_id toward to_id this turn"
    vocab_lookup = {t.lower(): t for t in vocab}

    def _resolver(raw):
        for item in (raw or {}).get("behavior_tags") or []:
            if not isinstance(item, dict):
                continue
            if str(item.get("from_id") or "").strip().lower() != from_id:
                continue
            if str(item.get("to_id") or "").strip().lower() != to_id:
                continue
            canonical = vocab_lookup.get(str(item.get("tag") or "").strip().lower())
            return canonical if canonical is not None else BEHAVIOR_TAG_NONE
        return BEHAVIOR_TAG_NONE

    return Decision(
        id=f"behtag_{from_id}_{to_id}",
        task=BEHAVIOR_TAG_TASK,
        kind="choice",
        instructions=(
            f"Did {from_id}'s words or actions THIS TURN show an observable attitude/behavior "
            f"toward {to_id}? Pick the closest matching tag from the allowed list, or NONE if no "
            "clear behavior toward this specific character is shown. This is a raw observation of "
            "this turn only, not a judgment about whether anything has changed."
        ),
        criteria=criteria,
        criticality=Criticality.DEGRADABLE,
        allowed=frozenset(criteria.keys()),
        none_option=BEHAVIOR_TAG_NONE,
        legacy_resolver=_resolver,
    )


def behavior_tag_batch_decisions(
    character_keys: Sequence[str], vocabulary: Sequence[str],
) -> tuple[Decision, ...]:
    """Every ordered (from, to) pair over the known characters (self-pairs
    excluded) - O(n^2), matching ability 8/9's documented NPC-pair scope
    limitation, times a vocabulary the story must have authored (empty
    vocabulary -> no decisions at all; caller should not even build this
    batch in that case, but this returns () defensively either way)."""
    vocab = [str(t).strip() for t in (vocabulary or []) if str(t or "").strip()]
    if not vocab:
        return ()
    keys = sorted({str(k).strip().lower() for k in (character_keys or []) if str(k or "").strip()})
    decisions: list[Decision] = []
    for from_id in keys:
        for to_id in keys:
            if from_id == to_id:
                continue
            decisions.append(behavior_tag_decision(from_id, to_id, vocab))
    return tuple(decisions)


def social_shift_certainty_decision(subject_id: str, target_id: str, pair_tags: Sequence[str]) -> Decision:
    """Ability 12 (step 9). A SINGLE decision, not a fan-out - matches the
    legacy design's own scope: at most one ripe pair is ever evaluated per
    turn (see prompt_engine.py's _ripe_behavior_pairs), so there is only
    ever one (subject, target) pair worth asking about. Jev only judges
    `certainty` (NONE/WISH/SHIFT); it cannot generate `new_value`'s free
    text, so a SHIFT answer still needs legacy's own new_value to be
    usable - see TurnExtractor._apply_social_shift_override for how that
    gap is closed without ever writing a SHIFT with an empty description."""
    subject_id = str(subject_id).strip().lower()
    target_id = str(target_id).strip().lower()

    def _resolver(raw):
        signal = (raw or {}).get("social_shift_signal")
        if not isinstance(signal, dict):
            return "NONE"
        if str(signal.get("scope") or "").strip().lower() != "disposition":
            return "NONE"
        if str(signal.get("subject_id") or "").strip().lower() != subject_id:
            return "NONE"
        if str(signal.get("target_id") or "").strip().lower() != target_id:
            return "NONE"
        certainty = str(signal.get("certainty") or "NONE").strip().upper()
        return certainty if certainty in SOCIAL_SHIFT_CERTAINTIES else "NONE"

    pattern = ", ".join(str(t) for t in (pair_tags or []))
    return Decision(
        id="social_shift_certainty",
        task=SOCIAL_SHIFT_TASK,
        kind="choice",
        instructions=(
            f"{subject_id} has shown this behavior pattern toward {target_id} (oldest -> newest): "
            f"{pattern}. Has {subject_id}'s disposition toward {target_id} genuinely, settledly "
            "shifted (SHIFT), or is this still a momentary/mixed pattern not yet a real change "
            "(WISH), or is there no real pattern here at all (NONE)?"
        ),
        criteria={
            "NONE": "no genuine pattern / still too noisy to judge",
            "WISH": "a momentary flicker or one-off outlier, not a real change",
            "SHIFT": "the accumulated pattern shows a real, settled change",
        },
        criticality=Criticality.DEGRADABLE,
        allowed=frozenset(SOCIAL_SHIFT_CERTAINTIES),
        none_option="NONE",
        legacy_resolver=_resolver,
    )
