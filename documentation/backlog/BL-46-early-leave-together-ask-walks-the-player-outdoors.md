# BL-46 — Asking to "leave this house together" physically moves the player outside even when the answer is no

- **Type:** bug
- **Found:** 2026-09-29, hosted beta play (`eed2fd0`, Terrace as Paul, turn 12 of 27)
- **Severity:** medium; a refused ask leaves the scene on the street for several turns (narration: "glancing down the street", "the streets of Higashi-Gotanda", then "as you walk back to the house … settle into bed"), which breaks continuity and where later invitations are heard.

## Problem
Turn 12: "Minori, let's leave this house together, right now, just you and me. Will you come?" Minori declined in dialogue ("I want to settle in a little first"), the Goal banner stayed "No mutual relationship yet", but the storyteller narrated the scene outdoors from that turn on (turns 13-15). The ask reads as a movement to the movement extractor / heuristic (`prompt_engine.py` `_match_world_destination`, `_resolved_movement_destination`, the `MOVE` intent in the turn extractor), and `world_model/companions.py` `INVITE` also matches "let's leave", so Minori travelled with the player. A social ask must not move anyone; only an accepted departure (`record_departure_decisions`, `ask_leave_together` verdict `accept`) ends the run. The response body carries no location field, so the location was inferred from narration; verify with the session state before fixing.

## Fix direction
Reproduce with a test through `/api/chat` (scripted extraction, `SocialActUpdate("ask_leave_together", target)`) and assert the player's `location_id` and the target's place are unchanged after a `not_yet`/`reject` verdict. Make a turn that carries a typed social act (`ask_leave_together`, `confess`) skip destination extraction for that message, and drop `leave` from the companion `INVITE` verbs (a companion needs an explicit "come with me to <place>", never a departure ask). Expose `location` in the chat response so browser checks can assert it.

## Touches
`backend/app/api/prompt_engine.py` (movement resolution around `extraction.movement_intent`), `backend/app/engine/world_model/companions.py`, `tests/backend/app/api/test_terrace_campaigns.py`-style scripted test, chat response schema.
