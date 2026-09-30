# Test docs and config comments (audit B, 2026-09-30; BL-55 to BL-59 done)

CI (`.github/workflows/tests.yml`), the Dockerfile test gate (`Dockerfile:80-100`), `scripts/run_tests.sh` and `pytest.ini` disagree with each other. Fix them together so one definition of "unit run" and "integration run" exists.

## BL-60 — Test docs and config comments are stale
- **Open:** `pytest.ini:37` example points at `tests/backend/integration/test_location_extractor_e2e.py`, which does not exist. `pytest.ini` setup notes and the `integration` marker text (`pytest.ini:26`, `tests/conftest.py:1-24`, `pytest_configure`) mention only `OPENAI_API_KEY`, but the promise-judge test needs `TYPESAFE_API_KEY`.
- **Next:** Rewrite the header comments and marker descriptions to match the real keys and the new markers from BL-50/BL-51; update `AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md` and `AI_LEARNINGS_WRITING_INTEG_TESTS.md` if they repeat the old text.
- **Touches:** `pytest.ini`, `tests/conftest.py`, the two `ai_learnings_mistakes` docs.
