# AI Documentation Index & Catalogue

> **What this doc is for:** The single index of all project documentation. Every doc has a one-line "edit this doc if..." description so you don't have to open every file to find where new information goes. Layout consolidated 2026-09-30: four folders, four top-level files.

## Layout

- **Top level:** this index, [plan/](plan/) (the shared work board: one file per task, claimed through `scripts/work.py`; start at [plan/README.md](plan/README.md); finished tasks are deleted), [backlog/](backlog/) (the backlog: one small file per bug or per few related bugs, each holding `## BL-<n>` sections of open work only; delete a section when it is fixed and the file when it empties; list the folder, open only the file you need; see `/add-and-remove-from-backlog`), [user_corrections.md](user_corrections.md). Agent instructions are in `/AGENTS.md` (the only instruction file).
- **`design/`** — the engineering design docs (as-built plus designed-not-built), one file per subsystem. Each merged file keeps one section per original document with its own status notes. If a section disagrees with the running code, fix the doc (or file a backlog entry if the code is what's wrong). When a piece ships, update its section and delete finished narrative rather than adding "done" logs.
- **`ai_learnings_mistakes/`** — process rules and postmortems, not gameplay or architecture design.
- **`human_north_star_docs/`** — vision only, human-owned. Read `NorthStar.md` before design questions; edit only when asked.
- **`research/`** — supporting material (Terrace source research, artwork prompt). `scripts/build_six_strangers_world.py` reads `research/terrace_house_bgitc_places.md`, so keep that path.
- Finished records (audits, plans, hosted-play and replay reports, review Q&A, the old backlog files) were deleted 2026-09-30; git history has them.

---

## Safety / process (read before coding)

| Doc | Edit this doc if... |
|-----|---------------------|
| [ai_learnings_mistakes/AI_FATAL_MISTAKES.md](ai_learnings_mistakes/AI_FATAL_MISTAKES.md) | ...a production-breaking mistake happens that must never be repeated. |
| [ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md) | ...test runner behavior changes, a new testing pattern is established, or a deploy gate lesson is learned (gitignored `data/` fixtures, live-Jev integration gates, `-m "not integration"`). |
| [ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md](ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md) | ...push/deploy workflow rules change (commit conventions, CI, deploy flow). |
| [ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md](ai_learnings_mistakes/AI_LEARNINGS_INTEGRATION_REQUIREMENTS.md) | ...integration test policies or mock boundaries change. |
| [ai_learnings_mistakes/AI_LEARNINGS_WRITING_INTEG_TESTS.md](ai_learnings_mistakes/AI_LEARNINGS_WRITING_INTEG_TESTS.md) | ...the integration test framework or patterns change. Start here for writing new integ tests. |
| [ai_learnings_mistakes/AI_PWA_IPHONE_WEBAPP_LEARNINGS.md](ai_learnings_mistakes/AI_PWA_IPHONE_WEBAPP_LEARNINGS.md) | ...an iPhone Home Screen install, PWA cache, standalone viewport, keyboard, map, mobile chat or update-reload mismatch needs diagnosis or verification. |
| [ai_learnings_mistakes/AI_TASK_WORKFLOW.md](ai_learnings_mistakes/AI_TASK_WORKFLOW.md) | ...the reasons or rules behind the work board change (what replaced `TASKS_INTERMEDIATE.md`, lease and lock rules). |
| [ai_learnings_mistakes/AI_LOGICAL_BUGS.md](ai_learnings_mistakes/AI_LOGICAL_BUGS.md) | ...a new logic bug is discovered and resolved during an audit. |
| [ai_learnings_mistakes/AI_GAME_STRUCTURE.md](ai_learnings_mistakes/AI_GAME_STRUCTURE.md) | ...the story data model changes or a new file type is added to story directories. |
| [ai_learnings_mistakes/AI_SCORER_SYSTEM.md](ai_learnings_mistakes/AI_SCORER_SYSTEM.md) | ...the debug system, scoring, player-agent loop or grader changes. |
| [ai_learnings_mistakes/AI_UI_WORKFLOW.md](ai_learnings_mistakes/AI_UI_WORKFLOW.md) | ...frontend architecture or UI development patterns change. Its body is a stale March snapshot; use `.claude/skills/ship-and-verify/BROWSER_QA.md` for current browser QA. |
| [ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md](ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md) | ...adding a bracket command or game-mode flag to the chat system. Built around the removed `COMMAND_PATTERNS`; rewrite before next use. |
| [user_corrections.md](user_corrections.md) | ...the user corrects a mistake that should be remembered across sessions. |
| [backlog/](backlog/) | ...work is knowingly deferred or an item is fixed (add a `## BL-<n>` section to the topic file, or delete it; delete the file if it empties). One file per bug or per few related bugs, kept small. |
| [plan/README.md](plan/README.md) | ...the work-board protocol changes (claims, leases, file locks, finishing a task). The sequence is in [plan/ORDER.md](plan/ORDER.md); each task is a `plan/P-<n>-*.md` file you add, claim and delete through `scripts/work.py`. |

## Design docs — `design/`

| Doc | Edit this doc if... |
|-----|---------------------|
| [design/SOCIAL_ENGINE.md](design/SOCIAL_ENGINE.md) | ...the social engine changes: the master character-centred design and its build ledger (section 11a of the first part), the v2 typed action/event/transaction model and release gates, the optional `mode` story schema and ensemble authoring, or cast lifecycle (entry, exit, rotation). Read the master before shared Character/relationship work. |
| [design/WORLD_MODEL.md](design/WORLD_MODEL.md) | ...the world simulation changes: the character object and world location index, `backend/app/engine/world_model/` modules, routines/sleep/off-screen life/commitments, evidence and conversation obligations, or map/atlas behaviour. |
| [design/CHARACTER_MEMORY.md](design/CHARACTER_MEMORY.md) | ...the character graph schema and edge query API, epistemic retrieval and belief injection, the transient buffer, or any data model, schema or field changes (the model inventory). |
| [design/PROMPT_PIPELINE.md](design/PROMPT_PIPELINE.md) | ...the storyteller system prompt structure or injection order, the single-call turn extractor schema/prompt/validation, the message-to-prompt assembly, or prompt layer test coverage change. Source of truth: `backend/app/api/prompt_engine.py` and its tests. |
| [design/JEV.md](design/JEV.md) | ...anything about Jev changes: provider architecture and fallback, the extractor redesign, shared Jev context selection, the `NPC_DECISION_MODE` switch (`rules`/`jev`/`compare`), or the promise-completion judge (`PROMISE_JUDGE_ENABLED`, on by default) and its 2% accuracy gate `tests/backend/integration/test_promise_judge_accuracy.py`. |
| [design/JEV_GAME_ARENA.md](design/JEV_GAME_ARENA.md) | ...the beta-vs-prod arena changes: rubric/weights, judge policy, pairing, rating math, checks, CLI or implementation status. Code: `.claude/skills/promote-to-prod/arena/` (local-only, never deployed); release procedure `/promote-to-prod`. `ARENA_LLM_ENABLED` defaults off. |
| [design/PLATFORM.md](design/PLATFORM.md) | ...deployment, hosting, environment variables, auth/OAuth/persistence, UI screens and CSS, the integration playback test layer, or Python coding conventions change. Known stale spots: says the frontend is on Namecheap (FastAPI serves it), missing about 13 env vars (`JEV_*`, `TYPESAFE_*`, `WORLD_MODEL_ENABLED`, `PROMISE_JUDGE_ENABLED`), JWT lifetime (code uses 365 days), UI cast/journal/skip screens undocumented. |
| [design/TERRACE_HOUSE.md](design/TERRACE_HOUSE.md) | ...anything about the Terrace House mode (`7_six_strangers`) changes: the win (leave together), the loss (director cut), earned romance, the player fact ledger, confessions, clocks, endings, judges panel or context focus. Also holds the real-show research (Appendix A). |
| [design/ROADMAP_NOT_BUILT.md](design/ROADMAP_NOT_BUILT.md) | ...a designed-but-unbuilt plan changes: backend restructure (`SessionFactory`/`SnapshotCodec`/`TurnService`), measured optimizations, frontend modularization, delivery/CI, core gameplay systems (quests, difficulty, post-milestone loop), NPC sidequests. Move a section into the matching `design/` doc when it ships. |

## Vision (human-owned, read-only unless asked)

| Doc | Edit this doc if... |
|-----|---------------------|
| [human_north_star_docs/NorthStar.md](human_north_star_docs/NorthStar.md) | ...the long-term product vision or user experience goals change. Vision only, no technical details. |
| [human_north_star_docs/StoriesChatNorthStar.txt](human_north_star_docs/StoriesChatNorthStar.txt) | ...the owner's original north-star text changes (human-owned). |
| [human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md](human_north_star_docs/epistemic_state/EpistemicStateJennieIntegrationTestExample.md) | ...the epistemic state example for the Jennie scenario needs updating. |

## Research (supporting material)

| Doc | Purpose |
|-----|---------|
| [research/terrace_house_bgitc_places.md](research/terrace_house_bgitc_places.md) | Source places for the Six Strangers/Terrace atlas; read by `scripts/build_six_strangers_world.py`. |
| [research/six_strangers_artwork_prompt.md](research/six_strangers_artwork_prompt.md) | The artwork prompt used for the Six Strangers assets. |
| `research/terrace_house_regional_reference.png` | Regional reference image for the map. |
