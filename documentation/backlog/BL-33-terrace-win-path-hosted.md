# Terrace: the win path on hosted beta

Offline coverage (BL-33) and the rival mechanics with late-arrival aims and beat limits (BL-34) shipped 2026-09-30;
as built: `design/SOCIAL_ENGINE.md`, "Scene recall and visible rivals" and "Leave-together asks, choice cards and
plans". BL-34's remaining hosted evidence (rivals visibly competing over several story days) became an acceptance
check of the headless season (BL-86); its pace margin became the P-08 difficulty sweep (done; rival pressure BL-98 shipped 2026-10-10, see `design/SOCIAL_ENGINE.md`).

## BL-33 — Terrace win path on hosted beta
- **Bucket:** A (verification run)
- **Open:** offline, seeded campaigns prove the earned win on both player genders (`test_terrace_campaigns.py`, `test_terrace_win_paths.py`). Never seen on hosted beta: the accepted path (mutual relationship, leave-together yes, confirmation, panel ending) and the female-player path with the real storyteller and Jev. The capped, guest-only driver `scripts/verify_terrace_win_hosted.py` and its offline tests (`tests/scripts/test_terrace_campaign_driver.py`) exist; the runs were done on 2026-10-11 against beta `82d39ec` (guest, 25-day and 120-turn caps, both genders) and neither won: the driver ended at turn 97 (day 9 to 10) with the target speaking in the player's scene on only 6 of 97 turns (male) and 12 (female); the female run confessed on day 9 and got no leave-together card. The blocker is finding the resident (BL-72), not the confession path, which the offline campaigns prove.
- **Next:** fix BL-72 (a player-facing way to find a resident) or make the driver ask where the target is, then repeat both runs and record whether the real extractor recognised the confession and the ask. Delete this section if both won. The Drama Theatre or the season runner may replace manual hosted playing (see `documentation/plan/ORDER.md`, where these runs are off the critical path).
- **Touches:** `scripts/verify_terrace_win_hosted.py`, evidence in this file.
