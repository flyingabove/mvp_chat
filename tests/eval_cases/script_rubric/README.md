# Script rubric: labelling instructions (owner)

**What this is for:** the engine scores scenes, days and seasons with a Jev "script reader" (`backend/app/sim/rubric.py`).
Until you have labelled enough scenes to show Jev agrees with you, every score is **advisory** and says so. Your labels
are the ground truth the rubric is calibrated against.

**Edit this doc if** the rubric items, the scale, the agreement bar or the file layout change.

## What to label

- `dev.json`: 40 real Terrace scenes (a player line plus the storyteller's reply, from hosted arena runs). Used while
  tuning the rubric.
- `holdout.json`: 20 more. **Do not use them for tuning**; they are read once at the end to check the rubric was not
  fitted to the dev set.
- Total target: about 60 labelled scenes (`rubric.LABELS_REQUIRED`).

Each case looks like `{"id", "source", "setting", "text", "labels": null}`. Replace `null` with your scores:

```json
"labels": {"S1": 3, "S2": 2, "S3": 4, "S4": 2, "S5": 3, "S6": 5, "S7": 2, "S8": 3}
```

## How to score a scene

1. Print the anchors: `python -m scripts.eval.script_rubric_eval --anchors`. Each of the 8 items has five described
   levels. Pick the level whose description best fits the scene (1 = the first description, 5 = the last).
2. Judge **only what is on the page**. Do not reward length. A pleasant, flat scene is a 1 or 2 on most items; keep 5
   for scenes you would show to someone as good drama.
3. S6 (plausibility) is about believability, not tameness: exaggeration is fine when the situation earns it.
4. Score every item for every scene you label. A scene with a missing item is ignored.

The scale Jev reports is 2 to 10 (your 1-5 doubled). A scene is "Recommend" at mean 8+, no item below 5 and
plausibility 8+ (your S6 of 4 or 5).

## Checking progress and agreement

- `python -m scripts.eval.script_rubric_eval --status --set all`: how many scenes are labelled (free).
- `python -m scripts.eval.script_rubric_eval --run --set dev`: Jev's agreement per item on the labelled dev scenes.
  **This calls live Jev and costs money: ask the owner before running it.** It refuses to run with no labels.

**The bar** (fixed before any labels exist): for every item, Jev is within one point of you on at least 80% of scenes,
and the scene verdict (Pass / Consider / Recommend) agrees on at least 70%. Once the bar holds on the held-out set,
set `CALIBRATED = True` in `rubric.py` and the advisory note disappears. The integration test
`tests/backend/integration/test_script_rubric.py` (`pytest -m integration`, never run on deploy) enforces the bar.

## Rebuilding the candidate scenes

`--build-candidates` samples from local arena transcripts (`data/eval_arena`, gitignored) with a fixed seed. It refuses
to overwrite existing files so labels are never lost.
