# Epistemic Engine TODO (Archived)

This file is retained for historical planning context only.

## Why archived

The prior phase checklist drifted from current implementation details and created conflicting guidance. Active behavior should be inferred from code + tests + canonical design docs.

## Use these docs instead

- `documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md`
- `documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md`
- `documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md`

## Runtime source of truth

- `backend/app/engine/epistemic_state.py`
- `backend/app/engine/prompt_builder.py`
- `backend/app/engine/active_characters.py`
- `backend/app/api/chat.py`
- `tests/backend/app/engine/`
- `tests/backend/integration/`

Keep new work tracking in PRs/issues instead of reviving long-lived checklist docs here.
