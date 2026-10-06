---
id: P-13
title: Season camera, artifacts and the admin-only watch mode
stage: 3
size: L
depends_on: [P-04, P-11]
touches: [backend/app/sim/camera.py, backend/app/sim/artifacts.py, backend/app/api/debug_engine.py, frontend/debug.html, tests/backend/app/sim/]
backlog: BL-86
---
**Goal:** a season worth watching: the camera picks the interesting encounters, the run leaves readable artifacts, and an admin
can watch it and inspect any character's mind. Players never see this (owner: admin only).

**Read first:** `documentation/backlog/BL-86-headless-season-simulation.md` (design 2-4), the operator auth in
`backend/app/api/debug_engine.py` and `ai_learnings_mistakes/AI_SCORER_SYSTEM.md`, `frontend/debug.html`,
P-11's scene tension scores.

**Build**
- Camera: rank each day's encounters by scene tension and write the top `scenes_per_day` in full; summarize the rest in one
  line inside the same writing call, so the world advances everywhere.
- Artifacts per season: scenes, state diffs, plans, mind changes, rubric scores, as JSONL plus a static HTML episode view.
- Admin watch mode behind the existing operator auth: start/stop a season, read it day by day, and open any character's mind
  (what they know, what they think others know) and stance graph.
- The capped integration test from BL-86 design 5 (`pytest -m integration`, never on deploy): six residents always,
  no telepathy, consent rules, rival evidence over several days (absorbed BL-34), a minimum rubric score.

**Tests first:** camera ranking and caps on the fake writer; artifacts are complete and ordered; the watch routes reject
non-operators; the page renders from a saved season.

**Done when:** an admin can run and read an offline season in the debug UI; BL-86 is rewritten to what remains or deleted.

**Already built (do not redo):** the Drama Theatre (`backend/app/sim/theatre.py`, `backend/app/api/theatre.py`,
`frontend/drama.html`) is the interactive watch mode: group scenes, nudges, skips, auto-play and replay. P-13 now adds the
tension-ranked camera and episode artifacts to it; reuse its beat log rather than a second viewer.
