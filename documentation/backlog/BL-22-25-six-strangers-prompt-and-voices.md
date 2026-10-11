# Six Strangers prompt quality, voices and pacing

## BL-25 — Six Strangers prompt slips
- **Bucket:** C (engine)
- **Open:** (b) the murder-mystery "CANON CORRECTION" block is injected into the slice-of-life prompt for every story regardless of mode (`prompt_builder.py`); (c) pronoun and self-reference slips ("Yuki ... her" though Yuki Adachi is a man): whereabouts rows carry pronouns but Cast IDs and the speaker list do not; (d) head-count slips ("just us five" with six residents including the player), no regression suite.
- **Next:** gate the canon-correction layer on story mode; add pronouns to Cast IDs; a seeded-roster head-count regression.

## BL-22 — Six Strangers replies read as generic next to prod
- **Bucket:** C (engine)
- **Open:** a 40-pair arena pilot favoured prod for Six Strangers (beta 2 wins, prod 9) and the remaining explanation is that beta replies are about 30% shorter (the intentional BL-12 pacing cap) while the judge has a length bias (BL-23), so "worse" cannot be separated from "shorter". Residual: the model occasionally puts `**"bold quotes"**` inside a narration segment, which the frontend shows literally (`clean_spoken_text` only cleans dialogue).
- **Next:** length-matched arena evidence after BL-23; apply the wrapper cleanup to quoted speech inside narration.
- **Touches:** `engine/dialogue.py`, `prompt_builder.py`.
- **Also (absorbed from BL-12):** replies to "hi"/"ok" still tend to two paragraphs against a 3-4 sentence cap; more prompt wording has diminishing returns. Next lever: a lower `MAX_TOKENS` for detected-short messages (`api/prompt_engine.py`, `config/settings.py`).
