---
name: add-and-remove-from-backlog
description: StoriesChat backlog conventions. The backlog is the folder documentation/backlog/ of small topic files (one per bug, or one per few closely related bugs), each holding `## BL-<n>` sections of open work only; a fixed item's section is deleted, and an empty file is deleted. Use this whenever work is knowingly deferred (a bug found but not fixed, a partial fix, a follow-up, an owner action), whenever a backlog item gets fixed, or when the user asks to add, update, list or remove backlog items.
user-invocable: true
---

# /add-and-remove-from-backlog

The backlog is the folder `documentation/backlog/`. Each file is small (aim for under about 3 KB) so an agent reads
only the file for the bug it is working on. **One file per bug, or one file for a few closely related bugs.** Each
file holds one `## BL-<n>` section per open item, with **open work only**. There is no index file and no "Done"
section: the folder listing is the backlog (`ls documentation/backlog/`), a fixed item's section is **deleted**, and
git history plus the fixing commit are the record.

## File and section convention

- File name: a short topic slug, `kebab-case.md` (for example `terrace-plans-and-promises.md`). First line
  `# <topic title>`. Group bugs that share a subsystem or a fix; split a file that grows past about 3 KB.
- Section heading: `## BL-<number> — <one-line title>`.
- Number: the next unused integer, never reused, including numbers of deleted items:
  `(grep -rhoE "BL-[0-9]+" documentation/backlog; git log --all --format=%B | grep -oE "BL-[0-9]+") | sort -t- -k2 -n -u | tail -1`
  gives the highest used; add one.
- Brief, with concrete code names (files, functions, fields, commits) so another agent can act without
  re-investigating:

```markdown
## BL-<n> — <one-line title>
- **Open:** what is wrong and where (`path/file.py` `function_name`), the data involved, repro evidence (numbers, not
  adjectives), and the date and build it was seen on.
- **Next:** the intended fix and the regression test that should prove it; any risk when fixing it (behavior change,
  needs an arena gate, owner decision).
- **Touches:** the files expected to change.
```

Severity and type go in the first sentence of **Open** when they matter. Link to `design/*.md` rather than copying it.

## Adding an item

1. Search first so you don't duplicate: `grep -rin "<keyword>" documentation/backlog/`. If an item exists, update
   its section instead.
2. Add a section to the file for its topic (or create a new small file). Write only what is still open.
3. Commit documentation-only changes on `beta`. **Always push and verify after a merge/integration into beta**,
   including documentation-only work (owner decision 2026-09-28). Standalone edits without a merge can wait for the
   next code push unless the user asks to push or another clone needs them. See `AGENTS.md` "End-of-task completion
   rule".

## Removing an item (when fixed)

1. Fix the issue with its regression test (normal `/ship-and-verify` flow).
2. **Delete the item's `## BL-<n>` section in the same commit as the fix; if that empties the file, delete the file
   (`git rm documentation/backlog/<file>.md`).**
3. Put `Closes BL-<n>` in the commit message body, so `git log --grep "BL-<n>"` finds the fix.
4. A partial fix does not delete the section. Rewrite it so it describes only the remaining work, and delete the
   history of what was done.
5. An item dropped by user decision is also deleted. Say why in the commit message (`Withdraws BL-<n>: <reason>`).

## Listing

`ls documentation/backlog/` shows the topics; `grep -rn "^## BL-" documentation/backlog/` lists every open item.
Check the folder at session start alongside `documentation/AI_DOC_INDEX_CATALOGUE.md`, then open only the file you need.
