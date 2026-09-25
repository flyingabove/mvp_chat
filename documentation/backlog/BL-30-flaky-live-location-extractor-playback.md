# BL-30 — Live-LLM location extractor playback test fails intermittently

- **Type:** tech-debt (test reliability)
- **Found:** 2026-09-25, while running the full suite for the character & world model work
- **Severity:** low. It is `@pytest.mark.integration`, excluded from the deploy test gate, but it makes local full-suite runs flaky.

## Problem
`tests/backend/app/engine/extractors/test_location_extractor.py::test_location_extractor_playback` runs
`LocationExtractorScenario` (`backend/app/integration_playback/scenarios/scenario_location_extractor_llm.py`) against the
real OpenAI API. It failed in 2 of 7 consecutive full-suite runs and passed 6 of 6 times in isolation. The code under test
(`engine/extractors/location_extractor.py`) was not changed. The failure comes from model output variance and/or
concurrent load on the shared org rate limit.

## Fix direction
Either pin the expectations to intent classes with tolerance (accept semantically equivalent destinations), retry once on
a mismatch, or record the model responses (VCR-style) and replay them in the default suite, keeping a live variant behind
an explicit opt-in marker.

## Why deferred / cautions
Unrelated to the world-model change that surfaced it. Don't loosen it into a no-op; the test is meant to catch real
extractor regressions.

## Touches
`tests/backend/app/engine/extractors/test_location_extractor.py`,
`backend/app/integration_playback/scenarios/scenario_location_extractor_llm.py`.
