# Speaker-aware dialogue

The shared chat renderer presents every AI reply in one classic chat bubble.
It totals the number of spoken characters for each canonical speaker across the
reply and places the most frequent speaker's portrait beside that bubble. A tie
uses the speaker who appeared first. Narration does not add to a speaker's total.

If no one speaks, the winning speaker is unknown (for example, a generated
waiter), or the winning canonical character has no dedicated portrait, the
bubble uses the current game's cover and title. Hovering the picture shows that
person or game name. Clicking or pressing Enter opens the full image in the
center. Escape, the close button, and the backdrop dismiss it and restore focus.

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
New turns, resumed games, and paginated history share one renderer. The readable
reply retains speaker-name prefixes inside the single bubble. Existing
unlabelled history uses the game cover rather than guessing who spoke. Authored
openings use speaker markers; the IU opening's unidentified voice stays unnamed.
Translation carries the same speaker IDs through preserved markers.

Character metadata can supply `portrait_url` or `avatar_url` under `/img/`.
Otherwise the shared asset registry supplies existing artwork. The repository
currently has Terrace House portraits but no dedicated IU cast portrait files,
so IU replies use that game's cover.

The story-model endpoint must support OpenAI-compatible `json_schema` structured
output. Older prose responses remain readable, but cannot provide reliable
speaker attribution. No additional attribution model call is required.

## Reveal and delivery

Saved speed settings retain their meaning, with delays divided by three:
normal is 10ms instead of 30ms. An elapsed-time animation clock batches characters
per frame and respects punctuation pauses. Reduced-motion preferences show
replies instantly. Clicking the bubble completes the turn; clicking the picture
opens it without skipping the text.

The frontend modules are `dialogue.js` and `dialogue.css`, loaded relative to the
environment's base URL and included in the frontend deployment whitelist. FastAPI
serves both root and beta paths. The service worker cache version is bumped.

## Verification

- Python unit/API tests cover both games, structured output, state updates,
  history metadata, malformed markers, unknown voices, and portrait URLs.
- `node --test tests/frontend/dialogue_renderer.test.cjs` checks the one-bubble
  layout, dominant-speaker totals and ties, fallback cases, the 3x reveal rate,
  and completion on interruption.
- Local browser checks exercised a real multi-speaker model reply, portrait
  enlargement, Escape/focus restoration, and phone-width layout.
- Beta deployment `90f2b537-63d8-454f-a5b8-de17aab77f7f` served commit
  `0043948`. Hosted desktop and 390×844 checks confirmed one bubble, the IU
  unknown-voice game-cover fallback, the centered picture viewer, and a clean
  browser console.

The game cover for Terrace in the City is a generated, optimized photograph-style
asset of a believable Japanese house on a Tokyo residential street.
