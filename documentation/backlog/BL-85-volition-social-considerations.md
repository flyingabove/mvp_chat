# Volition: one data-driven layer for what characters want to do (generic social engine)

Pattern taken from Comme il Faut / Ensemble (Prom Week, Slice of Life FDG '25) and Versu: a character's urge to act is
the **sum of weighted social rules that are true from their own point of view**. We already have the pieces (typed
`Condition`s, `Viewpoint`, `Personality`, `StandingBook`, `Intention`/agenda, typed effects through single writers).
What is missing is the layer that joins them, so every "who wants to do what" decision is data, not code.

## BL-85 — Replace hand-coded NPC desire heuristics with weighted considerations (volition)
- **Open (2026-10-01, beta `582ee13`):** each mechanism hard-codes its own logic and numbers for what a character
  wants. Seven places do it, each written differently:
  - `world_model/agenda.py` `refresh_agendas`: tier reached means `pursue`, two or more admirers means `compete_for`.
  - `agenda.py` `next_beat`: has no repeat cost, so a `pursue` beat is offered every turn (BL-37).
  - `world_model/intentions.py` `propose_rival_invitations`: affection thresholds 0.25 and 0.1, plus gender checks.
  - `world_model/offscreen.py` `outcome_weights`: `BASE_WEIGHTS`, warmth multipliers and a `rivalry` gender block.
  - `world_model/act_fallout.py`: `WITNESS_LOSS 2.0`, `REFUSER_LOSS 2.5`, `RIVAL_AIM 0.5`.
  - `world_model/rivals.py`: aims are seeded once at world build.
  - `rules/personality.py` `STRATEGIES`: a single `aim_scale`.

  This has three costs:
  - **Engine logic is not generic.** The world model has 19 `player_gender`/`genders.get` sites, against the
    SOCIAL_ENGINE §1 rule "no gender rule in generic engine logic".
  - **New personality behaviour means new code.** `scheming`, `safe_pick`, `planfulness` and `candor` have no
    consumers (BL-80).
  - **Tuning is scattered.** Nothing explains why a character acted.

### Design
1. **Considerations** are story data. Each one is
   `{id, intent, weight, when: <Condition>}`.
   - `when` uses the existing closed language in `rules/conditions.py`, judged from the actor's `Viewpoint`
     (`holder` = actor, `subject` = target). A character therefore reasons only from their own knowledge, and
     privacy holds by construction.
   - Tri-state: `None` (unknown) never fires a rule.
   - Example: `{"id": "strangers_hold_back", "intent": "flirt", "weight": -4, "when": {"kind": "not", "condition":
     {"kind": "acquaintance_at_least", "level": "familiar"}}}`.
2. **Intents** are a closed, story-extensible vocabulary.
   - Engine defaults: `pursue, compete_for, test_loyalty, invite, flirt, confide, avoid, gossip_about, confess`.
   - Offscreen outcome kinds (`chat, activity, conflict, affection, plan, gossip`) are intents too.
   - An `Intention.kind` is an intent.
3. **`rules/volition.py`** (pure, no I/O):
   - `volition(view, intent, considerations) -> Score(total, fired_ids)`.
   - `rank(view_fn, actor, targets, intents) -> list[Choice]`, with a stable order: score, then the order of
     authored considerations, then the id. This is the CiF "first in list wins" tie rule, so it is deterministic.
   - `fired_ids` is the explanation. It goes to the debug panel and Jev's target view; it never reaches the
     storyteller as raw text.
4. **New condition kinds**, closed, each with `explain()` and parser validation:
   - `trait` (temperament dial op value)
   - `strategy` (in list)
   - `has_intention` (the holder's own agenda kind toward the subject)
   - `acquaintance_at_least`
   - `in_couple`
   - `eligible` (the appraisal policy covers the pair; this replaces every gender check)
   - `present`
   - `witnessed` (the holder witnessed an event of a kind/tag by subject [toward a third person], within N days)

   `event_count` gains `within_days`, matching CiF's "was rude in the last N steps". A third party is referred to
   by the role names `holder | subject | third`, and `Viewpoint` gains `third`. There are still no executable
   expressions.
5. **Default pack** `rules/volition_defaults.json`:
   - Generic, with no names or story ids.
   - Merged as engine defaults, then story `volition` overrides (SOCIAL_ENGINE §8 order).
   - It reproduces today's behaviour exactly, so adopting it is a no-op until a story tunes it.
   - Per-intent `threshold` (minimum score to act) and `cooldown` live beside the considerations.
6. **Typed effects** for consequences (fallout, practice outcomes):
   - `impression(track, delta)`, `feeling(dimension, delta)`, `add_intention(kind, priority, days)`,
     `counter(+n)`.
   - Applied only through the existing writers (`StandingBook.apply`, `graph.update_edge`, `agenda.add_intention`).
   - Idempotent per cause event id.
7. **Hard limits** (unchanged contracts):
   - Volition ranks admissible options only. It never creates consent and never overrides refusal, cooldowns or
     closed tracks.
   - `social_acts.assess` / `npc_decision` keep the verdict.
   - Zero LLM calls. Jev stays optional, through the existing resolver.

### Phases (each: failing-first tests, ship-and-verify; P1-P4 must be byte-for-byte parity)
- **P0 Golden harness.** Record per-day agendas, beats, invitations, offscreen outcomes and fallout for seeded
  campaigns 0-11, both player genders (`test_terrace_campaigns.py` pattern), as a fixture. Every later parity
  phase diffs against it.
- **P1 Core.**
  - `volition.py`, the new condition kinds, parsing and validation (unknown intent/kind, `|weight| <= 10`, unique
    ids, thresholds name real intents), and the default pack.
  - Unit tests: tri-state, ties, privacy (remove a witness and the score changes; change a hidden feeling and it
    does not).
- **P2 Agenda.** `refresh_agendas` and `next_beat` read volition. A `beat_repeat` consideration (a negative weight
  on the same beat today) closes the BL-37 note. Parity, except that note's intended change, which gets its own
  test.
- **P3 Invitations and off-screen.**
  - `propose_*_invitations` and `outcome_weights` take weights from volition; the gender blocks are deleted in
    favour of `eligible`. Parity on the golden harness.
  - `rivals.seed_rival_aims` becomes a consideration evaluated continuously, so late arrivals get aims with no
    special path.
- **P4 Fallout as data.** `act_fallout` constants become default-pack effects. Parity.
- **P5 New behaviour** (changes what players see, so it needs the hosted arena gate and an offline sim over seeds):
  - strategy and trait considerations (`scheming`, `safe_pick`, `planfulness` for plan reliability, `candor`)
  - acquaintance gating of NPC flirting and confession
  - an NPC-initiated `confess` intent behind a large lead
  - `goal_weights` with shift conditions
- **P6 Generic proof.**
  - A minimal non-Terrace fixture (a workplace with two colleagues and one rival, no romance track) runs the same
    pack through data only (SOCIAL_ENGINE O16).
  - Rename-content test: behaviour follows data, not names.
  - Update `design/SOCIAL_ENGINE.md` (move this design in as built) and delete this item.
- **Follow-up, file separately when started:** social practices (Versu/ESP).
  - Staged, role-based exchanges whose stage actions carry an intent, preconditions and typed effects, chosen by
    volition and voiced by the storyteller.
  - These would generalise `opening.group_ritual`, the choice cards and future `stage_talk`/`watch` (BL-83) into
    one registry.

### What this closes or unblocks in the current backlog
- **Closes:** BL-76(b) (NPC initiative gated on acquaintance and tier); BL-34(2) (aims for later arrivals); BL-37's
  `next_beat` cadence note; BL-80(b, c) (consumers for `scheming`, `safe_pick`, `planfulness`, `candor`).
- **Mostly closes:** BL-80(a) (goals and shifts become considerations; content still needed); BL-82(b, e) (NPC
  confession intent; fallout sizes become tunable data, and the long-run sim is still needed).
- **Unblocks or shrinks:**
  - BL-82(a) "still thinking" (`safe_pick` resolves through volition).
  - BL-83(b, c) (`stage_talk`/`watch` become intents; execution needs BL-81).
  - BL-75 (`rival_aim` becomes one weight to sweep).
  - BL-06 (decides it: NPC-side drift comes from the world model via volition, not the extractor).
  - BL-84(5) (a `gossip_about` intent for third-party reads).
- **Not solved:**
  - BL-81 (volition chooses *what* to want; async planning decides *how*).
  - BL-11 (NPC-NPC edges are still content).
  - BL-35 attendance.
  - Any prompt or prose item (BL-12/22/25/37 wording).

- **Next:** P0, then P1. Do not start P5 before P1-P4 show zero golden diffs.
- **Touches:**
  - New: `engine/rules/volition.py`, `rules/volition_defaults.json`.
  - Changed: `rules/conditions.py`, `rules/personality.py`, `world_model/{agenda,intentions,offscreen,rivals,act_fallout}.py`,
    `engine/content_validation.py`, story JSON (`volition`).
  - Tests: `tests/backend/app/engine/rules/test_volition.py`, the golden harness.
  - Docs: `design/SOCIAL_ENGINE.md`.
