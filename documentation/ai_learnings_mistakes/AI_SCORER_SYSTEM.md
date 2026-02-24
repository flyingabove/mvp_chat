Scorer System — AI Learnings & Reference
==========================================

Overview
--------
The scorer is a self-contained FastAPI + embedded HTML/JS app that tests NPC quality
by running automated conversations and grading them with a separate LLM.

File Locations
--------------
- Main app:           scripts/scorer/story_agent_ui.py  (FastAPI + full UI in one file)
- Scoring rubric:     scripts/scorer/scorer_instructions.md
- Score history CSV:  scripts/saves/scores.csv
- Test case library:  scripts/saves/test_cases.json
- Package marker:     scripts/scorer/__init__.py

Related backend files:
- Prompt Engine:      backend/app/api/prompt_engine.py  → POST /api/chat
- Story context API:  backend/app/api/stories.py        → GET /api/stories/{story_id}/context
- Story JSONs:        backend/app/stories/<folder>/<story_id>_story.json
- Transient buffer:   backend/app/engine/transient_buffer.py

Architecture
------------
Browser (HTML/CSS/JS)  ←→  FastAPI backend (story_agent_ui.py)  ←→  Main API + Ollama

Three tabs in the UI:
1. Tester      — run conversations, view chat + evaluation
2. Leaderboard — ranked score history from CSV
3. Test Cases  — design & run scripted test scenarios

Key Constants
-------------
- API_BASE = "https://beta-api.storieschat.ai"
- OLLAMA_BASE = "http://127.0.0.1:11434"
- Scorer port = 8899
- Session ID format: "ui_{story_id}_{timestamp}"
- Run ID: first 8 chars of uuid4

How a Run Works (WebSocket /ws/run)
-----------------------------------
1. Client sends config JSON (story_id, turns, models, personas, etc.)
2. Backend sends __cmd_reset__ → __cmd_newgame__:story_id|gender|name → [D] (enable debug)
3. Loop for N turns:
   a. Generate player message (LLM via Ollama, or test case messages, or fallback list)
   b. POST to /api/chat with player message
   c. Emit "message", "progress", "debug" events over WebSocket
4. After conversation ends:
   a. Fetch /api/stories/{story_id}/context (story canon for scorer)
   b. Run scorer LLM with transcript + scorer_instructions.md + story context
   c. Parse JSON response, append row to scores.csv
   d. Emit "evaluation" event
   e. Emit "done" with the active `session_id` so UI manual mode can continue the same game session

WebSocket Events
----------------
- "status"     — system status text
- "message"    — chat message (role, content, turn, latency_ms, tokens)
- "debug"      — turn-level debug info (debug_box, prompt_debug) — stored in debugPayloads{}
- "progress"   — turn X / total turns
- "warning"    — non-fatal warning
- "error"      — error message
- "evaluation" — final scorer JSON
- "done"       — run complete

After "done", the tester UI enables manual input and reuses that run's session id, so you can
append extra player messages to the same game instead of starting from turn 0.

Player Personas (chatter agent)
-------------------------------
- curious_rookie       — polite, exploratory questions (default)
- confrontational_cop  — direct, pressure-testing, skeptical
- empathetic_confidant — warm, rapport-first, feelings-seeking
- chaos_gremlin        — edge-case breaker, non-sequiturs, stress-tests
- first_time_user      — tentative, basic/clarifying questions
- expert_llm_grader    — experienced evaluator (default for rater)

Scoring Dimensions (7 dimensions, weighted)
--------------------------------------------
| Dimension              | Weight | What it measures                                    |
|------------------------|--------|-----------------------------------------------------|
| Canon Fidelity         | 2.0x   | Never invents facts, contradicts identity, 3rd-person self-ref |
| Character Voice        | 1.5x   | Distinct personality, consistent tone, authentic emotion |
| Player Agency Respect  | 2.0x   | Never narrates player actions/feelings/thoughts     |
| Responsiveness         | 1.0x   | Answers questions, reacts to tone                   |
| Mystery Mechanics      | 1.5x   | Clues when earned, believable withholding           |
| Immersion Quality      | 1.0x   | Atmospheric but not overwhelming, clear speaker labels |
| Edge Case Resilience   | 0.5x   | Handles gibberish, empty input, prompt injection    |

Overall score formula:
  weighted_total = sum(score * weight for each dimension)
  max_possible = 5 * sum(all_weights) = 47.5
  overall = round(weighted_total / max_possible * 5, 1)

Critical Failures (auto-deductions from overall)
-------------------------------------------------
- NPC speaks as player          → -2.0
- NPC reveals SECRET_CANON unprompted → -2.0
- NPC contradicts ANCHOR identity → -1.0
- NPC refers to itself in 3rd person → -1.0
  Example: ghost NPC saying "She died" about herself → should be "I died"

Every category scoring <5 MUST have notes citing specific turns/quotes.

Context Modal (click NPC message)
---------------------------------
When user clicks an NPC message, a full-context modal opens with collapsible sections.
All sections have per-section copy buttons. The header has a "Copy Context JSON" button
that exports a structured snapshot (schema_version, player/npc messages, context object).

Current section order:
 1. Game State         — timestamp, location+uuid, speakers, story, instance, turn, truth_mode,
                         trimmed_history count (open by default)
 2. Transient Buffer   — all short-lived scene entries with TTL remaining; [N entries]
                         (collapsed; tag: transient, teal color)
 3. Player Message     — raw player input for this turn (open)
 4. NPC Response       — NPC reply + latency_ms + token count (open)
 5. RETRIEVED KNOWLEDGE       — FAISS/BM25 chunks (open; tag: retrieval)
 6. CHARACTER SELF-KNOWLEDGE  — identity facts (open; tag: identity)
 7. CANONICAL MEMORIES        — epistemic facts (open; tag: canonical)
 8. RELATIONSHIPS             — character feelings from graph (open; tag: relationships)
 9. LOCATION                  — current scene description (open; tag: location)
10. BELIEFS                   — character beliefs (open; tag: beliefs)
11. CHARACTER DETAILS         — motive & tells (open; tag: details)
12. TRUTH MODE                — debug truth override if active (open; tag: truth)
13. FIRST TURN HINT           — opening hint if present (open; tag: hint)
14. Full System Prompt (raw)  — complete assembled system prompt (collapsed)
15. User Message Header       — the header injected before user message (collapsed)
16. Knowledge Chunks — Canonical Core        — tiered chunk view (collapsed; tag: canonical)
17. Knowledge Chunks — Canonical Graph       — world-context chunks (collapsed; tag: canonical)
18. Knowledge Chunks — Subjective Belief (X) — belief chunks by confidence level (collapsed)
19. Knowledge Chunks — Retrieved Memory      — memory tier chunks (collapsed; tag: retrieval)
20. Retrieval Debug  — raw retrieval scoring data (collapsed)
21. Raw Debug Box    — fallback if no structured game state (open only when gameLines empty)

Debug data is stored in JS variable debugPayloads[turn] — populated via "debug" WebSocket events.
The side debug panel was REMOVED (only the modal remains).

Debugging Workflow
------------------
IMPORTANT: The main API is NOT in debug mode by default.
Debug mode is a per-session flag that must be explicitly enabled.

How debug mode works:
- Enabled by sending the message "[D]" to the chat API after starting a game session.
- When debug mode is ON, every API response includes `debug_box` and `prompt_debug` fields.
- When debug mode is OFF (normal production use), those fields are absent — no overhead.

The scorer auto-enables debug mode during automated runs:
  Backend sends "[D]" immediately after __cmd_newgame__ — before turn 1 begins.
  This ensures debugPayloads[turn] is populated for every turn.

What `debug_box` contains (only present when debug mode is ON):
  - timestamp       — current in-game time string
  - location        — human-readable location name
  - location_uuid   — internal location identifier
  - speakers        — list of character names present in scene
  - transient_count — number of active transient entries
  - transient_entries — full list: [{text, turns_remaining}, ...]
    Each entry is a short-lived scene fact with a TTL that decays each turn.
    Examples: "Player said: ...", "NPC replied: ...", "KnowledgeResolution chunk=...",
              "__active_character_marker__:key", "__character_location_marker__:key:loc_id",
              "story.X: ..."

What `prompt_debug` contains (only present when debug mode is ON):
  - story, instance, turn, truth_mode, trimmed_history
  - prompt_layers: dict of named system prompt sections (retrieved_knowledge,
    character_self_knowledge, canonical_memories, relationship_context,
    location_description, belief_context, character_details, truth_override,
    first_turn_hint)
  - system_prompt_preview: full assembled system prompt
  - header: user message header string
  - chunks: list of knowledge chunks with tier/certainty/known_by fields
  - retrieval_debug: raw retrieval scoring data

To inspect a specific turn:
  1. Run a scorer test (or manual mode after a run)
  2. Click any NPC message bubble in the chat
  3. The context modal opens — all prompt layers visible, transient buffer included

To manually test without the scorer:
  1. Use the main chat UI, open browser devtools
  2. After newgame, POST {"message": "[D]"} to /api/chat to enable debug
  3. Subsequent responses include debug_box and prompt_debug
  CAUTION: Do not leave debug mode ON in production — it adds overhead and
  leaks internal state structure to API responses.

Leaderboard
-----------
- Reads scripts/saves/scores.csv
- Shows all runs ranked by overall_score descending
- Color-coded: Red (1-2), Yellow (3), Green (4-5)
- Deduction notes aggregated (only dimensions scoring <5)
- 26 columns including model names, personas, latency, tokens

Test Cases
----------
Structure: { id, name, description, story_id, strategy, messages[] }
6 built-in test cases (greeting, pressure, edge-case, location, empathy, confusing).
User can create/edit/delete/run test cases. Saved to scripts/saves/test_cases.json.
When a test case runs, its messages replace LLM-generated player messages.
Strategy field is injected into chatter agent's system prompt.

Story Context for Scoring
-------------------------
The scorer fetches GET /api/stories/{story_id}/context which returns:
- character_self_knowledge (identity facts NPC must embody)
- canonical_facts (ground truth with known_by attribution)
- characters (key, name, role, is_main, is_suspect, tags)
- protagonist (player character details)
- rules

This is formatted into a STORY CONTEXT block prepended to the scorer prompt so the
rater LLM can verify canon fidelity.

Authoring Checklist
-------------------
The knowledge authoring invariants live at: backend/app/engine/authoring_checklist.py
(Previously: backend/app/knowledge/authoring_checklist.py — moved to engine in Feb 2026)
These rules are enforced by humans at authoring time. The AI engine is never told
what is rumor vs fact vs narrative — consistency must be guaranteed before indexing.
Rules: NO_CONTRADICTIONS, AVOID_EXCLUSIVE_CLAIMS, NARRATIVES_MUST_BE_CONSERVATIVE,
       AMBIGUITY_OVER_FALSE_SPECIFICITY, TRUTH_REPLACES_SPECULATION, MODEL_NEVER_DECIDES_TRUTH

Gotchas & Common Mistakes
--------------------------
1. The scorer UI is ONE file (story_agent_ui.py) — HTML, CSS, JS all embedded.
   Do NOT split it into multiple files without understanding the full structure.

2. Debug data collection (debugPayloads) must stay even though the side panel was removed.
   The context modal depends on it. If you remove debugPayloads or handleDebug(), the
   click-to-inspect feature breaks.

3. The scorer auto-enables debug mode by sending "[D]" after newgame. If this is removed,
   no debug data flows and context modals will be empty.

4. Ollama must be running locally for LLM-based chatter/rater. If offline, the UI
   gracefully degrades — can still run with fallback messages but no evaluation.

5. CSV appends — never overwrite scores.csv. Each run adds one row.

6. Third-person self-reference is a CRITICAL FAILURE. If the NPC IS the dead person
   (ghost), it must say "I died" not "She died." This is the most common canon violation.

7. Player agency violations: NPC saying "You feel scared" or "You lean forward" is wrong.
   NPC can say "I sense you're lying" (NPC's perception) but not "You think I'm lying"
   (narrating player thought).

8. Turn numbering: Turn 0 = opening/game state. Turn 1+ = actual exchanges.
   Game ends if NPC says "Game already finished" or "END GAME".

9. Timeouts: Ollama calls have 120s timeout. API calls have 60s. If timeout occurs,
   fallback message is used and a warning is emitted. Run continues.

10. Session ID isolation: each run gets a unique session_id. Don't reuse across runs
    or game state will leak between tests.

11. Transient buffer entries: these are short-lived and decay each turn. If you see
    entries like "__active_character_marker__:key" or "__character_location_marker__:key:loc_id"
    those are internal engine markers, not LLM-visible content. Entries prefixed with
    "Player said:" or "NPC replied:" ARE injected into the LLM context as scene memory.

12. Speakers in debug box show who is present at the current location. If a world JSON
    has no `location_speakers` mapping, the fallback lists ALL non-victim characters —
    this may show more speakers than expected. Fix: add `location_speakers` to the
    world JSON's location definitions.

CSS Conventions
---------------
- Dark theme with CSS custom properties (--bg, --surface, --text, --accent, etc.)
- Background: #0c0e14, accent: #6c5ce7 (purple)
- NPC color: orange (#fab1a0), Player color: blue (#74b9ff)
- All in :root block at top of embedded <style>

Layer tag colors in context modal:
- base:          grey   (#b2bec3)
- retrieval:     orange (#fab1a0)
- identity:      purple (#a29bfe)
- canonical:     teal   (#55efc4)
- relationships: amber  (#e17d56)
- location:      blue   (#74b9ff)
- beliefs:       pink   (#fd79a8)
- details:       lavender (#dfe6e9)
- truth:         red    (#f06595)
- hint:          yellow (#fdcb6e)
- transient:     cyan   (#81ecec)

Chat Text Formatting (important parity behavior)
------------------------------------------------
- Scorer chat bubbles now use the same rich-text rendering style as the main game chat:
   - `**bold**` -> `<strong>`
   - `*italic*` -> `<em>`
   - quoted dialogue wrapped/styled as dialogue text
   - preserves paragraph breaks and single-line breaks (`<p>` + `<br>`)
- Implementation lives in `scripts/scorer/story_agent_ui.py` JS helpers:
   - `normalizeNewlines()`
   - `formatInline()`
   - `toRichHTML()`
- `addChatMsg()` must render message content via `toRichHTML(...)`, not plain `escapeHtml(...)`,
  otherwise formatting/newlines will be lost.
