Documentation map (what to read for which need)
Instructions to AI:
- Use this doc (\documentation\ai_1_guide_to_docs.md) to find which docs document what. update this doc if ever needed
- Update this doc as needed (There is a line which says "Only Update Material After This LINE ", only update this doc AFTER that line, leave these instructions)
- Update all docs as needed, except any docs under human_north_star_docs
- Don't be lazy and always rememember to update docs with any changes or learnings 
- After making code changes always add a descriptive comment and push the code.
- Always boldly disagree with me when you feel like something doesnt make sense, dont be shy. and always ask questions if something is unclear.


==== Only Update Material After This LINE ====

## AI-first lookup order (always follow this order)

1) **Task safety + process guardrails first**
- [documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt](documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt](documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)

2) **Feature/domain docs second**
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt)
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md](documentation/model_output_docs/TRANSIENT_BUFFER_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md](documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md)

3) **Generated references last (never use as behavior source of truth)**
- [documentation/auto_update_docs/QUICK_REFERENCE.md](documentation/auto_update_docs/QUICK_REFERENCE.md)
- [documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md](documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md)
- [documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd](documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd)

## Task-to-doc routing

### Test/debug tasks
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt)
- [documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt](documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt)

### Prompt/epistemic behavior tasks
- [documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md](documentation/model_output_docs/STORYTELLER_PROMPT_REDESIGN.md)
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md)
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md)

### Story authoring/content tasks
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt)
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt)

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