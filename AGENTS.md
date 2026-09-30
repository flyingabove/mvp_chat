# Codex collaboration workflow

- The user designated the independent sibling clone `mvp_chat_for_codex_only` for Codex work. Use that checkout; do not edit or clean another agent's `mvp_chat` working tree.
- Read `documentation/AI_DOC_INDEX_CATALOGUE.md` and the relevant project documentation before implementation. Track work in `documentation/TASKS_INTERMEDIATE.md`.
- ALWAYS work directly on `beta`; never create or work on another branch. Pull latest `origin/beta` before code changes and again before shipping. This beta-only instruction supersedes prior feature-branch guidance.
- Read conflicting commits, preserve both agents' intended behavior, and test the integrated result. Never force-push shared branches or use blanket ours/theirs conflict resolution.
- Keep local credentials ignored. Stage explicit task files, never unrelated work or runtime data.
- Follow `.claude/skills/ship-and-verify/SKILL.md`: test and view locally, then deploy to beta and verify the actual hosted behavior. Retest after integrating new upstream changes. Push to production only when explicitly requested.
- If another writer changes this checkout unexpectedly, preserve work and investigate before overwriting it. Use checkpoint commits on beta to protect substantial progress.

## End-of-task completion rule

- At the end of every task that changes code, story data, frontend, config, tests or scripts, commit the task files and push the integrated beta HEAD to `origin/beta` before reporting completion. This is standing user authorization; do not ask again or stop at a local commit.
- **Always push after merging into beta** (user decision 2026-09-28). When work is merged or integrated into local `beta`, push the integrated HEAD to `origin/beta` and verify it before reporting completion, including documentation-only merges and merges from `origin/beta` into local work. This is standing authorization; do not ask again or stop at a local merge/commit. This rule supersedes the documentation-only exception for merged work.
- **Standalone documentation-only changes do not otherwise need a beta push** (user decision 2026-09-24, narrowed 2026-09-28). This covers `documentation/`, Markdown instructions such as `AGENTS.md`, `.claude/CLAUDE.md`, skill `*.md`, and `tasks/`. If no merge/integration occurred, commit locally and include them in the next code push unless the user requests a push or another clone needs them. Report that case as "committed locally, not pushed". Every push redeploys Railway beta and invalidates running arena gates; avoid discretionary documentation pushes during arena runs. Explicitly requested pushes and the mandatory merge-push rule take precedence.
- Fetch and merge current `origin/beta`, resolve conflicts preserving both writers' intent, and perform the checks appropriate to the changes before `git push origin HEAD:beta`. Never force-push. If beta advances and rejects the push, fetch, integrate, recheck, and retry.
- Verify the pushed commit is present on remote beta. For runtime/UI changes, also complete the existing ship-and-verify deployment checks. When documentation-only commits are pushed with other work, verify the remote files and do not claim a runtime deployment was tested.
- If a real failure prevents shipping, report that task completion is blocked and state the exact failure. Never describe unpushed work as finished. Production still requires an explicit user request.
