# Terrace: repetition, stock lines and reply pacing

## BL-47 — Arrival introductions are replayed and refusal lines are reused
- **Open:** hosted beta 2026-09-29: Yuriko and Hikaru said their arrival lines a second time, word for word, when Paul greeted them (turn 9). After the first confession Minori answered many unrelated turns with "I want to take my time getting to know everyone, no big plans for now" (breakfast, moving rooms); Hikaru reused a line Minori had just said. Mechanism unverified (an arrival beat re-offered as a reply; a refusal directive or memory re-injected each turn).
- **Next:** mark an introduction delivered per character and test a greeting after arrival through `begin_turn`; find what keeps the confession outcome in front of the storyteller (`view.must_address`, relationship-decision memories in `romance.py`/`social_acts.py`) and pass it only on the turn of the ask or when raised again. Measure by counting repeated sentences in a 25-turn replay.

## BL-37 — Reply pacing, repetition and player agency
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (see BL-47); narration still assigns the player feelings not stated (see BL-29); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.
