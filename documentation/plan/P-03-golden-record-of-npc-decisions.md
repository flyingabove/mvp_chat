---
id: P-03
title: Golden record of seeded Terrace NPC decisions (the refactor safety net)
stage: 0
size: M
depends_on: []
touches: [tests/backend/app/engine/world_model/test_decision_golden.py, tests/backend/app/engine/world_model/golden/]
backlog: BL-85 (P0)
---
**Why:** stances (P-08) and scenes (P-11) replace several hand-coded decision paths. They must not change behaviour by
accident, so we record today's behaviour first and diff against it.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (phase P0),
`tests/backend/app/api/test_terrace_campaigns.py` (the seeded campaign pattern and its fixtures),
`world_model/agenda.py`, `intentions.py`, `offscreen.py`, `rivals.py`, `act_fallout.py`.

**Build**
- A helper that runs seeded Terrace campaigns (seeds 0-11, both player genders) with no model calls, and records per
  story day: each character's intentions (kind, target, priority), the beat offered, invitations made, off-screen
  outcomes (kind, pair), fallout applied, couples formed or left, and the director clock.
- Commit the record as JSON under `tests/backend/app/engine/world_model/golden/` and a test that re-runs the helper and
  compares to it. A deliberate behaviour change must update the golden in the same commit with the reason in the
  message; the test failure message says exactly that.
- Keep it fast (target under 30 s) and fully deterministic; no wall-clock or network.

**Done when:** the test passes twice in a row and fails (with a readable diff) when you change one constant such as
`act_fallout.WITNESS_LOSS`; documented in `design/SOCIAL_ENGINE.md` under the engine test notes.

**Note:** BL-85 stays open; remove only its P0 mention when this ships.
