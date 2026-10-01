---
id: P-05
title: Jev script rubric (scene, day, season) and a labelled calibration set
stage: 1
size: M
depends_on: [P-02]
touches: [backend/app/sim/rubric.py, tests/eval_cases/script_rubric/, scripts/eval/script_rubric_eval.py, tests/backend/integration/test_script_rubric.py]
backlog: BL-87
---
**Goal:** a repeatable way to say whether a scene, a day and a season are engaging drama.

**Read first:** `documentation/backlog/BL-87-drama-direction-and-script-rubric.md` (the rubric items S1-S8, E1-E6, R1-R5,
the verdict rule and its research sources), `scripts/eval/promise_judge_eval.py` and
`backend/app/engine/world_model/promise_judge.py` (the pattern: bounded Jev questions, labelled dev set, untouched held-out
set, never tuned against), `backend/app/llm/decisions/`.

**Build**
- Each rubric item as a bounded question with anchored answers 1-5 (mapped to 2-10), asked through the shared Jev
  resolver; aggregate to scene, day and season scores and the Pass / Consider / Recommend verdict (Recommend: mean >= 8, no
  item below 5, plausibility >= 8).
- `tests/eval_cases/script_rubric/`: a dev set and a held-out set of scenes with human labels. Start from real transcripts;
  the owner labels (target about 60). Until labelled, the rubric is advisory and says so in every report.
- `scripts/eval/script_rubric_eval.py` reports agreement per item; an integration test (marked `integration`, never run
  on deploy) enforces a stated agreement bar once labels exist.
- Unit tests with a fake Jev: aggregation, the verdict rule, advisory flag.

**Spending:** live Jev calls cost money; the offline unit tests come first and the labelled run needs the owner's go-ahead.

**Done when:** unit tests pass; the rubric scores a sample scene offline with the fake; the labelling instructions for the
owner are in `tests/eval_cases/script_rubric/README.md`.
