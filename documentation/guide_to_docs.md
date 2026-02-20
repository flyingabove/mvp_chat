Documentation map (what to read for which need)

- [documentation/ai_learnings_mistakes/ai_create_new_flag.txt](documentation/ai_learnings_mistakes/ai_create_new_flag.txt): How to add new bracket commands ([H]/[HINT]) across backend + frontend with testing notes.
- [documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt](documentation/ai_learnings_mistakes/ai_fatal_mistakes.txt): Postmortem on blank-page incident; guards to avoid orphaned frontend code and how to recover.
- [documentation/ai_learnings_mistakes/ai_game_structure.txt](documentation/ai_learnings_mistakes/ai_game_structure.txt): Story/game asset layout (story folders, knowledge indexes, maps, UUID rules) and steps to author a new case.
- [documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt](documentation/ai_learnings_mistakes/ai_learnings_integration_requirements.txt): Integration test requirements—conda env, .env.test/OPENAI_API_KEY, commands for Windows/Railway, scenario expectations.
- [documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt](documentation/ai_learnings_mistakes/ai_learnings_pushing_code.txt): How AI pushes code (git auth, safe staging/commits, branch norms main/beta/prod).
- [documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt](documentation/ai_learnings_mistakes/ai_learnings_running_tests.txt): Known-good pytest commands (full/unit/integration) for Windows with get_output_via_markers wrapper; pre-flight checklist.
- [documentation/ai_learnings_mistakes/ai_ui_workflow.txt](documentation/ai_learnings_mistakes/ai_ui_workflow.txt): Frontend single-file architecture and state machine (menu→name→gender→chat, commands, map rendering, error guards, API calls).

- [documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd](documentation/auto_update_docs/ARCHITECTURE_DIAGRAM.mmd): Mermaid architecture diagram covering client/API/engine/knowledge layers.
- [documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md](documentation/auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md): Full generated system manual with file-by-file notes and architecture narrative.
- [documentation/auto_update_docs/QUICK_REFERENCE.md](documentation/auto_update_docs/QUICK_REFERENCE.md): Condensed index of files, endpoints, commands, and key constants.

- [documentation/human_north_star_docs/NorthStar.md](documentation/human_north_star_docs/NorthStar.md): Vision doc for the narrative engine (state/time/incentives/constraints, two-call loop philosophy).
- [documentation/human_north_star_docs/StoriesChatNorthStar.txt](documentation/human_north_star_docs/StoriesChatNorthStar.txt): One-paragraph north star summary of the game’s intent.
- [documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md](documentation/human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md): Detailed IU/Bob/Steve interrogation script used for epistemic tests and layer mapping.

- documentation\model_output_docs is where AI will typically write new docs
- [documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md](documentation/model_output_docs/CHARACTER_GRAPH_DESIGN.md): Implemented relationship graph design plus enforced prompt-source boundaries (canonical graphs/objects + BM25/FAISS + transient).
- [documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md](documentation/model_output_docs/EPISTEMIC_ENGINE_DESIGN.md): Epistemic architecture (truth vs belief vs retrieval) with namespacing rules `<user>-<story>-<instance>`.
- [documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md](documentation/model_output_docs/EPISTEMIC_ENGINE_TODO.md): Implementation todo list for epistemic data model, extractor schema, prompt lift, and tests.
- [documentation/model_output_docs/epistemic_harness_plan.md](documentation/model_output_docs/epistemic_harness_plan.md): Harness status/plan for epistemic layer toggles and scenario coverage.
- [documentation/model_output_docs/EPISTEMIC_REDESIGN.md](documentation/model_output_docs/EPISTEMIC_REDESIGN.md): Story JSON v2 proposal with canon tiers (ANCHOR/CANON/SECRET_CANON/CLAIM/RUMOR), knowledge chunks, and invariants.
- [documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md](documentation/model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md): Scenario/step registry + UI playback design for integration tests (cached vs live LLM, assertions).
- [documentation/model_output_docs/layer_coverage_mapping.md](documentation/model_output_docs/layer_coverage_mapping.md): Mapping of IU scenario segments to epistemic layers and how toggle tests assert them.
- [documentation/model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md](documentation/model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md): End-to-end runtime trace from previous LLM response through retrieval/extractors/graphs/transient updates to the next LLM prompt send.
- [documentation/model_output_docs/NORTH_STAR_GAPS_AUDIT_2026-02-20.md](documentation/model_output_docs/NORTH_STAR_GAPS_AUDIT_2026-02-20.md): Detailed gap audit of current implementation vs north-star design principles, with prioritized remediation actions.
