# BL-35 — Social plans, invitations and knowledge need reliable follow-through

- **Type:** bug / feature
- **Found:** 2026-09-25, manual Terrace play
- **Severity:** medium; agreed plans and trust changes feel arbitrary without an agreed-state record.

## Problem
In [Terrace turns 3 and 5](../model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md), the player proposed a next-day cooking lesson; the initial question was dropped on a room transition, then Misaki later accepted. Turn 9 staged the lesson in prose but the world clock was wrong (BL-30). Turn 7 assigned picnic duties; turn 10 Misaki declared herself "definitely in" although the player asked whether she had heard of it, without showing how she learned. Masako answered a quiet aside in turn 5 although the player asked for privacy while she was nearby. None proves remote knowledge leakage, but the experience gives no clear boundary or source.

## Fix direction
Represent proposed, accepted, declined, kept and broken plans, with participants, due time/place and witness/source; use the existing world-model commitment memory rather than another store. A housemate may react only if they heard, witnessed or was told the relevant fact. Promised cooking and picnic contributions should appear when due; missed or conflicting plans should affect trust. Ask for privacy or stage a private move when a nearby resident can hear. Test multi-intent prompts, cross-room knowledge, offscreen telling with provenance, invitation versus confirmed attendee, on-time/missed obligations and save/resume. Pair with BL-30 for authoritative time.

## Why deferred / cautions
The engine already records some extracted commitments; this item targets the remaining user-visible contract and knowledge provenance. Do not infer broken memory solely from a missed answer in one reply. Keep privacy mechanics consistent with BL-27.

## Touches
`backend/app/engine/world_model/commitments.py`, `memory.py`, `turn.py`, prompt projection, extractor and tests.
