Debug System — AI Learnings & Reference
==========================================

> **What this doc is for:** How the debug/scorer/grader system works (player agent, grader, WebSocket protocol). Edit this doc when the debug system, scoring, or player-agent loop changes.

> **Terminology**:
> - **Story master** = NPC-generating AI (always /api/chat pipeline).
> - **Player** (or "player agent") = LLM AI that simulates a human in automated test runs. NOT a real human.
> - **User** = real human interacting with the game via the browser.
> - **Grader** = LLM AI that evaluates run quality.
>
> This distinction matters for future logging: user sessions come from humans; player sessions come from the debug engine's LLM agent.

Overview
--------
The debug system is integrated into the main backend and accessible at `/beta/debug`.
It runs automated conversations (player agent vs. story master NPC) and grades them
with a separate grader LLM.

File Locations
--------------
- Debug engine:        backend/app/api/debug_engine.py  (WebSocket + REST handler)
- Debug UI:            frontend/debug.html  (served at /beta/debug)
- Thin local launcher: scripts/scorer/story_agent_ui.py  (~20 lines, starts backend on port 8899)
- Scoring rubric:      scripts/scorer/scorer_instructions.md
- Score history CSV:   data/debug_scores.csv  (or /data/debug_scores.csv on Railway)
- Test case library:   data/test_cases.json   (or /data/test_cases.json on Railway)
- Run JSON archives:   data/debug_runs/*.json (or /data/debug_runs/ on Railway)

Related backend files:
- Prompt Engine:      backend/app/api/prompt_engine.py  → POST /api/chat
- Story context API:  backend/app/api/stories.py        → GET /api/stories/{story_id}/context
- Story JSONs:        backend/app/stories/<folder>/<story_id>_story.json
- Transient buffer:   backend/app/engine/transient_buffer.py

Architecture
------------
Browser → /beta/debug (debug.html) → WebSocket /beta/debug/ws (debug_engine.py)
                                    ↕
                              POST /api/chat (prompt_engine.py — story master)
                                    ↕
                              Ollama or cloud API (player + grader)

Mode Detection (URL-based, automatic)
--------------------------------------
hostname == "localhost" or "127.0.0.1"  →  **local mode**
any other hostname                       →  **online mode**

| AI Role      | Local (Ollama)      | Online (cloud API)         |
|--------------|---------------------|----------------------------|
| Story master | /api/chat → Ollama  | /api/chat → OpenAI/cloud   |
| Player       | ollama_generate()   | cloud_generate()           |
| Grader       | ollama_generate()   | cloud_generate()           |

Story master ALWAYS goes through /api/chat. In local mode the backend env vars
(STORY_MASTER_BASE_URL etc.) redirect /api/chat's underlying call to Ollama.

Local Mode Setup
-----------------
Run the thin launcher:
  python scripts/scorer/story_agent_ui.py

Then open: http://localhost:8899/beta/debug

Sets env vars automatically:
  STORY_MASTER_BASE_URL = http://localhost:11434/v1
  STORY_MASTER_MODEL    = llama3.1:8b
  STORY_MASTER_API_KEY  = ollama

Online Mode
-----------
Deployed to Railway at /beta/debug (same backend, cloud models).
Storage goes to /data Railway volume (detected automatically: Path("/data").exists()).

Key Constants in debug_engine.py
---------------------------------
- DEFAULT_PLAYER_MODEL  = "llama3.1:8b"   (local)
- DEFAULT_GRADER_MODEL  = "gemma3:12b"    (local)
- PLAYER_API_MODEL      = env PLAYER_API_MODEL or OPENAI_MODEL  (online)
- GRADER_API_MODEL      = env GRADER_API_MODEL or OPENAI_MODEL  (online)
- PLAYER_NAME           = "Alex"
- PLAYER_GENDER         = "M"
- History window        = 12 turns (wider than original 6 to reduce looping)

How a Run Works (WebSocket /beta/debug/ws)
-------------------------------------------
1. Client sends config JSON (story_id, turns, models, personas, etc.)
2. Backend sends __cmd_reset__ → __cmd_newgame__:story_id|gender|name → [D] (enable debug)
3. Backend calls _build_player_brief() — fetches story context for player (public info only, no spoilers)
4. Loop for N turns:
   a. Generate player message (player LLM via generate(), test case messages, or fallback list)
   b. POST to /api/chat (story master) with player message
   c. Emit "message", "progress", "debug" events over WebSocket
   d. Run _verify_game_ended() — two-stage check (literal + LLM verifier)
5. Save run JSON to DEBUG_RUNS_DIR
6. After conversation ends:
   a. Fetch /api/stories/{story_id}/context (story canon for grader)
   b. Run grader LLM with transcript + scorer_instructions.md + story context
   c. Parse JSON response, append row to debug_scores.csv
   d. Emit "evaluation" event
   e. Emit "done" with active session_id (manual mode can continue the same session)

Player Brief (Anti-loop feature)
----------------------------------
_build_player_brief() fetches /api/story/{story_id} (the PUBLIC endpoint shown
to real human users in the UI) and builds only what a real user would know:

- STORY: title
- YOUR ROLE: player_role from rules (e.g. "You are a detective")
- HOW TO WIN: win_text_rule from goal (e.g. "Get a confession from the killer")
- YOUR GOAL: Discover what happened and who is responsible.

Deliberately NOT included (not shown to real users):
- Character names / roles  → real users discover these through gameplay
- Protagonist personality  → internal story JSON, never surfaced in UI
- Canonical facts          → spoilers

The brief is injected into the player agent's system prompt before turn 1.
Combined with the 12-turn history window and anti-loop instruction, this
simulates a realistic first-time player experience without giving the LLM
an unfair information advantage over real users.

WebSocket Events
-----------------
- "status"           — system status text
- "message"          — chat message (role, content, turn, latency_ms, tokens)
- "debug"            — turn-level debug info (debug_box, prompt_debug) — stored in debugPayloads{}
- "progress"         — turn X / total turns
- "warning"          — non-fatal warning
- "error"            — error message
- "evaluation"       — final grader JSON
- "post_game_review" — player model's open-ended post-game thoughts
- "game_won"         — signals the "YOU WIN" overlay
- "done"             — run complete (conversation + session_id)

After "done", the tester UI enables manual input and reuses that run's session id.

Player Personas
---------------
- curious_rookie       — polite, exploratory questions (default)
- confrontational_cop  — direct, pressure-testing, skeptical
- empathetic_confidant — warm, rapport-first, feelings-seeking
- chaos_gremlin        — edge-case breaker, non-sequiturs, stress-tests
- first_time_user      — tentative, basic/clarifying questions
- expert_llm_grader    — experienced evaluator (default for grader)

Scoring Dimensions (7 dimensions, weighted)
--------------------------------------------
| Dimension              | Weight | What it measures                                    |
|------------------------|--------|-----------------------------------------------------|
| Canon Fidelity         | 2.0x   | Never invents facts, contradicts identity           |
| Character Voice        | 1.5x   | Distinct personality, consistent tone               |
| Player Agency Respect  | 2.0x   | Never narrates player actions/feelings/thoughts     |
| Responsiveness         | 1.0x   | Answers questions, reacts to tone                   |
| Mystery Mechanics      | 1.5x   | Clues when earned, believable withholding           |
| Immersion Quality      | 1.0x   | Atmospheric, clear speaker labels                   |
| Edge Case Resilience   | 0.5x   | Handles gibberish, empty input, prompt injection    |

Critical Failures (auto-deductions from overall)
-------------------------------------------------
- NPC speaks as player              → -2.0
- NPC reveals SECRET_CANON unprompted → -2.0
- NPC contradicts ANCHOR identity   → -1.0
- NPC refers to itself in 3rd person → -1.0

Context Modal (click NPC message)
----------------------------------
When user clicks an NPC message, a full-context modal opens with collapsible sections.
All sections have per-section copy buttons.

Section order:
 1. Game State         — timestamp, location, speakers, story, instance, turn, truth_mode (open)
 2. Transient Buffer   — scene entries with TTL remaining (collapsed; tag: transient)
 3. Player Message     — raw player input for this turn (open)
 4. NPC Response       — NPC reply + latency_ms + token count (open)
 5. RETRIEVED KNOWLEDGE       — FAISS/BM25 chunks (open; tag: retrieval)
 6. CHARACTER SELF-KNOWLEDGE  — identity facts (open; tag: identity)
 7. CANONICAL MEMORIES        — epistemic facts (open; tag: canonical)
 8. RELATIONSHIPS             — character graph feelings (open; tag: relationships)
 9. LOCATION                  — current scene description (open; tag: location)
10. BELIEFS                   — character beliefs (open; tag: beliefs)
11. CHARACTER DETAILS         — motive & tells (open; tag: details)
12. TRUTH MODE                — debug truth override if active (open; tag: truth)
13. FIRST TURN HINT           — opening hint if present (open; tag: hint)
14. Full System Prompt (raw)  — complete assembled system prompt (collapsed)
15. User Message Header       — the header injected before user message (collapsed)
16-20. Knowledge Chunks, Retrieval Debug, Raw Debug Box

Debug data stored in JS variable debugPayloads[turn] — populated via "debug" WS events.

Debugging Workflow
------------------
Debug mode is auto-enabled by the debug engine (sends "[D]" after newgame).
Every API response while in debug mode includes `debug_box` and `prompt_debug`.

What `debug_box` contains:
  - timestamp, location, location_uuid, speakers
  - transient_count, transient_entries (text + turns_remaining)

What `prompt_debug` contains:
  - story, instance, turn, truth_mode, trimmed_history
  - prompt_layers: dict of named system prompt sections
  - system_prompt_preview, header, chunks, retrieval_debug

Leaderboard
-----------
- Reads data/debug_scores.csv (or /data/debug_scores.csv on Railway)
- Shows all runs ranked by overall_score descending
- Color-coded: Red (1-2), Yellow (3), Green (4-5)
- 26 columns including player/grader models, personas, latency, tokens

Test Cases
----------
Structure: { name, messages[], strategy }
1 built-in test case: "Confusing IU #1" (message: "what happened to the previous tenant?")
User can create/edit/delete/run test cases. Saved to data/test_cases.json.
When a test case runs, its messages replace LLM-generated player messages.
Strategy field is injected into player agent's system prompt.

Storage Path Detection
-----------------------
DATA_DIR = Path("/data") if Path("/data").exists() else Path("./data")
  - Online (Railway): /data volume (50GB persistent)
  - Local: ./data relative to working directory

Story Context for Scoring
--------------------------
The grader fetches GET /api/stories/{story_id}/context which returns:
- character_self_knowledge (identity facts NPC must embody)
- canonical_facts (ground truth with known_by attribution)
- characters (key, name, role, is_main, is_suspect, tags)
- protagonist (player character details)
- rules

This is formatted into a STORY CONTEXT block prepended to the grader prompt.

Game-End Detection
-------------------
Two-stage: fast literal check → dedicated grader LLM call
1. Fast: "END GAME YOU WIN" or "Game already finished" or "END GAME" in NPC reply
2. If (1) passes, call grader LLM with _verify_game_ended() — outputs [@@GAME ENDED CONGRATS@@] or NO
Returns True only when the exact sentinel is output.
Chatter/player agent has no game-end instructions — plays naturally.

OOC Direct Channel (Out-of-Character)
--------------------------------------
Players can speak directly to the narrator/author by wrapping their message in `()` or `[]`:
  - `(is IU alive or dead?)` → narrator steps out of scene and responds in `()`
  - `[what happened before the game started?]` → same behavior

build_messages() in prompt_builder.py detects full-wrap and prepends [OOC:] directive.

Canon Correction — MANDATORY
------------------------------
If the player operates under a false belief about a canonical fact, the NPC must correct:
  - Correction wrapped in parentheses using NARRATOR THIRD-PERSON voice:
    "(Just to be clear — IU is the one who died here, not someone else.)"
  - NOT character first-person: "(I'm the one who died)" is WRONG
  - Then resumes the scene naturally.
Documented in base_prompt as "CANON CORRECTION — OVERRIDES EVERYTHING".

Player Agent Persona (AGENT_PERSONA)
--------------------------------------
Written for naturalistic, human-like chat behaviour:
- Writes like someone texting on their phone — short, casual, reactive.
- NO preambles, no apologies, no meta-commentary.
- One or two sentences max.
- No emojis ever.
- Do NOT start with "PLAYER:", "NPC:", or any role label.
- Game brief injected (story title, protagonist, characters, goal) → reduces looping.
- Anti-loop instruction in per-turn prompt: "Ask a NEW question... do NOT repeat questions."

Gotchas & Common Mistakes
--------------------------
1. The debug UI is now frontend/debug.html served at /beta/debug.
   story_agent_ui.py is a thin ~20-line launcher only.

2. Debug data collection (debugPayloads) must stay in the HTML.
   The context modal depends on it.

3. The engine auto-enables debug mode by sending "[D]" after newgame. If removed,
   context modals will be empty.

4. Ollama must be running locally for local mode. If offline, UI gracefully degrades —
   can still run with fallback messages but no LLM evaluation.

5. CSV appends — never overwrite debug_scores.csv. Each run adds one row.

6. Third-person self-reference is a CRITICAL FAILURE. If the NPC IS the dead person
   (ghost), it must say "I died" not "She died."

7. Player agency violations: NPC saying "You feel scared" is wrong. NPC can say
   "I sense you're lying" but not "You think I'm lying."

8. Turn numbering: Turn 0 = opening/game state. Turn 1+ = actual exchanges.

9. Timeouts: Ollama calls have 120s timeout. Story master API calls have 60s.

10. Session ID isolation: each run gets a unique session_id (debug_{story_id}_{ts}).

11. Canon correction voice: ALWAYS narrator third-person in parentheses.
    "(IU is the one who died here)" NOT "(I died here)".

12. WebSocket config accepts both new names (player_model, grader_model) and
    legacy names (chatter_model, rater_model) for backward compatibility.

CSS Conventions (debug.html)
-----------------------------
- Dark theme with CSS custom properties (--bg, --surface, --text, --accent, etc.)
- Background: #0c0e14, accent: #6c5ce7 (purple)
- NPC color: orange (#f39c12), Player color: blue (#3498db)
- Mode chip colors: local = green (#2ecc71), online = blue (#74b9ff)

Layer tag colors in context modal:
- base: grey, retrieval: orange, identity: purple, canonical: teal
- relationships: amber, location: blue, beliefs: pink, details: lavender
- truth: red, hint: yellow, transient: cyan
