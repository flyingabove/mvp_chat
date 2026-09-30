# CI and Docker test configuration (audit B, 2026-09-30)

CI (`.github/workflows/tests.yml`), the Dockerfile test gate (`Dockerfile:80-100`), `scripts/run_tests.sh` and `pytest.ini` disagree with each other. Fix them together so one definition of "unit run" and "integration run" exists.

## BL-55 — Integration job condition is invalid
- **Open:** `tests.yml:43` uses `if: ${{ secrets.OPENAI_API_KEY != '' }}` at job level. The `secrets` context is not available in a job-level `if`, so the workflow is rejected or the job never runs as intended.
- **Next:** Map the secret into a job-level `env` and gate with a first step (`if: env.OPENAI_API_KEY != ''`), or drop the condition and use `workflow_dispatch` (see BL-57). Validate the file with `actionlint`.
- **Touches:** `.github/workflows/tests.yml`.

## BL-56 — CI integration job lacks the Jev key
- **Open:** The job passes only `OPENAI_API_KEY` (`tests.yml:59`), but `tests/backend/integration/test_promise_judge_accuracy.py` needs `TYPESAFE_API_KEY`. It would fail in CI. `pytest -m integration -v` also has no path, so it collects every marked test.
- **Next:** Pass `TYPESAFE_API_KEY` from secrets; select the integration tests explicitly (`pytest tests/backend/integration -m integration`) once BL-50 has cleaned up markers.
- **Touches:** `.github/workflows/tests.yml`.

## BL-57 — Paid integration tests run on every push and PR
- **Open:** The integration job triggers on every push and pull request to `beta` and `prod`, which spends LLM money on each deploy (the thing the owner wants to avoid). Fork PRs do not receive secrets, so it also behaves differently per author.
- **Next:** Move the integration job to `workflow_dispatch` plus an optional nightly `schedule`; leave the unit job on push/PR. Document how to trigger it in `AI_LEARNINGS_RUNNING_TESTS.md`.
- **Touches:** `.github/workflows/tests.yml`, `documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md`.

## BL-58 — CI unit job and Docker gate differ
- **Open:** CI adds a redundant `--ignore=tests/backend/integration/` (the marker already deselects it); the Dockerfile does not. CI does not blank `OPENAI_API_KEY` / `TYPESAFE_API_KEY` / `LANGSMITH_API_KEY` / `LANGCHAIN_API_KEY`, so a leaked key would make CI hit the network. CI lacks `--continue-on-collection-errors` and `-ra`, so failures show differently.
- **Next:** Extract one command (a `scripts/run_unit_tests.sh` or a shared make target) used by CI, the Dockerfile and local runs: `-m "not integration"`, blank keys, `TESTS_BLOCK_LLM_NETWORK=1`, `--disable-warnings --tb=short -ra`.
- **Touches:** `.github/workflows/tests.yml`, `Dockerfile`, `scripts/run_tests.sh`.

## BL-59 — `scripts/run_tests.sh` runs the wrong set
- **Open:** It runs `pytest tests/backend` with no marker filter, so with keys set it runs the paid tests, and it skips `tests/frontend` and `tests/scripts`.
- **Next:** Point it at the shared command from BL-58 (all of `tests/`, `-m "not integration"`), and add the Node step from BL-53.
- **Touches:** `scripts/run_tests.sh`.

## BL-60 — Test docs and config comments are stale
- **Open:** `pytest.ini:37` example points at `tests/backend/integration/test_location_extractor_e2e.py`, which does not exist. `pytest.ini` setup notes and the `integration` marker text (`pytest.ini:26`, `tests/conftest.py:1-24`, `pytest_configure`) mention only `OPENAI_API_KEY`, but the promise-judge test needs `TYPESAFE_API_KEY`.
- **Next:** Rewrite the header comments and marker descriptions to match the real keys and the new markers from BL-50/BL-51; update `AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md` and `AI_LEARNINGS_WRITING_INTEG_TESTS.md` if they repeat the old text.
- **Touches:** `pytest.ini`, `tests/conftest.py`, the two `ai_learnings_mistakes` docs.
