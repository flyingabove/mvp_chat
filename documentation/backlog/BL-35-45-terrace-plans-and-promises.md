# Terrace: plans, promises and the promise judge

## BL-35 — Plans and knowledge follow-through
- **Bucket:** C (engine)
- **Open:** a verbal acceptance of a later meeting ("coffee tomorrow at 10") still leaves the place empty at that time; the player is only accompanied when they invite at that moment (`companions.py`). Missing: scheduled arrival at a promised time and place, typed witnessed NPC actions, per-participant attendance, travel validation, privacy movement when a nearby resident can hear, full same-turn invitation extraction. Lapsed promise-derived plans now expire silently by design (owner rule: never register a kept promise as broken), so "missed plans affect trust" is deliberately not built.
- **Touches:** `world_model/commitments.py`, `agreements.py`, `turn.py`, extractor, prompt projection.

## BL-45 — Promise judge misses about 1% of kept promises
- **Bucket:** C (engine)
- **Open:** `world_model/promise_judge.py` registers a kept promise when either of two Jev questions says done. Measured 0.6-1.2% missed (gate 2%: `pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py -s`), 0 wrongly kept. Remaining misses are first-person-plural completions Jev reads as pending: "We finish the whole basket together and fold everything" (case `s4-done4`, choice `pending` at 0.95), "We walk out together and I point out the pool" (`s1-done4`, flips around the 0.30 line), and an ambiguous "How's the braid?" (`h2-done5`).
- **Next, in order:** (1) a third differently framed question, keep either-says-done, confirm 0 wrongly kept; (2) reword the state text so a joint completed action reads as done; (3) write 60+ new "we ... together" and narration-only cases to a fresh third file first (the current holdout is no longer clean because the design was chosen after seeing it) and do not tune against it. At 171 cases one miss still has a 95% interval of 0.1-3.2%.
- **Touches:** `promise_judge.py` (`decision_for`, `done_decision_for`, `view_text`, `DONE_AT`), `tests/eval_cases/`, `scripts/eval/promise_judge_eval.py`.
