# Terrace: repetition, stock lines and reply pacing

## BL-47 — A refusal line is reused across unrelated turns
- **Open:** hosted beta 2026-09-29 (35 turns): after the first confession Minori answered many unrelated turns with variants of "I want to take my time getting to know everyone, no big plans for now" (moving rooms, breakfast, turn 26 while Paul made her breakfast); Hikaru reused a line Minori had just said. The exact-replay guard (`dialogue.py` `own_repeat_indexes`, checks each speaker's own earlier lines of 6+ words) does not catch variants. Mechanism unverified: either the refusal is re-injected each turn (`view.must_address`, relationship-decision memories in `romance.py`/`social_acts.py`) or the character's own earlier lines come back as retrieved dialogue memories.
- **Next:** build the prompt offline for a scripted state after a `not_yet` verdict and see whether the refusal or the speaker's old lines are injected on unrelated turns; pass the outcome only on the turn of the ask and when the player raises it again; failing-first test that a plain non-romantic message two turns after a `not_yet` carries no refusal directive. Measure by counting repeated sentences in a 25-turn replay.

## BL-37 — Reply pacing, repetition and player agency
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (see BL-47); narration still assigns the player feelings not stated (see BL-29); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.
