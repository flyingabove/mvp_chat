# app/api/chat.py
from fastapi import APIRouter
import httpx
import json
import re
import time
from backend.app.knowledge.runtime.load_indexes import load_character_indexes

INDEXES = load_character_indexes()


from app.config.settings import (
    OPENAI_API_KEY, OPENAI_MODEL,
    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS
)

from app.engine.state import (
    init_state,
    apply_state_tag,
    extract_state_tag,
    MurderGameState,
    CharacterState,
)
from app.engine.story_loader import load_story
from app.engine.gameplay import (
    advance_time,
    confession_detected
)
from app.engine.prompt_builder import (
    build_messages
)

router = APIRouter()

# In-memory session store
SESSIONS = {}  # session_id → { state: MurderGameState, log: list }


# ---------------------------------------------------------------------------
# SESSION RETRIEVAL
# ---------------------------------------------------------------------------
def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": []
        }
    return SESSIONS[session_id]


# ---------------------------------------------------------------------------
# PLACEHOLDERS FOR OPENING TEXT ONLY
# ---------------------------------------------------------------------------
def apply_placeholders(text: str, state: MurderGameState) -> str:
    """
    For narrator-only opening text. Uses meta player_name only.
    IU herself does NOT know the name yet.
    """
    name = state.player_name or "Player"
    honorific = "unnie" if (state.gender == "F") else "oppa"
    return (
        text.replace("{{PLAYER_NAME}}", name)
            .replace("{{HONORIFIC}}", honorific)
    )


# ---------------------------------------------------------------------------
# KOREAN HONORIFIC SANITIZER
# ---------------------------------------------------------------------------
def sanitize_korean_terms(text: str, state: MurderGameState) -> str:
    """
    Removes intimacy honorifics ("oppa", "unnie", etc.) unless relationship >= 2.
    If display_name is available → replace.
    If not → remove entirely.
    """
    rel = state.relationship or 0
    display_name = (state.user.display_name or "").strip()

    forbidden = ["oppa", "unni", "unnie", "eonnie"]

    if rel < 2:
        for term in forbidden:
            pattern = rf"(?i)(?<![A-Za-z]){term}(?![A-Za-z])"
            repl = display_name if display_name else ""
            text = re.sub(pattern, repl, text)

    return text


# ---------------------------------------------------------------------------
# NAME EXTRACTION — USER TELLS THEIR NAME
# ---------------------------------------------------------------------------
NAME_PATTERNS = [
    r"\bmy name is ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bcall me ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\byou can call me ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bjust call me ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bit'?s ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bi am ([A-Za-z][A-Za-z\s'\-]{0,40})",
    r"\bim ([A-Za-z][A-Za-z\s'\-]{0,40})",
]


def clean_name(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"[^\w\s'\-]", "", raw)
    return raw.title()[:40]


def extract_user_name_from_text(user_msg: str) -> str:
    txt = user_msg.lower()

    # Try structured name patterns
    for pat in NAME_PATTERNS:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            return clean_name(m.group(1))

    # Standalone single-word guess
    solo = re.fullmatch(r"[A-Za-z][A-Za-z\s'\-]{0,40}", user_msg.strip())
    if solo:
        return clean_name(solo.group(0))

    return ""


# ---------------------------------------------------------------------------
# NAME CONFIRMATION — USER CONFIRMS IU'S GUESS
# ---------------------------------------------------------------------------
CONFIRM_WORDS = [
    "yes", "yeah", "yea", "yup", "correct",
    "right", "that's right", "mhmm", "mm", "sure"
]


def handle_name_confirmation(user_msg: str, state: MurderGameState):
    guess = (state.last_assistant_guess_name or "").strip()
    if not guess:
        return

    low = user_msg.lower()

    if any(w in low for w in CONFIRM_WORDS):
        state.user.formal_name = guess
        if not state.user.display_name:
            state.user.display_name = guess
        state.last_assistant_guess_name = ""  # consume guess


# ---------------------------------------------------------------------------
# MAIN CHAT ENDPOINT
# ---------------------------------------------------------------------------
@router.post("/chat")
async def chat_handler(data: dict):
    session_id = data.get("session_id") or "default"

    msg = str(data.get("message", "")).strip()
    sess = get_session(session_id)
    state: MurderGameState = sess["state"]
    log = sess["log"]

    # -------------------------------------------------------------------
    # RESET
    # -------------------------------------------------------------------
    if msg == "__cmd_reset__":
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": []
        }
        return {"reply": "[memory cleared]", "usage": {"total_tokens": 0}, "character": "default"}

    # -------------------------------------------------------------------
    # NEWGAME
    # -------------------------------------------------------------------
    if msg.startswith("__cmd_newgame__:"):
        payload = msg[len("__cmd_newgame__:"):]
        parts = payload.split("|", 2)

        story_id = parts[0]
        gender = parts[1].strip().upper() if len(parts) > 1 else "M"
        player_name = parts[2].strip() if len(parts) > 2 else ""

        # sanitize raw player name (narration only!)
        player_name = re.sub(r"[^A-Za-z\s\-'\"]", "", player_name)[:40] or "Player"

        cfg = load_story(story_id)
        if not cfg:
            return {"error": f"story not found: {story_id}"}

        # ---- Initialize state object ----
        new_state: MurderGameState = init_state()
        new_state.story = story_id
        new_state.gender = "F" if gender == "F" else "M"
        new_state.player_name = player_name
        new_state.story_cfg = cfg

        # user object
        new_state.user.gender = new_state.gender
        # formal_name & display_name intentionally remain blank.

        # starting location & emotion
        new_state.location = cfg.get("setting", {}).get("start_location", new_state.location)
        new_state.iu_emotion = cfg.get("emotion", {}).get("start", new_state.iu_emotion)

        # create IU character
        victim_name = cfg.get("victim", {}).get("public_name", "IU")
        victim_short = victim_name.split(",")[0].strip()

        iu_char = CharacterState(
            key="IU",
            name=victim_short,
            role="ghost",
            emotion=new_state.iu_emotion,
            relationship=new_state.relationship,
        )

        new_state.characters["IU"] = iu_char
        new_state.main_character_id = "IU"

        # opening narration
        opening = cfg.get("opening", {}).get("text", "The room is quiet. A story begins.")
        opening = apply_placeholders(opening, new_state)

        sess["state"] = new_state
        sess["log"] = [
            {"role": "system", "content": build_messages(new_state, [], "")[0]["content"]},
            {"role": "assistant", "content": opening}
        ]

        return {"reply": opening, "usage": {"total_tokens": 0}, "character": "default"}

    # -------------------------------------------------------------------
    # REGULAR TURN
    # -------------------------------------------------------------------
    if not state.story or not state.story_cfg:
        return {"reply": "No active game. Use /newgame to begin.", "character": "default"}

    if state.over:
        return {"reply": "Game already finished. Type /reset to play again.", "character": "default"}

    # TIME PROGRESSION
    advance_time(state, msg)

    # NAME CONFIRMATION (IU guessed last turn)
    handle_name_confirmation(msg, state)

    # USER EXPLICITLY GIVES NAME
    extracted = extract_user_name_from_text(msg)
    if extracted:
        state.user.formal_name = extracted
        if not state.user.display_name:
            state.user.display_name = extracted

    # Build messages BEFORE incrementing turns
    messages = build_messages(state, log, msg)

    # Increment turn after prompt building
    state.turns += 1

    # ----- OpenAI request -----
    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )

    if r.status_code < 200 or r.status_code >= 300:
        return {"error": f"upstream HTTP {r.status_code}: {r.text}", "character": "default"}

    data = r.json()
    reply = str(data["choices"][0]["message"]["content"])

    # Detect IU guessing: "Is your name Chris?"
    guess_match = re.search(
        r"\bis your name\s+([A-Za-z][A-Za-z\s'\-]{0,40})\??",
        reply,
        re.IGNORECASE
    )
    if guess_match:
        state.last_assistant_guess_name = clean_name(guess_match.group(1))

    # Strip state tag
    clean, tag = extract_state_tag(reply)

    clean = sanitize_korean_terms(clean, state)

    if not isinstance(tag, dict):
        tag = {"iu_emotion": state.iu_emotion, "rel_delta": 0}

    apply_state_tag(state, tag)

    # Update logs
    log.append({"role": "user", "content": msg})
    log.append({"role": "assistant", "content": clean})
    sess["log"] = log[-MEMORY_TURNS:]

    # Win detection
    if confession_detected(clean, state):
        state.over = True
        clean += f"\n\nEND GAME YOU WIN — turns: {state.turns}"

    return {"reply": clean, "usage": data.get("usage"), "character": "default"}
