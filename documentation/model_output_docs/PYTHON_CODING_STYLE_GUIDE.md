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
- For normal helper functions/methods, do not use leading underscore names.
- Preferred: `apply_knowledge_resolution_updates`
- Avoid: `_apply_knowledge_resolution_updates`

### Classes
- Use PascalCase.

### Constants
- Use UPPER_SNAKE_CASE.

## Personal preference style rule
This codebase prefers readable non-underscored names for normal helper methods/functions.

If a helper is intentionally private to a class internals context, define it as a class method and document why it is internal.

## Testing file naming rule
Every test file must map to the source file stem it validates.

Pattern:
- Source: `backend/app/api/prompt_engine.py`
- Test: `tests/backend/app/api/test_prompt_engine.py`

No naked test filenames are allowed. Test filenames must directly reveal the target module.

## Documentation consistency rule
If docs describe runtime behavior that differs from code, update docs immediately and record the correction in `documentation/model_output_docs/errors.txt`.
