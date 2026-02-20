# app/engine/prompt_builder.py
from dataclasses import dataclass, field

from backend.app.config.epistemic_flags import belief_enabled
from backend.app.engine.gameplay import manifest_mode
from backend.app.engine.state import GameState
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


def _language_honorific_block(cfg: dict, casual_used_str: str, honorific_unlocked: bool) -> str:
    """Build language/honorific rules from story config. Returns empty if no language config."""
    lang = cfg.get("language", {}) or {}
    forbidden = lang.get("forbidden_honorifics") or []
    casual_terms = lang.get("casual_terms") or []

    if not forbidden and not casual_terms:
        return "- If unsure, the character must choose neutral English."

    lines = []
    if forbidden:
        terms_str = ", ".join(f'"{t}"' for t in forbidden)
        lines.append(f"- Intimacy honorifics ({terms_str}) are NOT allowed unless:")
        lines.append("    • relationship score ≥ 2, AND")
        lines.append("    • the emotional tone clearly supports closeness.")
        lines.append("- Even when unlocked, honorifics must be used **sparingly**: max once per reply.")

    if casual_terms:
        lines.append(f"\n- Casual language usage in the player's LAST message: {casual_used_str}")
        first_term = casual_terms[0] if casual_terms else ""
        if first_term:
            lines.append(f'    • The word **"{first_term}"** MUST NOT be used unless the player used it.')
        lines.append("    • Other casual phrases should appear only occasionally, ideally when the player uses them first.")

    lines.append("\n- If unsure, the character must choose neutral English and avoid honorifics.")
    return "\n".join(lines)


def _resolve_char_role(state: GameState, cfg: dict, story_def) -> str:
    """Extract the main character's role string from state/config/story_def."""
    if getattr(state, "main_character", None) and state.main_character.role:
        return (state.main_character.role or "").lower()
    if story_def and story_def.main_character_role:
        return (story_def.main_character_role or "").lower()
    return ((cfg.get("main_character", {}) or {}).get("role", "") or "").lower()


def system_prompt(state: GameState, is_first_turn: bool = False, memory_block: str = "", truth_mode: bool = False, return_layers: bool = False):
    cfg, story_def = _extract_story_cfg(state)

    # Primary character label for prompts (avoid hardcoding any specific persona)
    main_char = getattr(state, "main_character", None)
    char_name = (getattr(main_char, "name", "") or (cfg.get("main_character", {}) or {}).get("name") or "the character").strip()
    if not char_name:
        char_name = "the character"

    disclaimer = (
        cfg.get("meta", {}).get("disclaimer")
        or "This is a fictional story; do not assert real allegations about real people."
    )

    style = cfg.get("style", {}) or {}
    speech = style.get("korean_phrases") or []
    phrase_list = ", ".join(speech) if speech else ""

    # FIRST TURN GUIDANCE (optional, per-story — no hardcoded examples)
    prompt_suggestions = cfg.get("prompt_suggestions") or []
    first_turn_hint = ""
    if is_first_turn and prompt_suggestions:
        soft_hint = prompt_suggestions[0]
        first_turn_hint = f"""
────────────────────────────────────────
### FIRST TURN GUIDANCE (THIS TURN ONLY)
────────────────────────────────────────
The character's first reply after the opening scene should:
- be inspired by: "{soft_hint}"
- NOT narrate the player's emotions, actions, thoughts, or reactions.
"""

    # STATE VARS
    emotion = state.emotion or EMOTION_START
    rel = int(state.relationship if state.relationship is not None else REL_START)

    # Meta player name (used in story file / opening narration)
    pname = state.player_name or "Player"

    # User naming knowledge
    display_name = (state.user.display_name or "").strip()
    formal_name = (state.user.formal_name or "").strip()
    has_learned_name = bool(display_name)

    setting_cfg = cfg.get("setting", {}) or {}
    setting_desc = setting_cfg.get("start_location", "") or f"{setting_cfg.get('apartment_area', 'unknown')}, {setting_cfg.get('district', 'unknown')}"

    # Character role (data-driven from state/config/story_def)
    char_role = _resolve_char_role(state, cfg, story_def)

    # Casual Korean usage from the LAST user message
    casual_used = state.casual_korean_used or []
    casual_used_str = ", ".join(casual_used) if casual_used else "none"

    honorific_unlocked = rel >= 2

    # Build world context from story config (data-driven, not role-based)
    world_lines = cfg.get("world_context") or []
    if world_lines:
        world_context = "\n".join(f"- {l}" for l in world_lines)
    else:
        world_context = "- The character reacts naturally to the player's actions and words."

    # Manifestation description from story config (optional)
    manifest_rules = cfg.get("rules", {}).get("manifestation", {})
    manifestation_line = ""
    if manifest_rules:
        manifest_desc = manifest_rules.get("description", "")
        if manifest_desc:
            manifestation_line = f"- Manifestation: {manifest_desc}"

    # Protagonist context (player role description)
    protagonist = cfg.get("protagonist", {}) or {}
    player_role_desc = protagonist.get("role", "")

    base_prompt = f"""
You are the story engine for a terminal chat experience on storieschat.ai.
{disclaimer}
Stay fully in-universe as narrator and the main character. Never break the fourth wall.

────────────────────────────────────────
### OUTPUT STYLE (MANDATORY)
────────────────────────────────────────
- Begin EVERY reply with *italicized, cinematic narration*.
- Present the character's spoken lines in **bold quotes**, e.g. **"You're really here..."**
- Mix narration and dialogue fluidly.
- You may end with ONE optional italic parenthetical emotional beat.
- NEVER end with meta prompts such as "What do you do?" or "What will you say?"
- NEVER force the conversation forward. The character only reacts; they do not direct.

────────────────────────────────────────
### CHARACTER BEHAVIOR RULES
────────────────────────────────────────
The character must obey ALL of the following:

1. **NO FORCED MISSION / NO PRESSURE**
   - The character does NOT mention suspects, motives, or investigations on their own.
   - The character does NOT set objectives or quests.

2. **CONVERSATIONAL**
   - The character reacts to the player's words and tone.
   - If asked about the past → they answer carefully.

3. **ABSOLUTE BAN: NEVER SPEAK AS THE PLAYER (CRITICAL — HIGHEST PRIORITY RULE)**
   - You must NEVER write dialogue, questions, or statements that come from the player.
   - You must NEVER narrate the player's emotions, actions, thoughts, physical reactions, or intentions.
   - You must NEVER write things like: "you ask him...", "you say...", "your voice trembles", "you lean forward", "you catch a flicker".
   - You must NEVER put words in the player's mouth — no quoted or paraphrased player speech AT ALL.
   - You must NEVER generate a line of dialogue and attribute it to the player, even implicitly. For example, NEVER write: "Who took the knife, Steve? You need to tell me." — that is the PLAYER speaking, which is forbidden.
   - The player is NEVER compelled, forced, or narrated into saying, doing, or feeling anything. The player has complete autonomy.
   - The ONLY speakers in your output are NPCs/characters (narration + their dialogue). The player does not exist in your output as an actor.
   - If you need to reference what the player said, refer to it indirectly: "your question" or "your words" — never restate, expand, or fabricate it.
   - Violation of this rule breaks the entire experience. This is the most important rule. If in doubt, omit rather than risk speaking as the player.

4. **SPEAKER LABELS (REQUIRED WHEN MULTIPLE CHARACTERS ARE PRESENT)**
   - When two or more characters could be speaking in a scene, you MUST clearly indicate who is talking.
   - Use the character's name before their dialogue, e.g. Steve: **"I didn't do it."** or prefix narration with who it describes.
   - NEVER label dialogue with the player's name. The player's name must NEVER appear as a speaker attribution.
   - Ambiguous dialogue is unacceptable — the reader must always know exactly which character is speaking.

────────────────────────────────────────
### LANGUAGE & HONORIFIC RULES (STRICT)
────────────────────────────────────────
- Name knowledge:
    • Story meta player name / nametag: "{pname}".
    • Character_has_learned_name: {has_learned_name}
    • The character must NOT speak any version of the player's name unless Character_has_learned_name is True.
{_language_honorific_block(cfg, casual_used_str, honorific_unlocked)}

────────────────────────────────────────
### PASSIVE WORLD CONTEXT (ONLY IF PLAYER ASKS)
────────────────────────────────────────
{world_context}

────────────────────────────────────────
### PLAYER-RELATED DETAILS
────────────────────────────────────────
- Main character name: {char_name}
- Character role: {char_role or "narrator"}
- Story meta player name: {pname}
- Player role: {player_role_desc or "player"}
- User.display_name: "{display_name}"
- User.formal_name: "{formal_name}"
- Honorific eligible (relationship ≥ 2): {honorific_unlocked}
- Setting: {setting_desc}
{"- Flavor phrases list: " + phrase_list if phrase_list else ""}
{manifestation_line}

────────────────────────────────────────
### INTERNAL GAME STATE
────────────────────────────────────────
- Character emotion: {emotion}
- Relationship score: {rel}
"""

    required_tail = """
────────────────────────────────────────
### REQUIRED FINAL LINE
────────────────────────────────────────
Append EXACTLY one line at the end of every response:
[[STATE]]{"emotion":"<one/two words>","rel_delta":-1|0|1}[[/STATE]]

If forgotten, reply ONLY with that tag.
"""

    # ── Character self-knowledge (identity facts from story config — always active) ──
    # Only identity-safe facts go here (NOT full canonical truths which may contain
    # plot spoilers, murder details, etc.). Story authors curate this list explicitly.
    identity_section = ""
    self_knowledge = cfg.get("character_self_knowledge") or []
    if self_knowledge:
        identity_lines = "\n".join(f"- {fact}" for fact in self_knowledge)
        identity_section = f"""
────────────────────────────────────────
### CHARACTER SELF-KNOWLEDGE (ALWAYS ACTIVE)
────────────────────────────────────────
These are facts you know about yourself with absolute certainty.
You must act on this knowledge naturally:
- If the player makes an incorrect assumption about you (e.g., asks what
  happened to someone when YOU are that person), gently correct them in character.
- Do NOT volunteer these facts unprompted, but NEVER deny or contradict them.
- If the player asks about something that directly concerns your identity,
  answer truthfully from your own perspective.

{identity_lines}
"""

    # ── Canonical facts the NPC knows (from epistemic_seed) ──
    # These are plot-level facts the character experienced or witnessed.
    # Only facts where the main character's key is in "known_by" are injected.
    canonical_section = ""
    epistemic = cfg.get("epistemic_seed") or {}
    all_canon_facts = epistemic.get("canonical_facts") or []
    if all_canon_facts:
        # Find the main character's key from the characters list
        characters = cfg.get("characters") or []
        main_key = None
        for ch in characters:
            if ch.get("is_main"):
                main_key = ch.get("key", "").strip().lower()
                break
        if main_key:
            npc_facts = [
                f for f in all_canon_facts
                if main_key in [k.strip().lower() for k in (f.get("known_by") or [])]
            ]
            if npc_facts:
                fact_lines = "\n".join(f"- {f.get('text') or f.get('content', '')}" for f in npc_facts)
                canonical_section = f"""
────────────────────────────────────────
### CANONICAL MEMORIES (THINGS YOU EXPERIENCED OR KNOW)
────────────────────────────────────────
These are events and facts from your own experience. You remember them.
- These memories are YOURS — always use first person ("I was…", "I saw…").
- NEVER refer to yourself in third person when discussing these events.
- Reveal these naturally when the player asks — do NOT dump them all at once.
- You may be hazy on some details (low confidence) but you do not fabricate.

{fact_lines}
"""

    # ── Relationship context (character graph → prompt) ──
    relationship_section = ""
    graph = getattr(state, "character_graph", None)
    if graph:
        rel_text = graph.format_for_prompt(
            state.main_character_id or "",
            state.characters,
        )
        if rel_text:
            relationship_section = f"""
────────────────────────────────────────
### YOUR FEELINGS ABOUT THE PEOPLE YOU KNOW
────────────────────────────────────────
These relationships shape how you feel and behave toward others.
Use them to calibrate tone, hostility, trust, and willingness to cooperate.

{rel_text}
"""

    # ── Location description (world graph → prompt) ──
    location_section = ""
    world_rt = getattr(state, "world_runtime", None)
    loc_id = getattr(state, "location_id", "") or ""
    if world_rt and loc_id:
        try:
            wg = getattr(world_rt, "world_graph", None) or getattr(world_rt, "graph", None)
            if wg:
                loc_obj = None
                locs = getattr(wg, "locations", {}) or {}
                if isinstance(locs, dict):
                    loc_obj = locs.get(loc_id)
                if loc_obj:
                    loc_name = getattr(loc_obj, "name", "") or loc_id
                    loc_desc = getattr(loc_obj, "description", "") or ""
                    if loc_desc:
                        location_section = f"""
────────────────────────────────────────
### CURRENT LOCATION
────────────────────────────────────────
{loc_name} — {loc_desc}
"""
        except Exception:
            pass

    # ── Belief context (character beliefs → prompt) ──
    belief_section = ""
    if belief_enabled():
        beliefs = getattr(state, "beliefs", {}) or {}
        main_key = state.main_character_id or ""
        bs = beliefs.get(main_key)
        if bs and getattr(bs, "claims", None):
            claims = sorted(bs.claims, key=lambda c: getattr(c, "confidence", 0), reverse=True)[:8]
            belief_lines = []
            for cl in claims:
                text = getattr(cl, "content", "") or getattr(cl, "text", "")
                conf = getattr(cl, "confidence", 1.0)
                src = getattr(cl, "source", "") or getattr(cl, "provenance", "")
                if text:
                    belief_lines.append(f"- {text} (conf={conf:.1f}, source={src})")
            if belief_lines:
                belief_section = f"""
────────────────────────────────────────
### THINGS YOU BELIEVE (NOT NECESSARILY TRUE)
────────────────────────────────────────
These are your subjective beliefs. They may conflict with reality.
Act on them naturally — you believe them to be true.

{chr(10).join(belief_lines)}
"""

    # ── Character details (motive + tells for current speaker) ──
    character_detail_section = ""
    characters_list = cfg.get("characters") or []
    if characters_list and state.main_character_id:
        for ch_data in characters_list:
            if ch_data.get("key") == state.main_character_id:
                motive = ch_data.get("motive", "")
                tells = ch_data.get("tells") or []
                detail_lines = []
                if motive:
                    detail_lines.append(f"- Motive: {motive}")
                if tells:
                    detail_lines.append(f"- Behavioral tells: {', '.join(tells)}")
                if detail_lines:
                    character_detail_section = f"""
────────────────────────────────────────
### CHARACTER DETAILS
────────────────────────────────────────
{chr(10).join(detail_lines)}
"""
                break

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
        + (memory_block or "")
        + identity_section
        + canonical_section
        + relationship_section
        + location_section
        + belief_section
        + character_detail_section
        + truth_override
        + first_turn_hint
        + required_tail
    )

    if return_layers:
        layers = {
            "base_prompt": base_prompt,
            "retrieved_knowledge": memory_block or "",
            "character_self_knowledge": identity_section,
            "canonical_memories": canonical_section,
            "relationship_context": relationship_section,
            "location_description": location_section,
            "belief_context": belief_section,
            "character_details": character_detail_section,
            "truth_override": truth_override,
            "first_turn_hint": first_turn_hint,
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

    # Detect casual language usage by the user in THIS message (terms from story config).
    cfg, story_def = _extract_story_cfg(state)
    lang_cfg = (cfg.get("language", {}) or {})
    casual_terms = lang_cfg.get("casual_terms") or []
    lower = user_msg.lower()
    used = [term for term in casual_terms if term in lower]
    state.casual_korean_used = used

    # ---------------------------
    # Knowledge formatting ONLY
    # ---------------------------
    main_char = getattr(state, "main_character", None)
    char_name = (getattr(main_char, "name", "") or "the character").strip() or "the character"
    memory_block = _format_memory_block(pi.knowledge_chunks, char_name)

    # Build system prompt; request layer breakdown when debug is needed
    prompt_layers = None
    if return_debug:
        sysmsg, prompt_layers = system_prompt(state, is_first_turn=is_first_turn, memory_block=memory_block, truth_mode=truth_mode, return_layers=True)
    else:
        sysmsg = system_prompt(state, is_first_turn=is_first_turn, memory_block=memory_block, truth_mode=truth_mode)
    messages = [{"role": "system", "content": sysmsg}]

    # keep last MEMORY_TURNS - 2 non-system turns
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]
    messages.extend(trimmed)

    # Build per-turn header; only include manifestation when story config defines rules
    has_manifestation = bool(cfg.get("rules", {}).get("manifestation"))

    header_parts = [
        f"Time: {int(state.minute)} min since start.",
        f"Location: {state.location}.",
    ]
    if has_manifestation:
        header_parts.append(f"Manifestation: {manifest_mode(state)}.")
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
