# Terrace: the goal, its ending, and rivals

## BL-34 — Same-gender housemates do not visibly compete
- **Open:** a rival only states interest when asked directly ("Yeah, a bit", hosted 2026-09-29, two rosters checked). No counter-invitation, competing plan or visible rival state in about three story days.
- **Causes found by code reading (2026-09-30):**
  1. `agenda.refresh_agendas` creates `compete_for` only when two NPCs are both drawn to the same target (`len(admirers) >= 2` over NPC owners). The player is never counted as an admirer, so a rival never competes with the player, whatever the player achieves with the target.
  2. NPC-to-NPC standing starts at 0 and only rises through off-screen encounters, so in ~3 days no rival is drawn to anyone and there is nothing to compete with: rivals have no independent aim.
  3. `agenda.next_beat` only surfaces intentions aimed at the player (`test_loyalty`, `pursue`), so even a real `compete_for` gives no visible beat; only an invitation (`intentions.propose_agenda_invitations`, needs rival and target co-present with the player) makes it visible.

### Engineering plan (BL-34)
1. **Failing-first tests** (`tests/backend/app/engine/world_model/test_rivals.py`): (a) target X reached the interested tier toward the player and rival R is drawn to X -> R holds `compete_for X`; (b) R present with X -> `next_beat` returns R's compete beat and the directive names both; (c) after seeding, every same-gender resident holds a `pursue` on day 0.
2. **Count the player as an admirer** in `refresh_agendas`: a target whose own standing toward the player reached the interested tier, who is eligible, not closed to the player and not in an NPC couple, is "courted"; NPC admirers of a courted target get `compete_for`. The player never gets an agenda entry.
3. **Independent rival aims** (`world_model/rivals.py`, `seed_rival_aims`), opt-in by story config. *Plan change while implementing:* the plan seeded an initial standing, but the Terrace "interested" tier has event gates and a floor of 45, so a faked standing would be an invented feeling and might not count. The aim is instead a long-lived `pursue` intention (`AIM_DAYS`) on a deterministic, seed-chosen opposite-gender resident, configured as `social_tracks.couples.rival_aim` (0-1, Terrace 0.3), and `refresh_agendas` treats a live `pursue` aim as "drawn to" so an overlap with the player's choice becomes `compete_for`.
4. **Visible beat:** `next_beat` also offers `compete_for` when the target is in the scene; `BEAT_TEXT["compete_for"]` allows ONE small visible move and no confession or private thoughts; `begin_turn` formats `{target}`.
5. **Do not break pacing:** seeded campaigns still pass on both genders; the passive cut is measured across seeded houses with and without aims.
6. **Roster matrix tests:** both player genders; no interested rival; two rivals on one target; mutual interest; rejection (closed track); cast rotation (departed rival); already-coupled rival or target.
7. **Docs:** `design/SOCIAL_ENGINE.md` and the story-schema note for `rival_aim`.

### Checklist (BL-34)
- [x] Failing-first tests (a), (b), (c) seen failing (import/behaviour errors before the code existed)
- [x] Player counted as an admirer; taken and rejecting targets excluded; player never gets an agenda
- [x] `CouplePolicy.rival_aim` parsed and validated; Terrace sets 0.3
- [x] `seed_rival_aims` implemented, deterministic, opt-in, wired in `build_world_model`
- [x] `next_beat` + `BEAT_TEXT["compete_for"]` + `{target}` formatting; real-turn test reaches the storyteller
- [x] Roster matrix tests (both genders, none, two rivals, mutual, rejection, rotation, coupled)
- [x] Real-bootstrap test: every same-gender resident starts with an aim, both genders
- [x] Seeded campaigns still pass on both genders; passive cut measured on six houses: days 95-135 before, 93-156 after (allowance 180)
- [x] Docs updated
- [ ] Hosted multi-day rival observation with the real storyteller (kept open below)
- [ ] Aims for residents who arrive later through cast rotation (kept open below)
- **Touches:** `world_model/agenda.py`, `world_model/rivals.py`, `world_model/bootstrap.py`, `world_model/turn.py`, `rules/tracks.py`, `six_strangers_story.json`, tests.

## BL-33 — Terrace: the relationship goal and its ending are not proven end to end
- **Open:** the goal shows on the card and chat banner, and early confessions or "leave together" asks are refused with no false win (hosted, 2026-09-29). Never seen on hosted beta: the accepted path (mutual relationship, both leave, panel ending) and the female-player path. Offline seeded campaigns prove the earned win on both player genders (`test_terrace_campaigns.py`, now through the BL-46 choice card). Missing: natural-language decision coverage, explicit refusal and coercion cases, reload and long-skip scenarios. Leaving alone is no longer an ending (BL-46); no regex win detector, no silent time limit.
- **Depends on:** BL-34 (rivals) and BL-35 (plans).

### Engineering plan (BL-33)
What can be proven offline, deterministically, in this change (`tests/backend/app/api/test_terrace_win_paths.py`, campaign fixture):
1. **Refusal then retry** on both player genders: a `not_yet` ask sets the cooldown; the same-day re-ask is refused by the hard rule (no card); after a day the ask with enough standing opens the card and the win plays.
2. **Wording never changes the verdict (coercion):** the polite and the coercive wording give identical outcomes; pressure never raises standing or skips a rule.
3. **Long skip over an open card:** a `DAY` skip lapses the yes; answering it afterwards continues the scene.
4. **Relationship ended while the card is open:** withdrawing removes the card in the same response (*engine change while implementing:* `end_turn` now refreshes the card so a lapsed yes leaves the response at once and the storyteller is told next turn).
5. **Explicit refusal in prose:** a storyteller "yes" on a `not_yet` turn is replaced before display, through `/api/chat`.
6. **Still needs real play:** a hosted 20-turn campaign per player gender that earns the win with the real storyteller and Jev. It cannot be forced (standing needs days of real behaviour), so it stays open as evidence to collect.

### Checklist (BL-33)
- [x] Refusal-then-retry test, both genders
- [x] Coercion-wording invariance test
- [x] Long-skip-over-open-card test
- [x] Relationship-ended-while-card-open test (and the same-response card removal)
- [x] Prose-yes-on-not_yet repair test through `/api/chat`
- [ ] Hosted accepted-path campaign (male and female player) run and recorded (kept open below)
- **Touches:** tests, `world_model/turn.py` (`end_turn` card refresh).
