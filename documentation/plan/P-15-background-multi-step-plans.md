---
id: P-15
title: Background multi-step plans for any character (short and long horizon)
stage: 4
size: L
depends_on: [P-11]
touches: [backend/app/engine/world_model/plans.py, backend/app/engine/world_model/agenda.py, backend/app/engine/world_model/intentions.py, backend/app/sim/jobs.py, backend/app/api/prompt_engine.py]
backlog: BL-81
---
**Goal:** characters carry out plans longer than one turn: talk to X, call Y, go to a room, plant a rumour, stage a conversation, watch
someone. Horizon comes from personality (an INTP rarely plans long-term; `planfulness`).

**Read first:** `documentation/backlog/BL-81-82-adversaries-and-intrigue.md` (BL-81), `documentation/backlog/BL-85-character-social-mind.md`
(owner decision: short- and long-term plans scaled by planfulness; fog of war), `world_model/agenda.py`, `commitments.py`,
`offscreen.py`, P-11's wants.

**Build**
- A plan is an ordered list of physically executable steps (a conversation, a call, a location). A trigger (a confession, a
  betrayal opening, a rival noticing interest) starts a background job after a turn's bounded decision step; a finished plan
  executes unless the player acts first. No telepathy: every step uses information the planner actually has (the mind) and an
  action the world allows.
- Persistence across saves and deploys, a cost cap per job, and determinism in tests (a fake planner).
- The two-LLM-calls-per-turn budget applies to player turns; background jobs use the headless writer's budget (P-04) and are
  counted separately.

**Tests first:** a plan survives a save/reload and resumes; the player acting first cancels the next step; a step that needs
unknown information is not generated; a long-horizon plan appears only for high `planfulness`; cost cap stops a job.

**Done when:** suite green; `WORLD_MODEL.md` documents plans as built; BL-81 deleted or rewritten to the remainder.
