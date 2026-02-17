"""
StoriesChat Agent Tester — Browser UI
======================================
A local web app for point-and-click story testing.

Usage:
    pip install httpx uvicorn fastapi
    python story_agent_ui.py

    Then open http://localhost:8899 in your browser.

Optional (for LLM-powered play + evaluation):
    pip install ollama
    ollama pull llama3.1:8b
    ollama serve
"""

import asyncio
import csv
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE = "https://beta-api.storieschat.ai"
DEFAULT_CHATTER_MODEL = "llama3.1:8b"
DEFAULT_RATER_MODEL = "gemma3:12b"
PLAYER_NAME = "Alex"
PLAYER_GENDER = "M"
PORT = 8899

SCRIPTS_DIR = Path(__file__).parent
SAVE_DIR = SCRIPTS_DIR.parent / "saves"
SCORES_CSV = SAVE_DIR / "scores.csv"
TEST_CASES_FILE = SCRIPTS_DIR / "test_cases.json"
SCORER_INSTRUCTIONS_FILE = SCRIPTS_DIR / "scorer_instructions.md"

# Ensure save dir exists
SAVE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Agent persona & evaluator prompts
# ---------------------------------------------------------------------------
AGENT_PERSONA = """\
You are a beta tester playing a text-based murder mystery chat game.
You are chatting with an NPC character. Your goal is to:
1. Stay in character as a curious, engaged player
2. Ask questions to uncover clues about the mystery
3. Try different conversation approaches (friendly, suspicious, direct, indirect)
4. Occasionally test edge cases (non sequiturs, repeated questions, odd inputs)
5. Keep responses SHORT — 1-2 sentences max, like real chat messages

Respond with ONLY your next message to the character. No commentary or meta-text.
"""

# Load scorer instructions from file
def _load_scorer_instructions() -> str:
    try:
        return SCORER_INSTRUCTIONS_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""

PERSONAS = {
  "curious_rookie": "Curious Rookie: polite, exploratory questions.",
  "confrontational_cop": "Confrontational Cop: direct, pressure-testing and skeptical.",
  "empathetic_confidant": "Empathetic Confidant: warm, rapport-first, feelings/context seeking.",
  "chaos_gremlin": "Chaos Gremlin: edge-case breaker, non sequiturs, stress-tests scripts.",
  "first_time_user": "First-time User: new to chatbots, tentative, asks basic or clarifying questions.",
  "expert_llm_grader": "Expert and Thoughtful LLM Grader: experienced evaluator, balances rigor with fairness.",
}

EVAL_PERSONAS = PERSONAS
CHATTER_PERSONAS = PERSONAS

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
# State
# ---------------------------------------------------------------------------
active_runs: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Ollama helper
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
    """Check if Ollama is running and what models are available."""
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:11434", timeout=5.0) as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
            return {"available": True, "models": models}
    except Exception:
        return {"available": False, "models": []}


# ---------------------------------------------------------------------------
# CSV scores helper
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
  "timestamp", "run_id", "story_id", "player_name",
  "chatter_model", "rater_model", "chatter_persona", "rater_persona", "eval_persona", "turns",
  "avg_latency_ms", "total_tokens",
  "canon_fidelity", "character_voice", "player_agency_respect",
  "responsiveness", "mystery_mechanics", "immersion_quality",
  "edge_case_resilience", "overall_score", "critical_failures",
  "bugs", "summary", "deduction_notes",
]


def _append_score_csv(row: dict):
    """Append a score row to the CSV. Creates the file + header if needed."""
    file_exists = SCORES_CSV.exists() and SCORES_CSV.stat().st_size > 0
    with open(SCORES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def _read_scores_csv() -> list[dict]:
    """Read all score rows from the CSV."""
    if not SCORES_CSV.exists():
        return []
    with open(SCORES_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


# ---------------------------------------------------------------------------
# Test cases helper
# ---------------------------------------------------------------------------
def _load_test_cases() -> list[dict]:
    try:
        data = json.loads(TEST_CASES_FILE.read_text(encoding="utf-8"))
        return data.get("test_cases", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_test_cases(cases: list[dict]):
    data = {"version": 1, "test_cases": cases}
    TEST_CASES_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.get("/api/status")
async def status():
    ollama = await check_ollama()
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{API_BASE}/api/stories")
            r.raise_for_status()
            stories = r.json().get("stories", [])
    except Exception:
        stories = []
    return {"ollama": ollama, "stories": stories, "api_base": API_BASE}


@app.get("/api/scores")
async def get_scores():
    return JSONResponse(_read_scores_csv())


@app.get("/api/test-cases")
async def get_test_cases():
    return JSONResponse(_load_test_cases())


@app.post("/api/test-cases")
async def save_test_cases_endpoint(body: dict):
    cases = body.get("test_cases", [])
    _save_test_cases(cases)
    return {"ok": True}


@app.websocket("/ws/run")
async def ws_run(ws: WebSocket):
    await ws.accept()
    try:
        config = await ws.receive_json()
        run_id = str(uuid.uuid4())[:8]
        active_runs[run_id] = {"status": "running"}

        story_id = config.get("story_id", "iu_murder_mystery")
        num_turns = int(config.get("turns", 12))
        use_llm = config.get("use_llm", True)
        chatter_model = config.get("chatter_model", DEFAULT_CHATTER_MODEL)
        rater_model = config.get("rater_model", DEFAULT_RATER_MODEL)
        do_eval = config.get("evaluate", True)
        eval_persona = config.get("eval_persona", "expert_llm_grader")
        chatter_persona = config.get("chatter_persona", "curious_rookie")
        # Test case mode: use scripted messages instead of LLM/fallback
        test_case_messages = config.get("test_case_messages", None)
        test_case_strategy = config.get("test_case_strategy", "")

        session_id = f"ui_{story_id}_{int(time.time())}"

        async def send(event: str, data: dict):
            await ws.send_json({"event": event, **data})

        # Build agent persona with strategy/persona if provided
        persona_desc = CHATTER_PERSONAS.get(chatter_persona, chatter_persona)
        agent_system = AGENT_PERSONA + f"\n\nPLAYER PERSONA: {persona_desc}"
        if test_case_strategy:
            agent_system += f"\n\nSTRATEGY: {test_case_strategy}"

        # --- Start game ---
        await send("status", {"text": f"Starting {story_id}..."})

        async with httpx.AsyncClient(timeout=60.0) as api:
            # Reset
            await api.post(f"{API_BASE}/api/chat", json={
                "session_id": session_id,
                "message": "__cmd_reset__",
            })

            # New game
            r = await api.post(f"{API_BASE}/api/chat", json={
                "session_id": session_id,
                "message": f"__cmd_newgame__:{story_id}|{PLAYER_GENDER}|{PLAYER_NAME}",
            })
            result = r.json()
            opening = result.get("reply", "")

            await send("message", {"role": "npc", "content": opening, "turn": 0})
            conversation = [{"role": "npc", "content": opening, "turn": 0}]

            # --- Play turns ---
            effective_turns = num_turns
            if test_case_messages:
                effective_turns = len(test_case_messages)

            for turn in range(1, effective_turns + 1):
                if active_runs.get(run_id, {}).get("status") == "stopped":
                    await send("status", {"text": "Stopped by user."})
                    break

                # Get player message
                if test_case_messages:
                    player_msg = test_case_messages[turn - 1] if turn - 1 < len(test_case_messages) else ""
                elif use_llm:
                    try:
                        history = "\n".join(
                            f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                            for m in conversation[-6:]
                        )
                        prompt = f"Conversation so far:\n{history}\n\nTurn {turn}/{effective_turns}. What do you say next?"
                        player_msg = await ollama_generate(chatter_model, agent_system, prompt)
                        player_msg = player_msg.strip().strip('"').strip("'")
                    except Exception as e:
                        player_msg = FALLBACK_MESSAGES[(turn - 1) % len(FALLBACK_MESSAGES)]
                        await send("warning", {"text": f"LLM error, using fallback: {e}"})
                else:
                    player_msg = FALLBACK_MESSAGES[(turn - 1) % len(FALLBACK_MESSAGES)]

                await send("message", {"role": "player", "content": player_msg, "turn": turn})
                conversation.append({"role": "player", "content": player_msg, "turn": turn})

                # Send to API
                t0 = time.time()
                try:
                    r = await api.post(f"{API_BASE}/api/chat", json={
                        "session_id": session_id,
                        "message": player_msg,
                    })
                    latency = time.time() - t0
                    result = r.json()
                    npc_reply = result.get("reply", "")
                    tokens = (result.get("usage") or {}).get("total_tokens", 0)
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

                if "Game already finished" in npc_reply or "END GAME" in npc_reply:
                    await send("status", {"text": "Game over!"})
                    break

            # --- Evaluate (scorer runs AFTER conversation is done) ---
            if do_eval:
                await send("status", {"text": f"Scoring with {rater_model}..."})
                try:
                    scorer_instructions = _load_scorer_instructions()
                    transcript = "\n".join(
                        f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                        for m in conversation
                    )
                    persona_desc = EVAL_PERSONAS.get(eval_persona, eval_persona)

                    system_prompt = scorer_instructions if scorer_instructions else (
                        "You are a QA scorer for a narrative game. "
                        "Rate the conversation and return JSON."
                    )

                    prompt = (
                      f"Story: {story_id}\n"
                      f"Total turns: {len([m for m in conversation if m['role'] == 'player'])}\n"
                      f"Chatter model: {chatter_model}\n\n"
                      f"Player persona (assumed for evaluation): {persona_desc}\n\n"
                      "Score ONLY the NPC (LLM) replies. Use player lines strictly as context."
                      " Focus on canon fidelity, voice, agency respect, responsiveness, mystery pacing,"
                      " immersion, and edge-case handling."
                      f"\n\n=== CONVERSATION ===\n{transcript}\n=== END ===\n\n"
                      f"Provide your evaluation as JSON per the output format above."
                    )
                    raw = await ollama_generate(rater_model, system_prompt, prompt)
                    start = raw.find("{")
                    end = raw.rfind("}") + 1
                    if start >= 0 and end > start:
                        evaluation = json.loads(raw[start:end])
                    else:
                        evaluation = {"raw_response": raw, "parse_error": "No JSON found"}
                    await send("evaluation", evaluation)

                    # --- Record to CSV ---
                    scores = evaluation.get("scores", {})
                    npc_msgs = [m for m in conversation if m.get("latency_ms")]
                    avg_lat = 0
                    if npc_msgs:
                        avg_lat = int(sum(m["latency_ms"] for m in npc_msgs) / len(npc_msgs))
                    tot_tokens = sum(m.get("tokens", 0) for m in npc_msgs)

                    def _score_val(key):
                        v = scores.get(key, {})
                        return v.get("score", "") if isinstance(v, dict) else v

                    def _score_note(key):
                        v = scores.get(key, {})
                        return v.get("notes", "") if isinstance(v, dict) else ""

                    # Aggregate deduction notes: only categories < 5
                    deduction_parts = []
                    for cat_key in [
                        "canon_fidelity", "character_voice", "player_agency_respect",
                        "responsiveness", "mystery_mechanics", "immersion_quality",
                        "edge_case_resilience",
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
                        "chatter_model": chatter_model,
                        "rater_model": rater_model,
                        "chatter_persona": chatter_persona,
                        "rater_persona": eval_persona,
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
                    await send("status", {"text": f"Score saved to {SCORES_CSV.name}"})

                except Exception as e:
                    await send("error", {"text": f"Evaluation failed: {e}"})

            await send("done", {"conversation": conversation})

        active_runs.pop(run_id, None)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"event": "error", "text": str(e)})
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HTML / CSS / JS — single-file browser UI
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StoriesChat Agent Tester</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0c0e14;
    --surface: #13161f;
    --surface2: #1a1e2a;
    --surface3: #222736;
    --border: #2a2f3f;
    --text: #c8cdd8;
    --text-dim: #6b7280;
    --text-bright: #e8ecf4;
    --accent: #6c5ce7;
    --accent-glow: #6c5ce740;
    --npc: #f39c12;
    --npc-bg: #f39c1210;
    --player: #3498db;
    --player-bg: #3498db10;
    --green: #2ecc71;
    --red: #e74c3c;
    --yellow: #f1c40f;
    --font-mono: 'JetBrains Mono', monospace;
    --font-sans: 'DM Sans', sans-serif;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: var(--font-sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    overflow: hidden;
  }

  .app {
    display: grid;
    grid-template-columns: 320px 1fr 360px;
    grid-template-rows: 56px 1fr;
    height: 100vh;
    gap: 1px;
    background: var(--border);
  }

  /* ---- Header ---- */
  .header {
    grid-column: 1 / -1;
    background: var(--surface);
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 16px;
    border-bottom: 1px solid var(--border);
  }
  .header h1 {
    font-family: var(--font-mono);
    font-size: 14px;
    font-weight: 600;
    color: var(--text-bright);
    letter-spacing: 0.5px;
  }
  .header .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--red);
    transition: background 0.3s;
  }
  .header .dot.connected { background: var(--green); }
  .header .status-text {
    font-size: 12px;
    color: var(--text-dim);
    font-family: var(--font-mono);
  }
  .header .tab-bar {
    margin-left: auto;
    display: flex;
    gap: 2px;
  }
  .header .tab-btn {
    padding: 8px 16px;
    background: transparent;
    border: none;
    color: var(--text-dim);
    font-family: var(--font-sans);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    border-radius: 6px 6px 0 0;
    transition: all 0.15s;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .header .tab-btn:hover { color: var(--text); background: var(--surface2); }
  .header .tab-btn.active { color: var(--accent); background: var(--surface2); }

  /* ---- Sidebar (controls) ---- */
  .sidebar {
    background: var(--surface);
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .section-label {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-dim);
    margin-bottom: 8px;
  }

  .control-group { display: flex; flex-direction: column; gap: 8px; }

  select, input[type="number"], input[type="text"], textarea {
    width: 100%;
    padding: 10px 12px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-bright);
    font-family: var(--font-sans);
    font-size: 13px;
    outline: none;
    transition: border-color 0.2s;
  }
  select:focus, input:focus, textarea:focus { border-color: var(--accent); }
  select option { background: var(--surface2); }
  textarea { resize: vertical; min-height: 60px; font-family: var(--font-sans); }

  .toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
  }
  .toggle-label {
    font-size: 13px;
    color: var(--text);
  }
  .toggle {
    width: 40px; height: 22px;
    background: var(--surface3);
    border-radius: 11px;
    cursor: pointer;
    position: relative;
    transition: background 0.2s;
    border: 1px solid var(--border);
  }
  .toggle.on { background: var(--accent); border-color: var(--accent); }
  .toggle::after {
    content: '';
    position: absolute;
    width: 16px; height: 16px;
    border-radius: 50%;
    background: white;
    top: 2px; left: 2px;
    transition: transform 0.2s;
  }
  .toggle.on::after { transform: translateX(18px); }

  .btn {
    padding: 12px 20px;
    border: none;
    border-radius: 8px;
    font-family: var(--font-sans);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .btn-primary {
    background: var(--accent);
    color: white;
    box-shadow: 0 2px 12px var(--accent-glow);
  }
  .btn-primary:hover { filter: brightness(1.15); transform: translateY(-1px); }
  .btn-primary:active { transform: translateY(0); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; transform: none; }

  .btn-danger {
    background: var(--red);
    color: white;
  }
  .btn-danger:hover { filter: brightness(1.15); }

  .btn-secondary {
    background: var(--surface3);
    color: var(--text);
    border: 1px solid var(--border);
  }
  .btn-secondary:hover { border-color: var(--accent); color: var(--text-bright); }

  .btn-sm {
    padding: 6px 12px;
    font-size: 11px;
  }

  .btn-row { display: flex; gap: 8px; }
  .btn-row .btn { flex: 1; }

  /* Progress bar */
  .progress-wrap {
    height: 4px;
    background: var(--surface3);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 4px;
  }
  .progress-bar {
    height: 100%;
    background: var(--accent);
    width: 0%;
    transition: width 0.3s;
    border-radius: 2px;
  }

  /* ---- Chat panel ---- */
  .chat-panel {
    background: var(--bg);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    scroll-behavior: smooth;
  }
  .chat-messages::-webkit-scrollbar { width: 6px; }
  .chat-messages::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .msg {
    max-width: 85%;
    padding: 10px 14px;
    border-radius: 12px;
    font-size: 13.5px;
    line-height: 1.55;
    animation: msgIn 0.25s ease-out;
    position: relative;
  }
  @keyframes msgIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .msg.npc {
    align-self: flex-start;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-bright);
    border-bottom-left-radius: 4px;
  }
  .msg.player {
    align-self: flex-end;
    background: var(--accent);
    color: white;
    border-bottom-right-radius: 4px;
  }
  .msg .meta {
    font-size: 10px;
    color: var(--text-dim);
    margin-top: 6px;
    font-family: var(--font-mono);
  }
  .msg.player .meta { color: rgba(255,255,255,0.5); }
  .msg .role-tag {
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 4px;
  }
  .msg.npc .role-tag { color: var(--npc); }
  .msg.player .role-tag { color: rgba(255,255,255,0.7); }

  .system-msg {
    text-align: center;
    font-size: 11px;
    color: var(--text-dim);
    font-family: var(--font-mono);
    padding: 8px;
  }

  /* Manual input bar */
  .chat-input-bar {
    display: flex;
    gap: 8px;
    padding: 12px 20px;
    border-top: 1px solid var(--border);
    background: var(--surface);
  }
  .chat-input-bar input {
    flex: 1;
    padding: 10px 14px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text-bright);
    font-family: var(--font-sans);
    font-size: 13px;
    outline: none;
  }
  .chat-input-bar input:focus { border-color: var(--accent); }
  .chat-input-bar button {
    padding: 10px 16px;
    background: var(--accent);
    border: none;
    border-radius: 8px;
    color: white;
    font-weight: 600;
    cursor: pointer;
    font-size: 13px;
  }
  .chat-input-bar button:hover { filter: brightness(1.15); }
  .chat-input-bar button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ---- Right panel ---- */
  .right-panel {
    background: var(--surface);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .right-panel-content {
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
    flex: 1;
  }

  /* Tab content visibility */
  .tab-page {
    display: none;
    flex-direction: column;
    height: 100%;
    grid-column: 1 / -1;
    grid-row: 2 / -1;
    overflow: hidden;
    min-height: 0;
  }
  .tab-page.active { display: flex; }

  /* ---- Eval panel ---- */
  .score-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
  }
  .score-card h3 {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
  }
  .score-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 0;
    border-bottom: 1px solid var(--border);
  }
  .score-row:last-child { border-bottom: none; }
  .score-label { font-size: 12px; color: var(--text); }
  .score-value {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 14px;
  }
  .score-1, .score-2 { color: var(--red); }
  .score-3 { color: var(--yellow); }
  .score-4, .score-5 { color: var(--green); }

  .overall-score {
    text-align: center;
    padding: 20px;
    background: var(--surface2);
    border-radius: 10px;
    border: 1px solid var(--border);
  }
  .overall-score .number {
    font-family: var(--font-mono);
    font-size: 48px;
    font-weight: 700;
    color: var(--accent);
  }
  .overall-score .label {
    font-size: 11px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .eval-list {
    list-style: none;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .eval-list li {
    font-size: 12px;
    color: var(--text);
    padding: 6px 10px;
    background: var(--surface3);
    border-radius: 6px;
    line-height: 1.4;
  }
  .eval-list li.bug { border-left: 3px solid var(--red); }
  .eval-list li.highlight { border-left: 3px solid var(--green); }

  .eval-summary {
    font-size: 13px;
    line-height: 1.6;
    color: var(--text);
    padding: 12px;
    background: var(--surface2);
    border-radius: 8px;
    border: 1px solid var(--border);
  }

  .eval-placeholder {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    color: var(--text-dim);
    font-size: 13px;
    text-align: center;
    padding: 40px;
    line-height: 1.6;
  }

  .stats-row {
    display: flex;
    gap: 8px;
  }
  .stat-box {
    flex: 1;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px;
    text-align: center;
  }
  .stat-box .stat-val {
    font-family: var(--font-mono);
    font-size: 18px;
    font-weight: 700;
    color: var(--text-bright);
  }
  .stat-box .stat-label {
    font-size: 9px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-top: 2px;
  }

  .hint {
    font-size: 12px;
    color: var(--text-dim);
    line-height: 1.4;
    margin-top: 8px;
  }

  /* ---- Leaderboard ---- */
  .lb-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  .lb-table th {
    text-align: left;
    padding: 8px 6px;
    font-family: var(--font-mono);
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--surface);
  }
  .lb-table td {
    padding: 8px 6px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
  }
  .lb-table tr:hover td { background: var(--surface2); }
  .lb-rank {
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--accent);
    width: 30px;
  }
  .lb-score {
    font-family: var(--font-mono);
    font-weight: 700;
  }

  /* ---- Test case designer ---- */
  .tc-card {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 8px;
  }
  .tc-card .tc-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }
  .tc-card .tc-name {
    font-weight: 600;
    font-size: 14px;
    color: var(--text-bright);
  }
  .tc-card .tc-desc {
    font-size: 12px;
    color: var(--text-dim);
    margin-bottom: 8px;
  }
  .tc-card .tc-msgs {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--text);
    background: var(--surface3);
    padding: 8px;
    border-radius: 6px;
    max-height: 100px;
    overflow-y: auto;
  }
  .tc-actions { display: flex; gap: 6px; }
</style>
</head>
<body>
<div class="app">
  <!-- Header -->
  <div class="header">
    <h1>&#x1F9EA; STORIESCHAT TESTER</h1>
    <div class="dot" id="statusDot"></div>
    <span class="status-text" id="statusText">Connecting...</span>
    <div class="tab-bar">
      <button class="tab-btn active" onclick="switchTab('tester')">Tester</button>
      <button class="tab-btn" onclick="switchTab('leaderboard')">Leaderboard</button>
      <button class="tab-btn" onclick="switchTab('test-cases')">Test Cases</button>
    </div>
  </div>

  <!-- ================= TAB: TESTER ================= -->
  <div class="tab-page active" id="tab-tester" style="display:contents">
  <!-- Left sidebar: Controls -->
  <div class="sidebar" id="sidebar-tester">
    <div>
      <div class="section-label">Story</div>
      <div class="control-group">
        <select id="storySelect"><option value="">Loading stories...</option></select>
      </div>
    </div>

    <div>
      <div class="section-label">Models</div>
      <div class="control-group">
        <label style="font-size:12px;color:var(--text-dim)">Chatter (player agent)</label>
        <select id="chatterModelSelect"><option value="">Loading...</option></select>
      </div>
      <div class="control-group" style="margin-top:6px">
        <label style="font-size:12px;color:var(--text-dim)">Rater (scorer)</label>
        <select id="raterModelSelect"><option value="">Loading...</option></select>
      </div>
      <div class="hint">Chatter and rater should be different models to avoid self-bias.</div>
    </div>

    <div>
      <div class="section-label">Settings</div>
      <div class="control-group">
        <label style="font-size:12px;color:var(--text-dim)">Turns</label>
        <input type="number" id="turnsInput" value="12" min="1" max="100" />
      </div>

      <div class="toggle-row">
        <span class="toggle-label">Use LLM player</span>
        <div class="toggle on" id="llmToggle" onclick="this.classList.toggle('on')"></div>
      </div>
      <div class="toggle-row">
        <span class="toggle-label">Auto-evaluate</span>
        <div class="toggle on" id="evalToggle" onclick="this.classList.toggle('on')"></div>
      </div>

      <div class="control-group" style="margin-top:6px">
        <label style="font-size:12px;color:var(--text-dim)">Chatter persona (player agent)</label>
        <select id="chatterPersonaSelect">
          <option value="curious_rookie">Curious Rookie</option>
          <option value="confrontational_cop">Confrontational Cop</option>
          <option value="empathetic_confidant">Empathetic Confidant</option>
          <option value="chaos_gremlin">Chaos Gremlin</option>
          <option value="first_time_user">First-time User</option>
          <option value="expert_llm_grader">Expert and Thoughtful LLM Grader</option>
        </select>
      </div>

      <div class="control-group" style="margin-top:6px">
        <label style="font-size:12px;color:var(--text-dim)">Rater persona (scorer)</label>
        <select id="raterPersonaSelect">
          <option value="curious_rookie">Curious Rookie</option>
          <option value="confrontational_cop">Confrontational Cop</option>
          <option value="empathetic_confidant">Empathetic Confidant</option>
          <option value="chaos_gremlin">Chaos Gremlin</option>
          <option value="first_time_user">First-time User</option>
          <option value="expert_llm_grader" selected>Expert and Thoughtful LLM Grader</option>
        </select>
      </div>
    </div>

    <div>
      <div class="section-label">Actions</div>
      <div class="btn-row">
        <button class="btn btn-primary" id="runBtn" onclick="startRun()">&#9654; Run</button>
        <button class="btn btn-danger" id="stopBtn" onclick="stopRun()" style="display:none">&#9632; Stop</button>
      </div>
      <div class="progress-wrap" style="margin-top:8px">
        <div class="progress-bar" id="progressBar"></div>
      </div>
    </div>

    <div>
      <div class="section-label">Stats</div>
      <div class="stats-row">
        <div class="stat-box">
          <div class="stat-val" id="statTurns">0</div>
          <div class="stat-label">Turns</div>
        </div>
        <div class="stat-box">
          <div class="stat-val" id="statLatency">--</div>
          <div class="stat-label">Avg ms</div>
        </div>
        <div class="stat-box">
          <div class="stat-val" id="statTokens">0</div>
          <div class="stat-label">Tokens</div>
        </div>
      </div>
    </div>

    <div>
      <div class="section-label">Export</div>
      <button class="btn btn-secondary" style="width:100%" onclick="exportLog()">&#x1F4BE; Save conversation</button>
      <button class="btn btn-secondary" style="width:100%; margin-top:8px" onclick="createTestCaseFromConversation()">+ Create Test Case</button>
    </div>
  </div>

  <!-- Center: Chat -->
  <div class="chat-panel" id="chatPanel-tester">
    <div class="chat-messages" id="chatMessages">
      <div class="system-msg">Select a story and click Run to begin.</div>
    </div>
    <div class="chat-input-bar">
      <input type="text" id="manualInput" placeholder="Type a manual message..." disabled />
      <button id="sendBtn" onclick="sendManual()" disabled>Send</button>
    </div>
  </div>

  <!-- Right: Evaluation -->
  <div class="right-panel" id="rightPanel-tester">
    <div class="right-panel-content">
      <div class="section-label">Evaluation</div>
      <div class="eval-placeholder" id="evalPlaceholder">
        Run a test with "Auto-evaluate" enabled<br>to see scorer results here.
      </div>
      <div id="evalContent" style="display:none"></div>
    </div>
  </div>
  </div><!-- /tab-tester -->

  <!-- ================= TAB: LEADERBOARD ================= -->
  <div class="tab-page" id="tab-leaderboard">
    <div style="flex:1; padding: 20px; overflow-y: auto; min-height: 0;">
      <div style="max-width: 1100px; margin: 0 auto;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 16px;">
          <div class="section-label" style="margin:0">Scores Leaderboard</div>
          <button class="btn btn-secondary btn-sm" onclick="loadLeaderboard()">&#x1F504; Refresh</button>
        </div>
        <div id="leaderboardContent" style="overflow-x:auto">
          <div class="eval-placeholder">Loading scores...</div>
        </div>
      </div>
    </div>
  </div>

  <!-- ================= TAB: TEST CASES ================= -->
  <div class="tab-page" id="tab-test-cases">
    <div style="flex:1; display: grid; grid-template-columns: 380px 1fr; min-height: 0; gap: 1px; background: var(--border);">
      <!-- Test case list -->
      <div style="background: var(--surface); padding: 20px; overflow-y: auto; min-height: 0;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 16px;">
          <div class="section-label" style="margin:0">Test Cases</div>
          <button class="btn btn-primary btn-sm" onclick="newTestCase()">+ New</button>
        </div>
        <div id="testCaseList"></div>
      </div>
      <!-- Test case editor -->
      <div style="background: var(--bg); padding: 20px; overflow-y: auto; min-height: 0;">
        <div id="testCaseEditor">
          <div class="eval-placeholder">Select or create a test case to edit it.</div>
        </div>
      </div>
    </div>
  </div>

</div>

<script>
  let ws = null;
  let running = false;
  let conversation = [];
  let latencies = [];
  let totalTokens = 0;
  let turnCount = 0;
  let manualSession = null;
  let testCases = [];
  let editingTestCaseIdx = -1;
  let currentTab = 'tester';

  // ---- Tab switching ----
  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-page').forEach(p => {
      p.classList.remove('active');
      p.style.display = 'none';
    });
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));

    const page = document.getElementById('tab-' + tab);
    if (page) {
      page.classList.add('active');
      page.style.display = tab === 'tester' ? 'contents' : 'flex';
    }
    document.querySelectorAll('.tab-btn').forEach(b => {
      if (b.textContent.toLowerCase().replace(/\s/g, '-') === tab ||
          (tab === 'tester' && b.textContent === 'Tester') ||
          (tab === 'leaderboard' && b.textContent === 'Leaderboard') ||
          (tab === 'test-cases' && b.textContent === 'Test Cases')) {
        b.classList.add('active');
      }
    });

    if (tab === 'leaderboard') loadLeaderboard();
    if (tab === 'test-cases') loadTestCases();
  }

  // ---- Init ----
  async function init() {
    const r = await fetch('/api/status');
    const data = await r.json();

    const dot = document.getElementById('statusDot');
    const txt = document.getElementById('statusText');

    // Populate stories
    const sel = document.getElementById('storySelect');
    sel.innerHTML = '';
    if (data.stories.length) {
      data.stories.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s.id;
        opt.textContent = s.title;
        sel.appendChild(opt);
      });
    } else {
      sel.innerHTML = '<option value="">No stories found</option>';
    }

    // Populate model selects (both chatter and rater)
    const chatterSel = document.getElementById('chatterModelSelect');
    const raterSel = document.getElementById('raterModelSelect');
    chatterSel.innerHTML = '';
    raterSel.innerHTML = '';

    if (data.ollama.available && data.ollama.models.length) {
      const models = data.ollama.models;
      models.forEach((m, i) => {
        const opt1 = document.createElement('option');
        opt1.value = m; opt1.textContent = m;
        chatterSel.appendChild(opt1);

        const opt2 = document.createElement('option');
        opt2.value = m; opt2.textContent = m;
        raterSel.appendChild(opt2);
      });
      // Default: rater is a different model if possible
      if (models.length >= 2) {
        raterSel.selectedIndex = 1;
      }
      dot.classList.add('connected');
      txt.textContent = 'API + Ollama ready';
    } else {
      chatterSel.innerHTML = '<option value="">No models (Ollama offline)</option>';
      raterSel.innerHTML = '<option value="">No models (Ollama offline)</option>';
      if (data.stories.length) {
        dot.classList.add('connected');
        txt.textContent = 'API ready (Ollama offline)';
      } else {
        txt.textContent = 'API unreachable';
      }
    }
  }

  // ---- Run ----
  function startRun(testCaseOverride) {
    const storyId = document.getElementById('storySelect').value;
    if (!storyId) return;

    const turns = parseInt(document.getElementById('turnsInput').value) || 12;
    const useLlm = document.getElementById('llmToggle').classList.contains('on');
    const evaluate = document.getElementById('evalToggle').classList.contains('on');
    const chatterPersona = document.getElementById('chatterPersonaSelect').value || 'curious_rookie';
    const evalPersona = document.getElementById('raterPersonaSelect').value || 'curious_rookie';
    const chatterModel = document.getElementById('chatterModelSelect').value;
    const raterModel = document.getElementById('raterModelSelect').value;

    // Reset
    conversation = [];
    latencies = [];
    totalTokens = 0;
    turnCount = 0;
    document.getElementById('chatMessages').innerHTML = '';
    document.getElementById('evalContent').style.display = 'none';
    document.getElementById('evalPlaceholder').style.display = 'flex';
    document.getElementById('progressBar').style.width = '0%';
    updateStats();

    running = true;
    document.getElementById('runBtn').style.display = 'none';
    document.getElementById('stopBtn').style.display = 'block';
    document.getElementById('manualInput').disabled = true;
    document.getElementById('sendBtn').disabled = true;

    // Switch to tester tab if not already
    if (currentTab !== 'tester') switchTab('tester');

    addSystemMsg('Starting ' + storyId + '...');

    const wsConfig = {
      story_id: storyId,
      turns: turns,
      use_llm: useLlm,
      chatter_model: chatterModel,
      rater_model: raterModel,
      evaluate: evaluate,
      eval_persona: evalPersona,
      chatter_persona: chatterPersona,
    };

    // Test case override
    if (testCaseOverride) {
      wsConfig.test_case_messages = testCaseOverride.messages || [];
      wsConfig.test_case_strategy = testCaseOverride.strategy || '';
      addSystemMsg('Running test case: ' + (testCaseOverride.name || 'unnamed'));
    }

    ws = new WebSocket('ws://' + location.host + '/ws/run');
    ws.onopen = () => {
      ws.send(JSON.stringify(wsConfig));
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      handleEvent(msg);
    };
    ws.onclose = () => {
      running = false;
      document.getElementById('runBtn').style.display = 'block';
      document.getElementById('stopBtn').style.display = 'none';
      document.getElementById('manualInput').disabled = false;
      document.getElementById('sendBtn').disabled = false;
    };
    ws.onerror = () => {
      addSystemMsg('WebSocket error');
    };
  }

  function stopRun() {
    if (ws) ws.close();
    running = false;
    document.getElementById('runBtn').style.display = 'block';
    document.getElementById('stopBtn').style.display = 'none';
    addSystemMsg('Stopped.');
  }

  function handleEvent(msg) {
    switch (msg.event) {
      case 'message':
        addChatMsg(msg);
        conversation.push(msg);
        if (msg.role === 'npc' && msg.latency_ms) {
          latencies.push(msg.latency_ms);
          totalTokens += (msg.tokens || 0);
        }
        if (msg.role === 'player') turnCount++;
        updateStats();
        break;
      case 'progress':
        const pct = (msg.turn / msg.total) * 100;
        document.getElementById('progressBar').style.width = pct + '%';
        break;
      case 'status':
        addSystemMsg(msg.text);
        break;
      case 'warning':
        addSystemMsg('\u26A0 ' + msg.text);
        break;
      case 'error':
        addSystemMsg('\u2717 ' + msg.text);
        break;
      case 'evaluation':
        renderEval(msg);
        break;
      case 'done':
        addSystemMsg('Done.');
        document.getElementById('progressBar').style.width = '100%';
        break;
    }
  }

  function addChatMsg(msg) {
    const el = document.createElement('div');
    el.className = 'msg ' + msg.role;
    let html = '<div class="role-tag">' + (msg.role === 'npc' ? 'NPC' : 'Player') + '</div>';
    html += '<div>' + escapeHtml(msg.content) + '</div>';
    if (msg.latency_ms) {
      html += '<div class="meta">' + msg.latency_ms + 'ms \u00B7 ' + (msg.tokens || 0) + ' tok</div>';
    }
    el.innerHTML = html;
    document.getElementById('chatMessages').appendChild(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function addSystemMsg(text) {
    const el = document.createElement('div');
    el.className = 'system-msg';
    el.textContent = text;
    document.getElementById('chatMessages').appendChild(el);
    el.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }

  function updateStats() {
    document.getElementById('statTurns').textContent = turnCount;
    document.getElementById('statTokens').textContent = totalTokens;
    if (latencies.length) {
      const avg = Math.round(latencies.reduce((a,b) => a+b, 0) / latencies.length);
      document.getElementById('statLatency').textContent = avg;
    }
  }

  function renderEval(ev) {
    document.getElementById('evalPlaceholder').style.display = 'none';
    const container = document.getElementById('evalContent');
    container.style.display = 'flex';
    container.style.flexDirection = 'column';
    container.style.gap = '12px';

    let html = '';

    // Overall score
    if (ev.overall_score != null) {
      html += '<div class="overall-score"><div class="number">' + ev.overall_score + '</div><div class="label">Overall Score / 5</div></div>';
    }

    // Category scores
    if (ev.scores) {
      html += '<div class="score-card"><h3>Category Scores</h3>';
      for (const [key, val] of Object.entries(ev.scores)) {
        const label = key.replace(/_/g, ' ');
        const score = typeof val === 'object' ? val.score : val;
        const notes = typeof val === 'object' ? val.notes : '';
        html += '<div class="score-row"><span class="score-label">' + escapeHtml(label) + '</span>';
        html += '<span class="score-value score-' + score + '">' + score + '/5</span></div>';
        if (notes) html += '<div style="font-size:11px;color:var(--text-dim);padding:2px 0 6px">' + escapeHtml(notes) + '</div>';
      }
      html += '</div>';
    }

    // Critical failures
    if (ev.critical_failures && ev.critical_failures.length) {
      html += '<div class="score-card"><h3>\u26A0 Critical Failures</h3><ul class="eval-list">';
      ev.critical_failures.forEach(f => { html += '<li class="bug">' + escapeHtml(f) + '</li>'; });
      html += '</ul></div>';
    }

    // Bugs
    if (ev.bugs && ev.bugs.length) {
      html += '<div class="score-card"><h3>\uD83D\uDC1B Bugs</h3><ul class="eval-list">';
      ev.bugs.forEach(b => { html += '<li class="bug">' + escapeHtml(b) + '</li>'; });
      html += '</ul></div>';
    }

    // Highlights
    if (ev.highlights && ev.highlights.length) {
      html += '<div class="score-card"><h3>\u2728 Highlights</h3><ul class="eval-list">';
      ev.highlights.forEach(h => { html += '<li class="highlight">' + escapeHtml(h) + '</li>'; });
      html += '</ul></div>';
    }

    // Summary
    if (ev.summary) {
      html += '<div class="eval-summary">' + escapeHtml(ev.summary) + '</div>';
    }

    container.innerHTML = html;
  }

  // ---- Manual send ----
  async function sendManual() {
    const input = document.getElementById('manualInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    if (!manualSession) {
      const storyId = document.getElementById('storySelect').value;
      if (!storyId) { addSystemMsg('Select a story first.'); return; }
      manualSession = 'manual_' + Date.now();
      addSystemMsg('Starting manual session for ' + storyId + '...');
      await fetch('/api/status'); // just to get API_BASE
      const apiBase = 'https://beta-api.storieschat.ai';
      await fetch(apiBase + '/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ session_id: manualSession, message: '__cmd_reset__' }),
      });
      const r = await fetch(apiBase + '/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ session_id: manualSession, message: '__cmd_newgame__:' + storyId + '|M|Player' }),
      });
      const data = await r.json();
      addChatMsg({ role: 'npc', content: data.reply || 'No response', turn: 0 });
    }

    addChatMsg({ role: 'player', content: msg, turn: turnCount + 1 });
    turnCount++;
    updateStats();

    const t0 = performance.now();
    try {
      const r = await fetch('https://beta-api.storieschat.ai/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ session_id: manualSession, message: msg }),
      });
      const data = await r.json();
      const lat = Math.round(performance.now() - t0);
      const tokens = data.usage?.total_tokens || 0;
      addChatMsg({ role: 'npc', content: data.reply || 'No response', turn: turnCount, latency_ms: lat, tokens });
      latencies.push(lat);
      totalTokens += tokens;
      updateStats();
    } catch (e) {
      addSystemMsg('API error: ' + e.message);
    }
  }

  document.getElementById('manualInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendManual();
  });

  // ---- Export ----
  function exportLog() {
    if (!conversation.length) { alert('No conversation to export.'); return; }
    const blob = new Blob([JSON.stringify(conversation, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'storieschat_test_' + Date.now() + '.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- Capture to test case ----
  function createTestCaseFromConversation() {
    if (!conversation.length) { alert('No conversation to capture.'); return; }
    const playerMsgs = conversation.filter(m => m.role === 'player').map(m => m.content || '').filter(Boolean);
    if (!playerMsgs.length) { alert('No player messages found to capture.'); return; }

    const storyId = document.getElementById('storySelect').value || '';
    const ts = new Date().toISOString().replace(/[:.]/g, '-');
    const tc = {
      id: 'tc_capture_' + ts,
      name: 'Captured run ' + ts,
      description: 'Replay of captured player inputs from UI run.',
      story_id: storyId,
      strategy: 'Captured automatically from UI. Replay these exact player messages to reproduce.',
      messages: playerMsgs,
    };

    if (!Array.isArray(testCases)) testCases = [];
    testCases.push(tc);
    editingTestCaseIdx = testCases.length - 1;
    saveTestCasesToServer();
    renderTestCaseList();
    renderTestCaseEditor();
    switchTab('test-cases');
  }

  // ---- Leaderboard ----
  async function loadLeaderboard() {
    const container = document.getElementById('leaderboardContent');
    try {
      const r = await fetch('/api/scores');
      const rows = await r.json();
      if (!rows.length) {
        container.innerHTML = '<div class="eval-placeholder">No scores recorded yet. Run a test with Auto-evaluate enabled.</div>';
        return;
      }

      // Sort by overall_score descending
      rows.sort((a, b) => (parseFloat(b.overall_score) || 0) - (parseFloat(a.overall_score) || 0));

      let html = '<table class="lb-table"><thead><tr>';
      html += '<th>#</th><th>Time</th><th>Story</th><th>Chatter</th><th>Chatter Persona</th><th>Rater</th><th>Rater Persona</th><th>Turns</th>';
      html += '<th>Canon</th><th>Voice</th><th>Agency</th><th>Resp.</th><th>Mystery</th><th>Immers.</th><th>Edge</th>';
      html += '<th>Overall</th><th>Latency</th><th>Notes</th>';
      html += '</tr></thead><tbody>';

      rows.forEach((row, i) => {
        const os = parseFloat(row.overall_score) || 0;
        const scoreClass = os >= 4 ? 'score-4' : os >= 3 ? 'score-3' : 'score-2';
        const notes = row.deduction_notes || row.summary || '';
        const hasNotes = notes.length > 0;
        html += '<tr>';
        html += '<td class="lb-rank">' + (i + 1) + '</td>';
        html += '<td>' + escapeHtml(row.timestamp || '') + '</td>';
        html += '<td>' + escapeHtml(row.story_id || '') + '</td>';
        html += '<td style="font-size:11px">' + escapeHtml(row.chatter_model || '') + '</td>';
        html += '<td style="font-size:11px">' + escapeHtml(row.chatter_persona || row.eval_persona || '') + '</td>';
        html += '<td style="font-size:11px">' + escapeHtml(row.rater_model || '') + '</td>';
        html += '<td style="font-size:11px">' + escapeHtml(row.rater_persona || row.eval_persona || '') + '</td>';
        html += '<td>' + (row.turns || '') + '</td>';
        html += '<td>' + (row.canon_fidelity || '-') + '</td>';
        html += '<td>' + (row.character_voice || '-') + '</td>';
        html += '<td>' + (row.player_agency_respect || '-') + '</td>';
        html += '<td>' + (row.responsiveness || '-') + '</td>';
        html += '<td>' + (row.mystery_mechanics || '-') + '</td>';
        html += '<td>' + (row.immersion_quality || '-') + '</td>';
        html += '<td>' + (row.edge_case_resilience || '-') + '</td>';
        html += '<td class="lb-score ' + scoreClass + '">' + (row.overall_score || '-') + '</td>';
        html += '<td>' + (row.avg_latency_ms || '-') + 'ms</td>';
        if (hasNotes) {
          html += '<td style="max-width:300px"><details><summary style="cursor:pointer;font-size:11px;color:var(--accent)">View</summary>';
          html += '<div style="font-size:11px;color:var(--text);margin-top:4px;white-space:pre-wrap;line-height:1.4">' + escapeHtml(notes) + '</div>';
          html += '</details></td>';
        } else {
          html += '<td style="color:var(--text-dim);font-size:11px">-</td>';
        }
        html += '</tr>';
      });

      html += '</tbody></table>';
      container.innerHTML = html;
    } catch (e) {
      container.innerHTML = '<div class="eval-placeholder">Failed to load scores: ' + escapeHtml(e.message) + '</div>';
    }
  }

  // ---- Test Cases ----
  async function loadTestCases() {
    try {
      const r = await fetch('/api/test-cases');
      testCases = await r.json();
    } catch (e) {
      testCases = [];
    }
    renderTestCaseList();
  }

  function renderTestCaseList() {
    const container = document.getElementById('testCaseList');
    if (!testCases.length) {
      container.innerHTML = '<div class="eval-placeholder" style="padding:20px">No test cases yet. Click + New to create one.</div>';
      return;
    }
    let html = '';
    testCases.forEach((tc, i) => {
      const isActive = i === editingTestCaseIdx;
      html += '<div class="tc-card" style="' + (isActive ? 'border-color:var(--accent)' : '') + '">';
      html += '<div class="tc-header">';
      html += '<span class="tc-name">' + escapeHtml(tc.name || 'Untitled') + '</span>';
      html += '<div class="tc-actions">';
      html += '<button class="btn btn-primary btn-sm" onclick="runTestCase(' + i + ')" title="Run">\u25B6</button>';
      html += '<button class="btn btn-secondary btn-sm" onclick="editTestCase(' + i + ')" title="Edit">Edit</button>';
      html += '<button class="btn btn-danger btn-sm" onclick="deleteTestCase(' + i + ')" title="Delete">Del</button>';
      html += '</div></div>';
      html += '<div class="tc-desc">' + escapeHtml(tc.description || '') + '</div>';
      html += '<div class="tc-msgs">' + (tc.messages || []).map(m => escapeHtml(m)).join('<br>') + '</div>';
      html += '</div>';
    });
    container.innerHTML = html;
  }

  function newTestCase() {
    testCases.push({
      id: 'tc_' + Date.now(),
      name: 'New Test Case',
      description: '',
      story_id: '',
      strategy: '',
      messages: ['Hello, who are you?'],
    });
    editingTestCaseIdx = testCases.length - 1;
    renderTestCaseList();
    renderTestCaseEditor();
  }

  function editTestCase(idx) {
    editingTestCaseIdx = idx;
    renderTestCaseList();
    renderTestCaseEditor();
  }

  function deleteTestCase(idx) {
    const name = testCases[idx]?.name || 'Untitled';
    if (!confirm('Delete "' + name + '"?')) return;
    testCases.splice(idx, 1);
    if (editingTestCaseIdx === idx) editingTestCaseIdx = -1;
    else if (editingTestCaseIdx > idx) editingTestCaseIdx--;
    saveTestCasesToServer(true);
    showSaveToast('Deleted "' + name + '"');
    renderTestCaseList();
    renderTestCaseEditor();
  }

  function renderTestCaseEditor() {
    const container = document.getElementById('testCaseEditor');
    if (editingTestCaseIdx < 0 || editingTestCaseIdx >= testCases.length) {
      container.innerHTML = '<div class="eval-placeholder">Select or create a test case to edit it.</div>';
      return;
    }
    const tc = testCases[editingTestCaseIdx];
    let html = '<div style="display:flex;flex-direction:column;gap:12px">';
    html += '<div class="section-label">Edit Test Case</div>';

    html += '<div class="control-group">';
    html += '<label style="font-size:12px;color:var(--text-dim)">Name</label>';
    html += '<input type="text" id="tcName" value="' + escapeAttr(tc.name || '') + '" onchange="updateTC()" />';
    html += '</div>';

    html += '<div class="control-group">';
    html += '<label style="font-size:12px;color:var(--text-dim)">Description</label>';
    html += '<input type="text" id="tcDesc" value="' + escapeAttr(tc.description || '') + '" onchange="updateTC()" />';
    html += '</div>';

    html += '<div class="control-group">';
    html += '<label style="font-size:12px;color:var(--text-dim)">Strategy (instructions for the player agent)</label>';
    html += '<textarea id="tcStrategy" rows="3" onchange="updateTC()">' + escapeHtml(tc.strategy || '') + '</textarea>';
    html += '</div>';

    html += '<div class="control-group">';
    html += '<label style="font-size:12px;color:var(--text-dim)">Messages (one per line)</label>';
    html += '<textarea id="tcMessages" rows="8" onchange="updateTC()">' + escapeHtml((tc.messages || []).join('\n')) + '</textarea>';
    html += '</div>';

    html += '<div class="btn-row">';
    html += '<button class="btn btn-primary" onclick="runTestCase(' + editingTestCaseIdx + ')">\u25B6 Run This Test</button>';
    html += '<button class="btn btn-secondary" onclick="saveTestCasesToServer()">Save All</button>';
    html += '</div>';

    html += '</div>';
    container.innerHTML = html;
  }

  function updateTC() {
    if (editingTestCaseIdx < 0) return;
    const tc = testCases[editingTestCaseIdx];
    tc.name = document.getElementById('tcName')?.value || '';
    tc.description = document.getElementById('tcDesc')?.value || '';
    tc.strategy = document.getElementById('tcStrategy')?.value || '';
    const msgsRaw = document.getElementById('tcMessages')?.value || '';
    tc.messages = msgsRaw.split('\n').filter(l => l.trim() !== '');
    renderTestCaseList();
  }

  async function saveTestCasesToServer(silent) {
    try {
      if (!Array.isArray(testCases)) testCases = [];

      const seen = new Set();
      const normalized = testCases.map((tc, idx) => {
        const copy = { ...tc };
        if (!copy.id) copy.id = 'tc_' + Date.now() + '_' + idx;
        if (seen.has(copy.id)) {
          copy.id = copy.id + '_' + Math.random().toString(36).slice(2, 8);
        }
        seen.add(copy.id);
        return copy;
      });

      testCases = normalized;

      const resp = await fetch('/api/test-cases', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ test_cases: testCases }),
      });
      if (resp.ok && !silent) {
        showSaveToast('Saved ' + testCases.length + ' test case(s)');
      }
    } catch (e) {
      alert('Failed to save: ' + e.message);
    }
  }

  function showSaveToast(text) {
    let toast = document.getElementById('saveToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'saveToast';
      toast.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--green);color:#fff;padding:8px 20px;border-radius:8px;font-size:13px;font-weight:600;z-index:9999;opacity:0;transition:opacity 0.3s;pointer-events:none;';
      document.body.appendChild(toast);
    }
    toast.textContent = text;
    toast.style.opacity = '1';
    setTimeout(() => { toast.style.opacity = '0'; }, 2000);
  }

  function runTestCase(idx) {
    const tc = testCases[idx];
    if (!tc) return;
    // If test case has a story_id, set it
    if (tc.story_id) {
      document.getElementById('storySelect').value = tc.story_id;
    }
    startRun({
      name: tc.name,
      messages: tc.messages || [],
      strategy: tc.strategy || '',
    });
  }

  // ---- Utility ----
  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }
  function escapeAttr(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  init();
  loadTestCases();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print(f"\n  \U0001F9EA StoriesChat Agent Tester")
    print(f"  Open http://localhost:{PORT} in your browser\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
