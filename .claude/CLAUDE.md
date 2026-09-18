```md
## Workflow Orchestration


## IMPORTANT: Always read and follow instructions in documentation\AI_DOC_INDEX_CATALOGUE.md before starting any task.
This file contains critical project knowledge, architecture decisions, and previous mistakes to avoid.
If instructions every conflict with what is designed in the doc, always update the doc to reflect the correct behavior.
- so that I know you read this file. Before any planning or thinking or response. First respond with "Yes. Anointed One". Be sure to call me "Anointed One" always when you respond. Always include these words in every response. 
- Conda env should always use storieschat install everything you need on that

### Auth / Local Dev Credentials (READ ME FIRST IF AUTH BREAKS)
- Real Google OAuth + JWT credentials live in `.env.test` at project root (gitignored).
- The Python app does NOT auto-load `.env.test` via dotenv. It is loaded lazily by `backend/app/config/credentials.py` (`_load_env_test_once`) on first read of `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, or `JWT_SECRET`.
- If Google auth "doesn't work" locally: confirm `.env.test` exists and the three Google/JWT vars are populated; the loader is triggered automatically from `settings.py` (so `from backend.app.config.settings import ...` is enough).
- Railway/CI env vars always win over `.env.test`. Never commit secrets.
- Steering from kiro (`.kiro/` folder) only holds the docs MCP server config + a reindex hook — nothing auth-related. If you're hunting for auth settings, look in `backend/app/auth/` and `backend/app/config/`.
- Production OAuth redirect URIs are hosted-only (`https://storieschat.ai/auth/google/callback`, `https://beta-api.storieschat.ai/auth/google/callback`). Localhost is intentionally NOT registered; for local play, use the guest bypass instead.

### Guest Bypass ("Play as Guest")
- Frontend exposes a `✦ Play as Guest` pill on the home top-bar (`#home-guest-pill`) and a `Continue as Guest` button in the login modal.
- Clicking either sets `localStorage.storieschat_skip_login = "1"` and mints a guest UUID into `localStorage.storieschat_guest_id` + a 1-year cookie.
- `startGame(...)` checks `isSkipLoginEnabled()` — when true, the login modal is skipped and the chat call uses `X-Guest-Id` instead of a JWT.
- Backend: `get_current_user_or_guest` dependency accepts the guest header and produces `sub="guest:<uuid>"`. Sessions are persisted under `/data/users/guest_<uuid>/sessions/...`.
- Explicit sign-in (`profile-auth-btn` or `?token=` callback) clears the bypass flag so JWT is used going forward.

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately — don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- Always ask questions, but always consult docs first for technical questions
- For design questions and decisions at minimum always read documentation\human_north_star_docs\NorthStar.md first to see if the design question is not obvious from the north start design. 
- After ANY correction from the user: update or create `documentation/user_corrections.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes — don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests — then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

### 7. Testing & Pushing Changes (Multi-Agent Workflow)
- Always add good unit test for any code changes. If it's a bug fix, add a test that reproduces the bug before fixing it. If it's a new feature, add tests that verify the new behavior.
- **Multiple agents work on `beta` simultaneously.** Follow this flow:
  1. `git pull --rebase origin beta` **before starting work**
  2. Make changes + run tests
  3. `git pull --rebase origin beta` **again before pushing** (catch parallel pushes)
  4. If new code was pulled in step 3, **run tests again** to catch integration issues
  5. Commit with detailed message (see AI_LEARNINGS_PUSHING_CODE.md for format), push
- **Commit messages must be detailed enough for another agent to resolve merge conflicts.** Include WHY, WHAT CHANGED (per file), and SIDE EFFECTS. See `documentation/ai_learnings_mistakes/AI_LEARNINGS_PUSHING_CODE.md` for full format.
- If merge conflicts arise, read the other agent's commit messages to understand intent, then preserve both agents' work. Never blindly pick "ours" or "theirs".
- All tests must pass before pushing. No skipped tests except xfail.
- If a test fails to spin up a resource such as a database locally, fix the test or the test environment. Don't skip the test or push with a failing test.

### 8. Deploy Flow — Beta First, Prod on Request
- **ALWAYS push to `beta` branch first.** Never push directly to `prod` without explicit user approval.
- After pushing to `beta`, inform the user and wait for them to confirm before merging to `prod`.
- The `prod` branch is production (Railway auto-deploys from it). Treat it as sacred.
- Only merge `beta` → `prod` when the user explicitly says to push to prod.
- There is NO `main` branch. It was deleted. Do NOT create or reference `main`.

### 9. Use the `/ship-and-verify` skill for shipping changes
- Any non-trivial change (backend or frontend) should follow
  `.claude/skills/ship-and-verify/SKILL.md`: implement with tests → verify
  offline → push to beta → poll the real Railway deploy → actually exercise
  the feature on the live hosted beta site (browser-level via the Playwright
  MCP plugin when available, curl-level against the real endpoints
  otherwise) before calling it done. Passing the local test suite is
  necessary, not sufficient — BL-03 shipped a bug that only existed in the
  deployed/browser context, not in pytest.
- Browser automation: the official Playwright MCP plugin
  (`playwright@claude-plugins-official`) should be installed
  (`claude plugin list` to check). If its tools aren't showing up in a
  session, it needs a Claude Code restart/reconnect to load — say so rather
  than silently skipping live browser verification.

## Task Management (任务管理)
1. **Plan First:** Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan:** Check in before starting implementation
3. **Track Progress:** Mark items complete as you go
4. **Explain Changes:** High-level summary at each step
5. **Document Results:** Add review section to `tasks/todo.md`
6. **Capture Lessons:** Update `tasks/lessons.md` after corrections
7. **Track Deferred Work:** Whenever work is knowingly deferred instead of finished (a finding fixed only partially, a manual owner action, a follow-up), add an entry to `documentation/BACKLOG.md`. Check it at session start alongside the doc index; move an item to its "Done" section (with the closing commit SHA) once actually resolved.

## Core Principles (核心原则)
- **Simplicity First:** Make every change as simple as possible. Impact minimal code.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid introducing bugs.
```