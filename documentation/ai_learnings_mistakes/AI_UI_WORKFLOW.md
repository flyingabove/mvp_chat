UI WORKFLOW & FRONTEND ARCHITECTURE
====================================

> **What this doc is for:** Frontend development workflow and architecture patterns. Edit this doc when frontend architecture, build process, or UI patterns change.

Current as of 2026-09-24: `frontend/index.html` remains the SPA shell, with
`frontend/dialogue.js`, `dialogue.css`, `world-map.js` and `world-map.css` for
major components. FastAPI serves content-addressed JS/CSS URLs. Shell and
worker revisions are derived from file contents in `backend/app/main.py`;
there is no manual `version.json` bump. See
`documentation/model_output_docs/UI_REDESIGN_2026.md` for current behavior.

For UI development, follow `.claude/skills/ship-and-verify/SKILL.md` and its
`BROWSER_QA.md`. Run `scripts/verify_ui_browser.py` in real desktop Chromium,
iPhone 13 WebKit and simulated standalone WebKit, then click through the changed
feature with a task-specific Playwright flow. Run locally before committing
and against hosted beta after its health endpoint reports the pushed commit.
Inspect screenshots, console errors, API request hosts and mobile top/bottom
safe areas. `scripts/verify_mobile_pwa_browser.py` is an executable example.

The sections below are a March 2026 architecture snapshot. Some selectors,
screens and legacy commands have since changed; inspect current source before
using those details as implementation guidance.

════════════════════════════════════════════════════════════════
MARCH 2026 UI ARCHITECTURE SNAPSHOT (HISTORICAL)
════════════════════════════════════════════════════════════════

SCREENS (SPA routing via showScreen(name)):
  home    → Netflix-style game discovery with hero banner + card rows
  games   → My Games list (Character.AI Chats style, from localStorage)
  chat    → In-game chat (Character.AI exact clone — no tab bar)
  create  → Create Game form (POST /api/stories/draft)
  profile → Stats + settings (localStorage data)

GAME STARTUP FLOW (new):
  1. Boot: showScreen("home") → loadStories() → GET /api/stories
  2. User clicks game card → showGameDetail(story) → modal opens
  3. User clicks Play → startGame(story) → modal-onboard opens
  4. User enters name (step 1) → gender (step 2) → launchChat()
  5. launchChat() → showScreen("chat") → sendMessage("__cmd_newgame__:...")
  6. Chat screen stays until back button or Exit Game menu item

STATE MACHINE (new):
  "home"  ─(card click)──→ game_detail_modal
  game_detail_modal ─(Play)──→ modal-onboard (name)
  modal-onboard(name) ─(Continue)──→ modal-onboard (gender)
  modal-onboard(gender) ─(Start Game)──→ "chat"
  "chat" ─(back/Exit)──→ "home"

KEY FUNCTIONS (new):
  showScreen(name)         — SPA router, manages tab bar visibility
  showGameDetail(story)    — Opens detail modal sheet
  startGame(story)         — Opens onboarding modal
  launchChat(story,n,g)    — Initializes chat screen, sends __cmd_newgame__
  sendMessage(text,isInit) — POSTs to /api/chat, renders bubble, updates session
  addMessage(role,text)    — Appends chat bubble (role: "user"|"npc"|"system")
  showMapModal()           — Opens world map modal using appState.currentMeta
  renderGamesList()        — Reads localStorage sessions, renders My Games
  refreshProfileScreen()   — Reads localStorage stats

STORAGE (localStorage):
  storieschat_sessions  — Array of { story_id, session_id, last_played, ... }
  storieschat_profile   — { name, handle }
  storieschat_stats     — { games, wins, turns }

API CALLS (new UI):
  GET  /api/stories            — Home screen story rows
  GET  /api/story/{id}         — Story metadata (map, locations) — after game start
  POST /api/chat               — Chat messages (same as before)
  POST /api/stories/draft      — Create game draft
  GET  version.json            — App version (profile screen)
  GET  /manifest.json          — PWA manifest
  GET  /sw.js                  — Service worker

NEW STORY JSON FIELDS (required for UI):
  description    — Short game teaser shown on cards and modal
  genre          — Category tag (e.g., "Murder Mystery") used for row grouping
  thumbnail_url  — Optional image path; null = emoji fallback
  featured       — Boolean; featured games go in "Featured" row and hero banner

PWA:
  frontend/manifest.json   — App manifest (dark theme, standalone display)
  frontend/sw.js           — Cache-first shell, network-first /api/*
  main.py routes:          GET /manifest.json, /beta/manifest.json, /sw.js, /beta/sw.js

────────────────────────────────────────────────────────────────
LEGACY TERMINAL ARCHITECTURE (Historical Reference Only)
────────────────────────────────────────────────────────────────

This section describes the original terminal UI that was replaced.
The API contracts (/api/chat, __cmd_newgame__, bracket commands) are unchanged.

This document describes the complete frontend UI workflow, state machine,
rendering pipeline, and conventions. The frontend is a SINGLE FILE
(frontend/index.html) — an IIFE with no build step.

────────────────────────────────────────
GAME STARTUP FLOW (exact order on screen)
────────────────────────────────────────

1. Boot: loadVersion() + showMenu() + ime.focus() + __appBooted = true
2. Story list renders (fetched from GET /api/stories)
3. User picks a number → handleMenu()

After story selection, the screen shows IN THIS ORDER:

  a) "Welcome to **<Game Title>**"           (writeLine, class "sys")
  b) Murder Mystery — Rules & Objective box  (renderInstructions → writeBox)
  c) "Enter your name:"                      (writeLine, class "sys")
  d) User types name → handleName()
  e) "Are you a girl (F) or boy (M)?"        (writeLine, class "sys")
  f) User types F or M → handleGender()
  g) World Map IMAGE (PNG)                   (renderWorldMap → img element)
  h) World Map TEXT (location list)          (renderWorldMap → writeBox)
  i) First LLM dialogue (opener)            (send __cmd_newgame__, typewrite)
  j) Chat mode unlocks (state.mode = "chat")

IMPORTANT: The world map (g+h) renders BEFORE the opener dialogue (i).
The opener typewriters at TYPE_OPENER speed (faster than normal chat).
After the opener finishes, input unlocks.

────────────────────────────────────────
STATE MACHINE (mode transitions)
────────────────────────────────────────

  "menu" ──(pick story)──→ "name"
  "name" ──(enter name)──→ "gender"
  "gender" ──(pick F/M)──→ "chat"
  "chat" ──(EXIT cmd)────→ "menu"

  "menu" ──(pick 0)──→ "integration_menu"
  "integration_menu" → "integration_debug_prompt" → "integration_running" → "menu"

Global commands ([M], [E]) are intercepted in commitLine() BEFORE
mode-specific routing. This means they work in ALL modes.

Mode-specific handlers (handleName, handleGender) also check isCommand()
to forward bracket commands ([D], [C], [T]) to the backend, then
re-prompt the current question.

────────────────────────────────────────
KEY FUNCTIONS (with approximate line ranges)
────────────────────────────────────────

commitLine()
  Entry point for ALL user input.
  1. Prevents double-submit (awaitingResponse guard)
  2. Reads ime.value, clears it, removes input line
  3. Writes "> <text>" as user message
  4. Checks EXIT command → exitToMenu()
  5. Checks MAP command → renderWorldMap() + repromptCurrentMode()
  6. Routes to mode handler (handleMenu / handleName / handleGender)
  7. Default (chat mode): send() to backend

send(msg, done, typeOpt)
  POSTs { message, session_id } to CHAT_ENDPOINT.
  On success: typewrite() the reply, then renderDebugBox(), then done().
  On error: writeLine() error message, then done().

typewrite(text, cls, opt)
  Character-by-character animation. Returns Promise.
  - TYPE_DEFAULT = { charsPerTick: 3, tickMs: 15 }  (normal chat)
  - TYPE_OPENER  = { charsPerTick: 3, tickMs: 10 }  (~50% faster opener)
  Uses toRichHTML() for markdown (bold/italic/dialogue).

renderWorldMap(meta)
  Renders both the PNG map image and the location list.
  1. If meta.world_map_image exists → creates <img> with src =
     API_BASE + "/story-image/" + meta.world_map_image
  2. If meta.known_locations exists → writeBox("World Map", names)
  Uses state.storyMeta which is cached from fetchStoryMeta() during
  story selection — no backend call needed.

renderInstructions(meta)
  Renders the "Murder Mystery — Rules & Objective" box using writeBox().
  Shows: objective, how to play, rules/gameplay, available commands.

writeBox(title, body)
  Renders a styled div with .box class (dark background, border-radius).
  Title in bold, body processed through toRichHTML().

writeLine(text, cls)
  Renders a single line. cls = "sys" (green), "user" (blue),
  "bot" (yellow), "err" (red).

newPrompt()
  Creates the "> " input line with cursor. HTML structure:
    <div id="inputline">
      <span class="sys">> </span>
      <span id="buffer">text before cursor</span>
      <span id="cursor">&nbsp;</span>
      <span id="afterCursor">text after cursor</span>
    </div>

renderBuffer()
  Reads ime.selectionStart to position the blinking cursor correctly.
  Called on input/keydown/keyup/click/select events.

unlockInput()
  Sets awaitingResponse = false, calls newPrompt(), focuses IME.

repromptCurrentMode()
  After a local command during name/gender entry, re-displays the
  question ("Enter your name:" or "Are you a girl (F) or boy (M)?")
  and creates a new prompt.

────────────────────────────────────────
COMMANDS (bracket commands)
────────────────────────────────────────

All commands work in [bracket] and (parenthesis) forms, case-insensitive.

  [D] / [DEBUG]   — Toggle debug mode (backend handled, shows game state)
  [M] / [MAP]     — Show world map (LOCALLY handled, no backend call)
  [C] / [CHINESE] — Toggle Chinese translation (backend handled)
  [T] / [TRUTH]   — Toggle truth mode (backend handled)
  [E] / [EXIT]    — Exit to story menu (locally handled)

MAP and EXIT are intercepted in commitLine() before mode routing.
Other commands are caught by isCommand() in handleName/handleGender
and forwarded to the backend via send().

COMMAND_PATTERNS array must stay in sync with backend token detection.
See documentation/ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md.

────────────────────────────────────────
RENDERING PIPELINE (markdown)
────────────────────────────────────────

All text goes through: normalizeNewlines → escapeHTML → toRichHTML

toRichHTML splits on double newlines into <p> tags, then runs formatInline:
  **bold**    → <strong>
  *italic*    → <em>
  "dialogue"  → <span class="dialogue"> (italicized)

────────────────────────────────────────
CSS COLOR CLASSES
────────────────────────────────────────

  .sys      → #77dd77 (green)   — system messages, prompts
  .user     → #8ab4f8 (blue)    — player input echo
  .bot      → #ffd466 (yellow)  — LLM character replies
  .err      → #ff6b6b (red)     — errors
  .dialogue → italic inline     — quoted speech in LLM output

────────────────────────────────────────
IMAGE SERVING
────────────────────────────────────────

Map images are served by the backend endpoint:
  GET /api/story-image/{path}

The frontend constructs the URL as:
  API_BASE + "/story-image/" + meta.world_map_image

The backend's _discover_map_image() finds images by:
  1. Explicit: story JSON → world.world_map_image field
  2. Convention: {folder}/{folder}.png (e.g., 2_jennie_murder_mini/2_jennie_murder_mini.png)
  3. Alternates: {story_id}.png or {story_id}_wm.png inside the folder

CSS for map image:
  .map-img { width:340px; max-width:90%; border-radius:8px; display:block; margin:12px auto; }

────────────────────────────────────────
ERROR HANDLING
────────────────────────────────────────

Two layers:

1. FATAL INIT GUARD (runs BEFORE main IIFE):
   A <script> tag sets window.__appBooted = false and listens for
   window "error" events. If the main script crashes during init,
   it renders a visible error in #errbox instead of a blank page.

2. RUNTIME ERROR HANDLERS:
   window.onerror and window.onunhandledrejection display errors
   in #errbox (fixed-position, dark-red box above toolbar).

Both exist because a previous incident left ~80 lines of orphaned code
outside any function scope, which killed the entire script and produced
a blank page with no error visible. See AI_FATAL_MISTAKES.md.

────────────────────────────────────────
API ENDPOINTS
────────────────────────────────────────

  API_BASE = isBeta
    ? "https://beta-api.storieschat.ai/api"
    : "https://api.storieschat.ai/api"

  POST /api/chat              — Send message, get LLM reply
  GET  /api/stories           — List available stories
  GET  /api/story/{story_id}  — Story metadata (rules, locations, map)
  GET  /api/story-image/{path} — Serve PNG map image

────────────────────────────────────────
STATE OBJECT FIELDS
────────────────────────────────────────

  state.mode              — Current mode string
  state.sid               — Session UUID (sent to backend)
  state.turns             — Turn counter
  state.story             — Selected story ID (e.g., "jennie_murder_mini")
  state.gender            — "F" or "M"
  state.playerName        — Player's chosen name
  state.storyMeta         — Cached response from /api/story/{id}
  state.storyOptions      — Array from /api/stories
  state.integrationOptions — Integration test scenarios
  state.pendingIntegration — Selected integration scenario
  state.integrationDebug  — Debug mode flag for integration runs

────────────────────────────────────────
CRITICAL GOTCHAS FOR AI EDITORS
────────────────────────────────────────

1. NEVER leave code outside the IIFE scope. This causes a fatal blank page.
   After any refactor, check lines after the closing brace of the IIFE.

2. The frontend is a SINGLE FILE. There is no build step, no modules,
   no imports. All code lives in one IIFE inside index.html.

3. Commands must be registered in BOTH frontend (COMMAND_PATTERNS) and
   backend (token sets). Missing one side causes silent failures.

4. state.storyMeta is set asynchronously in handleMenu(). It may be null
   if fetchStoryMeta fails. Always null-check before using.

5. The MAP command is handled LOCALLY (no backend call). All other
   bracket commands go to the backend. This is intentional because MAP
   data is already cached in state.storyMeta.

6. awaitingResponse is the ONLY mutex for input. If a code path fails
   to set it back to false, the UI permanently locks up.

7. Historical note only: version.json no longer needs a manual bump.
   `backend/app/main.py` fingerprints the shell and serves hashed assets.

8. The typewrite() Promise chain is critical. The done() callback
   MUST be called after typewriter finishes, or input never unlocks.

9. Story JSON files may use {story_id}_story.json naming (not just
   {story_id}.json). The story_loader handles both conventions.

10. World paths in story JSON (world.file, world.world_map_image) must
    use the ACTUAL folder name (e.g., "2_jennie_murder_mini/..."), not
    short aliases.
