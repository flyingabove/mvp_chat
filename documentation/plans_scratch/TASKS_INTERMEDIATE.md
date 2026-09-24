# Intermediate Tasks (Canonical)

Use this file as the single source of truth for intermediate execution tasks.

## Active

### Jev game arena implementation (design: `model_output_docs/JEV_GAME_ARENA_DESIGN.md`)

Package: `backend/app/evaluation/` (pure core, I/O at the edges). CLI: `scripts/eval/arena.py`.

- [x] **P1 Judge foundation (offline, no network in tests)**
  - [x] `contracts.py` — frozen dataclasses: `TargetIdentity`, `PersonaSpec`, `ScenarioSpec`, `ExperimentManifest` (+ `manifest_hash`), `TurnRecord`, `ArmTranscript`, `EpisodePair`, `DimensionVerdict`, `EpisodeVerdict`, `JudgeCallRecord`.
  - [x] `rubric.py` — `Dimension` (id, weight, critical, instructions, A/B/tie/insufficient_evidence criteria, 0-4 bands), `Rubric` (+ `rubric_hash`), `DEFAULT_RUBRIC` (6 dims, weights 25/20/20/15/15/5).
  - [x] `knowledge.py` — `GameKnowledgeBundle.from_story(story_id)` (canon facts w/ IDs + known_by, characters, rules/goal, world atlas nodes/edges) + `bundle_hash`.
  - [x] `evidence.py` — `EvidencePacketBuilder`: numbered spans, relevant-fact selection (entity mention match), blinding (strip URLs/SHAs/model names), quoted-text fencing, token-budget guard (< 32k state).
  - [x] `judge.py` — `PairwiseJudge` protocol; `JevPairwiseJudge` (A/B + B/A separate requests via `JevClient`, bounded transport retry on same input, strict validation fail-closed -> unresolved, order reconciliation); `FakeJudge` for tests.
  - [x] `aggregate.py` — pure stats: dimension vote -> episode vote (0.55/0.45 margin), unresolved-could-flip check, stratified p, Elo delta (unbounded at 0/1), seeded cluster bootstrap CI, pessimistic/optimistic sensitivity, `AdvisoryDecision`.
  - [x] `checks.py` — `CorrectnessCheck` protocol + deterministic checks usable from observational data: target error/empty reply, secret-leak (unearned canonical-fact phrase in reply), version drift, repetition stall.
  - [x] Tests for every module (order remap, malformed Jev answers, Elo math p=0.6 -> +70.4, bootstrap determinism, injection text stays quoted).
- [ ] **P2 Control & observability (server side, minimal)**
  - [x] Beta pin identity: `deployment_id` (RAILWAY_DEPLOYMENT_ID) in build info, since CLI deploys carry no SHA.
  - [x] `GET /api/eval/capabilities` (versioned contract; operator-only).
  - [ ] (moved to BACKLOG BL-19) Per-turn receipt fields in `/api/chat` for operator requests (build commit, turn index, world clock, location, cast) so drift + state checks work.
  - [x] BACKLOG: controlled init / snapshot export-restore / idempotency keys (belongs with PHASE_2 SessionFactory/SnapshotCodec).
- [x] **P3 Matched runner**
  - [x] `targets.py` — `TargetAdapter` protocol; `HostedTargetAdapter` (guest-id sessions, `/api/chat`, version pin check each turn); `FakeTarget` for tests.
  - [x] `players.py` — `PlayerPolicy` protocol; `LLMPlayer` (public brief only, reuses debug_engine brief/persona conventions), `ScriptedPlayer`; 5 personas from the design.
  - [x] `store.py` — `ArtifactStore`: atomic JSON/JSONL writes under `data/eval_arena/<experiment_id>/`, resume by completed arm IDs.
  - [x] `runner.py` — `ArenaRunner`: pair generation, balanced randomized order, equal budgets, spend/turn/wall-clock ceilings, cancellation, timeout classification.
  - [x] `scripts/eval/arena.py` CLI: `run`, `judge`, `report`.
- [ ] **P4 Validate measurement**
  - [x] `calibration.py` — mutation generators (secret leak, fabricated player action, speaker swap, shortened reply, injected judge instruction), A/A identical-transcript tie check, sensitivity report.
  - [x] Human-label file format + agreement report; BACKLOG the ~200 human labels (owner action).
  - [ ] Pilot: small paired run beta vs prod (observational), report cost/variance.
- [ ] **P5 Report & results view**
  - [x] `report.py` — JSON + self-contained HTML report (SHAs, headline Elo/CI, per-story/persona, critical regressions, unresolved coverage, cost, latency, blinded transcript drill-down).
  - [x] Docs: index entry, AI_SCORER_SYSTEM cross-link, DATA_MODEL_INVENTORY.

### Terrace in the City mobile/PWA and six-resident correctness

- [x] Add reachable cache-clearing Update App navigation action and simplify text-speed choices.
- [x] Eliminate iOS standalone safe-area gap and inspect desktop/mobile screenshots before shipping.
- [x] Randomize valid starting five-NPC roster, enforce player-bedroom opening variants, and retain atomic same-gender replacements.
- [x] Regenerate the world-map artwork without any guest-room representation; show the artwork automatically without location descriptions and open it full-screen when tapped, then deploy beta and live-test.

### Six Strangers researched atlas and isolated Codex checkout

- [x] Clone latest beta into `mvp_chat_for_codex_only`; create `codex/six-strangers-world-atlas`.
- [x] Restore artwork and reusable map/location/route models without touching the shared checkout.
- [x] Model all supplied research IDs, uncertainty, area containers, and estimated travel relationships.
- [x] Finish reusable map UI and verify desktop/mobile behavior locally (Chromium + iPhone 13 WebKit; no page errors or failed requests).
- [ ] Run the full suite, integrate latest beta changes, and retest as needed.
- [ ] Commit, deploy beta, and verify live artwork, data, and interactions.

- [x] Finalize the two-story catalog: keep only IU Murder Mystery and Six Strangers, delete stale inactive games, and align runtime tests to the active catalogue.
- [x] Keep the server-backed default persona system and temp persona flow for the active titles.
- [ ] Push the final beta-ready branch after the live validation step.

## Consumed History

- 2026-09-23: Implemented dynamic optional-memory selection on current beta: source-balanced broad authored/session retrieval, per-candidate Jev relevance Noul scoring, visibility filtering, deterministic anchor plus seeded no-replacement power sampling, and configurable `JEV_CONTEXT_SELECTION_ALPHA` defaulting to 1.5. The path is gated behind `TYPESAFE_ENABLED=true` and `JEV_ENABLED_TASKS=context_selection`; deterministic fallback preserves game turns if Jev is unavailable. Verification: 24 relevant post-merge tests pass. The full suite stops at existing `test_extraction_outbox_row_marked_done_after_successful_extraction`, which leaves its background outbox row pending; it reproduced before the feature test and is outside this change. Beta push and remote branch verification completed; hosted Railway deployment was still serving pre-feature commit `0c9eca7` while polling.

- 2026-09-23: Updated the dynamic-context design with proposed backend constant `JEV_CONTEXT_SELECTION_ALPHA = 1.5`, fractional exponents, validation, uniform-sampling semantics and replay metadata. Documentation-only clarification; runtime setting remains to be implemented with the selector. Verified whitespace and integrated latest beta before pushing; remote verification follows the push.

- 2026-09-23: Completed `JEV_DYNAMIC_CONTEXT_DESIGN.md` for unified mystery/social memory selection, subtle callbacks and controlled randomness. Inspected current retrieval/provider contracts and official TypeSafe documentation; verified seven relative document links, balanced code fences and whitespace. Indexed the design and integrated current origin/beta before shipping. Documentation-only scope; no runtime behavior or live gameplay testing claimed. Remote beta verification is performed after this commit's push and reported in the task response.

- 2026-09-23: Pushed Jev arena design `181d618` and persistent beta completion instruction `82123ad` to `origin/beta`. Fetched the remote and verified design ancestry, document presence and the AGENTS.md rule. Documentation checks passed; no runtime code changes or runtime QA claimed.

- 2026-09-23: Completed Jev game arena research/design against beta `3ffecea` on `codex/jev-game-evaluation-design`. Added `documentation/model_output_docs/JEV_GAME_ARENA_DESIGN.md` and indexed it. Specifies paired adaptive games, response forks, complete world evidence, calibrated Jev judgments, independent correctness gates, Elo-equivalent intervals, costs and implementation acceptance criteria. Documentation only; no runtime implementation, paid model runs or deployment. Validation: source/API schema review, repository integration-path checks and `git diff --check`.

- 2026-09-21: Single-bubble dominant-speaker presentation completed and deployed to beta in `0043948` (Railway deployment `90f2b537-63d8-454f-a5b8-de17aab77f7f`).
	- Restored one bubble per AI reply while retaining structured speaker metadata for reliable attribution.
	- The canonical speaker with the greatest total spoken text supplies the avatar; ties use first appearance.
	- Narration, unknown/side characters, and characters without dedicated art use the game cover.
	- Replaced the Terrace in the City cover with an optimized, realistic Tokyo house image.
	- Verification: `768 passed, 1 xfailed`; four Node renderer tests; local and hosted desktop/390×844 browser passes; hosted console clean; live health endpoint reported `0043948`.

- 2026-03-21: Initialized canonical intermediate-task workflow file.
- 2026-03-22: Save/resume hardening complete.
	- Added persisted runtime snapshots for `character_graph`, `character_locations`, `last_turn_*`, and `session_chunk_store` facts in `state_json`.
	- Added restore logic to rehydrate runtime graph edge state and session BM25 chunks after cache miss/restart.
	- Synced Home-page resume sources to backend `/api/user/sessions` cache so Home and My Games resume the same sessions.
	- Verification: `C:/Users/Christian/miniconda3/envs/storieschat/python.exe -m pytest -q` -> `414 passed, 1 xpassed`.
- 2026-03-22: Cloudflare routing/control-plane documentation hardening complete.
	- Documented current path-based Cloudflare behavior for `storieschat.ai` (`/beta/*` to beta origin, catch-all to prod origin).
	- Added explicit tamper vectors showing how domain-preserving reroutes to different Railway projects can happen via Cloudflare changes.
	- Added required controls: least-privilege tokens, change approval, audit log review, synthetic origin-identity checks, and incident response steps.

## Cleanup Rules (Quick Reference)

1. Keep only open items in `Active`.
2. Move completed lists to `Consumed History` at task completion.
3. If this file exceeds ~200 lines, archive older consumed entries to `ARCHIVE_TASKS_INTERMEDIATE.md`.
