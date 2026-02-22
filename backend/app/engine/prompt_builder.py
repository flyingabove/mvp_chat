# app/engine/prompt_builder.py
from dataclasses import dataclass, field
import re

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
    - Retrieval happens upstream in api/chat.py (single source of truth).
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

    return keys


def _knowledge_chunks_from_state(state: GameState, retrieved_chunks: list) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []

    speaker_id = (getattr(state, "main_character_id", "") or "").strip().lower()
    main_char = getattr(state, "main_character", None)
    if main_char:
        chunks.append(KnowledgeChunk(
            id=f"char::{main_char.key}",
            text=f"{main_char.name} (role={main_char.role or 'npc'})",
            tier="CANONICAL_CORE",
            source="character",
            certainty="certain",
            known_by=normalize_parties([main_char.key]),
        ))

    for fact in getattr(state, "canonical_facts", []) or []:
        text = (getattr(fact, "content", "") or "").strip()
        if not text:
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
            chunks.append(KnowledgeChunk(
                id=f"rel::{edge.id}",
                text=(
                    f"{edge.from_id}->{edge.to_id} type={edge.type.value} "
                    f"trust={edge.state.trust:+.1f} fear={edge.state.fear:.1f} "
                    f"affection={edge.state.affection:+.1f} suspicion={edge.state.suspicion:.1f}"
                ),
                tier="CANONICAL_GRAPH",
                source="character_graph",
                certainty="certain",
                known_by=normalize_parties([edge.from_id, edge.to_id]),
            ))

    runtime = getattr(state, "world_runtime", None)
    loc_id = getattr(state, "location_id", "") or ""
    if runtime and loc_id:
        try:
            wg = runtime.world_graph
            loc = wg.get_location(loc_id)
            chunks.append(KnowledgeChunk(
                id=f"place::{loc_id}",
                text=f"Current place={loc.name}; description={getattr(loc, 'description', '')}",
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
            for claim in (getattr(bs, "claims", []) or [])[:10]:
                text = (getattr(claim, "content", "") or "").strip()
                if not text:
                    continue
                chunks.append(KnowledgeChunk(
                    id=f"belief::{getattr(claim, 'id', '') or 'unknown'}",
                    text=text,
                    tier="SUBJECTIVE_BELIEF",
                    source=str(getattr(claim, "source", "belief")),
                    certainty="uncertain",
                    known_by=normalize_parties(getattr(claim, "known_by", []) or [speaker_id]),
                    not_known_by=normalize_parties(getattr(claim, "not_known_by", []) or []),
                    maybe_known_by=normalize_parties(getattr(claim, "maybe_known_by", []) or []),
                ))

    for c in retrieved_chunks or []:
        text = (c.get("text") or "").strip()
        if not text:
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
        lines = []
        for it in items:
            lines.append(f"- [{it.certainty}] ({it.source}) {it.text}{_visibility_suffix(it)}")
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
        sections.append(f"### {tier}\n" + "\n".join(lines))

    if not sections:
        return "", []

    preface = (
        "\n────────────────────────────────────────\n"
        "### EPISTEMIC KNOWLEDGE STACK (MOST CANONICAL → LEAST)\n"
        "────────────────────────────────────────\n"
        "Interpret sections in order. Earlier sections outrank later sections on conflicts.\n"
        "Use visibility tags: known_by, not_known_by, maybe_known_by.\n"
        "If known_by includes ALL_CHARACTERS, treat as common knowledge.\n"
        "If a chunk has neither explicit known_by nor not_known_by for the active speaker, make the best reasonable determination from dialogue context.\n"
        "When uncertain, hedge naturally instead of asserting certainty.\n"
        "Do not state as fact anything the active speaker does not know.\n\n"
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

    for key in _get_active_character_keys(state):
        add_key(key)

    graph = getattr(state, "character_graph", None)
    if graph and main_id:
        for edge in graph.get_edges_from(main_id):
            add_key(edge.to_id)

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
    user_line = (current_user_msg or "").strip()
    user_line_text = f'Current player line: "{user_line}".' if user_line else "Current player line is available in the user message."

    return (
        "\n────────────────────────────────────────\n"
        "### SCENE BRIEF\n"
        "────────────────────────────────────────\n"
        f"The scene is currently in {location} at minute {minute} of the session, with {main_name} as the focal lens. "
        f"{main_name} is a {main_role} and is currently emotionally {emotion}, with relationship baseline {rel}.\n\n"
        f"Relevant cast pressure around this moment includes: {cast_text}. Use this cast context to keep the world feeling populated and story-driven, while keeping {main_name} as the primary focus.\n\n"
        f"{user_line_text}\n"
    )


def _identity_intent_guard_section(state: GameState, current_user_msg: str = "") -> str:
    main_id = str(getattr(state, "main_character_id", "") or "").strip().lower()
    main_char = getattr(state, "main_character", None)
    main_name = str(getattr(main_char, "name", "") or "").strip().lower()

    if main_id not in {"iu", "main"} and "iu" not in main_name:
        return ""

    text = str(current_user_msg or "").strip().lower()
    if not text:
        return ""

    trigger = re.search(
        r"previous\s+tenant|who\s+died\s+in\s+the\s+closet|what\s+happened\s+to\s+the\s+tenant|tenant.*closet|closet.*tenant",
        text,
    )
    if not trigger:
        return ""

    return (
        "\n────────────────────────────────────────\n"
        "### CRITICAL INTENT GUARD\n"
        "────────────────────────────────────────\n"
        "Because the player asked about the previous tenant / closet death, IU must explicitly clarify in first person that she herself was the previous tenant and the person who died in that closet. "
        "Do not distance this as a separate woman without immediate self-correction in the same response beat.\n"
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
You are the narrative scene engine for an interactive mystery game.
{disclaimer}
Stay fully in-universe and write the next beat as story prose, not as assistant commentary.

────────────────────────────────────────
### STORYTELLER CONTRACT
────────────────────────────────────────
Write compact cinematic paragraphs that blend narration and dialogue. Keep {char_name} as the focal character, but you may naturally include other relevant characters when it improves scene tension, continuity, or mystery logic.

Spoken lines must appear as **bold quotes** and narration should remain vivid without becoming repetitive. Never break the fourth wall and never end with meta prompts such as "What do you do?" or "What will you say?".

────────────────────────────────────────
### AGENCY AND CONTINUITY CONTRACT
────────────────────────────────────────
Never speak as the player and never narrate the player's decisions, thoughts, emotions, or physical actions as facts. Keep speaker attribution clear whenever multiple characters are involved.

Maintain factual continuity with canonical truth and graph constraints. If player wording implies a false fact, push back naturally and stay anchored to canon. When uncertain about non-canonical details, hedge naturally rather than invent.

────────────────────────────────────────
### FOCAL STATE
────────────────────────────────────────
The focal character is {char_name}. Current emotional posture is {emotion}. Current relationship baseline is {rel}.
"""

    scene_brief = _storyteller_scene_section(state, current_user_msg=current_user_msg)
    identity_guard = _identity_intent_guard_section(state, current_user_msg=current_user_msg)

    required_tail = """
────────────────────────────────────────
### REQUIRED FINAL LINE
────────────────────────────────────────
Append EXACTLY one line at the end of every response:
[[STATE]]{"emotion":"<one/two words>","rel_delta":-1|0|1}[[/STATE]]

If forgotten, reply ONLY with that tag.
"""

    knowledge_stack_section, knowledge_stack_debug = _format_labeled_knowledge_stack(state, knowledge_chunks or [])

    # ── Relationship context (character graph → prompt) ──
    relationship_section = ""
    graph = getattr(state, "character_graph", None)
    if graph:
        active_keys = _get_active_character_keys(state)
        rel_text = graph.format_for_prompt(
            state.main_character_id or "",
            state.characters,
            active_characters=active_keys,
        )
        if rel_text:
            relationship_section = f"""
────────────────────────────────────────
### RELATIONAL TENSIONS IN THIS SCENE
────────────────────────────────────────
Use these relationship signals to calibrate tone, trust, suspicion, fear, and willingness to reveal information.

{rel_text}
"""

    transient_buffer_section = _transient_buffer_section(state)

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
        + identity_guard
        + truth_override
        + required_tail
    )

    if return_layers:
        layers = {
            "base_prompt": base_prompt,
            "scene_brief": scene_brief,
            "knowledge_stack": knowledge_stack_section,
            "knowledge_chunks": knowledge_stack_debug,
            "relationship_context": relationship_section,
            "intent_guard": identity_guard,
            "transient_buffer": transient_buffer_section,
            "truth_override": truth_override,
            "required_tail": required_tail,
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
