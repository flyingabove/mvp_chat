# Small doc/code leftovers

## BL-48 — Small doc/code leftovers
- `CharacterIndexBundle.chunks` is still `List[dict]`; backward-compatibility aliases from the character-model refactor are still present (see `engine/state.py`, `knowledge/`); the `INTEGRATION_TEST_PLAYBACK` browser UI was removed and only the scenario/runner/API layer remains, so its docs describe less than exists.
