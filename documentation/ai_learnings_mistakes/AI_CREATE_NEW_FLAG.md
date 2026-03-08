PART 2 — HOW TO ADD NEW COMMAND FLAGS / MODES
----------------------------------------------

> **What this doc is for:** How to add new command flags/modes to the chat system. Edit this doc when adding a new bracket command or game mode flag.

Commands like [D], [M], [C] are "bracket commands" — shortcuts the player
types that toggle modes or trigger actions without calling the LLM.

To add a new one you must change both frontend and backend:

### Example: adding a [H] / [HINT] command that gives the player a hint

#### STEP 1 — Backend (backend/app/api/prompt_engine.py)

The Prompt Engine (prompt_engine.py) is the single file that receives the raw
request, orchestrates all context, builds the final LLM prompt, and dispatches
the API call. All bracket commands are processed here before any LLM call.

A) Define token set and detection function (near line ~78, next to existing ones):

    HINT_TOGGLE_TOKENS = {
        "[HINT]",
        "(HINT)",
        "[H]",
        "(H)",
    }

    def _is_hint_toggle(msg: str) -> bool:
        return (msg or "").strip().upper() in HINT_TOGGLE_TOKENS

B) Add handler in chat_handler(), BEFORE any LLM calls (near line ~400,
   after the map toggle block):

    # HINT COMMAND
    if _is_hint_toggle(msg):
        hint_text = "Try asking about alibis or timelines."
        return {
            "reply": _box("HINT", [hint_text]),
            "usage": {"total_tokens": 0},
            "character": "default",
        }

   For a toggle (on/off) instead of a one-shot, follow the debug_mode
   pattern: store a boolean in sess, flip it, return a notice.

#### STEP 2 — Frontend (frontend/index.html)

A) Add patterns to COMMAND_PATTERNS (near line ~469):

    var COMMAND_PATTERNS = [
      /^\[d\]$/i, /^\(d\)$/i, /^\[debug\]$/i, /^\(debug\)$/i,
      /^\[m\]$/i, /^\(m\)$/i, /^\[map\]$/i, /^\(map\)$/i,
      /^\[c\]$/i, /^\(c\)$/i, /^\[chinese\]$/i, /^\(chinese\)$/i,
      /^\[h\]$/i, /^\(h\)$/i, /^\[hint\]$/i, /^\(hint\)$/i    // <-- new
    ];

   This ensures isCommand() returns true, which matters because:
   - During name/gender entry, commands are intercepted and sent to the
     backend instead of being treated as the player's name.
   - Without this, typing [H] during name entry would set the player name
     to "[H]".

B) Update the instructions box in renderInstructions() (near line ~400):

    "- Type `[H]`, `(H)`, `[HINT]`, or `(HINT)` to get a hint\n"

C) Bump the version in frontend/version.json.

#### STEP 3 — Test

1. Run unit tests to make sure nothing breaks.
2. Deploy to beta branch and test on beta-api.storieschat.ai.
3. Type the new command during gameplay AND during name/gender entry to
   confirm it works in all states.

### Architecture notes

- Commands return immediately (no LLM call) → zero token cost.
- Detection is case-insensitive on both sides (frontend regex /i flag,
  backend .upper() before set lookup).
- Both [bracket] and (parenthesis) forms are supported for mobile
  convenience (some keyboards default to parentheses).
- The frontend COMMAND_PATTERNS list and backend token sets must stay in
  sync. If you add a command to only one side, it will either not be
  intercepted during setup (frontend miss) or not be recognized by the
  server (backend miss).
- For commands that need game state (like [M] which reads world_graph),
  access it via sess["state"] in the handler.
- For toggle modes that affect LLM output (like [C] Chinese mode),
  the toggle boolean is stored on the session dict and checked later
  in the response-building section of chat_handler().


PART 3 — INCIDENT REFERENCE (Feb 2025)
---------------------------------------

A refactoring of renderStepOutput left ~80 lines of orphaned code outside
any function scope in the IIFE. The orphaned code referenced undefined
variables, causing a ReferenceError that killed the entire script on load
and produced a blank page.

Lesson: after any refactor that moves code between functions, read the
lines AFTER the closing brace to make sure nothing leaked out.

The file now has an early fatal-error guard (<script> tag before the main
IIFE) that renders a visible error instead of a blank page if the main
script crashes during initialization.
