# Hosted checks the social engine still owes

Carried over from the retired `TASKS_INTERMEDIATE.md` (2026-10-01): its other open boxes described phases that
`design/SOCIAL_ENGINE.md` section 11a records as built; only these hosted proofs were never done.

## BL-88 — Hosted proof of the social engine: NPC decision modes and full campaigns
- **Open:** (1) `NPC_DECISION_MODE` (`rules` / `jev` / `compare`, `world_model/npc_decision.py`) was verified end to end locally only; no hosted beta check of the `jev` and `compare` modes. (2) The full acceptance campaigns were never played hosted: a complete Terrace and a complete IU campaign (20+ turns each, both player genders for Terrace) with every turn recorded and graded by a human for logic and engagement, plus desktop Chromium, iPhone WebKit and standalone WebKit passes. (3) The last hosted checkpoints (`fe54691`, 2026-09-27) still showed player-agency invention in narration, unanswered direct questions and IU source mistakes; none has been re-measured since the fixes.
- **Next:** play the campaigns on current beta through `scripts/play_turns.py` / the browser, save the raw records under `sim_runs/`, grade them, and file each failure as its own backlog item. Check `jev` and `compare` modes with the operator header `X-NPC-Decision-Mode`. The headless season runner (plan P-04, P-13) will replace the manual playing for Terrace once it exists.
- **Touches:** none until a failure is found; evidence goes in this file, then it is deleted or narrowed.
