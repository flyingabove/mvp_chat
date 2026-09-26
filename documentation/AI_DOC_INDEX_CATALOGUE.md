# AI Documentation Index & Catalogue

> **What this doc is for:** The single index of all project documentation. Use this to find the right doc to read or edit. Every doc has a one-line "edit this doc if..." description so you don't have to open every file to figure out where new info goes.

---

## Safety/Process (read before coding)

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_FATAL_MISTAKES.md](ai_learnings_mistakes/AI_FATAL_MISTAKES.md) | ...a production-breaking mistake happens that must never be repeated. |
| [AI_LEARNINGS_RUNNING_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md) | ...test runner behavior changes or new testing patterns are established. |
| [AI_LEARNINGS_PUSHING_CODE.md](ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md) | ...push/deploy workflow rules change (commit conventions, CI, deploy flow). |
| [AI_PWA_IPHONE_WEBAPP_LEARNINGS.md](ai_learnings_mistakes/AI_PWA_IPHONE_WEBAPP_LEARNINGS.md) | ...an iPhone Home Screen install, PWA cache, standalone viewport, keyboard, map or mobile chat mismatch needs diagnosis or verification. |
| [AI_TASK_WORKFLOW.md](ai_learnings_mistakes/AI_TASK_WORKFLOW.md) | ...intermediate task tracking location, consumption requirements, or cleanup policy changes. |
| [AI_LOGICAL_BUGS.md](ai_learnings_mistakes/AI_LOGICAL_BUGS.md) | ...a new logic bug is discovered and resolved during an audit. |
| [user_corrections.md](user_corrections.md) | ...the user corrects a mistake that should be remembered across sessions. |
| [backlog/](backlog/) | ...work is knowingly deferred (audit finding, follow-up, manual owner action): add one `BL-<n>-<slug>.md` file per item and delete it when fixed. Conventions: `/add-and-remove-from-backlog` skill (`.claude/skills/add-and-remove-from-backlog/SKILL.md`). |
| [BACKLOG.md](BACKLOG.md) | ...legacy items BL-01..BL-25 only: move an item to `backlog/` when you work on it, and remove its entry when it is fixed. No new entries. |

## Prompt Engine & Turn Orchestration

| Doc | Edit this doc if... |
|-----|---------------------|
| [STORYTELLER_PROMPT_REDESIGN.md](model_output_docs/STORYTELLER_PROMPT_REDESIGN.md) | ...the storyteller system prompt structure or injection order changes. |
| [SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](model_output_docs/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md) | ...the extractor schema, prompt, or validation logic changes. |
| [MESSAGE_TO_PROMPT_FLOW_TRACE.md](model_output_docs/MESSAGE_TO_PROMPT_FLOW_TRACE.md) | ...the prompt assembly pipeline (message → LLM prompt) changes. |
| Source of truth code: `backend/app/api/prompt_engine.py` | |
| Canonical tests: `tests/backend/app/api/test_prompt_engine.py` | |

## Epistemic & Memory Systems

The proposed shared Jev retrieval, weighted sampling and subtle narrative-context
system is documented in [JEV_DYNAMIC_CONTEXT_DESIGN.md](model_output_docs/JEV_DYNAMIC_CONTEXT_DESIGN.md).
Update it when candidate selection, callback/clue pacing, probability sampling,
or the cross-game context implementation plan changes. Broad retrieval, Jev
relevance judgment and configurable power-sampling are implemented behind the
`context_selection` Jev task flag; clue and relationship pacing policies remain
planned.

| Doc | Edit this doc if... |
|-----|---------------------|
| [EPISTEMIC_ENGINE_DESIGN.md](model_output_docs/EPISTEMIC_ENGINE_DESIGN.md) | ...knowledge retrieval, belief injection, or epistemic rules change. |
| [TRANSIENT_BUFFER_DESIGN.md](model_output_docs/TRANSIENT_BUFFER_DESIGN.md) | ...transient buffer eviction, injection, or scoring logic changes. |
| [CHARACTER_GRAPH_DESIGN.md](model_output_docs/CHARACTER_GRAPH_DESIGN.md) | ...the character graph schema, edge types, or query API changes. |
| [LAYER_COVERAGE_MAPPING.md](model_output_docs/LAYER_COVERAGE_MAPPING.md) | ...new prompt layers are added or test coverage for layers changes. |

## Game Design Systems

The proposed next-stage social engine is specified in [SOCIAL_ENGINE_V2_DESIGN.md](model_output_docs/SOCIAL_ENGINE_V2_DESIGN.md): typed actions/events, transactional turns, gossip provenance, character-local beliefs, agreements, NPC intentions, drama selection, migration and release gates. This is a design proposal, not shipped v2 behavior.

The reusable world/location atlas schema, research mapping and routing policy are
documented in [WORLD_ATLAS_DESIGN.md](model_output_docs/WORLD_ATLAS_DESIGN.md).
Update that document when map metadata, coordinates, routes or map UI behavior changes.

The proposed living-world investigation and conversation mechanics are in
[LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md](model_output_docs/LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md).
Use it for evidence types, NPC routines and sleep, context obligations, probabilistic
initiative, and social-scene handoffs; its runtime features are not yet implemented.

| Doc | Edit this doc if... |
|-----|---------------------|
| [GAME_DESIGN_SYSTEMS.md](model_output_docs/GAME_DESIGN_SYSTEMS.md) | ...core gameplay systems change (world state, time, quests, difficulty, win conditions). |
| [NPC_SIDEQUEST_DESIGN.md](model_output_docs/NPC_SIDEQUEST_DESIGN.md) | ...NPC behavior, sidequest triggers, or quest logic changes. |
| [SOCIAL_MODE_DESIGN.md](model_output_docs/SOCIAL_MODE_DESIGN.md) | ...the optional `mode` story-JSON schema, the mode prompt layer, or ensemble/slice-of-life ("social_sim") authoring guidance changes. |
| [CHARACTER_WORLD_MODEL_REDESIGN.md](model_output_docs/CHARACTER_WORLD_MODEL_REDESIGN.md) | ...the problems list (P1-P14), the character object, world location index (`where`/`contents`, `move()`), events, memories (`@id` refs, descriptors, provenance), relationship edges, context projection, or the redesign build order change. **Implemented (steps 0-8) in `backend/app/engine/world_model/`.** |
| [CHARACTER_WORLD_MODEL_IMPLEMENTATION_PLAN.md](model_output_docs/CHARACTER_WORLD_MODEL_IMPLEMENTATION_PLAN.md) | ...a world-model module, integration point, story-data schema (`world_model` section), test list, or known limit changes. Source of truth code: `backend/app/engine/world_model/` (entry: `turn.py`); tests: `tests/backend/app/engine/world_model/`. |
| [CAST_LIFECYCLE_DESIGN.md](model_output_docs/CAST_LIFECYCLE_DESIGN.md) | ...characters can enter, leave, rotate through capacity-limited slots, or lifecycle eligibility/persistence changes. |

## Tests & Integration Playback

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_LEARNINGS_RUNNING_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md) | ...test runner behavior changes or new testing patterns are established. |
| [AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md](ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md) | ...integration test policies or mock boundaries change. |
| [AI_LEARNINGS_WRITING_INTEG_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_WRITING_INTEG_TESTS.md) | ...the integration test framework, patterns, or requirements change. **Start here for writing new integ tests.** |
| [INTEGRATION_TEST_PLAYBACK_DESIGN.md](model_output_docs/INTEGRATION_TEST_PLAYBACK_DESIGN.md) | ...the playback system architecture or UI changes. |

## Story & Content Authoring

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_GAME_STRUCTURE.md](ai_learnings_mistakes/AI_GAME_STRUCTURE.md) | ...the story data model changes or a new file type is added to story directories. |
| Authoring invariant code: `backend/app/engine/authoring_checklist.py` | |

## UI & Frontend

| Doc | Edit this doc if... |
|-----|---------------------|
| [UI_REDESIGN_2026.md](model_output_docs/UI_REDESIGN_2026.md) | ...UI screens, components, CSS system, or navigation changes. **Full 2026 design spec.** |
| [AI_UI_WORKFLOW.md](ai_learnings_mistakes/AI_UI_WORKFLOW.md) | ...frontend architecture, build process, or UI development patterns change. Its older UI inventory is historical; use `.claude/skills/ship-and-verify/BROWSER_QA.md` for current browser QA. |
| [AI_CREATE_NEW_FLAG.md](ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md) | ...adding a new bracket command or game mode flag to the chat system. |

## Scorer / Debug System

The [2026-09-25 manual beta play review](model_output_docs/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md) records 10 personally chosen Terrace turns and 12 IU turns, subjective logic/engagement grades, deployment scope, and evidence for BL-30 through BL-32. Preserve it as a dated observational report; later playtests should be separate reports.

The proposed controlled beta/prod evaluation system is documented in
[JEV_GAME_ARENA_DESIGN.md](model_output_docs/JEV_GAME_ARENA_DESIGN.md).
Update it when paired-game controls, Jev judge calibration, evidence contracts,
rating statistics or the arena implementation plan change. Status: implemented in observational mode
(local-only tooling in `.claude/skills/promote-to-prod/`, see its §13-14); server receipts/snapshots and human calibration are BACKLOG BL-19/BL-20.

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_SCORER_SYSTEM.md](ai_learnings_mistakes/AI_SCORER_SYSTEM.md) | ...the debug system, scoring, player-agent loop, or grader changes. |
| [JEV_GAME_ARENA_DESIGN.md](model_output_docs/JEV_GAME_ARENA_DESIGN.md) | ...the beta-vs-prod arena changes: rubric/weights, judge policy, pairing, rating math, checks, CLI, or its §13 implementation status. Code: `.claude/skills/promote-to-prod/arena/` (local-only, never deployed), CLI `python .claude/skills/promote-to-prod/arena_cli.py`, release procedure `/promote-to-prod`. |

## Data Models

| Doc | Edit this doc if... |
|-----|---------------------|
| [DATA_MODEL_INVENTORY.md](model_output_docs/DATA_MODEL_INVENTORY.md) | ...any data model, schema, or field is added or changed. |

## Infrastructure & Deployment

| Doc | Edit this doc if... |
|-----|---------------------|
| [INFRASTRUCTURE.md](model_output_docs/INFRASTRUCTURE.md) | ...deployment, hosting, environment variables, or infrastructure changes. |
| [AUTH_AND_PERSISTENCE_DESIGN.md](model_output_docs/AUTH_AND_PERSISTENCE_DESIGN.md) | ...auth flow, session storage, OAuth redirect URI policy, or localhost-vs-hosted login boundaries change. |

## Coding Standards

| Doc | Edit this doc if... |
|-----|---------------------|
| [PYTHON_CODING_STYLE_GUIDE.md](model_output_docs/PYTHON_CODING_STYLE_GUIDE.md) | ...Python coding conventions or style rules for this project change. |

## Vision (Human-Owned, Read-Only Unless Asked)

| Doc | Edit this doc if... |
|-----|---------------------|
| [NorthStar.md](human_north_star_docs/NorthStar.md) | ...the long-term product vision or user experience goals change. **Vision only, no technical details.** |
| [EpistemicStateJennieIntegrationTestExample.md](human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md) | ...the epistemic state example for Jennie scenario needs updating. |

## Auto-Generated References (Do Not Manually Edit)

| Doc | Edit this doc if... |
|-----|---------------------|
| [QUICK_REFERENCE.md](auto_update_docs/QUICK_REFERENCE.md) | ...regenerating documentation snapshots (auto-generated). |
| [COMPREHENSIVE_DOCUMENTATION.md](auto_update_docs/COMPREHENSIVE_DOCUMENTATION.md) | ...regenerating documentation snapshots (auto-generated). |

## Archive / Historical (Read-Only Reference)

| Doc | Purpose |
|-----|---------|
| [ARCHIVE_EPISTEMIC_ENGINE_TODO.md](model_output_docs/ARCHIVE_EPISTEMIC_ENGINE_TODO.md) | Historical epistemic engine TODO list. |
| [ARCHIVE_TODO_REGISTER.md](model_output_docs/ARCHIVE_TODO_REGISTER.md) | Historical TODO register. |
| [ARCHIVE_EPISTEMIC_REDESIGN.md](model_output_docs/ARCHIVE_EPISTEMIC_REDESIGN.md) | Historical epistemic redesign notes. |
| [ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md](model_output_docs/ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md) | Historical audit of NorthStar gaps. |
| [ARCHIVE_DOC_REWRITE_ENFORCEMENT_2026_02_23.md](plans_scratch/ARCHIVE_DOC_REWRITE_ENFORCEMENT_2026_02_23.md) | Historical doc rewrite enforcement plan. |

## Active Initiatives (Plans Under Execution)

| Doc | Edit this doc if... |
|-----|---------------------|
| [ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md](ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md) | ...a phase of the reuse/correctness/performance/Jev initiative is started, completed, re-scoped, or its measurements are re-run. **Verified against code + measured on 2026-09-21; supersedes the raw audit's priorities where they conflict.** |
| [CODEBASE_AUDIT_AND_REUSE_PERFORMANCE_JEV_PLAN_2026_09_21.md](CODEBASE_AUDIT_AND_REUSE_PERFORMANCE_JEV_PLAN_2026_09_21.md) | ...never — source audit, read-only input to the engineering plan above. |
| [JEV_EXTRACTOR_REDESIGN_2026_09_22.md](JEV_EXTRACTOR_REDESIGN_2026_09_22.md) | ...the Jev/`TurnExtractor` ability mapping, call structure, cost model, or per-ability test cases change. **Refines Phase 4 of the engineering plan; every Jev result in it is a real live `jev-1.13.0` response, not a projection.** |
| [JEV_PROVIDER_ARCHITECTURE_2026_09_22.md](JEV_PROVIDER_ARCHITECTURE_2026_09_22.md) | ...the Jev provider/fallback machinery changes: the `resolve()` contract, circuit-breaker parameters, flags/rollout modes, `backend/app/llm/` layout, or the implementation order. **Implementation-level design; read `JEV_EXTRACTOR_REDESIGN` first for WHICH abilities move.** |
| [PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md](PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md) | ...the `SessionFactory`/`SnapshotCodec`/`TurnService`/`PlayerView`/`StoryDefinition.validate()` contracts, the `application/` package layout, or the handler decomposition order change. |
| [PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md](PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md) | ...any of the 11 optimization rows' design, measurement method, or ship/drop threshold changes. |
| [PHASE_5_FRONTEND_MODULARIZATION_DESIGN_2026_09_22.md](PHASE_5_FRONTEND_MODULARIZATION_DESIGN_2026_09_22.md) | ...the frontend module extraction order, the asset-manifest schema, or the motion-settings design changes. **Corrects the original plan's stale map-integration claim.** |
| [PHASE_6_DELIVERY_CI_DESIGN_2026_09_22.md](PHASE_6_DELIVERY_CI_DESIGN_2026_09_22.md) | ...the Dockerfile/CI/dependency-lock design, the startup-readiness fix, or the index-fingerprint mechanism changes. |

## Verification Ledger

| Doc | Edit this doc if... |
|-----|---------------------|
| [ERRORS.md](model_output_docs/ERRORS.md) | ...a doc/code discrepancy is found or resolved. |
