# BL-30 — Live narration accepts dates and waits that disagree with the game clock

- **Type:** bug
- **Found:** 2026-09-25, manual hosted beta playthrough
- **Severity:** high; commitments and mystery chronology cannot be trusted across the prose/state boundary.

## Problem
See [full review](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md). Terrace on `09633b6`, turn 9: request tomorrow 18:55, response accepts next evening 18:55, `debug_box.timestamp` remains January 1, 2025 at 21:19. IU on `67d9c4d`, turn 6: ghost reports death January 15, 2025 while debug is January 1. Turn 9 accepts next-workday 09:00 but debug is same-day 21:53. Turn 10 narrates a 30-minute wait but advances 13 minutes. Source IU `world.start_datetime` is January 15; its canonical facts also contain both a January 14/15 death window and "died the prior week".

## Fix direction
Trace initialization and `WorldTimeFormatter` against story start time, then natural-language skip/wait extraction versus the existing dedicated skip command. Establish one authoritative time before storyteller rendering. Either commit validated skip/wait or clarify/refuse it in prose. Align authored death chronology. Regression checks should exercise new-game clock, next-workday movement, a 30-minute wait and a recalled death date earlier than current time.

## Why deferred / cautions
This task is a playtest/review, not an implementation. Exact runtime cause and feature-flag state were not established; public debug is not a full state receipt. Do not assume the dedicated skip control has the same defect. Preserve existing schedule/commitment behavior and verify hosted natural-language turns after a fix.

## Touches
`backend/app/api/prompt_engine.py`, `backend/app/engine/state.py`, time formatting/gameplay and turn extraction, `backend/app/engine/world_model/`, `backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_story.json`.
