# TODO Register (Archived)

This document is archived to avoid stale planning conflicts.

## Current policy

- Runtime behavior source of truth is code + tests, not TODO prose.
- Keep active work tracking in GitHub issues/PRs and test expectations.
- If a test is quarantined (for example allowlisted `xfail`), record rationale directly beside the test and in the relevant implementation doc.

## Canonical references

- `backend/app/engine/prompt_builder.py`
- `backend/app/engine/active_characters.py`
- `tests/backend/app/engine/test_prompt_builder.py`
- `tests/backend/app/engine/test_active_characters.py`
- `tests/backend/integration/test_iu_identity_correction.py`
- `documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md`
- `documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md`
