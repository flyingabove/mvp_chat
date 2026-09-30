# Workload harness needs the full matrix run

## BL-15 — Workload harness needs the full matrix run
- **Open:** `scripts/bench/turn_workload_harness.py` only ran one story at concurrency 1/3 with 2 sessions. Missing: both stories, cold/warm start, short/long conversations, movement, time skip, queue exhaustion, provider errors, concurrency 10/50 (real paid-call bursts needing a deliberate window), and `cached_tokens` in its own summary.
