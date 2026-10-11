# Flaky outbox test fails the deploy gate

## BL-99 — `test_extraction_failure_leaves_row_pending_not_falsely_done` timed out once on the Railway build
- **Bucket:** C (engine test hygiene)
- **Open:** on 2026-10-06 (build of `b1494c4`, deployment `45ce6bea`) the test failed with `assert row is not None` after its 20 s poll (`_wait_for_row`, 400 x 0.05 s) while 2098 others passed; it passes locally and a redeploy of the same commit went green, so the failure is timing-dependent. A flake here blocks a beta deploy.
- **Next:** replace the poll with a deterministic wait on the outbox worker (a shared `wait_for_outbox(session_id, predicate)` helper that drives or awaits the worker instead of sleeping), then run the test 50 times in a loop. Same helper can serve the other outbox tests.
- **Touches:** `tests/backend/app/api/test_prompt_engine.py`, the outbox worker in `backend/app/api/prompt_engine.py`.
