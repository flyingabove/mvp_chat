# AGENTS.md: instructions for every agent in this repository

This is the **only** instruction file. Claude Code, Codex, Copilot and humans all follow it. `.claude/CLAUDE.md` and
`.github/copilot-instructions.md` only point here: never put instructions in them. Skills live in
`.claude/skills/<name>/SKILL.md` (the `.agents/skills/` entries are stubs that point to them). If anything in the
documentation disagrees with the running code or with this file, fix the document in the same change.

## 0. Start of every session (non-negotiable)

1. **Your first words are "Yes. Anointed One"**, before any planning, thinking or other response. Call the owner "Anointed
   One" and include those words in every response. (The owner uses this to know you read this file.)
2. Read `documentation/AI_DOC_INDEX_CATALOGUE.md` (the one documentation index; every entry says "edit this doc if...").
   It holds architecture decisions and past mistakes; then read only the docs for your area. For any **design** question,
   read `documentation/human_north_star_docs/NorthStar.md` first (human-owned: never edit it unless asked).
3. Skim `documentation/user_corrections.md` for lessons relevant to your area, and list `documentation/backlog/`.
4. Python work uses the **conda environment `storieschat`**; install whatever you need there.
5. `git pull --rebase origin beta`, then `python scripts/work.py status` and follow section 1.

## 1. How work is organised: the plan

All agents share one board, described in [documentation/plan/README.md](documentation/plan/README.md) (read it once; it is
short). Order and stage gates: [documentation/plan/ORDER.md](documentation/plan/ORDER.md).

- The plan is one file per task in `documentation/plan/P-<n>-<slug>.md`. `python scripts/work.py claim` takes the next ready
  task (or `claim P-07`), prints its spec, and locks its files for 4 hours (`renew` to extend). Claims live on the `work`
  branch, never on `beta`, so taking a task does not redeploy anything.
- **Never work on an unclaimed plan task.** If the owner gives you a specific request instead, do that; if it overlaps a
  claimed task, say so before touching those files.
- Finishing a task: one commit that contains the code and tests, deletes the task file, and updates the docs and the
  backlog item it closes; the message ends with `Closes P-07` (and `Closes BL-n` only when fully fixed). Push to `beta`, then
  `python scripts/work.py done P-07`.
- **Deferred or discovered work** becomes a `## BL-<n>` section in a small topic file in `documentation/backlog/` (use the
  `/add-and-remove-from-backlog` skill: open work only; delete the section, and the file when it empties, in the fixing
  commit) or a new plan task. Never a lingering checkbox, never a "done" log. Git history is the record.
- `documentation/TASKS_INTERMEDIATE.md` and the root `tasks/` folder are retired; do not create or read them. Plans for
  non-trivial work go in the task file, the backlog item or the relevant `design/` doc.
- If you are blocked by something outside your task: `release` it, write the blocker as a backlog item, take another task.

## 2. Working in the repository

- **Work on `beta` only.** Never create or work on another branch (the `work` claims branch is touched only by
  `scripts/work.py`). `prod` is production: never push to it without the owner's explicit request (section 4). There is no
  `main`; do not create or mention one.
- **One checkout per agent.** Each agent uses its own clone (the Codex clone is the sibling `mvp_chat_for_codex_only`). Do not
  edit or clean another agent's working tree. If another writer changes your checkout unexpectedly, preserve the work and
  investigate before overwriting. Use checkpoint commits on `beta` to protect substantial progress.
- **Parallel agents push to `beta` at the same time.** `git pull --rebase origin beta` before you start and again before you
  push. If new commits arrived, read their commit messages (they say why), preserve both agents' intent, and **re-run the
  tests**. Never force-push, never blanket `--ours`/`--theirs`. A pre-push hook rebases onto `beta` for you (details in
  `.claude/skills/promote-to-prod/SKILL.md`): commit and push as separate commands, and push `prod` alone.
- Stage explicit files, never `git add -A` over unrelated work or runtime data. Keep credentials and `.env*` ignored.
- Commit messages must let another agent resolve a merge conflict: **WHY**, **WHAT CHANGED** (per file) and **SIDE EFFECTS**
  (format: `documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md`). End with the attribution line your tool requires.

## 3. Tests, shipping and done

- **Every code change gets unit tests.** A bug fix starts with a test that reproduces the bug; a feature adds tests of the
  new behaviour. All tests pass before pushing (`python -m pytest tests/ -x -q`; the deploy gate runs
  `-m "not integration"` with blank LLM keys). **No skipped tests** except `xfail` (`pytest.skip` and `skipif` are banned and
  turn into failures). If a resource such as a database will not start locally, fix the test or the environment; never skip
  or push red.
- **Use `/ship-and-verify` for every non-trivial change, no exceptions, never ask**: 1) implement with tests, test and view
  locally, 2) push to `beta`, poll the real Railway deploy, 3) exercise the feature on the live beta site. Passing the local
  suite is necessary, not sufficient. **Any UI-visible change is checked in a real browser before committing** (desktop
  Chromium and iPhone-sized WebKit, locally, then again on beta); the procedure is in the skill. If the browser tooling is
  missing, say so; never claim a browser or iOS check you did not do.
- **Never mark a task done without proving it works**: run the tests, read the logs, diff behaviour against `beta` when it
  matters. Ask whether a staff engineer would approve it.
- **Completion rule.** At the end of every task that changes code, story data, frontend, config, tests or scripts: commit the
  task files and push the integrated `beta` HEAD to `origin/beta`, and verify the pushed commit is on the remote, **before
  reporting completion** (standing owner authorization; do not ask). Always push after merging or integrating into `beta`,
  including documentation-only merges. A standalone documentation-only change with no merge may stay committed locally until the
  next code push unless the owner asks or another clone needs it: report it as "committed locally, not pushed". Every push
  redeploys Railway beta and invalidates running arena gates, so avoid discretionary documentation pushes during arena runs.
  Documentation-only work needs no runtime `/ship-and-verify` checks; do not claim a deployment was tested when only docs were
  pushed.
- If a real failure blocks shipping, report the exact failure. Never describe unpushed work as finished.

## 4. Deploy: beta first, production on request

- Always push to `beta`. After pushing, tell the owner and wait. Only when the owner explicitly says to promote: use
  `/promote-to-prod` (verify the deployed beta, free offline precheck, hosted arena gate, merge, push, live smoke).
- `prod` is production (Railway deploys from it). Treat it as sacred. **Never `railway down`** to cancel one stuck deployment
  (it removes the latest deployment, possibly the live one).
- The game is not hosted locally for players. Only the debug evaluator (`scripts/scorer`, port 8899) and the offline arena run
  it locally, for testing. Production OAuth redirect URIs are hosted-only; for local play use the guest bypass (section 6).
- **Deploys and CI never call an LLM.** The deploy build runs unit tests only.
- **Only OpenAI costs money. Gemini and Jev are free** (owner, 2026-10-01): use them without asking for simulations, pilot
  seasons, rubric calibration, evals and live checks, within sensible rate limits. Never run anything on OpenAI
  (`LLM_PROVIDER=openai`, an OpenAI judge or player, the OpenAI-backed parts of the arena) without asking first, and cap it.
  The LLM arena stays disabled (`ARENA_LLM_ENABLED`) because its players and judges can be OpenAI: check which providers a run
  would use, and ask before enabling it. Providers: Gemini + Jev by default, OpenAI + Jev as the (paid) alternative; Ollama
  is switched off unless `OLLAMA_ENABLED=1`.

## 5. Owner rules for the product (standing permissions and design principles)

- **Real names and trademarks:** StoriesChat is non-commercial. The owner gives explicit permission to use real people's names
  (for example the Terrace House cast in `7_six_strangers`) and any trademarks in stories and docs. Do not rename characters or
  strip trademarks for that reason. Revisit only if the app becomes commercial.
- **Adult content:** the owner gives explicit, standing permission for explicit adult content between adult characters (Terrace:
  on camera stays show-real, behind closed doors anything goes at the player's lead). Do not soften it, add warnings, or treat a
  provider refusal as a design constraint; route such scenes to an API that will write them.
- **A request to change a specific game is, by default, a request to improve the engine.** Improve the character object and the
  engine so the interaction emerges for every game, and let the story's JSON supply data and tuning. Every backlog item and plan
  task is classified **C** (engine or character object: the default), **A** (authored text or data) or **B** (game-only
  mechanic: strongly avoided in every game, a last resort, acceptable only when essential and the generic form cannot express
  it, kept in its own story-specific module and reported to the owner). The full rubric and the rules for B are in
  `/add-and-remove-from-backlog`.
- **Social designs centre on the character object** (`Person`: personality, goals, stances, mind). Weighted rule tables are an
  internal tool for deriving those, never the headline architecture or a per-mechanic module.
- **No house log or event journal for players.** Players learn only through the story. (An admin-only season watch mode is
  allowed.) NPCs are autonomous off-screen. The game is turn-based: the clock moves only with the player's turn or a headless run.
- **Hybrid judgment, at most two LLM calls per player turn** (response plus extraction, Jev-assisted); never a deterministic
  rule alone for nuanced social judgment. State trackers may forget but must never miss what happened: for "did X happen",
  uncertainty resolves toward done, ≥99% on that error direction or the mechanic is dropped; semantic matching goes to Jev with
  a measured bar. Details: `documentation/user_corrections.md`.
- **Tone, every mode:** real life, dramatized; plausible but very dramatic, by tunable nudges and never scripted outcomes.

## 6. Auth and local credentials (read this first if auth breaks)

- Real Google OAuth and JWT credentials are in `.env.test` at the project root (gitignored). The app does not auto-load it via
  dotenv: `backend/app/config/credentials.py` (`_load_env_test_once`) loads it lazily on the first read of `OPENAI_API_KEY`,
  `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` or `JWT_SECRET`, triggered by importing `backend.app.config.settings`. If Google
  auth fails locally, confirm `.env.test` exists with those vars populated. Railway/CI env vars always win. Never commit secrets.
- `.kiro/` holds only the docs MCP server config and a reindex hook, nothing auth-related. Auth code: `backend/app/auth/` and
  `backend/app/config/`. Production redirect URIs: `https://storieschat.ai/auth/google/callback` and
  `https://beta-api.storieschat.ai/auth/google/callback`; localhost is deliberately not registered.
- **Guest bypass ("Play as Guest"):** the `✦ Play as Guest` pill (`#home-guest-pill`) and the login modal's `Continue as Guest` set
  `localStorage.storieschat_skip_login = "1"` and mint a guest UUID (`storieschat_guest_id`, plus a 1-year cookie).
  `startGame(...)` checks `isSkipLoginEnabled()` and sends `X-Guest-Id` instead of a JWT. Backend: `get_current_user_or_guest`
  produces `sub="guest:<uuid>"`; sessions persist under `/data/users/guest_<uuid>/sessions/...`. Explicit sign-in clears the flag.

## 7. How to think and work

- **Plan before non-trivial work** (3+ steps or an architectural decision): write a detailed design or spec first, share it,
  then implement. Do planning as an ordinary response; **never switch into a tool-enforced plan mode** and stay in
  bypass-permissions mode. If something goes sideways, stop and re-plan.
- **Use subagents liberally when your tool has them**: research, exploration and parallel analysis go to subagents, one task per
  subagent, to keep the main context clean.
- **Simplicity first, minimal impact:** touch only what is necessary. **No laziness:** find root causes, no temporary fixes, senior
  developer standards. For a non-trivial change ask "is there a more elegant way?"; if a fix feels hacky, implement the elegant
  one. Skip this for simple, obvious fixes. Challenge your own work before presenting it.
- **Bug reports:** just fix them; point at the logs, errors and failing tests, and resolve them without hand-holding.
- **Ask questions** when a decision is genuinely the owner's, but consult the docs first for technical questions.
- **After any correction from the owner:** add the pattern to `documentation/user_corrections.md` (and your own memory, if your
  tool has one) with a rule that prevents the same mistake. Review those lessons at session start.
- When a design or architecture decision is made or changed, update the matching doc in the same commit. Edit the doc, never add
  a history section: finished work is deleted from task and backlog files.

## 8. Skills

Skills are the detailed procedures behind sections 1 to 4. Open the one that matches your task before you start:
- `/ship-and-verify` (`.claude/skills/ship-and-verify/SKILL.md`): implement, test, deploy to beta, prove it live. Any non-trivial change.
- `/add-and-remove-from-backlog` (`.claude/skills/add-and-remove-from-backlog/SKILL.md`): classify work as A, B or C, add items,
  close them, and groom (clean) the backlog after tasks finish.
- `/promote-to-prod` (`.claude/skills/promote-to-prod/SKILL.md`): beta to production, only when the owner explicitly asks.

Browser automation for hosted checks uses the Playwright MCP plugin (`playwright@claude-plugins-official`) or the Python
Playwright scripts under `scripts/`; if neither is available, say so instead of skipping the check.
