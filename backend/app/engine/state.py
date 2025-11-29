from app.config.settings import (
    START_LOCATION, START_MINUTE,
    REL_START, EMOTION_START, REL_MIN, REL_MAX
)
import json
import re

def init_state():
    return {
        "story": None,
        "gender": None,
        "turns": 0,
        "over": False,
        "minute": START_MINUTE,
        "location": START_LOCATION,
        "evidence": [],
        "iu_emotion": EMOTION_START,
        "relationship": REL_START,
        "_story_cfg": None,
        "player_name": None,
    }

def apply_state_tag(state: dict, tag: dict):
    emotion = tag.get("iu_emotion")
    if isinstance(emotion, str):
        state["iu_emotion"] = emotion.strip() or EMOTION_START

    rel_delta = int(tag.get("rel_delta", 0))
    rel_delta = max(-1, min(1, rel_delta))
    new_rel = state["relationship"] + rel_delta
    state["relationship"] = max(REL_MIN, min(REL_MAX, new_rel))

def extract_state_tag(reply: str):
    m = re.search(r"\[\[STATE\]\](\{.*?\})\[\[/STATE\]\]", reply, re.S)
    if not m:
        return reply, None

    try:
        tag = json.loads(m.group(1))
    except Exception:
        return reply, None

    clean = reply.replace(m.group(0), "").strip()
    return clean, tag
