# BL-31 — Named NPC dialogue is Unknown voice while scene presence is empty

- **Type:** bug
- **Found:** 2026-09-25, manual hosted IU playthrough on `67d9c4d`
- **Severity:** high; a named suspect conversation loses identity and disagrees with recorded scene presence.

## Problem
[Review, IU turns 9–12](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md): narration introduces receptionist Jisoo, then canonical manager Yoo Min-ho in EDAM Entertainment Lobby. Every dialogue segment in those turns has `speaker_name: "Unknown voice"`, `speaker_id: null`; `debug_box.people_present` is empty. Player movement to the lobby is recorded. This establishes a public representation mismatch, not that every private state object is empty. Jisoo may be an incidental NPC; Yoo Min-ho is authored cast.

## Fix direction
Trace allowed-speaker selection, arrival staging and final segment normalization. A canonical NPC arriving in prose should have a validated scene transition and stable speaker identity; incidental named NPCs need an explicit supported identity policy. Test IU to EDAM reception to manager arrival, checking names/IDs/presence across subsequent turns. Do not populate presence merely by trusting arbitrary model-generated names.

## Why deferred / cautions
Review-only task. Related to legacy BL-24 movement tracking, but this evidence includes lost named-speaker presentation and needs an integrated regression. Do not bypass the cast/knowledge validation to fix labels cosmetically.

## Touches
`backend/app/engine/dialogue.py`, `backend/app/engine/world_model/speakers.py`, scene/presence and turn extraction in `backend/app/api/prompt_engine.py`, IU story locations.
