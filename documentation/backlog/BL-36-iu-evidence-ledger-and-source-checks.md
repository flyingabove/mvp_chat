# BL-36 — IU investigation needs sourced evidence and unresolved contradictions

- **Type:** feature
- **Found:** 2026-09-25, manual IU play
- **Severity:** medium; a mystery is hard to reason about when testimony and observed facts merge.

## Problem
The [IU play review](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md) found an observable closet-jamb scratch in turn 4; IU appropriately said she might have made it but was unsure. In turns 5–6 she supplied a death date that conflicted with the engine clock (BL-30). In turns 10–12 Yoo Min-ho's "few weeks" became January 8 versus January 12/13, a four/five-day interval. His later "memory can blur" may be a deliberate lie or a continuity error. The player requested a calendar check; no independent result arrived by turn 12. The engine needs to preserve the discrepancy without silently treating either statement as verified truth.

## Fix direction
Track each observation, statement and corroboration separately with source, speaker, time, confidence and unresolved conflict status. The player should see a concise journal/evidence view: scratch observed, origin unknown; IU's date is testimony pending clock repair; manager visit date is disputed pending calendar. Independent records or witnesses can confirm/refute, and the storyteller must not collapse uncertainty into fact. Reuse the existing world-model evidence/events/memories and journal where possible. Test clue discovery, contradictory testimony, verification, persistence, and no secret leakage. Solve BL-30/31 before claiming a trustworthy IU chronology.

## Why deferred / cautions
The user asked to focus current implementation on Terrace; keep IU as engine consistency follow-up. A suspect's shifting answer must remain possible rather than being deterministically "corrected" into honesty.

## Touches
`backend/app/engine/world_model/evidence.py`, `events.py`, `memory.py`, IU story leads, journal route and tests.
