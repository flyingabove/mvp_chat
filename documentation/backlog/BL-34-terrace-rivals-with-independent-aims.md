# BL-34 — Same-gender housemates need competing courtship and independent aims

- **Type:** feature
- **Found:** 2026-09-25, manual Terrace play and user direction
- **Severity:** high; the goal lacks opposition and social choices currently have little cost.

## Problem
In [Terrace turns 6–8](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md), all three housemates accepted the picnic, contributed food/drinks and agreed again when the player invited disagreement. Same-gender residents never pursued an overlapping romantic interest or made a competing plan. The user wants them to try to prevent a couple leaving together. Current NPC–NPC attraction/competition can vary offscreen, but there is no story goal that makes it a visible, persistent rival system.

## Fix direction
Give each active same-gender housemate an independent courtship aim that can overlap with the player's chosen partner, along with personal work/friendship boundaries. Rivals can invite the same person out, claim limited time, ask difficult questions or form their own bond. Their choices must respect schedules, knowledge, location and the potential partner's preferences; they must not all sabotage the player or make romance a prize. Track rival-to-partner relationship changes and plans as state events, not just dialogue, and surface observable traces without exposing private thoughts. Test different initial rosters, both player genders, no interested rival, mutually interested rivals, rejection and cast rotation.

## Why deferred / cautions
Requires integration with relationship edges, offscreen outcomes, schedules and commitment state. A story prompt can give immediate tone, but without durable events it cannot prove opposition or consequences. Initial rivals need not all be interested in the same person.

**Initial implementation (2026-09-25):** the optional `mode.romance_goal` prompt identifies active potential partners and rivals from authored genders. In a feasible offscreen mixed-gender encounter, if both the player and the same-gender rival have already shown affection toward the potential partner, the world resolver increases the odds of a durable plan/affection event; its normal time, place, availability, memory, relationship and seeded draw paths remain in force. The remaining work is proactive on-screen rivalry, candidate-specific aims, feedback the player can act on, and measurement across many rosters.

## Touches
Terrace story data, `backend/app/engine/world_model/offscreen.py`, `threads.py`, relationship graph, prompt projection and tests.
