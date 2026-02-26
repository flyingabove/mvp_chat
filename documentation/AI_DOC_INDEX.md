Documentation map (single AI index)

Use this file as the only doc index: `documentation/AI_DOC_INDEX.md`.

## Fast routing by task

### Safety/process first (read before coding)
- [documentation/ai_learnings_mistakes/AI_FATAL_MISTAKES.md](documentation/ai_learnings_mistakes/AI_FATAL_MISTAKES.md)
- [documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md](documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md)
- [documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md](documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md)
- [documentation/ai_learnings_mistakes/AI_LOGICAL_BUGS.md](documentation/ai_learnings_mistakes/AI_LOGICAL_BUGS.md)

### Prompt engine and turn orchestration
- Source of truth code: `backend/app/api/prompt_engine.py`
- Canonical tests: `tests/backend/app/api/test_prompt_engine.py`
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md)
- [documentation/model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md](documentation/model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md)

### Epistemic and memory systems
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md](documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)
- [documentation/model_output_docs/LAYER_COVERAGE_MAPPING.md](documentation/model_output_docs/LAYER_COVERAGE_MAPPING.md)

### Tests and integration playback
- [documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md](documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md)
- [documentation/ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md](documentation/ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md)
- [documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md](documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md)

### Story and content authoring
- [documentation/ai_learnings_mistakes/AI_GAME_STRUCTURE.md](documentation/ai_learnings_mistakes/AI_GAME_STRUCTURE.md)
- Authoring invariant code: `backend/app/engine/authoring_checklist.py`

### Data model reference
- [documentation/model_output_docs/DATA_MODEL_INVENTORY.md](documentation/model_output_docs/DATA_MODEL_INVENTORY.md)

### UI/scorer/flags
- [documentation/ai_learnings_mistakes/AI_UI_WORKFLOW.md](documentation/ai_learnings_mistakes/AI_UI_WORKFLOW.md)
- [documentation/ai_learnings_mistakes/AI_SCORER_SYSTEM.md](documentation/ai_learnings_mistakes/AI_SCORER_SYSTEM.md)
- [documentation/ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md](documentation/ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md)

### Coding style standards
- [documentation/model_output_docs/PYTHON_CODING_STYLE_GUIDE.md](documentation/model_output_docs/PYTHON_CODING_STYLE_GUIDE.md)

## Canonical vs generated docs

### Canonical runtime behavior docs
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md](documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md)

### Generated references (never behavior source of truth)
- [documentation/auto_update_docs/QUICK_REFERENCE.md](documentation/auto_update_docs/QUICK_REFERENCE.md)
- [documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md](documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md)
- [documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd](documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd)

### Archive/historical docs
- [documentation/model_output_docs/ARCHIVE_EPISTEMIC_ENGINE_TODO.md](documentation/model_output_docs/ARCHIVE_EPISTEMIC_ENGINE_TODO.md)
- [documentation/model_output_docs/ARCHIVE_TODO_REGISTER.md](documentation/model_output_docs/ARCHIVE_TODO_REGISTER.md)
- [documentation/model_output_docs/ARCHIVE_EPISTEMIC_REDESIGN.md](documentation/model_output_docs/ARCHIVE_EPISTEMIC_REDESIGN.md)
- [documentation/model_output_docs/ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md](documentation/model_output_docs/ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md)
- [documentation/plans_scratch/ARCHIVE_DOC_REWRITE_ENFORCEMENT_2026_02_23.md](documentation/plans_scratch/ARCHIVE_DOC_REWRITE_ENFORCEMENT_2026_02_23.md)

## Verification ledger

All doc/code mismatches fixed during active work and all open uncertainties are tracked in:
- [documentation/model_output_docs/ERRORS.md](documentation/model_output_docs/ERRORS.md)

## Read-only human vision docs

- [documentation/human_north_star_docs/NorthStar.md](documentation/human_north_star_docs/NorthStar.md)
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt)
- [documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md](documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md)
