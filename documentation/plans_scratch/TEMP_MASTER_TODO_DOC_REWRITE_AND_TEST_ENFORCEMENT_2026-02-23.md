# TEMP MASTER TODO (2026-02-23)

Status legend: [ ] not started, [~] in progress, [x] complete

## Phase A — Test architecture enforcement
- [x] Build source->test filename map for backend/app, scripts, and top-level backend entry modules
- [x] Detect all tests not matching target pattern: tests/.../test_<source_file_stem>.py
- [x] Detect duplicate ownership (same source file tested by multiple misnamed files)
- [x] Detect naked tests (tests not clearly mapped to a source module)
- [x] Move/rename test files to canonical names
- [x] Update imports/fixtures paths if needed after rename
- [x] Run targeted tests for moved files

## Phase B — Prompt engine master unit test
- [x] Define single "MASTER" prompt engine test scope (full endpoint orchestration path)
- [x] Implement test in canonical prompt engine test file
- [x] Ensure deterministic mocks and assertions across key orchestration stages
- [x] Run prompt engine test module and confirm pass

## Phase C — Coding style documentation
- [x] Create naming convention doc for methods/functions
- [x] Add personal preference rule: avoid leading underscore for normal helper methods/functions
- [x] Add examples: bad `_apply_knowledge_resolution_updates` vs good `apply_knowledge_resolution_updates`
- [x] Link this style doc from AI doc index

## Phase D — Documentation rewrite and optimization (excluding human_north_star_docs)
- [x] Audit every doc under documentation/ excluding human_north_star_docs
- [x] Standardize titles and pattern-driven names where beneficial
- [~] Restructure each doc for AI searchability:
  - [x] Purpose
  - [x] When to load
  - [x] Canonical files/modules
  - [~] Invariants and anti-patterns
  - [x] Quick checklist
- [x] Remove stale/duplicated guidance
- [x] Replace references to documentation/guide_to_docs.md with documentation/ai_1_guide_to_docs.md
- [x] Delete documentation/guide_to_docs.md

## Phase E — Doc/code consistency verification
- [x] For each doc touched, verify claims against runtime code
- [x] If mismatch found, fix docs and/or code
- [x] Record each mismatch and fix in documentation/model_output_docs/errors.txt
- [x] Record open questions/uncertainties in errors.txt as encountered

## Phase F — Final doc reorganization pass
- [~] Re-read all rewritten docs once more for consistency and searchability
- [x] Ensure naming patterns and cross-links are consistent
- [x] Ensure no chart dependency for critical understanding
- [x] Ensure ai_1_guide_to_docs.md is the only index reference

## Phase G — Validation and delivery
- [ ] Run full test suite
- [~] Update errors.txt with final accomplished list
- [~] Update errors.txt with unresolved questions list
- [ ] Summarize all completed work and questions for user decisions
