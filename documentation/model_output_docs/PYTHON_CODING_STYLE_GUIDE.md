# Python Coding Style Guide

## Purpose
This document defines coding style rules for Python changes in this repository so AI agents and humans produce consistent code.

## Scope
- Backend Python modules under `backend/app/**`
- Python test modules under `tests/**`
- Utility scripts under `scripts/**`

## Naming conventions

### Functions and methods
- Use snake_case names.
- **RULE: No leading underscore for helper functions or methods.**
- Leading underscores (`_name`) are reserved only for name-mangling or truly private class internals where Python convention demands it.
- Preferred: `apply_knowledge_resolution_updates`
- Avoid: `_apply_knowledge_resolution_updates`
- If a helper is intentionally private to class internals, make it a class method and leave a comment explaining why.

### Classes
- Use PascalCase.
- **RULE: Scenario and fixture classes must NOT be defined inside test files.** Define them in `backend/app/integration_playback/scenarios/` or equivalent backend modules. Test files are wrappers only.

### Constants
- Use UPPER_SNAKE_CASE.

## Documentation file naming rule

**RULE: All documentation files under `documentation/` (excluding `human_north_star_docs/` and `auto_update_docs/`) must be named `UPPER_SNAKE_CASE.md`.**

- No `.txt` files. Convert to `.md`.
- No `lowercase_with_underscores.md` prefixed names. Use `UPPER_SNAKE_CASE.md`.
- Archive files prefix with `ARCHIVE_`: e.g., `ARCHIVE_EPISTEMIC_ENGINE_TODO.md`
- The only index file is `documentation/AI_DOC_INDEX.md` (formerly `ai_1_guide_to_docs.md`).

Correct examples:
- `AI_FATAL_MISTAKES.md`
- `AI_LEARNINGS_RUNNING_TESTS.md`
- `ERRORS.md`

Wrong examples (do not use):
- `ai_fatal_mistakes.txt`
- `errors.txt`
- `1_example_plan.txt`

## Testing file naming rule
Every test file must map to the source file stem it validates.

Pattern:
- Source: `backend/app/api/prompt_engine.py`
- Test: `tests/backend/app/api/test_prompt_engine.py`

No naked test filenames are allowed. Test filenames must directly reveal the target module.

## Documentation consistency rule
If docs describe runtime behavior that differs from code, update docs immediately and record the correction in `documentation/model_output_docs/ERRORS.md`.
