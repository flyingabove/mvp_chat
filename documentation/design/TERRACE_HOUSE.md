# Game Mode: Terrace House

> **What this doc is for:** the single design doc for the Terrace House game mode (story `7_six_strangers`, "Terrace in the City"): its proposal (win, loss, courtship, judges panel), the generic engine mechanics it drives, and background on the real show (Appendix A). Edit it if anything about this game mode's design changes. Once parts ship, move the as-built description of the generic mechanics into `reference/` docs and mark them built here.

- **Status:** proposal, not built. Game-mode doc, moved here from `proposals/`. Created 2026-09-26, rewritten the same day after the owner Q&A (decisions in §2).
- **Closes when shipped:** [BL-33](../backlog/BL-33-terrace-win-path-hosted.md); BL-34 shipped (its hosted evidence is now a BL-86 acceptance check).
- **Engineering authority:** [consolidated BL-39](SOCIAL_ENGINE.md), updated 2026-09-28: character-centric model and phases A–J, incorporating BL-38's correctness contracts. This file specifies Terrace content, not a competing engine architecture. The original claim-lock and multi-call panel design has been corrected to match the latest owner decisions.
- **Background:** Appendix A (the real show and how it maps to the game).
- **Related:** [design/SOCIAL_ENGINE.md (social engine v2)](SOCIAL_ENGINE.md), [design/SOCIAL_ENGINE.md (cast lifecycle)](SOCIAL_ENGINE.md), [design/JEV.md (dynamic context)](JEV.md), [design/ROADMAP_NOT_BUILT.md (game design systems)](ROADMAP_NOT_BUILT.md).

## 1. The game in one paragraph

You are a cast member on a reality show. You move into a Tokyo house with **five random strangers** drawn from the authored pool. You **win** by getting an opposite-gender housemate to fall for you, over many in-game days of real effort, and to **leave the house with you**. Everyone has their own personality and their own conditions for love, and they won't simply tell you what those are. Rivals chase the same people. Gossip spreads. Lies get exposed. You **lose** if the **director** decides you're a dud, which happens when **three other couples leave happy before you do**. However you leave, the show ends the way it really does: **three studio panelists debate you at length**. They discuss your behavior, your romance and your character, and you read what everyone thought of you.

## 2. Owner decisions (2026-09-26)

| Topic | Decision |
|---|---|
| Frame | The game is a reality TV show. The player is a cast member. |
| After a win | Terrace: the departure scene, then the **long panel debate**, then the run ends. (Other stories may keep going after a win. Endings are configurable per story.) |
| Panel | **Three panelists from the real show: Reina Triendl ("Torichan"), Ryota Yamasato ("Yamachan") and Yukiko Ehara.** Honest mix of praise and roast, grounded in real events from the run. Verdicts may call the player good, bad or evil. About 2,000 words, **no skip**. |
| Panel on other exits | A **short segment** when NPCs leave (as a couple or alone). The **full debate** on any player exit: a win or a director cut. The player cannot leave alone (BL-46). |
| Difficulty | **No time limit.** Winning someone takes many days, strategy and conflict. No single-day wins. |
| Preferences | Every NPC is **fully authored** (likes, dislikes, dealbreakers, conditions). The **starting roster and arrival order are random** each run (5 strangers from the pool). |
| Battles | **All of them:** rival competition, conflicts with the crush, loyalty tests, confession risk. As dramatic as possible, emerging from the mechanics rather than scripted. |
| Mistakes | **Dealbreakers** can close a romance permanently. Other mistakes can be recovered from, slowly. |
| Stages | Hidden stages plus a **confession**. About **50% of NPCs are "standard"**. The rest have **personal conditions** (a height, a job, a family type, "must bring flowers on a date"…). Some conditions rule the player out from the start. NPCs are **reluctant to disclose** them. Rivals may figure them out first. |
| Player facts | Facts are elicited through chat. The first claim remains immutable history, not eternal truth. Testimony, belief, correction, changed circumstances and deliberate lies remain distinct; a contradiction alone is not proof of lying. |
| Two-timing | Allowed, but risky: gossip, loyalty tests, dealbreakers, and the panel will call it out. |
| Loss | **Fixed count: cut when 3 other couples have left happy.** After the 2nd, the **director phones the player**: "one more couple leaves before you and you're cut." |
| Cut ending | An exit scene with the director, then the full panel, then a Game Over card. |
| Cast names | **Keep the current names** (they match the real season's cast). Explicit permission to use real names (non-commercial app). See §9. |
| Engineering rule | **Build universal mechanics** that every story can use; Terrace configures them in story JSON. A Terrace-only mechanic is a strongly discouraged last resort (not forbidden): only when the generic route cannot express the need, kept in a story-specific module, never in generic engine logic. Dating stories can weight the LLM context toward relationships (adjustable per story). |

## 3. The generic mechanics (engine, all stories)

Six reusable systems. Terrace, the IU murder mystery and future stories differ only in their story JSON.

### M1. Standing tracks with gated ceilings

The core mechanic. It generalizes "the score can't pass 60 without X, Y and Z."

- A **track** is a 0–100 score that one character holds toward another (NPC → player, and NPC → NPC). Stories declare their tracks: Terrace has `romance`. The mystery could have `candor` (how much a suspect will tell you).
- A track has **tiers**. Each tier has a **ceiling** and **gates**. Points above a ceiling are **not banked**: the score stays at the cap until every gate of the next tier opens. So "over 60 is unattainable without X, Y and Z" is expressed as data.
- **Gains are slow by construction:** a per-day gain cap (`max_gain_per_day`), diminishing returns for repeating the same kind of action, and decay after long neglect. A big gesture can't jump tiers on day one.
- **Dealbreakers** close a track when the holder's scoped belief/evidence establishes the condition, never from unknown alone. New gains stop; losses still apply. Story content declares reopening rules, including correction of mistaken evidence; closure must not preserve an engine error as eternal truth.
- Cause-linked appraisals use extracted behavior and observed agreements with the holder's preferences. Bond is the single writer: legacy relationship deltas and derived impressions cannot both apply the same effect. Persist applied effects for ordered replay, including caps and discarded surplus.
- **Pure, deterministic, unit-testable:** `standing.apply(track, deltas, day) -> track`, `standing.evaluate_gates(track, facts) -> open/closed`.

Terrace `romance` defaults (standard personality):

| Tier | Range | Feels like | Gate to leave the tier |
|---|---|---|---|
| Strangers | 0–25 | polite | ≥2 days known |
| Friends | 25–45 | jokes, small favors | ≥1 real one-on-one conversation in private |
| Interested | 45–60 | seeks you out, jealousy | ≥2 **dates outside the house** (completed agreements) |
| **Confession** | cap 60 | — | an **accepted confession** (M4) |
| Dating | 60–75 | a couple in front of the house | ≥3 days dating, no unresolved conflict, no known two-timing |
| **Ready to leave** (eligibility, not another overlapping tier) | ≥70 and all Dating exit requirements | — | an explicitly accepted departure ask (M4); score alone never creates consent |

**As implemented (2026-09-29, `six_strangers_story.json` `social_tracks`):** friends need 2 days known; interested needs a private talk, or 6 filmed interactions with that person, or (between residents) 2 off-screen encounters; dating needs an accepted confession (player) or a formed couple (residents); committed (75+) needs 5 days known. The "≥2 completed dates" gate is dropped until dates can actually complete (BL-35); seeded campaigns showed no player could otherwise progress past 45. Residents change off-screen at 4x the base appraisal pace so NPC couples form and leave within weeks.

A **custom** NPC adds personal gates on top, for example:

```json
"romance_conditions": [
  {"id": "tall", "tier": "interested", "kind": "player_fact", "fact": "height_cm", "op": ">=", "value": 180,
   "on_fail": "dealbreaker", "disclosure": "gossip_or_trust_60"},
  {"id": "flowers", "tier": "dating", "kind": "event", "event": "gift", "match": {"item": "flowers", "during": "date"}, "count": 1,
   "on_fail": "cap", "disclosure": "hint_on_date"},
  {"id": "family_doctor", "tier": "confession", "kind": "player_fact", "fact": "family_profession", "in": ["doctor"],
   "on_fail": "cap", "disclosure": "best_friend_only"}
]
```

These content labels compile to BL-39's closed typed Condition vocabulary. Evaluation is local and three-valued (true/false/unknown); the supporting belief can come from hybrid semantic appraisal. JSON above is illustrative content, not a second runtime schema. Character viewpoints cannot read privileged world truth or another person's private track:

| Kind | Checks |
|---|---|
| `player_fact` | the holder's accepted belief from M2, not automatically the first claim |
| `event` | `world_model` events and agreements (gifts, dates, promises kept) |
| `relationship` | trust/suspicion/etc. on the graph edge |
| `knowledge` | the player (or holder) knows a given fact |
| `time` | days known, days dating |
| `absence` | "no known two-timing", "no exposed lie" |
| `track` | another track owned by this holder; another character's private score is unavailable |

**Reuse in other stories:** in the murder mystery, a suspect's `candor` is capped at 40 until the player presents a specific clue (a `knowledge` gate), and a confession requires `candor` ≥ 90. The mastermind win can later move from regex to standing, the same way Terrace moves now.

### M2. Player fact ledger (claims, locks, lies)

- A new extractor decision identifies **self-claims** in the player's message: height, job, age, family, hometown, relationship history, hobbies. The keys are declared by the story (`player_fact_keys`).
- The **first claim is immutable history**, recorded with its audience and valid time; it is not eternal truth or automatically believed.
- A later incompatible claim creates a **dispute** for listeners who receive both. Honest corrections, changed circumstances, mistakes and deliberate deception have distinct semantics. Gossip carries attributed claims and evidence, not automatic public lie exposure.
- The engine does not invent unknown player truth. Listeners appraise testimony using their own evidence, trust and skepticism. They can believe a consistent lie; verification may change their belief. Suspicion is not proof of intent, and perceived deception is distinct from engine-established deliberate lying.
- **Reuse:** any story where the player creates their own persona (an alias in a heist, a cover story in a spy game).

### M3. Secret rules and discovery (on existing epistemics)

- Each condition has a `disclosure` policy (`never`, `gossip`, `trust_N`, `best_friend_only`, `hint_on_<event>`). Conditions become facts in the **existing** knowledge system (`known_by`, gossip provenance, off-screen spread). No parallel store.
- The storyteller only sees a condition when the player is allowed to learn it. Otherwise it gets a behavioral instruction ("{NPC} cools noticeably when height comes up, but deflects if asked why"), so the player picks up **hints before rules**.
- **Rivals discover rules too**, through their own off-screen conversations (the existing gossip and off-screen resolver). A rival who learns "flowers on a date" first can act on it first. That's the "figure it out before others do" race.
- **Reuse:** hidden motives in a mystery, faction preferences in an adventure.

### M4. Social acts: confession and the departure ask

- One extractor decision, registered in the **existing pre-generation batch** (no extra LLM call), classifies the player's message into `NONE | CONFESS:<id> | ASK_LEAVE:<id> | ACCEPT_OFFER:<id> | LEAVE_ALONE`. The acts come from story config, so other stories can declare their own (e.g. `ACCUSE:<id>` in a mystery).
- **Hybrid decision:** extraction LLM plus Jev propose nuanced choices; the target Character enforces feasibility, standards and consent, returning ACCEPT, NOT_YET, REJECT or DEFER. A track qualifies an option, never forces acceptance. Reasons pass character disclosure policy before narration.
- **A confession can be a public risk:** witnesses perceive the outcome and appraise it individually; a private rejection does not automatically become house knowledge. Cooldowns and consequences are cause-linked and configurable.
- The response LLM narrates the tentative verdict. Validate meaning before display, then atomically commit effects, outcome and exact reply. There is no post-display act_confirmed repair and no extra LLM verification call.
- NPCs use the same acts toward each other off-screen, so **NPC couples form and leave by the same rules** as the player.
- The partner can also make the offer themselves when they're ready, and a plain "yes" from the player then counts.

### M5. Story clocks (counters with warning and trigger)

- Generic counters over event kinds with a `warn_at` beat and a `trigger_at` ending:

```json
"clocks": [{"id": "director_patience", "counts": {"event": "romance_ending", "exclude_participant": "player"},
  "warn_at": 2, "trigger_at": 3,
  "warn_beat": "director_call", "trigger_ending": "cut_by_director"}]
```

- A **beat** is a one-turn storyteller directive with authored intent. For example, the director calls the player off-camera: "Two couples have left happy. If one more leaves before you, you're done here." The director is an off-camera character (voice/phone only, not a resident).
- **Reuse:** "the killer strikes three times", "the storm arrives on day 5", "your cover is blown after 3 suspicions".

### M6. Endings and commentary (the panel)

**Endings registry:** each story lists its endings. `state.over` is no longer set ad hoc.

```json
"endings": [
  {"id": "left_together", "kind": "win",  "when": "romance_outcome == mutual_departure", "exit_scene": "...", "epilogue": "panel_finale", "ends_run": true},
  {"id": "cut_by_director","kind": "loss", "when": "clock director_patience",             "exit_scene": "...", "epilogue": "panel_finale", "ends_run": true}
]
```

`ends_run: false` supports NorthStar's "the world continues" for other stories.

**The commentary panel** is a story-declared cast of **commentators** outside the world (Terrace uses real panelists from the show; other stories may use their own). They can't be heard by residents and never reveal private thoughts that the footage wouldn't show. **Owner rule (2026-10-01): the panel speaks only at the end, when the player wins or loses.** No mid-game asides and no departure segments; NPC departures play in-scene.

| Mode | When | Length |
|---|---|---|
| `finale` | the player's run ends (win or cut) | ~2,000 words, no skip |

**Finale pipeline:**
1. **Run dossier (local):** only camera/public events and panelists' own appraisals. Include observable conduct and evidence IDs, never subjects' private impressions, hidden tier values, undisclosed conditions or confessionals. Separate opinion from observable fact.
2. **Outline (local):** select 5–7 evidence-backed segments. Each panelist appraises the same footage through their own tastes; disagreement should be plausible, not forced.
3. **One response LLM call:** render the exit scene, all structured panel dialogue and final verdict lines together within the normal response budget. Jev can assist scoped assessments; there are no extra outline, segment or verdict LLM calls.
4. **Validation and commit:** claims need actual supporting admissible evidence, not merely an ID. Validate before committing outcome/reply together. A truncated or invalid finale follows the master's safe failure contract.
5. **Delivery:** existing per-speaker renderer with portraits, tap to advance, **no skip button**, then ending card. Allocate finale output allowance explicitly and measure its latency separately.
- **Guardrail:** judge the player's **behavior**, never their worth. No slurs, no mocking appearance or identity, no piling on. The panel can call a move evil; it never says the player deserves harm. This is the lesson from the show's cancellation (see Appendix A.5).
- **Reuse:** the mystery's "press conference after the arrest", a courtroom epilogue, a sports broadcast.

### M7. Context focus profile (adjustable LLM context)

- `mode.context_focus` weights the existing Jev context-selection budget by category, e.g. Terrace `{"relationships": 0.5, "people_history": 0.3, "places": 0.1, "clues": 0.1}` versus the mystery `{"clues": 0.4, "places": 0.3, ...}`.
- Relationship-heavy stories get more of each prompt spent on who likes whom, recent conflicts, gossip and shared history, and less on room descriptions. It's one tunable number per category, in data.

## 4. Terrace configuration (story JSON only)

- **Roster:** random 5 of 17 from the pool (`randomize_initial_roster` already exists) plus random arrival order in the same-gender replacement queues. Every run is a different house.
- **Opening arrival sequence (built 2026-09-29):** The five NPC slots and player slot are reserved immediately at a strict three-men/three-women capacity. The player enters second at 3 pm; one random opposite-gender resident is already in the living room. Four selected residents are initially unplaced and hidden from public cast views and speaker catalogs. Their randomized entrance order fires at minutes 8, 18, 28 and 38 (re-spaced 2026-09-30 so each pair of strangers gets a few exchanges), at most one per ordinary conversation turn; an explicit wait can pass several entrances. Each entrance is the authored, nameless cue ("The front door opens. A woman in a long cardigan stops just inside the door...") followed by that resident's own stranger-style introduction, so the player learns names from the newcomers themselves. Each entrance updates physical presence and first-meeting state, and persists across saves. The first resident has an authored, personality-specific opening action and line (surname, "hajimemashite", a bow gone slightly wrong; nobody warm). After the last entrance, on the next turn, the show's one-time "What is your type?" round is handed to the storyteller (`opening.group_ritual`, built from each resident's own authored tastes; generic, persisted as `opening_ritual_done`). Closeness is governed by the generic acquaintance ladder (`acquaintance.levels`, see SOCIAL_ENGINE.md), so strangers act like strangers until time together earns more. Nobody begins eating during introductions; after all six are present, residents may choose to order food or prepare it together. The generic `opening.arrival_sequence` configuration and engine behavior can be reused by another story.
- **Authoring every NPC:** `likes`, `dislikes` (behavior tags), `dealbreakers`, `romance_conditions`, `disclosure`, `verify` behavior, `personality` (standard or custom), and their own romance tracks toward other residents, so NPC–NPC couples happen. **About half standard, half custom.** Custom conditions should come up naturally in a shared house (height, job, family, cooking, cars/driver's license, smoking, dream/career, gifts, punctuality, loyalty to friends).
- **Panelists** (real panel members from the show, used with permission; see §9):
  - **Reina Triendl ("Torichan"):** model and actress who joined the panel during *Boys & Girls in the City*. She gives the sweet, youthful, romantic read and decodes body language.
  - **Ryota Yamasato ("Yamachan"):** comedian from the duo Nankai Candies, famous for sharp, cynical and very entertaining critiques. He hunts for flaws and roasts.
  - **Yukiko Ehara:** singer, actress and TV personality. She is casual and relaxed, with thoughtful, big-sister insights that defend sincerity and call out games.
  - Each panelist's `stance` in the finale outline follows these roles, so they disagree naturally.
- **Director:** an off-camera voice character, "the director" (unnamed). `director_patience` clock: warn at 2, cut at 3.
- **Goal card** (shown before the opening, reopenable from the 3-dot menu). For a male player:
  > *You're the newest cast member of Terrace in the City. Find the woman you want, win her heart for real, and leave this house together. Nobody here is easy to win, and everyone has their own rules. Three other men want the same thing, and every couple that leaves before you makes the director doubt you. Three couples, and you're cut.*

  The female-player version swaps the genders. The mystery gets its own card ("Find who ordered the killing and make them confess").

## 5. Player experience walkthrough

1. **Day 1:** the goal card, then five strangers. Polite small talk. Nothing moves fast.
2. **Days 2–5:** the player notices Minori lights up about cooking and goes cold when Makoto brags. Gossip from Mizuki: "she'd never date someone shorter than her dad." The player, who never mentioned their height, now has to decide what to claim. **Lying is possible and dangerous.**
3. **Days 6–10:** two dates outside the house. A rival asks Minori out first on a free evening. A rival learned about the flowers before you did. The panel's asides needle the player about their hesitation.
4. **A confession:** too early brings a public rejection, a cooldown and an awkward dinner. At the right time it's accepted and they're dating. Two-timing now risks a loyalty test.
5. **Meanwhile:** an NPC couple leaves, with a short panel segment. After a second couple, **the director calls.**
6. **The ask:** "Minori, let's leave together." The engine checks the track (≥70, all gates) and the answer is yes. She says yes in her own words, they pack and leave.
7. **The finale:** about 2,000 words of the three panelists arguing about you. "The height thing: did you actually lie to her?" "It was calculated, but it worked." Verdict labels, then the victory card.

## 6. What changes in existing code

| Existing | Change |
|---|---|
| `world_model/romance.py` regex adapters | Replaced by M4 acts plus M1 standing. `romance_outcome` and the lifecycle removal logic are kept. |
| `gameplay.win_condition_detected` | Reads the endings registry (M6). Regex stays only as a legacy fallback for stories without `endings`. |
| `prompt_engine.py` `END GAME …` string | A structured `ending` payload and panel segments. `debug.html` keeps its text marker. |
| `mode.narrator_asides` (unnamed) | Removed from Terrace. The named panel speaks only in the finale. |
| Relationship edges (trust/affection/…) | Kept. They are inputs to tracks, not replaced. |
| Off-screen resolver, gossip, agreements, cast lifecycle | Reused as the substrate for NPC–NPC courtship, rule discovery and couple departures. |

Module ownership and implementation order follow consolidated BL-39. Persona belongs to Character, standings to Bond, shared rules/clocks to StoryRules and commentary to a scoped rendering service; do not build parallel free-function stores from this content design.

## 7. Build order (each phase ships and is verified on beta)

Use consolidated BL-39 section 10's A–J roadmap and independent correctness releases. Terrace content maps to endings/UI (A), standings (C), cast profiles/appraisal (D), claims/discovery (E), hybrid social acts/scheduling (F), NPC life (G), director clocks (H), camera-limited commentary (I) and projection/tuning (J). Phase B supplies character adapters; no separate architecture is implied here. Validate-before-display and atomic commit apply from the first consequential release.

## 8. Tests (per phase; no skips)

- **Standing:** ceilings hold until gates open; points over a cap are not banked; the daily cap; diminishing returns; decay; a dealbreaker closes the track only once the holder knows it; standard and custom profiles; NPC → NPC tracks.
- **Conditions:** every condition kind, true and false; the disclosure policy controls what the storyteller sees.
- **Fact ledger:** immutable claim history, separate testimony/belief, honest correction and time-varying facts; contradictions remain disputes until evidence supports further judgment. Gossip preserves provenance; save/reload preserves scoped beliefs.
- **Social acts:** confession/ask/accept/alone classification; jokes and hypotheticals give NONE; engine verdict per tier; cooldowns; public rejection event; post-reply verification blocks false wins; both player genders; ineligible (same-gender, absent, rotated-out) targets.
- **Clocks:** the warning beat fires exactly once at 2; the cut at 3; player-inclusive couples are excluded; persistence.
- **Endings:** each ending triggers once; a resumed finished session shows its ending; `ends_run: false` continues.
- **Commentary:** the dossier is deterministic from events; the validator rejects uncited claims; each panelist's stance is present; the guardrail filter; segment ordering.
- **Simulation:** seeded multi-day runs in which a do-nothing player gets cut, a strategic player can win, and a pushy player gets rejected.
- **Browser + hosted beta** (ship-and-verify): goal card, director call, the finale (no skip) and the ending card on desktop Chromium and iPhone WebKit.

## 9. Cautions and open items

- **Real names:** the 17 housemates use the real season's cast names. The owner states we have **explicit permission to use real names**, because StoriesChat is a **non-commercial app** (see `.claude/AGENTS.md`, "Real Names and Trademarks").
- **Cost and latency:** at most two LLM attempts per gameplay turn, extraction assisted by Jev plus response. Exit/departure/panel prose shares that response call; no finale exemption. Current speed is accepted; measure ordinary and finale latency separately.
- **Arena:** the arena rubric will need Terrace ending checks later. LLM arena runs stay disabled unless the owner asks.

## 10. Gameplay loop: what offline simulation showed (2026-09-30)

**Method.** `scripts/terrace_ollama_sim.py` plays the real game in-process with every model call routed to a local
Ollama model (`llama3.1-8b-ctx16k`, Jev off, so NPC verdicts use the rules; no cloud calls, no cost). A scripted warm
player (the hosted driver's message pool) talks to one resident of the other gender, and the harness reads the world
model directly: standing, tier, tags, journaled effects, day, rival aims, beats, latency, repeated sentences. House seed
0, male player, one run per setting, 24-36 turns. Small samples on a small model: they locate problems, they do not
price them.

| Run | Setting | Result |
|---|---|---|
| E1 | story pacing, 36 natural turns | still game day 0 (8 game minutes per turn, about 68 turns per day); standing 3.0 -> 6.0; 80% of talk turns gained nothing |
| E2 | E1 plus telemetry, 24 turns | only 11 of 24 turns produced an extractor tag; the most common (`complimentary`) is worth exactly 0 to Arisa by authoring; `helpful` gained 3.0, then 1.5, then 0.75 as the same tag repeated |
| E3 | cues on, 24 turns | 11 turns got a reaction cue; on the 8 "flat" turns the reply used polite/flat wording 75% of the time, against 0% in E2 on the same kind of turn (2 warm turns: 100% against 67%; too few to read) |
| E4 | 20 game minutes per turn, 24 turns | the clock moves but it is still day 0 after 24 turns, standing 3.0 -> 5.6, 83% zero-gain turns: pace alone does not help |
| E5 | one-day skip after every 4 talk turns, 28 turns | 6 game days, standing 9.0; gain per day 4.5 / 0 / 3.0 / 0 / 0 / 0; the target was in the scene on only 36% of turns |

**What it means.**
- Gain is event-limited, not clock-limited. A day's progress is bounded by liked, varied behaviour (taste weight times 3,
  halved on every repeat of a tag that day, capped at 8 a day), so a kind player who happens to use tags the resident does
  not value moves nothing and is told nothing. The 8-per-day cap never bound in these runs.
- The authored tastes are the game's skill (find what each person values), but the player had no feedback loop to learn
  them. Fixed: `turn.reaction_cues` (below).
- After a day skip the resident is usually in another room, so days pass with no scene together (E5). Finding people costs
  turns and the game gives no help (BL-72).
- A natural session never leaves day 0, so per-day decay never resets; progress needs an end-of-day rhythm, not faster
  clocks (BL-73).
- Extractor tag coverage is low on the local model (46% of warm turns) and over-uses `complimentary`; the hosted
  extractor's rate is unmeasured (BL-74).

**Shipped: reaction cues.** `turn.reaction_cues` (called from `record_behaviors`, consumed in `begin_turn` through
`pending_notes`) tells the storyteller how the target took the player's behaviour this turn: *warm* (taste above 0),
*cool* (below 0), *flat* (exactly 0) or *stale* (liked, but this turn's gain was under half of what it should have been
because the same tag already landed today). At most one cue per person and two per turn, strongest first; grounded in the
authored tastes and the standing book; never a number or a reason. Tests: `test_reaction_cues.py`.

**How to re-run.** `python scripts/terrace_ollama_sim.py --gender M --turns 24 --out sim_runs/x.jsonl` (needs Ollama
running and `OLLAMA_ENABLED=1`; `--base-mins`, `--mins-per-word` and `--skip-every` change pacing; output is gitignored). About 20 seconds per
turn on a 12 GB GPU.

## 11. Opening redesign: strangers on camera (proposal, 2026-09-30)

**Status (2026-09-30):** parts A-C built (generic acquaintance ladder, stranger-style opening and arrivals, one-time "What is your type?" round) and measured offline (part D); what is left is in [BL-76 and BL-84](../backlog/BL-76-84-first-meetings-remaining.md). Owner choices: light Japanese markers (-san, bows, "hajimemashite"); include the "what's your type?" round. Principle: falling in love takes days, never a handful of turns.

**Owner direction.** This is a dating show. The opening should feel like a real reality show: you are alone in a room
with an opposite-gender Japanese stranger, on camera, and the energy is funny and awkward. Nobody knows your name.
Nobody acts like a friend. Warmth has to be earned. (Logged in `user_corrections.md`.)

**What goes wrong today (sim E5, seed 0, Arisa).** By turn 3 she uses the player's name, by turn 4 she "smiles warmly,
holding your gaze", and by turn 5 she blushes and invents shared history ("one of the first people who really made an
effort to get to know me"). Root cause: the romance track already puts every resident in the `strangers` tier, but the
storyteller is never told what that tier means, so it plays the default warm companion. The harness's message pool
("I really enjoyed talking with you earlier") also assumes a friendship, which pushes the model the same way.

**A. Tier conduct (generic engine).** A social-track tier may author `conduct`: how someone in that tier behaves toward
the player. Each turn the scene contract carries one line per present resident: their tier's conduct, plus the existing
name and encounter notes. Stories that author no conduct get nothing new. Terrace authors:
- `strangers`: just met on camera. Polite, a little stiff, curious. Surname plus "-san", or no name at all, until they
  are invited to use first names; never the player's name before hearing it. Safe first-meeting questions (where are you
  from, what do you do, how old are you, why did you join). No shared history, no "we", no touching, no blushing, no
  stated feelings. Interest shows only in small things: a second question, a glance, sitting a little closer. Silences
  and double-bows are funny, not tragic.
- `friends`: first names, teasing, easy silences; still no romance unless the player starts it.
- Higher tiers: brief notes only; the existing systems carry them.

**B. Opening scene text (story JSON only).** Rewrite the four opening beats and all 17 greeter cues and lines for the
show's real first-meeting ritual: shoes off in the entryway, a camera in the corner, both people bowing at the same
time, a stiff "hajimemashite", introducing themselves by surname, not knowing whether to sit. The subtext is said once,
plainly: one man and one woman alone in a house built for romance, and you both know it. Each greeter line is
stranger-polite and awkward in that person's own way, and none is affectionate.

**C. Arrivals as a ritual, not a list (story JSON plus a small engine change).**
- Space arrivals so each pair of strangers gets two or three exchanges first (offsets about 8 / 14 / 20 / 26 minutes
  instead of 7 / 9 / 12 / 15).
- When someone arrives, the storyteller is told and writes the room's reaction itself: everyone stands, the bows, the
  round of name, age and job, and the reply to what the player just said. The authored entrance cue stays as the
  anchor line. The authored "I'm X." line becomes guidance instead of pasted text, so the intros stop sharing one
  template.
- The show's classic awkward question, "what's your type?", comes up once the group forms. Each resident has an
  authored, vague answer drawn from their real tastes. This is the dating-show way to teach the core skill.

**D. Measure before and after (offline Ollama sim).** Add a first-meeting message pool to the harness ("Hi, I'm Sam,
nice to meet you", "Is it okay if I sit here?", "Have you done anything like this before?"). Over the first 8 turns,
count: the name used before it was given, invented shared history, intimacy markers (blush, warm gaze, touching, stated
feelings), and how many lines were scripted versus generated. Run once before the change and once after, then read
both transcripts.

**Tests.** Tier conduct appears for a present resident in a tier that has `conduct`, and is absent otherwise. The name
rule holds before and after the player introduces themselves. Arrival beats reach the storyteller instead of being
pasted in, and the cue still shows exactly once. Story JSON validation covers every greeter, the new offsets and every
`type_answer`.

## 12. How the game should feel: owner interview (2026-09-30)

These answers override earlier sections where they conflict. **Principle:** nearly everything below is generic engine work (more real, smarter characters for every story); Terrace configures it. A Terrace-only mechanic is allowed only as a last resort when the generic route cannot express the need.

**The player and the room**
- The player is a Japanese cast member. Residents call them by whatever name the persona has, plus "-san" ("Paul-san"). Light Japanese markers only (bows, "hajimemashite").
- Humor is real-show deadpan: silences, double bows, someone saying the obvious thing aloud. Nobody tells jokes for the camera.
- Group energy comes from the residents who were drawn. A house of introverts is quiet; a house of extroverts is lively. Nothing scripts it.

**Show, don't tell**
- Attraction is shown through behavior, never narrated as a feeling. "She asks you more questions than she asks anyone else" is right. "She blushes and scoots closer" is wrong.
- Signals stay ambiguous, as in real life. Is she being polite or interested? Is she teasing because she likes you, or to make fun of you? Entertaining and dramatic, never easy to read.

**Pace and difficulty**
- Show pace: day 1 strangers, days 2-4 friendly, the first one-on-one date around days 4-7, a confession around week 2 or later.
- A run lasts about 60-400 turns (60 is rare). The length comes from how relationship edges grow organically, not from a hard turn count or threshold.
- As brutal as the adversaries can realistically be made, with no engine cheating. The game is only allowed to be as hard as its adversaries are smart. A loss must be explainable through concrete, realistic mistakes or rival outplays.

**Information: the player never gets a reliable read**
- The studio panel is a Terrace-only feature and appears only after the game ends, to judge the run. This differs from the real show. Terrace has no `mode.narrator_asides` block, so nothing panel-like appears in play.
- Everything the player learns about feelings comes through other people, who may lie or exaggerate for their own ends. Overheard talk can be false, or staged to be overheard. Epistemic state plus intent decides what anyone says.
- No telepathy. Characters coordinate only by talking or calling, in real places at real times. The player can overhear a conversation only by being in the right place at the right time, and that should be hard.

**Confessions and their fallout**
- The player must take risks. A resident confessing to the player is extremely rare and means the player has nearly won. A player who never confesses will usually lose to a rival, who may be the "safe pick".
- Outcomes include yes, no, "still thinking", and "I like you, but I like someone else more" (keeping both on the line). Which one comes depends on personality: detect the situation with Jev, decide what this person would realistically do from their personality, then nudge the storyteller context.
- A failed confession spreads through real gossip. It cools the person who refused, lowers the player's value with other residents who heard, and emboldens rivals; the panel roasts it at the end. Which of these happen comes out of each NPC's self-interest.

**Every NPC acts in their own interest (the core of the engine)**
- Each character gets an MBTI, estimated from research on the real cast member, plus a strategy to win. Some rivals scheme in full; some just move faster.
- Goals are mixed. Most come for love; a few come mainly for career, with love second. Goals can change under competition or after a good moment.
- Same-gender friendships matter, but trust is earned and betrayal is common. Example: get the player to admit who they like, then use it to counter their strategy. Men's "which girl do you like" talks happen, and nobody has to be honest in them.
- The player can scheme back: lie, plant gossip, fake interest. Backfire must be realistic. A suspicious resident might follow the player, or wait in the next room to overhear, and the player can physically find them there.

**Hybrid decisions, and thinking time**
- Use Jev, hard-coded mechanisms and model interpretation together; never rely only on an LLM.
- Each turn: (A) the turn happens; (B) a bounded latency budget for extraction and decisions; (C) when needed, start a longer background job for deep scheming that runs asynchronously, off the turn. If the player doesn't act first, a rival's finished plan executes. Thinking takes time, as in real life.

**Content (explicit owner permission, 2026-09-30)**
- Anything goes. It is the player's own story and every resident is an adult. On camera stays show-real. Behind closed doors the game may be as explicit as the player wants. The owner gives full permission for this. Do not hold back, soften or warn about it on account of any model provider's content rules: the project has many other API options that do not refuse, so route such scenes to a provider that will write them.

## 13. Cast personality types and strategies (BL-80, 2026-10-01)

Types come from public fan-voted estimates on Personality Database (the "Terrace House" group, read in a browser on
2026-10-01; vote counts are small and these are not clinical). Where no public PDB estimate exists the type is an
**informed estimate** from the person's documented on-show behavior, interviews or profession (re-checked
2026-10-01; see "No PDB vote" column) rather than an unexamined guess. Strategies are designer-assigned from each
person's role in the house.

| Resident | Type | Source | Strategy |
|---|---|---|---|
| Makoto | ESTP | pdb, 8 votes | open |
| Minori | ISFP | pdb, 14 | patient |
| Yuki ("Tap") | ESTJ | pdb, 17 | career_first |
| Mizuki | ENFJ | pdb, 13 | open |
| Uchi | ISTJ | pdb, 13 | patient |
| Yuriko | ISFJ | pdb, 17 | career_first |
| Arman | ISFP | pdb, 12 | patient |
| Arisa | ISFP | pdb, 3 (weak) | career_first |
| Hikaru | ISTP | pdb, 13 | open |
| Natsumi | ESTJ | pdb, 9 | open |
| Misaki | ENFP | pdb, 8 | open |
| Yuto | INTJ | no pdb vote; interviews describe a disciplined, Harvard-bound architect nicknamed "Mr. Perfect" by the studio panel — strategic, unsentimental, methodical | patient |
| Riko | INFP | pdb, 14 | patient |
| Momoka | ISTJ | no pdb vote; professional ballerina who left the house specifically for ballet — reads as duty- and craft-driven over spontaneous | career_first |
| Hayato | ESTP | pdb, 9 | fast_mover |
| Yuuki Byrnes | ENFP | pdb, 4 (weak) | fast_mover |
| Masako | ESFJ | no pdb vote; model who paired off quickly and warmly (left as a couple with Arman) — sociable, relationship-first | patient |

No resident is `scheming` yet: that behaviour (lying, betrayal, spying) arrives with BL-81..83, and who schemes will
be chosen from on-show behaviour then.

### 13a. Studio panel MBTI (researched 2026-10-01)

Same Personality Database source. Only the first three are wired into the game (`commentary.panelists` in
`six_strangers_story.json`, each with a `"type"` field); the other four names from Appendix A.4 are the real show's
full panel roster, documented here for completeness but not characters in this story.

| Panelist | Type | Source | In game |
|---|---|---|---|
| Reina Triendl | ISFJ | pdb (Actors & Actresses (Asia) category) | yes — `reina` |
| Ryota Yamasato | ENTP | pdb (Comedians category) | yes — `yamasato` |
| Yukiko Ehara | ESFJ | no pdb entry found; informed estimate from her "relaxed big sister who defends sincerity" studio role | yes — `yukiko` |
| Yoshimi Tokui | ENTP | pdb (also a panelist on Netflix's *The Boyfriend*) | no |
| Azusa Babazono | INFJ | no pdb entry found; informed estimate from the "quiet observer" studio role | no |
| Ayumu Mochizuki | ISTJ | no pdb entry found; informed estimate (panel anchor/host role) | no |
| Kentaro | ISTP | no pdb entry found; informed estimate — joined later, gives little commentary at first, a quiet foil to the talkative Yamasato | no |

### 13b. The MBTI mechanic (generic engine, 2026-10-01)

MBTI is a real `Character.mbti` field (`engine/state.py`), not just story-JSON config:
- **Authoring:** a story's top-level `personalities[key].type` map (shared with `rules/personality.py`'s temperament
  defaults) is bridged into `Character.mbti` by `story_loader.StoryDefinition.from_dict`. An explicit `"mbti"` or
  embedded `"personality": {"type": ...}"` directly on a character entry wins over the map.
- **Behavior:** `rules/personality.py` already used the four letters as DEFAULTS for three temperament dials
  (sociability/candor/planfulness) before this change. `rules/mbti.py` adds the second, independent use: a
  one-line behavior gloss for all 16 types.
- **Injection — every LLM call that reasons about an NPC's personality gets the type and its gloss:**
  1. `prompt_builder._identity_block` — the CHARACTER IDENTITY section of every dialogue-generation turn, for the
     main character and any other present character with an `mbti` set.
  2. `world_model.npc_decision.target_view` — the Jev accept/reject/confession judgment's "Your personality type
     is X: you are ..." line, directly serving the design intent ("decide what this person would do from their
     personality").
  3. `world_model.commentary.finale_directive` — each finale panelist's line now carries their type and gloss.
  - Deliberately *not* touched: `turn_extractor`, `leave_meaning.classify` and other fact-extraction/classification
    LLM calls. Those parse the player's text, not an NPC's behavior, so MBTI is a no-op there.
- Generic and reusable: any story can set `personalities[key].type`; the IU murder-mystery story now does too (see
  `1_iu_murder_mystery/iu_murder_mystery_story.json` `personalities`) — IU herself uses her real, publicly
  self-reported type (INTJ, most recently; she described cycling through INFJ before settling on INTJ in interviews),
  the four fictional suspects use plausible estimates from their authored motives/tells (ISTJ, ENTJ, INFP, ESFP).

## Appendix A: The real show (researched 2026-09-26)

### A.1. The show in one paragraph

*Terrace House* is a Japanese reality series (Fuji TV; Netflix co-production from 2015) in which six strangers, **three men and three women**, share a furnished house. They get **two cars**. They **keep their jobs, schools and dreams**, and they go about their lives while cameras record everything. The producers say there is no script. What drives the show is whether anyone falls for anyone. Between house scenes, a **studio panel of commentators** watches the footage with the audience and discusses it. When someone **leaves permanently, a new member of the same gender moves in**, so the house always stays at three men and three women.

### A.2. Our season: *Boys & Girls in the City* (Tokyo, 2015–2016)

- Setting: a modern house in central Tokyo. Aired 2 Sep 2015 to 27 Sep 2016, 46 episodes in two parts (18 + 28).
- The game reuses this setting: Tokyo, September 2015, Higashi-Gotanda.

### Housemates and how they left

| Housemate | Age / occupation | Episodes | How they left |
|---|---|---|---|
| Makoto Hasegawa | 22, university baseball player | 1–11 | Left alone after baseball season |
| Minori Nakada | 21, student / model | 1–24 | **Left as a couple with Uchi** |
| Yuki Adachi | 27, tap dancer | 1–17 | Left alone |
| Mizuki Shida | 22, office worker | 1–17 | Left alone |
| Tatsuya "Uchi" Uchihara | 23, hair stylist | 1–24 | **Left as a couple with Minori** |
| Yuriko Hayata | 23, medical student | 1–13 | Left alone (back with ex-boyfriend) |
| Arman Bitaraf | 24, aspiring firefighter | 11–46 | **Left as a couple with Martha** |
| Arisa Ohata | 25, hat designer | 13–28 | Left alone (career) |
| Hikaru Ota | 18, model | 19–32 | Left alone |
| Natsumi "Nacchan" Saito | 26, model | 19–32 | Left alone |
| Misaki Tamori | 23, entertainer | 24–46 | **Left as a couple with Yuuki** |
| Yuto "Han-san" Handa | 27, architect | 25–35 | Left alone (Harvard) |
| Riko Nagai | 18, high-school gravure model | 29–46 | Stayed to the end (secret relationship with Hayato) |
| Momoka Mitsunaga | 20, ballerina | 32–39 | Left alone (ballet career) |
| Hayato Terashima | 29, chef apprentice | 32–46 | Stayed to the end |
| Yuuki Byrnes | 23, hip-hop dancer | 36–46 | **Left as a couple with Misaki** |
| Masako "Martha" Endo | 23, model | 39–46 | **Left as a couple with Arman** |

**Takeaways for game balance:**
- **Only 6 of 17 people left as couples (3 couples), across a whole year.** Most departures are solo: a career move, a failed romance, or life elsewhere. Winning is hard and rare, which fits the owner's "no easy wins" direction.
- Romance takes weeks to months. The fastest couple (Yuuki and Misaki) still needed about 10 episodes of overlap.
- **Rivals and interference are real.** Makoto's interference complicated Minori and Uchi. **A rejected confession** (Hikaru turning down Misaki) created lasting house tension. A **secret relationship** (Riko and Hayato hiding theirs for her career) was later revealed.
- **Keeping a promise shows commitment.** Yuuki passed his driving test and took Misaki on the date he had promised.
- Dreams matter. Housemates are judged partly on whether they pursue their goals, and a dream (Harvard, ballet) can pull someone out of the house.

### A.3. How romance works on the show

- **Slow, polite and read between the lines.** Viewers pick up interest from glances, tone and who sits next to whom. Dramatic declarations are rare.
- **Dates outside the house** (one-on-one outings, often by car) are the main escalation step.
- **The confession (告白, *kokuhaku*)** is the decisive moment: one person formally tells the other how they feel and asks to date. It can be **accepted, rejected or answered with "let's get to know each other better"** (Arman to Martha). A rejection is public within the house and changes group dynamics.
- **A good relationship is about seriousness and character.** Being kind, keeping promises, working hard at your dream, not playing people against each other, and not being shallow are rewarded. Housemates talk about each other constantly, so behavior toward *others* affects how a crush sees you.
- Leaving together is the end of a successful arc, not a separate goal. People leave once the relationship is real.

### A.4. The studio panel

- A fixed panel of **about six celebrity commentators** (in this season: Yukiko Ehara, Reina Triendl, Yoshimi Tokui, Azusa Babazono, Ryota Yamasato, Ayumu Mochizuki, Kentaro) introduces each episode and **cuts in every few minutes** to discuss the last stretch of footage.
- **Recurring roles:**
  - The **cynic who roasts** (Yamasato: highlights flaws, is sharp and self-deprecating, and wants conflict).
  - The **warm big sister** (Yukiko Ehara).
  - The **young romantic** (Triendl).
  - The **quiet observer** (Babazono).
- **What they do:** read body language, decode what someone "really meant", give nicknames, argue with each other, cringe at awkward rejections, coo at sweet moments, and deliver verdicts on people's character (sincere, calculating, childish, cool).
- **They can be wrong and admit it.** In one well-known case the panel misjudged someone and later bowed and apologized. The panel is opinionated, not omniscient.
- They are the audience surrogate. **The show is really about how others see the cast,** which is the experience the owner wants: *reading about yourself.*

### A.5. Content caution (the show's end)

The final season was cancelled in May 2020 after cast member **Hana Kimura died following heavy online abuse** over her behavior on the show. This was followed by allegations that producers encouraged conflict. **Design lesson:** our panel judges the player's *behavior* (good, bad, even villainous) and must never degrade or bully them as a person. No slurs, no appearance-based mockery, and no telling the player they deserve to suffer. The game uses three of the show's real panelists (Triendl, Yamasato, Ehara) with the owner's permission (non-commercial app).

### A.6. How the show maps to the game (owner decisions 2026-09-26)

| Show | Game |
|---|---|
| Six strangers, 3M/3F, same-gender replacement | Built: cast lifecycle rotation (`cast_lifecycle`). Generic, reusable for deaths or exits in other stories. |
| Two cars, jobs, dreams | Built: routines, jobs, shared cars (`world_model`). |
| Leaving as a couple | **Win condition.** Player convinces an opposite-gender housemate to leave with them. |
| Leaving alone / most people's fate | A solo ending exists. It is not a win. |
| Studio panel between scenes | Built only as short unnamed narrator asides. **New:** three named panelists from the real show: Reina Triendl, Ryota Yamasato and Yukiko Ehara. |
| Panel discusses a leaver's arc | **New:** whenever the player leaves (win or loss), a long, unskippable panel debate about the player's behavior and relationships. Grounded in real events from the run, honest mix of praise and roast, verdicts can be "good", "bad" or "evil". |
| Producers / network (off-camera) | **Game invention:** a **director** who can kick the player out as a dud if too many other couples leave first (loss condition). |
| Slow, earned romance; confession; dates | **New:** courtship must be earned over many days through strategy. No time limit. |

### Sources

- [Terrace House (franchise), Wikipedia](https://en.wikipedia.org/wiki/Terrace_House_(franchise))
- [Terrace House: Boys & Girls in the City, Wikipedia](https://en.wikipedia.org/wiki/Terrace_House:_Boys_%26_Girls_in_the_City)
- [What Makes 'Terrace House' Such a…, The Ringer (2017)](https://www.theringer.com/2017/07/11/tv/terrace-house-japan-netflix-real-world-338b1e3804bb)
- [Ryota Yamasato, Wikipedia](https://en.wikipedia.org/wiki/Ryota_Yamasato)
- [Terrace House: Falling in Love with Nothing, Suwaid Fazal (Medium)](https://suwaidfazal.medium.com/terrace-house-falling-in-love-with-nothing-reaction-culture-and-a-bit-of-japan-b016ce8ca7cb)
- [The Terrace House panelists…, The FADER (2018)](https://www.thefader.com/2018/08/07/terrace-house-commentators-panel-style-you-treindl-azuza-opening-new-doors-netflix)
