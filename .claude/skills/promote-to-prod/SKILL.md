---
name: promote-to-prod
description: StoriesChat's beta -> production release procedure - verify the deployed beta, run the free offline Ollama precheck, run the hosted arena gate (Jev + OpenAI judges, Ollama advisory), then merge the verified beta commit into prod, push, and verify production live. Use ONLY when the user explicitly asks to promote/push/release beta to prod.
user-invocable: true
---

# /promote-to-prod - evaluate beta against prod, then release

Production is sacred (CLAUDE.md §8). This skill is the only way beta reaches
`prod`: the user must have **explicitly** asked for a promotion in this
conversation. Design: `documentation/model_output_docs/JEV_GAME_ARENA_DESIGN.md` §13-14.

**Everything evaluation-related lives in this folder and runs only on this
machine** (owner decision 2026-09-24) - it is never deployed and never runs
on deploy:

| Path | What |
| --- | --- |
| `arena/` | the arena package (players, targets, judges, gate, report, offline launcher, release helpers) |
| `arena_cli.py` | entry point; works from any directory |
| `tests/` | its tests - outside the repo's `tests/`, so the Docker build gate never runs them |
| `data/eval_arena/` (repo root) | run artifacts (gitignored) |

```bash
PY=C:/Users/Christian/miniconda3/envs/storieschat/python.exe
ARENA="env PYTHONIOENCODING=utf-8 $PY .claude/skills/promote-to-prod/arena_cli.py"
$PY -m pytest .claude/skills/promote-to-prod/tests -q      # the skill's own tests
```

## Vocabulary

- **episode** = one complete game: one AI player (persona) plays one scenario
  on one release for a fixed number of player turns (**minimum 10**, enforced).
- **paired episode** = the same scenario + persona played on beta AND prod;
  its verdict (beta win / prod win / tie / unresolved) is the unit of evidence.
- **judges**: `jev` (TypeSafe Jev), `llm` (OpenAI gpt-4o-mini), `ollama`
  (local llama3.1 8B, free, advisory - it never passes a game on its own).

## Step 0 - Preconditions (stop if any fails)

1. The user explicitly asked to promote. "Looks good" about beta is not a promotion request.
2. `git status` clean except untracked local config; on branch `beta`; `git pull --rebase origin beta`.
3. Record the candidate: `SHA=$(git rev-parse origin/beta)`.
4. Beta is actually running it and healthy:
   `$ARENA wait-deploy --url https://beta-api.storieschat.ai --commit ${SHA:0:7} --timeout 60`
   If it is not live yet, wait for the deploy (never evaluate a moving beta - the
   arena pins releases and marks drifted arms invalid).
5. Full suite passes locally: `$PY -m pytest tests/ -q -p no:cacheprovider`.

## Step 1 - Free offline precheck (Ollama, no cloud calls, ~15 min)

```bash
$ARENA precheck --experiment-id promote_${SHA:0:7}_precheck --baseline-ref origin/prod
```

- Serves the checkout and the baseline ref as two local uvicorn servers
  (ports 8811/8812), everything on Ollama (`llama3.1-8b-ctx16k`, created
  automatically - the default 2k context silently truncates prompts).
- If the baseline predates `OPENAI_BASE_URL` routing it refuses (it would
  call OpenAI). Then use `--baseline-ref origin/beta` (smoke of the candidate).
- **Pass/fail is reliability only**: no new target failures, turn errors or
  deterministic-check findings (routes, clock, repetition) vs the baseline.
  8B quality scores are advisory. Exit code 1 = stop; fix before anything paid.
- Needs `ollama serve` running with `llama3.1:8b` pulled.

## Step 2 - Hosted gate (paid: players + storytellers on OpenAI, ~30-45 min)

```bash
$ARENA all --profile gate --judges jev llm ollama --experiment-id promote_${SHA:0:7}
cat data/eval_arena/promote_${SHA:0:7}/gate.json
```

- `gate` profile = 12 paired episodes x 10 turns (both games, 2 openings each,
  3 personas); games are played ONCE and judged by all three judges.
- Concurrency stays at the defaults (2 games, 2 cloud judge calls, Ollama 1):
  the player, both storytellers and real users share one OpenAI rate limit.
  A run at concurrency 5 once produced 0 scorable episodes and user-visible errors.
- Do not push to beta while it runs (a redeploy invalidates the beta arms).
- A judge failure is never scored; rerun `$ARENA judge --experiment-id ...`
  to retry only the failed pairs (no games are replayed). Check
  `events.jsonl` for `judge_call_failed`.

### Gate rule (user decisions 2026-09-24)

PASS only if, for **every game**, beta's match score is **>= 50% (ties
count)** under **at least one counted judge** (`jev`, `llm`), AND no counted
judge shows the game significantly worse (95% interval below zero with >= 5
resolved episodes), AND no critical regression (unearned secret leak,
fabricated player action, target failures) under a counted judge.

- **PASS** -> Step 3.
- **FAIL** -> stop. Show the user the per-game table from `gate.json` and the
  report (`data/eval_arena/promote_<sha>/report.html`; publish
  `report_fragment.html` as an artifact if they want a link). Promote only if
  the user explicitly overrides after seeing it.

### Reading results honestly

- Jev prefers longer replies (BL-23); every report has a "Length check"
  table - if the longer side won most decided episodes, say so.
- Order disagreements (A/B vs B/A) are unresolved, not votes. Many
  unresolved episodes on nearly identical releases is expected, not a bug.
- Never describe Elo-equivalent as "% of players who prefer beta".

## Step 3 - Promote (exact commands, each as its own Bash call)

```bash
git fetch -q origin && git checkout -q -B prod origin/prod
git merge --no-ff $SHA -m "chore(release): promote verified beta ${SHA:0:7} to production" -m "<WHY / WHAT / VERIFIED: precheck + gate results with experiment ids / SIDE EFFECTS>"
git diff --stat $SHA HEAD          # MUST be empty: prod tree == verified beta tree
git push origin prod               # alone - see pitfall 1
git checkout -q beta               # separate call
```

Commit message ends with the Co-Authored-By line from the system reminder.

## Step 4 - Verify production live

```bash
MERGE=$(git rev-parse origin/prod)
$ARENA wait-deploy --url https://storieschat.ai --commit ${MERGE:0:7}
$ARENA smoke --url https://storieschat.ai
```

`smoke` = health, capabilities, home page, and a new game + one real turn in
each story through the arena's own adapter. Both must exit 0. If the deploy
fails or smoke fails: tell the user immediately with the output; never
`railway down` (it removes the latest deployment, possibly the live one).

## Step 5 - Record and report

- `documentation/plans_scratch/TASKS_INTERMEDIATE.md` -> Consumed History:
  candidate sha, merge sha, precheck + gate experiment ids and verdicts.
- Anything knowingly deferred -> a file in `documentation/backlog/` (`/add-and-remove-from-backlog`).
- Commit + push the docs to beta (normal flow).
- Tell the user: what shipped, the gate table, prod verification output,
  and the report link/path.

## Pitfalls learned the hard way

1. **Pre-push hook.** `.claude/hooks/pre_push_beta_rebase.sh` rebases onto
   beta before beta-targeted pushes; it now parses the real push target, but
   still run `git push origin prod` as its own command, and commit BEFORE any
   push (the hook sees the whole command before it runs).
2. **Docker build test gate** runs without `pytest.ini` and without `git`:
   mark async tests `@pytest.mark.asyncio`, never shell out to git in tests
   (repro: see `ai_learnings_mistakes/AI_LEARNINGS_RUNNING_TESTS.md`).
3. **Shared OpenAI rate limit**: keep arena concurrency at 2.
4. **Ollama context**: always use the `-ctx16k` model the CLI creates; the
   LLM decision client fails closed on detected prompt truncation.
5. **prod env has no JEV_* flags**: Jev paths stay off in production even
   though the code ships; that is expected.
6. **Local only.** There are no service-side arena endpoints (removed by
   owner decision; BACKLOG BL-21 withdrawn). Never add evaluation to the
   Dockerfile, CI, or app startup - a gate run costs real API spend.
