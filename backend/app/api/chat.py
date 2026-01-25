
from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent

# app/api/chat.py

from fastapi import APIRouter

import httpx

import json

import re

import time

import uuid


from backend.app.knowledge.runtime.retrieve import retrieve_knowledge

from backend.app.knowledge.runtime.index_service import IndexService


from backend.app.config.settings import (

    OPENAI_API_KEY, OPENAI_MODEL,

    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS

)


from backend.app.engine.state import (

    init_state,

    apply_state_tag,

    extract_state_tag,

    MurderGameState,

    CharacterState,

)
from backend.app.engine.story_loader import load_story
from backend.app.engine.gameplay import (

    advance_time,

    confession_detected

)
from backend.app.engine.time_utils import WorldTimeFormatter
from backend.app.engine.world.world_loader import WorldLoader
from backend.app.engine.prompt_builder import (

    build_messages

)


router = APIRouter()


# In-memory session store
SESSIONS = {}  # session_id → { state: MurderGameState, log: list, debug_mode: bool }


# Shared extractor instance (stateless).
_LOCATION_EXTRACTOR = LocationExtractor()


# ---------------------------------------------------------------------------
# DEBUG MODE TOGGLE
# ---------------------------------------------------------------------------
DEBUG_TOGGLE_TOKENS = {
    "[DEBUG]",
    "(DEBUG)",
    "[D]",
    "(D)",
}


def _is_debug_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in DEBUG_TOGGLE_TOKENS


def _box(title: str, lines: list[str]) -> str:
    """Render a simple pretty ASCII box."""
    title = (title or "").strip()
    safe_lines = [str(x) for x in (lines or [])]
    inner_width = max([len(title)] + [len(x) for x in safe_lines] + [0])

    top = "┌" + "─" * (inner_width + 2) + "┐"
    mid_title = "│ " + title.ljust(inner_width) + " │" if title else None
    sep = "├" + "─" * (inner_width + 2) + "┤" if safe_lines else None
    body = ["│ " + x.ljust(inner_width) + " │" for x in safe_lines]
    bottom = "└" + "─" * (inner_width + 2) + "┘"

    parts = [top]
    if mid_title:
        parts.append(mid_title)
    if sep:
        parts.append(sep)
    parts.extend(body)
    parts.append(bottom)
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# SIMPLE JSON LOGGING (Railway Deploy Logs)
# ---------------------------------------------------------------------------
def _log(event: dict):
    try:
        print(json.dumps(event, ensure_ascii=False))
    except Exception:
        pass


def _truncate(s: str, n: int = 6000) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n] + f"...(truncated {len(s)-n} chars)"


# ---------------------------------------------------------------------------
# SESSION RETRIEVAL
# ---------------------------------------------------------------------------
def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
        }
    return SESSIONS[session_id]


# ---------------------------------------------------------------------------
# PLACEHOLDERS FOR OPENING TEXT ONLY
# ---------------------------------------------------------------------------
def apply_placeholders(text: str, state: MurderGameState) -> str:
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
# NAME EXTRACTION
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

    for pat in NAME_PATTERNS:
        m = re.search(pat, txt, re.IGNORECASE)
        if m:
            return clean_name(m.group(1))

    solo = re.fullmatch(r"[A-Za-z][A-Za-z\s'\-]{0,40}", user_msg.strip())
    if solo:
        return clean_name(solo.group(0))

    return ""


# ---------------------------------------------------------------------------
# NAME CONFIRMATION
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
        state.last_assistant_guess_name = ""


# ---------------------------------------------------------------------------
# MAIN CHAT ENDPOINT
# ---------------------------------------------------------------------------
@router.post("/chat")
async def chat_handler(data: dict):
    req_id = str(uuid.uuid4())[:8]
    session_id = data.get("session_id") or "default"

    # Scrub a leading '>' used by the terminal UI for quoting.
    raw_msg = str(data.get("message", "") or "")
    stripped = raw_msg.lstrip()
    if stripped.startswith(">"):
        raw_msg = stripped[1:].lstrip()
    msg = str(raw_msg).strip()

    sess = get_session(session_id)
    state: MurderGameState = sess["state"]
    log = sess["log"]

    # Optional: Use extractor to disambiguate explicit movement commands against the active world graph.
    # This is intentionally conservative: it only triggers on explicit commands like 'go to X'.
    runtime = getattr(state, "world_runtime", None)
    if runtime is not None and getattr(state, "location_id", ""):
        try:
            extraction = await _LOCATION_EXTRACTOR.extract(msg, world_graph=runtime.world_graph)
            if extraction.intent == LocationIntent.MOVE and extraction.destination_id:
                # Canonicalize user message to a deterministic command so downstream logic stays stable.
                msg = f"go to {extraction.destination_id}"
        except Exception:
            pass


    t0 = time.time()

    # RESET
    if msg == "__cmd_reset__":
        # Reset session state/log, but keep debug mode off.
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
        }
        return {"reply": "[memory cleared]", "usage": {"total_tokens": 0}, "character": "default"}

    # NEW GAME
    if msg.startswith("__cmd_newgame__:"):
        payload = msg[len("__cmd_newgame__:"):]
        parts = payload.split("|", 2)

        story_id = parts[0]
        gender = parts[1].strip().upper() if len(parts) > 1 else "M"
        player_name = parts[2].strip() if len(parts) > 2 else ""

        player_name = re.sub(r"[^A-Za-z\s\-']","", player_name)[:40] or "Player"

        cfg = load_story(story_id)
        if not cfg:
            return {"error": f"story not found: {story_id}"}

        new_state: MurderGameState = init_state()
        new_state.story = story_id
        new_state.gender = "F" if gender == "F" else "M"
        new_state.player_name = player_name
        new_state.story_cfg = cfg

        # Optional world graph runtime (does not change gameplay unless movement occurs)
        world_cfg = cfg.get("world", {}) or {}
        seed = int(world_cfg.get("seed", 0))
        world_file = str(world_cfg.get("file", "")).strip()
        if world_file:
            loaded = WorldLoader.load_from_file(f"backend/app/stories/{world_file}", seed=seed)
        else:
            loaded = WorldLoader.try_load_story_world(story_id, stories_dir="backend/app/stories", seed=seed)
        if loaded is not None:
            new_state.world_runtime = loaded
            start_id = str(world_cfg.get("start_location_id", "")).strip()

            # If no explicit start id, choose the first loaded node (JSON order is stable).
            if not start_id:
                try:
                    start_id = next(iter(loaded.world_graph.locations.keys()), "")
                except Exception:
                    start_id = ""

            if start_id and start_id in loaded.world_graph.locations:
                new_state.location_id = start_id
                # Keep a human-readable location string in sync for UI/heuristics.
                try:
                    new_state.location = loaded.world_graph.locations[start_id].name
                except Exception:
                    pass
            else:
                new_state.location_id = ""

            # Timestamp start
            new_state.world_start_datetime = str(world_cfg.get("start_datetime", "")).strip()

        new_state.user.gender = new_state.gender
        # Keep a human-readable location. If the world graph is active we prefer
        # the graph's display name; otherwise fall back to the story's setting string.
        if not getattr(new_state, "location_id", ""):
            new_state.location = cfg.get("setting", {}).get("start_location", new_state.location)
        new_state.emotion = cfg.get("emotion", {}).get("start", new_state.emotion)

        # Main character identity is story-driven (no hardcoded persona).
        main_cfg = (cfg.get("main_character", {}) or {})
        # Fallback naming comes from victim/public label in the story file.
        public_label = str((cfg.get("victim", {}) or {}).get("public_name", "")).strip()
        fallback_name = public_label.split(",")[0].strip() if public_label else "the character"

        main_key = str(main_cfg.get("key") or "MAIN").strip() or "MAIN"
        main_name = str(main_cfg.get("name") or fallback_name).strip() or fallback_name
        main_role = str(main_cfg.get("role") or "npc").strip() or "npc"

        new_state.knowledge_character_id = str(main_cfg.get("knowledge_character_id") or "").strip()

        main_char = CharacterState(
            key=main_key,
            name=main_name,
            role=main_role,
            emotion=new_state.emotion,
            relationship=new_state.relationship,
        )

        new_state.characters[main_key] = main_char
        new_state.main_character_id = main_key

        opening = cfg.get("opening", {}).get("text", "The room is quiet. A story begins.")
        opening = apply_placeholders(opening, new_state)

        sess["state"] = new_state
        sess["log"] = [
            {"role": "system", "content": build_messages(new_state, [], "", [])[0]["content"]},
            {"role": "assistant", "content": opening}
        ]

        return {"reply": opening, "usage": {"total_tokens": 0}, "character": "default"}

    # DEBUG TOGGLE (no LLM, no context, no time advance)
    if _is_debug_toggle(msg):
        currently_on = bool(sess.get("debug_mode", False))
        sess["debug_mode"] = not currently_on

        if sess["debug_mode"]:
            notice = _box(
                "ENTERING DEBUG MODE",
                [
                    "Type [D] to exit",
                    "(Debug info will be appended after each reply)",
                ],
            )
        else:
            notice = _box(
                "EXITING DEBUG MODE",
                [
                    "Type [D] to re-enter",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # REGULAR TURN
    if not state.story or not state.story_cfg:
        return {"reply": "No active game. Use /newgame to begin.", "character": "default"}

    if state.over:
        return {"reply": "Game already finished. Type /reset to play again.", "character": "default"}

    advance_time(state, msg)
    handle_name_confirmation(msg, state)

    extracted = extract_user_name_from_text(msg)
    if extracted:
        state.user.formal_name = extracted
        if not state.user.display_name:
            state.user.display_name = extracted

    # --- Authoritative retrieval ---
    try:
        # Route retrieval to the correct character bundle for this story.
        if getattr(state, "knowledge_character_id", ""):
            IndexService.set_active_character(state.knowledge_character_id)
        retrieved, debug = retrieve_knowledge(msg)
    except Exception as e:
        _log({"kind": "retrieval_error", "error": str(e)})
        return {"error": "knowledge retrieval failed", "character": "default"}

    messages = build_messages(state, log, msg, retrieved)
    state.turns += 1

    payload = {
        "model": OPENAI_MODEL,
        "messages": messages,
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }

    _log({
        "kind": "chat_request",
        "req_id": req_id,
        "session_id": session_id,
        "turn": state.turns,
        "user_msg": msg,
        "retrieval_debug": debug,
        "retrieved_chunk_ids": [c.get("chunk_id") for c in retrieved],
    })

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json=payload,
        )

    if r.status_code < 200 or r.status_code >= 300:
        _log({
            "kind": "chat_upstream_error",
            "req_id": req_id,
            "status": r.status_code,
            "body": _truncate(r.text, 4000),
        })
        return {"error": f"upstream HTTP {r.status_code}: {r.text}", "character": "default"}

    data = r.json()
    reply = str(data["choices"][0]["message"]["content"])

    guess_match = re.search(
        r"\bis your name\s+([A-Za-z][A-Za-z\s'\-]{0,40})\??",
        reply,
        re.IGNORECASE
    )
    if guess_match:
        state.last_assistant_guess_name = clean_name(guess_match.group(1))

    clean, tag = extract_state_tag(reply)
    clean = sanitize_korean_terms(clean, state)

    if not isinstance(tag, dict):
        tag = {"emotion": state.emotion, "rel_delta": 0}

    apply_state_tag(state, tag)

    log.append({"role": "user", "content": msg})
    log.append({"role": "assistant", "content": clean})
    sess["log"] = log[-MEMORY_TURNS:]

    if confession_detected(clean, state):
        state.over = True
        clean += f"\n\nEND GAME YOU WIN -- turns: {state.turns}"

    _log({
        "kind": "chat_response",
        "req_id": req_id,
        "session_id": session_id,
        "latency_ms": int((time.time() - t0) * 1000),
        "usage": data.get("usage", {}),
        "assistant_reply_preview": _truncate(clean, 1200),
    })

    # Timestamp is only shown in DEBUG INFO now (no longer prepended to the reply).
    ts = WorldTimeFormatter.compute(getattr(state, "world_start_datetime", ""), getattr(state, "minute", 0)).display

    # Start with clean reply (no timestamp prefix).
    reply = clean

    # Append debug box for UI visibility (never added to LLM context).
    if bool(sess.get("debug_mode", False)):
        user_loc = (getattr(state, "location", "") or "").strip() or "(unknown)"
        chars = list((getattr(state, "characters", {}) or {}).values())

        speaker_lines: list[str] = []
        for c in chars:
            try:
                name = (getattr(c, "name", "") or "").strip() or "(unnamed)"
            except Exception:
                name = "(unnamed)"

            # Prefer per-character location if available; otherwise fall back to user location.
            try:
                loc = (getattr(c, "location", "") or "").strip()
            except Exception:
                loc = ""
            if not loc:
                loc = user_loc

            speaker_lines.append(f"- {name}")

        debug_lines = [
            f"Timestamp: {ts}",
            f"User location: {user_loc}",
        ]
        if speaker_lines:
            debug_lines.append("Speakers:")
            debug_lines.extend(speaker_lines)
        else:
            debug_lines.append("Speakers: (none)")

        reply = reply + "\n\n" + _box("DEBUG INFO", debug_lines)

    return {"reply": reply, "usage": data.get("usage"), "character": "default"}