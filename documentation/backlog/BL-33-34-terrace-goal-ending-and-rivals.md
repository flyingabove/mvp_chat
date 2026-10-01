# Terrace: the goal, its ending, and rivals (remaining evidence work)

The BL-33 offline coverage and the BL-34 rival mechanics shipped 2026-09-30 (as built: `design/SOCIAL_ENGINE.md`,
"Scene recall and visible rivals" and "Leave-together asks, choice cards and plans"). What is left needs more
code for the gaps and real play for the evidence. Plan and checklist below were written before the work started
(2026-09-30, second pass).

## BL-34 — Rivals: hosted evidence and the gaps the fix does not cover
- **Open:** (1) Not yet seen on hosted beta: rivals now start with an aim (`couples.rival_aim`) and compete when the player wins the same person, but no hosted run over several story days has confirmed a visible counter-invitation, competing plan or rival beat with the real storyteller. (2) Residents who arrive later through cast rotation get no seeded aim (`rivals.seed_rival_aims` runs once at world build). (3) The passive-player director cut moved from days 95-135 to 93-156 across six seeded houses with aims (allowance 180); only six houses were measured. (4) The rival beat text is engine-side only; how well the storyteller plays "one small visible move" is unmeasured.

### Engineering plan (BL-34, second pass)
1. **Aims for arrivals.** Failing-first test: a resident who arrives after world build (the cast rotation path, `turn.sync_membership`) and shares the player's gender gets an aim; existing aims are untouched; running it twice adds nothing; a rival whose target left or coupled is re-aimed. Implementation: a public `bootstrap.seed_rival_aims_for_state(state, model)` (the build-time helper made reusable), called at the end of `sync_membership`; `rivals.seed_rival_aims` counts an aim as live only while its target is still in the house and not in a couple.
2. **Pace over 12 houses.** Re-run the passive-player director-cut sweep with seeds 0-11, with and without aims; record the window in the design doc. If any house exceeds the 180-day allowance, lower `rival_aim` or investigate before shipping.
3. **Beat safety.** Test that the rendered rival beat never contains private-thought wording, that a character gets at most one compete beat per in-game day, and that across a scripted 25-turn replay the number of rival beats stays at or below one per rival per day.
4. **Hosted multi-day evidence.** The campaign driver below logs, per story day, any narration that shows a rival's move (an invitation trace such as "invited ... to spend time together", or a same-gender resident seeking the courted person out). Record what was seen; absence is reported as absence.

### Checklist (BL-34, second pass)
- [x] Failing-first arrival-aim tests seen failing
- [x] `seed_rival_aims_for_state` implemented and called from `sync_membership`
- [x] Live-aim rule (target present and not coupled) implemented and tested
- [x] 12-house pass: cut window measured with and without aims. Without aims days 95-136; with aims days 95-173. Every house is inside the 180-day allowance, but seed 0 moved from 135 to 173 (7 days of margin), so the allowance is tight: see the open note below
- [x] Beat-safety tests (no private thoughts, one per day, replay rate). The test found 24 compete beats in 25 turns; fixed with a once-per-day limit
- [ ] Hosted run logs rival evidence per story day; result recorded (driver written, run not done)
- [x] Design doc updated
- **Touches:** `world_model/rivals.py`, `world_model/bootstrap.py`, `world_model/turn.py` (`sync_membership`), tests, `scripts/`.

## BL-33 — Terrace win path on hosted beta
- **Open:** offline, seeded campaigns prove the earned win on both player genders (`test_terrace_campaigns.py`), and `test_terrace_win_paths.py` proves refusal then retry, wording that never changes the verdict, a long skip lapsing an open yes, a withdrawal removing the card, and a prose "yes" on a refusal being replaced. Never seen on hosted beta: the accepted path (mutual relationship, leave-together yes, confirmation, panel ending) and the female-player path with the real storyteller and Jev.

### Engineering plan (BL-33, second pass)
1. **A reusable hosted campaign driver** (`scripts/verify_terrace_win_hosted.py`, no secrets: a guest id like a browser): plays one player gender against a base URL with the real storyteller, extractor and Jev. Per story day it (a) finds the target (a resident of the opposite gender seen in the scene, genders from the repo's story JSON), (b) seeks them out when absent (named address, then rooms in rotation), (c) sends warm, varied, in-character messages the appraisal can tag, (d) confesses once the day count allows and again every few days, (e) reads progress from the response's `goal.status` ("You and X are together"), (f) asks to leave together the day after, (g) answers the choice card with `leave_now`, (h) stops on the ending and prints a compact turn-by-turn log (day, message, whether the verdict/card/status changed, any ending). It never touches operator endpoints and prints the commit it ran against.
2. **Offline tests for the driver's pure parts** (`tests/scripts/test_terrace_campaign_driver.py`): target choice from speakers and genders, status parsing, stop conditions, message variety (no repeat in a row), a scripted fake server proving it reaches the win and respects its day and turn caps.
3. **Run it on hosted beta once per player gender** (separate guest sessions) after the new deploy, in the background, with a hard cap (25 story days, 120 turns) so cost is bounded. Record commit, gender, roster, days, turns, and where it stalled if it did.
4. **Record the evidence honestly:** a win on both genders closes this section; a single win or a stall leaves a smaller section naming exactly what was and was not seen (including whether the real extractor recognised the confession and the ask, which is the "natural-language decision coverage" gap).

### Checklist (BL-33, second pass)
- [x] Driver script written (guest-only, capped, logs commit and per-day progress)
- [x] Offline driver tests pass (target choice, status parsing, caps, fake-server win; they found a driver that never searched for a target)
- [ ] Hosted run, male player: result recorded
- [ ] Hosted run, female player: result recorded
- [ ] Extractor recognition of the confession and the ask noted from the real runs
- [ ] Section deleted if both won, else rewritten to the exact remaining gap
- **Touches:** `scripts/verify_terrace_win_hosted.py`, `tests/scripts/`, evidence in this file.
