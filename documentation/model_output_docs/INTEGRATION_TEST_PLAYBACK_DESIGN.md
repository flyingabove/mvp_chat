# Integration Test Playback Design (UI + Harness)

Goal: All integration tests (chat, extractor-only, cached LLM, live LLM) can be played back in a UI submenu as auto-running dialogues with consistent structure. Tests remain executable via pytest but also expose a uniform, serializable script the UI can consume.

## Core Concepts
- **Scenario registry**: Each integration test registers a `Scenario` object describing metadata, required fixtures (cache vs live API), and a sequence of `Step` objects.
- **Step types (uniform)**:
  - `UserMessage(content)` – what the human sends
  - `SystemAction(name, payload)` – internal actions (state init, travel, time advance)
  - `LLMCall(kind, mode, prompt, cached_response=None)` – renderer/extractor calls; `mode` in {`live`, `cached`}; `cached_response` holds deterministic text when available
  - `Assertion(description, fn_ref)` – validates state after the step
  - `Delay(ms)` – optional pacing for playback
- **Execution engines**:
  - **Pytest runner**: Executes steps with real code paths, running assertions; respects `mode` to decide live vs cached calls.
  - **UI playback**: Reads the scenario, replays messages and responses (uses cached text or stubbed calls), surfaces assertion results and state snapshots in a side panel.

## Data Model (plain Python classes)
```python
class Scenario:
    id: str
    title: str
    description: str
    tags: list[str]  # e.g., ["integration", "live-llm", "extractor-only"]
    requires_api_key: bool
    requires_cache: bool  # needs /data or local cache
    steps: list[Step]

class Step:
    kind: Literal["user", "system", "llm", "assert", "delay"]
    payload: dict  # shape depends on kind

# Helpers for authoring
UserMessage = lambda text: Step(kind="user", payload={"text": text})
SystemAction = lambda name, payload=None: Step(kind="system", payload={"name": name, "payload": payload or {}})
LLMCall = lambda kind, mode, prompt, cached_response=None: Step(kind="llm", payload={"kind": kind, "mode": mode, "prompt": prompt, "cached_response": cached_response})
AssertionStep = lambda description, fn_ref: Step(kind="assert", payload={"description": description, "fn": fn_ref})
Delay = lambda ms=400: Step(kind="delay", payload={"ms": ms})
```

## Registry & Discovery
- A central `integration_scenarios.py` exports `SCENARIOS: dict[str, Scenario]`.
- Each test module registers its scenario in `SCENARIOS` and uses it in pytest via a small adapter fixture `run_scenario(scenario_id)`.
- UI reads the same registry (import or JSON export) to list scenarios.

## How existing tests map to scenarios
- **test_api_play_5_turns_world_time**: Steps are UserMessage(s) for each turn + Assertions on minute/location. LLM calls are mocked (cached deterministic replies). Mode: `cached`.
- **test_location_extractor_e2e**: Steps include UserMessage with movement text, LLMCall(kind="extractor", mode="live" or `cached` when provided), Assertion on extracted destination. Could provide cached response to allow offline playback.
- **test_hybrid_retrieval**: SystemAction to load indexes, LLMCall for embedder (live/cached), Assertions on recall thresholds. UI playback can skip heavy compute by using cached results.
- **test_epistemic_state_iu_flow**: Cached (no API). Steps are SystemAction(init), multiple UserMessage/LLMCall pairs if we later add extractor/renderer, Assertions on epistemic log state.
- **knowledge-resolution flow (new)**: UserMessage + renderer LLMCall + post-reply knowledge extractor LLMCall + Assertions on:
  - belief graph claim upsert (`kr::<speaker>::<chunk_id>`),
  - transient knowledge object existence,
  - 8-turn TTL expiration behavior.

## Playback Engine (UI)
- Menu entry: "Integration Playback" → list scenarios (id, title, tags, live/cached badges, needs API key). Filter by tag.
- On select: show sidebar with description, prereqs, and controls: Play, Pause, Step, Speed (delay ms).
- Renderer:
  - Renders chat transcript; for `llm` steps, uses `cached_response` when present; if `mode=live` and API keys are missing, UI disables play or prompts for key.
  - Shows assertions as checkmarks; if an assertion fails in playback mode, render red badge with message.
  - Shows state diff snapshot if provided by assertion function (optional return value from fn_ref).
- Deterministic mode: default to cached paths if available; allow toggle to "live" when supported.

## Test Runner Adapter (pytest)
- Fixture `scenario_runner` that takes a Scenario and executes steps:
  - `user`: call chat endpoint or extractor input depending on scenario config
  - `system`: perform setup (init state, set env, set character id)
  - `llm`: if `mode="cached"` use provided text; else call real LLM (guarded by api key fixtures)
  - `assert`: call fn_ref(state) and raise on failure
- Each integration test becomes a thin wrapper: `def test_xxx(scenario_runner): scenario_runner("api_play_5_turns")`

## Caching Strategy
- For LLM-dependent scenarios, store `cached_response` text in the scenario definition to ensure offline determinism.
- For extractor-only steps, store parsed JSON output as `cached_response`.
- Provide a script to refresh caches (opt-in) with live calls; not used in CI.

## Storage/Paths
- Registry lives in `tests/backend/integration/scenario_registry.py`.
- Cached payloads can be embedded inline in the scenario or stored under `tests/backend/integration/cached/{scenario_id}/step_{n}.json` and referenced.

## Implementation Plan (incremental)
1) Add Scenario/Step classes + registry file; add authoring helpers.
2) Refactor one test (api_play_5_turns) to use `scenario_runner`; include cached replies.
3) Add UI stub (menu + list + playback panel) consuming registry; CLI/JSON export if needed for frontend.
4) Migrate remaining integration tests into scenarios; add cached outputs where feasible to avoid live calls.
5) Add cache refresh script and docs on providing API keys when running live.

## CI / Docker Environment Notes

### OPENAI_API_KEY in CI
The `OPENAI_API_KEY` environment variable **is set** as a Railway build-time secret.
However, Docker `RUN` commands only see build args declared with `ARG`, not runtime
env vars. The Dockerfile must include:

```dockerfile
ARG OPENAI_API_KEY=""
ENV OPENAI_API_KEY=${OPENAI_API_KEY}
```

Without this, build-time `pytest` runs will skip any test guarded by
`require_openai_api_key` even though the key is available in Railway's
environment. Railway passes build args automatically when they match
configured env var names.

### scripts/ directory in Docker
The Dockerfile must `COPY scripts/ /srv/scripts/` alongside `backend/` and
`tests/`. Tests under `tests/scripts/` import from `scripts.scorer.story_agent_ui`
and will fail with `ModuleNotFoundError` if the `scripts/` tree is not present
in the Docker image.

## Acceptance
- All integration tests run via scenario runner with existing assertions unchanged in spirit.
- UI can list scenarios and auto-play transcripts using cached data.
- Live runs remain possible for scenarios tagged `live-llm` when API key is present.
- Playback model includes extractor-after-render phases (location extraction pre-render and knowledge-resolution extraction post-render).
