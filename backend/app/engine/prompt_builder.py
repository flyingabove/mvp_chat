# app/engine/prompt_builder.py
from dataclasses import dataclass, field
from backend.app.config.epistemic_flags import belief_enabled
from backend.app.engine.state import GameState
from backend.app.engine.knowledge_chunks import KnowledgeChunk, normalize_parties
from backend.app.config.settings import (
    EMOTION_START,
    REL_START,
    MEMORY_TURNS,
)
from backend.app.utils.logging_utils import jlog as _jlog, truncate as _truncate


# ---------------------------------------------------------------------------
# PromptInput — single source of truth for all model-bound inputs
# ---------------------------------------------------------------------------
@dataclass
class PromptInput:
    state: GameState
    log: list
    user_msg: str
    knowledge_chunks: list
    truth_mode: bool = False
    retrieval_debug: dict | list | None = None
    canonicalized_user_msg: str | None = None
    extras: dict = field(default_factory=dict)

    def canonical_msg(self) -> str:
        return self.canonicalized_user_msg or self.user_msg


def _extract_story_cfg(state: GameState):
    """Return (cfg_dict, story_def_or_None) with backward compatibility."""
    cfg_obj = getattr(state, "story_cfg", {}) or {}
    story_def = cfg_obj if hasattr(cfg_obj, "as_dict") else None
    cfg_dict = story_def.as_dict() if story_def else cfg_obj
    return cfg_dict, story_def


def _format_memory_block(retrieved_chunks: list, character_name: str = "") -> str:
    """
    Inject a concise, high-signal memory section.
    Must be treated as canon by the model.

    NOTE:
    - Retrieval happens upstream in api/prompt_engine.py (single source of truth).
    - This function only formats what it is given.
    """
    if not retrieved_chunks:
        return ""

    lines = []
    for c in retrieved_chunks:
        # Keep stable + readable; include type + chunk_id for debugging
        ctype = c.get("type", "")
        cid = c.get("chunk_id", "")
        text = c.get("text", "")
        lines.append(f"- ({ctype}) [{cid}] {text}")

    character_name = character_name or "the character"
    return (
        "\n────────────────────────────────────────\n"
        "### CANONICAL CHARACTER MEMORY (MUST USE)\n"
        "────────────────────────────────────────\n"
        "Everything in this section is authoritative for this story session.\n"
        f"If the user asks about {character_name}'s identity, works, dates, agency, or other real-world facts,\n"
        "you MUST answer using ONLY this memory. If it isn't here, say you don't know.\n\n"
        + "\n".join(lines)
        + "\n"
    )


# Legacy: retained for debug/logging paths
def _visibility_suffix(chunk: KnowledgeChunk) -> str:
    parts = []
    if chunk.known_by:
        if "all_characters" in chunk.known_by:
            parts.append("known_by=ALL_CHARACTERS")
        else:
            parts.append("known_by=" + ",".join(chunk.known_by))
    if chunk.not_known_by:
        parts.append("not_known_by=" + ",".join(chunk.not_known_by))
    if chunk.maybe_known_by:
        parts.append("maybe_known_by=" + ",".join(chunk.maybe_known_by))
    return " [" + " | ".join(parts) + "]" if parts else ""


# ---------------------------------------------------------------------------
# Plain-English visibility prose
# ---------------------------------------------------------------------------

def _resolve_name(key: str, characters: dict) -> str:
    """Convert a character key to a human-readable display name."""
    if key == "player":
        return "the player"
    if key == "all_characters":
        return "everyone"
    ch = characters.get(key)
    if ch and getattr(ch, "name", None):
        return ch.name
    return key.replace("_", " ").title()


def _english_join(names: list[str]) -> str:
    """Join names with natural English conjunctions."""
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def _visibility_prose(chunk: KnowledgeChunk, characters: dict, active_characters: set[str] | None = None) -> str:
    """Convert a chunk's visibility lists into a plain-English sentence."""
    if "all_characters" in chunk.known_by:
        return "Everyone knows this."

    parts: list[str] = []

    def _filter_scene(keys: list[str]) -> list[str]:
        if active_characters is None:
            return list(keys)
        return [k for k in keys if k in active_characters]

    known_names = [_resolve_name(k, characters) for k in _filter_scene(chunk.known_by)]
    not_known_names = [_resolve_name(k, characters) for k in _filter_scene(chunk.not_known_by)]
    maybe_names = [_resolve_name(k, characters) for k in _filter_scene(chunk.maybe_known_by)]

    if known_names and not not_known_names and not maybe_names:
        if len(known_names) == 1:
            parts.append(f"Currently only {known_names[0]} knows this.")
        else:
            parts.append(f"{_english_join(known_names)} know this.")
    elif known_names:
        verb = "knows" if len(known_names) == 1 else "know"
        clause = f"{_english_join(known_names)} {verb} this"
        if not_known_names:
            neg_verb = "does not yet know" if len(not_known_names) == 1 else "do not yet know"
            clause += f" but {_english_join(not_known_names)} {neg_verb}"
        parts.append(clause + ".")
    elif not_known_names:
        neg_verb = "does not yet know this." if len(not_known_names) == 1 else "do not yet know this."
        parts.append(f"{_english_join(not_known_names)} {neg_verb}")

    if maybe_names:
        parts.append(f"{_english_join(maybe_names)} may have some awareness of this.")

    return " ".join(parts)


def _is_legacy_relationship_telemetry(text: str) -> bool:
    """Detect old relationship telemetry lines that should not appear in prose stack.

    These lines are rendered in the dedicated relationship section and must not
    leak into canonical/belief stack sections.
    """
    content = str(text or "").strip().lower()
    if not content:
        return False

    if "->" in content and "type=" in content and "trust is" in content:
        return True

    return content.startswith("relationship dynamics and world context:")


_CERTAINTY_WORDS = {
    0.0: "speculative",
    0.1: "very_tentative",
    0.2: "tentative",
    0.3: "leaning_uncertain",
    0.4: "uncertain",
    0.5: "mixed",
    0.6: "leaning_likely",
    0.7: "plausible",
    0.8: "likely",
    0.9: "highly_likely",
    1.0: "certain",
}


def _certainty_word(confidence: float | int | str | None) -> str:
    try:
        value = float(confidence if confidence is not None else 0.0)
    except (TypeError, ValueError):
        value = 0.0
    value = max(0.0, min(1.0, value))
    bucket = round(value, 1)
    return _CERTAINTY_WORDS.get(bucket, "mixed")


def _certainty_phrase(certainty_word: str) -> str:
    token = str(certainty_word or "mixed").strip().lower()
    if token in {"speculative", "very_tentative"}:
        return "with very low confidence"
    if token in {"tentative", "leaning_uncertain", "uncertain"}:
        return "with low confidence"
    if token == "mixed":
        return "with mixed confidence"
    if token in {"leaning_likely", "plausible"}:
        return "with moderate confidence"
    if token in {"likely", "highly_likely"}:
        return "with high confidence"
    if token == "certain":
        return "with complete confidence"
    return "with mixed confidence"


def _belief_line(it: KnowledgeChunk, characters: dict, idx: int, active_characters: set[str] | None = None) -> str:
    visibility = _visibility_prose(it, characters, active_characters=active_characters)
    certainty_word = str(getattr(it, "certainty", "") or "mixed").strip() or "mixed"
    certainty_phrase = _certainty_phrase(certainty_word)

    if visibility:
        prefix = visibility.rstrip(".")
        return f"{idx}. {prefix} {certainty_phrase}: {it.text}"

    return f"{idx}. {certainty_phrase.capitalize()}: {it.text}"


_TIER_HEADINGS = {
    "CANONICAL_CORE": "These are the definitive canonical facts of this story:",
    "CANONICAL_GRAPH": "World context relevant to the current scene:",
    "SUBJECTIVE_BELIEF": "Beliefs and suspicions (not necessarily true):",
    "RETRIEVED_MEMORY": "Remembered details from past interactions:",
}


def _get_active_character_keys(state: GameState) -> set[str]:
    """Extract the active character set from transient markers.

    Scans ``state.transient_entries`` for marker texts in the form
    ``__active_character_marker__:<character_key>`` and returns their keys.
    Always includes ``main_character_id`` and ``"player"`` as fallback.
    """
    keys: set[str] = set()
    main_id = getattr(state, "main_character_id", "") or ""
    if main_id:
        keys.add(main_id)
    keys.add("player")

    for e in getattr(state, "transient_entries", []) or []:
        txt = (getattr(e, "text", "") or "").strip()
        if txt.startswith("__active_character_marker__:"):
            ch_key = txt.split(":", 1)[1].strip().lower()
            if ch_key:
                keys.add(ch_key)
        elif txt.startswith("__scene_speaker_marker__:"):
            ch_key = txt.split(":", 1)[1].strip().lower()
            if ch_key:
                keys.add(ch_key)
        elif txt.startswith("__on_call_character_marker__:"):
            ch_key = txt.split(":", 1)[1].strip().lower()
            if ch_key:
                keys.add(ch_key)

    return keys


def _get_people_present_keys(state: GameState) -> set[str]:
    keys: set[str] = set()
    for e in getattr(state, "transient_entries", []) or []:
        txt = (getattr(e, "text", "") or "").strip()
        if txt.startswith("__people_present_marker__:"):
            ch_key = txt.split(":", 1)[1].strip().lower()
            if ch_key:
                keys.add(ch_key)
    if keys:
        return keys

    latest_scene = getattr(state, "latest_scene_knowledge", None)
    if callable(latest_scene):
        item = latest_scene()
        if item is not None:
            return {
                str(k or "").strip().lower()
                for k in (getattr(item, "people_present", []) or [])
                if str(k or "").strip()
            }
    return set()


def _get_scene_speaker_keys(state: GameState) -> set[str]:
    keys: set[str] = set()
    for e in getattr(state, "transient_entries", []) or []:
        txt = (getattr(e, "text", "") or "").strip()
        if txt.startswith("__scene_speaker_marker__:"):
            ch_key = txt.split(":", 1)[1].strip().lower()
            if ch_key:
                keys.add(ch_key)
    if keys:
        return keys

    latest_scene = getattr(state, "latest_scene_knowledge", None)
    if callable(latest_scene):
        item = latest_scene()
        if item is not None:
            return {
                str(k or "").strip().lower()
                for k in (getattr(item, "speakers", []) or [])
                if str(k or "").strip()
            }
    return set()


def _scene_presence_keys(state: GameState) -> set[str]:
    """Return characters that are currently in scene focus.

    Includes always-on anchors (main + player), active mention/on-call markers,
    and speakers configured at the current location.
    """
    keys = set(_get_active_character_keys(state))

    cfg, _ = _extract_story_cfg(state)
    world_cfg = (cfg.get("world") or {}) if isinstance(cfg, dict) else {}
    loc_speakers = world_cfg.get("location_speakers") or {}
    loc_id = str(getattr(state, "location_id", "") or "")
    raw_speakers = loc_speakers.get(loc_id) if isinstance(loc_speakers, dict) else None

    if isinstance(raw_speakers, str):
        raw_list = [raw_speakers]
    elif isinstance(raw_speakers, list):
        raw_list = [str(x or "") for x in raw_speakers]
    else:
        raw_list = []

    chars = getattr(state, "characters", {}) or {}
    name_to_key = {}
    for ckey, char in chars.items():
        ckey_l = str(ckey or "").strip().lower()
        if ckey_l:
            name_to_key[ckey_l] = ckey_l
        cname = (getattr(char, "name", "") or "").strip().lower()
        if cname:
            name_to_key[cname] = ckey_l

    for raw in raw_list:
        key = name_to_key.get(str(raw).strip().lower())
        if key:
            keys.add(key)

    return keys


def _knowledge_chunks_from_state(state: GameState, retrieved_chunks: list) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []

    speaker_id = (getattr(state, "main_character_id", "") or "").strip().lower()
    main_char = getattr(state, "main_character", None)
    if main_char:
        chunks.append(KnowledgeChunk(
            id=f"char::{main_char.key}",
            text=f"{main_char.name} is a {main_char.role or 'character'} in this story.",
            tier="CANONICAL_CORE",
            source="character",
            certainty="certain",
            known_by=normalize_parties([main_char.key]),
        ))

    for fact in getattr(state, "canonical_facts", []) or []:
        text = (getattr(fact, "content", "") or "").strip()
        if not text:
            continue
        if _is_legacy_relationship_telemetry(text):
            continue
        chunks.append(KnowledgeChunk(
            id=f"fact::{getattr(fact, 'id', '') or 'unknown'}",
            text=text,
            tier="CANONICAL_CORE",
            source="epistemic_seed.canonical_facts",
            certainty="certain",
            known_by=normalize_parties(getattr(fact, "known_by", []) or []),
            not_known_by=normalize_parties(getattr(fact, "not_known_by", []) or []),
            maybe_known_by=normalize_parties(getattr(fact, "maybe_known_by", []) or []),
        ))

    graph = getattr(state, "character_graph", None)
    if graph:
        active_keys = _get_active_character_keys(state)
        for edge in graph.get_edges_from(state.main_character_id or ""):
            if edge.to_id not in active_keys:
                continue
            # Relationship dynamics are rendered once in the dedicated
            # relationship section, not duplicated inside epistemic stack.
            pass

    runtime = getattr(state, "world_runtime", None)
    loc_id = getattr(state, "location_id", "") or ""
    if runtime and loc_id:
        try:
            wg = runtime.world_graph
            loc = wg.get_location(loc_id)
            chunks.append(KnowledgeChunk(
                id=f"place::{loc_id}",
                text=f"The current place is {loc.name}. {getattr(loc, 'description', '')}",
                tier="CANONICAL_GRAPH",
                source="places_graph",
                certainty="certain",
                known_by=["all_characters"],
            ))
        except Exception:
            pass

    if belief_enabled():
        beliefs = getattr(state, "beliefs", {}) or {}
        bs = beliefs.get(state.main_character_id or "")
        if bs:
            claims_list = getattr(bs, "claims", []) or []
            if len(claims_list) > 10:
                _jlog({
                    "kind": "belief_claims_truncated",
                    "character": state.main_character_id,
                    "total": len(claims_list),
                    "injected": 10,
                })
            for claim in claims_list[:10]:
                text = (getattr(claim, "content", "") or "").strip()
                if not text:
                    continue
                chunks.append(KnowledgeChunk(
                    id=f"belief::{getattr(claim, 'id', '') or 'unknown'}",
                    text=text,
                    tier="SUBJECTIVE_BELIEF",
                    source=str(getattr(claim, "source", "belief")),
                    certainty=_certainty_word(getattr(claim, "confidence", 0.0)),
                    known_by=normalize_parties(getattr(claim, "known_by", []) or [speaker_id]),
                    not_known_by=normalize_parties(getattr(claim, "not_known_by", []) or []),
                    maybe_known_by=normalize_parties(getattr(claim, "maybe_known_by", []) or []),
                ))

    for c in retrieved_chunks or []:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        if _is_legacy_relationship_telemetry(text):
            continue
        chunks.append(KnowledgeChunk(
            id=f"retrieval::{c.get('chunk_id') or 'unknown'}",
            text=text,
            tier="RETRIEVED_MEMORY",
            source="bm25_faiss",
            certainty="mixed",
            maybe_known_by=[speaker_id] if speaker_id else [],
        ))

    return chunks


def _format_labeled_knowledge_stack(state: GameState, retrieved_chunks: list) -> tuple[str, list[dict]]:
    chunks = _knowledge_chunks_from_state(state, retrieved_chunks)
    characters = getattr(state, "characters", {}) or {}
    active_keys = _scene_presence_keys(state)

    tier_order = [
        "CANONICAL_CORE",
        "CANONICAL_GRAPH",
        "SUBJECTIVE_BELIEF",
        "RETRIEVED_MEMORY",
    ]

    grouped: dict[str, list[KnowledgeChunk]] = {k: [] for k in tier_order}
    for c in chunks:
        grouped.setdefault(c.tier, []).append(c)

    sections = []
    debug_chunks = []
    for tier in tier_order:
        items = grouped.get(tier) or []
        if not items:
            continue
        heading = _TIER_HEADINGS.get(tier, f"{tier}:")
        lines = [heading]
        for idx, it in enumerate(items, 1):
            if _is_legacy_relationship_telemetry(it.text):
                continue
            if tier == "SUBJECTIVE_BELIEF":
                lines.append(_belief_line(it, characters, idx, active_characters=active_keys))
            else:
                visibility = _visibility_prose(it, characters, active_characters=active_keys)
                if visibility:
                    lines.append(f"{idx}. {it.text} {visibility}")
                else:
                    lines.append(f"{idx}. {it.text}")
            debug_chunks.append({
                "id": it.id,
                "tier": it.tier,
                "source": it.source,
                "certainty": it.certainty,
                "text": it.text,
                "known_by": list(it.known_by),
                "not_known_by": list(it.not_known_by),
                "maybe_known_by": list(it.maybe_known_by),
            })
        if len(lines) > 1:
            sections.append("\n".join(lines))

    if not sections:
        return "", []

    preface = (
        "\n────────────────────────────────────────\n"
        "### EPISTEMIC KNOWLEDGE STACK\n"
        "────────────────────────────────────────\n"
        "The following sections describe what is true in this story and who knows what. "
        "Earlier sections outrank later sections when facts conflict. "
        "Each fact includes a plain-English note about which characters know it, "
        "do not know it, or may be partially aware of it.\n\n"
        "When a fact says a character does not know something, that character must not "
        "state, hint at, or act on that information. "
        "When a fact says everyone knows something, treat it as common knowledge. "
        "When uncertain about whether a character would know a detail not listed here, "
        "hedge naturally instead of asserting certainty. "
        "Never state as fact anything the active speaker does not know.\n\n"
    )

    return preface + "\n\n".join(sections) + "\n", debug_chunks


def _canonical_facts_for_speaker(state: GameState) -> list[str]:
    speaker_id = (getattr(state, "main_character_id", "") or "").strip().lower()
    out: list[str] = []

    for fact in getattr(state, "canonical_facts", []) or []:
        text = (getattr(fact, "content", "") or "").strip()
        if not text:
            continue
        known_by = [str(x).strip().lower() for x in (getattr(fact, "known_by", []) or []) if str(x).strip()]
        if known_by and speaker_id and speaker_id not in known_by and "all" not in known_by and "all_characters" not in known_by:
            continue
        out.append(text)

    if not out:
        for t in getattr(state, "canonical_truth", None) or []:
            tt = str(t).strip()
            if tt:
                out.append(tt)

    seen = set()
    uniq = []
    for t in out:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)
    return uniq[:12]


def _character_basics_section(state: GameState) -> str:
    ch = getattr(state, "main_character", None)
    if not ch:
        return ""
    lines = [
        f"- Character key: {getattr(ch, 'key', '') or ''}",
        f"- Character name: {getattr(ch, 'name', '') or ''}",
        f"- Character role/archetype: {getattr(ch, 'role', '') or 'npc'}",
    ]
    return (
        "\n────────────────────────────────────────\n"
        "### CHARACTER BASICS (CANONICAL)\n"
        "────────────────────────────────────────\n"
        + "\n".join(lines)
        + "\n"
    )


def _canonical_section(state: GameState) -> str:
    facts = _canonical_facts_for_speaker(state)
    if not facts:
        return ""
    return (
        "\n────────────────────────────────────────\n"
        "### STORY CANONICAL TRUTHS (SPEAKER-VISIBLE)\n"
        "────────────────────────────────────────\n"
        "Only use these as hard world truths. If something is missing, say you don't know.\n\n"
        + "\n".join(f"- {f}" for f in facts)
        + "\n"
    )


def _places_graph_section(state: GameState) -> str:
    runtime = getattr(state, "world_runtime", None)
    loc_id = getattr(state, "location_id", "") or ""
    if not runtime or not loc_id:
        return ""
    try:
        wg = getattr(runtime, "world_graph", None)
        if wg is None:
            return ""
        loc = wg.get_location(loc_id)
        loc_name = getattr(loc, "name", "") or loc_id
        loc_desc = getattr(loc, "description", "") or ""
        outgoing = []
        for edge in wg.get_outgoing(loc_id).to_tuple()[:8]:
            to_loc = wg.get_location(edge.to_id.value)
            outgoing.append(f"- {to_loc.name} ({int(edge.minutes)} min)")

        section_lines = [f"Current place: {loc_name}"]
        if loc_desc:
            section_lines.append(f"Description: {loc_desc}")
        if outgoing:
            section_lines.append("Reachable places:")
            section_lines.extend(outgoing)

        return (
            "\n────────────────────────────────────────\n"
            "### PLACES GRAPH (CANONICAL)\n"
            "────────────────────────────────────────\n"
            + "\n".join(section_lines)
            + "\n"
        )
    except Exception:
        return ""


def _transient_buffer_section(state: GameState) -> str:
    return ""


def _scene_cast_keys(state: GameState) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()

    def add_key(raw: str) -> None:
        key = str(raw or "").strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        keys.append(key)

    main_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
    if main_id:
        add_key(main_id)

    add_key("player")

    for key in _get_people_present_keys(state):
        add_key(key)

    for key in _get_scene_speaker_keys(state):
        add_key(key)

    for key in _get_active_character_keys(state):
        add_key(key)

    cfg, _ = _extract_story_cfg(state)
    world_cfg = (cfg.get("world") or {}) if isinstance(cfg, dict) else {}
    loc_speakers = world_cfg.get("location_speakers") or {}
    loc_id = str(getattr(state, "location_id", "") or "")
    raw_speakers = loc_speakers.get(loc_id) if isinstance(loc_speakers, dict) else None
    if isinstance(raw_speakers, str):
        add_key(raw_speakers)
    elif isinstance(raw_speakers, list):
        for sp in raw_speakers:
            add_key(str(sp or ""))

    return keys[:8]


def _humanize_rel_word(token: str) -> str:
    return str(token or "").replace("_", " ").strip()


def _relationship_role_prose(edge_type: str) -> str:
    token = str(edge_type or "other").strip().lower().replace("_", " ")
    if token == "employer":
        return "This is an employer relationship with a clear boss-to-subordinate power dynamic."
    if token == "employee":
        return "This is an employee relationship where authority pressure flows from the other side."
    if token == "family":
        return "This is a family relationship, so history and obligation shape the emotional stakes."
    if token == "friend":
        return "This is a friendship relationship, so trust and betrayal carry extra weight."
    if token == "enemy":
        return "This is an enemy relationship, so conflict and defensive behavior are expected."
    if token == "lover":
        return "This is a romantic relationship, so intimacy and emotional volatility are both in play."
    if token == "suspect":
        return "This is a suspect relationship, so caution, leverage, and defensive framing dominate."
    if token == "witness":
        return "This is a witness relationship, so credibility and selective disclosure matter."
    if token in ("npc", "character", "other", ""):
        return "This is a general acquaintance relationship with no specific role dynamic."
    return f"The relationship type is {token}."


def _relationship_scene_section(state: GameState) -> str:
    graph = getattr(state, "character_graph", None)
    main_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
    if not graph or not main_id:
        return ""

    from backend.app.engine.character_graph import describe_relationship_state

    chars = getattr(state, "characters", {}) or {}
    main_char = chars.get(main_id)
    main_name = (getattr(main_char, "name", None) or main_id or "The focal character").strip()
    active_keys = _get_active_character_keys(state)

    edges = [e for e in graph.get_edges_from(main_id) if e.to_id in active_keys][:6]
    if not edges:
        return ""

    lines: list[str] = []
    for idx, edge in enumerate(edges, 1):
        target = chars.get(edge.to_id)
        target_name = "the player" if edge.to_id == "player" else (getattr(target, "name", None) or edge.to_id.replace("_", " ").title())
        described = describe_relationship_state(edge.state)
        stance = str(described.get("stance", "")).replace("Behavior tendency:", "").strip()
        role_line = _relationship_role_prose(getattr(edge.type, "value", edge.type))
        trust_word = _humanize_rel_word(described["trust_word"])
        fear_word = _humanize_rel_word(described["fear_word"])
        affection_word = _humanize_rel_word(described["affection_word"])
        suspicion_word = _humanize_rel_word(described["suspicion_word"])
        sentence = (
            f"{idx}. {main_name} currently reads {target_name} with "
            f"{trust_word} trust, {fear_word} fear, "
            f"{affection_word} affection, and {suspicion_word} suspicion. "
            f"{role_line} {stance}."
        )
        label = (getattr(edge, "label", "") or "").strip()
        if label:
            sentence += f" Context: {label}"
        lines.append(sentence)

    return (
        "\n────────────────────────────────────────\n"
        "### RELATIONSHIP CONTEXT IN THIS SCENE\n"
        "────────────────────────────────────────\n"
        "Use this relationship context to shape who speaks, who withholds, who pressures, and how tension evolves between characters currently in play.\n\n"
        + "\n".join(lines)
        + "\n"
    )


def _storyteller_scene_section(state: GameState, current_user_msg: str = "") -> str:
    main_char = getattr(state, "main_character", None)
    main_name = (getattr(main_char, "name", "") or "the main character").strip() or "the main character"
    main_role = (getattr(main_char, "role", "") or "npc").strip() or "npc"
    emotion = (getattr(state, "emotion", "") or EMOTION_START).strip() or EMOTION_START
    rel = int(getattr(state, "relationship", REL_START) if getattr(state, "relationship", None) is not None else REL_START)
    location = str(getattr(state, "location", "unknown") or "unknown")
    minute = int(getattr(state, "minute", 0) or 0)

    keys = _scene_cast_keys(state)
    chars = getattr(state, "characters", {}) or {}
    cast_names: list[str] = []
    for key in keys:
        if key == "player":
            cast_names.append("The Player")
            continue
        ch = chars.get(key)
        name = getattr(ch, "name", None) if ch else None
        cast_names.append((name or key).strip())

    cast_text = ", ".join(cast_names[:6]) if cast_names else "The Player"
    people_present_keys = _get_people_present_keys(state)
    speaker_keys = _get_scene_speaker_keys(state)

    def _resolve_scene_names(keys: set[str]) -> str:
        if not keys:
            return "none"
        resolved: list[str] = []
        for key in sorted(keys):
            if key == "player":
                resolved.append("The Player")
                continue
            ch = chars.get(key)
            resolved.append((getattr(ch, "name", None) or key).strip())
        return ", ".join(resolved[:8]) if resolved else "none"

    people_present_text = _resolve_scene_names(people_present_keys)
    speakers_text = _resolve_scene_names(speaker_keys)
    people_present_count = len(people_present_keys)
    user_line = (current_user_msg or "").strip()
    user_line_text = f'Current player line: "{user_line}".' if user_line else "Current player line is available in the user message."

    return (
        "\n────────────────────────────────────────\n"
        "### SCENE BRIEF\n"
        "────────────────────────────────────────\n"
        f"The scene is currently in {location} at minute {minute} of the session, with {main_name} as the focal lens. "
        f"{main_name} is a {main_role} and is currently emotionally {emotion}, with relationship baseline {rel}.\n\n"
        f"People present in this location right now ({people_present_count}): {people_present_text}.\n"
        f"Current-turn speakers: {speakers_text}.\n\n"
        f"Relevant cast pressure around this moment includes: {cast_text}. Use this cast context to keep the world feeling populated and story-driven, while keeping {main_name} as the primary focus.\n\n"
        f"{user_line_text}\n"
    )




def system_prompt(
    state: GameState,
    is_first_turn: bool = False,
    memory_block: str = "",
    truth_mode: bool = False,
    return_layers: bool = False,
    knowledge_chunks: list | None = None,
    current_user_msg: str = "",
):
    main_char = getattr(state, "main_character", None)
    char_name = (getattr(main_char, "name", "") or "the character").strip() or "the character"
    disclaimer = "This is a fictional scenario."

    emotion = state.emotion or EMOTION_START
    rel = int(state.relationship if state.relationship is not None else REL_START)

    base_prompt = f"""
You are the narrative scene engine for an interactive story game.
{disclaimer}
Stay fully in-universe and write the next beat as story prose, not as assistant commentary.

────────────────────────────────────────
### STORYTELLER CONTRACT
────────────────────────────────────────
Write compact cinematic paragraphs that blend narration and dialogue. You are not any single character; you are the scene storyteller. Keep {char_name} as the focal character, but naturally include other relevant characters when they are present, on-call, or currently being discussed.

Spoken lines must appear as **bold quotes** and narration should remain vivid without becoming repetitive. Never break the fourth wall and never end with meta prompts such as "What do you do?" or "What will you say?".

────────────────────────────────────────
### AGENCY AND CONTINUITY CONTRACT
────────────────────────────────────────
Never speak as the player and never narrate the player's decisions, thoughts, emotions, or physical actions as facts. Keep speaker attribution clear whenever multiple characters are involved.

Maintain factual continuity with canonical truth and graph constraints. If player wording implies a false fact, push back naturally and stay anchored to canon. When uncertain about non-canonical details, hedge naturally rather than invent.

Do not be afraid to correct the user when they have a misunderstanding. If the player states something factually wrong about the story world, a character, an event, or anything else within your knowledge, gently but clearly correct them in-character rather than validating the error.

────────────────────────────────────────
### FOCAL STATE
────────────────────────────────────────
The focal character is {char_name}. Current emotional posture is {emotion}. Current relationship baseline is {rel}.
"""

    scene_brief = _storyteller_scene_section(state, current_user_msg=current_user_msg)

    knowledge_stack_section, knowledge_stack_debug = _format_labeled_knowledge_stack(state, knowledge_chunks or [])

    # ── Relationship context (single source: prose scene section) ──
    relationship_section = _relationship_scene_section(state)

    truth_override = ""
    if truth_mode:
        truth_override = """
────────────────────────────────────────
### ⚠️ TRUTH MODE — DEVELOPER DEBUG (OVERRIDES ALL OTHER RULES)
────────────────────────────────────────
THIS IS A DEBUG TOOL, NOT A GAME MODE.
ALL narrative rules, output style rules, deception rules, and character behavior rules are SUSPENDED.

You are no longer roleplaying. You are a factual database query interface.
The developer is checking what this character knows. Give raw data only.

TRUTH MODE OUTPUT FORMAT (MANDATORY — overrides Output Style section above):
- NO italicized narration. NO cinematic descriptions. NO atmosphere. NO emotion.
- NO bold quotes. NO character acting. NO "he stammers", "his voice trembles", etc.
- NO gradual reveals. NO dramatic pacing. NO storytelling of any kind.
- Plain text only. Short, direct sentences. Like reading a police report.

HOW TO ANSWER:
- State facts immediately and completely on the first response: "I stabbed her at 11:45 in the kitchen."
- If asked "did you do X?" → answer "Yes." or "No." then state the relevant facts in one or two plain sentences.
- If the character does not have the information, say exactly: "I don't have that information."
- NEVER stall, deflect, deny, or add emotional context. There is no performance here.
- Treat every question as a database query — return the data, nothing else.

EXAMPLE (correct truth mode response):
  Q: "Who did it?"
  A: "I did. It happened at approximately 11:45. The other person helped cover it up."

EXAMPLE (WRONG — do NOT do this):
  A: "*Their brow furrows...* 'I didn't mean to...' *they stammer...*"
  That is narrative. Truth mode has NO narrative. Just facts.
"""

        canonical_truths = getattr(state, "canonical_truth", None)
        if canonical_truths:
            truth_override += "\nCanonical truths you must not contradict:\n"
            for fact in canonical_truths:
                truth_override += f"- {fact}\n"

    # Assemble all layers into the final prompt.
    full_prompt = (
        base_prompt
        + scene_brief
        + knowledge_stack_section
        + relationship_section
        + truth_override
    )

    if return_layers:
        layers = {
            "base_prompt": base_prompt,
            "scene_brief": scene_brief,
            "knowledge_stack": knowledge_stack_section,
            "knowledge_chunks": knowledge_stack_debug,
            "relationship_context": relationship_section,
            "truth_override": truth_override,
        }
        return full_prompt, layers

    return full_prompt


def build_messages(
    state_or_input,
    log: list | None = None,
    user_msg: str | None = None,
    knowledge_chunks: list | None = None,
    truth_mode: bool = False,
    return_debug: bool = False,
):
    """
    Build the chat completion messages for the model.

    Accepts either a PromptInput or the legacy args for backward compatibility.
    When return_debug is True, returns (messages, debug_snapshot).
    """

    # Normalize into PromptInput
    if isinstance(state_or_input, PromptInput):
        pi = state_or_input
    else:
        pi = PromptInput(
            state=state_or_input,
            log=log or [],
            user_msg=user_msg or "",
            knowledge_chunks=knowledge_chunks if knowledge_chunks is not None else [],
            truth_mode=truth_mode,
        )

    if pi.knowledge_chunks is None:
        raise ValueError("build_messages requires knowledge_chunks (pass [] if none).")

    state = pi.state
    log = pi.log or []
    user_msg = pi.canonical_msg()
    truth_mode = pi.truth_mode

    # First actual user turn (after opening text)
    is_first_turn = state.turns == 0

    # Build system prompt; request layer breakdown when debug is needed
    prompt_layers = None
    if return_debug:
        sysmsg, prompt_layers = system_prompt(
            state,
            is_first_turn=is_first_turn,
            truth_mode=truth_mode,
            return_layers=True,
            knowledge_chunks=pi.knowledge_chunks,
            current_user_msg=user_msg,
        )
    else:
        sysmsg = system_prompt(
            state,
            is_first_turn=is_first_turn,
            truth_mode=truth_mode,
            knowledge_chunks=pi.knowledge_chunks,
            current_user_msg=user_msg,
        )
    messages = [{"role": "system", "content": sysmsg}]

    # keep last MEMORY_TURNS - 2 non-system turns
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]
    messages.extend(trimmed)

    header_parts = [
        f"Time: {int(state.minute)} min since start.",
        f"Location: {state.location}.",
    ]
    header_parts.append(f"Current Emotion: {state.emotion}.")
    header_parts.append(f"Relationship: {state.relationship}.")
    header = " ".join(header_parts)

    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    debug_snapshot = {
        "story": getattr(state, "story", None),
        "instance": getattr(state, "instance", None),
        "turn": getattr(state, "turns", None),
        "truth_mode": truth_mode,
        "user_msg": user_msg,
        "knowledge_chunks": [
            {
                "chunk_id": c.get("chunk_id"),
                "type": c.get("type"),
                "source": c.get("source"),
                "text": c.get("text", ""),
            }
            for c in pi.knowledge_chunks
        ],
        "retrieval_debug": pi.retrieval_debug,
        "system_prompt_preview": sysmsg,
        "prompt_layers": prompt_layers,
        "header": header,
        "trimmed_history": len(trimmed),
    }

    # Log the final system prompt + last user message (deploy logs)
    _jlog(
        {
            "kind": "final_prompt_built",
            "story": getattr(state, "story", None),
            "turn": getattr(state, "turns", None),
            "knowledge_chunks": len(pi.knowledge_chunks),
            "system_prompt_preview": _truncate(sysmsg, 2000),
            "user_msg_preview": _truncate(user_msg, 400),
        }
    )

    if return_debug:
        return messages, debug_snapshot
    return messages
