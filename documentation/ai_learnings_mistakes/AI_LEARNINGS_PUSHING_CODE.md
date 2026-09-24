AI learnings: pushing code & adding command flags
==================================================

> **What this doc is for:** Rules for pushing code (commit conventions, CI checks, deploy flow). Edit this doc when push/deploy workflow rules change.


PART 1 — HOW AI PUSHES CODE (GIT PERMISSIONS)
----------------------------------------------

### Why it works out of the box

This repo uses HTTPS remotes:
  origin  https://github.com/flyingabove/mvp_chat.git

The machine has Git Credential Manager (credential.helper=manager) installed.
When the human (Christian) previously logged into GitHub via the browser or
Git CLI, Credential Manager cached an OAuth / PAT token in Windows Credential
Store. That token is automatically used for all HTTPS git operations.

Result: any process on this machine — including an AI agent running in a
terminal — can `git push` without extra auth setup.

### Why AI pushes silently but human gets an account-selection popup

Git Credential Manager for Windows (v1.18.5) is installed system-wide
(C:/Program Files/Git/etc/gitconfig → credential.helper=manager).

This machine's Windows Credential Store has MULTIPLE GitHub credentials:
  - git:https://flyingabove@github.com       → flyingabove
  - git:https://github.com                   → flyingabove
  - git:https://christiansgao@github.com     → christiansgao
  - (plus several older repo-specific PATs)

When multiple credentials exist for the same host (github.com):
  • GUI-capable terminal (VSCode, Windows Terminal, PowerShell):
    GCM detects GUI availability and pops up an account-selection dialog.
  • Non-interactive shell (AI agent / Claude Code):
    GCM cannot show a GUI, so it silently picks the first matching
    credential (flyingabove for github.com) and proceeds with no prompt.

### How the human can fix the account-selection popup

Option A — Remove duplicate credentials (recommended):
  1. Open Windows Credential Manager:
     Control Panel → User Accounts → Credential Manager → Windows Credentials
  2. Find entries starting with "git:https://github.com" or
     "git:https://christiansgao@github.com"
  3. Delete the ones you don't need for this repo. Keep only:
       git:https://github.com → flyingabove
     (or the one matching the flyingabove account)
  4. If you still need christiansgao for other repos, keep that
     credential but make sure the flyingabove one is URL-specific:
       git config --global credential.https://github.com/flyingabove.username flyingabove

Option B — Set GCM to never prompt (use cached credential silently):
  Run:  git config --global credential.interactive never
  This tells GCM to never show GUI prompts; it will use whatever
  credential is cached. If no credential is cached, the push will
  fail with 401 instead of prompting (which is fine — you can then
  run `git push` from a browser-capable terminal once to cache it).

Option C — Use the gh CLI for auth (cleanest long-term solution):
  1. Install GitHub CLI: https://cli.github.com
  2. Run:  gh auth login
     Choose: GitHub.com → HTTPS → Login with a web browser
  3. This stores a single OAuth token via GCM and avoids conflicts.
  4. Verify:  gh auth status

### Step-by-step: what the AI does to push (MULTI-AGENT AWARE)

Multiple AI agents may be working on the `beta` branch simultaneously.
Every push must account for other agents' changes that may have landed
since you last pulled. Follow these steps exactly:

```
┌─────────────────────────────────────────────────────┐
│  1. PULL latest           ← before you start coding │
│  2. Make code changes                               │
│  3. Run tests             ← verify YOUR changes     │
│  4. PULL + MERGE again    ← catch parallel pushes   │
│  5. Run tests AGAIN       ← only if step 4 merged   │
│  6. Push                                            │
│  7. Verify                                          │
└─────────────────────────────────────────────────────┘
```

#### Step 1 — Pull latest before starting work

```bash
git pull --rebase origin beta
```
This ensures you start from the latest code. Other agents may have
pushed since your conversation began.

#### Step 2 — Make your code changes

Write code, edit files, do your thing.

#### Step 3 — Run tests (verify your changes)

```bash
python -m pytest tests/ -x -q
```
All tests must pass before proceeding. Fix any failures.

#### Step 4 — Pull + merge again (catch parallel pushes)

```bash
git pull --rebase origin beta
```

**If new commits were pulled in:**
- This means another agent pushed while you were working.
- If there are **merge conflicts**, read the conflicting commit messages
  (`git log --oneline -5`) to understand the other agent's intent.
  Resolve conflicts by preserving both agents' intentions.
- Proceed to Step 5 (re-test).

**If already up to date:**
- No new commits landed. Skip Step 5, go straight to Step 6.

#### Step 5 — Re-test after merge (ONLY if Step 4 pulled new code)

```bash
python -m pytest tests/ -x -q
```
This catches integration issues between your changes and the other
agent's changes. If tests fail, diagnose whether it's your code or
theirs and fix accordingly.

#### Step 6 — Stage and commit

Stage specific files (never `git add -A` — avoids secrets / binaries):
```bash
git add frontend/index.html backend/app/api/prompt_engine.py
```

Commit with a HEREDOC message (preserves multi-line formatting):
```bash
git commit -m "$(cat <<'EOF'
fix(scope): short summary of what changed

WHY: Explain the motivation — what problem this solves or what feature
this adds. Another agent reading this message should understand the
intent well enough to resolve a merge conflict involving these files.

WHAT CHANGED:
- file1.py: description of change
- file2.html: description of change

SIDE EFFECTS: Any non-obvious consequences (e.g., "changes the session
restore flow — other code that calls get_session() is unaffected").

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

#### Step 7 — Push and verify

```bash
git push
git status
```

If push fails with "non-fast-forward" (another agent pushed between
your Step 4 pull and now), repeat from Step 4.

### Commit message format for multi-agent collaboration

Commit messages are **the primary way agents communicate** about what
changed and why. Other agents will read your commit messages to resolve
merge conflicts, so they must be detailed and intent-clear.

**Required structure:**
```
<type>(<scope>): short imperative summary (≤72 chars)

WHY: One sentence explaining the motivation / problem being solved.

WHAT CHANGED:
- <file>: what was changed and why
- <file>: what was changed and why

SIDE EFFECTS: (if any) Non-obvious consequences for other code.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

**Types:** `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`

**Rules:**
- The WHY line is mandatory. "Fixed bug" is not enough — say what the
  bug was and how users experienced it.
- WHAT CHANGED should list every file modified with a brief reason.
  This helps other agents resolve conflicts without reading the full diff.
- SIDE EFFECTS helps other agents know if their in-progress work might
  be affected.

**Bad example:**
```
fix: update prompt engine
```

**Good example:**
```
fix(resume): auto-reinit game state when session cache is empty

WHY: After server restart, resuming a game showed "Session expired"
because _try_load_session_from_db only restored primitive fields,
not the full GameState (world, characters, graph, knowledge).

WHAT CHANGED:
- prompt_engine.py: Added auto-reinit fallback in chat_handler — if
  state.story is missing at regular turn time, queries DB and rebuilds
  full GameState mirroring __cmd_newgame__ setup.
- prompt_engine.py: _try_load_session_from_db now falls back to
  row["story_id"] if state_json is missing the "story" key.

SIDE EFFECTS: None — get_session() callers are unaffected; the reinit
is transparent.
```

### Resolving merge conflicts (multi-agent)

When `git pull --rebase` produces conflicts:

1. **Read the conflicting commit messages first:**
   ```bash
   git log --oneline -10
   ```
2. **Understand the other agent's intent** from their WHY and WHAT
   CHANGED sections. Don't just pick "ours" or "theirs" blindly.
3. **Preserve both intents** wherever possible. If both agents changed
   the same function for different reasons, merge the logic.
4. **If intents truly conflict** (e.g., one agent removed a function
   the other modified), prefer the more recent commit's intent and
   note what you dropped in your commit message.
5. **Run tests after resolving** to verify the merge is sound.

### Branch conventions in this repo

  prod  — production (auto-deploys to api.storieschat.ai / mvpchat-prod on Railway)
  beta  — staging   (auto-deploys to beta-api.storieschat.ai / mvpchat-beta on Railway)

⚠️  CRITICAL: There is NO `main` branch. It has been DELETED.
    Do NOT create, reference, or push to `main`. Only `beta` and `prod` exist.
    Production deploys from `prod` only.

⚠️  CRITICAL: ALL code changes MUST be made on the `beta` branch first.
    Flow is always: beta (make changes) → prod (squash-merge FROM beta) → push prod.
    NEVER make changes directly on prod. NEVER merge prod into beta.
    The merge direction is always: beta → prod, never prod → beta.

AI should NEVER force-push to prod or beta. Pushing to beta is generally safe for testing.


PART 2 — "PUSH TO PROD" WORKFLOW
---------------------------------

When the user says **"push to prod"**, execute these exact steps in order:

```bash
# 1. Switch to prod branch (NOT main — prod is the Railway production branch)
git checkout prod

# 2. Squash-merge beta into prod (theirs = beta wins on conflicts)
git merge --squash beta -X theirs

# 3. Commit with a descriptive message summarising what's in the merge
git commit -m "$(cat <<'EOF'
chore: promote beta to prod

<one-line summary of what's being promoted>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"

# 4. Push prod to remote
git push

# 5. Switch back to beta locally
git checkout beta
```

**Rules:**
- ALWAYS use `prod` branch — there is NO `main` branch (it was deleted)
- Always use `--squash` — keeps prod history clean (one commit per promotion)
- `-X theirs` — beta always wins on merge conflicts
- Write a real commit message summarising the features/fixes being promoted
- Always end by switching back to beta (never leave the user on prod)
- Never skip the `git checkout beta` at the end

### If push fails

- "remote rejected" / 403 → credential expired. Ask the human to re-auth:
    git credential reject  (then retry, browser will prompt)
- "non-fast-forward" → someone else pushed. Pull first:
    git pull --rebase && git push
- Pre-commit hook failure → fix the issue, stage, make a NEW commit (never
  --amend after a hook failure, it would modify the previous commit).

## 2026-09-24 beta-only convention

Work directly on `beta` in the dedicated Codex checkout. Pull `origin/beta`
before code changes and again before pushing. Resolve conflicts by preserving
both writers' intent, rerun affected checks, and push without force. This replaces
older instructions to create a `codex/` feature branch. No production promotion
is authorized by the mobile/PWA repair task.
