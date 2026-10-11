---
id: P-14
title: Strategies (scheming, safe pick, planfulness, candor) and "let me think" answers
stage: 4
size: M
depends_on: [P-11]
touches: [backend/app/engine/rules/personality.py, backend/app/engine/world_model/social_acts.py, backend/app/engine/world_model/npc_decision.py, backend/app/engine/world_model/act_fallout.py, backend/app/engine/world_model/commentary.py, backend/app/engine/world_model/person.py]
backlog: BL-85 (P5), BL-82
---
**Goal:** the personality fields that are stored but unused start to matter, and a high-stakes ask can be answered later.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (P5 and the absorbed-work list),
`documentation/backlog/BL-81-82-adversaries-and-intrigue.md` (BL-82: `pending_answer`, the `defer` verdict, leave-together
fallout, finale dossier), `rules/personality.py` (`STRATEGIES` has only `aim_scale` today; `scheming` and `safe_pick` have no
behaviour), `world_model/social_acts.py`, `npc_decision.py`, P-11's wants.

**Build**
- `scheming`: uses secrets and second-order beliefs (selective telling, staging a conversation) through P-11's wants;
  `safe_pick`: when asked, prefers whoever stands highest with them over the player; `planfulness`: how reliably someone
  keeps plans and how far ahead they plan; `candor`: how directly they speak and disclose. All consume the stance and
  mind objects, never engine truth.
- `pending_answer(act, target, due_day)`: a "still thinking" reply that resolves after days from the target's own stances and
  strategy; a rival may ask first. Add `defer` to the verdict options. Apply declined-act fallout to `ask_leave_together`, and
  add declined acts to the finale dossier (check `commentary.FOOTAGE_KINDS`).

**Tests first:** each strategy changes the chosen want in a fixed-seed fixture; a deferred answer comes back on the due day and
can lose to a rival who asked first; fallout for `ask_leave_together`; the golden record differs only where configured.
**Arena gate** (behaviour change; owner approval).

**Done when:** suite green; docs updated; BL-85 P5 and the matching BL-82 parts removed or narrowed in the same commit.
