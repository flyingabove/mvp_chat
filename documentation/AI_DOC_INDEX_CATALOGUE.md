# AI Documentation Index & Catalogue

> **What this doc is for:** The single index of all project documentation. Use this to find the right doc to read or edit. Every doc has a one-line "edit this doc if..." description so you don't have to open every file to figure out where new info goes.

## Folder map (reorganized 2026-09-26)

- **`reference/`** — as-built docs. What's described should match the running code. If you find a mismatch, fix the doc (or file a backlog item if the code is what's wrong).
- **`proposals/`** — designed, not built. Read before starting the work; update in place while building; once shipped, move the built parts into the matching `reference/` doc and delete or trim the proposal.
- **`archive/`** — finished records and superseded designs. Read-only history; don't add new work here.
- **`backlog/`** — one file per open, actionable item. Delete a file when it's fixed (see `/add-and-remove-from-backlog`).
- **`BACKLOG.md`** — legacy items BL-01..BL-25 only. No new entries; move an item into `backlog/` when you start working on it.
- **`ai_learnings_mistakes/`** — process rules and postmortems, not gameplay/architecture design.
- **`human_north_star_docs/`** — vision only, human-owned.
- **`auto_update_docs/`** — deleted 2026-09-26 (was stale since January, described a pre-rewrite "Terminal Frontend", and no generator script exists in the repo to refresh it). Recreate it only if a real doc-generation tool is added.
- **`research/`**, **`plans_scratch/`** — supporting material, unchanged by this reorg.

A doc's status is either implied by its folder (`reference`/`proposals`/`archive`) or spelled out inline when a single doc is a mix (mostly-done docs kept in `reference/` still note their open items in the table below).

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

## Prompt Engine & Turn Orchestration — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [STORYTELLER_PROMPT_REDESIGN.md](reference/STORYTELLER_PROMPT_REDESIGN.md) | ...the storyteller system prompt structure or injection order changes. **Mostly built; still open: the post-response rewrite validator isn't wired into runtime, and the doc's "no numbers leak into the prompt" and "canon-correction removed" claims are stale — see `backend/app/engine/prompt_builder.py`'s CANON CORRECTION block and relationship baseline lines.** |
| [SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md](reference/SINGLE_CALL_TURN_EXTRACTOR_DESIGN.md) | ...the extractor schema, prompt, or validation logic changes. **The "exactly one extractor call" framing is stale: Jev batches and a post-turn fact-extraction pass now also run.** |
| [MESSAGE_TO_PROMPT_FLOW_TRACE.md](reference/MESSAGE_TO_PROMPT_FLOW_TRACE.md) | ...the prompt assembly pipeline (message → LLM prompt) changes. **Missing steps: Jev context selection, world-model turn begin/end, sleep/time-skip, commitments, `post_with_retry`. Update before trusting it as a trace.** |
| Source of truth code: `backend/app/api/prompt_engine.py` | |
| Canonical tests: `tests/backend/app/api/test_prompt_engine.py` | |

## Epistemic & Memory Systems — `reference/`

The shared Jev retrieval, weighted sampling and narrative-context system is
documented in [JEV_DYNAMIC_CONTEXT_DESIGN.md](reference/JEV_DYNAMIC_CONTEXT_DESIGN.md).
Broad retrieval, Jev relevance judgment and power-sampling are implemented
behind the `context_selection` Jev task flag. **Still not built:** clue and
relationship-callback pacing/cooldowns, the F/C/D/A dimension scoring, and the
planned `engine/context_selection/` module split (everything currently lives
in one module). See [backlog/BL-27](backlog/BL-27-memory-mechanisms-small-problems.md)
for the selector-exception fallback gap.

| Doc | Edit this doc if... |
|-----|---------------------|
| [EPISTEMIC_ENGINE_DESIGN.md](reference/EPISTEMIC_ENGINE_DESIGN.md) | ...knowledge retrieval, belief injection, or epistemic rules change. **A stronger invariant validator and full belief-graph projection remain undone; see `CHARACTER_WORLD_MODEL_REDESIGN.md` P8/P9 for the superseding direction.** |
| [TRANSIENT_BUFFER_DESIGN.md](reference/TRANSIENT_BUFFER_DESIGN.md) | ...transient buffer eviction, injection, or scoring logic changes. |
| [CHARACTER_GRAPH_DESIGN.md](reference/CHARACTER_GRAPH_DESIGN.md) | ...the character graph schema, edge types, or query API changes. **`summarize_relationships()` and the room-dynamics prompt section are documented but not wired at runtime; the `rel_updates` STATE-tag design was superseded by the extractor.** |
| [LAYER_COVERAGE_MAPPING.md](reference/LAYER_COVERAGE_MAPPING.md) | ...new prompt layers are added or test coverage for layers changes. **Missing the world-model, language-style, pacing and canon-correction layers — add them.** |

## World Model & Character Systems — `reference/`

`backend/app/engine/world_model/` is the current, additive world-simulation
layer (routines, sleep, off-screen life, commitments, engine-chosen speakers).
It sits alongside — and does not replace — `character_graph.py`, `BeliefState`
and the knowledge index, which are all still live.

The staged successor is specified in [SOCIAL_ENGINE_V2_DESIGN.md](reference/SOCIAL_ENGINE_V2_DESIGN.md):
typed actions/events, transactional turns, gossip provenance, character-local
beliefs, agreements, NPC intentions, drama selection, migration and release
gates. Section 18 distinguishes implemented slices from remaining v2
acceptance work — check it before assuming any given piece is built. A dated
hosted-play review of the in-progress build is in
[archive/SOCIAL_V2_HOSTED_PLAY_2026_09_26.md](archive/SOCIAL_V2_HOSTED_PLAY_2026_09_26.md).

| Doc | Edit this doc if... |
|-----|---------------------|
| [SOCIAL_ENGINE_V2_DESIGN.md](reference/SOCIAL_ENGINE_V2_DESIGN.md) | ...the v2 typed action/event model, transactional turn boundary, gossip provenance, character-local beliefs, agreements, NPC intentions, drama selection, or migration/release gates change. **Check §18 for what's actually implemented vs. still a gap before citing this as done.** |
| [CHARACTER_WORLD_MODEL_REDESIGN.md](reference/CHARACTER_WORLD_MODEL_REDESIGN.md) | ...the problems list (P1-P14), the character object, world location index, events, memories, relationship edges, context projection, or the build order changes. **Steps 0-8 shipped in `backend/app/engine/world_model/`. Still open: P4 (NPC↔NPC edges never reach the prompt), P9 (no `character.project()`), P13 (dead stores `epistemic_log`/`observation_log`/`tells`/`disposition` not removed).** |
| [CHARACTER_WORLD_MODEL_IMPLEMENTATION_PLAN.md](reference/CHARACTER_WORLD_MODEL_IMPLEMENTATION_PLAN.md) | ...a world-model module, integration point, story-data schema (`world_model` section), test list, or known limit changes. Source of truth code: `backend/app/engine/world_model/` (entry: `turn.py`); tests: `tests/backend/app/engine/world_model/`. |
| [CAST_LIFECYCLE_DESIGN.md](reference/CAST_LIFECYCLE_DESIGN.md) | ...characters can enter, leave, rotate through capacity-limited slots, or lifecycle eligibility/persistence changes. **Automatic prose-to-transition extraction (§5, §10) shipped (`0662670`, `635fb4c`) — the doc still calls it "next phase".** |
| [LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md](reference/LIVING_WORLD_INVESTIGATION_AND_CONVERSATION_DESIGN.md) | ...evidence types, NPC routines/sleep, context obligations, initiative, or social-scene handoffs change. **About half shipped (routines, speakers, threads, off-screen life, gossip, contact) — this doc's own header still says "not implemented"; treat the header as stale. Not built: the evidence case graph, Jev scoring of off-screen outcomes (hook exists, unwired), waking a sleeping NPC.** |
| [WORLD_ATLAS_DESIGN.md](reference/WORLD_ATLAS_DESIGN.md) | ...map metadata, coordinates, routes or map UI behavior changes. Built and current. |
| [SOCIAL_MODE_DESIGN.md](reference/SOCIAL_MODE_DESIGN.md) | ...the optional `mode` story-JSON schema, the mode prompt layer, or ensemble/slice-of-life (`social_sim`) authoring guidance changes. **References to the deleted reference story ("The Common Room") and "no schedules" are stale — routines now exist.** |

## Not Yet Built — `proposals/`

The [2026-09-28 engine-plan review](research/ENGINE_PLAN_ROUND_TWO_REVIEW_2026_09_28.md) compares BL-38 with the sibling checkout's BL-39, records historical latency/Jev evidence, and identifies unresolved authority and NPC-decision choices. Read it before implementing shared character/relationship ownership. Detailed first-round Q&A is preserved in [the review record](research/ENGINE_PLAN_FIRST_REVIEW_QA_2026_09_28.md); BL-38 section 15 now contains only current decisions and navigation.

| Doc | Edit this doc if... |
|-----|---------------------|
| [GAME_DESIGN_SYSTEMS.md](proposals/GAME_DESIGN_SYSTEMS.md) | ...core gameplay systems change (world state, time, quests, difficulty, win conditions). **World state and time are built; quests, difficulty/rerolls, decay, and the post-milestone loop ("winning doesn't end the game" — currently it does, `prompt_engine.py` sets `over=True`) are not.** |
| [LEAVE_TOGETHER_WIN_CONDITION.md](proposals/LEAVE_TOGETHER_WIN_CONDITION.md) | ...the Terrace "convince a partner to leave with you" win, the generic goal card / ending screen, the `leave_together` extractor decision, or the partner acceptance thresholds change. **Not built; closes BL-33. Replaces the regex detectors in `world_model/romance.py`.** |
| [NPC_SIDEQUEST_DESIGN.md](proposals/NPC_SIDEQUEST_DESIGN.md) | ...NPC behavior, sidequest triggers, or quest logic changes. **Not built at all; reconcile with `world_model/threads.py` (personal threads/commitments) before resuming this, since they now cover similar ground.** |
| [BL-38: reusable object-centered simulation engine](backlog/BL-38-social-engine-authority-and-epistemic-transactions.md) | ...the proposed character-owned voice/context, object ownership, agreements/travel, evidence, NPC objectives, per-game policies, migration or acceptance gates change. **Detailed engineering proposal expanded 2026-09-27; existing components and uncommitted attendance work are distinguished from proposed APIs. Runtime completion is not claimed.** |
| [PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md](proposals/PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md) | ...the `SessionFactory`/`SnapshotCodec`/`TurnService`/`PlayerView`/`StoryDefinition.validate()` contracts, the `application/` package layout, or the handler decomposition order change. **Not started; `prompt_engine.py` is 3,700+ lines.** |
| [PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md](proposals/PHASE_3_MEASURED_OPTIMIZATION_DESIGN_2026_09_22.md) | ...any of the 11 optimization rows' design, measurement method, or ship/drop threshold changes. **1 of 11 done differently (source-aware memory merge, BL-26), 1 dropped by design (cache registry/BM25), the rest not started.** |
| [PHASE_5_FRONTEND_MODULARIZATION_DESIGN_2026_09_22.md](proposals/PHASE_5_FRONTEND_MODULARIZATION_DESIGN_2026_09_22.md) | ...the frontend module extraction order, the asset-manifest schema, or the motion-settings design changes. **Not started; the asset-manifest idea was superseded by content-hash cache-busting (`b792f44`) — update this doc's §5 to match rather than building the original design.** |
| [PHASE_6_DELIVERY_CI_DESIGN_2026_09_22.md](proposals/PHASE_6_DELIVERY_CI_DESIGN_2026_09_22.md) | ...the Dockerfile/CI/dependency-lock design, the startup-readiness fix, or the index-fingerprint mechanism changes. **Not started, except the index fingerprint already existed before this doc was written (`fingerprint.py`, 2025-12) — the doc missed it.** |

## Tests & Integration Playback

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_LEARNINGS_RUNNING_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md) | ...test runner behavior changes or new testing patterns are established. |
| [AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md](ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md) | ...integration test policies or mock boundaries change. |
| [AI_LEARNINGS_WRITING_INTEG_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_WRITING_INTEG_TESTS.md) | ...the integration test framework, patterns, or requirements change. **Start here for writing new integ tests.** |
| [INTEGRATION_TEST_PLAYBACK_DESIGN.md](reference/INTEGRATION_TEST_PLAYBACK_DESIGN.md) | ...the playback system architecture or UI changes. **The browser playback UI was removed from the frontend (`21e0fc1`); only the scenario/runner/API layer remains built.** |

## Story & Content Authoring

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_GAME_STRUCTURE.md](ai_learnings_mistakes/AI_GAME_STRUCTURE.md) | ...the story data model changes or a new file type is added to story directories. **Example still cites the deleted `jennie_murder_mini` story — update the example.** |
| Authoring invariant code: `backend/app/engine/authoring_checklist.py` | |

## UI & Frontend — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [UI_REDESIGN_2026.md](reference/UI_REDESIGN_2026.md) | ...UI screens, components, CSS system, or navigation changes. **Full 2026 design spec, but several claims are stale: chat does have a persistent tab bar now (hidden only while the keyboard is open), sessions are no longer localStorage-only (`/api/user/sessions` + SQLite), and playback is no longer reachable from `/debug`. Cast, Journal, Skip Ahead and persona onboarding aren't documented at all.** |
| [AI_UI_WORKFLOW.md](ai_learnings_mistakes/AI_UI_WORKFLOW.md) | ...frontend architecture, build process, or UI development patterns change. **Body is a stale March snapshot (references a removed `COMMAND_PATTERNS` system); use `.claude/skills/ship-and-verify/BROWSER_QA.md` for current browser QA.** |
| [AI_CREATE_NEW_FLAG.md](ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md) | ...adding a new bracket command or game mode flag to the chat system. **Also built around the removed `COMMAND_PATTERNS` — needs a rewrite before next use.** |

## Scorer / Debug System — `reference/`

The [2026-09-26 social-v2 hosted play review](archive/SOCIAL_V2_HOSTED_PLAY_2026_09_26.md) records ten fresh Terrace turns and ten IU turns against beta `1045464`, with the complete raw exchanges stored locally. It identifies clock, private-plan, unknown-speaker, player-agency, evidence-source and repeated-clue failures, and distinguishes subsequent local corrections from hosted proof.

The [2026-09-27 beta replay](reference/SOCIAL_V2_BETA_REPLAY_2026_09_27.md) records ten more hosted turns per story on beta `9db4b8f`, including improved chronology and clue deduplication plus remaining false player-source attribution, broken compound movement/wait commands, and a missed Terrace coffee date. Its new repairs require their own deployed replay.

The proposed controlled beta/prod evaluation system is documented in
[JEV_GAME_ARENA_DESIGN.md](reference/JEV_GAME_ARENA_DESIGN.md). Implemented in
observational mode as local-only tooling in `.claude/skills/promote-to-prod/arena/`
(the doc's §13/§14 file paths are stale — it says `backend/app/evaluation/`,
the real location is `arena/`). Server receipts/snapshots and human
calibration are still open: [backlog/BL-19](backlog/) / BL-20. `ARENA_LLM_ENABLED`
now defaults off (`67d9c4d`) — not yet reflected in the doc.

| Doc | Edit this doc if... |
|-----|---------------------|
| [AI_SCORER_SYSTEM.md](ai_learnings_mistakes/AI_SCORER_SYSTEM.md) | ...the debug system, scoring, player-agent loop, or grader changes. |
| [JEV_GAME_ARENA_DESIGN.md](reference/JEV_GAME_ARENA_DESIGN.md) | ...the beta-vs-prod arena changes: rubric/weights, judge policy, pairing, rating math, checks, CLI, or its §13 implementation status. Code: `.claude/skills/promote-to-prod/arena/` (local-only, never deployed), CLI `python .claude/skills/promote-to-prod/arena_cli.py`, release procedure `/promote-to-prod`. |

## Data Models — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [DATA_MODEL_INVENTORY.md](reference/DATA_MODEL_INVENTORY.md) | ...any data model, schema, or field is added or changed. **Stale in several places (says "4 relationship dimensions", there are 5; missing `CastLifecycleState`, `SceneContext`, `SessionChunkStore`, the Jev decision types, `CommitmentUpdate`) — due for a refresh.** |

## Infrastructure & Deployment — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [INFRASTRUCTURE.md](reference/INFRASTRUCTURE.md) | ...deployment, hosting, environment variables, or infrastructure changes. **Stale: says the frontend is hosted on Namecheap (FastAPI serves it directly now); missing ~13 env vars including all `JEV_*`/`TYPESAFE_*` and `WORLD_MODEL_ENABLED`.** |
| [AUTH_AND_PERSISTENCE_DESIGN.md](reference/AUTH_AND_PERSISTENCE_DESIGN.md) | ...auth flow, session storage, OAuth redirect URI policy, or localhost-vs-hosted login boundaries change. **Stale: says JWTs last 30 days, code uses 365 (`settings.py`); missing the `/journal` endpoint and the world-model/cast-lifecycle DB tables.** |

## Coding Standards — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [PYTHON_CODING_STYLE_GUIDE.md](reference/PYTHON_CODING_STYLE_GUIDE.md) | ...Python coding conventions or style rules for this project change. **The "no leading underscore in function names" rule is violated by ~42% of functions in `backend/app` — either relax the rule or treat this as a real cleanup backlog item, don't leave the doc contradicting the code.** |

## Vision (Human-Owned, Read-Only Unless Asked)

| Doc | Edit this doc if... |
|-----|---------------------|
| [NorthStar.md](human_north_star_docs/NorthStar.md) | ...the long-term product vision or user experience goals change. **Vision only, no technical details.** Goals with no design doc or code yet: NPCs that can exploit/betray the player, new-stories/shared-world-history across players. Goals designed but not built: post-milestone loop, hidden quests, clue decay (see the Not Yet Built section above). |
| [EpistemicStateJennieIntegrationTestExample.md](human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md) | ...the epistemic state example for Jennie scenario needs updating. |

## Archive / Historical (Read-Only Reference)

| Doc | Purpose |
|-----|---------|
| [ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md](archive/ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md) | The reuse/correctness/performance/Jev master plan. Phases 0A, 1 and 4 (Jev plumbing) shipped; Phases 2, 3, 5, 6 are unstarted — tracked now as `proposals/` docs and the backlog, not here. Its own execution log only covers 0A/1.3 and is stale. |
| [CODEBASE_AUDIT_AND_REUSE_PERFORMANCE_JEV_PLAN_2026_09_21.md](archive/CODEBASE_AUDIT_AND_REUSE_PERFORMANCE_JEV_PLAN_2026_09_21.md) | Source audit behind the plan above. Fully superseded by it; kept for provenance only. |
| [PHASE_0B_BASELINE_NOTES_2026_09_22.md](archive/PHASE_0B_BASELINE_NOTES_2026_09_22.md) + [PHASE_0B_BASELINE_2026_09_22.json](archive/PHASE_0B_BASELINE_2026_09_22.json) | Finished performance baseline. Its follow-up list duplicates `backlog/BL-15` — treat BL-15 as the live tracker. |
| [SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md](archive/SIX_STRANGERS_AUDIT_PROPOSAL_2026_09_19.md) + [SIX_STRANGERS_LIVE_AUDIT_2026_09_19.json](archive/SIX_STRANGERS_LIVE_AUDIT_2026_09_19.json) | Phases 1-4 all shipped (see `BACKLOG.md` Done section for commits). Still referenced by `BACKLOG.md` as evidence — leave in place. |
| [IOS_UI_SMOOTHNESS_PLAN_2026_09_19.md](archive/IOS_UI_SMOOTHNESS_PLAN_2026_09_19.md) | Most items shipped; open rows (placeholder buttons, debug menu visible to players, zoom lock, no IME guard, no draft persistence, no Skip button) are tracked under `backlog/BL-13`, not here. |
| [SPEAKER_DIALOGUE_UI.md](archive/SPEAKER_DIALOGUE_UI.md) | Superseded by `frontend/dialogue.js`'s per-speaker portraits and Slow/Normal/Fast speeds — this doc describes an earlier single-bubble design. |
| [BETA_MANUAL_PLAY_REVIEW_2026_09_25.md](archive/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md) | Dated observational report: 10 Terrace + 12 IU manually chosen turns, logic/engagement grades, evidence for BL-30 through BL-32. Later playtests should be separate dated reports, not edits to this one. |
| [SOCIAL_V2_HOSTED_PLAY_2026_09_26.md](archive/SOCIAL_V2_HOSTED_PLAY_2026_09_26.md) | Dated hosted-play review of the in-progress social engine v2 build (two 10-turn guest sessions on Terrace). Later social-v2 playtests should be separate dated reports, not edits to this one. |
| [ARCHIVE_EPISTEMIC_REDESIGN.md](archive/ARCHIVE_EPISTEMIC_REDESIGN.md) | Historical epistemic redesign notes. Its `TurnContract`/forbidden-fact and `MemoryTrigger` ideas were never built and still have no home — read before designing an evidence-lock or unlock-rule system. StoryPackage v2 was abandoned; ignore it. |
| [ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md](archive/ARCHIVE_AUDIT_NORTH_STAR_GAPS_2026_02_20.md) | Historical audit of NorthStar gaps. Most gaps are still open (see `human_north_star_docs/NorthStar.md` row above) — read the current status there, not this doc's original claims. |

## Verification Ledger — `reference/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [ERRORS.md](reference/ERRORS.md) | ...a doc/code discrepancy is found or resolved. Several entries are still open (`CharacterIndexBundle.chunks` still `List[dict]`, backward-compat aliases still present); the recorded test counts (266/262) are long outdated (suite is now 1000+ tests) — don't trust the numbers, just the open/closed status of each row. |
