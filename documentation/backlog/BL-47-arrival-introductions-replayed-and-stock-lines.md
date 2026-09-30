# BL-47 — Residents replay their arrival introduction when greeted, and lean on stock "take it slow" lines

- **Type:** bug
- **Found:** 2026-09-29, hosted beta play (`eed2fd0`, Terrace as Paul, 27 turns)
- **Severity:** low-medium; breaks the sense of a living house and makes long sessions feel scripted.

## Problem
1. **Replayed introductions.** Turn 2 the authored arrival line played once ("Hello, I'm Yuriko. It is good to finally meet the people I'll be living with." / "I'm Hikaru. That sounded more confident in my head."). Turn 9, when Paul greeted both by name, they said the **same two lines again word for word**. The authored arrival beat (`opening_cast` / arrival staging in `world_model/turn.py` `_build_view`, story JSON `arrival` lines) is probably re-offered as a reply to any greeting instead of being marked as spent once played (mechanism unverified; reproduce first).
2. **Stock refusal wording.** After the first confession Minori answered nearly every later turn (breakfast, going back to the living room) with variants of "I want to take my time getting to know everyone, no big plans for now", including turns where nothing romantic was asked (turn 26: "I just want to take my time getting to know everyone, so no big plans for now, okay?" while Paul was making her breakfast). The refusal is being re-injected as a standing directive or appears in retrieved memory for every turn.

## Fix direction
1. Mark an arrival introduction as delivered in world-model state (per character) so a later greeting gets an ordinary reply; test through `begin_turn` with a greeting after the arrival turn.
2. Find what keeps the confession outcome in front of the storyteller (`view.must_address`, `ending_hint`, relationship-decision memories in `romance.py` / `social_acts.py` `commit`), and pass it as context only on the turn of the ask and when the player raises it again, not every turn. Add a test that a plain non-romantic message two turns after a `not_yet` verdict carries no refusal directive.
Measure by replaying the 27-turn script in the beta play notes (see `tasks/todo.md` D-section, 2026-09-29) and counting repeated sentences.

## Touches
`backend/app/engine/world_model/turn.py` (`_build_view`, scene directives), `romance.py`, `social_acts.py`, `bootstrap.py` (opening cast), Terrace story JSON arrival lines, tests under `tests/backend/app/engine/world_model/`.
