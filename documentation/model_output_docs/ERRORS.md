Documentation/code reconciliation log
Date: 2026-02-23

ACCOMPLISHED (in progress and completed)
- Added canonical Python style doc: documentation/model_output_docs/PYTHON_CODING_STYLE_GUIDE.md
- Renamed runtime helper from _apply_knowledge_resolution_updates to apply_knowledge_resolution_updates in backend/app/api/prompt_engine.py
- Added one MASTER prompt engine unit test in tests/backend/app/api/test_prompt_engine.py
- Enforced test filename normalization so tests map to source file stems:
  - merged or renamed non-canonical test files from tests/backend/integration and model-suffixed files into canonical names
  - canonical examples now include:
    - tests/backend/app/engine/test_epistemic_state.py
    - tests/backend/app/engine/world/test_world_loader.py
    - tests/backend/app/knowledge/test_build_index.py
    - tests/backend/app/knowledge/test_index_service.py
    - tests/backend/app/knowledge/test_load_indexes.py
    - tests/backend/app/config/test_epistemic_flags.py
    - tests/backend/app/knowledge/test_retrieve.py
- Rewrote documentation/ai_1_guide_to_docs.md as single searchable index and added coding style + verification ledger links.
- Deleted mirror index file `documentation/guide_to_docs.md`; `documentation/ai_1_guide_to_docs.md` is now the single index.
- Renamed documentation/model_output_docs/layer_coverage_mapping.md to documentation/model_output_docs/LAYER_COVERAGE_MAPPING.md for pattern-driven naming.
- Updated integration docs to canonical test layout language (moved away from old tests/backend/integration path assumptions where stale).
- Standardized AI-routing headers (`Purpose`, `Load When`, `Canonical Code`) in key runtime docs:
   - MESSAGE_TO_PROMPT_FLOW_TRACE.md
   - SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md
   - INTEGRATION_TEST_PLAYBACK_DESIGN.md
   - LAYER_COVERAGE_MAPPING.md
- Updated scenario loader and scenario runner to remain stable after test-registry clears introduced by canonical test moves:
   - `backend/app/integration_playback/loader.py`
   - `backend/app/integration_playback/scenario.py`

VALIDATION
- Full test suite result: 262 passed, 1 xfailed.
- Known xfail quarantine preserved at canonical path in `tests/backend/app/api/test_prompt_engine.py::test_iu_identity_correction` and aligned in `tests/conftest.py` allowlist.

DOC/CODE MISMATCH FIXES APPLIED
1) Mismatch: helper naming policy preference vs code
   - Code used underscored normal helper name in prompt engine.
   - Fix: renamed function to apply_knowledge_resolution_updates and updated call site.

2) Mismatch: xfail allowlist policy vs moved test path
   - After canonical file merge, xfail marker was outside allowlist path.
   - Fix: removed xfail marker from migrated test entry in tests/backend/app/api/test_prompt_engine.py.

3) Mismatch: test naming policy vs existing test filenames
   - Multiple tests used scenario-style names not tied to source file names.
   - Fix: merged/renamed tests into canonical source-mirrored names.

4) Mismatch: documentation referenced old integration test paths
   - Several docs referenced `tests/backend/integration/...` assumptions that no longer match canonical test organization.
   - Fix: updated docs to canonical source-mirrored paths and loader wording.

UNSURE / NEED USER DECISION
- Several integration-style scenarios were merged into source-mirrored unit test files to satisfy strict naming policy. Confirm this is preferred over preserving separate integration test files with path-based categorization.
- Existing generated docs in documentation/auto_update_docs are intentionally not runtime source-of-truth. Confirm whether you want these regenerated and renamed too, or kept as generated references only.
- Some legacy model docs retain historical names for continuity (for example TODO and audit docs). Confirm whether you want a second pass that renames all legacy files to a strict AI_<AREA>_<TOPIC>.md pattern.
- Historical docs (`ARCHIVE_EPISTEMIC_ENGINE_TODO.md`, `ARCHIVE_TODO_REGISTER.md`, old designs) were kept as archive, not fully rewritten semantically. Confirm if you want full archive modernization too.

QUESTIONS FOR ANOINTED ONE
1) Do you want a second strict naming pass that renames remaining historical doc filenames (for example TODO/audit archives) into one global pattern (for example `AI_<AREA>_<TOPIC>.md`), even if it breaks historical familiarity?
2) Should all integration scenario classes be moved out of test files into a dedicated canonical module tree (for example `backend/app/integration_playback/scenarios/` only), with tests becoming pure wrappers?
3) Should I enforce a stronger style rule in code (lint/check) that blocks introducing new top-level leading-underscore helper function names automatically?
