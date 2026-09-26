# BL-33 — Terrace needs a relationship goal and a validated ending

- **Type:** feature
- **Found:** 2026-09-25, manual Terrace play and user direction
- **Severity:** high; without a goal, friendly conversations lack direction and consequence.

## Problem
Terrace `mode.open_ended`, its `rules_profile`, `world_context`, and `tests/backend/app/engine/test_gameplay.py` explicitly forbid a win condition. The user wants a male player to form a relationship with a woman, or a female player with a man, and for the two to leave the house together. In the [manual play review](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md), the player arranged a cooking lesson (turns 2, 5, 9) and a picnic (turns 6–7) but had no goal that made choosing between those connections matter. A pleasant activity must not itself count as mutual romance or consent to leave.

## Fix direction
Expose the goal in the story card/player brief and storyteller context, resolved from player gender and current active cast. Track the player's chosen/possible partner without predetermining one. A win requires a current eligible opposite-gender partner's explicit, voluntary commitment to leave together, the player's own commitment, and an engine-approved departure/ending transition; verify it from structured state, not a regex match in prose. Rejection and leaving alone remain valid endings. Do not declare victory when the player merely asks or when an NPC uses a generic phrase like "let's go." Cover male and female paths, new and resumed sessions, inactive/rotated cast, coerced/refused departures, and false-positive dialogue.

## Why deferred / cautions
Work can ship in stages, but a prose-only goal is not a completed mechanic. The previous answer proposed a limited stay; the user did not choose a duration, so do not silently impose one. Any deadline should be optional/explicit. Keep the resident replacement invariant and don't prewrite an NPC's consent.

**Initial implementation (2026-09-25):** Terrace now displays the goal on its story card and public story brief, sets `mode.open_ended=false`, and renders only active gender-eligible partners/rivals in storyteller context. No regex win detector was added. The remaining work is relationship choice/state, independent acceptance, player and partner departure, alternate endings, and hosted proof of those endings.

## Touches
`backend/app/stories/7_six_strangers/six_strangers_story.json`, `backend/app/engine/`, `backend/app/api/prompt_engine.py`, public story/brief routes, tests and UI as needed.
