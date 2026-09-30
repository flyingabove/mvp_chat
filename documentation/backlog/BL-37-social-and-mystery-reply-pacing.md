# BL-37 — Replies need distinct voices, direct answers and less repeated atmosphere

- **Type:** quality follow-up
- **Found:** 2026-09-25, manual hosted play
- **Severity:** medium; repetition and uniform agreement reduce engagement in both stories.

## Problem
[Terrace turns 6–8](../archive/BETA_MANUAL_PLAY_REVIEW_2026_09_25.md) show unanimous agreement, including when Natsumi is asked if she would disagree. Her house-rule answer is generic. IU turns 2–8 repeatedly describe heavy air, shadows, trembling and unspoken truths while producing fewer new leads than lines of atmosphere. Terrace turn 10 avoids the direct rice-memory question; IU turns 10–12 spend substantial text narrating guarded expressions around checkable questions. The engine already has character voices in Terrace story data and a direct-response design, but live behavior underuses them.

## Fix direction
Give an addressed, answerable question a concise answer or honest inability; prioritize the player's current intent over ensemble chatter. Limit decorative atmosphere to scene changes or specific new sensory evidence. Keep speaker style tied to their authored voice, work, aims and boundaries; allow a neutral silence or disagreement. Track direct-answer rate, repeated scene imagery, character distinguishability and turn length in hosted samples. Coordinate with BL-29 (do not assign player feelings/actions) and legacy BL-22 (character distinction) rather than duplicating their fixes.

## Why deferred / cautions
Prompt changes alter both games and need arena and human review; this is not a reason to simply cap all replies. Do not force disagreement every turn or punish deliberate uncertainty in a mystery.

**Hosted reproduction (2026-09-26, beta `1045464`):** Terrace turn 3 ignored the direct request for Misaki to confirm a 7 pm plan and let Masako volunteer instead; turn 4 required the player to restate the boundary. IU turn 4 narrated "the weight of her words" while IU gave no answer to a direct source question; turn 5 required repetition. IU turn 10 did not answer whether any new physical evidence existed. The same atmosphere phrases and player feelings recur in both ten-turn runs. The current social-only scene guard removes some player-internal narration and unidentified speech in empty rooms, but direct-answer and mystery pacing gates remain open.

**Hosted retest:** beta `c1050c9` desktop/iPhone/standalone screenshots still contain player-feeling narration such as “You can feel the potential for connection.” The narrow scene guard is insufficient for agency and repetitive-atmosphere acceptance; this item stays open.

**Partial correction pending hosted proof (2026-09-26):** the exact "You can feel" form is now filtered in Terrace and IU world-model turns. Direct-answer behavior, repetitive atmosphere and the wider player-agency issue still require sustained play evidence.

**Hosted limit:** a fresh beta `fe54691` browser turn asked two housemates to introduce themselves after the player introduced themselves; a later housemate still asked “What’s your name?” Decorative kitchen narration remained. The direct-answer and repetition gates are still open.

**O12 opening text (2026-09-28):** the IU `opening.text` held 20 double-escaped `\\n` sequences. The chat bubble hid them (`formatMsgText` and `dialogue.js` rewrite every literal `\n`), but the raw `/api/chat` reply, the session `last_message` preview and storyteller history carried the literal escapes. The data had no real U+FFFD; the replay's "replacement characters" were curly quotes mangled by a Windows console. Fixed the field; `engine/content_validation.py::find_text_defects` plus a per-active-story test now gate literal `\n`/`\t` and U+FFFD with field paths; `scripts/verify_story_opening_browser.py` checks the raw API body and rendered opener in all three browser modes. Follow-up, not done: the frontend's global `\n` rewrite contradicts "preserve deliberate literal escapes" and masks authoring errors; revisit only if a story needs a literal backslash. The opening's second-person backstory ("You didn't ask for details") is O09/BL-29 content, unchanged here.

**O08 addressed questions (2026-09-28, hosted-verified on `a554c5a` with `scripts/verify_addressed_questions.py`):** `world_model/conversation.py::ConversationState` (saved in `WorldModel`) keeps player questions owed until the existing extraction call judges the previous reply answered/refused/unknown/deferred; chatter or someone else speaking stays "unanswered". Questions are recorded only when grounded in the current message. Open questions to a present addressee enter MUST ADDRESS and boost that speaker; an absent addressee is named once and nobody answers for them; stale ones lapse after 12 turns. No extra model call. Not covered: semantic checking that a given answer is truthful/grounded (O04/O26), and pacing/atmosphere repetition (O10).

## Touches
`backend/app/engine/prompt_builder.py`, `dialogue.py`, Terrace voice data, tests and hosted evaluation.

**O08 follow-up from hosted play (2026-09-29, beta `eb4cae1`):** the first version of the engine backstop closed an unresolved question only after two addressee replies, which guaranteed a second answer (seen three times: Minori's reason for joining and her hopes, Hikaru's favourite thing to cook). `conversation.py` `MAX_DIRECTED_REPLIES` is now 1: a question closes on the addressee's first reply after it was asked (a dodge is let go; the owner's rule is that repeating is the visible failure, forgetting is not). Verified live: eight questions to five housemates were each answered once and not repeated on later turns. Related still open here: stock phrases reused across characters and turns ([BL-47](BL-47-arrival-introductions-replayed-and-stock-lines.md)).
