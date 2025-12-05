# app/api/chat.py
from fastapi import APIRouter, Request
import httpx
import json
import re
import time

from app.config.settings import (
    OPENAI_API_KEY, OPENAI_MODEL,
    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS
)

from app.engine.state import (
    init_state, apply_state_tag, extract_state_tag
)
from app.engine.story_loader import load_story
from app.engine.gameplay import (
    advance_time, confession_detected
)
from app.engine.prompt_builder import (
    build_messages
)

router = APIRouter()

# Simple in-memory session store
SESSIONS = {}  # session_id → { state, log }


def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": []
        }
    return SESSIONS[session_id]


def apply_placeholders(text: str, state: dict):
    name = state.get("player_name", "Player")
    honorific = "unnie" if state.get("gender") == "F" else "oppa"
    return (
        text.replace("{{PLAYER_NAME}}", name)
            .replace("{{HONORIFIC}}", honorific)
    )


@router.post("/chat")
async def chat_handler(data: dict):
    """
    Python equivalent of backend/api/chat.php
    """
    session_id = data.get("session_id") or "default"

    msg = str(data.get("message", "")).strip()
    sess = get_session(session_id)
    state = sess["state"]
    log = sess["log"]

    # -------------------
    # /reset
    # -------------------
    if msg == "__cmd_reset__":
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": []
        }
        return {
            "reply": "[memory cleared]",
            "usage": {"total_tokens": 0},
            "character": "default"
        }

    # -------------------
    # /newgame
    # format: __cmd_newgame__:<story>|<gender>|<name>
    # -------------------
    if msg.startswith("__cmd_newgame__:"):
        payload = msg[len("__cmd_newgame__:"):]
        parts = payload.split("|", 2)
        story_id = parts[0] if len(parts) > 0 else ""
        gender = parts[1].strip().upper() if len(parts) > 1 else "M"
        player_name = parts[2].strip() if len(parts) > 2 else ""

        # sanitize player name
        player_name = re.sub(r"[^A-Za-z\s\-'\"]", "", player_name)[:40]
        if not player_name:
            player_name = "Player"

        cfg = load_story(story_id)
        if not cfg:
            return {"error": f"story not found: {story_id}"}

        # full reset
        new_state = init_state()
        new_state["story"] = story_id
        new_state["gender"] = "F" if gender == "F" else "M"
        new_state["player_name"] = player_name
        new_state["_story_cfg"] = cfg
        new_state["location"] = cfg.get("setting", {}).get("start_location", new_state["location"])
        new_state["iu_emotion"] = cfg.get("emotion", {}).get("start", new_state["iu_emotion"])

        # opening text with placeholders
        opening = cfg.get("opening", {}).get("text", "The room is quiet. A story begins.")
        opening = apply_placeholders(opening, new_state)

        sess["state"] = new_state
        sess["log"] = [
            {"role": "system", "content": build_messages(new_state, [], "")[0]["content"]},
            {"role": "assistant", "content": opening}
        ]

        return {
            "reply": opening,
            "usage": {"total_tokens": 0},
            "character": "default"
        }

    # -------------------
    # Regular turn
    # -------------------
    if not state.get("story") or not state.get("_story_cfg"):
        return {
            "reply": "No active game. Choose a story, enter your name, and select F/M to start.",
            "character": "default"
        }

    if state.get("over"):
        return {
            "reply": "Game already finished. Type /reset to play again.",
            "character": "default"
        }

    advance_time(state, msg)

    # DO NOT increment turn until AFTER prompt creation (so first-turn logic works)
    messages = build_messages(state, log, msg)

    # Now increment turn AFTER generating assistant response
    state["turns"] += 1

    # OpenAI request
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload
        )

    if r.status_code < 200 or r.status_code >= 300:
        return {
            "error": f"upstream HTTP {r.status_code}: {r.text}",
            "character": "default"
        }

    data = r.json()
    reply = str(data["choices"][0]["message"]["content"])

    # strip state tag
    clean, tag = extract_state_tag(reply)
    if not isinstance(tag, dict):
        tag = {"iu_emotion": state["iu_emotion"], "rel_delta": 0}

    apply_state_tag(state, tag)

    # update memory log
    log.append({"role": "user", "content": msg})
    log.append({"role": "assistant", "content": clean})
    sess["log"] = log[-MEMORY_TURNS:]

    # win detection
    if confession_detected(clean, state):
        state["over"] = True
        clean += f"\n\nEND GAME YOU WIN — turns: {state['turns']}"

    return {
        "reply": clean,
        "usage": data.get("usage"),
        "character": "default"
    }
