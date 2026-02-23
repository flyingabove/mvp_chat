Documentation map (what to read for which need)
Instructions to AI:
- Use this doc (\documentation\ai_1_guide_to_docs.md) to answers anyquestions you might have and load context for problems you need to solve and find designs and common problems. 
- Update this doc and all docs as needed, except any docs under human_north_star_docs
- Only read docs as necessary as related to your task

## AI-first lookup order (always follow this order)

1) **Task safety + process guardrails first**
- [documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt](documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt](documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)
- [documentation/ai_learnings_mistakes/ai_logical_bugs.txt](documentation/ai_learnings_mistakes/ai_logical_bugs.txt) — known logical bugs, dead code, and silent failures

2) **Feature/domain docs second**
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt)
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md](documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md)
- [documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md](documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md)

3) **Generated references last (never use as behavior source of truth)**
- [documentation/auto_update_docs/QUICK_REFERENCE.md](documentation/auto_update_docs/QUICK_REFERENCE.md)
- [documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md](documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md)
- [documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd](documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd)

## Task-to-doc routing

### Test/debug tasks
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt](documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt)

### Prompt Engine tasks (backend/app/api/prompt_engine.py)
The **Prompt Engine** (`backend/app/api/prompt_engine.py`) is the single file that receives
raw requests, orchestrates all context (state, knowledge, history, flags), builds the fully-
assembled LLM prompt, and dispatches the API call. Its test file mirrors the path exactly:
`tests/backend/app/api/test_prompt_engine.py`.

### Prompt/epistemic behavior tasks
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](documentation/model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md)
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)

### Story authoring/content tasks
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt)
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt)
- Knowledge authoring invariant rules: `backend/app/engine/authoring_checklist.py`
  (enforced at authoring time — engine never sees rumor-vs-fact labels)

### Frontend/UI tasks
- [documentation/ai_learnings_mistakes/ai_ui_workflow.txt](documentation/ai_learnings_mistakes/ai_ui_workflow.txt)

### Scorer/grader tasks
- [documentation/ai_learnings_mistakes/ai_scorer_system.txt](documentation/ai_learnings_mistakes/ai_scorer_system.txt)

### Flags/commands tasks
- [documentation/ai_learnings_mistakes/ai_create_new_flag.txt](documentation/ai_learnings_mistakes/ai_create_new_flag.txt)

## Status annotations

- **Canonical runtime behavior docs:**
	- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
	- [documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md](documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md)
	- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)
	- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)

- **Historical/archive docs (not source of truth):**
	- [documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md](documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md)
	- [documentation/model_output_docs/TODO_REGISTER.md](documentation/model_output_docs/TODO_REGISTER.md)
	- [documentation/model_output_docs/old designs/EPISTEMIC_REDESIGN.md](documentation/model_output_docs/old%20designs/EPISTEMIC_REDESIGN.md)

## Human vision docs (read-only)

- [documentation/human_north_star_docs/NorthStar.md](documentation/human_north_star_docs/NorthStar.md)
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt)
- [documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md](documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md)