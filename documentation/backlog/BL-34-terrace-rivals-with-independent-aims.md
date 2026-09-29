# BL-34 — Same-gender housemates need competing courtship and independent aims

- **Type:** feature
- **Found:** 2026-09-25, manual Terrace play and user direction
- **Severity:** high; the goal lacks opposition and social choices currently have little cost.

## Problem
In [Terrace turns 6–8](../archive/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md), all three housemates accepted the picnic, contributed food/drinks and agreed again when the player invited disagreement. Same-gender residents never pursued an overlapping romantic interest or made a competing plan. The user wants them to try to prevent a couple leaving together. Current NPC–NPC attraction/competition can vary offscreen, but there is no story goal that makes it a visible, persistent rival system.

## Fix direction
Give each active same-gender housemate an independent courtship aim that can overlap with the player's chosen partner, along with personal work/friendship boundaries. Rivals can invite the same person out, claim limited time, ask difficult questions or form their own bond. Their choices must respect schedules, knowledge, location and the potential partner's preferences; they must not all sabotage the player or make romance a prize. Track rival-to-partner relationship changes and plans as state events, not just dialogue, and surface observable traces without exposing private thoughts. Test different initial rosters, both player genders, no interested rival, mutually interested rivals, rejection and cast rotation.

## Why deferred / cautions
Requires integration with relationship edges, offscreen outcomes, schedules and commitment state. A story prompt can give immediate tone, but without durable events it cannot prove opposition or consequences. Initial rivals need not all be interested in the same person.

**Initial implementation (2026-09-25):** the optional `mode.romance_goal` prompt identifies active potential partners and rivals from authored genders. In a feasible offscreen mixed-gender encounter, if both the player and the same-gender rival have already shown affection toward the potential partner, the world resolver increases the odds of a durable plan/affection event; its normal time, place, availability, memory, relationship and seeded draw paths remain in force. The remaining work is proactive on-screen rivalry, candidate-specific aims, feedback the player can act on, and measurement across many rosters.

**Further implementation (2026-09-26):** Interested, co-present same-gender rivals can now propose a competing invitation at most once per day. It remains a proposal until the target accepts, and the plan persists in the agreement book. Remaining: broader independent aims, target preference and refusal policies, offscreen plans with the same decision contract, cast-rotation tests and roster-scale measurement.

**Hosted replay (2026-09-27, beta `9db4b8f`):** After Paul announced a coffee plan with Natsumi, Yuuki and Hikaru each said she was interesting but declined to compete in the moment. No visible counter-invitation or independent plan occurred in ten turns. This single roster does not prove the rival system never fires; it does show that the player's pursuit still faced no meaningful opposition in a fresh game. Measure across rosters and make individual rival aims actionable, not merely polite dialogue.

## Touches
Terrace story data, `backend/app/engine/world_model/offscreen.py`, `threads.py`, relationship graph, prompt projection and tests.

**Hosted beta check (2026-09-29, beta `f088640`, fresh guest as Paul, ~20 turns, 3 story days):** Arman and Hayato (male rivals) arrived and stayed co-present with Riko. Arman only asked about the coffee plan ("Sounds fun!"). No counter-invitation, competing plan or visible rival state appeared in 3 days. This is a second roster with the same result as the 2026-09-27 replay, so BL-34 is **not verified**; keep it open. The player did not reach a stated interest from a rival, which the engine path requires, so this is a weak negative, not proof the path never fires.
