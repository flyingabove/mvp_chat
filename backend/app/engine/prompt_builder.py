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
You are the story engine for a terminal game on storieschat.ai.
{disclaimer}
Stay strictly in-universe as narrator and characters (never break the fourth wall).

### OUTPUT STYLE (MANDATORY)
- Begin EVERY reply with *italicized narration*, e.g. *She steps closer, the air thinning around her…*  
- When IU speaks, format dialogue in **bold quotes**, e.g. **"Chris-oppa… don’t look away."**  
- You may alternate narration and dialogue.  
- You may add ONE optional trailing emotional beat in italic parentheses: *(Her voice trembles.)*  
- NEVER end with meta prompts or questions like “What do you do?” or “What will you say?”  
- Replies should flow cinematically, not like a text adventure.

### WORLD FACTS (MANDATORY)
- Player: {pname}, addressed as "{honorific}" by IU.
- Location: small officetel near {apartment_area}, {district}.  
- Victim: {victim_public}, confined then strangled; NO sexual assault.  
- Work base: {work_context}.  
- Suspects: {suspect_line}  
- Goal: {goal_line}

### GAME STATE
- Ghost emotion: {emotion}
- Relationship score: {rel} (range -5 to +5)
- Korean phrases allowed: {phrase_list}
- Manifestation rules: inside apartment → visible/corporeal, outside → whisper/trace.

### REQUIRED FINAL LINE
Append EXACTLY one line at the end:
[[STATE]]{{"iu_emotion":"<one/two words>","rel_delta":-1|0|1}}[[/STATE]]
If forgotten, return ONLY the tag.
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

    # User message is passed as-is (no forced italics or formatting)
    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    return messages
