# User Corrections Log

> **What this doc is for:** Log of user corrections to prevent repeating mistakes. Edit this doc when the user corrects a mistake that should be remembered across sessions.

Patterns from user feedback to prevent repeating mistakes.

## 2026-09-24: Documentation-only changes do not need a beta push

The user narrowed the 2026-09-23 rule below: a change that touches only
documentation or Markdown instruction files does not need to be pushed to
beta. Commit it locally on `beta`; it goes out with the next code push. Why:
every push redeploys Railway beta (about 10 minutes) and invalidates any
running arena precheck or gate. Never push documentation alone during an arena
run. Code, story data, frontend, config, tests and scripts still follow the
rule below. Updated `AGENTS.md` (End-of-task completion rule) and
`.claude/CLAUDE.md` §7.

## 2026-09-23: Always finish repository work by pushing to beta

The Jev arena design was left in a local feature-branch commit. The user corrected
this: every completed repository task, including design/docs, must be pushed to
beta without another permission request. Added an end-of-task completion rule to
`AGENTS.md`: integrate latest beta, run applicable checks, commit explicit task
files, push `HEAD:beta`, and verify remote inclusion before reporting completion.
This is a persistent agent instruction, not an installed executable lifecycle hook.
Never force-push or infer authorization to deploy to production.

## 2026-09-20: Isolate Codex from other agents' working trees

The user requested a full independent `mvp_chat_for_codex_only` clone after an
external reset removed in-progress map work from the shared checkout. Codex uses
a dedicated `codex/` feature branch there, fetches/merges current `origin/beta`
before work and before shipping, preserves both agents' intent in conflicts,
and verifies local and deployed beta behavior. Do not reset or clean the other
agents' `mvp_chat` checkout. This supersedes older direct-on-beta implementation
guidance for Codex; beta remains the deployment target.

## 2026-03-08: Don't auto-push to production

**What happened:** After fixing SVG thumbnails and hero CSS, I pushed to both `beta` AND `main` (production) without asking.

**Rule:** Always push to `beta` first. Only merge to `prod` when the user explicitly requests it. `prod` triggers Railway production deploy — treat it as sacred.

**Added to:** CLAUDE.md section 8, MEMORY.md workflow preferences.

## 2026-03-12: Localhost is debugger-only

**What happened:** OAuth/login guidance included localhost callback assumptions, but user clarified localhost should only be used for debug tooling.

**Rule:** Treat localhost as debug/scorer-only (`/beta/debug`). App login and Google OAuth callbacks should be documented and configured for hosted domains.

**Added to:** `documentation/model_output_docs/AUTH_AND_PERSISTENCE_DESIGN.md`, `documentation/model_output_docs/INFRASTRUCTURE.md`.

## 2026-03-21: Use one canonical intermediate task file

**What happened:** Intermediate task tracking was spread across ad-hoc files/folders (`tasks/`), creating inconsistency and stale leftovers.

**Rule:** Intermediate execution tasks must be tracked in one canonical file: `documentation/plans_scratch/TASKS_INTERMEDIATE.md`. Agents must consume this file before non-trivial work, update it during execution, and clean up completed entries at task end.

**Added to:** `documentation/ai_learnings_mistakes/AI_TASK_WORKFLOW.md`, `documentation/AI_DOC_INDEX_CATALOGUE.md`, `.gitignore`.

## 2026-09-18: Human characters are personas; default persona is canonical and reuseable

**What happened:** User clarified that NPCs and player-controlled humans must be treated differently. The human character path is always a `persona`, not an NPC or a generic "player" avatar, and the app should support exactly two persona modes for now: a temp per-game persona and a built-in default persona.

**Rule:** Use the term `persona` for the human-controlled character layer, reserve `NPC`/`character` for story cast members, and default to the server-stored Paul Dingus persona unless the user chooses a temp persona. Keep the system reusable across both active games and avoid custom persona creation/storage in this pass.

**Added to:** `backend/app/personas/persona_store.py`, `backend/app/engine/state.py`, `frontend/index.html`.

## 2026-09-24: Deploys must never call OpenAI (or any LLM API)

**What happened:** The Dockerfile passed `OPENAI_API_KEY` as a build arg so the Railway build-time test gate ran `@pytest.mark.integration` tests against the real API on every deploy. User: "we dont run any requests to openAI during deployment ... it should be unit test only unless otherwise configured."

**Rule:** The deploy build runs unit tests only (`-m "not integration"`), with blank LLM keys and `TESTS_BLOCK_LLM_NETWORK=1` (conftest blocks LLM hosts). Real-API tests must carry `@pytest.mark.integration`. Live tests at build time only via explicit `RUN_LIVE_LLM_TESTS=1`. Never add evaluation or LLM calls to the Dockerfile, CI unit job, or app startup.

**Added to:** `Dockerfile`, `tests/conftest.py`, `.github/workflows/tests.yml`, `pytest.ini`, `documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md`, `documentation/model_output_docs/INFRASTRUCTURE.md`.

