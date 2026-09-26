# BL-37 — Replies need distinct voices, direct answers and less repeated atmosphere

- **Type:** quality follow-up
- **Found:** 2026-09-25, manual hosted play
- **Severity:** medium; repetition and uniform agreement reduce engagement in both stories.

## Problem
[Terrace turns 6–8](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md) show unanimous agreement, including when Natsumi is asked if she would disagree. Her house-rule answer is generic. IU turns 2–8 repeatedly describe heavy air, shadows, trembling and unspoken truths while producing fewer new leads than lines of atmosphere. Terrace turn 10 avoids the direct rice-memory question; IU turns 10–12 spend substantial text narrating guarded expressions around checkable questions. The engine already has character voices in Terrace story data and a direct-response design, but live behavior underuses them.

## Fix direction
Give an addressed, answerable question a concise answer or honest inability; prioritize the player's current intent over ensemble chatter. Limit decorative atmosphere to scene changes or specific new sensory evidence. Keep speaker style tied to their authored voice, work, aims and boundaries; allow a neutral silence or disagreement. Track direct-answer rate, repeated scene imagery, character distinguishability and turn length in hosted samples. Coordinate with BL-29 (do not assign player feelings/actions) and legacy BL-22 (character distinction) rather than duplicating their fixes.

## Why deferred / cautions
Prompt changes alter both games and need arena and human review; this is not a reason to simply cap all replies. Do not force disagreement every turn or punish deliberate uncertainty in a mystery.

**Hosted reproduction (2026-09-26, beta `1045464`):** Terrace turn 3 ignored the direct request for Misaki to confirm a 7 pm plan and let Masako volunteer instead; turn 4 required the player to restate the boundary. IU turn 4 narrated "the weight of her words" while IU gave no answer to a direct source question; turn 5 required repetition. IU turn 10 did not answer whether any new physical evidence existed. The same atmosphere phrases and player feelings recur in both ten-turn runs. The current social-only scene guard removes some player-internal narration and unidentified speech in empty rooms, but direct-answer and mystery pacing gates remain open.

## Touches
`backend/app/engine/prompt_builder.py`, `dialogue.py`, Terrace voice data, tests and hosted evaluation.
