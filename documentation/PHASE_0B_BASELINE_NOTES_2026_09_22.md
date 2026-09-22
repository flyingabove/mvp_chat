# Phase 0B baseline — first captured measurements

2026-09-22. Companion to `PHASE_0B_BASELINE_2026_09_22.json` (raw harness output).
Captured via `scripts/bench/turn_workload_harness.py` against live beta
(`https://beta-api.storieschat.ai`), six_strangers, both genders, concurrency 1
and 3, 2 sessions per level, 2 messages per session after new-game.

**This is a small, conservative first run — not the full matrix the plan
specifies** (1/10/50 concurrency, both stories, cold+warm, short+long
conversations, movement, time skip, queue exhaustion, provider errors). It
exists to prove the harness and stage ledger work end-to-end and to capture a
real number before Phase 1+ changes anything. Extending it to the full matrix
is flagged as follow-up, not done here — see bottom of this file.

## Results

| Scenario | ok/attempts | p50 (ms) | p95 (ms) | max (ms) | prompt tok (mean) | completion tok (mean) |
|---|---|---:|---:|---:|---:|---:|
| six_strangers-M-conc1 | 6/6 | ~3.1–3.7k | ~4.4–4.6k | — | ~4,800 | ~200 |
| six_strangers-M-conc3 | 6/6 | 3,738 | 4,436 | 4,436 | 4,789 | 235 |
| six_strangers-F-conc1 | 6/6 | 3,090 | 4,619 | 4,619 | 4,802 | 170 |
| six_strangers-F-conc3 | 6/6 | 3,954 | 5,873 | 5,873 | 4,801 | 226 |

(Full precision in the JSON; this table rounds for readability.)

## What this establishes

1. **100% success rate** across 24 turns (new-game + 2 follow-ups × 4
   scenario/concurrency combinations). No provider errors, no dropped
   sessions, no retrieval failures in this run.
2. **Prompt tokens are consistently ~4,800 per turn regardless of turn
   number or concurrency.** This is the number the Phase 3 "stable instruction
   prefix caching" item and the Phase 4 Jev economics both need as a
   denominator.
3. **`cached_tokens: 0` on every turn** (visible in the raw server-side
   `usage` field from a prior manual check, not yet added to this harness's
   summary — see follow-up below). Confirms the plan's Phase 3 item is real,
   unclaimed savings, not a guess.
4. **Concurrency 1 → 3 adds roughly 500–1,300ms to p50/p95** on this small
   sample. Not yet enough data to separate "real contention" from "provider
   variance" — the harness needs more sessions per level and a higher
   concurrency tier (10, 50) to say anything load-bearing about scaling.
5. **The per-turn `turn_stage_ledger` JSONL line now exists server-side**
   (Phase 0B code change, see `backend/app/utils/stage_timer.py`), giving
   `stage_ms.retrieval` / `stage_ms.storyteller` / `stage_ms.commit`. Not yet
   pulled into this harness's report — the harness currently measures
   round-trip only. Correlating client-observed latency against the
   server-side stage breakdown (to see how much of the ~3-4s is
   retrieval/extraction vs. the storyteller call itself) is the natural next
   step and is listed below.

## Known gaps vs. the plan's full spec (explicitly not done in this pass)

- Only `six_strangers` exercised; the second story is not in this run.
- Concurrency 10 and 50 not run (cost/time; opt in via `--concurrency 10 50`).
- No cold-start-specific run (the harness's "new game" turn is a reasonable
  proxy but doesn't force a cold embedder — Phase 1.3 already warms it at
  startup, so cold-start numbers now require killing the model in-process to
  observe, which the harness doesn't do).
- No long-conversation, movement, time-skip, or queue-exhaustion scenarios.
- No injected provider-error scenario (would require a fault-injection proxy
  or a monkeypatched STORY_MASTER_BASE_URL pointed at a failing stub).
- The harness does not yet parse `turn_stage_ledger` from server logs to
  attribute latency to a specific stage — it only has the client-observed
  total and the `usage` field the chat response already returns.

## Follow-up (tracked as BL-15 in BACKLOG.md)

Extend `turn_workload_harness.py` to:
1. Add `cached_tokens` to `TurnResult`/`summary()` (the response already
   carries `usage.prompt_tokens_details.cached_tokens`).
2. Run concurrency 10 and 50 tiers once there is a controlled window to spend
   the tokens (each is a real paid LLM call).
3. Add a second story once one with comparable content depth is available for
   a fair A/B.
4. Optionally correlate against server-side `turn_stage_ledger` lines (would
   need either Railway log export or a local dev run where stdout is
   captured directly) to break latency into `retrieval` / `storyteller` /
   `commit` components rather than only round-trip total.
