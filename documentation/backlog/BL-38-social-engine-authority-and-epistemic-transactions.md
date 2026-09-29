# BL-38 — Social-engine correctness and atomic transactions

- **Type:** bug / tech-debt
- **Found:** 2026-09-26, social engine audit and hosted play.
- **Severity:** high: unreliable consent, provenance, retries and context boundaries.
- **Status:** open. Architecture consolidated on 2026-09-28; no runtime fix claimed.

## Problem

Partial protections do not complete durable turn/reply atomicity, scoped testimony/beliefs, source/answer checks, single-writer relationships or old-save migration. Gameplay failures overlap BL-35, BL-36 and BL-37.

## Fix direction

The sole target design is [BL-39 — canonical character-centered simulation engine](BL-39-character-centric-social-engine.md). It incorporates these contracts and retains O01–O29, including O26a. Do not implement BL-38 as another Character architecture.

- Sections 3–5: ownership, provenance, hybrid Jev decisions, validation and atomic state/outcome/reply commits.
- Sections 6 and 8: agreements/consent, clocks, knowledge, configuration and migration.
- Section 10: independent backend receipt slice reusing frontend request_id without waiting for A–J.
- Close this item only when applicable correctness/replay/privacy/configuration/migration gates have evidence. Related gameplay items stay independently open.

## Why deferred / cautions

This consolidation implements no runtime fix. Preserve existing work and migrate with adapters. Keep one social-state writer, at most two LLM calls, no hidden-state leakage, no fabricated consent and no post-display act_confirmed repair. Atomic storage and model annotations alone do not prove prose semantics.

The [first-review Q&A](../research/ENGINE_PLAN_FIRST_REVIEW_QA_2026_09_28.md) and [second-review evidence](../research/ENGINE_PLAN_ROUND_TWO_REVIEW_2026_09_28.md) are historical. Current answers are at the end of the master.

**Receipt slice O15/O24 (2026-09-28, hosted-verified on `3dbbe90` with `scripts/verify_turn_receipts.py` 8/8):** `turn_receipts(session_id, request_id)` stores input hash + exact reply in the same `BEGIN IMMEDIATE` transaction as the state CAS; a failed receipt insert rolls the state back. The chat handler replays any of the latest 200 committed requests (not only the last), rejects a reused id with different text (409), replays after restart, and replays when a racing duplicate loses the CAS or hits the receipt key. New-game requests now get receipts (a retried new game no longer re-draws a different cast) and reset the old playthrough's receipts; persona fields are part of the input hash. Legacy `last_request_*` columns stay in sync and remain readable. Tests in `test_repos.py` and `test_prompt_engine.py`; that file's API tests now use an isolated SQLite file instead of `./data/storieschat.db`. **Still open:** the JSONL transcript (`ConversationRepo.append_turns`) and fact-extraction outbox enqueue happen after the commit, so a crash between them loses transcript/extraction work though never state or reply; early-return command paths (bracket toggles, previews, errors) write no receipt; a failed new-game save is still logged and swallowed.

## Touches

backend/app/api/prompt_engine.py; engine/world_model/{turn,model,character,epistemics,agreements,projection}.py; engine/character_graph.py; session persistence/receipts; backend/frontend regression and migration fixtures.