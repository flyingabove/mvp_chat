Documentation map (single AI index)

Use this file as the only doc index: `documentation/ai_1_guide_to_docs.md`.

## Fast routing by task

### Safety/process first (read before coding)
- [documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt](documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt](documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt)
- [documentation/ai_learnings_mistakes/ai_logical_bugs.txt](documentation/ai_learnings_mistakes/ai_logical_bugs.txt)

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
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt](documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt)
- [documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md](documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md)

### Story and content authoring
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt)
- Authoring invariant code: `backend/app/engine/authoring_checklist.py`

### UI/scorer/flags
- [documentation/ai_learnings_mistakes/ai_ui_workflow.txt](documentation/ai_learnings_mistakes/ai_ui_workflow.txt)
- [documentation/ai_learnings_mistakes/ai_scorer_system.txt](documentation/ai_learnings_mistakes/ai_scorer_system.txt)
- [documentation/ai_learnings_mistakes/ai_create_new_flag.txt](documentation/ai_learnings_mistakes/ai_create_new_flag.txt)

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
- [documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md](documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md)
- [documentation/model_output_docs/TODO_REGISTER.md](documentation/model_output_docs/TODO_REGISTER.md)
- [documentation/model_output_docs/old designs/EPISTEMIC_REDESIGN.md](documentation/model_output_docs/old%20designs/EPISTEMIC_REDESIGN.md)

## Verification ledger

All doc/code mismatches fixed during active work and all open uncertainties are tracked in:
- [documentation/model_output_docs/errors.txt](documentation/model_output_docs/errors.txt)

## Read-only human vision docs

- [documentation/human_north_star_docs/NorthStar.md](documentation/human_north_star_docs/NorthStar.md)
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt)
- [documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md](documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md)