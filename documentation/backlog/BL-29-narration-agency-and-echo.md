# Narration restates the player and invents feelings

## BL-29 — Narration restates the player's action and invents their feelings
- **Open:** about 20% of turns open by restating the player's typed action in second person; hosted recurrence 2026-09-29 ("Inviting her to join you in the Living Room. As you lead the way ..."). The bounded lexical echo trimmer misses paraphrases and gerund forms; invented feelings ("making your stomach grumble", "your eyes scanning its surface") bypass the filter. Any prompt change needs its own arena gate and must not trim narration that adds new information.
- **Why the current trimmer misses it (`dialogue.py` `drop_narrated_player_echo`):** it only looks at the text before the first comma, only when that clause starts with the word "you", and compares raw word forms, so "Inviting her to join you in the Living Room." (gerund opener, sentence ends with a full stop, "invite" vs "Inviting") never matches. Nothing at all inspects invented sensations: the prompt rule (`prompt_builder.py` "Do not invent the player's feelings...") is the only guard.

### Engineering plan
1. **Failing-first tests** in `tests/backend/app/engine/test_dialogue.py`: the two verbatim examples plus negatives.
   - Restatement: player "I invite her to join me in the living room and lead the way" and narration `"Inviting her to join you in the Living Room. As you lead the way, the hallway light flickers."` keeps only the new information ("The hallway light flickers.").
   - Feelings: `"The kettle clicks off, making your stomach grumble."` keeps the kettle; `"Your eyes scanning its surface, you notice a chip."` loses the invented gaze tail; `"You feel a surge of nerves."` is dropped.
   - Must keep: `"Your phone buzzes on the table."`, `"The kitchen smells of miso."`, and any feeling the player wrote themself ("I feel nervous" then "You feel nervous" is kept).
2. **Restatement backstop:** extend `drop_narrated_player_echo` to work per sentence for the first narration beat: light stemming (strip -ing/-ed/-es/-s) on both sides, first-to-second person mapping, and no "starts with you" requirement, with a forward-coverage threshold of 0.8 (at least 4 words) so beats that add information survive (*plan change:* the old reverse-coverage check was dropped because narration often restates only a clause of a longer message); only the leading restating sentence is removed, never the consequence.
3. **Invented-feelings backstop** (new `drop_invented_player_feelings`, same module): removes (a) second-person sentences that open with `You feel/felt/sense/find yourself/can't help but`, (b) sentences whose subject is the player's body state (`Your stomach|heart|pulse|palms|chest|throat|cheeks|breath|mind ...`), (c) trailing `making|causing|leaving|letting your <body> ...` and `, your eyes|gaze|fingers <verb>ing ...` tails. Skipped when the player's own message contains the body word or feeling word. A segment emptied by it is dropped, never replaced with text.
4. **Prompt rule:** add one explicit line to the structured-scene rule (`dialogue.py` point-of-view text) and the prose rule (`prompt_builder.py`): open with what changes in the world or what others do, never with the player's action or sensations. Arena gate before promotion (BL-19/20/23 limits noted).
5. **Wire:** call the new function beside `drop_narrated_player_echo` in `prompt_engine.py`; log a `player_feelings_trimmed` counter for later measurement.
6. **End-to-end test** through `/api/chat` with a fake storyteller returning both slips; the response contains neither.

### Checklist
- [x] Failing-first unit tests for both verbatim examples and all negatives
- [x] Restatement backstop implemented (stemming, per-sentence, keeps consequences)
- [x] `drop_invented_player_feelings` implemented and wired after the echo trimmer
- [x] Player-stated feelings and world sensory detail are not trimmed (tests)
- [x] Prompt rule added in both places
- [x] End-to-end API test
- [x] Trim counter logged
- [x] Design doc note (`design/PROMPT_PIPELINE.md`); the arena gate is still required before promotion (recorded in the design doc); section deleted in the fixing commit (`Closes BL-29`)
- **Touches:** `prompt_builder.py`, `dialogue.py`, `prompt_engine.py`, tests.
