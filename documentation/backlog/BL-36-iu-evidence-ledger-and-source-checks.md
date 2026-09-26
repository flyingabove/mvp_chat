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

**Hosted reproduction (2026-09-26, beta `1045464`, new IU session):** turn 3 established closet scratches and turn 4 photographed them. Turn 5 correctly distinguished IU's lack of memory of making them. On turn 6 IU invented that Mira had told her additional items were missing; on turns 7–8 she repeated that attribution after Mira explicitly denied ever saying it. Turn 9 presented the same scratches as a fresh discovery and turn 10 repeated IU's earlier reaction. This requires source/path validation and discovered-clue deduplication, not merely another storyteller instruction. Full raw turn records are in the local social-v2 hosted-play artifact folder.

**Partial correction awaiting beta retest:** the inspection result now distinguishes first discovery from reinspection and tells the storyteller when no new surface was found. This does not itself prevent invented testimony provenance or guarantee the model follows the clue instruction; the item remains open.

## Touches
`backend/app/engine/world_model/evidence.py`, `events.py`, `memory.py`, IU story leads, journal route and tests.
