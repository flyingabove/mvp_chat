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

## Touches

backend/app/api/prompt_engine.py; engine/world_model/{turn,model,character,epistemics,agreements,projection}.py; engine/character_graph.py; session persistence/receipts; backend/frontend regression and migration fixtures.