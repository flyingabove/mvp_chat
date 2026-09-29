# Promise completion judged by Jev (2026-09-29)

**Status:** built. Reminders and silent lapse are live; the Jev judge is built but **off by default** (`PROMISE_JUDGE_ENABLED`) because it measured just under the owner's 99% bar. Move the built parts into a `reference/` doc if the judge is ever turned on by default.

## Problem
Live beta (`f088640`): the player promised Riko tea, made it ("Here you go, Riko. How do you take your tea?"), and Riko kept asking about the tea and kettle for turns. The old `commitments._performed` only counted a message that started with "I", named the counterpart and shared two words with the promise, and `due_commitments` re-injected an open promise every turn for 12 in-game hours.

## Owner rule (`user_corrections.md` 2026-09-29)
An NPC forgetting is acceptable. The game **failing to register something that happened** is not. A tracker that cannot reach ~99% in that direction is removed in favour of plain conversation context. Semantic judgments go to Jev, not regex or word overlap.

## What was built
1. **Remind once** (`Memory.reminded`, `commitments.mark_reminded`): a due promise is put in the scene contract (or an away-contact message) at most once, on both parties' copies. Independent of Jev, on by default.
2. **Silent lapse**: a promise-derived plan that passes its deadline no longer creates an "unfulfilled plan" conflict. Nothing can prove it went unkept, and accusing someone over something that happened is the forbidden error. Plans with no promise memory (NPC agendas) keep the old behaviour.
3. **Word-overlap completion deleted** (`_performed`, `complete_actions` and their tests). No regex fallback.
4. **Jev judge** (`world_model/promise_judge.py`, task `promise_status`), behind `PROMISE_JUDGE_ENABLED` (default off, needs `TYPESAFE_ENABLED`). For each open promise whose parties are both present (max 4, newest first), one Jev request asks two differently shaped questions about the last exchange: a four-way choice (`done | cancelled | pending | unclear`) and a yes/no "was it carried out?". `done` registers if **either** says so (choice `done`, choice odds for done >= 0.30, or yes/no >= 0.30). Staying open needs a confident `pending` (>= 0.60). Everything else closes the promise quietly. Jev unreachable leaves it untouched. `done` completes the agreement with an evidence event and gives the doer +0.05 trust.
5. Turn wiring: `world_turn.review_promises` in `prompt_engine.py`, before the scene is built; every ruling is logged as `promise_judgment`.

## Measurement (local, live Jev; `python -m scripts.eval.promise_judge_eval --set all --show-misses`)
Cases: `tests/data/promise_judge_cases.json` (dev, 150: tuned against) and `promise_judge_holdout.json` (168: written before seeing Jev's behaviour, and no wording or threshold was tuned on it; but the two-question design was chosen after its results were seen, so it is no longer a fully clean test. Write a fresh set before certifying). 171 kept, 93 not-yet and 54 cancelled across 27 promise scenarios, both directions, nicknames, narration-only, handovers.

| Version | Missed kept promises | Kept when not done |
|---|---|---|
| Choice only, confidence cutoff 0.6 | 10/75 (13%) on dev | 0/75 |
| Choice only, cutoff removed, done from p>=0.30, clearer instructions | dev 1/75, holdout 1/96 | 0/147 |
| Choice + yes/no, either says done (shipped) | **2/171 = 1.2%** (95% interval 0.3-4.2%) | **0/147** |

Both remaining misses are "we ... together" statements the model reads as still pending. 1.2% is a hair under the gate, and 171 cases cannot certify 1% (the interval is wide), so the judge ships dark. Measuring more before turning it on: run the eval with a bigger held-out set, or `--runs 3` for stability.

## To turn it on
Set `PROMISE_JUDGE_ENABLED=1` (and `TYPESAFE_ENABLED`). Watch `promise_judgment` log lines for `keep`/`dropped` on promises the player visibly kept.

## Out of scope / follow-up
Name and nickname matching (e.g. "Uchi" vs "Tatsuya") moves to Jev under the same 99% rule: see `backlog/BL-43`.
