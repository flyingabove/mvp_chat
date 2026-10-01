# Terrace: reply pacing, repetition and player agency

## BL-37 — Reply pacing, repetition and player agency
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (the refusal-line cause was fixed 2026-09-30: residents' spoken lines no longer come back as recall); invented-feeling slips are now trimmed after generation (BL-29, lexical and bounded); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Also seen (2026-09-30, rivals work):** `agenda.next_beat` uses the last-beat day only to order candidates, so a `pursue` or `test_loyalty` beat toward the player is offered on every turn, not once a day (the new `compete_for` beat is limited to once a day). Check whether that makes residents repetitive in long play before changing its cadence.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.
