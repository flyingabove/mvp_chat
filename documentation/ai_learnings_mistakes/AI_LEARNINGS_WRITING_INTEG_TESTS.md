How to write a new integration test
====================================

> **What this doc is for:** Step-by-step guide for writing new integration tests. Edit this doc when the integration test framework, patterns, or requirements change.

This document is the authoritative guide for writing and running integration tests
in this project. Read this before creating any new integration test scenario.

---

## Quick overview

Integration tests in this project are **class-based scenarios** that run through
the full FastAPI app stack (real HTTP, real session state, real LLM calls when needed).
They live under `backend/app/integration_playback/scenarios/` and are registered
automatically. The entry point is always a tiny pytest function in
`tests/backend/app/api/test_prompt_engine.py` that calls `MyScenario.run_as_test()`.

---

## When to write an integration test (not a unit test)

Write an integration test when you need to verify:
- End-to-end behavior through the `/api/chat` HTTP endpoint
- LLM output quality (non-deterministic — use multi-run mode)
- Interaction between multiple subsystems (prompt builder + session + extractor)
- A scenario that cannot be mocked without losing the thing you are testing

Write a unit test for everything else.

---

## File locations

| Type | Location |
|------|----------|
| Scenario class | `backend/app/integration_playback/scenarios/scenario_<name>.py` |
| Pytest entry point | `tests/backend/app/api/test_prompt_engine.py` |
| Framework base class | `backend/app/integration_playback/scenario.py` |
| Run count constants | `backend/app/config/settings.py` |
| xfail allowlist | `tests/conftest.py` (only for non-deterministic LLM tests) |

---

## Step 1: Create the scenario file

```python
# backend/app/integration_playback/scenarios/scenario_my_feature.py

import os
from dataclasses import dataclass

from backend.app.integration_playback.scenario import IntegrationScenario, step


@dataclass
class MyFeatureContext:
    client: object = None       # TestClient, set by _open_test_client()
    llm_reply: str = ""         # capture LLM responses for evaluation
    score: int = -1             # -1 = not yet evaluated


class MyFeatureScenario(IntegrationScenario):
    # ---- Required metadata ----
    scenario_id = "my_feature"                          # unique kebab-case id
    title = "Short human-readable title"
    description = "One sentence describing what this tests."
    tags = ["integration", "your_tag_here"]
    requires_api_key = True                             # True if LLM calls happen
    player_role = "Detective"                           # speaker label in playback UI

    # ---- Multi-run (only for non-deterministic LLM tests) ----
    # multi_run = True   # uncomment to run N times and score each run

    # ---- Lifecycle ----
    def setup(self):
        ctx = MyFeatureContext()
        self.state = ctx
        ctx.client = self._open_test_client()           # creates TestClient + sets env var
        return {"reply": "*Setting up scenario.*", **self.debug_info()}

    def cleanup(self):
        self._close_test_client()                       # restores env var

    # ---- Convenience wrapper (optional) ----
    def _post(self, message: str) -> dict:
        return self._post_chat(self.state.client, "my_session_id", message)

    # ---- Steps ----
    @step(kind="action", description="Start game", uses_llm=False)
    def start_game(self):
        result = self._post("__cmd_newgame__:iu_murder_mystery|M|Alex")
        return [self.say_user("Start game."), self.say_llm("IU", result.get("reply", "")), self.debug_info()]

    @step(kind="action", description="Send test message", uses_llm=True)
    def send_message(self):
        result = self._post("your test message here")
        self.state.llm_reply = result.get("reply", "")
        return [self.say_user("your test message"), self.say_llm("IU", self.state.llm_reply), self.debug_info()]

    @step(kind="assert", description="Assert expected behavior")
    def assert_response(self):
        assert "expected phrase" in self.state.llm_reply.lower(), (
            f"Expected phrase not found.\nReply: {self.state.llm_reply}"
        )
        return self.say_system("Assertion passed.")
```

---

## Step 2: Add the pytest entry point

In `tests/backend/app/api/test_prompt_engine.py`, add at the bottom:

```python
# For deterministic tests (always pass or always fail):
def test_my_feature():
    from backend.app.integration_playback.scenarios.scenario_my_feature import MyFeatureScenario
    MyFeatureScenario.run_as_test()
```

For non-deterministic LLM tests (see multi-run section below):
```python
@pytest.mark.xfail(reason="LLM non-deterministic: <describe the variability>", strict=False)
def test_my_feature():
    from backend.app.integration_playback.scenarios.scenario_my_feature import MyFeatureScenario
    MyFeatureScenario.run_as_test()
```

If you use `@pytest.mark.xfail`, you MUST also add the test node ID to the
allowlist in `tests/conftest.py` (search for `_ALLOWED_XFAIL_NODEIDS`).

---

## Base class helpers — no need to copy this boilerplate

`IntegrationScenario` provides all common operations. Use these instead of writing
your own:

### Test client

```python
# In setup():
ctx.client = self._open_test_client()
# Sets SKIP_KNOWLEDGE_INDEX_BUILD=1 and creates TestClient from backend.app.main.app

# In cleanup():
self._close_test_client()
# Restores SKIP_KNOWLEDGE_INDEX_BUILD to its original value
```

### Chat API

```python
# Post to /api/chat and assert 200; returns the JSON dict
data = self._post_chat(ctx.client, "session_id", "message text")
reply = data.get("reply", "")
```

### LLM evaluator (for multi-run scoring)

```python
# In an async @step method:
score = await self.call_evaluator(evaluator_prompt)
# Calls OpenAI with temperature=0, max_tokens=10
# Parses the first token as int; returns min(valid_scores) on parse error
# Default valid_scores = (100, 50, 0)
```

### Playback display helpers

```python
self.say_user("Player message text")         # → {"user": player_role, "reply": ..., "role": "user"}
self.say_llm("IU", "LLM response text")      # → {"user": "IU", "reply": ..., "role": "llm"}
self.say_system("System message")             # → {"user": "System", "reply": ..., "role": "llm"}
self.debug_info()                             # → {"debug_box": {timestamp, scenario, step, ...}}
self.debug_info({"extra_key": value})         # merge extra fields into debug box
```

### Multi-run scoring

```python
self.record_score(score)   # append to class-level _score_history (call BEFORE assert)
```

---

## Multi-run scenarios (non-deterministic LLM tests)

For tests where the LLM response varies on every call, use multi-run mode.

### Opt-in

```python
class MyScenario(IntegrationScenario):
    multi_run = True   # default is False
```

### Run counts

Controlled globally in `settings.py` — **never hardcode run counts in scenario files**:
```python
LOCAL_INTEG_RUN_COUNT: int = 5   # used when no RAILWAY_* env vars are set
PROD_INTEG_RUN_COUNT: int = 5    # used on Railway (RAILWAY_ENVIRONMENT or RAILWAY_PROJECT_ID set)
```

### Score tiers (100 / 50 / 0 convention)

- **100** — Best: criterion met explicitly in character dialogue
- **50** — Partial: criterion met only via narration or indirectly
- **0** — Fail: no criterion met, or actively wrong

### Evaluator step pattern

```python
@step(kind="assert", description="Evaluate LLM output", uses_llm=True)
async def evaluate_response(self):
    reply = self.state.llm_reply
    assert reply, "LLM reply was empty"

    evaluator_prompt = f"""You are a strict test evaluator.

THE RESPONSE:
\"\"\"{reply}\"\"\"

SCORING TIERS:
100 — <describe 100 condition>
 50 — <describe 50 condition>
  0 — <describe 0 condition>

Answer with EXACTLY one of: 100, 50, or 0"""

    score = await self.call_evaluator(evaluator_prompt)
    self.state.score = score
    return self.debug_info({"evaluator_score": score})


@step(kind="assert", description="Assert evaluator score > 0")
def assert_verdict(self):
    score = self.state.score
    self.record_score(score)          # ALWAYS call before asserting
    assert score > 0, f"Score was {score}.\nReply:\n{self.state.llm_reply}"
    return self.say_system(f"PASSED — score {score}.")
```

### Pass condition

`assert any(s > 0 for s in cls._score_history)` — passes if AT LEAST ONE of the N
runs scored > 0. The test fails only if ALL N runs score 0.

### Score report

After every multi-run scenario, this is printed to stdout automatically:
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

**AI reporting rule**: After running any multi-run integration test, read the
full score report block from stdout and report it verbatim to the user with
individual scores, distribution per tier, and total score %. Never just report
pass/fail — always give the full distribution.

---

## Checklist before committing a new integration test

- [ ] Scenario class in `backend/app/integration_playback/scenarios/scenario_<name>.py`
- [ ] Uses `_open_test_client()` / `_close_test_client()` — NOT manual env var management
- [ ] Uses `_post_chat()` — NOT a manual `client.post(...)` with inline assertion
- [ ] Uses `call_evaluator()` for LLM scoring — NOT inline httpx boilerplate
- [ ] Steps return `say_user` / `say_llm` / `debug_info` payloads
- [ ] Pytest entry in `test_prompt_engine.py`; xfail test added to conftest allowlist if needed
- [ ] `multi_run = True` for non-deterministic LLM tests
- [ ] Score tiers use 100/50/0 convention; `record_score()` called BEFORE assert
- [ ] Run count NOT hardcoded (use `LOCAL_INTEG_RUN_COUNT` / `PROD_INTEG_RUN_COUNT`)
- [ ] Full test suite passes: `python -m pytest tests/ -x -q -m "not integration"`
- [ ] Commit, push beta, squash-merge to prod, push prod

---

## Example: minimal deterministic scenario

```python
# scenario_story_loads.py

from dataclasses import dataclass
from backend.app.integration_playback.scenario import IntegrationScenario, step

@dataclass
class StoryLoadsContext:
    client: object = None
    reply: str = ""

class StoryLoadsScenario(IntegrationScenario):
    scenario_id = "story_loads"
    title = "Story loads and returns a reply"
    description = "Verify newgame command returns a non-empty reply."
    tags = ["integration", "smoke"]
    player_role = "Player"

    def setup(self):
        ctx = StoryLoadsContext()
        self.state = ctx
        ctx.client = self._open_test_client()
        return {"reply": "*Setup done.*", **self.debug_info()}

    def cleanup(self):
        self._close_test_client()

    @step(kind="action", description="Start game", uses_llm=True)
    def start_game(self):
        data = self._post_chat(self.state.client, "s1", "__cmd_newgame__:iu_murder_mystery|M|Alex")
        self.state.reply = data.get("reply", "")
        return [self.say_user("newgame"), self.say_llm("IU", self.state.reply), self.debug_info()]

    @step(kind="assert", description="Reply is non-empty")
    def assert_reply(self):
        assert self.state.reply, "Game returned empty reply"
        return self.say_system("PASSED — reply is non-empty.")
```

---

## Running integration tests

```bash
# Run one specific integration test (with score report visible)
python -m pytest tests/backend/app/api/test_prompt_engine.py::test_iu_identity_correction -s -v

# Run all integration tests
python -m pytest -m integration -r s

# Run only unit tests (fast, no API key needed)
python -m pytest -m "not integration" -x -q
```
