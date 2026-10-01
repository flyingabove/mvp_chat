# Terrace: the win path on hosted beta

Offline coverage (BL-33) and the rival mechanics with late-arrival aims and beat limits (BL-34) shipped 2026-09-30;
as built: `design/SOCIAL_ENGINE.md`, "Scene recall and visible rivals" and "Leave-together asks, choice cards and
plans". BL-34's remaining hosted evidence (rivals visibly competing over several story days) became an acceptance
check of the headless season (BL-86); its pace margin became the BL-85 difficulty sweep.

## BL-33 — Terrace win path on hosted beta
- **Open:** offline, seeded campaigns prove the earned win on both player genders (`test_terrace_campaigns.py`, `test_terrace_win_paths.py`). Never seen on hosted beta: the accepted path (mutual relationship, leave-together yes, confirmation, panel ending) and the female-player path with the real storyteller and Jev. The capped, guest-only driver `scripts/verify_terrace_win_hosted.py` and its offline tests (`tests/scripts/test_terrace_campaign_driver.py`) exist; the runs have not been done.
- **Next:**
  - [ ] Hosted run, male player (cap 25 story days, 120 turns): result recorded
  - [ ] Hosted run, female player: result recorded
  - [ ] Note whether the real extractor recognised the confession and the ask
  - [ ] Delete this section if both won, else rewrite it to the exact remaining gap
- **Touches:** `scripts/verify_terrace_win_hosted.py`, evidence in this file.
