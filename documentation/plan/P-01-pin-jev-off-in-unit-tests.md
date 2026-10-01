---
id: P-01
title: Pin Jev off in unit tests so the suite is green on every machine
stage: 0
size: S
depends_on: []
touches: [tests/conftest.py, documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md]
backlog: BL-79
---
**Why:** on a machine whose `.env.test` sets `TYPESAFE_API_KEY` and `TYPESAFE_ENABLED`, a normal turn makes a second
(Jev) HTTP post, so four tests fail locally (`test_debug_mode_toggle_no_llm_on_toggle_and_appends_debug_box`,
`test_debug_toggle_strips_leading_gt`, `test_six_strangers_prompt_states_whereabouts_and_never_names_unarrived_residents`,
and one in `test_location_extractor.py`). CI and Railway are fine. Every later task needs a reliably green suite.

**Read first:** `documentation/backlog/BL-79-prompt-engine-llm-call-count-tests.md` (the root cause is already found),
`backend/app/config/settings.py` (`is_typesafe_enabled`), `tests/conftest.py`.

**Build**
- Failing test first: with `TYPESAFE_ENABLED=true` and a fake key in the environment, a normal turn in a unit test still
  makes exactly one storyteller post (add it as a guard test that fails today).
- In `tests/conftest.py`, force Jev off for every test that is not marked `integration`
  (clear `TYPESAFE_API_KEY`, set `TYPESAFE_ENABLED=false`, drop `JEV_ENABLED_TASKS`), the same way `_block_llm_hosts` blocks
  LLM hosts. `integration` tests keep their real settings.
- Add the `TYPESAFE_*` variables to the documented gate command in `AI_LEARNINGS_RUNNING_TESTS.md`.

**Done when:** the full suite passes locally with a populated `.env.test`, and with blank keys; the four failing tests
pass; integration tests still reach Jev when selected.

**Closes** BL-79 (delete its file in the fixing commit).
