AI learnings: running tests on this repo
=======================================

> **What this doc is for:** How to run tests correctly in this repo (pytest flags, common pitfalls). Edit this doc when test runner behavior changes or new testing patterns are established.

POLICY: NO TESTS MAY BE SKIPPED — EVER
---------------------------------------
All tests in `tests/` must run and pass in every environment (local, CI, Railway).
pytest.skip(), @pytest.mark.skip, and @pytest.mark.skipif are BANNED.
The conftest.py hook converts any skip attempt into a hard FAILURE.
If a test needs an API key, the key MUST be available — never gate on it.

XFAIL POLICY (STRICT ALLOWLIST)
-------------------------------
- `xfail` is permitted only for explicitly quarantined tests in the conftest allowlist.
- Current allowed xfail is controlled only by `tests/conftest.py` allowlist.
- Any additional `xfail` marker outside allowlist is treated as a policy violation at collection time.
- If you add or modify any xfail quarantine, document the rationale in the PR and keep the allowlist in `tests/conftest.py` synchronized.

Context
- OS: Windows (PowerShell terminals). Environment: conda env at C:\Users\Christian\Miniconda3.
- .env.test exists and is auto-loaded by tests/conftest.py; it provides OPENAI_API_KEY.
- Integration playback scenarios are discovered through the integration playback loader and canonical test modules under `tests/backend/app/**`.
- Railway must have OPENAI_API_KEY set as an environment variable.

Commands that reliably work
1) Full suite (default — run everything, always)
   python -m pytest tests/ -v
   Expected: full suite passes, 0 skipped.

2) Quick run
   python -m pytest tests/ -x -q
   Expected: stops on first failure.

3) Via conda/VSCode wrapper (if needed)
   C:/Users/Christian/miniconda3/Scripts/conda.exe run -p C:\Users\Christian\Miniconda3 --no-capture-output python c:\Users\Christian\.vscode\extensions\ms-python.python-2026.0.0-win32-x64\python_files\get_output_via_markers.py -m pytest -v

4) Integration tests only
   python -m pytest tests/ -m integration -v

Pitfalls observed
- Plain `conda run ... pytest -m "not integration"` from PowerShell often failed due to quoting; the get_output_via_markers wrapper avoided this.
- Background runs with redirection sometimes produced empty logs; prefer foreground with the commands above.
- KeyboardInterrupts were seen when commands were re-invoked mid-run; wait for completion or rerun cleanly.
- NEVER add pytest.skip() to any test — the conftest hook will convert it to a failure.

Pre-flight checklist before running
- Ensure .env.test exists with OPENAI_API_KEY (already present) or set env var directly.
- If running on Railway/CI, ensure OPENAI_API_KEY is set as an environment variable.
- If scenarios are missing, confirm integration playback loader paths and scenario registration imports are reachable from canonical test modules.

Reminder
- Read this note before running tests. If a command fails, re-use the exact working forms above.
- NEVER skip tests. Fix the test or fix the environment.

## Async tests need an explicit `@pytest.mark.asyncio` (2026-09-23)

The root `pytest.ini` sets `asyncio_mode = auto`, but the Dockerfile copies only
`backend/ frontend/ tests/ scripts/`, so the Railway build-time test gate runs WITHOUT
it (strict mode). Unmarked `async def test_*` pass locally and fail in the build
("async def functions are not natively supported"), which blocks the deploy.
Always decorate async tests with `@pytest.mark.asyncio`, and reproduce the build
condition locally with: `python -m pytest <path> -c /dev/null --rootdir .`

- 2026-09-24: The outbox completion regression must keep `TestClient` open as a
  context manager while polling. Without it, Starlette closes the per-request
  event loop and cancels extraction before the poll starts. Preserve the real
  background task and database transition; do not skip the test or force-mark
  the outbox row done.
