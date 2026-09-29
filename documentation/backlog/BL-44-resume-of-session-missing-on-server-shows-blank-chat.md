# BL-44 — Resuming a session the server no longer has leaves a blank "Resuming game…" chat

- **Type:** bug
- **Found:** 2026-09-29, live beta check (Playwright, guest)
- **Severity:** medium; the player is stuck on an empty chat with no way back except the tab bar.

## Problem
`frontend/index.html` `resumeGameFromSession` restores a session from `localStorage.storieschat_sessions` / the session list, then fetches `GET /api/user/sessions/<id>/history?limit=20`. When the server has no such session (guest progress is deleted after 24 hours; or a local session was created by a launch that failed before the first turn) the request returns 404 and the chat stays on "Resuming game as … (Continue where you left off)" with no messages and no error. Repro on beta `f26511b`: create a local session record without a server turn, open the story card ("Resume Game"), observe the 404 in the console and the empty chat.

## Fix direction
On a 404 from the history endpoint, tell the player the saved game is gone, drop that local session record, and offer to start a new game (reuse the character picker). Add a `tests/frontend/` structural test for the 404 branch plus a Playwright check on the empty-session path.

## Touches
`frontend/index.html` (`resumeGameFromSession`, session list rendering), `backend/app/api` user-sessions route only if a clearer "gone" response is wanted.
