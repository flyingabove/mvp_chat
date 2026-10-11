---
name: add-and-remove-from-backlog
description: StoriesChat backlog procedures. Use whenever work is knowingly deferred (a bug found but not fixed, a partial fix, a follow-up, an owner action), whenever a backlog item is fixed or a task finishes, when the user asks to add, update, list, groom, clean or remove backlog items, and when deciding WHERE a change belongs (A authored text, B game-only mechanic, C engine/character object). The backlog is the folder documentation/backlog/ of small topic files holding `## BL-<n>` sections of open work only.
user-invocable: true
---

# /add-and-remove-from-backlog

The backlog is the folder `documentation/backlog/`. Each file is small (aim for under about 3 KB) so an agent reads
only the file for the work it is doing. **One file per bug, or one file for a few closely related bugs.** Each file holds
one `## BL-<n>` section per open item, with **open work only**. There is no index file and no "Done" section: the folder
listing is the backlog (`ls documentation/backlog/`), a fixed item's section is **deleted**, and git history plus the
fixing commit are the record.

**Exception, design-bearing items.** When the owner asks for a full design inside an item (BL-85, BL-87, BL-95), the
file may be long. It still holds open work only: when a phase ships, move its as-built description to the matching
`design/` doc and delete the phase; delete the item when the last phase ships.

This skill covers four jobs: **classify** (section 1), **add** (2), **close** (3) and **groom** (4).

## 1. Classify: where does the change belong? (A, B or C)

Every item and every plan task says which bucket it is in. Ask: *if this works, which stories get it?*

| Bucket | What it is | Rule |
|---|---|---|
| **C. Engine / character object** | A generic mechanism on the engine, the `Person` / relationship / world-model objects or the prompt pipeline. Another story could switch it on with data. | **The default. Try this first, every time.** |
| **A. Authored text or data** | Words and numbers in a story's JSON (`opening`, `acquaintance` texts, tuning, cue lines, thresholds). Hardcoding is right when the text is fixed before any model has context (the opening the player sees before typing), is set dressing that carries no outcome, or is a tuning number for an engine knob. | Fine and common. Never put an *outcome* or a *decision rule* in text. |
| **B. Game-only mechanic** | Code that exists for one game and would be meaningless in another (the Terrace studio panel, a game's special ritual). | **Strongly avoid in every game, as much as possible. Sometimes it is acceptable when it is truly essential to that game and the generic form cannot express it. A last resort, never a shortcut.** |

### How to decide (in this order)
1. **Can it be a field or rule on the character, relationship or world objects, with the story only supplying data?**
   Name the generic form in one sentence ("a secret ballot", "a scheduled foreshadow", "a trait that changes how
   someone fills a silence"). If you can name a second story that would use it, it is C.
2. **Is it mostly words or numbers?** Then it is A, plus whatever small C hook reads it.
3. **Only if the honest attempt at 1 and 2 fails**, it is B.

### Rules for B (all required)
- The item has a **`Why not C:`** line: which generic form was tried or considered and why it cannot express the need.
- The code lives in its **own story-specific module or hook**, never inside generic engine code (`world_model/`,
  `rules/`, `prompt_builder.py` and similar). A story id, character name or gender test inside generic code is a hidden
  B and is not allowed; move it to data (A) or to a story module (B).
- Prefer a shape another story could reuse later. Record the decision in the matching `design/` doc.
- Tell the owner in the item and in the handover message: B is the choice the owner wants to know about.
- Tests as for any code (AGENTS.md section 3).

### Mixed items
Split by bucket: one row, phase or sub-bullet per bucket, each labelled. An item's `Bucket:` line lists every bucket it
contains (for example `C engine + A data`). A phase that is B on its own gets its own explicit justification.

### Smell tests
- The title says "Terrace" but the mechanism would work anywhere: rename it, and make it C.
- "Only this story uses it" is a reason to look at A (data) first, not a reason for B.
- A weighted rule table for one mechanic is not the architecture: express it on the `Person` object (AGENTS.md section 5).
- A new field with no second possible user is probably A or B; say which.

## 2. Add an item

1. **Search first** so you do not duplicate: `grep -rin "<keyword>" documentation/backlog/`. If an item exists, update its
   section instead. Also check `documentation/plan/` (deferred work may already be a plan task).
2. **Next number:** the next unused integer, never reused, including numbers of deleted items:
   `(grep -rhoE "BL-[0-9]+" documentation/backlog; git log --all --format=%B | grep -oE "BL-[0-9]+") | sort -t- -k2 -n -u | tail -1`
   gives the highest used; add one.
3. **Classify** (section 1) and write the item.
4. **File name:** `BL-<ids>-<topic-slug>.md`, the ids of every section in it joined by dashes, ascending (for example
   `BL-35-45-terrace-plans-and-promises.md`). Rename the file when a section is added or deleted. First line
   `# <topic title>`. Group bugs that share a subsystem or a fix; split a file that grows past about 3 KB (design-bearing
   items excepted).
5. **Section format**, brief, with concrete code names (files, functions, fields, commits) so another agent can act
   without re-investigating:

```markdown
## BL-<n> — <one-line title>
- **Bucket:** C (engine) | A (authored text/data) | B (game-only; add `Why not C:`) | mixed: e.g. C engine + A data.
- **Open:** what is wrong and where (`path/file.py` `function_name`), the data involved, repro evidence (numbers, not
  adjectives), and the date and build it was seen on. Severity and type go in the first sentence when they matter.
- **Next:** the intended fix and the regression test that should prove it; any risk when fixing it (behavior change,
  needs an arena gate, owner decision).
- **Touches:** the files expected to change.
```

6. Link to `design/*.md` rather than copying it. Open owner questions go in the item (a short numbered list), and in the
   message to the owner.
7. Commit documentation-only changes on `beta`. Always push and verify after a merge or integration into `beta`,
   including documentation-only work; a standalone edit without a merge can wait for the next code push unless the owner
   asks or another clone needs it (AGENTS.md section 3 "Completion rule").

## 3. Close an item (when fixed, withdrawn or absorbed)

1. Fix the issue with its regression test (the normal `/ship-and-verify` flow).
2. **Delete the item's `## BL-<n>` section in the same commit as the fix; if that empties the file, delete the file**
   (`git rm documentation/backlog/<file>.md`). Rename the file if its id list changed.
3. Put `Closes BL-<n>` in the commit message body, so `git log --grep "BL-<n>"` finds the fix.
4. **A partial fix does not delete the section.** Rewrite it so it describes only the remaining work and delete the
   history of what was done.
5. **Withdrawn by owner decision:** delete it and say why (`Withdraws BL-<n>: <reason>`).
6. **Absorbed into another item:** move the open work into the destination, delete the source section, and leave at most
   a one-line pointer in the destination's header ("absorbed from BL-<n>"); never a tombstone section.
7. **Sweep dangling references** (a fix leaves other docs pointing at a deleted section):
   ```bash
   open=$(grep -rhoE "^## BL-[0-9]+" documentation/backlog | grep -oE "[0-9]+" | sort -u)
   for id in $(grep -rhoE "BL-[0-9]+" documentation AGENTS.md | grep -oE "[0-9]+" | sort -u); do
     echo "$open" | grep -qx "$id" || echo "BL-$id is referenced but not open"; done
   ```
   References to *closed* items are fine only as a historical note ("as built, BL-76") or in a commit message. A live
   link to a deleted file (`](../backlog/BL-..md)`) must be fixed. Update `design/` docs the fix changed.

## 4. Groom (keep the backlog true and small)

**When:** after every task that touches code or docs in an area with backlog items (the five-minute pass, steps 1 to 4);
whenever the owner says groom, clean or tidy the backlog (the full pass); and at the start of a session where you will work
from the backlog. Grooming is documentation work: a standalone groom commit can stay local until the next push unless the
owner asks (AGENTS.md section 3).

1. **List:** `ls documentation/backlog/` and `grep -rn "^## BL-" documentation/backlog/`.
2. **Is it still open?** For each item in the area you touched, read its `Open` claim and check the code it names
   (`grep` the function, field or file) and `git log --grep "BL-<n>" --oneline`. If the named code is gone, the behavior is
   fixed, or a commit says `Closes BL-<n>`, delete the section (section 3). If only part is fixed, rewrite it to the
   remainder.
3. **Is it accurate?** Fix stale paths (`git ls-files | grep -F "<name>"` for every file in `Touches`), renamed
   functions, old plan-task ids, and links to files that moved. Update the build or date only if you re-observed it.
4. **Fields:** every section has `Bucket`, `Open`, `Next`, `Touches`. If `Bucket` is missing, classify it now
   (section 1) and say so in the commit.
5. **Duplicates and overlaps:** `grep -rin "<keyword>" documentation/backlog/`. Merge duplicates into one section (keep the
   lower number, move the open work, delete the other, section 3 item 6). Split a section that mixes unrelated problems.
6. **Bucket audit:**
   - Every **B** has `Why not C:`, a story-specific module in `Touches`, and has been told to the owner.
   - No C item names a story, character or gender in generic code; if one does, reclassify it (move to A or B).
   - No item whose mechanism is generic is titled or scoped as a single game.
   - Count the B items in the report. The number should stay low.
7. **Files:** names match their ids; no empty file; no file over about 3 KB unless it is design-bearing; no `Done` or
   history section anywhere.
8. **Plan board:** `python scripts/work.py status`. A plan task that closed (`Closes P-<n>`) may have finished parts of
   backlog items; rewrite or delete those parts. A backlog item that is now a ready plan task should say which one.
9. **Report** what you deleted, merged, rewrote and reclassified, and the B count, in the commit message
   (`docs(backlog): groom <area>`) and to the owner.

## 5. Listing

`ls documentation/backlog/` shows the topics; `grep -rn "^## BL-" documentation/backlog/` lists every open item;
`grep -rn "^- \*\*Bucket:\*\* B" documentation/backlog/` lists the game-only ones. Check the folder at session start
alongside `documentation/AI_DOC_INDEX_CATALOGUE.md`, then open only the file you need.
