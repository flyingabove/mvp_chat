# Game Mode: Terrace House

> **What this doc is for:** the single design doc for the Terrace House game mode (story `7_six_strangers`, "Terrace in the City"): its proposal (win, loss, courtship, judges panel), the generic engine mechanics it drives, and background on the real show (Appendix A). Edit it if anything about this game mode's design changes. Once parts ship, move the as-built description of the generic mechanics into `reference/` docs and mark them built here.

- **Status:** proposal, not built. Game-mode doc, moved here from `proposals/`. Created 2026-09-26, rewritten the same day after the owner Q&A (decisions in §2).
- **Closes when shipped:** [BL-33](../backlog/terrace-goal-ending-and-rivals.md); most of [BL-34](../backlog/terrace-goal-ending-and-rivals.md).
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
| Panel on other exits | A **short segment** when NPCs leave (as a couple or alone). The **full debate** on any player exit: win, cut or leaving alone. |
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
| Engineering rule | **Build universal mechanics** that every story can use. Terrace only configures them in story JSON. Dating stories can weight the LLM context toward relationships (adjustable per story). |

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
  {"id": "left_alone",    "kind": "neutral", "when": "act LEAVE_ALONE confirmed",          "epilogue": "panel_finale", "ends_run": true},
  {"id": "cut_by_director","kind": "loss", "when": "clock director_patience",             "exit_scene": "...", "epilogue": "panel_finale", "ends_run": true}
]
```

`ends_run: false` supports NorthStar's "the world continues" for other stories.

**The commentary panel** is a story-declared cast of **commentators** outside the world (Terrace uses real panelists from the show; other stories may use their own). They can't be heard by residents and never reveal private thoughts that the footage wouldn't show. Three modes:

| Mode | When | Length |
|---|---|---|
| `aside` | between scene beats (existing narrator asides, now voiced by the named panelists) | 1–3 lines |
| `departure_segment` | an NPC or NPC couple leaves | ~300 words |
| `finale` | the player leaves (win, cut or alone) | ~2,000 words, no skip |

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
- **Opening arrival sequence (built 2026-09-29):** The five NPC slots and player slot are reserved immediately at a strict three-men/three-women capacity. The player enters second at 3 pm; one random opposite-gender resident is already in the living room. Four selected residents are initially unplaced and hidden from public cast views and speaker catalogs. Their randomized entrance order fires at minutes 7, 9, 12 and 15, one per ordinary conversation turn; an explicit wait can pass several entrances. Each entrance uses a character-specific authored cue, updates physical presence and first-meeting state, and persists across saves. The first resident has an authored, personality-specific opening action and line. Nobody begins eating during introductions; after all six are present, residents may choose to order food or prepare it together. The generic `opening.arrival_sequence` configuration and engine behavior can be reused by another story.
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
| `mode.narrator_asides` (unnamed) | Voiced by the named panel (M6 `aside`). |
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

- **Real names:** the 17 housemates use the real season's cast names. The owner states we have **explicit permission to use real names**, because StoriesChat is a **non-commercial app** (see `.claude/CLAUDE.md`, "Real Names and Trademarks").
- **Cost and latency:** at most two LLM attempts per gameplay turn, extraction assisted by Jev plus response. Exit/departure/panel prose shares that response call; no finale exemption. Current speed is accepted; measure ordinary and finale latency separately.
- **Arena:** the arena rubric will need Terrace ending checks later. LLM arena runs stay disabled unless the owner asks.

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
