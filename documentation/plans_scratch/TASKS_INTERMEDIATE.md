# Intermediate Tasks (Canonical)

Use this file as the single source of truth for intermediate execution tasks.

## Active

### 2026-09-26 Social engine v2 implementation and hosted play

- [ ] Implement the authoritative turn/event and replay contracts with unit and integration scenarios.
- [ ] Implement epistemic gossip provenance, agreements, NPC intentions, drama pacing and validated endings with tests.
- [ ] Run full regression suite, integrate beta, deploy, then personally play Terrace and IU on hosted beta and record findings.

### 2026-09-25 Terrace goal and rival mechanics

- [x] Record all playtest recommendations and the user's Terrace objective in BL-33..37, referring to existing BL-29..32 and BL-22 where those already cover the issue.
- [x] Implement the initial Terrace objective and rival pressure with gender-specific active eligibility and durable offscreen plan/affection weighting; BL-33/34 retain the unfinished mutual-departure ending and fuller rival system.
- [ ] Add regression tests and update game-design documentation, run full offline checks, integrate beta, push, and verify hosted turns. Focused tests and 1198-test suite passed; local desktop Chromium / iPhone WebKit / standalone WebKit goal-card checks passed.

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

- 2026-09-26: Expanded SOCIAL_ENGINE_V2_DESIGN.md with ordered implementation phases, concrete scenario IDs and expected state/knowledge outcomes, hosted acceptance requirements, dependency handoffs, cross-phase campaigns and evidence-based completion records. Documentation-only change; no runtime phase is marked implemented. Checked document structure/whitespace before shipping to beta.

- 2026-09-26: Completed the user-requested social-engine engineering sketch in `SOCIAL_ENGINE_V2_DESIGN.md`, grounded in the current world-model, gossip, promise and extraction code. Specified typed events, atomic response/state commits, observation/assertion/transmission provenance, bounded NPC planning, agreements, drama pacing, migration and mechanical/engagement gates. Indexed it and added BL-38 for cross-cutting authority/epistemic work; existing feature backlogs remain open. Documentation-only scope; validation is document links, whitespace and remote-file verification, not runtime deployment testing.

- 2026-09-25: Personally played 10 Terrace turns on hosted beta `09633b6` and 12 IU turns on `67d9c4d` via the simulator's live chat API. Captured all 26 setup/gameplay responses, public debug, segments, latency and build metadata in a local evidence bundle outside git. Browser simulator was stuck Connecting with an initialization TypeError; protected system prompts were unavailable. Added a dated review with per-turn logic/engagement grades, BL-30 clock divergence, BL-31 missing speaker/presence identity and BL-32 simulator failure; appended live evidence to BL-29. Documentation only; no runtime fix or production deployment claimed.

- 2026-09-25: **Terrace welcome party + beta->prod release a76030a.** Terrace now starts with the player in the kitchen with two opposite-gender housemates (male player greeted by two women, female by two men). The other three housemates are in the living room. The engine stages this, not just the prose: `backend/app/engine/opening_scene.py` with the reusable `opening.welcome_party` config, `GameState.opening_cast`, the focal lens and a first-turn SCENE BRIEF line. The focal character is now persisted across restore. Also shipped: one regeneration when a storyteller draft is empty or echo-only (`807022f`; local Ollama arena, 60 turns per side: blank turns 4 -> 0, NPC echoes 1 -> 0), a unit-only deploy test gate with zero LLM calls (`ea5011c`, confirmed in the Railway build log), and a widened wait for a flaky test (`37bbcb2`). First gate `promote_37bbcb2` FAILED on one Jev "player action fabricated" flag (IU t1-t4). mvp-chat-6b fixed its orphaned speech-tag fragment in `a76030a`; invented player feelings are in BL-29. Offline precheck `promote_a76030a_precheck` PASS (candidate and baseline both a76030a). Hosted gate `promote_a76030a` PASS: IU jev 0.67 / llm 0.50; Six Strangers jev 0.00 / llm 0.50 (12/12 llm ties after retrying three 429'd judge calls); no critical regressions; 24/24 arms. Merged as prod `fa8b9d5` (tree == a76030a); `wait-deploy` and `smoke` exit 0; welcome party verified on prod 4/4. Open: BL-29 (narration retells the player's action and invents feelings), and watch Jev's six_strangers 0.00.

- 2026-09-24: User confirmed the newly installed **StoriesChat Beta** Home Screen app worked on their iPhone after beta install-route repair. Documented the full PWA/mobile UI incident, offline reproduction, standalone layout rules and future verification procedure in `documentation/ai_learnings_mistakes/AI_PWA_IPHONE_WEBAPP_LEARNINGS.md`. The report confirms the new install outcome; individual native-keyboard geometry was not measured on device.

- 2026-09-24: Six Strangers echo and whereabouts fix. Root causes: `drop_player_echo` stopped at a leading short sentence ("Cool!"); the player started at the front entry while NPCs were in the living room, so the prompt said "People present: none"; all 17 names, including unarrived residents, were in the Cast IDs, the speaker enum and self-knowledge. Shipped to beta as `d300ef5` and promoted to prod as `d753f4e` on user request. Offline precheck `promote_d300ef5_precheck` PASS on reliability; prod predates offline routing, so the baseline was origin/beta. Hosted gate `promote_d300ef5` PASS: IU jev 0.5 / llm 0.5; Six Strangers jev 1.0 / llm 0.5; the Jev result is length-confounded (the longer side won 80%, beta +24 words per reply). 24 of 24 arms completed with 0 turn errors. Prod `wait-deploy` and `smoke` exit 0. The post-release live check on prod found the storyteller re-sending the opening's lines every turn. The follow-up fix (repeat filter, one regeneration and a reworded-echo sentence rule) went to beta; its prod promotion is pending user approval. Open: BL-24 (NPC movement), BL-25 (audit quality items).

- 2026-09-24: Designed living-world detective and Terrace conversation mechanics from the beta play findings and current engine/Jev code. Mapped every player requirement to an authority boundary; specified evidence types, NPC schedules and sleep, a turn/context contract, narrow MUST-mention rules, probability/replay, anti-hallucination checks, social handoffs, and rollout proof. Indexed the design; eight document links and code-fence balance verified; documentation-only, no runtime change or deploy claim.

- 2026-09-24: Reproduced the user's stale iPhone install offline with production's root manifest and worker: old `/` shell had a 180px standalone gap, old chat/upload UI, visible tab bar during simulated keyboard focus, 36px map X and no pinch zoom. A separate worker test showed the legacy cache serving the stale `/beta/manifest.json`. Shipped beta install isolation in `f639128c9630dc1e2dd0ad932f6ad351e780f569` (Railway deployment `ac508d48-5a44-437d-808f-6b0be8937cc4`): new uncached `manifest-beta-v2.json`, `/beta/` start/scope/id, **StoriesChat Beta** identity/badge, and Refresh Cache route check. Before push: 1017 repository tests passed/1 expected failure, 129 arena skill tests, 10 Node tests, worker upgrade in Chromium/WebKit, seven local viewport modes, and three interactive modes. Hosted beta health confirmed exact SHA; manifest and page returned no-store; seven hosted viewport modes and three interactive modes passed with zero browser/API errors. Inspected standalone screenshots for the badge, chat, simulated keyboard and large map X. Physical iPhone confirmation remains Active above; an old production icon cannot be repointed by this beta-only change.

- 2026-09-24: Shipped the iPhone PWA and speaker-aware story follow-up to beta in `18ce288` (merged head `c8986ba`; Railway deployment `b003bb74-b7d3-40e6-bf21-0b19247b042f`). Fixed standalone height/safe areas and keyboard transition, home header overlap, map close/pinch zoom, text speeds, Terrace's new-game opening, separated narration and named speaker beats, Jev fallback for unmarked quotes, and async 288px/1254px portraits from the supplied ZIP. A hosted browser pass found old 96px portraits served from cache; versioned their URLs and repeated verification. Local: 1016 repository tests passed/1 expected failure, 129 separate arena skill tests passed, 10 Node tests, legacy-worker upgrade in Chromium/WebKit, seven local viewport modes and three interactive UI modes passed. Hosted: seven viewport modes and three interactive UI modes passed with zero browser/API errors; a real model turn returned eight ordered segments with three named speakers. HTML/worker no-store and beta manifest scope verified. Physical iPhone confirmation remains Active above.

- 2026-09-24: Jev game arena implemented, measured and released. `backend/app/evaluation/` (contracts, rubric, knowledge bundle, blinded evidence, fail-closed Jev judge with order swap, deterministic checks, paired hosted runner with rate-limit resilience, Elo/bootstrap aggregation, mutation + A/A calibration with verbosity probe, JSON/HTML report), CLI `python -m scripts.eval.arena`, `/api/eval/capabilities`, `deployment_id` pinning. Arena-found fixes shipped: NPC echo of the player's lines, markdown in dialogue, third-person/POV confusion. Pilot `arena_pilot_20260923b` (40 pairs): IU beta 10-4; Six Strangers verdict confounded by judge verbosity bias (BL-22/BL-23). Promoted beta `15ce6a8` to prod as `76a0652` (user-approved); prod verified live (health, capabilities, both stories). Open: BL-18..BL-23.

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

### 2026-09-24 PWA and mobile repair checklist

- [x] Switch to beta and pull current origin/beta; persist beta-only convention.
- [x] PWA: no-store HTML/worker/version; content-version JS/CSS; automatic activation, old cache cleanup, foreground update detection; test stale-worker upgrade.
- [x] Confirm startup map has no instructions and tapping maximizes it; brief player-facing location descriptions only.
- [x] Restore/verify bottom Refresh Cache action; remove photo upload control.
- [x] Verify standalone viewport fills phone including bottom navigation.
- [x] House cover for chat/header; individual named portrait bubbles nested in each scene.
- [x] Slow = prior 1x, Normal = 2.5x, Fast = 3.5x; default Normal and persistent choices.
- [x] Full-width My Games resume; swipe reveals accessible X delete button.
- [x] Run regression/full tests and inspect desktop Chromium + iPhone WebKit local screenshots and interactions.
- [x] Merge latest beta and preserve both agents' changes.
- [x] Incorporate user clarification: full manual browser-state reset, automatic deploy updates, short opening, pinch/drag map zoom, clear narrator/speaker/human groups, full-size portrait popup, confirmed delete.
- [x] Retest desktop Chromium, iPhone WebKit, and simulated standalone locally after integration.
- [x] Full regression suite: 1101 passed, 1 expected failure; 9 Node tests; legacy-worker upgrade in Chromium and WebKit.
- [x] Integrated parallel evaluation commits, pushed beta `b3fd435`, verified remote HEAD and Railway deployment `190789fd-8926-4434-9c0d-8d6bc7419a0d` serving that SHA.
- [x] Hosted beta: desktop Chromium, iPhone WebKit and simulated standalone browser flows passed with API calls to `beta-api.storieschat.ai`; screenshots inspected for map, chat, swipe delete and bottom navigation. Live HTML/worker are no-store with matching shell revision `5ff480e89e359392`; beta manifest starts at `/beta/`.

- Local evidence: real Chromium + iPhone WebKit + simulated standalone interaction/screenshot passes; old-worker upgrade passed Chromium/WebKit; 9 Node tests; full pytest 1096 passed / 1 expected failure before final integration.

### 2026-09-24 Claude browser QA skill refresh

- [x] Pull current beta and inspect the existing Claude skill, browser scripts and current test workflow.
- [x] Replace stale viewport-only and missing-JS-harness guidance with real Chromium/WebKit/standalone commands and evidence checks.
- [x] Improve the reusable browser verification script and document how Claude adapts it for future UI changes.
- [x] Validate the skill, script and relevant tests; integrate latest beta; commit and push the documentation/code to beta; verify remote files. Local checks: 1139 pytest passed / 1 expected failure; 9 Node tests; Chromium, iPhone WebKit and simulated standalone baseline and deterministic UI flows passed. Real chat reply currently returns `story master is unavailable`.
- Hosted `1340175`: health reported the pushed SHA; baseline and deterministic UI flows passed in desktop Chromium, iPhone WebKit, and simulated standalone WebKit with `beta-api.storieschat.ai`, zero browser/HTTP/API errors. Screenshots inspected; mobile home header overlap added to BL-13. Mocked chat validates UI rendering only; the external story master was unavailable in the real local path.
