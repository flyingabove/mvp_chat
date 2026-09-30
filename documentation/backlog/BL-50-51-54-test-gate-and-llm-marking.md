# Test gate and LLM marking (audit A, 2026-09-30; BL-52 and BL-53 done)

Audit of `tests/` on 2026-09-30: 1,531 unit tests pass in about 100 s; 13 are deselected as `integration`. The deploy gate itself is sound (Dockerfile runs `-m "not integration"` with blank keys and `TESTS_BLOCK_LLM_NETWORK=1`; `tests/conftest.py` `_block_llm_hosts` fails any test that resolves an LLM host). The problems are labelling and what sits outside the gate.

## BL-50 — `integration` marker: remaining cleanup
- **Open:** 2026-09-30 fixed the mislabels (A12 concurrency test and the epistemic/retrieve tests now run in the deploy gate). Still open: `tests/backend/app/knowledge/test_hybrid.py::test_character_hybrid_retrieval_recall_threshold` needs the real SentenceTransformer (11 s), not an LLM, yet is marked `integration` only to keep it out of deploys. The `integration` marker text (`pytest.ini`, `tests/conftest.py` `pytest_configure`) still says "requires API keys".
- **Next:** Decide whether "slow/real-model" gets its own marker and deselect it in the gate; else leave hybrid as `integration`. Reword the marker to "calls a real LLM (or a real model)". Add a conftest collection check that every `integration` test references a key or is on an allowlist, so a mislabel fails at collection.
- **Touches:** `pytest.ini`, `tests/conftest.py`, `tests/backend/app/knowledge/test_hybrid.py`.

## BL-51 — The promotion-gate scoring is not a pytest integration test
- **Open:** The beta-to-prod and local-to-beta scoring (arena: `precheck`, `gate` profile, Jev/OpenAI/Ollama judges) lives in `.claude/skills/promote-to-prod/` and runs only through `arena_cli.py` behind `ARENA_LLM_ENABLED=1`. It returns exit codes and writes `precheck.json` / `gate.json`, but nothing under `pytest -m integration` runs or asserts it. Only the promise-judge eval (`scripts/eval/promise_judge_eval.py`) is already an integration test.
- **Next:** Add `tests/backend/integration/test_arena_gate.py`, marked `integration` (plus an opt-in `arena_live` marker for the Ollama and paid parts). It bootstraps `sys.path` to the skill directory, requires `ARENA_LLM_ENABLED=1`, `OPENAI_API_KEY`, `TYPESAFE_API_KEY` and a reachable Ollama (missing prerequisites FAIL with a clear message; skips are banned), calls `arena.cli.precheck` / `tiered` with a tmp root and pinned `--baseline-ref`, and asserts `precheck.json["passed"]` and `gate.json["passed"]`. Keep it OUT of the CI integration job (CI cannot supply Ollama or git refs). Precheck takes about 15 min and the hosted gate spends real money, so it must never run in deploys. Owner decision needed: this touches the 2026-09-25 "arena LLM runs disabled" rule, so the wrapper keeps the flag requirement. Update `promote-to-prod/SKILL.md` and `AI_LEARNINGS_RUNNING_TESTS.md` to say the gate is "one of the integ tests".
- **Touches:** new `tests/backend/integration/test_arena_gate.py`, `pytest.ini` (marker), `.claude/skills/promote-to-prod/SKILL.md`, `documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md`.

## BL-54 — IU identity xfail can never fail
- **Open:** `test_prompt_engine.py::test_iu_identity_correction` is `xfail(strict=False)` and needs `OPENAI_API_KEY`, so a regression is invisible either way. (The `importorskip` calls were removed 2026-09-30.)
- **Next:** Make it a repeated-trial pass-rate assertion (integration only) or delete it; drop it from `_ALLOWED_XFAIL_NODEIDS` in `tests/conftest.py` if removed.
- **Touches:** `tests/backend/app/api/test_prompt_engine.py`, `tests/conftest.py`.
