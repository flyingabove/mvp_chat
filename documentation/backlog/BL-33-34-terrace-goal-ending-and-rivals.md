# Terrace: the goal, its ending, and rivals

## BL-33 — Terrace: the relationship goal and its ending are not proven end to end
- **Open:** the goal shows on the card and chat banner, and early confessions or "leave together" asks are refused with no false win (hosted, 2026-09-29). Never seen on hosted beta: the accepted path (mutual relationship, both leave, panel ending) and the female-player path. Missing pieces: natural-language decision coverage, explicit refusal and coercion cases, reload and long-skip scenarios. Rejection and leaving alone must stay valid endings; no regex win detector, no silent time limit.
- **Next:** a hosted 20-turn campaign for each player gender that earns the win (seeded campaigns already prove it offline). Depends on BL-34 and BL-35.
- **Touches:** `six_strangers_story.json`, `engine/world_model/romance.py`, `prompt_engine.py`, tests.

## BL-34 — Same-gender housemates do not visibly compete
- **Open:** a rival only states interest when asked directly ("Yeah, a bit", hosted 2026-09-29, two rosters checked). No counter-invitation, competing plan or visible rival state in about three story days. The engine fires a rival invitation only after the rival has shown interest and is co-present (`intentions.py`, `offscreen.py`).
- **Next:** independent per-rival aims that overlap the player's chosen partner, respecting schedules, knowledge and the partner's preferences; state events, not just dialogue; observable traces without exposing private thoughts. Measure across rosters (both player genders, no interested rival, mutual interest, rejection, cast rotation).
- **Touches:** `world_model/offscreen.py`, `threads.py`, `intentions.py`, relationship graph, prompt projection, tests.
