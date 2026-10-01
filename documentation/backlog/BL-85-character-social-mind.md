# The social mind: characters whose traits, goals, stances and beliefs make drama on their own (generic engine)

**Principle (owner, 2026-10-01):** drama comes from the **character object**, not from per-mechanic code. Put any two
or more characters in a room, and the following, read from each one's own point of view, should produce engaging
scenes in every story:
- their personalities (MBTI type);
- their goals;
- their stances toward each other ("considers Yuto a rival", "has a crush on Arisa", "resents Momoka");
- what each one knows;
- what each one **thinks the others know**.

Stories only supply data. Prior art: Comme il Faut / Ensemble (weighted social rules), Versu (practices), Slice of
Life FDG '25 (symbolic state, LLM only voices it).

## BL-85 — Build the character's social mind and let scenes be composed from it
- **Open (2026-10-01, beta `582ee13`):** the parts exist but are scattered, and the character object does not own
  them.
  - **Personality type** only sets dial defaults and reaches Jev (`npc_decision._TRAIT_WORDS`). The storyteller
    never learns that someone is an INTJ or what that means for how they talk and act.
  - **Goals** are a free-text `EvolvingTrait` (`engine/state.py` `goal`). The world model never reads them. BL-80(a)
    asks for weights and shifts.
  - **Attitudes toward people** exist only as anonymous intentions with no stance behind them (`pursue`,
    `compete_for`, `test_loyalty` in `agenda.py`), plus one-off modules:
    - `rivals.py` seeds aims once;
    - `act_fallout.py` hard-codes losses;
    - `stakes.py` writes motive notes;
    - `intentions.py` and `offscreen.py` carry their own rivalry logic with gender checks (19 `genders.get` sites).

    The edge-scoped `disposition` is persisted and never read (BL-27 row 13).
  - **Knowledge** is first-order only: memories, the epistemic ledger and persona claims. Nobody models "I think she
    knows", "she doesn't know I saw", or "I think he likes me". This is the source of dramatic irony, secrets and
    bluffing.
  - **Scenes** are assembled in `turn._build_view` from about ten unrelated directive sources (beats, signals, stake
    notes, tells, requirement hints, conduct notes). The scene never asks "what is the tension between these people".

### 1. The character object
`world_model/person.py` `Person` is already the aggregate (profile, body, heart, scoped views). It gains four parts.
Each is a **view or a small store owned per character**. None is a second copy of existing state.

```python
class Person:
    personality: Personality   # rules/personality.py: type (MBTI), dials, strategy, tastes; + describe() for the LLM
    goals: Goals               # weighted goals, each with shift conditions
    stances: Stances           # typed, directed attitudes toward others, each with cause and strength
    mind: Mind                 # what I know, what I think others know, what I think others feel
    heart: Heart               # existing: feelings and standing (single writer: graph / StandingBook)

    def stance_toward(self, other) -> list[Stance]
    def wants(self, scene) -> list[Want]           # ranked options for this scene, own view only
    def inner_state(self, scene) -> InnerState     # disclosure-safe private brief for the storyteller
```

| Part | Holds | Built from (reuse) | New storage |
|---|---|---|---|
| Personality | MBTI type, dials, strategy, tastes | `rules/personality.py` | none; add `describe()` with an engine type catalogue that stories can override |
| Goals | `Goal(id, kind, target?, weight, shifts)`; kinds are a closed, extensible list: love, career, status, belonging, keep_secret, revenge, protect | the `goal` trait and story `personalities[key].goals` | goal weights on the person, with history kept in `EvolvingTrait` |
| Stances | `Stance(kind, target, about?, strength, cause_ids, since_day)`; kinds: crush, rival, ally, resents, suspects, protective_of, owes, distrusts, ex, admires | **derived** from heart feelings, standing tiers, own agenda, witnessed events and goals, by stance rules | `StanceBook` in `WorldModel`, recomputed each turn, persisted for cause history; replaces `disposition` |
| Mind | first order: beliefs and memories (existing); **second order**: `ThinksKnows(owner, other, proposition, basis)`, `ThinksFeels(owner, other, feeling, basis)` | memories, `EpistemicLedger`, persona beliefs, affinity signals, co-presence at events | second-order entries in the epistemic ledger |

### 2. Stances: "considers this person a rival" as a real, explainable trait
- A stance is a **trait of the holder about one other person** (sometimes about a third: `rival(target=Yuto,
  about=Arisa)`).
- It is derived, never free-written by the LLM. Stance rules are weighted considerations over the existing
  `rules/conditions.py` language, judged from the holder's `Viewpoint`. A stance holds while its summed weight
  passes the kind's threshold, so `strength` is that sum.
- Rules live in a generic default pack (`rules/stance_defaults.json`), which stories can override. Examples:
  - `crush(X)` ⇐ standing tier ≥ interested toward X; plus personality (openness); minus `career` goal weight.
  - `rival(Y, about X)` ⇐ I have `crush(X)`, and I **witnessed or was told** that Y shows interest in X. It never
    comes from Y's hidden feelings.
  - `resents(Y)` ⇐ a witnessed rude or `failed_confession` event caused by Y, weighted by low forgiveness, within
    N days.
  - `suspects(Y, P)` ⇐ I hold a disputed belief on a claim Y made (`persona.belief` status disputed), plus
    skepticism.
- Every stance keeps `cause_ids` (event or memory ids), so "why does Momoka resent you" has an answer for debug and
  Jev.
- New closed condition kinds needed: `trait`, `strategy`, `goal_weight`, `has_stance`, `witnessed`,
  `acquaintance_at_least`, `in_couple`, `eligible` (this replaces every gender check), and a `within_days` option on
  `event_count`. The role names `holder | subject | third` let a rule reference a third person.
- Intentions stay as the **action** layer (what I will do today). They are now derived from stances and goals. For
  example, `rival` with a strategy of `fast_mover` or `scheming` gives `compete_for`. The agenda keeps its API.

### 3. Mind: first- and second-order beliefs (theory of mind without telepathy)
- **I think X knows P** only with evidence I perceived:
  - I told X;
  - I saw X present when P was said or happened;
  - someone told me they told X.

  The basis is stored, and so is its absence: "X wasn't there when I learned P", so X probably doesn't know.
- **I think X feels F about me** comes only from behaviour I perceived:
  - affinity signals (`signals.py`), now recorded as the observer's perception (deliberately ambiguous, so belief
    confidence stays low);
  - witnessed behaviour tags;
  - X's claims.

  Decoys mean this belief can be wrong. That is intended.
- Derived scene facts the storyteller can use, always from one character's view:
  - **Secret held:** I know P, P matters to X, and I think X doesn't know.
  - **Dramatic irony:** I know P, and X doesn't know I know.
  - **Exposure risk:** I hid P from X, and someone present who I think knows P is about to talk to X.
  - **Misread:** I think X likes me, but the engine truth says otherwise. Truth stays engine-only and is used only to
    choose the scene, never written into a prompt.
- Second-order beliefs update with the same perception path as memories (`observe_event`, `transmit`, gossip). No
  new provider calls.

### 4. Scene: from character objects to drama
`world_model/scene.py` `Scene(people, place, time)` builds **dynamics** from each present person's own parts:
- **Pair** `(A, B)`: A's stances toward B and B's toward A, each from its owner's view. Temperament interplay comes
  from a type/dial clash table: both high pride means they needle each other; E with I means one fills the silences;
  T meeting F means bluntness lands hard. Goal clash: same love target, or keep_secret against a curious person.
  Knowledge asymmetry comes from the mind.
- **Triangle** `(A, B, C)`: A is a rival of B about C and C is present; A holds a secret about B that C would care
  about; A thinks B likes C.
- **Dynamic kinds** form a closed registry: `rivalry, crush, triangle, secret_held, dramatic_irony, exposure_risk,
  resentment, suspicion, goal_clash, temperament_clash, debt, alliance`. Each kind has:
  - a detector over the person parts;
  - a `tension` score (stance strengths × relevant goal weights × temperament);
  - a wording template.
- **Selection:**
  - Rank by tension, with variety: a dynamic shown recently is damped, and paraphrase duplicates share a cooldown
    (SOCIAL_ENGINE O27).
  - Surface at most two dynamics per turn.
  - Stable ordering makes the choice deterministic.
  - Unanswered direct questions still come first (as `next_beat` does today).
- **Rendering**, one prompt section that replaces the scattered directives:
  - Each present person's card gets one MBTI line from `Personality.describe()` (for example, "INTJ: few words,
    plans ahead, dislikes small talk"), their active goal, and their stances toward people **in this room**.
  - Their `inner_state` adds what they are hiding and what they think others know, phrased as subtext. They never
    state it outright, and hidden feelings are never asserted as fact. This is the `stake_notes` framing, made
    general.
  - Plus one line naming the scene's chosen tension.
  - Cap: a fixed line budget per scene, with the people who speak this turn first.
- **NPC initiative** comes from the same objects. `Person.wants(scene)` ranks admissible actions for the chosen
  dynamic: compete, needle, confide, withhold, probe, test, gossip_about, invite, confess. It uses weighted
  considerations, the CiF volition sum. The winner becomes the turn's beat, and an invitation remains a state event
  as today. This replaces `next_beat`, `stakes.py` and the per-module rival logic.

### 5. Example: two residents in the kitchen, nothing authored for this scene
- **Arisa** is ENFP, with a love goal of 0.8 and `crush(player)`. She thinks Momoka likes the player too (she saw
  Momoka linger near the player twice). She knows the player turned down Momoka's confession last night, because she
  was in the room.
- **Momoka** is ISTJ, with a career goal of 0.6, `resents(player)` from that refusal and `rival(Arisa, about
  player)`. She doesn't know Arisa saw the refusal.
- **What the scene finds:**
  - a triangle: Momoka is a rival of Arisa about the player;
  - dramatic irony: Arisa knows about the refusal, and Momoka doesn't know Arisa knows;
  - a temperament clash: ENFP warmth against ISTJ reserve.
- **What reaches the storyteller:**
  - Momoka is clipped and practical, and steers away from last night.
  - Arisa is bright, and is tempted to mention it without saying how she knows.
- **The result** is tension the player can read and push on. If Arisa does let it slip, Momoka's mind gains `Arisa
  saw` and a `resents(Arisa)` stance. The next scene changes because of it.

### 6. Owner decisions (2026-10-01)
- **The LLM writes everything; the objects shape the prompt.** Every scene (player or NPC-only) is written by the
  LLM. Personality, goals, stances, mind and scene dynamics only build the prompt. Changes to state come back
  through the existing extraction pass (extractor plus Jev), the same way player turns work today.
  - The engine is deterministic up to the prompt. Prose is not, so the simulation is judged by the rubric (BL-87),
    not by golden prose.
- **Realism with tunable nudges, not enforced detail.** How a scene plays follows from personality. The engine
  only nudges, and every nudge has a tuning knob (BL-87).
- **The mind is a per-character store with fog of war.** Each character keeps what they know and what they think
  others know in the database, like a real video game.
  - Nobody knows where others are or what they did without perceiving it or being told.
  - NPCs search, miss each other, and act on stale or wrong beliefs.
- **Plans have two horizons.** There is a short-term plan (this scene or day) and a long-term plan (days). How far
  ahead someone plans comes from personality: `planfulness`, where J is high and P is low, so an INTP rarely plans
  long-term. Multi-step execution is BL-81.
- **Goals change, and need not be love.** Goals shift with events, and anyone may have a goal like "watch the world
  burn". Game-mode rules sit on top and are configured as data. For example, in Terrace a mutually committed couple
  leaves the house.
- **Interruptions are written realistically.** When someone walks into a scene in progress, the LLM writes the
  interruption realistically from the scene state.
- **The player is one more `Person`** under the same rules, with choices from input. In a headless run, an AI
  resident fills the player's slot.
- **Free will over routine.** A strong enough goal can pull someone off their routine (skip work for a date), and
  that costs something.
- **Locations** carry `privacy`, `filmed` and `earshot` (adjacent rooms that can overhear).
  - **Objects** carry generic affordances (`use, give, read, hide, break, move`) with social, goal and evidence
    effects.
  - Needs (hunger, fatigue) stay off unless a story turns them on.

### 7. Contracts (from SOCIAL_ENGINE.md, still binding)
- Everything is judged from the holder's view. Engine truth is used only to choose scenes, never in prompts.
- Stances, wants and dynamics never create consent or override refusals, cooldowns or closed tracks. Verdicts stay
  in `social_acts` / `npc_decision`.
- LLM budget: at most two LLM calls per player turn (response plus extraction, Jev-assisted). A headless NPC scene
  uses the same shape: one writing call plus extraction.
- Single writers stay as they are: feelings go through the graph, standing through `StandingBook`, intentions
  through `agenda.add_intention`.
- No story ids, names or genders in engine code. Eligibility is data (`appraisal.eligible`).

### Phases (failing-first tests in each; ship-and-verify)
- **P0 Golden harness.** Record per-day intentions, beats, invitations, offscreen outcomes and fallout for seeded
  campaigns 0-11, both player genders. P2 is diffed against it.
- **P1 Personality and goals on `Person`.**
  - `Personality.describe()` with an engine MBTI catalogue (16 short behaviour lines, overridable per story) goes
    into each present card. This changes what players see, so it goes through the arena gate.
  - `Goals` with weights and shift conditions, read from story JSON and the existing goal trait.
- **P2 Stances.**
  - `Stance`, `StanceBook`, the stance rules and default pack, and the new condition kinds.
  - Intentions are derived from stances. The rival seeding, fallout and gender blocks move into rules.
  - Parity with P0. Each intended change (late-arrival aims, beat cadence) gets its own test.
- **P3 Mind.**
  - Second-order `ThinksKnows` and `ThinksFeels`, kept by the perception path.
  - No-telepathy tests: remove a witness and the belief disappears; change a hidden feeling and nobody's mind
    changes.
- **P4 Scene.**
  - `Scene`, the dynamics registry and ranking, `inner_state`, and `Person.wants`. These replace `next_beat`,
    `stakes.py` and the scattered card directives.
  - Arena gate, plus an offline sim over several seeds measuring how often a dynamic appears and how varied the
    dynamics are.
- **P5 Strategies.**
  - `scheming` uses secrets and second-order beliefs (stage talk, selective telling).
  - `safe_pick` resolves pending answers (BL-82a).
  - `planfulness` affects plan reliability; `candor` affects disclosure.
- **P6 Generic proof.**
  - A minimal workplace fixture (two colleagues, one secret, one promotion goal, no romance track) produces dynamics
    from data alone.
  - Rename-content test.
  - Move this design into `design/SOCIAL_ENGINE.md` as built, then delete this item.

### What this closes or unblocks
- **Closes:**
  - BL-80(a, b, c): goals and shifts; scheming and safe_pick; consumers for planfulness and candor.
  - BL-76(b): NPC initiative gated by stance and acquaintance.
  - BL-34(2): stances are derived for anyone present, including late arrivals.
  - BL-37: the beat cadence note.
  - BL-27 row 13: `disposition` replaced by stances, so non-main characters' attitudes reach the prompt.
- **Mostly closes:**
  - BL-84(3, 5): room energy becomes part of temperament interplay; third-party reads come through gossip and
    second-order beliefs.
  - BL-82(b, e): NPC confession as a want; fallout as stance rules.
  - BL-83(a): claims passed on carry the teller's intent through the mind.
- **Unblocks or shrinks:**
  - BL-83(b, c): stage talk and watching become wants; executing them needs BL-81.
  - BL-82(a).
  - BL-75: rival strength becomes one stance weight.
  - BL-06: decides it; NPC-side drift comes from the world model.
  - BL-36: the mind's provenance is the base for the evidence journal.
- **Not solved:**
  - BL-81: asynchronous planning (how to carry out a want over several steps).
  - BL-11: authored NPC-NPC edges.
  - BL-35: attendance.
  - The prose and pacing items.

- **Related:** BL-86 is the headless season simulation and admin watch mode that proves this. BL-87 is the drama
  direction knobs and the Jev script rubric that tune and judge it.
- **Next:** P0, then P1. Do not start P4 before P2 shows zero golden diffs and P3 passes its no-telepathy tests.
- **Touches:**
  - Changed: `world_model/person.py`, `rules/personality.py`, `rules/conditions.py`, `world_model/epistemics.py`,
    `world_model/{agenda,intentions,offscreen,rivals,act_fallout,stakes,signals,turn}.py`, `engine/content_validation.py`,
    story JSON (`personalities[*].goals`, `stances` overrides).
  - New: `rules/stance_defaults.json`, `world_model/{stances,mind,scene}.py`.
  - Tests and the golden harness.
  - Docs: `design/SOCIAL_ENGINE.md`.
