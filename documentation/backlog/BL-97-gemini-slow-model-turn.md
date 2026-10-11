# A slow Gemini model stalls a beta turn

## BL-97 — One turn took 75 s on beta when a slow model timed out before the router spilled over
- **Bucket:** C (engine)
- **Open:** the quota failures are fixed (`gemini_router.call_gemini` spreads calls over the free models; `dfcad6c` and
  `cc93569` made thinking models run at low effort and spill on truncation or timeout). Left: on 2026-10-02 (beta `dfcad6c`)
  one of nine live turns took 75 s, probably one model reaching the 30 s story-master client timeout before the router
  spilled to the next. Prod does not run the router yet, so it still has the old "story master is unavailable" failure mode
  until the next promote.
- **Next:** read the router snapshot (`data/gemini_router.json`) for the model that stalled; decide whether the client
  timeout should be per model, or whether a model that timed out once should be skipped sooner (`COOLDOWN_TIMEOUT_S`).
  Test: a router test where the first model times out and the answer comes from the second within one timeout.
- **Touches:** `backend/app/llm/gemini_router.py`, `backend/app/llm/retry.py`, `tests/backend/app/llm/`.
