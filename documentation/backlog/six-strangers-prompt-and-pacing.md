# Six Strangers prompt quality, voices and pacing

## BL-25 — Six Strangers prompt slips
- **Open:** (b) the murder-mystery "CANON CORRECTION" block is injected into the slice-of-life prompt for every story regardless of mode (`prompt_builder.py`); (c) pronoun and self-reference slips ("Yuki ... her" though Yuki Adachi is a man): whereabouts rows carry pronouns but Cast IDs and the speaker list do not; (d) head-count slips ("just us five" with six residents including the player), no regression suite.
- **Next:** gate the canon-correction layer on story mode; add pronouns to Cast IDs; a seeded-roster head-count regression.

## BL-22 — Six Strangers replies read as generic next to prod
- **Open:** a 40-pair arena pilot favoured prod for Six Strangers (beta 2 wins, prod 9) and the remaining explanation is that beta replies are about 30% shorter (the intentional BL-12 pacing cap) while the judge has a length bias (BL-23), so "worse" cannot be separated from "shorter". Residual: the model occasionally puts `**"bold quotes"**` inside a narration segment, which the frontend shows literally (`clean_spoken_text` only cleans dialogue).
- **Next:** length-matched arena evidence after BL-23; apply the wrapper cleanup to quoted speech inside narration.
- **Touches:** `engine/dialogue.py`, `prompt_builder.py`.

## BL-12 — Short-message pacing does not fully meet its own cap
- **Open:** replies to "hi"/"ok" fell from about 142-178 to about 120-126 tokens but still tend to two paragraphs against a stated 3-4 sentence cap; more prompt wording has diminishing returns.
- **Next:** a non-prompt lever, e.g. a lower `MAX_TOKENS` for detected-short messages in `prompt_engine.py`.
