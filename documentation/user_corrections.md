# User Corrections Log

> **What this doc is for:** Log of user corrections to prevent repeating mistakes. Edit this doc when the user corrects a mistake that should be remembered across sessions.

Patterns from user feedback to prevent repeating mistakes.

## 2026-09-28: Always push after a beta merge

After merging/integrating work into beta, always push the integrated HEAD to origin/beta and verify the remote commit, even for documentation-only work. Do not ask again or finish at a local merge/commit. This supersedes the documentation-only exception for merged work; standalone documentation edits without a merge retain that exception unless the user requests a push or another clone needs them.

## 2026-09-28: One BL-39-led proposal, hybrid Jev and 5% fallback ceiling

Owner selected consolidation: BL-39 supplies the Character → Heart → Bond model and A–J roadmap; BL-38 correctness contracts are mandatory within it, not another architecture. Use [the master](design/SOCIAL_ENGINE.md). Keep independent opening/answer/receipt fixes shippable.

NPC judgment is hybrid: extraction LLM plus Jev propose nuanced choices; character/engine rules enforce feasibility, authority and consent. Pure character methods accept application-supplied proposals without provider I/O. Do not silently replace nuanced decisions with deterministic utility alone.

Owner accepted a provisional 5% visible canned/constrained fallback ceiling and delegated practical judgment. Treat as a measured rollout gate with zero critical source/consent violations, not a claimed achieved rate. Continue gameplay-first latency priorities and the two-LLM-attempt cap. Panelists use camera/public evidence, never subject private state; panel prose shares the response call.

## 2026-09-27: Gameplay first; two LLM calls plus Jev and visible thinking dots

Latest user direction supersedes the earlier unresolved latency question and any immediate 1–2-second optimization gate: current response speed feels good. Focus on gameplay, measure latency, and defer speed optimization/true streaming. Keep at most two LLM calls per gameplay turn: extraction LLM assisted by Jev, then response LLM. Use Jev extensively for supported work with bounded batching and separate latency/cost accounting; do not replace the extraction LLM with local-only intent parsing or add a third LLM verifier/repair/background call.

Preserve animated three-dot thinking feedback before results. Source inspection confirms it exists in `frontend/index.html` and is shown before fetch, hidden on reply/error. BL-38 specifies lifecycle QA and client/server timing measurement built on the existing `StageTimer`; source inspection is not a new hosted verification. Playtest arena judging stays off.

## 2026-09-27: Arena judging is not needed for playtest review

The user explicitly turned arena judging off for playtest review and said it is not important to that work. Do not keep proposing a judging pilot as a prerequisite. They described an arena-judge gameplay mechanic as Terrace House-specific for now, reusable but default-off for other games. Keep that desired gameplay capability distinct from the developer build-comparison arena and runtime semantic validation; no corresponding existing gameplay implementation was verified in this review. This clarification does not authorize starting arena runs or modifying runtime flags.

“Response time” was clarified as the real-world wait for the complete game reply, not story time. The user did not select a latency target; do not treat the illustrative 10/20/30-second options as requirements.

## 2026-09-27: Plausible drama, engine dialogue and character uncertainty

The user clarified the reusable simulation proposal after review:

- Prioritize enjoyable, heightened but plausible dramatic scenes over mundane realism, including humor and characters knowingly breaking routine obligations with consequences.
- Before a skip would miss important known events, list them and request confirmation. Engine-to-player messages and player-to-engine commands must be parenthesized and distinct from in-world dialogue.
- NPC autonomy is tunable with a moderate default. Longer elapsed game time permits more cascading independent changes (butterfly effects); closing the app still freezes simulation time.
- Intentional lying is allowed and should generally have observable hints, varying with character skill and circumstances. Skilled liars can be harder to read; nervousness is not proof.
- Tentative plans and misunderstandings are valid gameplay. Preserve actual speech/decisions separately from each character's interpretation; never manufacture player consent or mutual agreement.

Engineering contracts, tuning and acceptance scenarios are in [BL-38](BACKLOG.md), especially the confirmed owner decisions and scenarios O19–O23. These are design requirements, not claims that the runtime already implements them.

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

**Added to:** `documentation/design/PLATFORM.md`, `documentation/design/PLATFORM.md`.

## 2026-03-21: Use one canonical intermediate task file

**What happened:** Intermediate task tracking was spread across ad-hoc files/folders (`tasks/`), creating inconsistency and stale leftovers.

**Rule:** Intermediate execution tasks must be tracked in one canonical file: `documentation/TASKS_INTERMEDIATE.md`. Agents must consume this file before non-trivial work, update it during execution, and clean up completed entries at task end.

**Added to:** `documentation/ai_learnings_mistakes/AI_TASK_WORKFLOW.md`, `documentation/AI_DOC_INDEX_CATALOGUE.md`, `.gitignore`.

## 2026-09-18: Human characters are personas; default persona is canonical and reuseable

**What happened:** User clarified that NPCs and player-controlled humans must be treated differently. The human character path is always a `persona`, not an NPC or a generic "player" avatar, and the app should support exactly two persona modes for now: a temp per-game persona and a built-in default persona.

**Rule:** Use the term `persona` for the human-controlled character layer, reserve `NPC`/`character` for story cast members, and default to the server-stored Paul Dingus persona unless the user chooses a temp persona. Keep the system reusable across both active games and avoid custom persona creation/storage in this pass.

**Added to:** `backend/app/personas/persona_store.py`, `backend/app/engine/state.py`, `frontend/index.html`.

## 2026-09-24: Deploys must never call OpenAI (or any LLM API)

**What happened:** The Dockerfile passed `OPENAI_API_KEY` as a build arg so the Railway build-time test gate ran `@pytest.mark.integration` tests against the real API on every deploy. User: "we dont run any requests to openAI during deployment ... it should be unit test only unless otherwise configured."

**Rule:** The deploy build runs unit tests only (`-m "not integration"`), with blank LLM keys and `TESTS_BLOCK_LLM_NETWORK=1` (conftest blocks LLM hosts). Real-API tests must carry `@pytest.mark.integration`. Live tests at build time only via explicit `RUN_LIVE_LLM_TESTS=1`. Never add evaluation or LLM calls to the Dockerfile, CI unit job, or app startup.

**Added to:** `Dockerfile`, `tests/conftest.py`, `.github/workflows/tests.yml`, `pytest.ini`, `documentation/ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md`, `documentation/design/PLATFORM.md`.


## 2026-09-29 — State trackers must never miss what happened

**Correction:** A word-overlap check failed to notice the player had made Riko's promised tea ("Here you go, Riko"), so she kept nagging about it. Owner: an NPC forgetting is fine; the game not registering something that happened is not. A mechanic that can't reach ~99% on that error direction should be removed in favour of plain conversation context. Semantic judgments (completion, name/nickname dedup) belong to Jev, not regex.

**Rule:** For any "did X happen / is X still open" tracker, uncertainty resolves toward "done / stop reminding". Before shipping, measure the "happened but not registered" rate on a labeled eval; below 99%, delete the mechanic.
