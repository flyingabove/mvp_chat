AI learnings: task workflow
===========================

> **What this doc is for:** why the work board exists and the failure modes it prevents. The procedure itself is in
> [../plan/README.md](../plan/README.md) and `/AGENTS.md` section 1. Edit this doc when the way tasks are tracked or
> consumed changes.

What replaced what
------------------

- `documentation/TASKS_INTERMEDIATE.md` (one shared narrative file) and the root `tasks/` folder are **retired** (2026-10-01).
  They had no owner field and no dependencies, collected unchecked boxes for work that had long shipped, and conflicted on
  every edit when several agents worked at once.
- Active work is the **plan**: one file per task in `documentation/plan/`, claimed through `scripts/work.py`.
- Deferred or discovered work is the **backlog** in `documentation/backlog/` (`/add-and-remove-from-backlog`).
- Lessons from owner corrections go in `documentation/user_corrections.md`. There is no separate lessons file.

Rules that keep it working
--------------------------

1. Claim before you work, release if you stop, renew while you work. A claim is a lease that expires (4 hours by default).
2. A task's `touches:` list is a file lock. Do not edit files another agent's live claim covers.
3. Finished work is **deleted**, not ticked: the fixing commit removes the task file (and the backlog section it closes) and says
   `Closes P-<n>`. Git history is the only record; no "done" log, no history section.
4. Anything knowingly deferred becomes a backlog item or a new plan task in the same commit. Nothing lingers as a checkbox.
5. The plan is read from `origin/beta`, so a stale checkout still sees the live plan, but pull before editing code.

Non-goals
---------

- This workflow tracks execution. Product design lives in `documentation/design/`; the vision in
  `documentation/human_north_star_docs/`.
