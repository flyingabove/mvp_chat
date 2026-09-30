# Terrace: a refused ask walks the player outdoors

Owner design session 2026-09-29. This file is over the ~3 KB guideline on purpose: it holds the agreed design until it
ships, then the as-built rules move to `design/SOCIAL_ENGINE.md` and this section is deleted.

## BL-46 — A "leave together" ask moves the player, and a yes ends the game without asking

- **Open:** hosted beta 2026-09-29 turn 12: Minori declined in dialogue, but the narration moved the scene to the
  street for several turns ("glancing down the street", "as you walk back to the house"). One player line is read by
  four parts of the code that never check each other: the typed social act (`prompt_engine.py` ~L3243), the
  extractor movement guess (`MOVE`, applied ~L3191 *before* the act is decided), the regex fallback
  `_match_world_destination`, and companions (`companions.py` `INVITE`, only matters once the player moved). The decline
  directive (`social_acts.py` `directive`) never says where the scene is, so narration can drift even when state does
  not. The chat response has no location field, so the report came from narration alone. A second problem: an
  accepted `ask_leave_together` commits the ending immediately (`commit_mutual_departure`); the player never chooses
  when to end.

### Agreed design (owner decisions)

1. **Parentheses talk to the game master.** `(...)` and `[...]` are interchangeable. They go to the game master (the
   engine plus storyteller), not to the characters. The content can be a question (`(what does that mean?)`: answered
   in author voice, as today) or a command/action (`(I walk outside onto the street)`: performed and narrated in scene).
   The existing whole-message OOC header (`prompt_builder.py` "DIRECT CHANNEL") changes to cover both kinds.
2. **Who moves the player.** In order of authority:
   - A parenthesised action is an explicit command and always applies, even right after a decline ("you walk alone").
   - A plain first-person performed move ("I walk to the kitchen") still applies (`_match_world_destination`).
   - The extractor's movement guess is **ignored on any turn that carries a typed social act**. An ask, an invitation or
     a question never moves anyone before it is answered.
   - An ask plus a walk in one message (`"Minori, leave with me? (I walk onto the street)"`): the ask is decided
     first and the player walks either way; a yes still produces the choice card in point 5.
3. **"Leave together" means two things; decide which before judging.** A Jev question (new task `leave_meaning`, the
   same bounded pattern as `npc_decision.judge`, no extra LLM call) reads the player's line with the relationship
   status: `leave_as_couple` (leave the house/show for good together), `outing` (go out for a walk/date and come back)
   or `unclear`.
   - `leave_as_couple`: the normal `ask_leave_together` verdict. Terrace's win rule stays: they must already be a
     couple (`requires_relationship`, `romance_relationship_partner`); otherwise the hard `not_yet` ("we're not even
     together") applies.
   - `outing`: no typed act, no verdict, no cooldown, nobody moves this turn. The target answers the invitation in
     character; the player then goes with a parenthesised action or a performed move (companions follow as today).
   - `unclear`, or Jev unavailable while they are not a couple: the target asks a clarifying question in character
     ("Do you mean go for a walk, or leave the house together, for good?"). No verdict, no cooldown.
   - Jev unavailable while they are a couple: `leave_as_couple` (the current behaviour).
4. **The scene stays put on a decline.** Every non-accept directive names the current place: "The scene stays at
   {place}; nobody leaves unless the player says so."
5. **A yes to leaving together shows a choice card, never an instant ending.** Accepting records the yes and a
   `pending_choice` in session state. The chat shows an in-chat card: **[Leave together now — play the judges' ending]**
   and **[Keep talking]**.
   - Leave now: commit `commit_mutual_departure`, then run the finale turn (exit scene + studio panel, "You win!" card).
   - Keep talking: the card collapses and the game master says: `(Minori's yes stands. Type [play ending] or tap
     "Play ending" when you're ready.)` A "Play ending" chip stays in the chat. `[play ending]`/`(play ending)` works too.
   - The card is part of the saved session, so a reload, app restart or resume mid-choice shows it again
     (the history endpoint returns `pending_choice`, like `ending`).
   - The yes lapses at the end of that in-game day, or at once if the relationship ends or the partner leaves the
     house; the game master then says so. (Owner skipped this question; this is the proposed default.)
6. **A yes to a future plan also offers a jump.** When an accepted player/resident plan with a future time is
   recorded ("date next Saturday"), a card offers **[Skip to Saturday 12:00]** / **[Keep playing]**. Skipping runs the
   world forward to the due time (everything in between happens off-screen: consequences are the player's) and brings
   the counterpart to the player. Plans are extracted from the previous exchange, so the card appears one turn after
   the yes. The meeting place is not tracked yet (BL-35); the counterpart joins the player where they are.
7. **Ordinary "come with me now" invitations move at once, no card** (`companions.py`, unchanged). Cards are only for
   things that skip time or end the game. `INVITE` keeps `leave` ("let's leave for the cafe" is a real invitation).
8. **Remove the player's "leave alone" mechanic.** The player cannot end the game by walking out. `leave_alone` is
   removed from the social acts, the extractor prompt, the six-strangers story JSON, `record_solo_departure`,
   `commit_solo_departure` and the `left_alone` ending. The only losing exit is the director cutting the player
   (the `director_patience` clock), which ends with the panel judging the run.
9. **Bots use the same choice.** The chat response carries `pending_choice {id, kind, prompt, options}`; the choice is
   sent back as a normal chat message (`__choice__:<id>:<option>`), so the player agent and the arena can answer it. The
   arena defaults to the ending/skip option so runs still finish.
10. **`location_id` in the chat response** so tests and browser checks can see where the player is.

- **Next:** failing-first tests through `/api/chat` with a scripted extractor: (a) `ask_leave_together` + `not_yet` +
  extractor `MOVE -> neighborhood` leaves the player's and Minori's places unchanged and the directive names the room;
  (b) the same plus `(I walk onto the street)` moves the player alone; (c) an accept returns `pending_choice`, keeps
  `over=False`, and `__choice__:...:leave_now` produces the win ending; (d) `outing`/`unclear` give no verdict and no
  cooldown. Update the arena player agent for `pending_choice`. Behaviour change for Terrace: needs the arena gate at
  the next promotion.
- **Touches:** `api/prompt_engine.py`, `engine/prompt_builder.py`, `world_model/social_acts.py`, `turn.py`,
  `romance.py`, new `world_model/leave_meaning.py` and `world_model/choices.py`, `extractors/turn_extractor.py`,
  `rules/endings.py`, `api/user_sessions.py`, `stories/7_six_strangers/six_strangers_story.json`, `frontend/index.html`,
  `api/debug_engine.py` / arena player agent, `design/SOCIAL_ENGINE.md`.
