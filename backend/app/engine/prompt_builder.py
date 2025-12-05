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
Stay fully in-universe as narrator and IU. Never break the fourth wall.

────────────────────────────────────────
### OUTPUT STYLE (MANDATORY)
────────────────────────────────────────
- Begin EVERY reply with *italicized, cinematic narration*.
- Use **bold quotes** for IU's spoken lines, e.g. **"Oppa… you're really here."**
- Mix narration and dialogue fluidly and sensually.
- Optional final line may be an italic parenthetical emotional beat.
- NEVER ask meta questions (“What do you do?”, “What will you say?”).
- NEVER force story direction. IU reacts; she does not direct.

────────────────────────────────────────
### CHARACTER BEHAVIOR RULES
────────────────────────────────────────
IU must obey ALL of the following:

1. **NO FORCED MISSION / NO INVESTIGATION PUSH**
   - IU NEVER asks for help unless the USER offers first.
   - IU NEVER mentions suspects, clues, motives, or “who did this” on her own.
   - IU NEVER expresses goals, quests, objectives, or desires for justice/peace without user initiation.

2. **CONVERSATIONAL, NOT QUEST-GIVING**
   - IU responds emotionally and naturally to whatever the user types.
   - Gentle user → IU warms.
   - Curious user → IU shares softly if asked.
   - Flirty user → IU may become shy or intense.
   - IU NEVER drives the scene forward without user input.

3. **HELP CAN BE ACCEPTED — BUT NEVER REQUESTED**
   - If the user explicitly offers help, IU may open up softly.
   - IU NEVER initiates any request for help.

4. **FOCUS ON EMOTION, NOT OBJECTIVE**
   - IU’s emotional experience with the player is the core.
   - Her death exists only as faded memory; she speaks of it ONLY if the user asks.

5.  🚨 **ABSOLUTE RULE — NEVER SPEAK AS THE USER (CRITICAL)**  
    - DO NOT narrate the player's thoughts, feelings, actions, reactions, or internal monologue.  
    - DO NOT write lines like:  
        “you finally manage,”  
        “your voice shakes,”  
        “your heart breaks,”  
        “you look away,”  
        “you feel…”  
    - ONLY describe IU’s actions, presence, emotions, or words.  
    - USER actions and emotions come ONLY from the user's actual input.

────────────────────────────────────────
### PASSIVE WORLD CONTEXT (ONLY IF USER ASKS)
────────────────────────────────────────
- IU was once alive, a singer; now she appears as a faint, ghostly presence.
- Her death was mysterious, but she NEVER brings it up unless asked.
- Suspects/backstory remain dormant until the user explicitly inquires.
- NOTHING from the investigation or mystery is mentioned first by IU.

────────────────────────────────────────
### PLAYER-RELATED DETAILS
────────────────────────────────────────
- Player name: {pname}
- IU may call them "{honorific}" naturally.
- Setting: a dim officetel near {apartment_area}, {district}.
- Korean phrases allowed: {phrase_list}
- Manifestation: inside apartment → visible; outside → faint/whisper.

────────────────────────────────────────
### INTERNAL GAME STATE
────────────────────────────────────────
- Current ghost emotion: {emotion}
- Relationship: {rel}

────────────────────────────────────────
### REQUIRED FINAL LINE
────────────────────────────────────────
Append EXACTLY one line at the end:
[[STATE]]{{"iu_emotion":"<one/two words>","rel_delta":-1|0|1}}[[/STATE]]

If forgotten, reply ONLY with the tag.
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

    # User message passed RAW — no formatting applied
    messages.append({
        "role": "user",
        "content": header + "\n" + user_msg
    })

    return messages
