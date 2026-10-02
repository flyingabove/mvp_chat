# Gemini quota and demand make beta turns fail intermittently

## BL-97 — "The story master is unavailable right now" on beta while the Gemini default model is over quota

- **Open (observed 2026-10-01, beta `f97068f`):** a direct one-word call to the default model `gemini-3.8-flash` returns
  HTTP 429 ("exceeded your current quota"), and the fall-back model `gemini-3.5-flash-lite` sometimes answers and
  sometimes returns HTTP 503 ("high demand"). `retry.post_with_model_fallback` retries once on the primary and then makes
  one attempt on the fall-back, so when both fail the player gets the public error "The story master is unavailable right
  now" (about 1 opening turn in 3 in a short live check). Nothing in the engine is at fault.
- **Why it matters:** the free key is shared by beta play, local checks and pilot seasons (`scripts/run_season.py`), so heavy
  local use can make beta turns fail.
- **Next:** owner decision on the key (quota or billing for `gemini-3.8-flash`, or a separate key for local and sim runs);
  then, if still needed, a second fall-back attempt or a slightly longer wait for 503 in `retry.py`, with a test.
- **Done when:** a 10-turn live check on beta shows no "story master unavailable" with no other load on the key.
