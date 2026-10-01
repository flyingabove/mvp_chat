---
id: P-04
title: SeasonRunner on a fake writer (headless season, offline)
stage: 1
size: L
depends_on: [P-01, P-02]
touches: [backend/app/sim/__init__.py, backend/app/sim/runner.py, backend/app/sim/writer.py, tests/backend/app/sim/]
backlog: BL-86
---
**Goal:** run a whole story with no human player, offline, so the plumbing is proven before any paid model runs.

**Read first:** `documentation/backlog/BL-86-headless-season-simulation.md` (design 1, 2 and owner decisions),
`backend/app/engine/world_model/stepper.py`, `routine.py`, `offscreen.py` (encounters), `turn.py` (`begin_turn`,
`end_turn`: the one turn transaction to reuse), `backend/app/api/prompt_engine.py` (how a turn is committed).

**Build**
- `SeasonRunner(story, seed, writer, days, budget)` that advances the clock, lets every present-or-moving character act
  from today's routines and agendas, forms encounters of two or more co-located awake people, asks the `writer` for the
  scene, and commits through the **existing** turn path (no second engine). Hard caps: scenes per day and a total
  budget (calls/tokens) that stops the run cleanly.
- A `Writer` protocol with a `FakeWriter` (deterministic scripted text and extraction) for tests. The real LLM writer
  comes later (P-06 uses it); keep the protocol small: `write_scene(prompt) -> text`, `extract(text) -> updates`.
- The AI-resident hook: the player slot can be held by a scripted resident under the same `Person` rules.
- Invariants checked every day: Terrace holds exactly six residents (cast lifecycle replaces leavers), no character knows
  something they never perceived, no consent bypass.

**Tests first:** a 5-day Terrace season on the fake writer completes, is repeatable per seed, respects both caps, and
never violates the invariants; a deliberately broken writer (invents a fact) is caught.

**Done when:** `pytest` runs the offline season in the unit gate in under 60 s; BL-86's design section is updated to as-built
and its Next line drops this item.
