---
name: add-and-remove-from-backlog
description: StoriesChat backlog conventions. There is one Markdown file per bug or deferred item in documentation/backlog/, and the file is deleted when the item is fixed. Use this whenever work is knowingly deferred (a bug found but not fixed, a partial fix, a follow-up, an owner action), whenever a backlog item gets fixed, or when the user asks to add, update, list or remove backlog items.
user-invocable: true
---

# /add-and-remove-from-backlog

The backlog is the folder `documentation/backlog/`. **One file = one open item.**
The folder listing is the backlog; there is no index file to maintain. A fixed item's
file is **deleted**, and git history plus the fixing commit are the record.

## File convention

- Name: `BL-<number>-<short-kebab-slug>.md`, e.g. `BL-26-lore-retrieval-namespace-filter.md`.
- Number: the next unused integer across **both** `documentation/backlog/` and the legacy
  `documentation/BACKLOG.md` (`grep -o "BL-[0-9]*"` over both, take max + 1). Never reuse a number.
- Brief content, with concrete code names (files, functions, fields, commits) so another agent can act on it
  without re-investigating:

```markdown
# BL-<n> — <one-line title>

- **Type:** bug | follow-up | tech-debt | owner action
- **Found:** <YYYY-MM-DD>, <where: audit, live check, arena run, user report>
- **Severity:** high | medium | low, plus a short reason

## Problem
What is wrong and where: `path/file.py` `function_name`, the data involved, and repro evidence (numbers, not adjectives).

## Fix direction
The intended fix and the regression test that should prove it.

## Why deferred / cautions
Why it isn't fixed now, and any risk when fixing it (behavior change, needs an arena gate, etc.).

## Touches
The files expected to change.
```

## Adding an item

1. Search first so you don't duplicate: `grep -ril "<keyword>" documentation/backlog documentation/BACKLOG.md`.
   If an item exists, update its file instead.
2. Create the file with the template above. Keep it short; link to design docs rather than copying them.
3. This is a documentation-only change: commit it locally on `beta`. It doesn't need its own push
   (see `AGENTS.md` "End-of-task completion rule"). It goes out with the next code push.

## Removing an item (when fixed)

1. Fix the issue with its regression test (normal `/ship-and-verify` flow).
2. **Delete the item's file in the same commit as the fix** (`git rm documentation/backlog/BL-<n>-*.md`).
3. Put `Closes BL-<n>` in the commit message body, so `git log --grep "BL-<n>"` finds the fix.
4. A partial fix doesn't delete the file. Rewrite it to describe only the remaining work.
5. An item dropped by user decision is also deleted. Say why in the commit message
   (`Withdraws BL-<n>: <reason>`).

## Legacy `documentation/BACKLOG.md`

Items BL-01..BL-25 still live in the old single file. Don't add new items there. When you work on a
legacy item, move it into its own file here first (same number). When a legacy item is fixed, remove
its entry from `BACKLOG.md` in the fixing commit instead of moving it to a "Done" section.

## Listing

`ls documentation/backlog/` shows open items; `grep -l "Severity:\*\* high" documentation/backlog/*` finds the urgent ones.
Check the folder at session start alongside `documentation/AI_DOC_INDEX_CATALOGUE.md`.
