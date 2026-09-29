# BL-39 — Engineering plan: character-centric social engine (earned romance, endings, panel)

- **Type:** feature (engineering plan)
- **Found:** 2026-09-27, owner request after the Terrace game-mode design ([TERRACE_HOUSE.md](../game_modes/TERRACE_HOUSE.md))
- **Severity:** high. This is the implementation path for BL-33 and BL-34, and part of BL-35 and BL-38. Terrace has no earnable win or loss until it lands.
- **Status (2026-09-28):** conflicts with [BL-38](BL-38-social-engine-authority-and-epistemic-transactions.md) on relationship ownership, standing arithmetic, turn boundary, panel call count and NPC decision model. See the [conflict table](../research/ENGINE_PLAN_ROUND_TWO_REVIEW_2026_09_28.md#conflicts-requiring-reconciliation). The owner is writing one consolidated plan; do not implement shared Character/relationship state from this doc alone.

## Problem

The Terrace design (standing tracks with gated ceilings, personal requirements, a player fact ledger, confessions/asks, story clocks, endings, the judges panel) needs characters that **perceive, judge, remember, want and decide**. Today, one person's inner life is scattered across unrelated stores, keyed by id strings. Nothing owns it:

| What a person "is" | Where it lives today |
|---|---|
| Authored identity, voice, goal, tells | `engine/state.py::Character` (in `GameState.characters`) |
| Body, routine, mood, aim | `world_model/character.py::CharacterState` (in `WorldModel.characters`) |
| Feelings toward others | `character_graph.py::RelationshipEdge.state`, in `GameState.character_graph`, looked up by `(from_id, to_id)` string key |
| Memories | `world_model/memory.py::MemoryStore`, a flat list filtered by `owner` |
| Beliefs and claims | `world_model/epistemics.py::EpistemicLedger`, flat lists filtered by `owner` |
| Plans and promises | `world_model/agreements.py::AgreementBook` |
| Romance decisions | six loose `romance_*` string fields on `WorldModel` plus regex in `world_model/romance.py` |
| NPC initiative | the free function `intentions.py::propose_rival_invitations` with hard-coded thresholds |
| Off-screen life | `offscreen.py::outcome_weights`, flat `BASE_WEIGHTS` tuned by pair averages, not by who these people are |

Consequences: an NPC can't "react" to something they saw, because no object receives the event and judges it by its own tastes. Adding requirements, standing or loyalty tests as more free functions would add more loose tables. The owner's direction (2026-09-27): **make the Character object the focus.** Characters should react like real people, the state should make sense, and every mechanic should be reusable across game modes.

## Fix direction

### 1. Design principles

1. **A Character is an object with an inner life, not a row.** Everything *about one person's point of view* is a component of that character: tastes, standards, feelings toward each person, claims about themselves, and intentions. Code asks the character (`minori.opinion_of(player)`, `minori.respond(act)`), never a table.
2. **Shared things stay shared, and only genuinely shared things.** World truth (the event log and places), the transmission chain of claims (`EpistemicLedger`), and two-party contracts (`AgreementBook`) belong to no single person. Characters reach them through **views scoped to themselves** (`character.memories`, `character.beliefs`, `character.commitments`), so callers never filter by `owner` strings.
3. **Perceive → appraise → feel → want → act.** This is the one loop that makes NPCs human. Every consequential thing that happens is a world `Event`. Each character who *perceives* it (witnessed, overheard, told) *appraises* it with their own personality. That produces **impressions** (attributed feeling changes) and **reactions** (new intentions). Nothing changes feelings without an event cause.
4. **Characters judge from what they believe, not from truth.** Requirement checks read the character's *beliefs* about the other person. A lie that is believed passes, and it fails the moment it's exposed. This makes lying, gossip and discovery work with no special cases.
5. **Characters never call an LLM** (constraint from [CHARACTER_WORLD_MODEL_REDESIGN.md](../reference/CHARACTER_WORLD_MODEL_REDESIGN.md) §2.5). They are data plus deterministic, seeded methods. LLMs only *classify* input (extractor decisions) and *render* prose (storyteller, panel) from what characters decided.
6. **Generic engine, story data.** Nothing says "Terrace", "romance" or "height" in engine code. Tracks, tiers, requirements, conditions, endings, clocks and commentators are all declared in story JSON. The murder mystery uses the same classes: a suspect's `candor` track, gated by evidence shown, and a confession ending.
7. **No arbitrary scores** (from [SOCIAL_ENGINE_V2_DESIGN.md](../reference/SOCIAL_ENGINE_V2_DESIGN.md) §3). A standing value is the capped sum of **impressions**, each with a cause event, a behavior tag and a minute. It is explainable and auditable, and it feeds the panel.

### 2. Object model (target)

```
WorldModel (aggregate root, saved per game)
├── world: World                         shared truth: clock, places, event log
├── epistemics: EpistemicLedger          shared: propositions, assertions, transmissions
├── agreements: AgreementBook            shared: two-party contracts (dates, promises, LEAVE_TOGETHER)
├── rules: StoryRules                    immutable, from story JSON (tracks, conditions, endings, clocks)
├── cast: dict[id, Character]            every person incl. player and offstage people
└── outcome: Outcome | None              the ending that fired (replaces romance_* fields)

Character
├── profile: Profile                     immutable authored identity: name, gender, role, voice, attributes
├── personality: Personality
│     ├── temperament: Temperament       0..1 dials: patience, jealousy, forgiveness, skepticism, openness, pride
│     └── tastes: Tastes                 behavior-tag weights: likes / dislikes (+ intensity)
├── standards: Standards                 Requirements per track (gates, dealbreakers, disclosure, tells)
├── heart: Heart                         dict[target_id, Bond]  (this person's feelings about each other person)
│     └── Bond
│          ├── feelings: RelationshipState     (trust/affection/fear/suspicion/jealousy, existing class)
│          ├── standings: dict[track, Standing] (0..100, tiered, capped, closed)
│          ├── impressions: ImpressionLog       (attributed deltas; bounded, summarized when old)
│          └── stage: str                       derived from the tier of the primary track
├── persona: Persona                     claims this character made about themselves (player and NPCs)
├── agenda: Agenda                       Intentions ranked by priority (pursue, compete, confront, test, repair, leave)
├── body: Body                           availability, activity, routine, block (today's CharacterState fields)
├── presence: Presence                   onstage | offstage | commentator (who can be where, and how they perceive)
└── views (not stored): memories, beliefs, commitments   scoped windows onto the shared stores
```

**The player is a `Character`** (`presence=onstage`, no `personality`/`standards` needed, but it has a `persona`). The **director** is an offstage `Character` who reaches the player only through the existing contact channel (`contact.py`). The **panelists** are `Character`s with `presence=commentator`. They perceive through the camera (§3.8) and appraise with their own tastes, using the same code as housemates.

### 3. Components in detail

#### 3.1 `Profile` and `Persona`: who you are vs. what you've said

- `Profile` is authored truth about an NPC: `gender`, `age`, `occupation`, plus a free `attributes` map (`height_cm`, `family_profession`, `smokes`…). Declared keys come from `rules.attribute_keys` (story JSON). An NPC's own `persona` is seeded from its profile as honest claims.
- `Persona` holds `SelfClaim(key, value, minute, utterance_event_id, audience: frozenset[id])` entries: what this character has *said* about themselves and who heard it.
  - `persona.claim(key, value, event)`: the **first claim of a key is locked** (`persona.locked(key)`). A later claim with a different value is recorded as a `Contradiction(first, second)`.
  - Each claim is also written to the epistemic ledger as a structured `Proposition(subject=self, predicate=key, value)` via `assert_claim`, and transmitted to every listener. So **each listener now *believes* it**, and gossip can carry it on through existing `transmit`.
  - A lie is exposed **in a listener's mind** when that listener's `Belief` on `(subject, key)` has two different values supported (the existing `Belief.stance == "disputed"`, extended to structured values). That listener then appraises a `lie_exposed` event (§3.5). There's no global "is a liar" flag: exposure is per person and spreads through gossip.
- Player facts come only from chat (owner decision). NPC facts come from `Profile`, and an NPC can lie too if the author gives it a `false_claims` list, which is useful for mysteries.

#### 3.2 `Personality`: `Temperament` and `Tastes`

- `Temperament` holds a few 0..1 dials that change *how* a person reacts: `patience` (tolerance for pushing), `jealousy`, `forgiveness` (how fast negative impressions fade), `skepticism` (probes claims, triggers loyalty tests), `openness` (starting warmth to strangers) and `pride` (how rejection hurts).
- `Tastes` maps behavior tags to weights: `{"cooked_for": +1.5, "bragged": -2.0, "kept_promise": +1.0, "flirted_with_other": -3.0}`. The vocabulary is the story's closed `behavior_tag_vocabulary` (the existing extractor ability 11 in `decision_registry.py::behavior_tag_decision`, BL-16-gated), extended with payload qualifiers (`gave_gift:flowers`). Unlisted tags use the story's `default_tastes`, so standard characters need only a short list.

#### 3.3 `Standing` and `TrackSpec` (pure math, no I/O)

```python
@dataclass(frozen=True)
class Tier:                     # from story JSON
    id: str; floor: int; ceiling: int
    gate: Condition             # must hold (from the holder's viewpoint) to rise past `ceiling`

@dataclass(frozen=True)
class TrackSpec:                # e.g. "romance", "candor", "loyalty"
    id: str; tiers: tuple[Tier, ...]
    max_gain_per_day: int; repeat_decay: float; neglect_decay_per_day: float

@dataclass
class Standing:
    track: str; value: float = 0; closed_by: str = ""        # requirement id that closed it
    day_gain: dict[int, float] = field(default_factory=dict)  # day -> points gained (for the daily cap)
    def apply(self, spec, delta, day, gate_open: Callable[[Tier], bool]) -> float: ...
    def tier(self, spec) -> Tier: ...
```

- `apply` enforces, in order: closed → no gain. The daily cap applies. Repeats of the same `(tag, day)` get `repeat_decay ** n`. Otherwise the gain is added up to the current tier's ceiling, and if the next gate is closed, **the surplus is discarded** (not banked). Losses always apply and can drop tiers.
- `neglect_decay_per_day` is applied by `Heart.tick(days)` when the world clock advances with no shared events.
- 100% unit-testable with no world, extractor or LLM.

#### 3.4 `Standards`, `Requirement` and `Condition`: the shared rule language

`engine/rules/conditions.py` holds one small typed condition language, **shared by requirements, tier gates, endings, clocks and beats**:

```python
class Condition(Protocol):
    def holds(self, vp: Viewpoint) -> bool: ...
    def explain(self, vp: Viewpoint) -> str: ...     # engine-only reason, e.g. "needs 2 dates"

# Kinds (closed set, JSON "kind" discriminator):
BelievedAttribute(subject, key, op, value)   # uses vp.beliefs, NOT truth
EventCount(kind, match, with_subject, min)   # dates completed, gifts (payload filter), promises kept
AgreementCount(activity, status, min)
Feeling(dimension, op, value)                # on the holder->subject bond
StandingAtLeast(track, value) / TierReached(track, tier)
Knows(proposition)                           # the holder knows a fact (clue shown, secret learned)
DaysKnown(min) / DaysInTier(track, tier, min)
Not(c) / All(cs) / Any(cs)
CounterAtLeast(clock_id, n)                  # for endings/beats
```

- `Viewpoint(holder, subject, model)` gives *whose eyes* the rule is judged through: a character (`holder` = Minori judging `subject` = player) or `Viewpoint.truth(model)` for endings and clocks. **The same condition class serves both.**
- `Requirement(id, track, tier, condition, on_fail: "cap" | "dealbreaker", disclosure: DisclosurePolicy, tell: str)`:
  - `cap`: the tier's gate is `All(tier.gate, *requirements for that tier)`.
  - `dealbreaker`: when `Not(condition)` becomes *believed-true*, the track closes (`closed_by = req.id`). It is re-checked on every belief change, so a later-exposed lie can close a romance that was open.
  - `tell` is a behavioral hint the storyteller may show while the requirement fails ("cools when height comes up, deflects if asked"). This reuses the idea of the existing `Character.tells`.
- A "standard" personality uses `rules.default_standards[track]`. Custom NPCs add requirements on top (about half the Terrace pool, per owner).

#### 3.5 `Heart`, `Bond` and `appraise()`: how a character reacts

```python
class Character:
    def perceive(self, event: Event, channel: str, model) -> Perception: ...
    def appraise(self, perception: Perception, model) -> Appraisal:
        """Deterministic. For each behavior in the event, judged by *this* person:
           delta = tastes.weight(tag) * base(tag) * relevance(self, actor, target)
           - actor acted toward me       -> my bond with actor
           - actor acted toward someone I care about / my rival / my partner
             -> jealousy, loyalty, protectiveness on bonds (temperament-scaled)
           - told_by channel             -> scaled by trust in the teller (gossip is weaker)
           Returns Impressions (bond deltas with cause event id) + Reactions (candidate Intentions)."""
    def feel(self, appraisal: Appraisal, model) -> None:   # applies impressions via Standing.apply / feelings
    def opinion_of(self, other_id) -> Bond: ...
```

- **Impression** = `(target, track|dimension, delta, tag, cause_event_id, minute, channel)`. `ImpressionLog` keeps the most recent N per bond and folds older ones into per-tag totals, so it stays bounded while the panel can still say "she complained about the bragging 4 times."
- **The same code runs for every observer.** When the player flirts with Riko at dinner, Riko appraises *flirted (toward me)*. Minori, who is dating the player, appraises *flirted_with_other (by my partner)* and gets jealousy and a trust hit scaled by her `jealousy` temperament. Makoto, who likes Riko, appraises *a rival move*. **One event produces three different human reactions**, and nothing in the code is Terrace-specific.
- Existing `character_graph.update_edge` calls from the extractor's rel-state deltas are routed through `Bond` as impressions carrying the current utterance event as cause. That's one writer for feelings.

#### 3.6 `Agenda` and `Intention`: what a character wants and does

- `Intention(kind, target, priority, reason_ids, prerequisites: Condition, expires)`. Kinds form a closed, generic set: `pursue`, `compete_for`, `confront`, `test_loyalty`, `repair`, `withdraw_from`, `share_news`, `protect`, `leave_house`, `pursue_goal` (career/dream threads from `threads.py`).
- Intentions are **born from appraisal reactions** (a jealousy spike leads to `test_loyalty(partner)`, an exposed lie leads to `confront(liar)`, rising romance leads to `pursue(x)`, a rival's success leads to `compete_for(x)`), **from authored goals** (`state.Character.goal`), and **from tier changes** (reaching the dating tier leads to `pursue` with `leave_house` preconditions).
- `Agenda.choose(opportunity, rng) -> ActionProposal | None` is deterministic and seeded, and respects temperament and cooldowns. It is used in three places that exist today:
  1. **Off-screen:** `offscreen.py::resolve_offscreen` asks both characters' agendas instead of rolling flat `BASE_WEIGHTS`. A `compete_for` rival alone with the target proposes a date (the `AgreementBook.propose` path already exists). This replaces `intentions.py::propose_rival_invitations` and the `rivalry` weight hack.
  2. **On-screen initiative:** `speakers.py` chooses who takes initiative from the highest-priority feasible intention among present characters, and hands the storyteller a **beat** (`"Minori wants to ask where you were last night"`) instead of free improvisation.
  3. **NPC–NPC courtship:** two NPCs whose bonds reach the ready tier form a `LEAVE_TOGETHER` agreement off-screen. That is a couple departure, which feeds the director clock.

#### 3.7 `SocialAct` and `respond()`: confessions, asks, invitations

```python
@dataclass(frozen=True)
class SocialAct:
    kind: str            # invite | confess | ask_exclusive | ask_leave_together | accept_offer | leave_alone
    actor: str; target: str; event_id: str; payload: dict

@dataclass(frozen=True)
class Verdict:
    answer: str          # accept | not_yet | reject
    reason_req: str      # the failing Requirement / tier gate id (engine-only)
    reason_hint: str     # in-character, disclosure-safe phrasing seed
    effects: tuple       # impressions (e.g. public rejection), cooldowns, agreement ops

class Character:
    def respond(self, act: SocialAct, model) -> Verdict: ...
```

- The *target character* decides from its own bond, standards and viewpoint, e.g. `ask_leave_together` needs `TierReached("romance", "ready")` plus the stage requirements. If a requirement fails, the answer is `not_yet` or `reject`. `reason_hint` is filtered by the requirement's `DisclosurePolicy`, so a reluctant character never states the hidden rule unless disclosure allows it.
- `confess` accepted moves the bond to the `dating` stage and creates an `exclusive` Agreement (bilateral, per SOCIAL_V2 §3). Rejected becomes a **public** `confession_rejected` event: witnesses appraise it, the actor's pride is hurt, and a cooldown starts.
- `ask_leave_together` accepted creates a `LEAVE_TOGETHER` **Agreement** (proposer, counterpart, both decisions `accepted`). This replaces the six `romance_*` fields, because an agreement is already the codebase's model of mutual consent. Committing it is the ending trigger (§3.9).
- **Recognizing acts:** one new extractor decision, `social_act_decision`, runs in the existing pre-generation batch (`turn_extractor.py`, next to `departure_check`) with no extra LLM call. Options are generated from `rules.social_acts` × present eligible targets, plus `NONE`. Criticality is `CRITICAL` (on failure, do nothing). This replaces the regexes in `world_model/romance.py`.
- **Same-turn narration:** the verdict is computed *before* the storyteller call, and projection adds a one-turn directive ("Minori does not agree yet; reason seed: …"). For `accept` verdicts on terminal acts, a post-reply `act_confirmed` check (one small Jev call, only on those turns) must pass before the agreement commits. This prevents false wins.
- NPC → player offers come from the agenda (`pursue` at the ready tier, alone with the player), and the player's reply is classified as `accept_offer`.

#### 3.8 `Presence` and perception channels

- `onstage` characters perceive by place (existing `present_with_player`, availability).
- `offstage` characters (the director) perceive only through events explicitly routed to them (clocks, contact).
- `commentator` characters perceive through a **camera** channel: every event whose place is `rules.filmed_places` (house, cars, dates), plus public events. They never perceive private memories, beliefs or confessional asides (the protected-content rule already in `SOCIAL_ENGINE_V2_DESIGN.md` §3). So the panel literally knows only what the footage showed.
- Panelists appraise with their own `Tastes` and `Temperament`: Yamasato's `bragged`/`calculated` weights are strongly negative and his temperament is cynical, Torichan rewards `romantic_gesture`, Yukiko Ehara rewards `sincere` and punishes `two_timing`. **Their disagreement emerges from their tastes**, not from a prompt instruction.

#### 3.9 `StoryRules`: endings, clocks and beats (world-level, not per character)

- `Ending(id, kind: win|loss|neutral, condition: Condition, exit_beat, epilogue: "panel_finale"|None, ends_run)`, evaluated in declared order against `Viewpoint.truth` once per turn, after commit. First match sets `model.outcome` (idempotent, persisted). Terrace: `left_together` ← `AgreementCommitted(LEAVE_TOGETHER, includes=player)`. `cut_by_director` ← `CounterAtLeast("couples_left", 3)`. `left_alone` ← `ActCommitted(leave_alone)`. The mystery: `confession` ← `StandingAtLeast(mastermind, "candor", 90) & Knows(...)` in a later phase. Until then, its regex stays behind a legacy condition kind.
- `Clock(id, counts: EventFilter, warn_at, trigger_at, warn_beat)`: a counter over committed events (`couple_departure` excluding the player). The warning beat is delivered by the offstage **director** character through the contact queue as a call.
- `Beat(id, speaker, intent, directive)`: a one-turn storyteller directive with an authored intent. It's used by clocks, endings (exit scenes) and verdicts.
- `gameplay.win_condition_detected` and the `END GAME …` string in `prompt_engine.py` are replaced by `model.outcome` plus a structured `ending` payload. `debug.html` keeps its text marker.

#### 3.10 Commentary: the panel service (LLM rendering, not character logic)

- `commentary/dossier.py::build(model, subject)` is deterministic. From commentator-perceivable events plus the subject's bonds' impression logs, it extracts arcs (tier timeline per bond), key acts and verdicts, lies told and exposed (only if exposed on camera), promises kept or broken, two-timing, conflicts and repairs, rivals, and requirements discovered or missed. Every item carries event ids.
- `commentary/panel.py` builds each panelist's `Appraisal` of the dossier (the same `appraise` code, §3.8), then makes LLM calls: **outline** (segments, each panelist's stance from their appraisal) → **segments** (structured dialogue with `speaker_id`, cites event ids) → **verdicts** (a label per panelist: good/bad/evil…, and a prediction).
- `commentary/validator.py` rejects sentences citing no dossier event, and applies the behavior-not-worth guardrail (TERRACE_HOUSE §M6).
- Modes: `aside` (existing narrator asides, now voiced by the panelists), `departure_segment` (~300 words, NPC exits) and `finale` (~2,000 words, no skip, rendered by `frontend/dialogue.js` with panelist portraits).

#### 3.11 Projection: `character.project(viewer, focus)`

- This finally implements CHARACTER_WORLD_MODEL_REDESIGN **P9**. Each present character renders its own prompt card: identity/voice, mood, **its bond with the player and with others present, as words not numbers**, its top intention as a scene aim, any failing requirement's `tell`, and disclosure-allowed facts. `TurnView.cards` already exists as the slot.
- `rules.context_focus` (TERRACE_HOUSE §M7) sets the budget per component category (relationships vs. places vs. clues). It's applied in `project()` and the Jev context selector.

### 4. Turn pipeline (where each piece runs)

```
begin_turn
  1. clock advance → step_world, threads, Heart.tick(days)           (existing + decay)
  2. off-screen:   Agenda.choose per encounter → events → perceive/appraise/feel for witnesses
  3. player utterance event (existing)
  4. extractor batch (existing pre-generation call) → behavior tags, self_claims, social_act
  5. behavior events committed → every perceiver.appraise → feel → agenda reactions
  6. self-claims → player.persona.claim → ledger assertions → listeners' beliefs; contradictions → lie_exposed
  7. dealbreaker re-check for characters whose beliefs changed
  8. social act → target.respond() → Verdict (pending until confirmation if terminal)
  9. clocks evaluated; beats selected (verdict > clock warning > agenda initiative > conflict focus)
 10. projection: character cards + beats → storyteller
end_turn
 11. utterance events for NPC lines (existing), act_confirmed check if needed → commit agreement
 12. endings evaluated → outcome → exit beat already written / finale scheduled
```

Steps 2, 5 and 6 use the same `perceive → appraise → feel` method, so on-screen and off-screen life follow one set of rules.

### 5. Persistence and migration

- `WorldModel.VERSION` 2 → 3. Each `Character.to_dict()` nests its own components (`personality` and `standards` are *not* saved; they rebuild from story JSON by id, so authored edits apply to existing saves). `heart`, `persona`, `agenda` and `body` are saved.
- **Feelings ownership:** in phase B, `Bond.feelings` *is* the existing `RelationshipEdge.state` object (the same reference, obtained from `CharacterGraph`), so there is no dual write. Phase G makes `CharacterGraph` a read facade over `cast[a].heart` and removes its separate serialization.
- **Two Character classes:** `state.Character` (authored + legacy prompt fields) becomes the source of `Profile` and is gradually thinned. `world_model.CharacterState` becomes `Character`'s `Body`, with `CharacterState = Character` as a compatibility alias until its callers migrate.
- v2 → v3 loader: `romance_relationship_partner` becomes the bond at the `dating` tier plus an `exclusive` agreement. A finished `romance_outcome` becomes `model.outcome`. Missing components are built empty. Round-trip tests go in `test_state.py` / `world_model` tests.

### 6. Build phases (each ships behind story config, is verified on beta and follows `/ship-and-verify`)

| Phase | Delivers | Closes / advances |
|---|---|---|
| **A. Endings & UI** | `StoryRules` loader + `Ending`, `model.outcome`, `ending` payload, ending overlay, goal card (reads today's romance state) | BL-33 (UI part) |
| **B. Character aggregate** | `Character` with `Profile`, `Body`, `Heart`/`Bond` wrapping existing edges, scoped views; the six `romance_*` fields removed via migration; no behavior change | BL-38 (single owner) |
| **C. Standing + conditions** | `engine/rules/conditions.py`, `TrackSpec`/`Standing`, `Standards`/`Requirement`, `Viewpoint`; impressions from existing rel deltas | BL-33 |
| **D. Perceive/appraise** | behavior vocabulary for Terrace, `Personality` authored for the 17, `appraise` for witnesses and gossip, `ImpressionLog`, dealbreakers | BL-34, BL-35 |
| **E. Persona & lies** | `self_claim` decision, `Persona`, structured propositions/values in the ledger, contradiction → `lie_exposed`, disclosure policies, `tell`s | new |
| **F. Social acts** | `social_act_decision`, `respond()`, confession/ask/accept/leave-alone, the `LEAVE_TOGETHER` agreement, `act_confirmed`; delete the `romance.py` regexes | BL-33 |
| **G. Agenda** | `Intention`/`Agenda`, off-screen and initiative driven by agendas, NPC–NPC courtship and couple departures, loyalty tests; `CharacterGraph` becomes a facade | BL-34 |
| **H. Clocks & director** | `Clock`, `Beat`, offstage director via contact, cut ending | new |
| **I. Commentary** | commentator presence/camera, dossier, panel service + validator, three modes, dialogue UI, no skip | new |
| **J. Projection & focus** | `character.project()`, `context_focus`, playtest tuning of thresholds (hosted, both genders) | P9 |

### 7. Tests (no skips; per phase)

- **Pure units:** `Standing.apply` (cap, surplus not banked, daily cap, repeat decay, losses, closed), every `Condition` kind under both character and truth viewpoints, `Requirement` cap vs. dealbreaker, and `Persona` lock/contradiction.
- **Reaction matrix:** one behavior event × observers with different relations (target, partner, rival, stranger, told-by-gossip) produces the expected impression signs per temperament. Asserting "Minori reacts differently from Riko to the same event" is a required test.
- **Belief-based judging:** a believed lie passes a requirement. After exposure (a second claim heard by the same listener, or gossip connecting the two claims), a dealbreaker closes the track only for characters who now hold the disputed belief.
- **Social acts:** a verdict per tier, and a disclosure-safe reason. Public rejection is witnessed. Cooldown. A false act (joke, hypothetical, a third party speaking) gives `NONE`. `act_confirmed` failing means no agreement.
- **Agenda:** a rival with `compete_for` invites the target off-screen. No overlapping interest means no sabotage (SOCIAL_V2 P4-02). An NPC couple departure increments the clock.
- **Endings/clocks:** each ending fires once and survives reload. The warning fires exactly once at 2, the cut at 3. The player's own departure is excluded from the count.
- **Commentary:** the dossier is deterministic. Commentators never see private memories or confessionals. The validator rejects uncited claims. Panelist stances differ for a mixed-conduct fixture.
- **Migration:** v2 saves (with romance fields) load into v3 and round-trip.
- **Simulation:** seeded 30-day runs where a passive player gets cut, a strategic player can win, and a pushy or lying player gets rejected. Report the median days-to-win for tuning.
- **Hosted:** SOCIAL_V2 §17 campaigns plus a Terrace win, a cut and a solo run, both player genders.

## Why deferred / cautions

- This is roughly ten phases of work across `prompt_engine.py` (3,700+ lines), the extractor and the world model. Ship phase by phase. Each phase must pass the full suite and hosted verification before the next one starts.
- **Latency:** the new extractor decisions ride the existing batch. The only new LLM calls are `act_confirmed` (rare) and the panel (once per exit). Measure p50/p95 per SOCIAL_V2 §17.
- **Prompt drift:** the directive must make the storyteller narrate the engine's verdict. The `act_confirmed` check exists because it sometimes won't.
- **Tuning:** thresholds (tiers, daily caps, clock pace) need hosted playtests. The owner wants wins to be hard, not impossible. The simulation phase gives numbers before hosted play.
- Don't enable LLM arena runs for validation without asking the owner (`ARENA_LLM_ENABLED`).

## Touches

`backend/app/engine/world_model/` (`character.py`, `model.py`, `offscreen.py`, `intentions.py`, `romance.py`, `speakers.py`, `projection.py`, `turn.py`, `epistemics.py`, `gossip.py`, `contact.py`, new `heart.py`, `persona.py`, `personality.py`, `standing.py`, `standards.py`, `appraisal.py`, `agenda.py`, `social_acts.py`), new `backend/app/engine/rules/` (`conditions.py`, `story_rules.py`, `endings.py`, `clocks.py`, `beats.py`), new `backend/app/engine/commentary/`, `engine/extractors/decision_registry.py` + `turn_extractor.py`, `engine/character_graph.py`, `engine/state.py`, `engine/gameplay.py`, `engine/authoring_checklist.py`, `api/prompt_engine.py`, `api/story.py`, `backend/app/stories/7_six_strangers/*.json` (and later `1_iu_murder_mystery`), `frontend/index.html`, `frontend/dialogue.js`, plus tests under `tests/backend/app/engine/` and `tests/backend/app/engine/world_model/`.
