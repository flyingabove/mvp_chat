AI learnings: integration test requirements
==========================================

Context
- OS: Windows (PowerShell terminals). Python via conda env at C:\Users\Christian\Miniconda3.
- .env.test is auto-loaded by tests/conftest.py; must contain OPENAI_API_KEY for integration tests that touch LLM/extractor flows.
- Integration playback scenarios are auto-registered and run through ScenarioRunner from canonical test modules.
- Railway deploy logging switch: `DEBUG_MODE` must be set to string `TRUE` to emit Docker build/runtime debug blocks; any other value (including `FALSE`) suppresses verbose startup diagnostics.

Technical requirements (numbered)
1) Environment
   - Use the configured conda env at C:\Users\Christian\Miniconda3.
   - Run from repo root (C:\Users\Christian\Documents\Projects\mvp_chat).
   - Ensure .env.test exists with OPENAI_API_KEY; alternatively set env var directly.

2) Commands that work (foreground)
   1. Full suite: python -m pytest
      - Expected: all tests (unit + integration) ~50s.
   2. Integration-only: python -m pytest -m integration -r s
      - Uses .env.test OPENAI_API_KEY.
   3. Unit-only: python -m pytest -m "not integration" -r s
      - No API key needed.
   - Use the vscode get_output_via_markers wrapper if quoting breaks in PowerShell (see AI_LEARNINGS_RUNNING_TESTS.md for exact command forms).

3) Scenario message formatting
   - Chat outputs must carry a single role tag per message block ([USER] or [LLM]), not per sentence.
   - Keep multi-line narrative blocks intact (preserve newlines and ">" prompts); typewriter rendering is shared between game and integration playback.
   - Role mapping: player_role -> [USER]; all other speakers -> [LLM].

4) Debug box expectations (shared code)
   - Use the shared debug_box renderer (no custom integration-only code).
   - Keys shown: timestamp, location, location_id, minute, story, scenario, speakers (auto-built from player_role + belief keys), plus any extra payload.
   - Same debug payload should render identically in both game and integration playback.

5) Epistemic integration specifics
   - Use IntegrationScenario helpers (say_user, say_llm, debug_info) so role tags are consistent.
   - Claims/observations/confessions logged via state methods; contested/resolved statuses must be asserted in tests.
   - Multi-turn dialogue should mirror the canonical script (denials -> observations -> contradictions -> confessions) with formatting unchanged from the game view except for role tags.

6) Class structure and execution
    - Integration scenarios should subclass IntegrationScenario with scenario_id/title/description/tags/player_role set.
    - Steps must be methods decorated with @step(kind="action"/"assert"/etc.), relying on get_steps ordering; no ad-hoc invocation.
    - Use run_as_test() as the pytest entry point so class-based scenarios execute via ScenarioRunner (same path as playback UI).
   - Registration is automatic via __init_subclass__ and scenario_registry; keep scenario modules importable from the canonical test tree.
    - Step outputs must return chat payloads (say_user/say_llm) and debug_info; avoid custom printing or bespoke debug formats.

6) Pitfalls and reminders
   - Quoting in PowerShell can break direct pytest calls; prefer the documented wrapper if commands fail.
   - Background runs with redirection can drop output; run foreground for reliable logs.
   - If scenarios do not appear, ensure ensure_scenarios_loaded runs and scenario registry import paths are correct.

Pre-flight checklist
- Confirm OPENAI_API_KEY available (.env.test loaded automatically).
- Run from repo root with the commands above.
- Expect role-tagged blocks and shared debug boxes; if format drifts, adjust IntegrationScenario/renderer, not ad-hoc in tests.

---

7) Multi-run scoring framework (non-deterministic LLM tests)
------------------------------------------------------------
LLM-backed integration tests are inherently non-deterministic. A single pass/fail verdict is unreliable.
Use the multi-run framework to run N times, score each run, and assert that at least one run passed.

### Global constants (backend/app/config/settings.py)
```
LOCAL_INTEG_RUN_COUNT: int = 5    # X — runs when no RAILWAY_* env vars are set (local dev)
PROD_INTEG_RUN_COUNT: int = 5     # Y — runs when on Railway (RAILWAY_ENVIRONMENT or RAILWAY_PROJECT_ID set)
```
These are the ONLY source of truth for run counts. Never hardcode run counts in scenario files.

### Opt-in: set multi_run = True on your scenario class
```python
class MyScenario(IntegrationScenario):
    scenario_id = "my_scenario"
    multi_run = True   # ← opt-in; default is False (single-run, original behavior)
    ...
```

### Score tiers (convention)
- **100** — Best outcome: criterion met explicitly (e.g. IU's own dialogue says she is the previous tenant)
- **50**  — Partial: criterion met only indirectly/poetically (e.g. narration implies it, dialogue stays evasive)
- **0**   — Failure: no criterion met at all, or actively wrong

Call `self.record_score(score)` from your assert step BEFORE asserting, so the score is captured even on failure:
```python
@step(kind="assert", description="Assert verdict")
def assert_verdict(self):
    score = self.state.score       # set by evaluate_* step (100, 50, or 0)
    self.record_score(score)       # ALWAYS call this first
    assert score > 0, f"Score was {score}"
```

### Pass condition
`assert any(s > 0 for s in cls._score_history)` — the scenario passes if AT LEAST ONE run scored > 0.
If ALL N runs score 0 the test fails. This tolerates occasional failures in non-deterministic LLM tests.

### Score report
After every multi-run scenario completes, a formatted report is printed to stdout automatically:
```
╔══════════════════════════════════════════════════════════════════╗
║  INTEGRATION SCORE REPORT                                        ║
║  Scenario: <title>                                               ║
║  Runs: 5  (local)                                                ║
╠══════════════════════════════════════════════════════════════════╣
║  Score Distribution:                                             ║
║  100 (explicit identity    ):  ██████░░░░  3/5  (60.0%)          ║
║   50 (poetic narration     ):  ██░░░░░░░░  1/5  (20.0%)          ║
║    0 (no connection        ):  ██░░░░░░░░  1/5  (20.0%)          ║
╠══════════════════════════════════════════════════════════════════╣
║  Individual Scores:  [100, 100, 50, 0, 100]                      ║
║  Total Score:  350 / 500  (70.0%)                                ║
╚══════════════════════════════════════════════════════════════════╝
```
Railway captures stdout to deployment logs. pytest -s shows it locally.

### AI reporting rule (IMPORTANT)
**After running any multi-run integration test, read the full `╔══ INTEGRATION SCORE REPORT` block
from stdout and report it verbatim to the user.** Include: individual scores, distribution per tier,
and total score %. Do NOT just report pass/fail — give the full distribution.

### Checklist: adding a new multi-run scenario
1. Set `multi_run = True` on the scenario class
2. Add an `evaluate_*` step that scores 100/50/0 and stores to `self.state.score`
3. Add an `assert_verdict` step that calls `self.record_score(self.state.score)` THEN asserts
4. Score tiers must match the 100/50/0 convention (no other values)
5. Do NOT call `record_score()` more than once per run
6. Run count is controlled globally via `LOCAL_INTEG_RUN_COUNT` / `PROD_INTEG_RUN_COUNT` — never hardcode

### Implementation files
- `backend/app/config/settings.py` — `LOCAL_INTEG_RUN_COUNT`, `PROD_INTEG_RUN_COUNT`
- `backend/app/integration_playback/scenario.py` — `_integ_run_count()`, `_print_score_report()`, `record_score()`, `run_as_test()` multi-run path
- `tests/backend/app/config/test_settings.py` — tests for constants
- `tests/backend/app/integration_playback/test_multi_run.py` — unit tests for `_integ_run_count()` and `record_score()`
