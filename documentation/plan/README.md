# The plan: how parallel agents pick up work

> **What this doc is for:** the one central place where every agent (Claude, Codex, anyone) finds the next task, claims
> it, and finishes it without colliding with the others. Edit this doc if the protocol changes. The sequence is in
> [ORDER.md](ORDER.md); the work itself is one file per task, `P-<n>-<slug>.md`, in this folder.

**The plan says who does what and when. The backlog (`../backlog/`) says what is wrong and why. The design docs
(`../design/`) say how it works.** A task links to the backlog item and the design; it never copies them.

## The loop every agent follows

```
git pull --rebase origin beta          # code + plan files
python scripts/work.py status          # what is ready, blocked, claimed by whom
python scripts/work.py claim           # take the best ready task (or: claim P-07); prints its spec
   ... do the task (see AGENTS.md: tests first, ship-and-verify, push to beta) ...
python scripts/work.py renew P-07      # if you need more than 4 hours
   ... the fixing commit DELETES the task file and says "Closes P-07" ...
python scripts/work.py done P-07       # after that commit is on origin/beta; frees the claim
```

Other commands: `next` (the ready list), `release P-07` (give a task back unfinished, and say why in the backlog),
`gc` (drop claims of finished tasks and expired leases), `check` (validate plan files before you push one).

## How it stays safe

- **The plan is read from `origin/beta`**, so `status`, `next` and `claim` are always current without a pull.
- **Claims live on a separate `work` branch**, not `beta`. Taking a task never redeploys Railway. A claim is a
  file `claims/P-07.json` pushed without force: if two agents race, git rejects the loser, who then sees the winner's
  claim and picks another task. The script uses git plumbing and never touches your working tree.
- **A claim is a lease** (default 4 hours, `--hours` to change). An agent that crashes or goes idle loses the task
  when the lease expires. Renew while you are working.
- **Files are locked, not just tasks.** Each task lists `touches:` (files or directories; a directory covers
  everything under it). `claim` refuses a task whose `touches` overlap a task another agent currently holds, so two
  agents never edit `turn.py` at the same time. Take another ready task, or wait.
- **Dependencies** are `depends_on:` task ids. A task is ready only when each dependency's file is gone from the plan
  on `origin/beta` (finished = deleted, exactly like backlog items).
- **Identity** is `--agent`, else the env var `WORK_AGENT`, else your checkout folder name. Several agents in one
  checkout must each set `WORK_AGENT`.
- **Git is the source of truth.** No history section anywhere: the fixing commit and `git log --grep "P-07"` are the
  record.

## A task file

```markdown
---
id: P-07
title: Short imperative title
stage: 2                      # whole number; lower stages first (see ORDER.md)
size: M                       # S (hours) | M (a day) | L (several days; split it if you can)
depends_on: [P-03, P-05]      # [] when none
touches: [backend/app/engine/world_model/stances.py, backend/app/engine/rules/]
backlog: BL-85 (P2)           # the backlog item(s) and design section this implements
---
Read first / Build / Tests first / Done when / Notes.
```

The body must let an agent with no other context start: what to read, what to build, which failing test to write
first, the measurable definition of done, and what the fixing commit must also delete or update in the docs.

## Finishing a task (the checklist inside the loop)

1. Tests first: the failing test, then the fix (`AGENTS.md`). `python -m pytest tests/ -x -q` green.
2. `git pull --rebase origin beta` again; if new commits arrived, re-run the tests.
3. In **one commit**: the code and tests, the deletion of `documentation/plan/P-07-*.md`, the deletion or rewrite of
   the backlog section it closes (`Closes BL-n` only when fully fixed), and updated design docs. Message ends with
   `Closes P-07`.
4. Push to `beta` (ship-and-verify), then `python scripts/work.py done P-07`.
5. If you discover follow-up work, add it as a new task file (below) or a backlog item. Never leave a lingering
   checkbox.

## Adding or changing a task

1. Next free id (ids are never reused, including finished ones):
   `(ls documentation/plan; git log --all --diff-filter=A --name-only --format= -- documentation/plan) | grep -oE "P-[0-9]+" | sort -t- -k2 -n -u | tail -1`
2. Create `P-<n>-<slug>.md` with the front matter above. Choose `touches:` honestly: too narrow and agents collide,
   too broad and work is needlessly serialized.
3. `python scripts/work.py check` (unknown dependencies, cycles, malformed files), then commit and push to `beta`.
   Plan files are documentation: commit them with your next code push unless a parallel agent needs them now.

## Rules specific to this plan

- **Spending money needs the owner.** A task that runs a paid LLM (Gemini, OpenAI, Jev season or pilot runs) says so in
  its body. Ask before running it; the offline path comes first. Arena runs stay disabled (`ARENA_LLM_ENABLED`).
- **Stage gates.** A stage's exit criteria are in `ORDER.md`. Do not start a later stage's task because it looks
  interesting; the dependencies exist because the earlier work changes what the later work builds on.
- **If you are blocked** by something outside your task, release it (`release`), write the blocker as a backlog item,
  and take another task. Do not sit on a claim.
- **Never edit another agent's claimed files** to "help". Message the owner of the claim through the user, or wait.
