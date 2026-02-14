
# app/api/chat.py

from backend.app.engine.extractors.location_extractor import LocationExtractor, LocationIntent

from fastapi import APIRouter

import httpx

import re

import time

import uuid


from backend.app.knowledge.runtime.retrieve import retrieve_knowledge

from backend.app.knowledge.runtime.index_service import IndexService

from backend.app.utils.logging_utils import jlog as _log, truncate as _truncate


from backend.app.config.settings import (

    OPENAI_API_KEY, OPENAI_MODEL,

    TEMPERATURE, MAX_TOKENS, MEMORY_TURNS,
    DEFAULT_USER_ID, DEFAULT_INSTANCE,

)
from backend.app.config.epistemic_flags import set_epistemic_flags, set_master


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
from backend.app.utils.id_utils import build_deterministic_uuid, build_namespace_key


router = APIRouter()


# In-memory session store (session-scoped: lost on server restart)
# Keys: state (MurderGameState), log (list), debug_mode (bool), chinese_mode (bool)
SESSIONS = {}


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


# ---------------------------------------------------------------------------
# CHINESE MODE TOGGLE
# ---------------------------------------------------------------------------
CHINESE_TOGGLE_TOKENS = {
    "[CHINESE]",
    "(CHINESE)",
    "[C]",
    "(C)",
}


def _is_chinese_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in CHINESE_TOGGLE_TOKENS


# ---------------------------------------------------------------------------
# MAP TOGGLE
# ---------------------------------------------------------------------------
MAP_TOGGLE_TOKENS = {
    "[MAP]",
    "(MAP)",
    "[M]",
    "(M)",
}


def _is_map_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in MAP_TOGGLE_TOKENS


# ---------------------------------------------------------------------------
# TRUTH MODE TOGGLE
# ---------------------------------------------------------------------------
TRUTH_TOGGLE_TOKENS = {
    "[TRUTH]",
    "(TRUTH)",
    "[T]",
    "(T)",
}


def _is_truth_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in TRUTH_TOGGLE_TOKENS


EPISTEMIC_TOGGLE_TOKENS = {
    "[ES]",
    "(ES)",
    "[EPISTEMICSTATE]",
    "(EPISTEMICSTATE)",
}


def _is_epistemic_toggle(msg: str) -> bool:
    return (msg or "").strip().upper() in EPISTEMIC_TOGGLE_TOKENS


def _match_world_destination(msg: str, runtime, current_location_id: str = "") -> str:
    """Heuristic location matcher for world-graph travel.

    The LLM-based extractor can miss natural phrasing like "i got to room b".
    This fallback checks for a movement verb plus a known location name/id.
    Returns a destination_id or "" if no confident match.
    """

    text = (msg or "").strip().lower()
    if not text:
        return ""

    verbs = ("go", "got", "move", "head", "walk", "switch", "return", "back", "enter", "step", "run")
    if not any(re.search(rf"\b{v}\b", text) for v in verbs):
        return ""

    try:
        locations = getattr(runtime, "world_graph", None).locations if runtime else {}
    except Exception:
        locations = {}

    for loc_id, loc in (locations or {}).items():
        name = (getattr(loc, "name", "") or "").lower()
        tokens = [name, loc_id.replace("_", " ").lower(), str(loc_id).lower()]
        if any(tok and tok in text for tok in tokens):
            if loc_id == current_location_id:
                return ""  # already there; do nothing
            return loc_id

    return ""


def _debug_speakers(state: MurderGameState) -> list[str]:
    """Collect speaker names for debug box with location-aware mapping."""

    speakers: list[str] = []

    cfg = getattr(state, "story_cfg", {}) or {}
    world_cfg = cfg.get("world", {}) or {}
    loc_speakers = world_cfg.get("location_speakers") or {}

    runtime = getattr(state, "world_runtime", None)
    loc_id = getattr(state, "location_id", "")

    if runtime is not None and loc_id:
        try:
            mapping = loc_speakers.get(loc_id)
            if isinstance(mapping, str) and mapping.strip():
                speakers.append(mapping.strip())
            elif isinstance(mapping, (list, tuple)):
                speakers.extend([str(x).strip() for x in mapping if str(x).strip()])
        except Exception:
            pass

    # Fallback to the characters dictionary if no location-specific mapping exists.
    if not speakers:
        chars = list((getattr(state, "characters", {}) or {}).values())
        for c in chars:
            try:
                name = (getattr(c, "name", "") or "").strip() or "(unnamed)"
            except Exception:
                name = "(unnamed)"
            if name:
                speakers.append(name)

    return [s for s in speakers if s]


def _box(title: str, lines: list[str]) -> str:
    """Render a simple pretty ASCII box."""
    title = (title or "").strip()
    safe_lines = [str(x) for x in (lines or [])]
    inner_width = max([len(title)] + [len(x) for x in safe_lines] + [0])

    top = "┌" + "─" * (inner_width + 2) + "┐"
    mid_title = "│ " + title.ljust(inner_width) + " │" if title else None
    # Render separator if there's a title OR lines (to properly separate title from content)
    sep = "├" + "─" * (inner_width + 2) + "┤" if (title or safe_lines) else None
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
# CHINESE TRANSLATION
# ---------------------------------------------------------------------------
async def _translate_to_chinese(text: str) -> str:
    """
    Translate English text to Chinese using OpenAI API.
    Preserves formatting: bold, italics, quotes, punctuation, line breaks.
    """
    if not text or not text.strip():
        return text
    
    try:
        prompt = (
            "Translate the following English text to Simplified Chinese. "
            "IMPORTANT: Preserve ALL formatting including: bold (**text**), "
            "italics (*text*), quotes, newlines, punctuation, and special characters. "
            "Keep the layout and structure exactly the same as the original. "
            "Only translate the actual words, not the formatting markers. "
            "Return ONLY the translated text, no explanations.\n\n"
            f"Text to translate:\n{text}"
        )
        
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional translator. Translate English to Simplified Chinese while preserving exact formatting."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Lower temperature for consistent translations
            "max_tokens": len(text) + 200,  # Chinese typically needs fewer characters
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json=payload,
            )
        
        if r.status_code < 200 or r.status_code >= 300:
            _log({
                "kind": "chinese_translation_error",
                "status": r.status_code,
                "error": _truncate(r.text, 1000),
            })
            return text  # Fallback to English on error
        
        data = r.json()
        translated = str(data["choices"][0]["message"]["content"]).strip()
        return translated
        
    except Exception as e:
        _log({
            "kind": "chinese_translation_exception",
            "error": str(e),
        })
        return text  # Fallback to English on error


# ---------------------------------------------------------------------------
# SESSION RETRIEVAL
# ---------------------------------------------------------------------------
def get_session(session_id: str):
    if session_id not in SESSIONS:
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
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
    r"\bcall me ([A-Za-z][A-Za-z\s'\-]{0,40})",  # also matches "you can call me", "just call me"
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

    # Sync epistemic master flag to this session's toggle.
    set_master(bool(sess.get("epistemic_state", True)))

    # DEBUG TOGGLE must be checked FIRST before any LLM calls
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

    # CHINESE TOGGLE must be checked FIRST before any LLM calls
    if _is_chinese_toggle(msg):
        currently_on = bool(sess.get("chinese_mode", False))
        sess["chinese_mode"] = not currently_on

        if sess["chinese_mode"]:
            notice = _box(
                "进入中文模式",
                [
                    "Type [C] to exit",
                    "(所有回复将被翻译为中文)",
                ],
            )
        else:
            notice = _box(
                "退出中文模式",
                [
                    "Type [C] to return to English",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # MAP TOGGLE - Show available locations
    if _is_map_toggle(msg):
        state: MurderGameState = sess.get("state")
        if not state or not state.world_runtime:
            notice = _box(
                "World Map",
                [
                    "No map available in this story.",
                ],
            )
            map_image = None
        else:
            locations = list(state.world_runtime.world_graph.locations.values())
            location_lines = []
            for loc in locations:
                location_lines.append(f"{loc.name}")
            notice = _box("World Map", location_lines)
            
            # Get world map image path if available
            map_image = None
            if state.story_cfg:
                world_cfg = state.story_cfg.get("world", {}) or {}
                map_image = str(world_cfg.get("world_map_image", "")).strip() or None

        result = {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}
        if map_image:
            result["world_map_image"] = map_image
            try:
                from PIL import Image as _PILImage
                import os as _os
                _stories_dir = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), "stories")
                with _PILImage.open(_os.path.join(_stories_dir, map_image)) as _im:
                    result["world_map_image_size"] = {"w": _im.width, "h": _im.height}
            except Exception:
                pass
        return result

    # TRUTH TOGGLE - Force character to answer honestly (debug tool)
    if _is_truth_toggle(msg):
        currently_on = bool(sess.get("truth_mode", False))
        sess["truth_mode"] = not currently_on

        if sess["truth_mode"]:
            notice = _box(
                "ENTERING TRUTH MODE",
                [
                    "Type [T] to exit",
                    "(Character will answer ALL questions honestly — no lies, no omissions)",
                ],
            )
        else:
            notice = _box(
                "EXITING TRUTH MODE",
                [
                    "Type [T] to re-enter",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    # EPISTEMIC STATE TOGGLE - Enable/disable epistemic layers for this session
    if _is_epistemic_toggle(msg):
        new_state = not bool(sess.get("epistemic_state", True))
        sess["epistemic_state"] = new_state
        set_master(new_state)

        if new_state:
            notice = _box(
                "EPISTEMIC STATE ON",
                [
                    "Type [ES] to turn off",
                    "Epistemic truth/belief layers are active.",
                ],
            )
        else:
            notice = _box(
                "EPISTEMIC STATE OFF",
                [
                    "Type [ES] to turn on",
                    "Epistemic truth/belief layers are paused.",
                ],
            )

        return {"reply": notice, "usage": {"total_tokens": 0}, "character": "default"}

    t0 = time.time()

    # RESET
    if msg == "__cmd_reset__":
        # Reset session state/log, but keep debug mode off.
        SESSIONS[session_id] = {
            "state": init_state(),
            "log": [],
            "debug_mode": False,
            "chinese_mode": False,
            "epistemic_state": True,
            "truth_mode": False,
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
        new_state.user_id = DEFAULT_USER_ID
        try:
            new_state.instance = int(cfg.get("instance", DEFAULT_INSTANCE))
        except Exception:
            new_state.instance = DEFAULT_INSTANCE
        # Canonical truths (for truth-mode override guidance)
        new_state.canonical_truth = cfg.get("canonical_truth", [])

        # Optional world graph runtime (does not change gameplay unless movement occurs)
        world_cfg = cfg.get("world", {}) or {}
        seed = int(world_cfg.get("seed", 0))
        world_file = str(world_cfg.get("file", "")).strip()
        if world_file:
            loaded = WorldLoader.load_from_file(
                f"backend/app/stories/{world_file}",
                seed=seed,
                user_id=new_state.user_id,
                story_id=story_id,
                instance=new_state.instance,
            )
        else:
            loaded = WorldLoader.try_load_story_world(
                story_id,
                stories_dir="backend/app/stories",
                seed=seed,
                user_id=new_state.user_id,
                instance=new_state.instance,
            )
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
                    start_loc = loaded.world_graph.locations[start_id]
                    new_state.location = start_loc.name
                    new_state.location_uuid = getattr(start_loc, "uuid", "")
                except Exception:
                    pass
            else:
                new_state.location_id = ""
                new_state.location_uuid = ""

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

        main_uuid = str(main_cfg.get("uuid", "")) or build_deterministic_uuid(
            user_id=new_state.user_id,
            story_id=story_id,
            instance=new_state.instance,
            entity_id=main_key,
        )

        main_char = CharacterState(
            key=main_key,
            name=main_name,
            role=main_role,
            emotion=new_state.emotion,
            relationship=new_state.relationship,
            uuid=main_uuid,
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

        # Apply Chinese translation if chinese_mode is enabled
        reply = opening
        if bool(sess.get("chinese_mode", False)):
            reply = await _translate_to_chinese(reply)

        return {"reply": reply, "usage": {"total_tokens": 0}, "character": "default"}

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

    # --- KNOWLEDGE RETRIEVAL (must happen BEFORE location extraction) ---
    # This retrieval provides context that helps LocationExtractor disambiguate ambiguous location
    # references. For example, "I'm going to IU's old workplace" needs FAISS knowledge context to
    # resolve "old workplace" to the specific location ID (e.g., EDAM entertainment building).
    try:
        # Route retrieval to the correct character bundle for this story.
        if getattr(state, "knowledge_character_id", ""):
            IndexService.set_active_character(state.knowledge_character_id)
        namespace = build_namespace_key(user_id=getattr(state, "user_id", ""), story_id=getattr(state, "story", ""), instance=getattr(state, "instance", 1))
        retrieved, debug = retrieve_knowledge(msg, namespace=namespace)
    except Exception as e:
        _log({"kind": "retrieval_error", "error": str(e)})
        return {"error": "knowledge retrieval failed", "character": "default"}

    # --- LOCATION EXTRACTION (with knowledge context for disambiguation) ---
    # LocationExtractor receives knowledge_chunks to disambiguate implicit location references
    # using LLM calls. Example: "old workplace" → FAISS chunks mention EDAM → LLM extracts EDAM_ID
    runtime = getattr(state, "world_runtime", None)
    extraction_applied = False
    if runtime is not None and getattr(state, "location_id", ""):
        try:
            _log({
                "kind": "location_extraction_attempting",
                "user_msg": msg,
                "current_location_id": state.location_id,
                "current_location_name": state.location,
            })
            extraction = await _LOCATION_EXTRACTOR.extract(
                msg,
                world_graph=runtime.world_graph,
                knowledge_chunks=retrieved,  # Pass knowledge chunks for disambiguation
                conversation_log=log  # Pass conversation history for context
            )
            
            _log({
                "kind": "location_extraction_complete",
                "user_msg": msg,
                "extraction_intent": extraction.intent.value,
                "extraction_destination_id": extraction.destination_id,
                "extraction_confidence": extraction.confidence,
            })
            
            if extraction.intent == LocationIntent.MOVE and extraction.destination_id:
                if extraction.destination_id in runtime.world_graph.locations:
                    original_msg = msg
                    msg = f"go to {extraction.destination_id}"
                    extraction_applied = True
                    _log({
                        "kind": "location_extraction_applied",
                        "original_msg": original_msg,
                        "canonicalized_msg": msg,
                        "destination_id": extraction.destination_id,
                    })
                else:
                    _log({
                        "kind": "location_extraction_invalid_destination",
                        "user_msg": msg,
                        "destination_id": extraction.destination_id,
                    })
        except Exception as e:
            _log({
                "kind": "location_extraction_error",
                "error": str(e),
                "user_msg": msg,
            })

        # Heuristic fallback when the classifier misses obvious movement phrasing
        if not extraction_applied:
            dest = _match_world_destination(msg, runtime, getattr(state, "location_id", ""))
            if dest:
                original_msg = msg
                msg = f"go to {dest}"
                extraction_applied = True
                _log({
                    "kind": "location_extraction_heuristic_applied",
                    "original_msg": original_msg,
                    "canonicalized_msg": msg,
                    "destination_id": dest,
                })
    else:
        if runtime is None:
            _log({"kind": "location_extraction_skipped", "reason": "no_world_runtime"})
        elif not getattr(state, "location_id", ""):
            _log({"kind": "location_extraction_skipped", "reason": "no_location_id"})

    messages = build_messages(state, log, msg, retrieved, truth_mode=bool(sess.get("truth_mode", False)))
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

    # Build debug_box as structured data for frontend rendering (never added to LLM context).
    debug_box = None
    if bool(sess.get("debug_mode", False)):
        user_loc = (getattr(state, "location", "") or "").strip() or "(unknown)"
        speakers = _debug_speakers(state)

        debug_box = {
            "timestamp": ts,
            "location": user_loc,
            "location_uuid": getattr(state, "location_uuid", ""),
            "speakers": speakers if speakers else None,
        }

    # Apply Chinese translation if chinese_mode is enabled
    if bool(sess.get("chinese_mode", False)):
        reply = await _translate_to_chinese(reply)

    result = {"reply": reply, "usage": data.get("usage"), "character": "default"}
    if debug_box is not None:
        result["debug_box"] = debug_box
    return result