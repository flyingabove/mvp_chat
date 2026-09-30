# BL-35 — Social plans, invitations and knowledge need reliable follow-through

- **Type:** bug / feature
- **Found:** 2026-09-25, manual Terrace play
- **Severity:** medium; agreed plans and trust changes feel arbitrary without an agreed-state record.

## Problem
In [Terrace turns 3 and 5](../archive/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md), the player proposed a next-day cooking lesson; the initial question was dropped on a room transition, then Misaki later accepted. Turn 9 staged the lesson in prose but the world clock was wrong (BL-30). Turn 7 assigned picnic duties; turn 10 Misaki declared herself "definitely in" although the player asked whether she had heard of it, without showing how she learned. Masako answered a quiet aside in turn 5 although the player asked for privacy while she was nearby. None proves remote knowledge leakage, but the experience gives no clear boundary or source.

## Fix direction
Represent proposed, accepted, declined, kept and broken plans, with participants, due time/place and witness/source; use the existing world-model commitment memory rather than another store. A housemate may react only if they heard, witnessed or was told the relevant fact. Promised cooking and picnic contributions should appear when due; missed or conflicting plans should affect trust. Ask for privacy or stage a private move when a nearby resident can hear. Test multi-intent prompts, cross-room knowledge, offscreen telling with provenance, invitation versus confirmed attendee, on-time/missed obligations and save/resume. Pair with BL-30 for authoritative time.

## Why deferred / cautions
The engine already records some extracted commitments; this item targets the remaining user-visible contract and knowledge provenance. Do not infer broken memory solely from a missed answer in one reply. Keep privacy mechanics consistent with BL-27.

**Further implementation (2026-09-26):** Canonical agreement proposal, decision, due, completion and expiry records now back legacy promise memories. Due scenes alone do not complete a plan; NPC dialogue about an action remains testimony. Missed accepted plans emit an expiry consequence. Speech observations and gossip transmissions retain their hearing/source path. Remaining: typed witnessed NPC actions, per-participant attendance and breach evidence, schedule/travel validation, privacy movement and full same-turn invitation extraction.

**Hosted recurrence (2026-09-27, beta `9db4b8f`):** Natsumi verbally accepted Paul’s coffee invitation for the next morning at 10 am and remembered it at 9 am. At 10 am Paul was alone in the cafe; no arrival, cancellation, alternate meeting instruction or breach consequence appeared. The preceding compound travel/wait parsing was also wrong (see BL-30), but an explicit second wait reached 10 am and still left the cafe empty. Acceptance must lead to a scheduled participant/place decision or explicitly remain a proposal; the player should not be left with a verbal promise and no event. Raw ten-turn replay is in the local `beta-replay-2026-09-27` artifact folder and the dated reference report.

## Touches
`backend/app/engine/world_model/commitments.py`, `memory.py`, `turn.py`, prompt projection, extractor and tests.

**Promise rework (2026-09-29, live on beta `eb4cae1`; design in [PROMISE_COMPLETION_JEV](../proposals/PROMISE_COMPLETION_JEV_2026_09_29.md)):** a due promise is raised once (`Memory.reminded`); the old word-overlap completion check is deleted; Jev judges whether an open promise between people who are present was carried out (`world_model/promise_judge.py`, on by default, 0.6-1.2% missed kept promises against a 2% gate that runs as an integration test, remainder in [BL-45](BL-45-promise-judge-remaining-misses.md)). Live: the tea, coffee and breakfast handovers registered as kept and nothing nagged. Invited moves ("Minori, come with me to the cafe") now take the invitee along (`companions.py`). **Design change to note:** this item's fix direction wanted missed plans to affect trust, but a promise-derived plan that lapses now expires silently, because nothing can prove it went unkept and the owner's rule is that the game must never register a kept promise as broken. Still open: scheduled arrival at a promised time and place (a verbal "coffee tomorrow at 10" still leaves the cafe empty unless the player invites at that moment), typed witnessed NPC actions, privacy movement.
