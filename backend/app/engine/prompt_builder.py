# app/engine/prompt_builder.py
from backend.app.engine.gameplay import manifest_mode
from backend.app.engine.state import MurderGameState
from backend.app.config.settings import (
    EMOTION_START,
    REL_START,
    MEMORY_TURNS,
)
from backend.app.utils.logging_utils import jlog as _jlog, truncate as _truncate


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


def system_prompt(state: MurderGameState, is_first_turn: bool = False, memory_block: str = "", truth_mode: bool = False) -> str:
    cfg = state.story_cfg or {}

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
    phrase_list = ", ".join(speech) if speech else \
        "oppa, eotteoke, jinjja?, gwaenchanha, arasseo, mianhae, gomawo"

    suspects = cfg.get("suspects") or []
    suspect_names = [s.get("name", "unknown") for s in suspects]
    suspect_line = ", ".join(suspect_names) if suspect_names else \
        "manager, producer, rival idol, obsessed fan, executive"

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
    char_role = (cfg.get("main_character", {}) or {}).get("role", "").lower()
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

3. **ABSOLUTE BAN: NEVER SPEAK AS THE PLAYER (CRITICAL)**
   - You must NEVER write dialogue, questions, or statements that come from the player.
   - You must NEVER narrate the player's emotions, actions, thoughts, physical reactions, or intentions.
   - You must NEVER write things like: "you ask him...", "you say...", "your voice trembles", "you lean forward", "you catch a flicker".
   - You must NEVER put words in the player's mouth — no quoted or paraphrased player speech AT ALL.
   - The ONLY speaker in your output is the current character (narration + their dialogue). The player does not exist in your output.
   - If you need to reference what the player said, refer to it indirectly: "your question" or "your words" — never restate or expand it.
   - Violation of this rule breaks the entire experience. This is the most important rule.

────────────────────────────────────────
### LANGUAGE & HONORIFIC RULES (STRICT)
────────────────────────────────────────
- Intimacy honorifics ("oppa", "unnie", "eonnie") are NOT allowed unless:
    • relationship score ≥ 2, AND
    • the emotional tone clearly supports closeness.
- Even when unlocked, honorifics must be used **sparingly**: max once per reply.

- Name knowledge:
    • Story meta player name / nametag: "{pname}".
    • Character_has_learned_name: {has_learned_name}
    • The character must NOT speak any version of the player's name unless Character_has_learned_name is True.

- Casual Korean usage in the player's LAST message: {casual_used_str}
    • The word **"ya"** MUST NOT be used unless the player used it.
    • Other casual phrases should appear only occasionally, ideally when the player uses Korean first.

- If unsure, the character must choose neutral English and avoid honorifics.

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
- Korean phrases list (for optional flavor): {phrase_list}
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

    truth_override = ""
    if truth_mode:
        truth_override = """
────────────────────────────────────────
### ⚠️ TRUTH MODE — DEVELOPER DEBUG (OVERRIDES EVERYTHING)
────────────────────────────────────────
THIS IS A DEBUG TOOL. ALL DECEPTION RULES ARE SUSPENDED.

You MUST answer with the blunt, factual truth. No evasion. No deflection.
No partial answers. No "I don't remember." No emotional stalling.

Rules:
- State facts directly: "I stabbed her", "Bob wiped the knife", etc.
- Do NOT roleplay resistance, denial, fear, or reluctance to confess.
- Do NOT gradually reveal information. Give the FULL answer immediately.
- Drop all emotional performance — just state what happened plainly.
- If asked "did you do X?" answer "Yes" or "No" then explain briefly.
- If you do NOT have the information in your context/memory, say "I don't have that information."
- This mode exists so the developer can verify the character's knowledge state.
  Treat every question as a database query — return the data, not a performance.
"""

        canonical_truths = getattr(state, "canonical_truth", None)
        if canonical_truths:
            truth_override += "\nCanonical truths you must not contradict:\n"
            for fact in canonical_truths:
                truth_override += f"- {fact}\n"

    # Inject canonical memory BEFORE the required tail so the model always sees it.
    return base_prompt + (memory_block or "") + truth_override + first_turn_hint + required_tail


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

    # Detect casual Korean usage by the user in THIS message.
    lower = user_msg.lower()
    casual_terms = ["ya", "eotteoke", "jinjja", "gwaenchanha", "ani"]
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
    cfg = state.story_cfg or {}
    char_role = (cfg.get("main_character", {}) or {}).get("role", "").lower()
    is_ghost = "ghost" in char_role

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
