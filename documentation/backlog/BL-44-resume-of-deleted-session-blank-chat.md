# Resuming a deleted session leaves a blank chat

## BL-44 — Resuming a session the server no longer has leaves a blank chat
- **Open:** `frontend/index.html` `resumeGameFromSession` fetches `GET /api/user/sessions/<id>/history?limit=20`. The server answers 404 (`user_sessions.py` "Session not found") when guest progress is deleted after 24 hours, the game was deleted elsewhere, or a local record came from a failed launch. The handler reads the JSON error as data, finds no `entries`, prints "(Continue where you left off)" and lets the player type into a session that cannot continue (the next chat turn silently starts nothing useful).

### Engineering plan
1. **Failing-first test** (`tests/frontend/test_session_gone_ui.py`, structural like the other frontend tests): `resumeGameFromSession` has a branch for `r.status === 404`, calls the new `handleSessionGone`, and does not render "Continue where you left off" on that path.
2. **`handleSessionGone(sess, story)`** in `index.html`:
   - removes the local record (`storieschat_sessions` filtered by `session_id`) and the `storieschat_briefing_seen` entry;
   - clears the chat area and shows one system message: "This saved game is gone (guest games are deleted after 24 hours). Start a new game?" plus a **Start new game** button that calls `startGame(story)` and a **Back to home** button;
   - disables the input via `setChatEnded(true)` with the placeholder "This saved game is gone.";
   - calls `refreshSessionCacheFromServer()` so "My Games" no longer lists it.
3. **Distinguish errors:** 401 keeps `handleUnauthorized`; 5xx/network keep "(History unavailable — continue where you left off)" and do NOT delete the local record (a server hiccup must not destroy a game).
4. **Backend check:** `tests/backend/app/api/test_user_sessions_history_404.py` proves the endpoint returns 404 for an unknown or other user's session and 200 for own session (the contract the frontend relies on).
5. **Playwright** (desktop Chromium and iPhone WebKit): seed a local session record with an unknown id, click it in My Games, see the message and buttons, press Start new game and reach the character screen for that story; confirm the record is gone after reload. *Found in the browser check:* a pre-briefing ("legacy") session popped the briefing and the inline map over the gone message, so the legacy briefing now runs only after the history check succeeds (`showLegacyBriefingOnce`) and the map is skipped once the session is gone.

### Checklist
- [x] Failing-first structural test
- [x] `handleSessionGone` implemented; 404 branch wired
- [x] Local record + briefing-seen entry removed; My Games refreshed
- [x] 401/5xx/network paths unchanged and do not delete anything (test)
- [x] Backend 404/200 contract test
- [x] Browser check on desktop Chromium and iPhone WebKit
- [x] Section deleted when fixed (`Closes BL-44`)
- **Touches:** `frontend/index.html`, `tests/frontend/`, `tests/backend/app/api/`.
