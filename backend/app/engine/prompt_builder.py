# app/engine/prompt_builder.py
from app.engine.gameplay import manifest_mode
from app.engine.state import MurderGameState
from app.config.settings import (
    EMOTION_START,
    REL_START,
    MEMORY_TURNS,
)


def system_prompt(state: MurderGameState, is_first_turn: bool = False) -> str:
    cfg = state.story_cfg or {}

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

    # FIRST TURN GUIDANCE (optional)
    prompt_suggestions = cfg.get("prompt_suggestions") or []
    first_turn_hint = ""
    if is_first_turn and prompt_suggestions:
        soft_hint = prompt_suggestions[0]
        first_turn_hint = f"""
────────────────────────────────────────
### FIRST TURN GUIDANCE (THIS TURN ONLY)
────────────────────────────────────────
IU's first reply after the opening scene should:
- remain gentle, cautious, and reactive only.
- open with a **simple, soft question** inspired by: "{soft_hint}"
- e.g., include a natural line like **"Can you see me?"**
- NEVER show panic or desperation.
- NEVER ask for help unless the player offers first.
- NEVER narrate the player’s emotions or thoughts.
"""

    # STATE VARS
    emotion = state.iu_emotion or EMOTION_START
    rel = int(state.relationship if state.relationship is not None else REL_START)

    # Meta name (narrator only)
    pname = state.player_name or "Player"

    # IU’s in-world knowledge of the user's real name
    display_name = (state.user.display_name or "").strip()
    formal_name = (state.user.formal_name or "").strip()
    has_learned_name = bool(display_name)

    # Setting info
    apartment_area = cfg.get("setting", {}).get("apartment_area", "Nonhyeon-dong")
    district = cfg.get("setting", {}).get("district", "Gangnam-gu")
    work_context = cfg.get("setting", {}).get("work_context", "Cheongdam/Apgujeong work base")
    victim_public = cfg.get("victim", {}).get("public_name", "the victim")

    # last-turn casual Korean usage
    casual_used = state.casual_korean_used or []
    casual_used_str = ", ".join(casual_used) if casual_used else "none"

    honorific_unlocked = (rel >= 2)

    # PROMPT BODY
    base_prompt = f"""
You are the story engine for a terminal chat experience on storieschat.ai.
{disclaimer}
Stay fully in-universe as narrator and IU. Never break the fourth wall.

────────────────────────────────────────
### OUTPUT STYLE (MANDATORY)
────────────────────────────────────────
- Start with *italicized cinematic narration*.
- IU’s speech must be in **bold quotes**, e.g. **"Can you see me?"**
- Blend narration + dialogue.
- Optional soft emotional parenthetical at the end.
- NEVER use meta questions (“What do you do?”).
- IU reacts; she never pushes a storyline.

────────────────────────────────────────
### CHARACTER BEHAVIOR RULES
────────────────────────────────────────
1. **NO FORCED MISSION**
   - IU does not request help.
   - IU does not mention suspects or investigations.
   - IU does not set goals.

2. **CONVERSATION-DRIVEN**
   - Gentle player → IU warms.
   - Curious player → IU reveals only faint truths.
   - Flirty player → IU may get shy or intense.
   - Past questions → IU answers softly.

3. **HELP ONLY IF OFFERED**
   - IU never initiates help-seeking.

4. **DO NOT SPEAK AS THE PLAYER**
   - No narration of the player's feelings, thoughts, or involuntary reactions.

────────────────────────────────────────
### LANGUAGE & HONORIFIC RULES (STRICT)
────────────────────────────────────────
- Intimacy honorifics (“oppa”, “unnie”, “eonnie”) are FORBIDDEN unless:
    • relationship score ≥ 2 AND
    • emotional context clearly supports it.
- Even when unlocked: max once per reply.

- **Name usage rules:**
    • Meta name: "{pname}" (NOT used by IU unless learned).
    • IU_has_learned_name: {has_learned_name}
    • IU must NOT use the name unless IU_has_learned_name is True.

- **Casual Korean:**
    • LAST USER casual Korean words: {casual_used_str}
    • “ya” MUST NOT be used unless the user said it.
    • “eotteoke” MAY be used (sparingly), even if user didn’t say it.
    • Other Korean terms: use only if user used Korean first.

────────────────────────────────────────
### PASSIVE WORLD CONTEXT (PLAYER-CONTROLLED)
────────────────────────────────────────
- IU was once alive, now ghost-like.
- Death details remain foggy unless player asks.
- Suspects NEVER appear unless the player mentions them.

────────────────────────────────────────
### PLAYER DETAILS
────────────────────────────────────────
- Story meta name: {pname}
- IU display_name (actual in-game name IU uses): "{display_name}"
- IU formal_name (her internal belief): "{formal_name}"
- Honorific unlocked: {honorific_unlocked}
- Setting: Officetel near {apartment_area}, {district}
- Korean phrase list: {phrase_list}

────────────────────────────────────────
### INTERNAL STATE
────────────────────────────────────────
- IU emotion: {emotion}
- Relationship: {rel}
"""

    required_tail = """
────────────────────────────────────────
### REQUIRED FINAL LINE
────────────────────────────────────────
Append EXACTLY one line at the end:
[[STATE]]{"iu_emotion":"<one/two words>","rel_delta":-1|0|1}[[/STATE]]
If forgotten, output ONLY the tag.
"""

    return base_prompt + first_turn_hint + required_tail


# ---------------------------------------------------------------------------
# MESSAGE BUILDER
# ---------------------------------------------------------------------------
def build_messages(state: MurderGameState, log: list, user_msg: str):
    # First turn after opening text
    is_first_turn = (state.turns == 0)

    # detect casual Korean usage THIS TURN
    lower = user_msg.lower()
    casual_terms = ["ya", "eotteoke", "jinjja", "gwaenchanha", "ani"]
    used = [term for term in casual_terms if term in lower]

    state.casual_korean_used = used
    state.allow_casual_korean = bool(used)

    sysmsg = system_prompt(state, is_first_turn=is_first_turn)
    messages = [{"role": "system", "content": sysmsg}]

    # log trim
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]
    messages.extend(trimmed)

    # world-state header
    header = (
        f"Time: {int(state.minute)} min since start. "
        f"Location: {state.location}. "
        f"Manifestation: {manifest_mode(state)}. "
        f"Ghost Emotion: {state.iu_emotion}. "
        f"Relationship: {state.relationship}."
    )

    # user turn
    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    return messages
