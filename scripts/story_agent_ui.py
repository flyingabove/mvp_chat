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
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_BASE = "https://beta-api.storieschat.ai"
DEFAULT_MODEL = "llama3.1:8b"
PLAYER_NAME = "Alex"
PLAYER_GENDER = "M"
PORT = 8899

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

EVALUATOR_PROMPT = """\
You are a QA evaluator for a text-based murder mystery chat game.
Analyze the following conversation between a player and an NPC character.

Assume one player persona while evaluating (and state which you used):
- Curious Rookie: polite, exploratory questions.
- Confrontational Cop: direct, pressure-testing and skeptical.
- Empathetic Confidant: warm, rapport-first, looking for feelings/context.
- Chaos Gremlin: edge cases, non sequiturs, tries to break scripts.

Rate each category 1-5 and provide brief notes:

1. **Character Consistency** — Does the NPC stay in character? Consistent personality/voice?
2. **Narrative Quality** — Are responses engaging, atmospheric, well-written?
3. **Responsiveness** — Does the NPC actually address what the player says?
4. **Mystery Mechanics** — Does the NPC appropriately reveal/withhold clues?
5. **Edge Case Handling** — How does the NPC handle odd or unexpected inputs?
6. **Immersion Breaking** — Any moments where the NPC breaks character or feels robotic?

Also list any specific BUGS or ISSUES you noticed.

Format your response as JSON:
{
    "scores": {
        "character_consistency": {"score": N, "notes": "..."},
        "narrative_quality": {"score": N, "notes": "..."},
        "responsiveness": {"score": N, "notes": "..."},
        "mystery_mechanics": {"score": N, "notes": "..."},
        "edge_case_handling": {"score": N, "notes": "..."},
        "immersion_breaking": {"score": N, "notes": "..."}
    },
    "overall_score": N,
    "bugs": ["...", "..."],
    "highlights": ["...", "..."],
    "summary": "..."
}
"""

EVAL_PERSONAS = {
    "curious_rookie": "Curious Rookie: polite, exploratory questions.",
    "confrontational_cop": "Confrontational Cop: direct, pressure-testing and skeptical.",
    "empathetic_confidant": "Empathetic Confidant: warm, rapport-first, feelings/context seeking.",
    "chaos_gremlin": "Chaos Gremlin: edge-case breaker, non sequiturs, stress-tests scripts.",
  "first_time_user": "First-time User: new to chatbots, tentative, asks basic or clarifying questions.",
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
        model = config.get("model", DEFAULT_MODEL)
        do_eval = config.get("evaluate", True)
        eval_persona = config.get("eval_persona", "curious_rookie")

        session_id = f"ui_{story_id}_{int(time.time())}"

        async def send(event: str, data: dict):
            await ws.send_json({"event": event, **data})

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
            for turn in range(1, num_turns + 1):
                if active_runs.get(run_id, {}).get("status") == "stopped":
                    await send("status", {"text": "Stopped by user."})
                    break

                # Get player message
                if use_llm:
                    try:
                        history = "\n".join(
                            f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                            for m in conversation[-6:]
                        )
                        prompt = f"Conversation so far:\n{history}\n\nTurn {turn}/{num_turns}. What do you say next?"
                        player_msg = await ollama_generate(model, AGENT_PERSONA, prompt)
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

                await send("progress", {"turn": turn, "total": num_turns})

                if "Game already finished" in npc_reply or "END GAME" in npc_reply:
                    await send("status", {"text": "Game over!"})
                    break

            # --- Evaluate ---
            if do_eval:
                await send("status", {"text": "Evaluating conversation quality..."})
                try:
                    transcript = "\n".join(
                        f"{'PLAYER' if m['role'] == 'player' else 'NPC'}: {m['content']}"
                        for m in conversation
                    )
                    persona_desc = EVAL_PERSONAS.get(eval_persona, eval_persona)
                    prompt = (
                        f"Story: {story_id}\n"
                        f"Total turns: {len([m for m in conversation if m['role'] == 'player'])}\n\n"
                        f"Player persona (assumed for evaluation): {persona_desc}\n\n"
                        f"=== CONVERSATION ===\n{transcript}\n=== END ===\n\n"
                        f"Provide your evaluation as JSON."
                    )
                    raw = await ollama_generate(model, EVALUATOR_PROMPT, prompt)
                    start = raw.find("{")
                    end = raw.rfind("}") + 1
                    if start >= 0 and end > start:
                        evaluation = json.loads(raw[start:end])
                    else:
                        evaluation = {"raw_response": raw, "parse_error": "No JSON found"}
                    await send("evaluation", evaluation)
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
HTML_PAGE = """<!DOCTYPE html>
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
    grid-template-columns: 320px 1fr 340px;
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

  select, input[type="number"] {
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
  select:focus, input:focus { border-color: var(--accent); }
  select option { background: var(--surface2); }

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

  /* ---- Eval panel ---- */
  .eval-panel {
    background: var(--surface);
    padding: 20px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

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
    height: 100%;
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
</style>
</head>
<body>
<div class="app">
  <!-- Header -->
  <div class="header">
    <h1>&#x1F9EA; STORIESCHAT TESTER</h1>
    <div class="dot" id="statusDot"></div>
    <span class="status-text" id="statusText">Connecting...</span>
  </div>

  <!-- Left sidebar: Controls -->
  <div class="sidebar">
    <div>
      <div class="section-label">Story</div>
      <div class="control-group">
        <select id="storySelect"><option value="">Loading stories...</option></select>
      </div>
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

      <div class="hint">
        Eval personas: Curious Rookie (polite), Confrontational Cop (direct),
        Empathetic Confidant (warm), Chaos Gremlin (edge-case breaker),
        First-time User (new to chatbots, tentative).
      </div>

      <div class="control-group" style="margin-top:6px">
        <label style="font-size:12px;color:var(--text-dim)">Eval persona</label>
        <select id="personaSelect">
          <option value="curious_rookie">Curious Rookie</option>
          <option value="confrontational_cop">Confrontational Cop</option>
          <option value="empathetic_confidant">Empathetic Confidant</option>
          <option value="chaos_gremlin">Chaos Gremlin</option>
          <option value="first_time_user">First-time User</option>
        </select>
      </div>

      <div class="control-group" style="margin-top:4px">
        <label style="font-size:12px;color:var(--text-dim)">Ollama model</label>
        <select id="modelSelect"><option value="llama3.1:8b">llama3.1:8b</option></select>
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
          <div class="stat-val" id="statLatency">—</div>
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
    </div>
  </div>

  <!-- Center: Chat -->
  <div class="chat-panel">
    <div class="chat-messages" id="chatMessages">
      <div class="system-msg">Select a story and click Run to begin.</div>
    </div>
    <div class="chat-input-bar">
      <input type="text" id="manualInput" placeholder="Type a manual message..." disabled />
      <button id="sendBtn" onclick="sendManual()" disabled>Send</button>
    </div>
  </div>

  <!-- Right: Evaluation -->
  <div class="eval-panel" id="evalPanel">
    <div class="section-label">Evaluation</div>
    <div class="eval-placeholder" id="evalPlaceholder">
      Run a test with "Auto-evaluate" enabled<br>and an Ollama model to see results here.
    </div>
    <div id="evalContent" style="display:none"></div>
  </div>
</div>

<script>
  let ws = null;
  let running = false;
  let conversation = [];
  let latencies = [];
  let totalTokens = 0;
  let turnCount = 0;
  // For manual message mode
  let manualSession = null;

  // Init
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

    // Populate models
    const msel = document.getElementById('modelSelect');
    msel.innerHTML = '';
    if (data.ollama.available && data.ollama.models.length) {
      data.ollama.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        msel.appendChild(opt);
      });
      dot.classList.add('connected');
      txt.textContent = 'API + Ollama ready';
    } else {
      msel.innerHTML = '<option value="">No models (Ollama offline)</option>';
      if (data.stories.length) {
        dot.classList.add('connected');
        txt.textContent = 'API ready (Ollama offline — scripted mode only)';
      } else {
        txt.textContent = 'API unreachable';
      }
    }
  }

  function startRun() {
    const storyId = document.getElementById('storySelect').value;
    if (!storyId) return;

    const turns = parseInt(document.getElementById('turnsInput').value) || 12;
    const useLlm = document.getElementById('llmToggle').classList.contains('on');
    const evaluate = document.getElementById('evalToggle').classList.contains('on');
    const evalPersona = document.getElementById('personaSelect').value || 'curious_rookie';
    const model = document.getElementById('modelSelect').value;

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

    addSystemMsg('Starting ' + storyId + '...');

    ws = new WebSocket('ws://' + location.host + '/ws/run');
    ws.onopen = () => {
      ws.send(JSON.stringify({
        story_id: storyId,
        turns: turns,
        use_llm: useLlm,
        model: model,
        evaluate: evaluate,
        eval_persona: evalPersona,
      }));
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
        addSystemMsg('⚠ ' + msg.text);
        break;
      case 'error':
        addSystemMsg('✗ ' + msg.text);
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
      html += '<div class="meta">' + msg.latency_ms + 'ms · ' + (msg.tokens || 0) + ' tok</div>';
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
    if (ev.overall_score) {
      html += '<div class="overall-score"><div class="number">' + ev.overall_score + '</div><div class="label">Overall Score / 5</div></div>';
    }

    // Category scores
    if (ev.scores) {
      html += '<div class="score-card"><h3>Category Scores</h3>';
      for (const [key, val] of Object.entries(ev.scores)) {
        const label = key.replace(/_/g, ' ').replace(/\\b\\w/g, c => c.toUpperCase());
        const score = typeof val === 'object' ? val.score : val;
        const notes = typeof val === 'object' ? val.notes : '';
        html += '<div class="score-row"><span class="score-label">' + label + '</span>';
        html += '<span class="score-value score-' + score + '">' + score + '/5</span></div>';
        if (notes) html += '<div style="font-size:11px;color:var(--text-dim);padding:2px 0 6px">' + escapeHtml(notes) + '</div>';
      }
      html += '</div>';
    }

    // Bugs
    if (ev.bugs && ev.bugs.length) {
      html += '<div class="score-card"><h3>&#x1F41B; Bugs</h3><ul class="eval-list">';
      ev.bugs.forEach(b => { html += '<li class="bug">' + escapeHtml(b) + '</li>'; });
      html += '</ul></div>';
    }

    // Highlights
    if (ev.highlights && ev.highlights.length) {
      html += '<div class="score-card"><h3>&#x2728; Highlights</h3><ul class="eval-list">';
      ev.highlights.forEach(h => { html += '<li class="highlight">' + escapeHtml(h) + '</li>'; });
      html += '</ul></div>';
    }

    // Summary
    if (ev.summary) {
      html += '<div class="eval-summary">' + escapeHtml(ev.summary) + '</div>';
    }

    container.innerHTML = html;
  }

  // Manual send
  async function sendManual() {
    const input = document.getElementById('manualInput');
    const msg = input.value.trim();
    if (!msg) return;
    input.value = '';

    // If no session, start one
    if (!manualSession) {
      const storyId = document.getElementById('storySelect').value;
      if (!storyId) { addSystemMsg('Select a story first.'); return; }
      manualSession = 'manual_' + Date.now();
      addSystemMsg('Starting manual session for ' + storyId + '...');
      // Reset + newgame
      await fetch('https://beta-api.storieschat.ai/api/chat', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ session_id: manualSession, message: '__cmd_reset__' }),
      });
      const r = await fetch('https://beta-api.storieschat.ai/api/chat', {
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

  function escapeHtml(s) {
    if (!s) return '';
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
  }

  init();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    print(f"\n  🧪 StoriesChat Agent Tester")
    print(f"  Open http://localhost:{PORT} in your browser\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")