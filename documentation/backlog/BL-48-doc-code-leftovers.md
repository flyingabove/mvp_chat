# Small doc/code leftovers

## BL-48 — Small doc/code leftovers
- **Bucket:** C (engine)
- **Open:** `CharacterIndexBundle.chunks` is still `List[dict]` (`contracts/index_bundle.py`); backward-compatibility aliases from the character-model refactor remain in `engine/state.py` (about lines 253 and 631). The playback-docs drift is tracked in BL-64-70 (BL-69).
- **Next:** type the chunks as a dataclass and delete the aliases, with the tests that use them.
- **Touches:** `backend/app/contracts/index_bundle.py`, `backend/app/engine/state.py`.
