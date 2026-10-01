# Opening arrival is narrated twice

## BL-93 — A resident's entrance appears twice in one reply (authored beat plus the storyteller's paraphrase)
- **Open:** bug, seen on beta `11871af` (2026-10-01, `six_strangers`, turn 3: Hayato's authored "A tall man in a plain
  jacket looks at the chairs..." beat, then the storyteller's own "A tall man in a plain jacket steps across the
  threshold, looking over the chairs..."). The prompt already says not to repeat the doorway description
  (`prompt_builder.py` opening arrival directive), and the model sometimes ignores it. The safety net
  `opening_scene.strip_generated_arrival_repeats` only drops narration that names the newcomer, but authored cues are
  nameless by design (the narrator never names a newcomer), so a paraphrase is never caught. The unit test only passes
  because its fake line contains a name.
- **Next:** match a generated narration against the authored entrance cue itself (shared content words), keep the name
  match, and test with a nameless paraphrase of a real cue.
- **Touches:** `backend/app/engine/opening_scene.py`, `tests/backend/app/engine/test_opening_scene.py`.
