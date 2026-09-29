# BL-42 — The storyteller rarely writes the studio panel itself

- **Type:** follow-up (tuning)
- **Found:** 2026-09-29, BL-39 phase I live finales (local and hosted beta `d1e28df`)
- **Severity:** medium: every finale so far used the canned fallback panel.

## Problem
On exit turns `world_model/turn.py::_build_view` adds the finale directive and `engine/dialogue.py::_panel_prompt` requires the reply to end with the panel, yet in 5 of 5 live finales the model wrote only the exit scene. `world_model/commentary.py::fallback_panel` then appended three short, generic, footage-only lines (counted as `TurnView.panel_fallbacks`, logged as `turn_quality_recoveries`). That breaks the O26a visible-fallback target (<= 5%) for finale turns. Also seen: the model wrote the player's own goodbye as an unattributed line, which the finale path turned into a quoted narration echo.

## Fix direction
Measure first (`turn_quality_recoveries` logs). Then try, in order: a larger output allowance for finale turns, putting the finale directive at the end of the prompt, and a structured panel field in the finale response schema, all within the same single response call (no extra model call). Drop echoed player lines on the finale path through `drop_player_echo`. Acceptance: panel written by the model in >= 95% of finales, no player echo.

## Why deferred / cautions
Needs real-model iteration and measurement; the fallback keeps finales safe meanwhile. Arena judging stays off.

## Touches
`backend/app/engine/dialogue.py`, `backend/app/engine/world_model/commentary.py`, `backend/app/api/prompt_engine.py` (finale token allowance), tests.
