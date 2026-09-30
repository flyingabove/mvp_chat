# Resuming a deleted session leaves a blank chat

## BL-44 — Resuming a session the server no longer has leaves a blank chat
- **Open:** `frontend/index.html` `resumeGameFromSession` fetches `GET /api/user/sessions/<id>/history?limit=20`; a 404 (guest progress is deleted after 24 hours, or a local record from a failed launch) leaves "Resuming game as ..." with no messages and no error.
- **Next:** on 404 tell the player the saved game is gone, drop the local record, offer a new game; add a `tests/frontend/` check for the 404 branch and a Playwright check.
