# Bugs and slow tests found inside the suite (audit C, 2026-09-30)

## BL-61 — Lost BL-07 test: orphaned code inside the IU test
- **Open:** `tests/backend/app/api/test_prompt_engine.py:4990-4995` sits under `test_iu_identity_correction` (line 4978), after a "BL-07: per-character self_knowledge propagation" banner. It uses names never defined there (`by_key`, `sysmsg`). It is the leftover body of a test that lost its `def` (added in commit e3a38d8). Result: the BL-07 self-knowledge check (new-game path and restore path both build the roster separately) is not running, and a NameError after the scenario is hidden by the non-strict xfail.
- **Next:** Recover the original test from `git show e3a38d8` and give it its own `def` and fixtures (new game, then restore, assert each character's `self_knowledge` appears in the system prompt only for the right speaker: mina and daeho present, priya absent). Delete the stray lines from the IU test. The regression test is the restored test itself; check it fails if `self_knowledge` propagation is removed.
- **Touches:** `tests/backend/app/api/test_prompt_engine.py`.

## BL-62 — A unit test loads a real HuggingFace model
- **Open:** `with client:` (`test_prompt_engine.py` around lines 1583 and 1671) runs the app lifespan, which starts `_warm_embedder` and builds `SentenceTransformer(MODEL_NAME)` (`backend/app/knowledge/build/embedder.py:75`). That is a real model load, and a download when the cache is cold. It costs 10-15 s in `test_extraction_outbox_row_marked_done_after_successful_extraction` (about a third of the file's runtime); the later test is fast only because `_MODEL` is cached. The run also shows a HuggingFace `resume_download` FutureWarning.
- **Next:** Add an autouse fixture (in a new `tests/backend/app/api/conftest.py`) that no-ops `main._warm_embedder` or sets the existing disable flag. `test_embedder_warmup.py` already tests warm-up with a fake model. Assert the suite runs with the model dir unreachable.
- **Touches:** new `tests/backend/app/api/conftest.py`, possibly `backend/app/main.py`.

## BL-63 — Slow and timing-based tests
- **Open:**
  - `test_terrace_campaigns.py::test_a_passive_player_is_eventually_cut_by_the_director` takes 28 s; the two `strategic_player_can_earn_the_win` cases take 3-4 s each. Together about 27 s of the roughly 100 s run.
  - Outbox tests in `test_prompt_engine.py` (about lines 1549, 1600, 1689, 1732) poll with `for _ in range(400): sleep(0.05)`.
  - `tests/backend/app/knowledge/test_embedder_warmup.py:34` sleeps 0.2 s per construct; `tests/backend/app/llm/decisions/test_resolver.py:411` sleeps 0.1 s in a latency test that can flake on a loaded machine.
- **Next:** Give the passive-player campaign a smaller seed or mark it `slow` and exclude it from the deploy gate (keep it in local runs). Add a `wait_for_outbox(sid)` helper that awaits the task instead of sleeping. Replace the sleeps in the embedder test with a `threading.Barrier` and the resolver test with a fake clock or an event.
- **Touches:** `tests/backend/app/api/test_terrace_campaigns.py`, `test_prompt_engine.py`, `tests/backend/app/knowledge/test_embedder_warmup.py`, `tests/backend/app/llm/decisions/test_resolver.py`, `pytest.ini` (`slow` marker).
