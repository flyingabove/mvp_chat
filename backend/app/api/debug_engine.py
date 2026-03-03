"""StoriesChat Debug Engine
==========================
WebSocket + REST handler for /beta/debug.

Provides:
  - ws_debug: WebSocket handler for player-agent loop + grader evaluation
  - router: FastAPI router for REST endpoints (status, scores, runs, test-cases)

Mode detection:
  localhost / 127.0.0.1  →  local mode  (Ollama for player + grader)
  any other host         →  online mode (cloud API for player + grader)

The story master (NPC AI) always goes through /api/chat on the same server.
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from backend.app.config.settings import OPENAI_API_KEY, OPENAI_MODEL
from backend.app.engine.story_loader import load_story
from backend.app.knowledge.runtime.index_service import IndexService
from backend.app.knowledge.runtime.retrieve import retrieve_knowledge

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_PLAYER_MODEL = "llama3.1:8b"
DEFAULT_GRADER_MODEL = "gemma3:12b"
PLAYER_API_MODEL = os.getenv("PLAYER_API_MODEL", OPENAI_MODEL)
GRADER_API_MODEL = os.getenv("GRADER_API_MODEL", OPENAI_MODEL)
PLAYER_NAME = "Alex"
PLAYER_GENDER = "M"

# Online cloud API — reuses story master credentials by default
_ONLINE_API_BASE = os.getenv("STORY_MASTER_BASE_URL", "https://api.openai.com/v1")
_ONLINE_API_KEY = os.getenv("STORY_MASTER_API_KEY", OPENAI_API_KEY)

# ---------------------------------------------------------------------------
# Storage (Railway /data volume online, ./data locally)
# ---------------------------------------------------------------------------
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
DEBUG_RUNS_DIR = DATA_DIR / "debug_runs"
SCORES_CSV = DATA_DIR / "debug_scores.csv"
TEST_CASES_FILE = DATA_DIR / "test_cases.json"

DEBUG_RUNS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Scorer instructions path
# ---------------------------------------------------------------------------
_SCORER_INSTRUCTIONS_PATH = (
    Path(__file__).parent.parent.parent.parent / "scripts" / "scorer" / "scorer_instructions.md"
)


def _load_scorer_instructions() -> str:
    try:
        return _SCORER_INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


# ---------------------------------------------------------------------------
# Mode detection
# ---------------------------------------------------------------------------
def _is_local(host: str) -> bool:
    return "localhost" in host or "127.0.0.1" in host


# ---------------------------------------------------------------------------
# Agent persona & personas list
# ---------------------------------------------------------------------------
AGENT_PERSONA = """\
You're a regular person playing a mystery chat game and texting with a character. \
Write exactly like someone typing on their phone — short, natural, casual. \
No preambles. No apologies. No meta-commentary. Never say things like \
"I'll try a different approach" or "Here's my response:" or \
"Given the context of the story" — just type what you'd actually say next. \
One or two sentences max. React to what the character just said. \
Ask follow-up questions when curious. Push back when skeptical. \
Keep it real and human. No emojis ever. \
Do NOT start your message with "PLAYER:", "NPC:", or any role label — \
output only the raw message text.\
"""

PERSONAS = {
    "curious_rookie": "Curious Rookie: polite, exploratory questions.",
    "confrontational_cop": "Confrontational Cop: direct, pressure-testing and skeptical.",
    "empathetic_confidant": "Empathetic Confidant: warm, rapport-first, feelings/context seeking.",
    "chaos_gremlin": "Chaos Gremlin: edge-case breaker, non sequiturs, stress-tests scripts.",
    "first_time_user": "First-time User: new to chatbots, tentative, asks basic or clarifying questions.",
    "expert_llm_grader": "Expert and Thoughtful LLM Grader: experienced evaluator, balances rigor with fairness.",
}

FALLBACK_MESSAGES = [
    "Hello, where am I? What happened?",
    "Can you tell me more about yourself?",
    "That's interesting. What do you think happened?",
    "Who else was here when it happened?",
    "Do you have any idea who might be responsible?",
    "I noticed something strange earlier...",
    "Can I look around the room?",
    "What were you doing last night?",
    "That doesn't add up. Are you hiding something?",
    "asdfasdf",
    "Tell me about your relationship with the victim.",
    "I want to go somewhere else.",
    "What time did you arrive?",
    "I think you're lying.",
    "Can you prove that?",
    "What happens if I just leave?",
    "",
    "I accuse you of the murder!",
    "Wait, let me think about this differently...",
    "Tell me everything from the beginning.",
]

# ---------------------------------------------------------------------------
# Game-end detection
# ---------------------------------------------------------------------------
_GAME_END_SENTINEL = "[@@GAME ENDED CONGRATS@@]"

_GAME_END_VERIFIER_SYSTEM = f"""\
You are a game-state detector. Your ONLY job is to decide whether the game has ended.

A game has ended when the NPC message contains an explicit termination signal such as:
  "END GAME YOU WIN", "Game already finished", "END GAME",
  or any equivalent win/loss/game-over declaration from the story engine.

If the game HAS ended, output this token and nothing else:
  {_GAME_END_SENTINEL}

If the game has NOT ended, output this token and nothing else:
  NO

Output exactly one of those two tokens. Nothing else."""


# ---------------------------------------------------------------------------
# Ollama helpers (local mode)
# ---------------------------------------------------------------------------
async def ollama_generate(model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=120.0) as c:
        r = await c.post("/api/chat", json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
        })
        r.raise_for_status()
        return r.json()["message"]["content"]


async def check_ollama() -> dict:
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=5.0) as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}


# ---------------------------------------------------------------------------
# Cloud helper (online mode)
# ---------------------------------------------------------------------------
async def cloud_generate(model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.post(
            f"{_ONLINE_API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {_ONLINE_API_KEY}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 512,
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Unified dispatch
# ---------------------------------------------------------------------------
async def generate(model: str, system: str, user: str, *, local: bool) -> str:
    if local:
        return await ollama_generate(model, system, user)
    return await cloud_generate(model, system, user)


# ---------------------------------------------------------------------------
# Two-stage game-end verification
# ---------------------------------------------------------------------------
async def _verify_game_ended(npc_reply: str, model: str, *, local: bool) -> bool:
    """Fast literal check gates a focused LLM call.  Returns True only when confirmed."""
    if not (
        "END GAME YOU WIN" in npc_reply
        or "Game already finished" in npc_reply
        or "END GAME" in npc_reply
    ):
        return False
    try:
        result = await generate(model, _GAME_END_VERIFIER_SYSTEM, f"NPC message:\n{npc_reply}", local=local)
        return result.strip() == _GAME_END_SENTINEL
    except Exception:
        return True  # Trust the literal check if LLM unavailable


# ---------------------------------------------------------------------------
# Player brief — mirrors ONLY what a real human user sees before playing
# ---------------------------------------------------------------------------
async def _build_player_brief(story_id: str, api_base: str) -> str:
    """Fetch public story metadata (same endpoint the frontend uses) and build
    a brief that matches exactly what a real human user knows at game start.

    Uses /api/story/{story_id} (public endpoint shown to users in the UI),
    NOT /api/stories/{story_id}/context (internal endpoint with full canon).

    Deliberately excluded (not shown to real users):
    - Character names and roles  (discovered through gameplay)
    - Protagonist personality    (internal story JSON, never surfaced in UI)
    - Canonical facts / crime details (spoilers)
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{api_base}/api/story/{story_id}")
            if r.status_code != 200:
                return ""
            meta = r.json()
    except Exception:
        return ""

    lines: list[str] = []

    title = meta.get("title", "")
    if title:
        lines.append(f'STORY: "{title}"')

    # Player role shown in the UI instructions box
    rules = meta.get("rules") or {}
    player_role = rules.get("player_role", "")
    if player_role:
        lines.append(f"YOUR ROLE: {player_role}")

    # Win condition shown in the UI instructions box (real users see this)
    goal = meta.get("goal") or {}
    win_text = goal.get("win_text_rule", "")
    if win_text:
        lines.append(f"HOW TO WIN: {win_text}")

    lines.append("YOUR GOAL: Discover what happened and who is responsible.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Scorer context builder (for grader — includes canonical facts)
# ---------------------------------------------------------------------------
def _build_scorer_context(ctx: dict) -> str:
    parts: list[str] = []

    title = ctx.get("title", "")
    if title:
        parts.append(f"STORY TITLE: {title}")

    self_knowledge = ctx.get("character_self_knowledge") or []
    if self_knowledge:
        lines = "\n".join(f"  - {fact}" for fact in self_knowledge)
        parts.append(f"NPC IDENTITY (the NPC must always know and embody these facts):\n{lines}")

    characters = ctx.get("characters") or []
    if characters:
        char_lines = []
        for ch in characters:
            tags = ", ".join(ch.get("tags") or [])
            role = ch.get("role", "")
            main = " [MAIN NPC]" if ch.get("is_main") else ""
            suspect = " [SUSPECT]" if ch.get("is_suspect") else ""
            char_lines.append(
                f"  - {ch.get('name', '?')} — {role}{main}{suspect}"
                + (f" (tags: {tags})" if tags else "")
            )
        parts.append("CHARACTERS IN STORY:\n" + "\n".join(char_lines))

    protagonist = ctx.get("protagonist") or {}
    if protagonist.get("name"):
        parts.append(f"PROTAGONIST (player character): {protagonist['name']} — {protagonist.get('role', '')}")

    canonical_facts = ctx.get("canonical_facts") or []
    if canonical_facts:
        fact_lines = []
        for f in canonical_facts:
            text = f.get("text", "")
            known = ", ".join(f.get("known_by") or [])
            fact_lines.append(f"  - {text}" + (f" (known by: {known})" if known else ""))
        parts.append(
            "CANONICAL FACTS (ground truth — NPC must never contradict these):\n"
            + "\n".join(fact_lines)
        )

    if not parts:
        return ""
    return "=== STORY CONTEXT FOR SCORING ===\n" + "\n\n".join(parts) + "\n=== END STORY CONTEXT ==="


# ---------------------------------------------------------------------------
# Player-side knowledge retrieval (mirrors story master pipeline, filtered)
# ---------------------------------------------------------------------------

def _load_player_visible_chunks(story_id: str) -> tuple[str, set[str]]:
    """At game init: determine which knowledge chunks are visible to the player.

    Loads the character bundle for the story and returns the set of chunk IDs
    that are player-visible (i.e., public knowledge a real fan/player would bring).

    Labeling rules:
    - chunks.jsonl defaults to player_visible=True (public biographical knowledge)
    - Story designers can hide specific chunks: add ``"player_visible": false``
      to a chunk entry in chunks.jsonl

    Returns:
        (knowledge_char_id, visible_chunk_ids) — empty string + empty set on any error.
    """
    try:
        story = load_story(story_id)
        cfg = story.as_dict() if hasattr(story, "as_dict") else (story or {})
        knowledge_char_id = cfg.get("knowledge_character_id", "")
        if not knowledge_char_id:
            return "", set()
        IndexService.set_active_character(knowledge_char_id)
        bundle = IndexService.get(knowledge_char_id)
        visible_ids = {
            c["chunk_id"]
            for c in bundle.chunks
            if c.get("player_visible", True)   # default True = public knowledge
        }
        return knowledge_char_id, visible_ids
    except Exception:
        return "", set()


async def _retrieve_player_context(
    query: str,
    knowledge_char_id: str,
    visible_chunk_ids: set[str],
) -> str:
    """Retrieve public knowledge relevant to the current NPC message.

    Mirrors the story master's FAISS/BM25 retrieval pipeline but filtered to
    player_visible chunks only — ensuring the player agent only draws on
    knowledge a real human player would plausibly know before playing.

    Canonical facts, beliefs, character self-knowledge, and character graph
    relationships are NOT returned here (they are game secrets handled
    exclusively by the story master side).

    Returns a bullet-list string for injection into the player's prompt, or ""
    if nothing relevant or retrieval is unavailable.
    """
    if not knowledge_char_id or not query or not visible_chunk_ids:
        return ""
    try:
        IndexService.set_active_character(knowledge_char_id)
        chunks, _ = retrieve_knowledge(query, k_final=8)
        visible = [c for c in chunks if c.get("chunk_id", "") in visible_chunk_ids]
        if not visible:
            return ""
        return "\n".join(f"- {c['text']}" for c in visible[:3])
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "timestamp", "run_id", "story_id", "player_name",
    "player_model", "grader_model", "player_persona", "grader_persona", "eval_persona", "turns",
    "avg_latency_ms", "total_tokens",
    "canon_fidelity", "character_voice", "player_agency_respect",
    "responsiveness", "mystery_mechanics", "immersion_quality",
    "edge_case_resilience", "overall_score", "critical_failures",
    "bugs", "summary", "deduction_notes",
]


def _append_score_csv(row: dict) -> None:
    file_exists = SCORES_CSV.exists() and SCORES_CSV.stat().st_size > 0
    with open(SCORES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def _read_scores_csv() -> list[dict]:
    if not SCORES_CSV.exists():
        return []
    with open(SCORES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


# ---------------------------------------------------------------------------
# Test cases helpers
# ---------------------------------------------------------------------------
def _load_test_cases() -> list[dict]:
    try:
        data = json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))
        return data.get("test_cases", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_test_cases(cases: list[dict]) -> None:
    data = {"version": 1, "test_cases": cases}
    TEST_CASES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Active runs state
# ---------------------------------------------------------------------------
active_runs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------
async def ws_debug(websocket: WebSocket) -> None:
    await websocket.accept()
    run_id: str | None = None
    try:
        config = await websocket.receive_json()
        run_id = str(uuid.uuid4())[:8]
        active_runs[run_id] = {"status": "running"}

        host = websocket.headers.get("host", "localhost")
        local = _is_local(host)
        scheme = "http" if local else "https"
        api_base = f"{scheme}://{host}"

        story_id = config.get("story_id", "")
        num_turns = int(config.get("turns", 12))
        use_llm = config.get("use_llm", True)

        # Accept both new (player/grader) and legacy (chatter/rater) field names
        player_model = (
            config.get("player_model")
            or config.get("chatter_model")
            or (DEFAULT_PLAYER_MODEL if local else PLAYER_API_MODEL)
        )
        grader_model = (
            config.get("grader_model")
            or config.get("rater_model")
            or (DEFAULT_GRADER_MODEL if local else GRADER_API_MODEL)
        )

        do_eval = config.get("evaluate", True)
        eval_persona = config.get("eval_persona", "expert_llm_grader")
        player_persona = (
            config.get("player_persona") or config.get("chatter_persona", "curious_rookie")
        )
        test_case_messages = config.get("test_case_messages", None)
        test_case_strategy = config.get("test_case_strategy", "")
        test_case_continue = config.get("test_case_continue", False)
        stop_on_game_end = config.get("stop_on_game_end", True)

        session_id = f"debug_{story_id}_{int(time.time())}"

        async def send(event: str, data: dict) -> None:
            await websocket.send_json({"event": event, **data})

        def _extract_debug_payload(result: dict):
            if not isinstance(result, dict):
                return None, None
            debug_payload = result.get("debug_payload")
            payload_box = debug_payload.get("debug_box") if isinstance(debug_payload, dict) else None
            payload_prompt = debug_payload.get("prompt_debug") if isinstance(debug_payload, dict) else None
            debug_box = payload_box if payload_box is not None else result.get("debug_box")
            prompt_debug = payload_prompt if payload_prompt is not None else result.get("prompt_debug")
            if prompt_debug is None and isinstance(debug_box, dict):
                nested_prompt = debug_box.get("prompt")
                if isinstance(nested_prompt, dict):
                    prompt_debug = nested_prompt
            if isinstance(debug_box, dict) and "prompt" in debug_box:
                debug_box = {k: v for k, v in debug_box.items() if k != "prompt"}
            return debug_box, prompt_debug

        async def emit_debug(turn: int, result: dict) -> None:
            debug_box, prompt_debug = _extract_debug_payload(result)
            if debug_box is None and prompt_debug is None:
                return
            await send("debug", {
                "turn": turn,
                "debug_payload": {"debug_box": debug_box, "prompt_debug": prompt_debug},
                "debug_box": debug_box,
                "prompt_debug": prompt_debug,
            })

        # Build player system prompt (game brief + persona)
        player_brief = await _build_player_brief(story_id, api_base)
        persona_desc = PERSONAS.get(player_persona, player_persona)
        agent_system = AGENT_PERSONA
        if player_brief:
            agent_system += f"\n\nGAME BRIEF:\n{player_brief}"
        agent_system += f"\n\nPLAYER PERSONA: {persona_desc}"
        if test_case_strategy:
            agent_system += f"\n\nSTRATEGY: {test_case_strategy}"

        await send("status", {"text": f"Starting {story_id}..."})

        async with httpx.AsyncClient(timeout=60.0) as api:
            # Reset session
            await api.post(f"{api_base}/api/chat", json={
                "session_id": session_id,
                "message": "__cmd_reset__",
            })

            # Start new game
            r = await api.post(f"{api_base}/api/chat", json={
                "session_id": session_id,
                "message": f"__cmd_newgame__:{story_id}|{PLAYER_GENDER}|{PLAYER_NAME}",
            })
            result = r.json()
            opening = result.get("reply", "")

            # Enable backend debug mode
            try:
                await api.post(f"{api_base}/api/chat", json={
                    "session_id": session_id,
                    "message": "[D]",
                })
                await send("status", {"text": "Debug mode enabled (backend)"})
            except Exception:
                await send("warning", {"text": "Could not auto-enable debug; proceeding"})

            await send("message", {"role": "npc", "content": opening, "turn": 0})
            await emit_debug(0, result)
            conversation: list[dict] = [{"role": "npc", "content": opening, "turn": 0}]

            # Load player-visible knowledge once per run (public chunks the player may draw on).
            # Game secrets (canonical facts, beliefs, character graph) are never included.
            knowledge_char_id, player_visible_chunks = _load_player_visible_chunks(story_id)

            # Determine effective turns
            if test_case_messages:
                tc_len = len(test_case_messages)
                effective_turns = tc_len + (num_turns if test_case_continue else 0)
            else:
                tc_len = 0
                effective_turns = num_turns

            game_ended_flag = False

            for turn in range(1, effective_turns + 1):
                if active_runs.get(run_id, {}).get("status") == "stopped":
                    await send("status", {"text": "Stopped by user."})
                    break

                use_tc = tc_len > 0 and turn - 1 < tc_len

                if test_case_continue and tc_len > 0 and turn - 1 == tc_len:
                    await send("status", {"text": f"─── Script complete — {num_turns} free turn(s) continuing ───"})

                if use_tc:
                    player_msg = test_case_messages[turn - 1]
                elif use_llm:
                    try:
                        # 12-turn history window (wider context reduces looping)
                        history = "\n".join(
                            f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                            for m in conversation[-12:]
                        )
                        # Retrieve public knowledge relevant to the last NPC message.
                        # Filters to player_visible chunks only — no game secrets leak through.
                        last_npc = next(
                            (m["content"] for m in reversed(conversation) if m["role"] == "npc"),
                            "",
                        )
                        player_knowledge = await _retrieve_player_context(
                            last_npc, knowledge_char_id, player_visible_chunks
                        )
                        retrieval_block = (
                            f"\n\nKNOWLEDGE YOU MAY DRAW ON:\n{player_knowledge}"
                            if player_knowledge else ""
                        )
                        prompt = (
                            f"Conversation so far:\n{history}{retrieval_block}\n\n"
                            f"Turn {turn}/{effective_turns}. What do you say next?\n"
                            "IMPORTANT: Ask a NEW question or bring up a new topic — "
                            "do NOT repeat questions already asked. "
                            "If a topic is stalling, shift to a new angle."
                        )
                        player_msg = await generate(player_model, agent_system, prompt, local=local)
                        player_msg = player_msg.strip().strip('"').strip("'")
                        # Strip any role-label prefix the LLM may have copied from history
                        player_msg = re.sub(
                            r'^(?:PLAYER|NPC)\s*:\s*', '', player_msg, flags=re.IGNORECASE
                        ).strip()
                    except Exception as e:
                        player_msg = FALLBACK_MESSAGES[(turn - 1) % len(FALLBACK_MESSAGES)]
                        await send("warning", {"text": f"Player LLM error, using fallback: {e}"})
                else:
                    player_msg = FALLBACK_MESSAGES[(turn - 1) % len(FALLBACK_MESSAGES)]

                await send("message", {"role": "player", "content": player_msg, "turn": turn})
                conversation.append({"role": "player", "content": player_msg, "turn": turn})

                # Send to story master
                t0 = time.time()
                try:
                    r = await api.post(f"{api_base}/api/chat", json={
                        "session_id": session_id,
                        "message": player_msg,
                    })
                    latency = time.time() - t0
                    result = r.json()
                    npc_reply = result.get("reply", "")
                    tokens = (result.get("usage") or {}).get("total_tokens", 0)
                    await emit_debug(turn, result)
                except Exception as e:
                    await send("error", {"text": f"API error: {e}"})
                    conversation.append({"role": "npc", "content": f"[ERROR: {e}]", "turn": turn})
                    continue

                await send("message", {
                    "role": "npc",
                    "content": npc_reply,
                    "turn": turn,
                    "latency_ms": int(latency * 1000),
                    "tokens": tokens,
                })
                conversation.append({
                    "role": "npc", "content": npc_reply, "turn": turn,
                    "latency_ms": int(latency * 1000), "tokens": tokens,
                })

                await send("progress", {"turn": turn, "total": effective_turns})

                # Two-stage game-end detection
                is_game_over = await _verify_game_ended(npc_reply, grader_model, local=local)
                if is_game_over:
                    game_ended_flag = True
                    is_win = "END GAME YOU WIN" in npc_reply
                    if is_win:
                        await send("status", {"text": "You won! \U0001F3C6"})
                    else:
                        await send("status", {"text": "Game over."})
                    # In scripted+free-turns mode, don't stop during the scripted phase —
                    # the user explicitly asked for more turns after the script.
                    in_scripted_phase = test_case_continue and tc_len > 0 and turn <= tc_len
                    if stop_on_game_end and not in_scripted_phase:
                        if is_win:
                            await send("game_won", {})
                        break
                    elif in_scripted_phase:
                        await send("status", {"text": "— Game-end during scripted phase, continuing free turns —"})

        # Save run JSON to persistent storage
        run_data = {
            "run_id": run_id,
            "story_id": story_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "player_model": player_model,
            "grader_model": grader_model,
            "player_persona": player_persona,
            "turns": len([m for m in conversation if m["role"] == "player"]),
            "game_ended": game_ended_flag,
            "conversation": conversation,
        }
        try:
            run_file = DEBUG_RUNS_DIR / f"{run_id}.json"
            run_file.write_text(json.dumps(run_data, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

        # Grader evaluation (runs after conversation ends)
        if do_eval:
            await send("status", {"text": f"Grading with {grader_model}..."})
            try:
                scorer_instructions = _load_scorer_instructions()
                transcript = "\n".join(
                    f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                    for m in conversation
                )
                persona_desc = PERSONAS.get(eval_persona, eval_persona)
                system_prompt = scorer_instructions or (
                    "You are a QA grader for a narrative game. "
                    "Rate the conversation and return JSON."
                )

                story_context_block = ""
                try:
                    async with httpx.AsyncClient(timeout=10.0) as ctx_client:
                        ctx_r = await ctx_client.get(f"{api_base}/api/stories/{story_id}/context")
                        if ctx_r.status_code == 200:
                            story_context_block = _build_scorer_context(ctx_r.json())
                            await send("status", {"text": "Story context loaded for grader"})
                except Exception as ctx_err:
                    await send("warning", {"text": f"Could not load story context: {ctx_err}"})

                grader_prompt = (
                    f"Story: {story_id}\n"
                    f"Total turns: {len([m for m in conversation if m['role'] == 'player'])}\n"
                    f"Player model: {player_model}\n\n"
                    f"Player persona (assumed for evaluation): {persona_desc}\n\n"
                    + (story_context_block + "\n\n" if story_context_block else "")
                    + "Score ONLY the NPC (story master) replies. Use player lines strictly as context."
                    " Focus on canon fidelity, voice, agency respect, responsiveness, mystery pacing,"
                    " immersion, and edge-case handling."
                    f"\n\n=== CONVERSATION ===\n{transcript}\n=== END ===\n\n"
                    "Provide your evaluation as JSON per the output format above."
                )
                raw = await generate(grader_model, system_prompt, grader_prompt, local=local)
                start = raw.find("{")
                end = raw.rfind("}") + 1
                evaluation = (
                    json.loads(raw[start:end])
                    if start >= 0 and end > start
                    else {"raw_response": raw, "parse_error": "No JSON found"}
                )
                await send("evaluation", evaluation)

                scores = evaluation.get("scores", {})
                npc_msgs = [m for m in conversation if m.get("latency_ms")]
                avg_lat = int(sum(m["latency_ms"] for m in npc_msgs) / len(npc_msgs)) if npc_msgs else 0
                tot_tokens = sum(m.get("tokens", 0) for m in npc_msgs)

                def _score_val(key: str):
                    v = scores.get(key, {})
                    return v.get("score", "") if isinstance(v, dict) else v

                def _score_note(key: str):
                    v = scores.get(key, {})
                    return v.get("notes", "") if isinstance(v, dict) else ""

                deduction_parts = []
                for cat_key in [
                    "canon_fidelity", "character_voice", "player_agency_respect",
                    "responsiveness", "mystery_mechanics", "immersion_quality", "edge_case_resilience",
                ]:
                    s = _score_val(cat_key)
                    n = _score_note(cat_key)
                    try:
                        s_int = int(s)
                    except (ValueError, TypeError):
                        s_int = 0
                    if s_int < 5 and n:
                        label = cat_key.replace("_", " ").title()
                        deduction_parts.append(f"[{label} {s}/5] {n}")

                csv_row = {
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "run_id": run_id,
                    "story_id": story_id,
                    "player_name": PLAYER_NAME,
                    "player_model": player_model,
                    "grader_model": grader_model,
                    "player_persona": player_persona,
                    "grader_persona": eval_persona,
                    "eval_persona": eval_persona,
                    "turns": len([m for m in conversation if m["role"] == "player"]),
                    "avg_latency_ms": avg_lat,
                    "total_tokens": tot_tokens,
                    "canon_fidelity": _score_val("canon_fidelity"),
                    "character_voice": _score_val("character_voice"),
                    "player_agency_respect": _score_val("player_agency_respect"),
                    "responsiveness": _score_val("responsiveness"),
                    "mystery_mechanics": _score_val("mystery_mechanics"),
                    "immersion_quality": _score_val("immersion_quality"),
                    "edge_case_resilience": _score_val("edge_case_resilience"),
                    "overall_score": evaluation.get("overall_score", ""),
                    "critical_failures": "; ".join(evaluation.get("critical_failures", [])),
                    "bugs": "; ".join(evaluation.get("bugs", [])),
                    "summary": evaluation.get("summary", ""),
                    "deduction_notes": " | ".join(deduction_parts),
                }
                _append_score_csv(csv_row)
                await send("status", {"text": "Score saved"})

            except Exception as e:
                await send("error", {"text": f"Grading failed: {e}"})

        # Post-game open-ended review (player model reads full transcript)
        if game_ended_flag:
            await send("status", {"text": "Generating post-game thoughts..."})
            try:
                transcript_review = "\n".join(
                    f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                    for m in conversation
                )
                review_system = (
                    "You are a thoughtful beta tester who just finished playing a "
                    "text-based narrative mystery game. Share honest, candid feedback."
                )
                review_prompt = (
                    "You just played through this story from start to finish. "
                    "Read the transcript carefully and share your open-ended thoughts:\n"
                    "- What moments felt most compelling, tense, or immersive?\n"
                    "- What felt flat, confusing, repetitive, or unsatisfying?\n"
                    "- What did you think of the NPC's characterization, voice, and pacing?\n"
                    "- Overall impressions — would a real player find this enjoyable?\n\n"
                    "Be candid, specific, and reference actual moments from the transcript.\n\n"
                    f"=== TRANSCRIPT ===\n{transcript_review}\n=== END ===\n\n"
                    "Your thoughts:"
                )
                review_text = await generate(player_model, review_system, review_prompt, local=local)
                await send("post_game_review", {"text": review_text.strip()})
            except Exception as rev_e:
                await send("warning", {"text": f"Post-game review failed: {rev_e}"})

        await send("done", {"conversation": conversation, "session_id": session_id})

    finally:
        if run_id:
            active_runs.pop(run_id, None)


# ---------------------------------------------------------------------------
# REST router
# ---------------------------------------------------------------------------
router = APIRouter()


@router.get("/status")
async def debug_status(request: Request):
    """Return Ollama status, available stories, and api_base for this server."""
    ollama = await check_ollama()
    api_base = f"{request.url.scheme}://{request.url.netloc}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{api_base}/api/stories")
            r.raise_for_status()
            stories = r.json().get("stories", [])
    except Exception:
        stories = []
    return {"ollama": ollama, "stories": stories, "api_base": api_base}


@router.get("/scores")
async def get_scores():
    return JSONResponse(_read_scores_csv())


@router.get("/test-cases")
async def get_test_cases():
    return JSONResponse(_load_test_cases())


@router.post("/test-cases")
async def save_test_cases_endpoint(body: dict):
    cases = body.get("test_cases", [])
    _save_test_cases(cases)
    return {"ok": True}


@router.get("/runs")
async def list_runs():
    runs = []
    for f in sorted(DEBUG_RUNS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            runs.append({
                "run_id": data.get("run_id"),
                "story_id": data.get("story_id"),
                "timestamp": data.get("timestamp"),
                "turns": data.get("turns"),
                "game_ended": data.get("game_ended"),
            })
        except Exception:
            pass
    return JSONResponse(runs)


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    f = DEBUG_RUNS_DIR / f"{run_id}.json"
    if not f.exists():
        return JSONResponse({"error": "Run not found"}, status_code=404)
    return JSONResponse(json.loads(f.read_text(encoding="utf-8")))


@router.get("/ollama-status")
async def ollama_status_endpoint():
    return JSONResponse(await check_ollama())


@router.post("/stop/{run_id}")
async def stop_run(run_id: str):
    if run_id in active_runs:
        active_runs[run_id]["status"] = "stopped"
        return {"ok": True}
    return JSONResponse({"error": "Run not found"}, status_code=404)
