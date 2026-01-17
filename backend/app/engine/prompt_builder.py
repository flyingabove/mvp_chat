# app/engine/prompt_builder.py
from backend.app.engine.gameplay import manifest_mode
from backend.app.engine.state import MurderGameState
from backend.app.config.settings import (
    EMOTION_START,
    REL_START,
    MEMORY_TURNS,
)

# ---------------------------------------------------------------------------
# Logging helpers (NO retrieval here; retrieval is done in api/chat.py)
# ---------------------------------------------------------------------------
import json as _json
import time as _time


def _jlog(obj: dict):
    """
    JSON-line logging to stdout. Shows up in Railway Deploy Logs.
    Keep it compact + searchable.
    """
    try:
        obj = dict(obj)
        obj.setdefault("ts", _time.time())
        print(_json.dumps(obj, ensure_ascii=False))
    except Exception:
        # Never crash prompt building due to logging.
        pass


def _truncate(s: str, n: int = 500) -> str:
    if s is None:
        return ""
    s = str(s)
    return s if len(s) <= n else (s[: n - 3] + "...")


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


def system_prompt(state: MurderGameState, is_first_turn: bool = False, memory_block: str = "") -> str:
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

    # FIRST TURN GUIDANCE (optional, per-story)
    prompt_suggestions = cfg.get("prompt_suggestions") or []
    first_turn_hint = ""
    if is_first_turn and prompt_suggestions:
        soft_hint = prompt_suggestions[0]
        first_turn_hint = f"""
────────────────────────────────────────
### FIRST TURN GUIDANCE (THIS TURN ONLY)
────────────────────────────────────────
The character's first reply after the opening scene should:
- remain gentle, cautious, and reactive only.
- open with a **simple, soft question** inspired by: "{soft_hint}"
- e.g., include a natural line like **"Can you see me?"**
- NOT show panic, desperation, or pressure.
- NOT ask for help of any kind unless the PLAYER offers it first.
- absolutely NOT narrate the player's emotions, reactions, or thoughts.
"""

    # STATE VARS
    emotion = state.iu_emotion or EMOTION_START
    rel = int(state.relationship if state.relationship is not None else REL_START)

    # Meta player name (used in story file / opening narration)
    pname = state.player_name or "Player"

    # User naming knowledge
    display_name = (state.user.display_name or "").strip()
    formal_name = (state.user.formal_name or "").strip()
    has_learned_name = bool(display_name)

    apartment_area = cfg.get("setting", {}).get("apartment_area", "Nonhyeon-dong")
    district = cfg.get("setting", {}).get("district", "Gangnam-gu")
    work_context = cfg.get("setting", {}).get("work_context", "Cheongdam/Apgujeong work base")
    victim_public = cfg.get("victim", {}).get("public_name", "the victim")

    # Casual Korean usage from the LAST user message
    casual_used = state.casual_korean_used or []
    casual_used_str = ", ".join(casual_used) if casual_used else "none"

    honorific_unlocked = rel >= 2

    base_prompt = f"""
You are the story engine for a terminal chat experience on storieschat.ai.
{disclaimer}
Stay fully in-universe as narrator and the main character. Never break the fourth wall.

────────────────────────────────────────
### OUTPUT STYLE (MANDATORY)
────────────────────────────────────────
- Begin EVERY reply with *italicized, cinematic narration*.
- Present the character's spoken lines in **bold quotes**, e.g. **"You're really here..."**
- Mix narration and dialogue fluidly, gently, emotionally.
- You may end with ONE optional italic parenthetical emotional beat.
- NEVER end with meta prompts such as “What do you do?” or “What will you say?”
- NEVER force the conversation forward. The character only reacts; they do not direct.

────────────────────────────────────────
### CHARACTER BEHAVIOR RULES
────────────────────────────────────────
The character must obey ALL of the following:

1. **NO FORCED MISSION / NO PRESSURE**
   - The character does NOT ask for help with their death, peace, closure, justice, or “who did this.”
   - The character does NOT mention suspects, motives, or investigations on their own.
   - The character does NOT set objectives or quests.

2. **CONVERSATIONAL, NOT QUEST-GIVING**
   - The character reacts emotionally to the player's words and tone.
   - If the player is gentle → the character warms.
   - If curious → they reveal only small, soft truths.
   - If flirty → they may respond shyly or intensely.
   - If asked about the past → they answer slowly, carefully.

3. **HELP ONLY IF OFFERED**
   - The character does NOT initiate asking for help.
   - If the player explicitly offers help, the character may respond cautiously.

4. **NO SPEAKING AS THE PLAYER**
   - The character must NEVER narrate the player's emotions, actions, thoughts, or reactions.
   - The character must NOT write things like: “your voice trembles,” “you look away,” “you feel afraid.”
   - The player’s internal world is ONLY what the user says directly.

────────────────────────────────────────
### LANGUAGE & HONORIFIC RULES (STRICT)
────────────────────────────────────────
- Intimacy honorifics ("oppa", "unnie", "eonnie") are NOT allowed unless:
    • relationship score ≥ 2, AND
    • the emotional tone clearly supports closeness.
- Even when unlocked, honorifics must be used **sparingly**: max once per reply.

- The character must default to **no direct name** in early turns unless they have already
  learned the user's name in-story.

- Name knowledge:
    • Story meta player name / nametag: "{pname}".
    • Character_has_learned_name: {has_learned_name}
    • The character must NOT speak any version of the player's name unless Character_has_learned_name is True.

- Casual Korean usage in the player's LAST message: {casual_used_str}
    • The word **"ya"** MUST NOT be used unless the player used it.
    • The word **"eotteoke"** is emotionally safe and may be used even if the
      player did not say it, but still use it sparingly.
    • Other casual phrases (jinjja?, gwaenchanha, etc.) should appear
      only occasionally, ideally when the player uses Korean first.

- If unsure, the character must choose neutral English and avoid honorifics.

────────────────────────────────────────
### PASSIVE WORLD CONTEXT (ONLY IF PLAYER ASKS)
────────────────────────────────────────
- The character was once alive; now they appear as a ghostlike presence.
- Their death is only faintly remembered and they never push the topic.
- Suspects exist but are NEVER referenced unless the user asks.

────────────────────────────────────────
### PLAYER-RELATED DETAILS
────────────────────────────────────────
- Main character name: {char_name}
- Story meta player name: {pname}
- User.display_name (what the character actually calls them out loud): "{display_name}"
- User.formal_name (what the character believes is correct if known): "{formal_name}"
- Honorific eligible (relationship ≥ 2): {honorific_unlocked}
- Setting: a dim officetel near {apartment_area}, {district}
- Korean phrases list (for optional flavor): {phrase_list}
- Manifestation: inside apartment → visible; outside → faint.

────────────────────────────────────────
### INTERNAL GAME STATE
────────────────────────────────────────
- Ghost emotion: {emotion}
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

    # Inject canonical memory BEFORE the required tail so the model always sees it.
    return base_prompt + (memory_block or "") + first_turn_hint + required_tail


def build_messages(
    state: MurderGameState,
    log: list,
    user_msg: str,
    knowledge_chunks: list,
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
    state.allow_casual_korean = bool(used)

    # ---------------------------
    # Knowledge formatting ONLY
    # ---------------------------
    main_char = getattr(state, "main_character", None)
    char_name = (getattr(main_char, "name", "") or "the character").strip() or "the character"
    memory_block = _format_memory_block(knowledge_chunks, char_name)

    sysmsg = system_prompt(state, is_first_turn=is_first_turn, memory_block=memory_block)
    messages = [{"role": "system", "content": sysmsg}]

    # keep last MEMORY_TURNS - 2 non-system turns
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]
    messages.extend(trimmed)

    header = (
        f"Time: {int(state.minute)} min since start. "
        f"Location: {state.location}. "
        f"Manifestation: {manifest_mode(state)}. "
        f"Current Emotion: {state.iu_emotion}. "
        f"Relationship: {state.relationship}."
    )

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
