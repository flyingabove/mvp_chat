# Speaker-aware dialogue

The shared chat renderer presents a reply as ordered narration and dialogue
blocks. Dialogue has a visible name and a 46px portrait (38px on phones).
Hovering a portrait shows the name; clicking or pressing Enter opens a centered,
uncropped image. Escape, the close button, and the backdrop dismiss it, restoring
focus to the originating portrait. Missing art uses initials and an explicit
unavailable message in the viewer.

## Generation and persistence

`engine/dialogue.py` owns the story-independent generation schema, speaker ID
validation, portrait resolution, and translation transport. The story model
returns `segments` and a structured `state` object under a strict JSON schema.
Narration has no speaker. Dialogue references canonical character IDs; unlisted
or unidentified voices use `unknown`. The server supplies names and portraits,
not the model. State is converted into the existing state-update pipeline and
kept out of the visible scene.

`/api/chat` returns readable `reply` text plus `segments`. Conversation memory
keeps speaker names, while JSONL history stores the full segment metadata.
New turns, resumed games, and paginated history share one renderer. Existing
unlabelled history remains narration rather than guessing who spoke. Authored
openings use speaker markers; the IU opening's unidentified voice stays unnamed.
Translation carries the same speaker IDs through preserved markers.

Character metadata can supply `portrait_url` or `avatar_url` under `/img/`.
Otherwise the shared asset registry supplies existing artwork. The repository
currently has Terrace House portraits but no dedicated IU cast portrait files.

The story-model endpoint must support OpenAI-compatible `json_schema` structured
output. Older prose responses remain readable, but cannot provide reliable
speaker attribution. No additional attribution model call is required.

## Reveal and delivery

Saved speed settings retain their meaning, with delays divided by three:
normal is 10ms instead of 30ms. An elapsed-time animation clock batches characters
per frame, respects punctuation pauses, and reveals speakers in reading order.
Reduced-motion preferences show replies instantly. Clicking scene text or the
Show full reply button completes the turn. Portrait interaction does not skip it.

The frontend modules are `dialogue.js` and `dialogue.css`, loaded relative to the
environment's base URL and included in the frontend deployment whitelist. FastAPI
serves both root and beta paths. The service worker cache version is bumped.

## Verification

- Python unit/API tests cover both games, structured output, state updates,
  history metadata, malformed markers, unknown voices, and portrait URLs.
- `node --test tests/frontend/dialogue_renderer.test.cjs` checks the 3x reveal
  rate, speaker ordering, completion on interruption, and history rendering.
- Local browser checks exercised a real multi-speaker model reply, portrait
  enlargement, Escape/focus restoration, and phone-width layout.

This change is local; it has not been deployed.
