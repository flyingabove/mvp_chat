# The opening hook: forward pull in the first hour

Design-bearing item (owner, 2026-10-01). Bucket rules: `.claude/skills/add-and-remove-from-backlog/SKILL.md`. When a phase
ships, move its as-built description to `design/SOCIAL_ENGINE.md` (engine) or `design/TERRACE_HOUSE.md` §11 (content),
delete the phase here, and delete the item with the last phase. What already exists (arrival staging, doorway clock clip,
type round, acquaintance conduct, signals) is described in `design/TERRACE_HOUSE.md` §11; do not rebuild it.

## BL-95 — The opening is polite and awkward, but nothing is pending
- **Bucket:** C (engine) + A (authored text and data). No B. Rejected B candidates: a Terrace studio-panel aside on the
  slips (the panel speaks only at the end, owner 2026-10-01) and a Terrace-only first-impression ritual module. Fallback
  only if sealed notes prove too loose after the sims: a story module, with the reason in the fixing commit and in
  `design/TERRACE_HOUSE.md`.
- **Open (code read 2026-10-06):** none of H1 to H5 exists. After the type round nothing is pending: arrivals are
  unannounced (the directive in `prompt_builder.py`, `opening_due`, asks the first resident only to "react naturally");
  everyone starts as a blank so first reads are never wrong; the type round is a single fixed question that every
  answerer answers truthfully (`opening_scene.group_ritual_brief`); no scheduled event is awaited. Success is
  unmeasured (BL-87 rubric S7 "ends on a hook"; the rubric shipped as P-05, no opening data yet).
- **Goal:** by about turn 14 (about 55 in-world minutes) the player holds questions it cannot answer (who is read
  wrong, whose name is on which slip, what is under the card). No outcome is scripted.
- **Next:** answer the questions below, convert the phases into plan tasks (`documentation/plan/README.md`), claim files.
  `world_model/turn.py` and `prompt_engine.py` are shared with P-08 to P-11.
- **Touches:** `engine/opening_scene.py`, `engine/prompt_builder.py` (arrival directive, `opening_scene_brief`),
  `engine/gameplay.py` (`advance_time` clip), `engine/world_model/{signals,turn,model}.py`, `engine/rules/acquaintance.py`,
  `api/prompt_engine.py` (state persistence, `[note:]` parse), `stories/7_six_strangers/six_strangers_story.json`,
  `tests/backend/app/engine/test_opening_scene.py`, `test_terrace_opening_text.py`.

### Features
- **H1 Foreshadowed arrivals (C + A).** `opening_scene.foreshadow_due(state, minute_after)` returns an authored cue when
  the next unarrived resident's minute is within `foreshadow.minutes` (default 5) and none was shown for that arrival.
  The server appends the cue after the storyteller reply (mirror of `opening_arrival_segments`); a skip shows it before
  the arrival beat. The storyteller gets one must-address line: "Something outside tells the room a new person is about
  to arrive. Do not say who, do not describe them. Each person present reacts in their own manner with one small
  behaviour. The server shows the sound after your reply; do not narrate it." Cues are keyed by arrival ordinal, never
  by resident. Data: `opening.arrival_sequence.foreshadow = {minutes, cues[]}`; absent means off. State:
  `opening_foreshadowed_ids` (older saves restore as all shown). Must hold: no identity, gender or count; once per arrival.
- **H2 Misleading first impressions (C + A).** `manner` is a pure function of dials: `easy` (sociability >= 0.65 and
  pride < 0.6), `guarded` (sociability <= 0.35 or pride >= 0.7), else `correct`. Acquaintance levels may carry
  `manner: {easy, correct, guarded}` text that `_conduct_note` (`world_model/turn.py`) appends; none from `familiar` up. A
  hidden first impression (float 0..1, seeded from the house seed, bounded by `first_impressions.spread`) is independent
  of manner, so first reads are unreliable. It must never move a tier. Readers: `signals.py` (interest plus
  `impression * fade`, `fade = max(0, 1 - turns_together/60)`) and sealed notes. **Decide before building:** P-08 stances
  have shipped, so express the impression as a `curious` stance with cause `first_meeting` (a stance rule plus a seeded
  trait) rather than a separate store. Must hold: the impression is in no prompt and no player-reachable surface; manner
  never depends on it (test: swap impressions, manner unchanged).
- **H3 Arrival collisions and the untouched card (C + A).** Append to the arrival directive: "Everyone present reacts to
  the newcomer in their own manner. If one person was alone with the player, they shift (straighten, go quieter, or
  relax) as one small behaviour that signals nothing about the player. The newcomer has not heard the player's name
  unless it is said in front of them." Add `group_ritual.prop = {untouched_until: "all_arrived"}`; while the ritual is
  pending the opening brief says a card lies face down, nobody touches it until all are in, and if the player reaches for
  it a resident says they would rather wait, without explaining the rule. The line stops when the ritual fires.
- **H4 Type round upgrade (C + A).** (a) `group_ritual.beat`: authored narration shown by the server before the reply.
  (b) The brief orders speakers by manner (easy first, guarded last or deflecting). (c) With probability
  `group_ritual.performative_chance` rolled once per ritual from the house seed, the answerer with the lowest `candor`
  (ties by seed; never the player) gets no hint and "answers with what they think the room wants to hear". At most one.
  (`candor` is already read by `stakes.py` and `npc_decision.py`.)
- **H5 Sealed notes (C, generic secret ballot).** A story authors `opening.sealed_note`. The engine: (1) shows the card
  beat the turn after the ritual fires; (2) each NPC's slip is chosen with no model call by score over every other
  resident (author's impression of the player, or graph-edge affinity, plus `opposite_gender_bonus` where
  `appraisal.eligible` allows, plus a bump for whoever spoke most to the author, plus seeded jitter); (3) the player's
  slip is the private `[note: name]` or `[note: none]`; the content never enters the storyteller prompt; the name is
  resolved by the BL-43 matching, an unresolvable name is asked again and never guessed, blank after 3 turns; (4) the
  reveal fires on the first turn whose end minute passes `reveal.at_clock`; `advance_time` clips to it like an arrival
  and a time skip stops there; (5) the storyteller receives slips in shuffled order, each with one physical tell from the
  author's manner (`slip_tells`), and never says who wrote what; (6) the reveal is a witnessed world-model event and
  changes no standing. State: `sealed_notes`, `sealed_notes_phase` (pending, collected, revealed),
  `sealed_reveal_minute`; older saves restore as revealed. Must hold: the reveal cannot be skipped; authors stay
  engine-only; NPCs do not know the player's slip until the reveal.
- **H6 Overheard fragment:** seam only. The reveal is eligible for BL-87 `coincidence_budget`. Needs P-11 earshot; delete
  this line when P-11 ships.
- **H7 Authored words (A):** in `six_strangers_story.json`, pinned by `test_terrace_opening_text.py`.
  - Opening segment 4: "... The camera does not mind. On the low table, between two empty cups, a card lies face down.
    It was here before you. Nobody has touched it. Beyond the hall is the {{PLAYER_BEDROOM}} you will share. The next
    arrival is still minutes away; the first words are yours."
  - Foreshadow cues (by ordinal): "Outside, a taxi door shuts. Neither of you mentions it." / "Slippers shuffle in the
    entryway, then stop, as if someone is reading the instructions on the wall." / "The front-door lock clicks twice.
    Whoever is out there is being polite about it." / "A suitcase wheel catches on the doorstep. There is a pause, a
    small apology to nobody, and then the door."
  - `group_ritual.beat`: "The card is turned over. Marker, careful capitals: WHAT IS YOUR TYPE? Nobody reads it aloud.
    Everybody reads it."
  - `sealed_note.beat`: "Under the first card there is a second, shorter one: 'Write one name. Who would you most like
    to talk to tomorrow? Fold it once. It will be opened tonight, after dinner.' There is one pen. It travels around the
    table in the wrong order." plus the system line "(Write your slip as [note: name], or [note: none]. Nobody will see
    it.)"
  - `sealed_note.closing`: "Six folded slips go into a paper bag. Someone puts the bag on the high shelf, where everyone
    can see it and no one can reach it without being seen. Dinner is at seven. It is {{CLOCK}}."
  - `sealed_note.reveal.beat`: "After dinner the paper bag comes down from the shelf. The slips are unfolded one at a
    time, in the order they come out. Nobody signed anything."
  - Manner lines (appended to `strangers` and `acquaintances`): easy "Your manner this first hour is easy and talkative;
    you fill a quiet a beat too fast. This says nothing about how much you like anyone."; correct "... correct and even:
    you answer what is asked and ask one thing back."; guarded "... guarded: short answers, and you do not fill a
    silence. If the player's line leaves you nothing to answer, do one small thing (a sip, a glance at the camera, a cup
    straightened) and wait."
  - Tuning: `foreshadow.minutes` 5, `first_impressions.spread` 0.6, `performative_chance` 0.6, `opposite_gender_bonus` 0.3.
  - Reveal prompt: "Slips in reading order: <n. tell> ... No one signed anything. Do not say or hint who wrote what.
    Residents may react to hearing their own name or the player's, each in their own manner."

### Phases (each ships alone, failing-first tests, `/ship-and-verify`)
P1 H7 card sentence, H3 prop and reaction line, H4 (a)(b). P2 H1. P3 H2 manner overlay, then the impression. P4 H4 (c).
P5 H5. P6 H6 (after P-11). Gate each: offline sim `scripts/terrace_ollama_sim.py --opening 15` and an arena gate.

### Tests and measurement
- Unit: H1 cue once, after the reply, names no one, shown before the arrival on a skip, legacy save replays nothing; H2
  manner pure of dials, impression absent from the assembled prompt, tiers unchanged, fade zero at 60 turns; H3 prop line
  only while pending; H4 beat precedes reply, at most one performative answerer, lowest `candor`, never the player; H5
  slips deterministic per seed with no model call, `[note:]` never in the storyteller prompt, unresolvable name asked
  again, reveal fires once and stops a skip and restores from a save, authors in no prompt; story validation (cue count
  equals arrival count, `{{CLOCK}}` resolves).
- Offline (seeds 0 to 11, both genders, Gemini + Jev): cue before each arrival 4 of 4; name used before heard 0; intimacy
  and shared-history markers 0 (BL-76 counts); guessing "who likes me" from manner alone right 40 to 65%; performative
  answer in 40 to 70% of rituals; a human reads every transcript before any gate. Hosted: one capped run after P1 and P5,
  read against BL-87 S1, S4, S7, S8 (advisory).
- Rules: two LLM calls per turn unchanged (`[note:]` rides on extraction, Jev-assisted for names); selection is seeded
  and deterministic; no story ids, names or genders in engine code; no player-visible log of slips; no standing change
  from a slip; nudges, not scripted outcomes.

### Open owner questions (answer before P1)
1. Scheduled reveal after dinner, or hold until a later event (first date, end of week one)?
2. Unsigned slips (authorship is the mystery) or signed?
3. Neutral "who would you most like to talk to tomorrow" or more romantic ("who caught your eye")?
4. May an NPC lie about their own slip later (P-14), or only dodge?
5. Face-down card from turn 0, or when the second resident arrives?
6. Same performative answerer on replay of a house seed, or random per run?
7. Should a high impression slightly raise `easy`, or stay independent?
