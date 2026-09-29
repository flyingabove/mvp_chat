# BL-45 — Promise judge still misses ~0.6-1.2% of kept promises ("we … together" phrasings)

- **Type:** follow-up
- **Found:** 2026-09-29, promise-completion rework (`documentation/proposals/PROMISE_COMPLETION_JEV_2026_09_29.md`)
- **Severity:** low; the shipped design already makes a miss invisible (reminders are once-only, a lapse is silent, a missed completion only skips a +0.05 trust gain). Fixing it moves the measured miss rate from ~1% toward 0.

## Problem
`backend/app/engine/world_model/promise_judge.py` registers a kept promise when either of its two Jev questions (four-way choice, yes/no) says done. Across 171 labeled kept promises the miss rate is 1/171 (0.6%) to 2/171 (1.2%) depending on the run (live Jev varies a little). The misses are player statements in first-person plural that describe a joint action as it is being completed, which Jev reads as still pending:
- `s4-done4` (`tests/eval_cases/promise_judge_cases.json`): promise "help her with the laundry", message "We finish the whole basket together and fold everything." Choice answer `pending` at 0.94-0.97 and the yes/no answer under 0.3, every run.
- `s1-done4`: promise "show her around the terrace", message "We walk out together and I point out the pool, the loungers, the skyline." Choice `pending` about 0.7; the yes/no answer sits near the 0.30 line, so it flips between runs.
- `h2-done5` (holdout): "How's the braid?" after "Riko peeks at herself in the mirror." Jev said `unclear` (0.45); the label itself is arguably ambiguous.

## Fix direction
Try in this order, measuring each with `pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py -s` (gate 2%) and `python -m scripts.eval.promise_judge_eval --runs 3 --show-misses`:
1. Add a third, differently framed question (for example "Who did the promised thing, and did they finish it?") and keep the either-says-done rule. Check it does not create wrongly-kept cases (today 0/147).
2. Rephrase the state text so a joint completed action reads as done (for example say the exchange is "what just happened", not "what was said").
3. Add cases first: write 60+ more "we … together" and narration-only kept promises to a **fresh** third file (the current holdout is no longer clean because the two-question design was chosen after its results). Do not tune against the fresh file.
Raise the sample size before trusting any number under 1%: at 171 cases a 95% interval for 1 miss still spans 0.1-3.2%.

## Touches
`backend/app/engine/world_model/promise_judge.py` (`decision_for`, `done_decision_for`, `view_text`, `DONE_AT`), `tests/eval_cases/promise_judge_*.json`, `scripts/eval/promise_judge_eval.py`, `tests/backend/integration/test_promise_judge_accuracy.py`.
