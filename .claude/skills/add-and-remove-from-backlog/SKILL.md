---
name: add-and-remove-from-backlog
description: StoriesChat backlog conventions. The backlog is the single file documentation/BACKLOG.md with one `### BL-<n>` entry per open bug, follow-up, tech-debt row or owner action, and the entry is deleted when the item is fixed. Use this whenever work is knowingly deferred (a bug found but not fixed, a partial fix, a follow-up, an owner action), whenever a backlog item gets fixed, or when the user asks to add, update, list or remove backlog items.
user-invocable: true
---

# /add-and-remove-from-backlog

The backlog is the single file `documentation/BACKLOG.md`. **One `### BL-<n>` entry = one open item, and only open
work.** There is no "Done" section: a fixed item's entry is **deleted**, and git history plus the fixing commit are
the record.

## Entry convention

- Heading: `### BL-<number> — <one-line title>` under the matching group in the file's contents list.
- Number: the next unused integer. The header line of `BACKLOG.md` names the last one used (`grep -o "BL-[0-9]*"`
  over the file and `git log --all --oneline | grep -o "BL-[0-9]*"` to be sure). Never reuse a number, including
  numbers of deleted items.
- Brief, with concrete code names (files, functions, fields, commits) so another agent can act without
  re-investigating:

```markdown
### BL-<n> — <one-line title>
- **Open:** what is wrong and where (`path/file.py` `function_name`), the data involved, repro evidence (numbers, not
  adjectives), and the date and build it was seen on.
- **Next:** the intended fix and the regression test that should prove it; any risk when fixing it (behavior change,
  needs an arena gate, owner decision).
- **Touches:** the files expected to change.
```

Severity and type go in the first sentence of **Open** when they matter. Link to `design/*.md` rather than copying it.

## Adding an item

1. Search first so you don't duplicate: `grep -in "<keyword>" documentation/BACKLOG.md`. If an item exists, update
   its entry instead.
2. Add the entry with the template above, bump the "last used" number in the header, and add the id to the contents
   list. Keep it short; write only what is still open.
3. Commit documentation-only changes on `beta`. **Always push and verify after a merge/integration into beta**,
   including documentation-only work (owner decision 2026-09-28). Standalone edits without a merge can wait for the
   next code push unless the user asks to push or another clone needs them. See `AGENTS.md` "End-of-task completion
   rule".

## Removing an item (when fixed)

1. Fix the issue with its regression test (normal `/ship-and-verify` flow).
2. **Delete the item's `### BL-<n>` entry (and its id in the contents list) in the same commit as the fix.**
3. Put `Closes BL-<n>` in the commit message body, so `git log --grep "BL-<n>"` finds the fix.
4. A partial fix does not delete the entry. Rewrite it so it describes only the remaining work, and delete the
   history of what was done.
5. An item dropped by user decision is also deleted. Say why in the commit message (`Withdraws BL-<n>: <reason>`).

## Listing

`grep -n "^### BL-" documentation/BACKLOG.md` lists the open items; the contents list at the top groups them.
Check the file at session start alongside `documentation/AI_DOC_INDEX_CATALOGUE.md`.
