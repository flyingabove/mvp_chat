# Layer Coverage Mapping (IU Scenario)

> **What this doc is for:** Maps which prompt layers are tested by which tests. Edit this doc when new prompt layers are added or test coverage changes.

## Purpose
Map IU scenario segments to epistemic layers and identify which tests verify each layer.

## Load When
- You update epistemic layer toggles.
- You change IU scenario assertions.
- You need to confirm whether layer failures are expected.

## Canonical Files
- Scenario harness: `backend/app/integration_playback/scenarios/scenario_epistemic_iu.py`
- Toggle behavior tests: `tests/backend/app/config/test_epistemic_flags.py`
- Prompt engine orchestration tests: `tests/backend/app/api/test_prompt_engine.py`

## Layer to Segment Mapping
- Truth layer: confession and disposal segments that become canonical facts.
- Belief layer: denials/contradictions that remain character-local claims until resolved.
- Narrative layer: visible scene output/flow steps in playback traces.
- Retrieval layer: retrieved snippets and memory blocks used for non-authoritative support.

## Test Alignment
- `scenario_epistemic_iu` validates canonical facts, claims, and observations.
- `test_epistemic_flags` toggles master/per-layer gates and asserts expected pass/fail behavior.
- `test_prompt_engine` validates turn orchestration and prompt-layer assembly behavior.

## Maintenance Rules
- Update this mapping when scenario step order or toggle semantics change.
- Keep paths aligned with canonical source-mirrored test naming.
