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

## Progress and remaining slices (keep current; delete this section when the task ships)

**Claimed** by mvp_chat on 2026-10-02 (4 h; `python scripts/work.py renew P-08`). Work in slices, each a green suite with the
P-03 golden record matching except for the listed intended changes. Push each slice to `beta`; arena gate before the
behaviour-changing slices (2 and 3).

**Slice 1 - DONE (`490505b`, no behaviour change).** `world_model/stances.py` (`Stance`, `StanceBook`, rule parsing with story
overrides, `refresh_stances`, recomputed each turn in `begin_turn` after goal shifts, persisted, old saves load);
`rules/stance_defaults.json` (crush, rival, ally, distrusts, suspects); new conditions `witnessed`, `trait`, `strategy`,
`goal_weight`, `has_stance`, `acquaintance_at_least`, `in_couple`, `eligible`, `event_count.within_days`, and `toward` on
`feeling`/`standing_at_least`/`tier_reached`; 30 tests in `test_stances.py`; `SOCIAL_ENGINE.md` section "Stances". Nothing
reads stances yet.

**Slice 2 - DONE (golden unchanged).** Romance gender tests, intensity, agendas read from `crush` stances, the new stance kinds
(resents, protective_of, owes, ex, admires, as pack data) and the fallout/contest numbers (`social_tracks.tuning`) are all built; see
`SOCIAL_ENGINE.md` "Courtship and intensity". Remaining non-romance gender uses are data enums for the opening
(`opening_scene.GENDER_RULES`) and honorifics (`prompt_builder`), not romance logic.

**Slice 3 - the intended behaviour changes, each with its own test and a golden diff that is explained.**
- Late arrivals get stances like everyone (BL-34 part 2 already ships through `sync_membership`; make it fall out of the rules).
- `next_beat` cadence once a day (BL-37 note).
- NPC initiative gated on acquaintance level and stance (BL-76 b): a day-0 confession is refused.
- The unread `disposition` replaced by stances so non-main characters' attitudes reach the prompt (BL-27 row 13); per
  `SOCIAL_ENGINE.md`, a present person's card also gets their stances toward people in the room.

**Slice 4 - difficulty sweep (was BL-75).** With parity holding, sweep the rival stance weight over seeds 0-11, both genders,
no model calls; record days to the win, whether a rival coupled with the target first, whether the player was cut, and the
passive cut day; pick the value that makes the engaged game harder without slowing the passive cut (allowance 180 days).

**Slice 5 - close.** Docs: `SOCIAL_ENGINE.md`, `CHARACTER_MEMORY.md`; remove or narrow BL-85 P2, the BL-37 note, BL-27 row 13 and
BL-76 (b) in the same commit; delete this file; message ends `Closes P-08`; push; `python scripts/work.py done P-08`; then
ship-and-verify on beta (play the Terrace game, confirm a rival appears and the stances reach the prompt).

**Rules to remember:** a stance reads only the holder's own view (privacy tests exist); never let the LLM write a stance;
commit and push as separate commands; no push during an arena run; Terrace stays configuration only (class C work).

## Open follow-ups from the 2026-10-01/02 session (not P-08 scope; the first live check is also in BL-97)
- Private-aim scene card (P-07) was only checked by unit test; look at one real scene card in the debug view.
- Beta live check after the router fix: 9 of 9 turns ok, one took 75 s (likely a slow model timing out before the router moved
  on; story-master client timeout is 30 s). Run the 10-turn check in BL-97 and look at `data/gemini_router.json`.
- Prod is not on the router yet, so a beta-vs-prod arena can be skewed by prod's own quota failures; report which models answered.
- LLM arena on Gemini + Jev: the smoke run (`gemini-smoke-2`) had only 2 pairs, so every judge said "inconclusive"; a larger
  `gate`/`pilot` run is still to do (needs Gemini quota; do not push during it).
- The five 20-requests-a-day thinking models are spent early in a day of heavy probing; real capacity is the two lite models.

