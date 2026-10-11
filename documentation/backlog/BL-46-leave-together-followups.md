# Terrace: leave-together asks (remaining work after the BL-46 fix)

The BL-46 design shipped 2026-09-30 (as built: `design/SOCIAL_ENGINE.md`, "Leave-together asks, choice cards and plans").
Only the unmeasured or unbuilt parts remain.

## BL-46 — Leave-together follow-ups: Jev accuracy, arena handling, plan meeting place
- **Bucket:** C (engine)
- **Open:** (1) `world_model/leave_meaning.py` (Jev `couple`/`outing`/`unclear`) has no accuracy measurement. It only runs when `NPC_DECISION_MODE` is `jev` or `compare`; in `rules` mode (the default) a couple reads `couple` and anyone else `unclear`, so a walk invitation from a couple is still treated as the win ask. Owner rule (`user_corrections.md`, asymmetric state errors): a mechanic that can wrongly end the game needs a measured bar (at least 99%) or must be dropped. (2) The arena and debug player agent are only told `[play ending]` through the briefing controls; nothing yet defaults them to answer a `pending_choice` card, so an arena run that earns a yes can stall before the win. (3) A skip-to-plan card brings the resident to the player wherever they are; the plan's meeting place is untracked (BL-35). (4) The card appears one turn after the agreement, because commitments are extracted from the previous exchange.
- **Next:** (1) write 60+ `leave_meaning` cases ("leave with me" as a walk, as a date, as moving out together, with and without a relationship) to a fresh file, measure like `scripts/eval/promise_judge_eval.py`, gate on false `couple` readings, then decide whether `jev` mode may be the default. (2) In the arena player loop, answer an open `pending_choice` with `leave_now` (a single `__choice__:<id>:leave_now` message) so runs can finish, and add a test. (3) Depends on BL-35. (4) Accept or move plan extraction into the current turn.
- **Touches:** `world_model/leave_meaning.py`, `tests/eval_cases/`, `scripts/eval/`, the arena player loop (`api/debug_engine.py`), `design/SOCIAL_ENGINE.md`.
