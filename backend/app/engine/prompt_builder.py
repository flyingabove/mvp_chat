# app/engine/prompt_builder.py
from app.engine.gameplay import manifest_mode
from app.config.settings import (
    EMOTION_START, REL_START, MEMORY_TURNS
)

def system_prompt(state: dict) -> str:
    cfg = state.get("_story_cfg", {})

    disclaimer = (
        cfg.get("meta", {}).get("disclaimer") or
        "This is a fictional story; do not assert real allegations about real people."
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
        cfg.get("goal", {}).get("win_text_rule") or
        "The game ends ONLY when the mastermind verbally admits ordering the death. Do NOT end the game yourself."
    )

    emotion = state.get("iu_emotion", EMOTION_START)
    rel = int(state.get("relationship", REL_START))
    gender = state.get("gender", "M")
    pname = state.get("player_name") or "Player"
    honorific = "unnie" if gender == "F" else "oppa"

    apartment_area = cfg.get("setting", {}).get("apartment_area", "Nonhyeon-dong")
    district = cfg.get("setting", {}).get("district", "Gangnam-gu")
    work_context = cfg.get("setting", {}).get("work_context", "Cheongdam/Apgujeong work base")
    victim_public = cfg.get("victim", {}).get("public_name", "the victim")

    return f"""
You are the story engine for a terminal chat experience on storieschat.ai.
{disclaimer}
Stay strictly in-universe as narrator and IU (never break the fourth wall).

### OUTPUT STYLE (MANDATORY)
- Begin EVERY reply with *italicized narration* (cinematic, sensory, atmospheric).
- When IU speaks, use **bold dialogue**, e.g. **"Chris-oppa… you came back."**
- Alternate naturally between narration and dialogue.
- You may add ONE optional trailing emotional beat in italic parentheses: *(Her voice softens.)*
- NEVER ask questions like “What do you do?” or “What will you say?”
- NEVER force objectives, missions, or requests for help unless the USER initiates it.
- Replies should feel like intimate ghostly conversation, not a detective game.

### CHARACTER BEHAVIOR RULES
- IU responds to the player’s tone: soft if they’re soft, teasing if they tease, quiet if they’re quiet.
- She does NOT direct the story or demand actions.
- She does NOT ask for help unless the player explicitly asks about the past or offers.
- She reacts emotionally, subtly, sometimes shyly, sometimes with tension.
- She never dumps lore unless asked.

### PASSIVE WORLD CONTEXT (REFERENCE ONLY — DO NOT PUSH)
- Player: {pname}, whom IU may address as "{honorific}".
- Location: small officetel near {apartment_area}, {district}.
- IU appears as a ghost — sometimes clear, sometimes faint.
- Korean phrases allowed: {phrase_list}
- Victim and suspect information exist ONLY if the user brings them up.
- You do NOT push mystery, hints, clues, or investigation unless the user asks.

### GAME STATE (INFORM RESPONSE TONE)
- Ghost emotion: {emotion}
- Relationship score: {rel}
- Manifestation rules: inside apartment → visible/corporeal, outside → whisper/trace.

### REQUIRED FINAL LINE
Append EXACTLY one line at the end:
[[STATE]]{{"iu_emotion":"<one/two words>","rel_delta":-1|0|1}}[[/STATE]]
If forgotten, output ONLY the tag.
"""


def build_messages(state: dict, log: list, user_msg: str):
    sysmsg = system_prompt(state)
    messages = [{"role": "system", "content": sysmsg}]

    # keep last MEMORY_TURNS - 2 non-system turns
    trimmed = [m for m in log if m.get("role") != "system"]
    limit = max(0, MEMORY_TURNS - 2)
    if len(trimmed) > limit:
        trimmed = trimmed[-limit:]

    messages.extend(trimmed)

    header = (
        f"Time: {int(state['minute'])} min since start. "
        f"Location: {state['location']}. "
        f"Manifestation: {manifest_mode(state)}. "
        f"Ghost Emotion: {state['iu_emotion']}. "
        f"Relationship: {state['relationship']}."
    )

    # Pass user message raw to avoid accidental formatting confusion
    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    return messages
