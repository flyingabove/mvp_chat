---
id: P-08
title: Stances - "considers X a rival", derived from each character's own view
stage: 2
size: L
depends_on: [P-03, P-07]
touches: [backend/app/engine/world_model/stances.py, backend/app/engine/rules/stance_defaults.json, backend/app/engine/rules/conditions.py, backend/app/engine/world_model/agenda.py, backend/app/engine/world_model/rivals.py, backend/app/engine/world_model/act_fallout.py, backend/app/engine/world_model/intentions.py, backend/app/engine/world_model/offscreen.py, backend/app/engine/world_model/model.py]
backlog: BL-85 (P2), BL-82 (fallout), BL-37 (beat cadence), BL-27 (row 13), BL-76 (b)
---
**Goal:** a typed, explainable stance of one character toward another (crush, rival, ally, resents, suspects, protective_of,
owes, distrusts, ex, admires), derived from that character's own feelings, standing, witnessed events and goals, never
written by the LLM. Intentions become the action layer derived from stances.

**Read first:** `documentation/backlog/BL-85-character-social-mind.md` (section 2, phase P2, the "absorbed work" list),
`rules/conditions.py` (closed tri-state language, `Viewpoint`), `world_model/agenda.py`, `rivals.py`, `act_fallout.py`,
`intentions.py`, `offscreen.py`, `heart.py`, and the golden record from P-03.

**Build**
- `Stance(kind, target, about?, strength, cause_ids, since_day)` and `StanceBook` on `WorldModel` (persisted, recomputed
  each turn, old saves load). Rules live in `rules/stance_defaults.json` (a generic pack; stories override); each is a
  weighted sum of conditions judged from the holder's `Viewpoint`; `strength` is that sum; every stance records its cause ids.
- New closed condition kinds (each with `explain()` and parser validation): `trait`, `strategy`, `goal_weight`,
  `has_stance`, `witnessed`, `acquaintance_at_least`, `in_couple`, `eligible` (replaces every gender check), plus
  `event_count.within_days`; role names `holder | subject | third`.
- Move the hand-coded paths onto stances with **no behaviour change**: rival seeding (`rivals.py`), `compete_for`
  derivation (`agenda.refresh_agendas`), fallout constants (`act_fallout.py`), the rival blocks in `intentions.py` and
  `offscreen.py`. Delete the 19 `genders.get` / `player_gender` sites in favour of `eligible`.
- Intended changes, each with its own test: late arrivals get stances like everyone (BL-34 part 2 is already shipped
  through `sync_membership`; make it fall out of the rules), the `next_beat` cadence once-a-day (BL-37 note), NPC
  initiative gated on acquaintance level and stance (BL-76 b: a day-0 confession is refused), the unread `disposition`
  replaced by stances so non-main characters' attitudes reach the prompt (BL-27 row 13).
- **Difficulty sweep (was BL-75):** with parity holding, sweep the rival stance weight over seeds 0-11, both genders, no
  model calls; record days to the win, whether a rival coupled with the target first, whether the player was cut, and the
  passive cut day; pick the value that makes the engaged game harder without slowing the passive cut (allowance 180 days).

**Tests first:** the golden record from P-03 still matches except for the listed intended changes; rule unit tests (tri-state,
privacy: remove a witness and a stance changes, change a hidden feeling and it does not); parser validation.

**Done when:** suite green, golden diff explained, design docs updated (`SOCIAL_ENGINE.md`, `CHARACTER_MEMORY.md`), BL-85 P2,
the BL-37 note, BL-27 row 13 and BL-76 (b) removed or narrowed in the same commit. Arena gate before shipping behaviour changes.
