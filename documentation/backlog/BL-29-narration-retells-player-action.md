# BL-29 — Narration retells the player's action and invents the player's feelings/history

- **Type:** bug
- **Found:** 2026-09-24, local Ollama arena `welcome_party_local_gate2` (Terrace, 6 paired games, 60 player turns per side)
- **Severity:** medium. It happens on ~20% of turns and makes the storyteller feel like it parrots the player. It isn't a correctness/safety issue.

## Problem
The storyteller often opens its reply by restating the player's typed action nearly verbatim, just switched from first to
second person, e.g. player "I walk over to the wall-mounted phone in the kitchen and start dialing." -> narration
"You walk over to the wall-mounted phone in the kitchen and start dialing, the sound of the dial tone filling the room."
It was 12 of 60 turns on both fbf2667 (feature) and ff4d924 (old beta). It's pre-existing, not a regression. Legacy BL-22 measured the same
"restating of the player" at 12-14% on hosted runs.
`backend/app/engine/dialogue.py` `drop_player_echo` only strips echoes attributed to **other speakers' dialogue**;
narration segments are untouched, so this passes through.
Scanner used: a longest-common-word-run check (>= 6 words, or >= 4 words covering 60% of the player message) between
each narration line and the player message.

Related, same narration rule: hosted gate `promote_37bbcb2` (2026-09-25) failed on one critical Jev flag,
"Player action fabricated" (beta 1 vs prod 0), in `iu.opening_m.direct_investigator` beta turns 1-4, readings 0.61/0.61.
The narration invented player history and feelings: "It's her, the presence that has haunted your dreams" (t1)
and "the sorrow in her eyes mirrored by your own feelings of helplessness" (t4). The orphaned speech-tag fragment in
the same window (t3 "you murmur, your voice steadying with resolve.") is a separate `drop_player_echo` bug, fixed by
another session. It isn't part of this item.

The turn-1 opening re-narration seen on 79ef6f7 is addressed in `09633b6`. `dialogue._is_repeat` now treats narration
with >= 0.6 word-trigram overlap with a recent reply as a repeat, so a draft that only re-tells the opening triggers
the single regeneration. It is no longer part of this item. What remains is prompt-side: restating the player's
action and inventing their feelings or history.

Additional hosted evidence from the [2026-09-25 manual review](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md): Terrace turns 7 and 10 invent feeling "more at ease"; turn 3 adds "a sense of purpose". IU turn 9 assigns "anticipation and caution"; turns 10 and 12 add unchosen nods and other social actions. These are independent live samples (10 Terrace / 12 IU turns), not a new prevalence estimate.

## Fix direction

1. Prompt: in the storyteller's narration rules (also: never assign the player feelings, memories or history they did not state) (`backend/app/engine/prompt_builder.py`, near
   "Narrate only what the player's message actually states or implies"), say not to restate the player's action.
   Narrate its consequence or the world's reaction instead.
2. Deterministic backstop in `dialogue.py`: a first-person->second-person normalized comparison
   ("I/my/me" <-> "you/your") that trims a leading narration sentence covering >= ECHO_COVERAGE of the player
   message. The rest of the segment stays.
3. Regression tests: the two verbatim examples above as unit cases for the trimmer, and an end-to-end
   `test_prompt_engine.py` case with a fake storyteller reply.

## Why deferred / cautions
Found during the 37bbcb2 promotion window. A prompt change alters every story's replies and needs its own arena
gate (hosted, Jev + OpenAI). Watch BL-23 (the Jev length preference): trimming makes replies shorter, which that
judge penalizes. Read the gate's length check before calling it a regression. Don't trim narration that adds new
information after the restated clause.

## Touches
`backend/app/engine/prompt_builder.py`, `backend/app/engine/dialogue.py`, `backend/app/api/prompt_engine.py`
(apply the trimmer next to `drop_player_echo`), `tests/backend/app/engine/test_dialogue*.py`,
`tests/backend/app/api/test_prompt_engine.py`.
