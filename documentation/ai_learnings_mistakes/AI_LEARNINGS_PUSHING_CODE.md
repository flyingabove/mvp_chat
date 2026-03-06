AI learnings: pushing code & adding command flags
==================================================


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

### Step-by-step: what the AI does to push

1. Stage specific files (never `git add -A` — avoids secrets / binaries):
     git add frontend/index.html

2. Commit with a HEREDOC message (preserves multi-line formatting):
     git commit -m "$(cat <<'EOF'
     fix: short summary of what changed

     Longer explanation if needed.

     Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
     EOF
     )"

3. Push to the current branch:
     git push

4. Verify:
     git status

### Branch conventions in this repo

  prod  — production (auto-deploys to api.storieschat.ai / mvpchat-prod on Railway)
  beta  — staging   (auto-deploys to beta-api.storieschat.ai / mvpchat-beta on Railway)
  main  — NOT the deploy branch. Do NOT push prod changes here.

⚠️  CRITICAL: "push to prod" means `git checkout prod`, NOT `git checkout main`.
    Pushing to main does NOT deploy to production. Always use the `prod` branch.

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
- ALWAYS use `prod` branch — NEVER push to `main` thinking it deploys to production
- Always use `--squash` — keeps prod history clean (one commit per promotion)
- `-X theirs` — beta always wins on merge conflicts
- Write a real commit message summarising the features/fixes being promoted
- Always end by switching back to beta (never leave the user on prod or main)
- Never skip the `git checkout beta` at the end

### If push fails

- "remote rejected" / 403 → credential expired. Ask the human to re-auth:
    git credential reject  (then retry, browser will prompt)
- "non-fast-forward" → someone else pushed. Pull first:
    git pull --rebase && git push
- Pre-commit hook failure → fix the issue, stage, make a NEW commit (never
  --amend after a hook failure, it would modify the previous commit).
