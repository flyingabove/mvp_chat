# Game Mode: Terrace House

> **What this doc is for:** the single design doc for the Terrace House game mode (story `7_six_strangers`, "Terrace in the City"): its proposal (win, loss, courtship, judges panel), the generic engine mechanics it drives, and background on the real show (Appendix A). Edit it if anything about this game mode's design changes. Once parts ship, move the as-built description of the generic mechanics into `reference/` docs and mark them built here.

- **Status:** proposal, not built. Game-mode doc, moved here from `proposals/`. Created 2026-09-26, rewritten the same day after the owner Q&A (decisions in §2).
- **Closes when shipped:** [BL-33](../backlog/BL-33-terrace-relationship-goal-and-ending.md); most of [BL-34](../backlog/BL-34-terrace-rivals-with-independent-aims.md).
- **Background:** Appendix A (the real show and how it maps to the game).
- **Related:** [SOCIAL_ENGINE_V2_DESIGN.md](../reference/SOCIAL_ENGINE_V2_DESIGN.md), [CAST_LIFECYCLE_DESIGN.md](../reference/CAST_LIFECYCLE_DESIGN.md), [JEV_DYNAMIC_CONTEXT_DESIGN.md](../reference/JEV_DYNAMIC_CONTEXT_DESIGN.md), [GAME_DESIGN_SYSTEMS.md](../proposals/GAME_DESIGN_SYSTEMS.md).

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
| Player facts | A fact about the player becomes true **the first time the player states it in chat**, then it's locked. The player **may lie**. Lies are recorded and can be exposed. |
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
- **Dealbreakers** are conditions that, once true and *known to the holder*, set the track to `closed`. A closed track never rises again. A dealbreaker can be true from the start (a player fact that rules you out), so the romance is closed the moment the NPC learns it.
- The score is fed by what the engine already extracts each turn (relationship deltas, behavior tags, agreements kept or broken), multiplied by the holder's **preferences**: authored `likes`/`dislikes` over a shared behavior-tag vocabulary. A player who flatters someone who hates flattery loses points while thinking they're gaining.
- **Pure, deterministic, unit-testable:** `standing.apply(track, deltas, day) -> track`, `standing.evaluate_gates(track, facts) -> open/closed`.

Terrace `romance` defaults (standard personality):

| Tier | Range | Feels like | Gate to leave the tier |
|---|---|---|---|
| Strangers | 0–25 | polite | ≥2 days known |
| Friends | 25–45 | jokes, small favors | ≥1 real one-on-one conversation in private |
| Interested | 45–60 | seeks you out, jealousy | ≥2 **dates outside the house** (completed agreements) |
| **Confession** | cap 60 | — | an **accepted confession** (M4) |
| Dating | 60–75 | a couple in front of the house | ≥3 days dating, no unresolved conflict, no known two-timing |
| **Ready to leave** | ≥70 | — | the departure ask (M4) |

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

Condition kinds are a **closed vocabulary**, so the checks are code, not LLM judgment:

| Kind | Checks |
|---|---|
| `player_fact` | the fact ledger (M2) |
| `event` | `world_model` events and agreements (gifts, dates, promises kept) |
| `relationship` | trust/suspicion/etc. on the graph edge |
| `knowledge` | the player (or holder) knows a given fact |
| `time` | days known, days dating |
| `absence` | "no known two-timing", "no exposed lie" |
| `track` | another track's value, e.g. the holder's romance toward a rival |

**Reuse in other stories:** in the murder mystery, a suspect's `candor` is capped at 40 until the player presents a specific clue (a `knowledge` gate), and a confession requires `candor` ≥ 90. The mastermind win can later move from regex to standing, the same way Terrace moves now.

### M2. Player fact ledger (claims, locks, lies)

- A new extractor decision identifies **self-claims** in the player's message: height, job, age, family, hometown, relationship history, hobbies. The keys are declared by the story (`player_fact_keys`).
- The **first claim locks** the fact. It's stored with who heard it (the listeners of that utterance).
- A **later contradicting claim** is recorded as an **exposed lie** to everyone who heard both claims. Otherwise it's an inconsistency waiting to be found. It becomes a public `lie_exposed` event that gossip can spread.
- The engine doesn't know the "real" truth. The ledger treats the player's first word as the truth, and inconsistency is the lie. This keeps it deterministic and fair. The player can lie *consistently*. The risk is holders with a `verify` behavior (a skeptic asks follow-up questions, a doctor friend quizzes you) and other people who heard a different claim.
- **Reuse:** any story where the player creates their own persona (an alias in a heist, a cover story in a spy game).

### M3. Secret rules and discovery (on existing epistemics)

- Each condition has a `disclosure` policy (`never`, `gossip`, `trust_N`, `best_friend_only`, `hint_on_<event>`). Conditions become facts in the **existing** knowledge system (`known_by`, gossip provenance, off-screen spread). No parallel store.
- The storyteller only sees a condition when the player is allowed to learn it. Otherwise it gets a behavioral instruction ("{NPC} cools noticeably when height comes up, but deflects if asked why"), so the player picks up **hints before rules**.
- **Rivals discover rules too**, through their own off-screen conversations (the existing gossip and off-screen resolver). A rival who learns "flowers on a date" first can act on it first. That's the "figure it out before others do" race.
- **Reuse:** hidden motives in a mystery, faction preferences in an adventure.

### M4. Social acts: confession and the departure ask

- One extractor decision, registered in the **existing pre-generation batch** (no extra LLM call), classifies the player's message into `NONE | CONFESS:<id> | ASK_LEAVE:<id> | ACCEPT_OFFER:<id> | LEAVE_ALONE`. The acts come from story config, so other stories can declare their own (e.g. `ACCUSE:<id>` in a mystery).
- **The engine decides the answer from the track, not the storyteller:** `ACCEPT`, `NOT_YET(reason)` or `REJECT(reason)`. A reason is a failed gate phrased *in character and non-revealing* ("we've never really been out, just us"). A failing personal condition only gets revealed as far as its `disclosure` allows.
- **A confession is a public risk:** a rejection becomes a house-visible event. It lowers the track, adds a cooldown, gives rivals an opening, and changes the house mood (as with Hikaru and Misaki on the show).
- The storyteller receives a one-turn directive to narrate the decided answer clearly. On an ACCEPT turn, a small post-reply check confirms the prose really shows the acceptance before any state commits (no false wins).
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
1. **Run dossier (deterministic):** built from `world_model` events. It contains every relationship arc with the tier timeline, confessions (accepted and rejected), dates, gifts, promises kept and broken, lies told and exposed, two-timing, conflicts and repairs, rivals beaten or lost to, and the conditions the player figured out (and the ones they never did). It also includes computed **conduct tags** (kind, strategic, manipulative, loyal, two-faced, cruel…) with evidence event ids.
2. **Outline call:** the panel agrees on 5–7 segments (first impressions, turning points, the worst move, the best move, the romance, a verdict debate). Each panelist gets an assigned stance so they **disagree**.
3. **Segment calls:** write each segment as structured dialogue (`speaker_id` = panelist), citing only dossier events. A validator rejects claims with no event id.
4. **Verdict:** each panelist ends with a one-line label, which may be good, bad or evil, plus a prediction ("they'll last" / "six months, tops").
5. **Delivery:** through the existing per-speaker dialogue renderer (`frontend/dialogue.js`) with panelist portraits, tap to advance, **no skip button**, then the ending card.
- **Guardrail:** judge the player's **behavior**, never their worth. No slurs, no mocking appearance or identity, no piling on. The panel can call a move evil; it never says the player deserves harm. This is the lesson from the show's cancellation (see Appendix A.5).
- **Reuse:** the mystery's "press conference after the arrest", a courtroom epilogue, a sports broadcast.

### M7. Context focus profile (adjustable LLM context)

- `mode.context_focus` weights the existing Jev context-selection budget by category, e.g. Terrace `{"relationships": 0.5, "people_history": 0.3, "places": 0.1, "clues": 0.1}` versus the mystery `{"clues": 0.4, "places": 0.3, ...}`.
- Relationship-heavy stories get more of each prompt spent on who likes whom, recent conflicts, gossip and shared history, and less on room descriptions. It's one tunable number per category, in data.

## 4. Terrace configuration (story JSON only)

- **Roster:** random 5 of 17 from the pool (`randomize_initial_roster` already exists) plus random arrival order in the same-gender replacement queues. Every run is a different house.
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

New modules (proposed): `engine/standing/` (tracks, tiers, gates, conditions), `engine/player_facts.py`, `engine/social_acts.py`, `engine/story_clocks.py`, `engine/endings.py`, `engine/commentary/` (dossier, outline, segments, validator).

## 7. Build order (each phase ships and is verified on beta)

1. **Endings registry + ending payload + ending overlay + goal card.** It runs on today's romance state, and the player sees the goal and a real ending immediately. *(Generic.)*
2. **Standing tracks M1:** tiers, gates, preferences, daily caps and dealbreakers, fed by the existing extractor deltas. Author standard profiles for all 17. *(Generic.)*
3. **Social acts M4:** confession and ask/accept/leave-alone, engine-decided answers, post-reply verification. Deletes the regex adapters.
4. **Player fact ledger M2 + discovery M3:** custom conditions for about half the cast, gossip-spread rules, lie exposure.
5. **NPC–NPC courtship and couple departures + story clocks M5:** the director call and the cut.
6. **Commentary M6:** named asides, the departure segment, then the finale pipeline (dossier, outline, segments, validator, dialogue UI with no skip).
7. **Context focus M7** and tuning from hosted playtests: how many days a skilled player needs, how often NPC couples leave, and whether the cut is fair.

## 8. Tests (per phase; no skips)

- **Standing:** ceilings hold until gates open; points over a cap are not banked; the daily cap; diminishing returns; decay; a dealbreaker closes the track only once the holder knows it; standard and custom profiles; NPC → NPC tracks.
- **Conditions:** every condition kind, true and false; the disclosure policy controls what the storyteller sees.
- **Fact ledger:** first claim locks; a contradiction heard by the same listener becomes exposed; one heard by different listeners stays latent until gossip connects the two claims; save/reload.
- **Social acts:** confession/ask/accept/alone classification; jokes and hypotheticals give NONE; engine verdict per tier; cooldowns; public rejection event; post-reply verification blocks false wins; both player genders; ineligible (same-gender, absent, rotated-out) targets.
- **Clocks:** the warning beat fires exactly once at 2; the cut at 3; player-inclusive couples are excluded; persistence.
- **Endings:** each ending triggers once; a resumed finished session shows its ending; `ends_run: false` continues.
- **Commentary:** the dossier is deterministic from events; the validator rejects uncited claims; each panelist's stance is present; the guardrail filter; segment ordering.
- **Simulation:** seeded multi-day runs in which a do-nothing player gets cut, a strategic player can win, and a pushy player gets rejected.
- **Browser + hosted beta** (ship-and-verify): goal card, director call, the finale (no skip) and the ending card on desktop Chromium and iPhone WebKit.

## 9. Cautions and open items

- **Real names:** the 17 housemates use the real season's cast names. The owner states we have **explicit permission to use real names**, because StoriesChat is a **non-commercial app** (see `.claude/CLAUDE.md`, "Real Names and Trademarks").
- **Cost and latency:** the finale takes roughly 5–8 LLM calls, run once per game. The departure segment is 1 call. The acts decision rides the existing extractor batch.
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
