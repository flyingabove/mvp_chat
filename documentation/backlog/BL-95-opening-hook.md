# The opening hook: forward pull in the first hour (engine first; the story authors the words)

**Principle (owner, 2026-10-01):** default to the generic engine / character-object route (bucket C); hardcode only
authored text (bucket A); a game-only mechanic (bucket B) is a strongly discouraged last resort, not forbidden. The
buckets and the test for choosing between them are in `.claude/skills/add-and-remove-from-backlog/SKILL.md`. This item
needs **no B**; the B candidates it examined are listed in section 5.

This is a **design-bearing item** (owner request, 2026-10-01), so it is long. When a phase ships, move its as-built
description into `design/SOCIAL_ENGINE.md` (engine) or `design/TERRACE_HOUSE.md` (content), delete the phase here, and
delete the item when the last phase ships.

## BL-95 — The opening is polite and awkward, but nothing is pending

- **Bucket:** C (engine) plus A (authored text). No B.
- **Open (read from code and the story file, 2026-10-01, beta `383082e`):** strangers now behave like strangers
  (acquaintance ladder with `conduct`, affinity signals, authored bows and "hajimemashite", staggered arrivals, a
  one-time "What is your type?" `group_ritual`). What the opening still lacks is **forward pull**. After the type round
  nothing is pending and nothing is promised; the first hour ends the way it started, with six polite people. Concretely:
  - An arrival is a surprise the player gets no warning of, and the people in the room do not react to it as a group
    (the directive in `prompt_builder.py` asks only that the first resident "react naturally").
  - Everyone starts as a blank. The player's first reads of people (who is warm, who is cold) have no reason to be
    wrong, so there is nothing to later correct.
  - The type round is a single fixed question that every answerer answers truthfully (`opening_scene.group_ritual_brief`
    hands each answerer one hint from their real tastes). Nobody ever answers to please the room.
  - There is no scheduled event the player is waiting for. The longest-lived promise in the game is the clock itself.
  - Success is not measured: BL-87 rubric item S7 ("ends on a hook") has no data yet.
- **Goal:** by the end of the opening (about 14 turns, about 55 in-world minutes) the player is holding questions they
  cannot yet answer: who is the person I am reading wrong, whose name is on which slip, what is under the card. The
  engine produces those questions from character objects and the clock; no outcome is scripted.
- **Next:** build in the phases of section 9. Do not start before the owner has answered section 11, and before any
  code, convert the phases into plan tasks (`documentation/plan/README.md`) and claim the files they touch (`turn.py`
  is shared with P-07 to P-11).
- **Touches:** see section 10.

## 1. What exists today (do not rebuild)

| Piece | Where | State |
|---|---|---|
| Authored opening segments with `{{GREETER_CUE}}` and `{{GREETER_LINE}}` | `six_strangers_story.json` `opening.segments`, `first_resident` | shipped |
| Staggered arrivals at minutes 8/18/28/38, authored nameless entrance cue plus authored self-introduction | `engine/opening_scene.py` `advance_opening_arrivals`, `opening_arrival_segments`; `prompt_builder.py` arrival directive | shipped |
| Clock stops at the next doorway (turns never skip an arrival) | `engine/gameplay.py` `advance_time` | shipped |
| Entrance retelling is dropped when the storyteller repeats it | `opening_scene.strip_generated_arrival_repeats` (BL-93) | shipped |
| One-time group question with per-person hints from authored tastes | `opening_scene.group_ritual_brief`, `mark_group_ritual`; `opening.group_ritual` | shipped |
| Acquaintance ladder with per-level `conduct` and `reminder` | `engine/rules/acquaintance.py`, `turn._conduct_note` | shipped |
| Ambiguous affinity signals with decoys | `world_model/signals.py` | shipped |
| Temperament dials (`sociability`, `pride`, `candor`, ...) and MBTI defaults | `engine/rules/personality.py`, `rules/mbti.py` | shipped; `candor` has no consumer yet |
| Private aside convention (a `[confessional: ...]` note is unspoken, no housemate hears it) | story `mode` convention, storyteller prompt | shipped |

## 2. The hook in one paragraph

A card lies face down on the table from the first second and nobody touches it. Every arrival is heard before it is
seen. Each resident's *manner* (easy, correct, guarded) comes from their temperament and says nothing reliable about how
much they like the player, because each also holds a hidden first impression the engine keeps to itself. When the sixth
person is in, the card is turned over: the type round, in which one answerer tells the room what the room wants to hear.
A second card follows: everyone privately writes one name on an unsigned slip that will be opened after dinner. The
player then spends the first evening reading faces with a paper bag on a high shelf in view.

## 3. Timeline of the first hour (Terrace, default pacing)

Turns are 3 to 5 in-world minutes (`dialogue_pace`), and a turn is clipped to land exactly on the next arrival.

| Turn | Clock | Beat | Source | Bucket |
|---|---|---|---|---|
| 0 | 3:00 | Opening: the room, the greeter, the face-down card, the slippers question | authored segments | A |
| 1 | 3:04 | First exchange with the greeter. End of turn: the first sound outside the door | authored foreshadow cue 1 | C + A |
| 2 | 3:08 | Arrival 1, mid-conversation; the greeter shifts | authored entrance + model | C + A |
| 3-4 | 3:12-3:16 | The pair becomes a trio. The card is looked at, not touched. End of turn 4: sound 2 | model + cue 2 | C + A |
| 5 | 3:18 | Arrival 2. The player or the newcomer asks about the card; a resident says they would rather wait | authored entrance + brief | C + A |
| 6-7 | to 3:26 | Round of name, age, work. End of turn 7: sound 3 | model + cue 3 | C + A |
| 8 | 3:28 | Arrival 3 | authored entrance | C + A |
| 9-10 | to 3:36 | Conversation shapes by who was drawn. End of turn 10: sound 4 | model + cue 4 | C + A |
| 11 | 3:38 | Arrival 4: six people and a card | authored entrance | C + A |
| 12 | about 3:41 | The card is turned over: "What is your type?" Two or three answer; one answer is performative | authored beat + brief | C + A |
| 13 | about 3:45 | The player answers (or does not). A second card appears: write one name | authored beat + system line | C + A |
| 14 | about 3:49 | Residents write; the player writes `[note: name]` privately. The slips go in a bag on a high shelf | authored closing | C + A |
| about 30 turns later | 8:00 pm | After dinner: the slips are read, unsigned. The reveal stops any time skip | authored frame + model | C + A |

## 4. The features

Each says what the player experiences, how it works, what is data, what is engine, and what must hold.

### H1. Foreshadowed arrivals (the doorbell roulette)
- **Experience:** one turn before each arrival the room hears something (a taxi door, slippers, a lock). The people in
  the room react in their own manner. Nobody knows who it is. Each arrival becomes a small lottery.
- **Mechanism (C):** `opening_scene.foreshadow_due(state, minute_after)` returns a cue when the next unarrived
  resident's minute is within `foreshadow.minutes` (default 5, equal to the longest opening turn) and no cue has been
  shown for that arrival. The server appends the authored cue narration **after** the storyteller's reply that turn
  (mirror of `opening_arrival_segments`, which comes before). The storyteller gets one must-address line (section 6)
  so the reaction is written, not the sound. Cues are keyed by arrival ordinal, never by resident, so they never name
  or describe anyone.
- **Data (A):** `opening.arrival_sequence.foreshadow` = `{ "minutes": 5, "cues": [ ...one per arrival... ] }`. Absent
  means off, so every other story is unchanged.
- **State:** `GameState.opening_foreshadowed_ids` (persisted; saves from before this feature restore as "all
  foreshadowed" so no cue is replayed into a game in progress, as `opening_ritual_done` does).
- **Must hold:** the cue never reveals identity, gender or count; it appears at most once per arrival; a skip that jumps
  past it shows it before the arrival beat (never after).

### H2. First impressions that can mislead (held, and manner)
- **Experience:** the person who seems warmest may feel nothing and the person who seems cold may be the one who wrote
  your name. The player's reading of manner is fair but unreliable.
- **Held impression (C):** a new `WorldModel.first_impressions[resident]`, a float 0..1, seeded deterministically from
  the house seed at world build (same hashing as `rivals.seed_rival_aims`), bounded by `first_impressions.spread`.
  It is **a separate store, not standing**, so it can never move a tier and love still takes days. Its only readers
  are: `signals.py` (interest = standing fraction plus `impression * fade`, `fade = max(0, 1 - turns_together / 60)`,
  so it fades into real standing) and the sealed notes (H5). It is **never written into any prompt**. P-08 (stances)
  replaces this store with a `Stance(kind=curious, cause=first_meeting)`; keep the seed data shape so P-08 can read it.
- **Manner (C + A):** a resident's `manner` is a pure function of their dials: `easy` (sociability at least 0.65 and
  pride under 0.6), `guarded` (sociability at most 0.35, or pride at least 0.7), otherwise `correct`. Each acquaintance
  level may carry `manner: { easy, correct, guarded }` text; `turn._conduct_note` appends the text for the person's
  manner. Because manner comes from dials and the impression is seeded separately, they are independent, which is
  what makes first reads unreliable. Level `familiar` and above carry no manner text, so the overlay stops once people
  know each other.
- **Silence rule lives here:** the `guarded` text tells the person not to fill a silence but to do one small thing and
  wait; the `easy` text tells them to fill a quiet a beat too fast. Group energy follows who was drawn (owner, 2026-09-30)
  without any script, and deadpan humor comes from the silences.
- **Data (A):** Terrace's three manner lines per level (section 6); `first_impressions.spread` (Terrace 0.6 of the
  range, so a few people start clearly curious and most start near zero).
- **Must hold:** the impression appears in no prompt, no log shown to a player and no `debug` surface that a player
  can reach (admin-only inspection is allowed); manner never depends on the impression (test: swap impressions, manner
  unchanged); tiers and `days_known` gates are untouched.

### H3. Arrivals as collisions, and the card nobody touches
- **Experience:** the greeter was alone with you; the newcomer walks in on the middle of your sentence and the greeter
  shifts (straightens, goes quieter, relaxes). Reaching for the card gets a polite "let's wait for everyone", and the
  rule is never explained. Waiting for the sixth person becomes the countdown.
- **Mechanism (C):** extend the existing arrival directive (`prompt_builder.py`, where `opening_due` is built) with the
  reaction line in section 6, and add a `group_ritual.prop` `{ "untouched_until": "all_arrived" }` that adds the "nobody
  touches it" line to `opening_scene_brief` while the ritual is pending. Generic: any story with a group ritual can hold a
  prop; a story without one is unchanged.
- **Data (A):** the face-down card sentence in opening segment 4 (section 7), and the ritual's authored card text.
- **Must hold:** the prop line appears only until the ritual fires; it does not stop the player from trying.

### H4. The type round, upgraded
- **Experience:** the card is turned over by an authored beat (the same words every game), then the most easy-mannered
  resident says the obvious thing aloud and the guarded ones answer last or deflect. One answer is meant to please the
  room, not to be true. The player is then asked.
- **Mechanism (C):** (a) `group_ritual.beat`: an authored narration shown by the server before the reply, like arrival
  beats; (b) the brief orders speakers by manner; (c) performative answerer: with probability
  `group_ritual.performative_chance` rolled once per ritual from the house seed, the answerer with the lowest `candor`
  (ties by seed) gets no hint and the line "answers with what they think the room wants to hear" instead. At most one per
  ritual, never the player. This is the first consumer of `candor`; P-14 generalizes it.
- **Data (A):** `group_ritual.beat`, `group_ritual.prop`, `performative_chance` (Terrace 0.6).
- **Must hold:** at most one performative answer; no answerer mentions anyone in the room; the existing "at most one
  hint per answerer" rule stays.

### H5. Sealed notes (the pending reveal)
- **Experience:** after the type round a second card asks everyone to write one name, unsigned, to be opened after
  dinner. The player writes one privately. The bag sits on a high shelf in view of everybody. After dinner the names are
  read in random order with no authors. Someone is named three times. The player was named once, by someone.
- **Mechanism (C, new, generic: "sealed notes"):** a story may author `opening.sealed_note`. The engine, in order:
  1. Triggers the card beat the turn after the ritual fired (the same trigger style as `mark_group_ritual`).
  2. At the end of that turn the NPCs write. Each NPC's slip is chosen by a deterministic score over every other
     resident: for the player, the author's `first_impression` of the player; for other residents, the character-graph
     edge affinity (`character_graph.get_edge`), or zero if none; plus `opposite_gender_bonus` where
     `appraisal.eligible` allows it; plus a social-proof bump for whoever has spoken most to that author so far
     (`turns_together`); plus seeded jitter; highest wins. No model call.
  3. The player's slip is the private aside `[note: <name>]` (or `[note: none]`). The note's content never enters the
     storyteller prompt. The name is resolved with the existing name matching (BL-43); an unresolvable name is not
     guessed: the producers' pen waits (one open conversation obligation) and the name is asked for again. If the player
     never writes one within 3 turns, the slip is blank.
  4. The reveal fires on the first turn whose end minute passes `reveal.at_clock`. `advance_time` clips to it exactly as
     it clips to arrivals, and a time skip stops there with a parenthesized system line instead of jumping over it.
  5. The storyteller is handed the slips in a shuffled reading order, each with one physical tell derived from its
     author's manner (`slip_tells`: neat, pressed hard, underlined, crossed out once), and is told never to say who wrote
     what. The authors are known only to the engine. Whether anyone later claims or denies a slip is their own choice
     (candor-limited, P-14).
  6. The reveal is recorded as a witnessed world-model event so it reaches memories and, with P-08/P-09, stances (who now
     knows who was named). It changes no standing: a name on a slip is curiosity, not affection.
- **Data (A):** the card text, closing text, system hint, reveal frame, reveal clock, `slip_tells`, `question` wording,
  `opposite_gender_bonus` (Terrace 0.3).
- **State (persisted, restored as "revealed" for older saves):** `GameState.sealed_notes` (author, subject, tell),
  `sealed_notes_phase` (`pending`, `collected`, `revealed`), `sealed_reveal_minute`.
- **Must hold:** never miss what happened (asymmetric rule): the reveal cannot be skipped by a time jump; an ambiguous
  `[note: ...]` is asked again, not guessed. No telepathy: authors stay engine-only, NPCs do not know the player's slip
  until the reveal, and nobody can read the bag.
- **Why generic:** a secret ballot is a mystery's "write your accusation", a school story's "write your secret crush", a
  heist's "vote on the plan". Terrace supplies only words and numbers.

### H6. The overheard fragment (seam only; not built here)
Two residents in the kitchen say something ambiguous about the slips and the player passes the open door. It needs real
rooms and earshot (BL-85 locations, P-11), so this item builds nothing for it. The only seam: the reveal event is eligible
for BL-87's `coincidence_budget`. Delete this section when P-11 ships.

### H7. Authored words (A)
Everything the player reads that is fixed: the face-down card sentence, four foreshadow cues, the ritual beat, the second
card, the closing line, the reveal frame, manner lines, slip tells. All in `six_strangers_story.json`; text pinned by
`tests/backend/app/engine/test_terrace_opening_text.py`. Hardcoding is right here: it is the player's first sight, before
any model has context, and it is reality-show set dressing that carries no outcome.

## 5. Classification: where each piece belongs

Rubric: see the skill. A = authored text/data. B = game-only mechanic. C = engine or character object.

| Piece | Bucket | Why |
|---|---|---|
| Opening segments, greeter cues and lines, slippers question | A | Fixed before the first word; no outcome |
| Face-down card sentence, ritual card text, second card, closing, reveal frame | A | Set dressing, same each game |
| Foreshadow cue texts | A | Four lines, rotated by ordinal |
| Foreshadow trigger and shown-after-reply beat | C | Any story with staggered arrivals gains it |
| Held first impression store and its fade into standing | C | A character-object property any story with a standing track uses |
| `manner` derived from dials; manner text per acquaintance level | C engine, A text | Engine picks the key from dials; Terrace writes the lines |
| Arrival reaction wording; prop line | C | Prompt text on the arrival directive and opening brief |
| Ritual beat shown by the server; speaking order by manner | C | Generalizes the arrival-beat pattern |
| Performative answer (first `candor` consumer) | C | A character trait with a general consumer (P-14 widens it) |
| Sealed notes: NPC pick, private player note, reveal, skip stop | C, new | Ballot, secret crush, vote, accusation in other stories |
| Overheard fragment | C, deferred | Needs P-11 earshot |
| Terrace studio panel commenting on the slips | B, rejected | Panel speaks only at the end (owner, 2026-10-01); no mid-game aside |
| A Terrace-only "first-impression cards" ritual in its own module | B, not needed | The generic sealed-note form expresses it |

**B check (required by the skill):** if the generic sealed-note form proves too loose to be funny after the first sims,
the allowed fallback is a Terrace-only ritual in a story-specific module, with the reason written in the fixing commit and
in `design/TERRACE_HOUSE.md`. Nothing here needs it today.

## 6. Exact engine instructions (the prompt text each feature adds)

These strings are the contract the tests pin. The storyteller writes the prose; these constrain it.

- **H1 foreshadow (must-address, that turn):** "Something outside tells the room that a new person is about to arrive.
  Do not say who, and do not describe them. Each person present reacts in their own manner with one small behaviour (a
  straightened back, a glance at the door, a sentence that stops halfway). The server shows the sound itself after your
  reply, so do not narrate it."
- **H3 arrival directive (appended to the existing one):** "Everyone present reacts to the newcomer in their own manner.
  If one person was alone with the player until now, that person shifts in a way that fits their temperament
  (straightens, goes quieter, or relaxes) as one small behaviour; it signals nothing about the player. Bows are not in
  step. The newcomer has not met the player and has not heard the player's name unless the player says it in front of
  them."
- **H3 prop (opening brief, while the ritual is pending):** "A card lies face down on the low table. Nobody touches it
  until all six residents are in the room. If the player reaches for it or asks about it, a resident says they would
  rather wait for everybody. Nobody explains the rule."
- **H2 manner (Terrace data, appended to `strangers` and `acquaintances`):**
  - `easy`: "Your manner this first hour is easy and talkative; you fill a quiet a beat too fast. This says nothing about
    how much you like anyone."
  - `correct`: "Your manner this first hour is correct and even: you answer what is asked and ask one thing back."
  - `guarded`: "Your manner this first hour is guarded: short answers, and you do not fill a silence. If the player's line
    leaves you nothing to answer, do one small thing (a sip, a glance at the camera, a cup straightened) and wait."
- **H4 ritual (replaces the existing brief's opening, rest unchanged):** "The most easy-mannered resident present says
  the obvious thing about the card aloud and speaks first; guarded residents answer last or deflect." For the
  performative answerer only: "<Name> answers with what they think the room wants to hear, not their own leaning."
- **H5 second card (after the authored beat):** "Each resident writes one name privately. Show the writing only as
  behaviour (covering the slip, hesitating, writing at once), never what is written. Do not ask the player for a name;
  the system line already did."
- **H5 reveal (after the authored frame):** "Slips in reading order: <n. 'tell'> ... No one signed anything. Do not say or
  hint who wrote what. Residents may react to hearing their own name or the player's, each in their own manner."

## 7. The words (authored, exact), for `six_strangers_story.json`

Opening segment 4 (replaces the current one; segments 1 to 3 are unchanged):
> Neither of you knows how long a bow should last. The camera does not mind. On the low table, between two empty cups, a
> card lies face down. It was here before you. Nobody has touched it. Beyond the hall is the {{PLAYER_BEDROOM}} you will
> share. The next arrival is still minutes away; the first words are yours.

`foreshadow.cues` (rotated by arrival ordinal):
1. "Outside, a taxi door shuts. Neither of you mentions it."
2. "Slippers shuffle in the entryway, then stop, as if someone is reading the instructions on the wall."
3. "The front-door lock clicks twice. Whoever is out there is being polite about it."
4. "A suitcase wheel catches on the doorstep. There is a pause, a small apology to nobody, and then the door."

`group_ritual.beat`:
> The card is turned over. Marker, careful capitals: WHAT IS YOUR TYPE? Nobody reads it aloud. Everybody reads it.

`sealed_note.beat` (and the system line shown in parentheses, distinct from the story):
> Under the first card there is a second, shorter one: "Write one name. Who would you most like to talk to tomorrow?
> Fold it once. It will be opened tonight, after dinner." There is one pen. It travels around the table in the wrong
> order.
>
> (Write your slip as [note: name], or [note: none]. Nobody will see it.)

`sealed_note.closing` (`{{CLOCK}}` resolved from the game clock when the beat is shown):
> Six folded slips go into a paper bag. Someone puts the bag on the high shelf, where everyone can see it and no one can
> reach it without being seen. Dinner is at seven. It is {{CLOCK}}.

`sealed_note.reveal.beat`:
> After dinner the paper bag comes down from the shelf. The slips are unfolded one at a time, in the order they come out.
> Nobody signed anything.

## 8. The hook as it will appear on screen

Sample game: male player, persona name Paul, house seed chosen so the greeter is Arisa and the arrivals are Hayato,
Natsumi, Yuuki and Momoka in that order. Legend:
- **[AUTHORED]** shown byte for byte from the story file or from the text in section 7.
- **[MODEL]** written by the storyteller from the briefs in section 6. **This is a sample, never a golden string:** judge
  real prose by the BL-87 rubric (owner rule), and two runs will differ.
- **[YOU]** a sample player line. **[SYSTEM]** an engine message in parentheses.

**Turn 0 (before you type)**

> [AUTHORED] Three o'clock in Higashi-Gotanda. The glass front of the house shows your bag, your own face, and a camera
> already aimed at the door. In the entryway a row of slippers waits and nobody has said which pair is yours. Inside, the
> living room is far too tidy for six people. One resident has arrived before you. Four empty places wait around the low
> table; nobody has begun to eat.
>
> [AUTHORED] A woman in a sharply cut jacket looks at you a moment longer than is comfortable, then bows exactly once.
> You are the second person in the house. One man and one woman, alone, in a house built for a romance show: you both
> know it, and neither of you will say it first.
>
> **ARISA** [AUTHORED]: Ohata Arisa. Hajimemashite. ...That is the whole introduction. I trimmed it.
>
> [AUTHORED] Neither of you knows how long a bow should last. The camera does not mind. On the low table, between two
> empty cups, a card lies face down. It was here before you. Nobody has touched it. Beyond the hall is the boys bedroom
> you will share. The next arrival is still minutes away; the first words are yours.

**Turn 1**

> [YOU] Hajimemashite. I'm Paul. Sorry, I wasn't sure which slippers were mine.
>
> [MODEL] Arisa looks at your feet, then at the row of slippers, then at the camera, as if the camera might rule on it.
>
> **ARISA** [MODEL]: Paul-san. The blue ones were already out. I didn't want to choose for you.
>
> [MODEL] She bows again, smaller. You bow back, smaller. Neither of you can find where it ends.
>
> [AUTHORED] Outside, a taxi door shuts. Neither of you mentions it.

**Turn 2**

> [YOU] Do you know who else is coming?
>
> [AUTHORED] The front door opens. A man in a plain jacket looks at the chairs, then the table, then politely at no one in
> particular, and bows.
>
> **HAYATO** [AUTHORED]: Terashima Hayato. Hajimemashite. I cook, if that ever becomes relevant. It probably won't today.
>
> [MODEL] Arisa had opened her mouth to answer you. She closes it, stands a beat late, and gives him exactly the bow she
> gave you.
>
> **ARISA** [MODEL]: Ohata. I was going to say I don't know. Now I know one.
>
> [MODEL] Hayato bows to you. You bow to him. Arisa, still standing, bows once more to be safe. Hayato looks at the three
> seats and takes the one that makes the three of you a triangle.

**Turn 3** (Hayato has not heard your name yet; he hears it here)

> [YOU] Paul. Nice to meet you. Have you done anything like this before?
>
> **HAYATO** [MODEL]: No. The closest was a wedding where I was the only guest who didn't know the groom.
>
> [MODEL] Arisa's eyes go to the card on the table and stay there a little too long for someone who is not interested in it.

**Turn 4**

> [YOU] Is it okay if I sit here?
>
> **HAYATO** [MODEL]: Paul-san, it is a chair. Anyone may sit in a chair. ...I've been told I say that a lot.
>
> [MODEL] Arisa lifts her cup, discovers it is empty, and holds it anyway.
>
> [AUTHORED] Slippers shuffle in the entryway, then stop, as if someone is reading the instructions on the wall.

**Turn 5**

> [YOU] Should we just turn the card over?
>
> [AUTHORED] The front door opens. A woman stops at the door, finds the camera before she finds anyone's face, and gives
> it a flat look.
>
> **NATSUMI** [AUTHORED]: Saito Natsumi. Hajimemashite. Everyone just sits here and gets filmed, then. Fine.
>
> [MODEL] Nobody has answered you. Hayato looks at Arisa; Arisa looks at Hayato; each is waiting for the other to have an
> opinion.
>
> **HAYATO** [MODEL]: Maybe when everyone's here. It feels rude to start without them.
>
> **NATSUMI** [MODEL]: Then somebody say how many "everyone" is. I'd like to know how long I'm going to look at that thing.

**Turns 6 and 7 (ordinary talk: name, age and work go round the four of you; shown here only for the beat the engine adds)**

> [AUTHORED] The front-door lock clicks twice. Whoever is out there is being polite about it.

**Turn 8**

> [YOU] Does anyone know if there's a schedule?
>
> [AUTHORED] The front door opens. A man with a lot of energy in his shoulders starts a handshake toward the nearest person,
> thinks better of it, and bows instead.
>
> **YUUKI** [AUTHORED]: Byrnes Yuuki. Hajimemashite. Handshake or bow... I think I just did both again.
>
> [MODEL] Natsumi looks at his hand, still halfway out, and shakes it, flatly, to end the matter.
>
> **NATSUMI** [MODEL]: There. Now it's official.
>
> [MODEL] Yuuki laughs a second too long. Arisa looks at the card again.

**Turns 9 and 10 (the room settles: Hayato and Natsumi do most of the talking, Arisa answers when asked)**

> [AUTHORED] A suitcase wheel catches on the doorstep. There is a pause, a small apology to nobody, and then the door.

**Turn 11**

> [YOU] So that's five. Who's left?
>
> [AUTHORED] The front door opens. A woman with perfect posture sets her shoes in a straight line, rises, and bows to the
> middle of the room.
>
> **MOMOKA** [AUTHORED]: Mitsunaga Momoka. Hajimemashite. I will remember all your names. It will take me a day.
>
> [MODEL] Six people, one low table, and a card nobody has touched. Hayato counts the room with his eyes, gets to six, and
> nods once to no one.

**Turn 12 (the ritual fires)**

> [YOU] I think that's everyone.
>
> [AUTHORED] The card is turned over. Marker, careful capitals: WHAT IS YOUR TYPE? Nobody reads it aloud. Everybody reads
> it.
>
> **NATSUMI** [MODEL]: It's asking. Honest answer: someone who says what they mean. I've had enough of hints.
>
> **HAYATO** [MODEL]: Mine's boring. Someone who actually helps. Not someone who talks about helping.
>
> **YUUKI** [MODEL] (the performative answer): Funny! Someone who can keep up with me.
>
> [MODEL] Momoka says she will go later, in the voice of a person for whom later has a time on the schedule. Arisa says "Hm"
> and turns her empty cup a quarter turn.
>
> [MODEL] The question stays on the table. It is, somehow, looking at you.

**Turn 13**

> [YOU] Honestly? Someone who doesn't laugh at their own jokes as much as I do.
>
> **NATSUMI** [MODEL]: That's not a type. That's a review.
>
> [MODEL] Hayato laughs once through his nose. Arisa's cup stops turning.
>
> [AUTHORED] Under the first card there is a second, shorter one: "Write one name. Who would you most like to talk to
> tomorrow? Fold it once. It will be opened tonight, after dinner." There is one pen. It travels around the table in the
> wrong order.
>
> [SYSTEM] (Write your slip as [note: name], or [note: none]. Nobody will see it.)

**Turn 14**

> [YOU] [note: Arisa]
>
> [MODEL] You write, fold once, and pass the pen on. Hayato studies the ceiling with real commitment. Yuuki covers his slip
> with his sleeve. Momoka folds hers into exact halves.
>
> [AUTHORED] Six folded slips go into a paper bag. Someone puts the bag on the high shelf, where everyone can see it and no
> one can reach it without being seen. Dinner is at seven. It is 3:52.

*What the player is now holding:* who will read their name aloud, who wrote Paul, what Arisa's cup was telling them, why
Yuuki hid his slip, and a bag on a shelf for the next four hours of game time.

**Later, after dinner (about 30 turns on; the engine stops any skip here)**

> [AUTHORED] After dinner the paper bag comes down from the shelf. The slips are unfolded one at a time, in the order they
> come out. Nobody signed anything.
>
> **NATSUMI** [MODEL] (reading): Arisa. ...Natsumi. That's me, apparently. Arisa. Paul. Hayato. Arisa.
>
> [MODEL] The Natsumi slip is in very straight letters. The Paul slip has been pressed hard enough to dent the table.
> Arisa is named three times. She takes it the way a person takes a parcel they did not order.
>
> **YUUKI** [MODEL]: Okay, but who wrote what?
>
> **HAYATO** [MODEL]: That is the one thing nobody can ask.

(In this sample, the engine's secret authors were Arisa to Paul, Hayato to Arisa, Natsumi to Hayato, Yuuki to Arisa,
Momoka to Natsumi, and the player to Arisa. None of this is shown; the player can only reason about the tells.)

## 9. Build order (each phase ships alone, with failing-first tests; `/ship-and-verify`)

| Phase | Content | Why this order | Gate |
|---|---|---|---|
| P1 | H7 card sentence and ritual card text, H3 prop line, H4 (a) beat and (b) speaking order | Data plus brief only; the cheapest visible change; proves the server-shown-beat pattern for rituals | Offline sim `--opening 15`; arena gate (players see it) |
| P2 | H1 foreshadow | Small, isolated, generic | Same |
| P3 | H2 manner overlay, then the impression store and its `signals.py` read | Manner is data plus a pure function; the store follows once the overlay is measured | Same, plus the independence test |
| P4 | H4 (c) performative answer | Needs only the `candor` read | Same |
| P5 | H5 sealed notes | Largest; new state, parsing, clock clip, reveal | Same, plus integration test of the clip and a save/load test |
| P6 | H6 overheard fragment | Waits for P-11 earshot | Own item then |

Coordination: `turn.py` is touched by P-07 to P-11; claim the files before each phase (`scripts/work.py`). This item is
not a plan task yet; convert phases on owner approval.

## 10. Tests and measurement

- **Unit (per phase, no skips):**
  - H1: cue appears in the turn before an arrival, once, after the reply, never names anyone; a skip across it shows the
    cue before the arrival; absent config changes nothing; a legacy save replays nothing.
  - H2: `manner` is a pure function of dials; swapping impressions leaves manner unchanged; impressions appear in no
    prompt (assert over the assembled prompt); tiers unchanged for any seed; the fade reaches zero at 60 turns together.
  - H3: prop line only while pending; reaction line present on arrival turns only.
  - H4: beat precedes the reply; at most one performative answer; the answerer has the lowest `candor`; never the player.
  - H5: NPC slips are deterministic for a seed and rule-based (no model call); `[note: ...]` never reaches the
    storyteller prompt; an unresolvable name is asked again; the reveal fires once, stops a skip, restores from a
    save; authors never appear in any prompt or response.
  - Story validation: every foreshadow cue count equals the arrival count; every authored text exists; `{{CLOCK}}`
    resolves.
- **Offline measurement** (`scripts/terrace_ollama_sim.py --opening 15`, seeds 0 to 11, both genders, Ollama, no cost):
  1. cue shown before each arrival: 4 of 4 in every run;
  2. name used before it was heard: 0; intimacy and shared-history markers: 0 (existing BL-76 counts);
  3. scripted-versus-generated word share over the first 15 turns (record, do not gate);
  4. manner versus impression: the best guess of "who likes me" from manner alone should be right between 40% and 65% of
     the time over 12 seeds (chance for three manners is 33%, a perfect read is 100%);
  5. performative answers: at most 1 per ritual, in 40% to 70% of rituals at `performative_chance` 0.6;
  6. every sample's transcript is read by a human before any gate is set.
- **Hosted:** after P1 and again after P5, one capped run, approved by the owner first (AGENTS.md section 4), read
  against BL-87 rubric items S1, S4, S7 and S8 once P-05 exists (advisory until calibrated).

## 11. Rule checks and risks

- Two LLM calls per player turn: unchanged (every feature is prompt text or deterministic selection; the `[note:]`
  parse rides on the existing extraction pass, Jev-assisted for names).
- Hybrid judgment: selection is deterministic and seeded; the model writes; nuanced reading of a player's note goes to
  the extractor and Jev, never a regex alone.
- Asymmetric errors: "did the player write a note, and who" resolves toward asking again, never guessing; the reveal is
  never skipped.
- No story ids, names or genders in engine code: the opposite-gender bonus uses `appraisal.eligible`; all wording is data.
- No house log: the reveal is told only through the story; there is no list of slips or authors anywhere a player can open.
- Tone: nudges, never scripted outcomes. The reveal is a scheduled *scene*, not an outcome; what it means is the player's
  to work out.
- Pace: nothing here moves a tier. Held impressions are a separate store. A name on a slip changes no standing.
- Risks: (1) the slips could read as a confession device; mitigated by the neutral question and by no standing change;
  (2) the face-down card could read as a gimmick; mitigated by the deadpan ("Nobody has touched it") and by never
  explaining the wait; (3) performative answers could feel like the game lying; they are in-world people pleasing a
  room, and the type round is already fiction; (4) seed jitter could make easy houses; the 12-seed sweep decides the
  spread; (5) `turn.py` merge conflicts with P-07 to P-11; claim before editing.

## 12. Open questions for the owner (answer before P1)

1. Is a *scheduled reveal after dinner* (H5) what you want, or should the notes stay secret until a later event (the first
   date, the end of week one)?
2. Should the slips be unsigned (as drafted, so authorship becomes the mystery), or signed?
3. Is "who would you most like to talk to tomorrow" the right neutral question, or do you want it more romantic
   ("who caught your eye")? More romantic risks running ahead of "love takes days".
4. Should an NPC ever lie about their own slip when asked later (candor and scheming, P-14), or may they only dodge?
5. Is the face-down card present from turn 0 (as drafted), or should it appear when the second resident arrives?
6. Should the performative answer be visible to a careful player on a replay (for example, the same house seed gives the
   same performative answerer), or random per run?
7. Is manner independent of impression the right call (as drafted), or should a high impression slightly raise `easy`?
