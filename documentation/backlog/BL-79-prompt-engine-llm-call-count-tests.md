# Prompt-engine tests count two LLM calls per turn

## BL-79 — Three `test_prompt_engine.py` tests fail locally: a normal turn makes 2 storyteller posts, tests expect 1
- **Open:** On beta `55f9d60` (and already at `1a11b34`), `test_debug_mode_toggle_no_llm_on_toggle_and_appends_debug_box` and `test_debug_toggle_strips_leading_gt` fail with `assert 2 == (0 + 1)` on `_TEST_OPENAI_POST_SPY.calls`, and `test_six_strangers_prompt_states_whereabouts_and_never_names_unarrived_residents` fails with `KeyError: 'messages'` because its last recorded post has no OpenAI `messages`. They fail even with `LLM_PROVIDER=openai`, with or without the `/beta` redirect change. Found while fixing the iPhone `/beta` reload loop; not investigated further. Likely from the single provider switch (`698932e`) or the Gemini fallback (`1a11b34`), which may add a second post per turn.
- **Next:** find what the second post is (log `sent` in the whereabouts test). Then either make the tests select the storyteller post explicitly, or remove the extra call if it is unintended.
- **Touches:** `tests/backend/app/api/test_prompt_engine.py`, `backend/app/api/prompt_engine.py`, `backend/app/llm/chat.py`.
