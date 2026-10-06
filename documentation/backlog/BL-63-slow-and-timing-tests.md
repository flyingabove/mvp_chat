# Slow and timing-based tests (audit C, 2026-09-30; BL-61 was dead code and BL-62 is fixed)

## BL-63 — Slow and timing-based tests
- **Bucket:** C (test infrastructure)
- **Open:**
  - `test_terrace_campaigns.py::test_a_passive_player_is_eventually_cut_by_the_director` takes 28 s; the two `strategic_player_can_earn_the_win` cases take 3-4 s each. Together about 27 s of the roughly 100 s run.
  - `tests/scripts/test_work_board.py` takes an unmeasured time for 23 tests (re-time it first): each board operation makes several real `git fetch`/plumbing calls against a local bare remote (the claim race is tested for real, deliberately). Batch the fetches or give the file a `slow` marker with the others.
  - Outbox tests in `test_prompt_engine.py` (about lines 1636, 1725, 1768; three polling loops) poll with `for _ in range(400): sleep(0.05)`.
  - `tests/backend/app/knowledge/test_embedder_warmup.py:34` sleeps 0.2 s per construct; `tests/backend/app/llm/decisions/test_resolver.py:411` sleeps 0.1 s in a latency test that can flake on a loaded machine.
- **Next:** Give the passive-player campaign a smaller seed or mark it `slow` and exclude it from the deploy gate (keep it in local runs). Add a `wait_for_outbox(sid)` helper that awaits the task instead of sleeping. Replace the sleeps in the embedder test with a `threading.Barrier` and the resolver test with a fake clock or an event.
- **Touches:** `tests/backend/app/api/test_terrace_campaigns.py`, `test_prompt_engine.py`, `tests/backend/app/knowledge/test_embedder_warmup.py`, `tests/backend/app/llm/decisions/test_resolver.py`, `pytest.ini` (`slow` marker).
