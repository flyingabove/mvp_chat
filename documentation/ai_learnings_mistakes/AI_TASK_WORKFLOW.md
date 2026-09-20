AI learnings: intermediate task workflow
=======================================

> **What this doc is for:** Canonical workflow for intermediate task tracking during AI-assisted coding sessions. Edit this doc when task logging location, consumption behavior, or cleanup policy changes.

Canonical location
------------------

- All intermediate tasks must live in exactly one file:
  - `documentation/plans_scratch/TASKS_INTERMEDIATE.md`
- Do not create or use root-level `tasks/` files for active task tracking.

Consumption rule (required)
---------------------------

Before implementation starts on any non-trivial request:

1. Read `documentation/plans_scratch/TASKS_INTERMEDIATE.md`.
2. Confirm the active checklist is up to date for the current request.
3. Mark tasks in progress/completed as work proceeds.
4. At the end, write a short outcome note in the same file.

Consolidation rule
------------------

- Keep one active checklist per request in `TASKS_INTERMEDIATE.md`.
- If multiple temporary lists exist, consolidate them into that same file and remove duplicates.
- Prefer concise checkboxes and short evidence notes (tests run, deploy IDs, etc.).

Cleanup policy
--------------

When to clean up:

1. Immediately after task completion.
2. Before pushing a final commit set for that request.
3. At the start of a new request if previous active items are already complete.

How to clean up:

1. Move completed checklists from "Active" to "Consumed History" in `TASKS_INTERMEDIATE.md`.
2. Keep only open/in-progress items in "Active".
3. If history becomes long (>200 lines), move older consumed entries to:
   - `documentation/plans_scratch/ARCHIVE_TASKS_INTERMEDIATE.md`
4. Keep a one-line summary of what was archived and when.

Non-goals
---------

- This workflow is for intermediate execution tracking, not product design docs.
- Long-term architecture decisions should still be recorded in the relevant model_output_docs files.
