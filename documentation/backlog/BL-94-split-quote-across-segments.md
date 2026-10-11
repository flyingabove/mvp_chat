# A spoken quote is cut in two by its own speech tag

## BL-94 — One quote becomes dialogue, narration, dialogue (bug in reply segmentation)
- **Bucket:** C (engine). Any story's reply goes through `engine/dialogue.py`; the fix names no story or character.
- **Open:** bug, seen on live beta `4aedb46` (Gemini, 2026-09-30, 12 turns, guest). One spoken sentence reached the
  player as three bubbles: dialogue "It is strange," then narration "Arman says," then dialogue "You forget it is
  there...". The storyteller returns structured `segments`; when it breaks a quote at its speech tag, each piece becomes
  its own segment, and `present_dialogue` deliberately never coalesces segments ("Coalescing them recreated the giant
  bubble", `engine/dialogue.py`). Nothing distinguishes a real scene beat from the tag in the middle of one quote. Seen
  once in 12 hosted turns; the rate is unmeasured.
- **Next:** failing test first (a three-segment reply: same speaker, narration that is only a speech tag, same speaker
  again, expecting one dialogue segment). Then merge in `decode_dialogue_response` or just before `present_dialogue`:
  a narration segment that is only `<that speaker's name or he/she/they> <speech verb>` (says, asks, murmurs, adds,
  whispers, with an optional short adverb) and sits between two dialogue segments of the same speaker is dropped and the
  two quotes are joined with a space. Do not merge when the narration has any other content (a gesture, a movement, a
  second person), when the speakers differ, or when either side is not dialogue. Semantic edge cases (a long action
  clause that happens to contain "says") stay unmerged: the failure to avoid is deleting a real beat, so uncertain
  means keep both. Check the reply-level regression with `scripts/terrace_ollama_sim.py` on a few seeds, counting
  split quotes before and after.
- **Touches:** `backend/app/engine/dialogue.py`, `tests/backend/app/engine/test_dialogue.py`.
