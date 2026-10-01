---
id: P-06
title: Baseline pilot season on Gemini + Jev with today's prompts (needs owner approval to spend)
stage: 1
size: M
depends_on: [P-04, P-05]
touches: [scripts/run_season.py, tests/scripts/test_run_season.py]
backlog: BL-86, BL-87
---
**Goal:** a recorded rubric score for today's engine, so every later stage can prove it made the drama better.

**Read first:** `documentation/backlog/BL-86-headless-season-simulation.md`, `BL-87-drama-direction-and-script-rubric.md`,
P-04 and P-05 as built (`backend/app/sim/`).

**Build**
- `scripts/run_season.py`: runs `SeasonRunner` with the real LLM writer (Gemini + Jev by default, OpenAI + Jev via the
  provider switch from P-02) for a capped pilot (2 story days, a hard cost cap printed before it starts), and writes the
  artifacts (scenes, state diffs, rubric scores) as JSONL.
- Offline unit tests drive the script with the fake writer (argument handling, cost cap refusal, artifact shape).

**Spending: ASK THE OWNER before the real run.** Report the cap and the expected cost, then run once and record the
baseline rubric scores (scene, day, season, verdict) in `design/SOCIAL_ENGINE.md` under a "Season baseline" heading with
commit, provider, seed and date. Absence of a result is reported as absence.

**Done when:** the baseline is recorded and the script is documented; BL-86's Next line is updated.
