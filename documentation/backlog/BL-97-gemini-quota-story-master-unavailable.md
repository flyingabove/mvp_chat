# Gemini quota and demand make beta turns fail intermittently

## BL-97 — "The story master is unavailable right now" on beta while the Gemini default model is over quota

- **Open (observed 2026-10-01, beta `f97068f`):** a direct one-word call to the default model `gemini-3.8-flash` returns
  HTTP 429 ("exceeded your current quota"), and the fall-back model `gemini-3.5-flash-lite` sometimes answers and
  sometimes returns HTTP 503 ("high demand"). `retry.post_with_model_fallback` retries once on the primary and then makes
  one attempt on the fall-back, so when both fail the player gets the public error "The story master is unavailable right
  now" (about 1 opening turn in 3 in a short live check). Nothing in the engine is at fault.
- **Why it matters:** the free key is shared by beta play, local checks and pilot seasons (`scripts/run_season.py`), so heavy
  local use can make beta turns fail.
- **Mitigated (2026-10-01):** `gemini_router.call_gemini` spreads every call over seven free models by their own budgets
  (see PLATFORM.md `GEMINI_ROUTER`), so the default model's 20 requests a day no longer decide availability.
- **Next:** watch live; the router's `snapshot()` shows per-model use. Left open until the 10-turn live check passes.
- **Done when:** a 10-turn live check on beta shows no "story master unavailable" with no other load on the key.
- **Live check 2026-10-02 (beta `dfcad6c`):** 9 of 9 turns answered, but one took 75 s, probably a slow model timing out (30 s
  story-master client timeout) before the router spilled to the next. Check the router snapshot for which model that was, and
  consider whether the timeout should differ per model. Prod does not run the router yet, so it still has the old failure mode.

