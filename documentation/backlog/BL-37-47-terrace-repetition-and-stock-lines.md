# Terrace: repetition, stock lines and reply pacing

## BL-47 — A refusal line is reused across unrelated turns
- **Open:** hosted beta 2026-09-29 (35 turns): after the first confession Minori answered many unrelated turns with variants of "I want to take my time getting to know everyone, no big plans for now" (moving rooms, breakfast, turn 26 while Paul made her breakfast); Hikaru reused a line Minori had just said. The exact-replay guard (`dialogue.py` `own_repeat_indexes`) checks only 6+ word verbatim repeats, so variants pass.
- **Cause found by code reading (2026-09-30):** `WorldModel.memories.search` (`world_model/memory.py`) ranks all of a speaker's memories, including `kind="dialogue"`. `end_turn` stores every spoken line as a dialogue memory for the speaker and for each listener (`"@minori said: ..."`). `search` adds `3.0` per `@id` the memory shares with the player's message, so once the player names Minori (or addresses her) every line she ever said is boosted regardless of topic, and the recency tiebreak puts her latest refusal on top. `_build_view` (`turn.py`) renders the top 3 as "What each speaker personally remembers that bears on this moment (their OWN memories)", a strong re-prime that also reaches listeners (Hikaru holds Minori's line). Ruled out: `_requirement_hints` (Terrace declares no `disclosure`/`tell` data), verdict directives (`pending_verdicts` is cleared in `end_turn`), the `hint` text (only on the turn of the ask).

### Engineering plan
1. **Failing-first test** (`tests/backend/app/engine/world_model/test_perspectives_no_echo.py`): a model where Minori has a dialogue memory of a refusal; a plain message that names her; assert `view.perspectives` contains no dialogue-memory text. Also Hikaru, who heard the line, gets none of it.
2. **Fix at the source:** `MemoryStore.search` gains an `exclude` predicate; `_build_view` excludes residents' spoken lines (dialogue memories not told by the player). *Plan change while implementing:* excluding every dialogue memory broke "what the player told her" (`test_scene_continuity.py`), so the exclusion is limited to `kind == "dialogue"` and `source != "told_by:player"`.
3. **Keep useful recall:** facts, promises, witnessed events and player-told memories still surface (tests).
4. **API-level test** (`tests/backend/app/api/test_refusal_not_reinjected.py`): after a scripted `not_yet`, unrelated turns carry no refusal directive and no spoken-line memory; it fails without the fix (verified by stashing it).
5. **Measure:** a scripted 25-turn replay counting turns whose engine text carries the refusal.
6. **Docs:** `design/SOCIAL_ENGINE.md` ("Scene recall and visible rivals").

### Checklist
- [x] Failing-first test written and seen failing on the current code (3 of 4 failed before the fix)
- [x] `exclude` predicate added to `MemoryStore.search` with a unit test
- [x] `_build_view` perspectives exclude residents' spoken lines
- [x] Recall of facts, promises and what the player told them still works (tests)
- [x] API-level "refusal not re-injected" test, verified to fail without the fix
- [x] Repeated-refusal count before/after: 25 of 25 turns before, 0 of 25 after
- [x] Design doc updated; section deleted in the fixing commit (`Closes BL-47`)

## BL-37 — Reply pacing, repetition and player agency
- **Open:** decorative atmosphere repeats across turns; stock phrases are reused across characters (see BL-47); narration still assigns the player feelings not stated (see BL-29); a later housemate can still ask a name the player already gave (hosted `fe54691`). Direct answers to addressed questions are handled (each addressee's first reply closes the question), truthfulness of an answer is not checked.
- **Next:** sustained-play evidence for the direct-answer and repetition gates; semantic check that answers are grounded.
- **Touches:** `prompt_builder.py`, `dialogue.py`, Terrace voice data.
