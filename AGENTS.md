# Codex collaboration workflow

- The user designated the independent sibling clone `mvp_chat_for_codex_only` for Codex work. Use that checkout; do not edit or clean another agent's `mvp_chat` working tree.
- Read `documentation/AI_DOC_INDEX_CATALOGUE.md` and the relevant project documentation before implementation. Track work in `documentation/plans_scratch/TASKS_INTERMEDIATE.md`.
- Start a `codex/` feature branch from current `origin/beta`. Fetch and merge `origin/beta` before work and again before shipping. The user's dedicated-branch instruction overrides older guidance to implement directly on `beta`.
- Read conflicting commits, preserve both agents' intended behavior, and test the integrated result. Never force-push shared branches or use blanket ours/theirs conflict resolution.
- Keep local credentials ignored. Stage explicit task files, never unrelated work or runtime data.
- Follow `.claude/skills/ship-and-verify/SKILL.md`: test and view locally, then deploy to beta and verify the actual hosted behavior. Retest after integrating new upstream changes. Push to production only when explicitly requested.
- If another writer changes this checkout unexpectedly, preserve work and investigate before overwriting it. Use checkpoint commits on the feature branch to protect substantial progress.

## End-of-task completion rule

- At the end of every task that changes repository files, including research/design documentation and workflow instructions, commit the task files and push the integrated feature-branch HEAD to `origin/beta` before reporting completion. This is standing user authorization; do not ask again or stop at a local commit.
- Fetch and merge current `origin/beta`, resolve conflicts preserving both writers' intent, and perform the checks appropriate to the changes before `git push origin HEAD:beta`. Never force-push. If beta advances and rejects the push, fetch, integrate, recheck, and retry.
- Verify the pushed commit is present on remote beta. For runtime/UI changes, also complete the existing ship-and-verify deployment checks. For documentation-only changes, verify the remote files; do not claim a runtime deployment was tested.
- If a real failure prevents shipping, report that task completion is blocked and state the exact failure. Never describe unpushed work as finished. Production still requires an explicit user request.
