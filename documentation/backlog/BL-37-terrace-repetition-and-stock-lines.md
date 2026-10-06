# Terrace: reply pacing, repetition and player agency

## BL-37 — Reply pacing, repetition and player agency
- **Bucket:** mixed: C engine + A voice data
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (the refusal-line cause was fixed 2026-09-30: residents' spoken lines no longer come back as recall); invented-feeling slips are now trimmed after generation (BL-29, lexical and bounded); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.
