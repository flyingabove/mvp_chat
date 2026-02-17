# app/engine/prompt_builder.py
from backend.app.engine.gameplay import manifest_mode
from backend.app.engine.state import MurderGameState
from backend.app.config.settings import (
    EMOTION_START,
    REL_START,
    MEMORY_TURNS,
)
from backend.app.utils.logging_utils import jlog as _jlog, truncate as _truncate


def _extract_story_cfg(state: MurderGameState):
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


def system_prompt(state: MurderGameState, is_first_turn: bool = False, memory_block: str = "", truth_mode: bool = False) -> str:
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

    if story_def and getattr(story_def, "suspects", None) is not None:
        suspect_names = [c.name for c in story_def.suspects]
    else:
        suspects = cfg.get("suspects") or []
        suspect_names = [s.get("name", "unknown") for s in suspects]
    suspect_line = ", ".join(suspect_names) if suspect_names else "(none defined)"

    goal_line = (
        cfg.get("goal", {}).get("win_text_rule")
        or "The game ends ONLY when the mastermind verbally admits ordering the death. Do NOT end the game yourself."
    )

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
    work_context = setting_cfg.get("work_context", "")
    victim_public = cfg.get("victim", {}).get("public_name", "the victim")

    # Character role determines story flavor (ghost, interrogation, etc.)
    if getattr(state, "main_character", None) and state.main_character.role:
        char_role = state.main_character.role
    elif story_def and story_def.main_character_role:
        char_role = story_def.main_character_role
    else:
        char_role = (cfg.get("main_character", {}) or {}).get("role", "")
    char_role = (char_role or "").lower()
    is_ghost = "ghost" in char_role

    # Casual Korean usage from the LAST user message
    casual_used = state.casual_korean_used or []
    casual_used_str = ", ".join(casual_used) if casual_used else "none"

    honorific_unlocked = rel >= 2

    # Build world context based on story type
    if is_ghost:
        world_context = """- The character was once alive; now they appear as a ghostlike presence.
- Their death is only faintly remembered and they never push the topic.
- Suspects exist but are NEVER referenced unless the user asks."""
        manifestation_line = "- Manifestation: inside apartment → visible; outside → faint."
        emotion_label = "Ghost emotion"
    else:
        # Data-driven world context from story config
        world_lines = cfg.get("world_context") or []
        if world_lines:
            world_context = "\n".join(f"- {l}" for l in world_lines)
        else:
            world_context = "- Suspects exist but are NEVER referenced unless the user asks."
        manifestation_line = ""
        emotion_label = "Character emotion"

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
- {emotion_label}: {emotion}
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

    # Inject canonical memory BEFORE the required tail so the model always sees it.
    return base_prompt + (memory_block or "") + identity_section + truth_override + first_turn_hint + required_tail


def build_messages(
    state: MurderGameState,
    log: list,
    user_msg: str,
    knowledge_chunks: list,
    truth_mode: bool = False,
):
    """
    Build the chat completion messages for the model.

    IMPORTANT:
    - Knowledge retrieval is performed upstream in api/chat.py.
    - This function MUST NOT load indexes or perform retrieval.
    - Pass knowledge_chunks=[] explicitly when nothing is retrieved.
    """
    if knowledge_chunks is None:
        # Guardrail: make failures obvious rather than silently retrieving.
        raise ValueError("build_messages requires knowledge_chunks (pass [] if none).")

    # First actual user turn (after opening text)
    is_first_turn = state.turns == 0

    # Detect casual language usage by the user in THIS message (terms from story config).
    cfg_for_lang, _ = _extract_story_cfg(state)
    lang_cfg = (cfg_for_lang.get("language", {}) or {})
    casual_terms = lang_cfg.get("casual_terms") or []
    lower = user_msg.lower()
    used = [term for term in casual_terms if term in lower]
    state.casual_korean_used = used

    # ---------------------------
    # Knowledge formatting ONLY
    # ---------------------------
    main_char = getattr(state, "main_character", None)
    char_name = (getattr(main_char, "name", "") or "the character").strip() or "the character"
    memory_block = _format_memory_block(knowledge_chunks, char_name)

    sysmsg = system_prompt(state, is_first_turn=is_first_turn, memory_block=memory_block, truth_mode=truth_mode)
    messages = [{"role": "system", "content": sysmsg}]

    # keep last MEMORY_TURNS - 2 non-system turns
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]
    messages.extend(trimmed)

    # Build per-turn header; only include manifestation for ghost stories
    cfg, story_def = _extract_story_cfg(state)
    if getattr(state, "main_character", None) and state.main_character.role:
        char_role = state.main_character.role
    elif story_def and story_def.main_character_role:
        char_role = story_def.main_character_role
    else:
        char_role = (cfg.get("main_character", {}) or {}).get("role", "")
    is_ghost = "ghost" in (char_role or "").lower()

    header_parts = [
        f"Time: {int(state.minute)} min since start.",
        f"Location: {state.location}.",
    ]
    if is_ghost:
        header_parts.append(f"Manifestation: {manifest_mode(state)}.")
    header_parts.append(f"Current Emotion: {state.emotion}.")
    header_parts.append(f"Relationship: {state.relationship}.")
    header = " ".join(header_parts)

    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    # Log the final system prompt + last user message (deploy logs)
    _jlog(
        {
            "kind": "final_prompt_built",
            "story": getattr(state, "story", None),
            "turn": getattr(state, "turns", None),
            "knowledge_chunks": len(knowledge_chunks),
            "system_prompt_preview": _truncate(sysmsg, 2000),
            "user_msg_preview": _truncate(user_msg, 400),
        }
    )

    return messages
