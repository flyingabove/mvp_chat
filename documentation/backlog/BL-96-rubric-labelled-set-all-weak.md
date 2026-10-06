# Script rubric: the labelled set has no strong scenes

## BL-96 — The rubric's labelled scenes are all weak, so it is not yet shown to recognise strong drama
- **Bucket:** mixed: A labelled data + C engine

- **Problem:** the 60 scenes in `tests/eval_cases/script_rubric/` are real opening-dinner chat and every one is Pass-level
  (human verdict Pass 60 of 60, S1 to S5 almost all 1 or 2). The agreement bar (within one point, verdict agreement) was
  met, but a rubric that answers 1 or 2 for everything also meets it. Also, the labels were written by Claude at the
  owner's instruction, not by the owner.
- **Fix:** add 20 or more scenes that a reader would score Consider or Recommend (real scenes from the P-06 baseline
  season and later tuned presets, plus hand-picked strong ones), label them, re-run `--run --set all`, and require
  agreement on those too (the verdict must separate the groups). Optionally have the owner re-label a sample of 20 to
  check the AI labeller.
- **Candidates now:** the six scenes in the P-06 baseline (`data/season_runs/baseline-pilot-1/season.jsonl`, local) are the
  first non-Pass scenes the rubric produced (Jev: four Recommend, two Consider); label them blind to Jev's scores. They also
  share one beat (a quiet shared task ending on a touch of hands), so a repetition check across scenes is part of this.
- **Done when:** the labelled set covers all three verdicts, the bar holds on a held-out part of it, and the README says who
  labelled.
