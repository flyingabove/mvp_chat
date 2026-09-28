# BL-38 — Reusable object-centered simulation engine and character context

- **Type:** follow-up
- **Found:** 2026-09-26, user-requested engine architecture review; expanded 2026-09-27 after hosted playtests
- **Severity:** high; gossip and consequential dialogue need enforceable authority boundaries.

## Original scope and implementation record (2026-09-26)

This opening record preserves the original backlog scope and partial implementation status. The expanded proposal starts at section 1 below; its code-inspection table is the newer assessment.
`world_model/gossip.py::share_memory` copies text with confidence decay and deduplicates by event ID, without proposition-level assertion/transmission provenance. `events.py::Event` has free-text truth. The engine has several knowledge representations and previous-turn extraction, which need a shared contract before richer social actions depend on them. These are code-review findings, not newly reproduced hosted failures.

## Fix direction
Implement phases 1–2 of [SOCIAL_ENGINE_V2_DESIGN.md](../reference/SOCIAL_ENGINE_V2_DESIGN.md): typed proposals/events, idempotent commit with final response, observation/assertion/transmission separation, belief support chains and perspective-safe projection. Preserve one canonical writer and legacy read adapters. Test false testimony, circular rumor corroboration, absent witnesses, protected confessionals, transaction retry and interrupted save/resume. BL-35 owns agreements; BL-34 owns rival initiative; BL-36 owns IU evidence behavior.

## Why deferred / cautions
This turn produces an engineering design, not a runtime migration. Requires schema versioning, compatible saved sessions and model-level leakage evaluation in addition to deterministic tests. Fictional secret disclosure must never weaken protection of confessionals or system-only content.

**Further implementation (2026-09-26):** Versioned snapshots, idempotent world event IDs with causal links, utterance observations, assertion/transmission provenance and root-source tracking now form a first adapter. The session row stores a completed state and retry reply together. An additive SQLite revision and `BEGIN IMMEDIATE` compare-and-swap now reject stale cross-worker commits; the chat handler refreshes stale cached sessions or returns retryable 409. Remaining: authoritative typed reducer for all writers, structured proposition/contradiction and reliability updates, a single retrieval/epistemic writer, before-display scene validation, full event replay, bounded hot state and model-level leakage gates. JSONL and extraction outbox writes remain separate from the session transaction.

## Touches
`backend/app/engine/world_model/`, `backend/app/engine/extractors/turn_extractor.py`, `backend/app/api/prompt_engine.py`, epistemic graph/retrieval and existing persistence transaction boundary.

---

## 1. Expanded engineering proposal — 2026-09-27

**Status: proposed engineering changes, not implemented or deployed.** This expands BL-38 at the user's request, covering all twelve remaining playtest issues through reusable domain objects. Existing BL-29–37 retain ownership of their feature-specific acceptance; this document owns their shared architecture. All APIs, types and configuration below are proposals unless explicitly described as existing.

The [latest ten-turn campaigns](../reference/SOCIAL_V2_BETA_REPLAY_2026_09_27.md) scored Terrace 4/10 for logic and 4/10 for engagement, and IU 5/10 for both. An accepted date did not happen; characters invented sources, deferred independent action, missed questions and repeated atmosphere. The engineering response is to give each fact and behavior one canonical owner, rather than adding another story prompt or another independent state store.

This refines [Social engine v2](../reference/SOCIAL_ENGINE_V2_DESIGN.md), the [character/world redesign](../reference/CHARACTER_WORLD_MODEL_REDESIGN.md) and the [backend decomposition proposal](../proposals/PHASE_2_BACKEND_RESTRUCTURE_DESIGN_2026_09_22.md). Their existing acceptance scenarios still apply. Where older text makes promise memories authoritative, the agreement object below supersedes that direction. No implementation phase is marked complete by this document.

### Principles

1. **Objects own behavior and invariants.** A character owns perception, decisions and speech; an agreement owns terms and participant decisions; the world owns placement and time. The application coordinates them and calls providers. Domain objects do not call HTTP, SQL or LLM services.
2. Use composition, not `TerraceCharacter`/`MysteryCharacter` subclasses. Pure helpers can remain functions behind object APIs. Avoid a god character class and needless classes around trivial calculations.
3. Believable simulation comes from causality, partial information, independent preferences, travel, scarcity and consequences. Do not simulate every biological detail or force conflict to look realistic.
4. Keep the turn-based clock: closing the app freezes the world. Long player actions advance NPC life through chronological events.
5. Separate world truth, observation, belief and speech. A character can lie, misunderstand, refuse or forget through explicit modeled behavior; generated contradictions are not a substitute.
6. The player controls voluntary actions, feelings and commitments. Engine-resolved external effects may affect the player when supported by the action rules. No NPC can accept on their behalf.
7. Game definitions choose capabilities and policy values. Shared engine code never branches on a story ID. Exceptional abilities, such as ghost perception, use narrow capability adapters with the same contracts.
8. Preserve the prior no-house-log/no-event-feed decision. Players learn through scenes and communication. Any optional case notebook contains only player-known evidence, not an omniscient simulation log.

## 2. Code inspection and reuse map

Inspected local `beta` at `de4781e`. Uncommitted date work exists in `agreements.py`, `commitments.py`, `turn.py`, its tests and BL-35. It is work in progress, not evidence of a deployed fix. Preserve it during implementation and reconcile it with these contracts. Paths below are repository-relative; `world_model/` abbreviates `backend/app/engine/world_model/`.

| Existing code | Verified foundation / gap | Engineering change |
|---|---|---|
| `backend/app/engine/state.py::Character` | Identity, self-knowledge, voice, goal, emotion and legacy relationship value already exist. | Keep the public character identity and compose runtime behavior into it; no third character registry. |
| `world_model/character.py::CharacterState` | Availability, activity, mood, aim, routine, speaker recency; location is read from `World`. No `project()` method. | Make this the character runtime component with decision/perception/context behavior exposed through the character facade. |
| `world_model/model.py::WorldModel` | Existing aggregate includes canonical books and several romance-specific scalar fields. | Preserve aggregate, replace story-shaped scalars with typed goal/decision records incrementally. |
| `world_model/world.py::World` | One location index, derived contents, clock and events; containment-cycle validation. | Keep one physical-state writer; movement requires validated route/access resolution. |
| `world_model/events.py::Event` | Operation IDs, causal IDs, generic payload and free-text `truth`. | Versioned payload types; text becomes rendering rather than semantic identity. |
| `world_model/agreements.py` | Agreement/book and propose/decide/reschedule/resolve functions; two parties, one due time, conflicts by equal due time. | Methods on agreement with terms revisions, participant roles, time intervals and obligation evidence. |
| `world_model/commitments.py`, `turn.py::record_commitments` | Previous-exchange extraction, promise memories; local attendance patch uses regex acceptance and direct due-time movement. | Same-turn typed decisions, reservations and travel. Keep old functions only as migration adapters. |
| `world_model/epistemics.py` | Observations, propositions, assertions, transmissions and support roots already exist; proposition identity is text plus valid-time string. | Structured proposition identity and owner-scoped views in the existing ledger. |
| `world_model/source_guard.py` | Regex/word-overlap repair of player-source attribution. | Sourced speech plans plus validation; retain the narrow filter temporarily as defense. |
| `world_model/evidence.py` | Entity surfaces with attention/tool checks; discovery deduplicated by memory text. | Stable surface IDs/revisions and typed inspect/read/query affordances. |
| `world_model/intentions.py::propose_rival_invitations` | Gender-based conditions, fixed thresholds, daily cooldown and tomorrow-at-19:00 invitation. | Character objectives and generic activity opportunities, configured through data. |
| `world_model/stepper.py`, `routine.py`, `offscreen.py` | Temporal boundaries, seeded encounters and short-turn anti-vanish protection. | Common chronological scheduler/action resolver for routines, appointments and offscreen decisions. |
| `backend/app/engine/character_graph.py` | Directed edges and five relationship dimensions. | Remain authoritative; typed appraisal methods and perspective-safe reads. |
| `world_model/turn.py::begin_turn/end_turn` | Mixes stepping, memories, relationships, agreements, speaker selection and projection. | Keep facade; move rules into objects and commits into `TurnService`. |
| `world_model/projection.py`, `backend/app/engine/prompt_builder.py` | Identity, voice, relationships and knowledge assembled through separate functions; elsewhere details included with a prose caveat. | Assemble typed character/player contexts; remove inaccessible data before model calls. |
| `backend/app/engine/story_loader.py::StoryDefinition` | Generic content model; tolerant parsing can omit malformed data. | Typed validation and explicit errors, with versioned legacy adapters. |
| `backend/app/db/repos.py::SessionRepo._upsert` | Revision compare-and-swap under SQLite `BEGIN IMMEDIATE`; state and last retry reply stored together. | Extend transaction to event batch, durable request receipts and outbox enqueue. Preserve ownership checks. |
| `FactExtractionOutboxRepo`, `backend/app/api/prompt_engine.py` | Async extraction/outbox exists; not all turn effects share the session commit. | Async extraction derives indexes, never retroactively decides consent or physical facts. |

## 3. Domain objects and ownership

| Owner | State owned | Proposed behavioral API |
|---|---|---|
| `Simulation` / existing `WorldModel` | Aggregate references, ruleset identity, revision | `prepare(commands)`, `apply(events)`, `validate()` |
| `World` | Clock, entity placement, physical events | `resolve_travel()`, `advance_to()`, `apply_movement()` |
| `Character` | Identity plus runtime, voice, preferences, objectives and conversation state | `perceive()`, `consider()`, `plan_speech()`, `project()` |
| `CharacterMind` | Mood/appraisals, bounded attention, owner-scoped knowledge access | `interpret()`, `belief_about()`, `choose_intent()` |
| `VoiceProfile` | Diction, rhythm, directness, warmth, register and habits | `constraints_for(context)`; cannot change facts or decisions |
| `ConversationState` | Questions, response status, recognition and introduction history | `receive()`, `pending_for()`, `acknowledge()` |
| `CharacterSchedule` | Routine policy and reservation references | `availability(window)`, `propose_slot()`, `next_boundary()` |
| `Agreement` | Terms revisions, participant decisions, obligations, outcome evidence | `decide()`, `propose_amendment()`, `record_attendance()`, `resolve_obligation()` |
| `RelationshipEdge` | Directional feelings and appraisal history references | `appraise(perceived_event, policy)` |
| `EpistemicLedger` | Propositions, observations, assertions, transmission paths | `record_observation()`, `assert_claim()`, `transmit()`, `view_for(owner)` |
| `Entity` with interaction capabilities | Physical properties, surfaces, access and interactions | `inspect()`, `read()`, `query_record()` |
| `Investigation` | Actor-owned questions, leads, evidence links | `open_question()`, `next_actions()`, `assess_support()` |
| `Goal` / `OutcomePolicy` | Progress and ending predicates | `evaluate(events, decisions)` |
| `Scene` | Participants, channels, visibility and response obligations | `can_perceive()`, `select_speakers()`, `project_for(viewer)` |
| `NarrationPolicy` | Viewpoint, pacing and agency constraints | `build_contract(scene_delta)`, `validate(candidate)` |
| `TurnService`, `SessionRepository` | Provider orchestration and durable commit | Load, prepare, render, validate, commit; no story rules |

A character's knowledge, agreement and relationship accessors are owner-scoped views over the canonical shared books, not copies serialized in every character. The world remains the sole location owner. A derived schedule reservation references agreement ID/revision rather than duplicating terms.

### Character composition

Keep `state.Character` imports working. Initially attach a runtime component referencing the existing `CharacterState` through a registry adapter. `GameState.characters` and `WorldModel.characters` must resolve the same ID/runtime; the final snapshot codec saves it once. Legacy dictionaries become read projections.

Illustrative proposed interfaces, not drop-in code:

```python
class Character:
    identity: CharacterDefinition
    state: CharacterState
    voice: VoiceProfile
    preferences: PreferenceProfile
    objectives: ObjectiveSet
    conversation: ConversationState

    def consider(self, offer: Opportunity, view: CharacterView) -> DecisionProposal: ...
    def plan_speech(self, request: ResponseRequest, view: CharacterView) -> SpeechPlan: ...
    def project(self, scene: SceneView, audience: Audience, budget: ContextBudget) -> CharacterContext: ...
    def apply(self, event: CharacterEvent) -> None: ...

class Agreement:
    def decide(self, actor: ActorId, terms_revision: int,
               decision: ParticipantDecision, evidence: DecisionEvidence) -> EventBatch: ...
    def record_attendance(self, arrival: ArrivalEvent) -> EventBatch: ...
```

Decision methods return proposals against a supplied revision. Only validated event application mutates objects. Inject narrow read ports instead of global `GameState` access. JSON stores IDs and versioned data, not executable policies or circular Python object graphs.

## 4. Canonical commands, events and atomic turns

### Typed action vocabulary

Shared `ActionIntent` variants: `Speak`, `Ask`, `Move`, `WaitUntil`, `Inspect`, `Read`, `Invite`, `RespondToOffer`, `Cancel`, `Amend`, `PerformActivity`, `Depart`. Speech distinguishes assertion, question, hypothetical, refusal, promise and quotation. “Did you go to the cafe?” is not movement. “Maybe tomorrow” is not acceptance.

Each proposal includes session/request ID, actor, expected revision, source segment/evidence spans, ordered dependencies and typed arguments. Name resolution yields authored IDs. Ambiguity in a consequential action produces an in-game clarification, not guessed consent. A semantic `DecisionProvider` may interpret natural language using current extractor infrastructure; its confidence score is not authority.

Versioned events include sequence, operation ID, simulated time, actors, place, payload, source/cause IDs and ruleset version. Examples: `OfferMade`, `ParticipantDecided`, `TravelStarted`, `Arrived`, `ActivityPerformed`, `AssertionUttered`, `ObservationRecorded`, `RecordRead`, `ObligationResolved`, `DepartureCommitted`. `Event.truth` remains compatibility rendering. An utterance proves only that words were said.

### Turn algorithm

1. Load snapshot/revision and check durable request receipt. Same ID/payload returns the exact committed reply; same ID/different payload is rejected.
2. Interpret ordered player attempts. Preserve wait-then-move versus move-then-wait; a question about a future destination cannot change today's route. Critical extraction happens in this turn.
3. Resolve player actions and scheduled boundaries on a private working snapshot. NPC objects propose decisions from their own knowledge views. Do not hold a database transaction during model calls.
4. Build a tentative `SceneResolution` containing NPC acts and consequences. Acceptance and its spoken response reference the same agreement revision.
5. Build sanitized character contexts and the player-visible narration contract; application-owned providers realize the planned acts.
6. Validate speaker IDs, decision polarity, sources, time/place, question responses and player agency. A changed decision requires a new validated plan, not just a text edit.
7. Atomically commit expected revision, events, snapshot, final reply/segments, request receipt and outbox jobs. Publish the cached snapshot and return only after success.
8. A revision conflict discards the stale plan/prose. Reload and retry within a bounded policy, otherwise return a retryable conflict. Never attach stale narration to a new revision.

Initially buffer consequential responses until commit; streaming an uncommitted “yes” would break the contract. After bounded realization failure, a truthful fallback may describe a revalidated subset of events. Remove any undelivered NPC speech decision and its dependent effects. Retain player movement only if the fallback accurately reports it and the complete subset is committed together. Otherwise abort without changing state.

Async extraction can add searchable projections linked to committed speech, but cannot retroactively decide attendance, consent or victory. JSONL exports become replayable outbox effects.

### Replay and storage

Replay applies recorded outcomes without new LLM calls or random decisions. Record policy versions and random draw keys/results; seeded resimulation is a separate operation from event replay. Snapshots record last event sequence and hash. Durable deduplication survives pruning, so an old arrival cannot execute twice after its in-memory event disappears.

Archive history durably and keep only active obligations, relevant relationships, unresolved claims and recent context hot. Indexes/notebook projections remain rebuildable. Never prune a referenced source or pending obligation. Add a per-request receipt table with unique `(session_id, request_id)`, rather than relying solely on the current last-request fields.

## 5. Character-owned speech and context

### What the character contributes

Replace independent prompt assembly with `Character.project()` and `Character.plan_speech()`:

- `VoiceProfile`: register, vocabulary, sentence rhythm, directness, expressiveness, humor and authored examples. Adapt existing `Character.voice` as the initial profile.
- `PreferenceProfile`: values, boundaries, risk tolerance and interests. Keep it separate from voice: a warm character can refuse.
- Dynamic state: mood, aim, availability and directional appraisal.
- `ConversationState`: addressed questions, past answers, introductions, deferred obligations and turn-taking.
- Knowledge view: supported claims, uncertainty, source chains and explicit withholding/deception decisions when enabled.

`SpeechPlan` contains speaker/addressee IDs, response-obligation IDs, approved claims and sources, dialogue acts, decisions to verbalize and voice constraints. Voice controls delivery; it does not manufacture facts or replace an answer with atmosphere.

An addressed question gets an answer, uncertainty, refusal, premise correction or concrete deferred action. These are legitimate outcomes. Close its obligation only when a matching response act is delivered. Unanswered parts remain queued and acknowledged. A question to an absent character is not silently assigned to someone else. Introductions update recognition state after delivery, preventing repeated “what's your name?” exchanges.

### Context isolation

`CharacterContext` contains identity/voice, perceived scene, personally known propositions with epistemic labels, pending questions and selected intentions. Exclude inaccessible whereabouts, undiscovered evidence, another actor's private beliefs and engine-only truth. Mandatory facts and response obligations take precedence over optional sampled memories.

A character decision view may contain its own private motives. Its public speech view contains only the outward act and information selected for disclosure. The shared narrator receives player-visible events and approved public speech acts, not every character's private mind. Remove secret fields before generation; “do not reveal” instructions alone are insufficient.

Batch public speech plans in normal scenes. If private semantic reasoning is needed, the application sends an isolated character view to a provider; never combine disjoint private views into one shared call. Most feasibility and choice logic is deterministic/seeded, avoiding one autonomous LLM call per resident per turn.

Filter retrieval by owner/channel/disclosure permission before ranking. On retrieval failure, use the safe typed context and uncertainty; do not fall back to global lore. Summaries retain proposition/source IDs and disputed status.

### Semantic validation limits

A valid claim ID proves the reference exists, not that the generated sentence means the same thing. Deterministic checks enforce IDs and structural permissions; curated/model-assisted checks assess paraphrase, negation and attribution. Bounded regeneration or minimal approved wording handles ambiguity. JSON schema validation alone cannot guarantee semantic fidelity.

Keep current source/agency filters as temporary defense and telemetry. Retire them fixture by fixture as object contracts cover the behavior; do not grow an endless English regex list.

## 6. Agreements, schedules and consequences

### Agreement semantics

Generalize two parties into explicit roles: proposer, required attendee, optional attendee, performer, beneficiary, informed observer. A unilateral promise binds its performer; informing its beneficiary does not bind them. Keep two-party calls as adapters.

Immutable `AgreementTerms` revisions specify activity ID, roles, venue/channel, earliest/latest start, expected duration, obligations, guest/privacy policy and conditions. A participant decision records actor, terms revision, accepted/declined/tentative/withdrawn status, source act and time. Conditional answers stay tentative until their condition resolves under an explicit policy.

Lifecycle: `proposed -> confirmed -> in_progress -> resolved`, with decline, cancellation and expiry branches. Individual obligations resolve as fulfilled, breached, excused, cancelled or unknown. An unanswered proposal can expire without a broken promise. Attendance alone does not prove fulfillment; missing evidence is not automatically breach.

Changing venue, time or participants creates an amendment requiring affected participants' decisions. Existing terms remain effective until amendment acceptance or explicit cancellation. A third person volunteering creates a join request; it cannot turn a private date into a group outing. Group quorum/unanimity is an activity policy, not a universal rule.

### Real attendance

`CharacterSchedule` considers reservations, routine blocks, preparation and route time. Check interval overlap rather than exact due-time equality. `World.resolve_travel()` checks access, routes, availability and movement capabilities.

Confirmation schedules preparation/departure/arrival events against the terms revision. A character can negotiate, cancel or arrive late if travel becomes impossible. Do not directly place them at a venue merely because the due time passed. Closed venues, sleeping participants and ambiguous destinations produce explicit pending/failure outcomes rather than silence.

`ActivityDefinition` holds prerequisites, roles, resources, duration, interruptibility and completion predicates. Coffee, rehearsal, a witness interview and a repair appointment use this same machinery with different data. Calls use a communication channel rather than physical co-location.

### Time and appraisal

One chronological queue merges routine boundaries, travel, appointments, contacts and world changes. Tie order uses documented priorities and stable IDs. Revalidate event preconditions at execution; cancellation invalidates queued work by agreement revision.

Long skips process intermediate boundaries. Interrupt for a configured player choice or important event, report the reached time and wait for the player's next action. NPC-only events may resolve offscreen. A work cap checkpoints and resumes internally; it must not drop obligations or falsely claim the skip completed.

`RelationshipEdge.appraise()` consumes perceived outcome evidence, obligation importance, ability to comply, notice, explanation credibility and character values. Only the affected direction changes unless another actor independently appraises it. Apply once per event/actor/policy. Non-witnesses need a source path. Correcting a false rumor need not erase all emotional consequences.

## 7. Knowledge, testimony and investigations

### Extend the existing epistemic objects

`Proposition` gains subject IDs, predicate, typed value, polarity, valid-time interval and optional place; free text remains an attached gloss. Example: `entered(person_17, studio, interval_20_00_20_15)`. Natural-language equivalence is not established by identical words alone: uncertain mappings stay separate with a candidate-equivalence link pending evidence. “Not seen entering” is not equivalent to “did not enter.”

`Observation` references a committed event or entity surface revision, observer, channel, perceived details and observation time. `Assertion` references proposition, speaker, stance, utterance event and claimed source. `Transmission` records actual delivery, sender/recipient, parent and independent root source. `Belief` stores the owner's support/opposition references, confidence and unresolved alternatives. Confidence reflects evidence quality and source reliability; it is not proof of objective truth.

Use `EpistemicLedger.view_for(character_id)` as the character's only knowledge port. Adapt current `BeliefState`, memory store, session chunks and index retrieval to this writer. Memories are recall projections; assertions and observations are the evidence. A gossip loop repeating one root cannot count as three independent witnesses. A forged document can be a real observed document containing a false claim; reading it does not make its claim true.

### Truthful speech, mistakes and deliberate lies

`Character.plan_speech()` selects `disclose`, `uncertain`, `withhold`, `misremember` or `deceive` acts according to its knowledge and policies. Default factual assertions require support. A deliberate lie may lack truthful support, but requires an explicit decision tied to a motive and a perceived situation. An authored/seeded memory error references the remembered material and distortion, rather than manufacturing an arbitrary source after generation.

Store what was actually said separately from what the speaker claimed its source was. A permitted lie such as “you told me” must not create a fake historical player utterance or a fake observation. The hidden decision receipt can record deception intent; listeners only get what they heard. They can challenge the claim without the narrator revealing the lie. This preserves mystery and realistic dishonesty while preventing accidental hallucinations from becoming canon.

A denial adds counter-testimony; it does not erase prior speech or automatically settle the issue. Contradiction rules distinguish incompatible claims about the same time/subject from legitimate changes over time. Corroboration updates belief through source paths, not by overwriting history.

### Evidence as entity behavior

Extend `Entity` with composed capabilities such as `Inspectable`, `Readable`, `RecordSource` and `Interactable`. A surface has stable ID, revision, prerequisites (light, access, tools, attention), visible content and hidden causal links. Discovery key is `(observer_id, surface_id, revision)` rather than the exact text of a memory. Repeat inspection can confirm the known state; a changed surface or new tool can reveal something new.

An `Investigation` links actor-owned questions to claims, physical observations, unresolved conflicts and available follow-up actions. It does not know undiscovered truth. A security desk, calendar or archive is a `RecordSource` with access policy, coverage interval, retention, query cost and response delay. `query_record()` returns an actual supported record, a pending request, denial or no matching record. Never fabricate footage because the player asked for it.

Authored leads map to executable affordances: where to go, whom to ask, which record to inspect, or what condition unlocks access. Unsupported leads must resolve honestly as unavailable instead of repeatedly promising progress. A suspect interview is a conversation/activity and their answer remains testimony. This machinery also supports checking a work shift, settling a household disagreement or verifying a delivery in non-mystery games.

Expose evidence through a player-safe `InvestigationView`: observation versus testimony, source as known to the player, uncertainty, disputes and pending tasks. Feed it into dialogue and the existing journal where permitted by product policy. No raw event IDs, hidden solution or internal trust score enters the player UI. A new notebook UI is optional and separately scoped; the engine contract does not depend on it.

## 8. Independent character aims, relationships and endings

### Objectives and opportunities

`Character.objectives` replaces the combination of a single prose aim and special rival invitation code with a bounded set of `Objective` objects. Each has owner, target references, category, priority, satisfaction conditions, current step, deadline if authored, and abandonment/reconsideration rules. Reuse `EvolvingTrait` and personal threads through adapters; preserve their history rather than resetting motives.

An `Opportunity` describes a feasible action with costs, participants, location/time, expected benefit and evidence available to this character. The character evaluates it using preferences, current needs if enabled, relationship beliefs, obligations and risk. Filter hard constraints first, then rank plausible options using bounded utilities and seeded variation. Record the score components for developer diagnosis. Do not choose from impossible actions and then narrate around the failure.

Examples of reusable intentions: invite, cooperate, seek information, practice, work, rest, avoid, apologize, compete for limited time, offer help. Romance is one configured objective/activity family. A workplace rival can compete for a rehearsal slot with the same opportunity/resource mechanisms. Gender eligibility belongs in story policy; it is not the engine's definition of rivalry or attraction.

The player is not the center of every motive. Characters can prefer someone else, prioritize work or choose solitude. Their estimate of another character's feelings comes from their own observations, not direct access to that character's hidden relationship edge. Only the target owns its acceptance/refusal decision.

### Fair scheduling and visible consequences

Reuse routines, offscreen encounters and threads, but send their proposed actions through the same action/decision resolver as on-screen behavior. Choose candidates at relevant boundaries (availability changes, new offers, discovered facts), not with an LLM for every minute or every actor.

Keep per-character initiative budget and cooldowns, plus time-since-last-opportunity to avoid starving low-scoring characters forever. At most a configured number of unsolicited scene acts can compete with direct player questions. Repeated refusals impose topic/target cooldowns. Measure distribution across rosters; do not force every rival to sabotage or every run to produce a triangle.

An offscreen action creates only actual perceptible traces and sourced reports. The scene selector can highlight a feasible consequence, but cannot invent a quarrel to hit an engagement target. A cancellation message is delivered through the same contact/knowledge channels as other communication.

### Relationship decisions and goals

Keep directional feelings in `CharacterGraph`; use separate typed `RelationshipDecision` records for explicit relationship status, consent and withdrawal. Affection/trust thresholds may influence a choice but never substitute for an affirmative decision. Move the aggregate's `romance_*` fields behind a migration adapter into these records and a generic `Goal` state.

`OutcomePolicy` checks required decisions, actor eligibility, lifecycle status and validated actions. Leaving together requires current mutual departure decisions plus a committed departure transition; “let's go” in unrelated dialogue does not end the game. Rejection, solo departure, withdrawal and continued play are distinct valid results. Game data selects terminal versus nonterminal outcomes; no unrequested fixed stay length is introduced.

Departure updates membership, outstanding agreements, contact reachability and goal progress in one event batch. Historical evidence and relationships continue to reference stable IDs. Replacements receive new actor IDs; they never inherit the departed person's promises or knowledge. Verify both current player-gender paths while keeping the underlying machinery gender-neutral.

## 9. Scene continuity, narration and content validation

### Identity, presence and channels

Extend `Scene` with a perception policy for hearing, sight, distance, barriers, speech volume and channel membership. Same room is not automatically proof of hearing everything; “private” is a desired interaction constraint, not magical secrecy. If privacy is infeasible, offer a quieter place or report that someone is within earshot. Moving for privacy follows normal travel and player choice.

Calls/messages carry explicit participant/channel state; a nearby person cannot hear a phone call without an applicable audibility rule. Sleep, attention and character capabilities affect perception. Confessionals remain excluded from world witnesses and ordinary retrieval. Special perception capabilities specify exactly which channels they grant, without bypassing protected content boundaries.

Recognition records distinguish identity, known name, prior introduction and last encounter. `SceneTransition` knows whether someone arrived, returned, resumed conversation or remained present. Greeting selection reads that event and the character's encounter history, avoiding a fabricated “welcome back.” Stable addressee IDs are realized as “you” when addressing the player, avoiding the IU third-person self-reference failure.

### Narration as realization of observable change

`NarrationPolicy` takes an approved `SceneDelta`: validated actions, sensory observations, public speech acts and response obligations. It may supply connective language and permitted nonconsequential texture, but cannot assign new player feelings, voluntary actions, agreement decisions, travel or clues. Authored openings use the same contract.

Pacing policy prioritizes direct responses and meaningful consequences, then optional atmosphere. Record recent imagery/semantic beat IDs and allow repetition when something actually changed or the player asks to revisit it. Character voice is supplied by `VoiceProfile`; narrator style is supplied separately by the game. This avoids making every character sound like the game's atmospheric narrator.

Do not impose a universal short-response cap. Configure target length, decorative-beat budget, scene-change emphasis and response queue limits; mandatory answers can exceed the target. Neutral silence, refusal and a quiet scene remain valid. Engagement means useful choices and consequences, not a compulsory new clue or argument every turn.

### StoryDefinition validation

Validate content at load/authoring time: IDs and references, start date, routes, ability/policy dependencies, activity roles, goal predicates and voice profile ranges. Fail invalid new definitions with actionable field paths instead of silently skipping characters. Legacy content receives an explicit compatibility adapter with diagnostics.

For the IU opening defect, inspect authored strings and decode JSON exactly once. Flag unintended literal escaped newline sequences and replacement characters for author review; do not globally unescape strings because intentional code/text may contain them. Validate opening text against initial scene state and player agency. Preview the rendered segments in the existing browser QA flow. This is a small content correction supported by a generic validator, not a mystery-specific narration filter.

## 10. Per-game mechanics, tuning and safe disabling

### Configuration ownership

`StoryDefinition` compiles a typed, immutable `SimulationRuleset`. Precedence: engine defaults -> capability preset -> story overrides -> permitted character/activity overrides. Reject unknown fields, invalid ranges, missing references and unsupported dependencies. Store the resolved ruleset/content version and hash in the session. Changing author defaults must not silently change an ongoing game; use an explicit migration or start a new session.

Separate **optional behavior** from **invariants**. An author may disable proactive invitations, evidence investigation, fatigue or terminal endings. They cannot disable revision safety, make unsupported statements become world facts, or let a character consent for another actor. Capability combinations are validated as a dependency graph.

| Mechanic | Owner and tuning controls | Disabled behavior / dependencies |
|---|---|---|
| Voice | Character `VoiceProfile`: register, directness, expressiveness, verbosity target, examples | Neutral voice fallback; factual/agency constraints remain. |
| Conversation | `ConversationPolicy`: question priority, defer limit, speaker count, interruption budget | Minimal addressed-response behavior remains; optional ensemble initiative can be off. |
| Agreements | `AgreementPolicy`: grace periods, invitation timeout, quorum, guest rules, acceptable conditions | Reject/clarify formal scheduling intents; never falsely claim a durable booking. Requires clock/identity. |
| Travel/schedules | `MobilityPolicy`, `SchedulePolicy`: route durations, preparation, flexibility, interruption | May use a static-scene policy with travel unavailable; must not auto-confirm impossible offsite plans. |
| Autonomous aims | `ObjectivePolicy`: weights, exploration, per-actor cooldown, action budget | Characters react but do not originate new autonomous plans. Existing obligations still execute. |
| Needs | Optional `NeedsProfile`: fatigue/social-energy decay, recovery and priority | No need simulation; authored routines still apply. Add only when a demonstrated scenario needs it. |
| Relationship appraisal | Edge policy: event salience, learning rates, memory/forgiveness, saturation | Static relationships or no appraisal; explicit decisions/consent remain separate. |
| Knowledge | `EpistemicPolicy`: source reliability, attention/recall, permitted deception | Basic observation/source integrity always on; disabling gossip removes transmission opportunities only. |
| Investigation | `InvestigationPolicy`: record cost/delay, lead hints, available affordances | No case workflow or notebook; normal observation and honest source attribution remain. |
| Perception | Scene/character capabilities: hearing range, barriers, channels | Simple conservative co-presence rules; no cross-scene leakage. |
| Narration | `NarrationPolicy`: viewpoint, texture budget, length target, callback cooldown | Minimal observable outcome narration; agency protection always on. |
| Goals/endings | `OutcomePolicy`: eligibility predicates, completion evidence, terminal flag | Open-ended play; departures can still occur as world events. |

Example proposed configuration (field names are illustrative; numeric values are starting hypotheses, not calibrated defaults):

```yaml
simulation:
  schema_version: 3
  preset: social_world
  capabilities:
    agreements: true
    autonomous_intentions: true
    investigation: false
    needs: false
  agreements:
    arrival_grace_minutes: 10
    invitation_timeout_minutes: 120
    default_guest_policy: request_join
  intentions:
    max_unsolicited_acts_per_scene: 1
    target_cooldown_minutes: 180
  narration:
    decorative_beats_per_reply: 1
    target_words: 100
  outcomes:
    terminal_on_goal: false
characters:
  resident_a:
    voice:
      directness: 0.8
      expressiveness: 0.4
      register: informal
    preferences:
      activities: {coffee: 0.7, rehearsal: 0.9}
```

A mystery preset can enable investigation and disable courtship opportunity templates while retaining schedules, evidence, agreements and independent goals. A ghost can have an authored perception/mobility capability without changing how claims, invitations or questions work. Presets must produce the same typed objects; they are defaults, not separate engine implementations.

Switches apply to new sessions by default. Disabling a mechanic mid-save requires a migration policy for pending state: drain existing obligations, explicitly cancel them with observable events, or reject the change. Never delete confirmed plans silently. A rollback cannot send a newer snapshot to an incompatible old writer.

## 11. Concrete walkthroughs

### A. Coffee invitation — also works for an interview or rehearsal

1. Player asks a named character to meet tomorrow at 10 at an authored venue. The action interpreter emits one `Invite` with those terms and exact input spans.
2. The target's own view supplies preferences and known obligations. Schedule feasibility checks actual routes without giving the character unrelated hidden information. The target proposes accept, decline, tentative or a counteroffer.
3. An acceptance speech plan and `ParticipantDecided` event refer to the same terms revision. Only after the response validates are they committed together. No next-turn extraction is necessary to bind the target.
4. A third person offers to join. Their join request does not change the accepted private terms; affected participants must approve an amendment.
5. On the next skip, the target departs early enough and travels. At 10 the actual arrival is recorded once. If access changed, the target can contact the player or arrive late; no teleport and no silent disappearance.
6. Arrival establishes attendance, not fulfillment. Shared activity evidence resolves the relevant obligation. Each character later appraises only the outcome they observed or learned about.

### B. Alleged player statement — also works for workplace gossip

1. IU is asked for a source. Her `CharacterView` has no observation that the player mentioned footage.
2. Honest `plan_speech()` cannot choose “you told me”; it selects uncertainty or an available real source. If deliberate deception is permitted and independently selected, the utterance remains a false assertion with no fabricated historical source.
3. The player disputes it. Record counter-testimony, preserving the earlier assertion. The investigation offers an actually available record request.
4. A record is accessed through its entity capability. The result is observed, source-linked and shown as corroborating/contradictory evidence. A request denial remains a denial; no footage is invented.

### C. Independent competition without a special rival system

A resident wants time with another resident; a coworker wants a scarce rehearsal room. Both form objectives, evaluate feasible opportunities and make proposals. The other participant or resource policy independently decides. The player may observe a competing booking or hear about it through a valid source. Neither outcome requires a story-ID branch or universal hostility.

## 12. Implementation sequence and integration boundaries

Implement vertical slices behind explicit session capability versions. Extend existing modules first; extract only when a domain boundary is real. No parallel simulator and no long-lived dual writers.

| Phase | Concrete edits and exit condition |
|---|---|
| **0. Baseline and inventory** | Freeze current replay fixtures and identify every clock/location/relationship/knowledge writer in `prompt_engine.py`, extractor, world model and repositories. Reconcile the uncommitted attendance slice. Record a baseline snapshot hash and source contracts before moving behavior. |
| **1. Authority and object facade** | Add typed commands/events and character composition; keep `world_model/turn.py` as facade. Implement `TurnService`, receipt/event storage and transactional outbox in current persistence. Move each writer behind event application, not all at once. Exit: retry, concurrency, crash/replay and read-only projection gates. |
| **2. Character context and conversations** | Implement `Character.project`, voice/context types and conversation obligations. Replace identity/voice/relationship/knowledge prompt reads with adapters to that interface. Migrate `source_guard` fixtures. Exit: no inaccessible data in model contexts; direct response, source and agency scenarios pass. |
| **3. Agreements and chronological activities** | Extend `agreements.py` with participant roles/revisions and obligation evidence. Convert `commitments.py` and extractor to adapters. Integrate reservations/routes with `routine.py`, `stepper.py`, `contact.py`. Exit: complete confirmed meeting, cancellation, conditional and conflicting-plan scenarios through save/resume and skip. |
| **4. Epistemics and usable evidence** | Evolve existing `epistemics.py`, `memory.py`, `gossip.py`, `entities.py`, `evidence.py`; adapt legacy belief/retrieval writes. Implement actor-owned investigation views and record affordances. Exit: contradiction, false-source, circular rumor and real follow-up evidence scenarios. |
| **5. Independent objectives and appraisal** | Replace `propose_rival_invitations` conditions with opportunity templates and character policies. Reuse `threads.py`, `offscreen.py`, graph edges and `drama.py`. Exit: varied independent behavior across rosters without forced rivalry or hidden-information planning. |
| **6. Narration, goals and authoring** | Finish scene/narration contracts, content validator, typed relationship/goal transitions and `romance.py` adapter retirement. Correct malformed opening content. Exit: both ending paths, player agency, continuity and pacing scenarios. |
| **7. Integrated acceptance** | Complete the existing social-v2 P1–P5 and cross-phase gates; fresh hosted campaigns, source-safe context checks and browser verification. Remove obsolete writers only after integration proof. |

Phase 2 can use the existing ledger's safe subset; advanced contradiction support lands in Phase 4. Phase 3 must use the Phase 1 transaction boundary. Phase 5 depends on the agreement and knowledge contracts, not merely their prompt summaries. Initial defect fixes may ship before the whole program, but report their limited scope.

Suggested new modules under `backend/app/engine/world_model/`: `commands.py`, `reducer.py`, `scene.py`, `conversation.py`, `policies.py`, `appraisal.py`, `activities.py`, `scene_contract.py`. Keep character-specific components beside `character.py`; keep application provider and persistence work outside the domain package. Final paths should follow the existing backend-decomposition plan, not introduce a second `TurnService` or snapshot codec.

### Migration and rollback

- Add a versioned `SnapshotCodec` and one `SessionFactory` used by new game and restore. Migrate `WorldModel.VERSION = 2` snapshots explicitly; do not rebuild a broken saved world silently.
- Reuse IDs and authored identity/voice; map `CharacterState` to the runtime component. Resolve legacy mood/relationship conflicts with documented provenance precedence, preserving unresolved alternatives rather than guessing.
- Import legacy accepted agreements only where the saved participant decision supports it. A player-only promise does not become mutual acceptance. Missing venue/time/source stays unknown and eligible for clarification.
- Convert legacy memories to sourced references when possible; otherwise mark `legacy_unknown`. Never invent a witness, consent decision or evidence record during migration.
- Map existing romance state to generic relationship/goal records while preserving withdrawals and terminal outcomes. Replacements and departed characters retain distinct IDs.
- Preserve a pre-migration snapshot and conversion report. Unknown future versions or corrupt references fail with a recoverable diagnostic; never reset the session into a fresh story.
- Shadow new decision logic without applying it to compare proposals. After cutover there is exactly one writer per field; adapters read or translate commands, never maintain independent authoritative copies.
- Pin schema, ruleset and authored content versions. Rollback routes compatible saves to compatible code or uses a tested explicit downgrade. Toggling a feature flag is not a downgrade strategy.

## 13. Acceptance scenarios and measurement

These are proposed test gates, not results. Each mechanical scenario asserts events, snapshot state, perspective visibility and displayed behavior; checking only that a sentence contains a keyword is insufficient.

| ID | Reported issue / ownership | Required proof |
|---|---|---|
| O01 | Date does not happen — BL-35 | Clear acceptance creates one confirmed agreement in the same turn; realistic departure/arrival occurs at the venue across save/reload; no teleport or duplicate arrival on retry. |
| O02 | Consent, conditions and private dates — BL-35 | “Maybe, if work finishes” remains tentative; refusal stays refusal; third-party join request cannot amend private terms; explicit withdrawal cancels affected future actions. |
| O03 | Promises lack consequences — BL-35 | Fulfilled, missed, excused and cancelled obligations differ; attendance is not completion; only observers/informed actors appraise consequences, exactly once. |
| O04 | Invented sources — BL-36/38 | Named, pronoun, reported-speech, negated and paraphrased source claims are grounded; intentional lies do not fabricate actual source events; a circular rumor is one root. |
| O05 | Investigation stalls — BL-36 | Available footage/calendar/witness lead executes through a real affordance to evidence, denial or pending status; missing records are not invented; pending tasks survive reload. |
| O06 | Evidence versus testimony — BL-36 | Conflicting statements remain visible as disputes; reinspection does not rediscover unchanged surfaces; new surface revisions can reveal new observations; notebook is player-scoped. |
| O07 | Passive rivals/independent aims — BL-34 | Across authored rosters, independent work/social aims generate feasible actions; uninterested characters can remain uninterested; NPCs cannot inspect each other's hidden feelings to plan. |
| O08 | Direct questions ignored — BL-37 | Correct addressee answers, refuses, expresses uncertainty or acknowledges deferral; multiple questions remain tracked; chatter does not close them. |
| O09 | Player agency — BL-29 | Neither opening nor generated narration invents voluntary action, emotion or consent; legitimate external consequences remain possible and source-linked. |
| O10 | Repetitive prose/voices — BL-37 | Voice changes preserve identical mechanical outcomes; characters remain distinguishable; repeated decoration falls without suppressing necessary answers or forcing conflict. |
| O11 | Identity/scene continuity — BL-31/37 | Introductions persist; return greetings require a relevant encounter transition; correct second-person player address; no speech from absent/ineligible speakers. |
| O12 | Broken opening text — BL-37 | Authored opening renders intended line breaks and characters in desktop/mobile; deliberate literal escapes are preserved; content validation gives actionable field errors. |
| O13 | Physical/time regression — BL-30 | Wait-then-go and go-then-wait preserve order and charge travel once; appointments during long skips execute chronologically; interruption reports actual reached time. |
| O14 | Endings/cast — BL-33 | Both existing gender paths reach a validated mutual ending; refusal, withdrawal, solo leaving and continued play behave distinctly; replacements inherit no private state. |
| O15 | Atomicity/replay — BL-38 | Inject failures before generation, before/after commit and during outbox delivery. Same request returns same reply and one event batch; concurrent workers cannot overwrite; replay hashes match. |
| O16 | Reuse and configuration — BL-38 | Run the same action contracts in social, mystery and a minimal third test fixture (e.g. workplace appointment) using only data/policies, without adding a product story. Invalid flag combinations fail explicitly. |
| O17 | Migration/disable — BL-38 | Old saves retain facts/unknowns; no new consent or knowledge appears; disabling mechanics handles outstanding work explicitly; incompatible rollback is rejected. |
| O18 | Privacy and source isolation — BL-27/38 | Remove a witness and their knowledge/planning input changes; alter a secret unknown to an NPC and its input does not change; private calls/confessionals never appear in unauthorized contexts. |

### Deterministic and model-level checks

Use state-machine/property tests for agreement transitions, temporal ordering, one-writer invariants, idempotency, containment and source graphs. Metamorphic tests vary an irrelevant secret, character name, story ID or voice while preserving equivalent mechanics. A new story name must not alter domain behavior. A different voice must not change consent.

Use fixed scripted provider outputs for deterministic integration tests and a separately budgeted real-model corpus for ambiguity, paraphrase, contextual refusals, unknown identity, multi-intent commands and player-agency violations. Test mechanical correctness and prose entailment independently. One passing generated response is focused evidence, not a universal fix.

Track direct-response completion, unsupported source claims, agency violations, attendance outcomes, repeated imagery, answer length, character distinction, NPC opportunity distribution and choice consequences. Denominators matter: an honest refusal is a completed response, an unanswered invitation is not a failed attendance, and unavailable evidence is not necessarily a progression bug. Record error examples rather than only aggregate scores.

Use blinded length-controlled comparisons plus human play review for engagement. Never accept a mechanically invalid run because a judge prefers its prose. Hard invariant fixtures require zero failures; qualitative improvements require a documented baseline/candidate comparison without regressions in logical consistency. Do not invent a universal numerical engagement threshold before calibration.

### Scale and performance

Measure 6/30/100-character fixtures, long-skip workloads and long-running saves: p50/p95 latency, model calls/tokens, queued events, hot state size and retrieval time. Use indexed event/source lookups and a time-priority queue instead of all-pairs scans each turn. Cache only owner-safe projections keyed by revision/policy/visibility; invalidate when any key changes. Benchmarks establish budgets before optimizing; no unmeasured latency promise.

### Release proof

For each implemented slice, follow ship-and-verify: relevant deterministic tests, integrated suite, local browser flows, integrated beta push, exact deployed SHA, then hosted feature replay. Include desktop Chromium, iPhone WebKit and simulated standalone WebKit. Record raw player inputs, responses, structured segments, accessible debug evidence and latency; do not claim protected system prompts were captured.

Final acceptance includes at least 20-turn campaigns on both existing player-gender paths, both games, fresh and resumed sessions, plus scripted reachable ending/contradiction scenarios. Archive grades and failures per scenario. These campaigns supplement, not replace, the existing social-v2 cross-phase criteria.

## 14. Completion boundaries and remaining cautions

This document is the requested engineering proposal. Runtime implementation is intentionally not part of this documentation task. BL-38 remains open until shared ownership, authority, projection, migration and replay acceptance pass. BL-29–37 close separately only when their feature-specific hosted proof passes; a single successful date does not close all agreement work.

Main risks to address during implementation:

- **Overengineering:** build one vertical scenario through current objects first; do not create every optional needs model or generic plugin framework up front.
- **False certainty:** typed fields and model confidence do not solve semantic interpretation. Keep unknowns, source spans and conservative in-game clarification.
- **Prompt leakage:** never serialize a broad engine snapshot into a character context and hope instructions hide it.
- **Migration drift:** shared stores need one writer and explicit adapters; dual-writing old/new representations makes inconsistencies harder to diagnose.
- **Unfair NPC behavior:** feasibility can use actual physical state, but planning preferences use the actor's own information. Engine truth must not leak into a rival's choices.
- **Narration changing simulation:** realization renders an approved decision; if its meaning changes, revalidate the decision before committing anything.

The desired outcome is a reusable simulation core: authored games supply people, activities, places, evidence, goals and tuning; objects enforce what those things can do and what each character can know and say.
