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
3. **Enjoyable, plausible drama takes priority over mundane realism.** Choose heightened, surprising and humorous scenes when their causes and character choices remain plausible. Causality, partial information, preferences and consequences constrain the drama; they do not require characters to make sensible choices or always follow routines. Do not simulate every biological detail.
4. Keep the turn-based clock: closing the app freezes the world. Long player actions advance NPC life through chronological events.
5. Separate world truth, observation, belief and speech. A character can lie, misunderstand, refuse or forget through explicit modeled behavior; generated contradictions are not a substitute.
6. The player controls voluntary actions, feelings and commitments. Engine-resolved external effects may affect the player when supported by the action rules. No NPC can accept on their behalf.
7. Game definitions choose capabilities and policy values. Shared engine code never branches on a story ID. Exceptional abilities, such as ghost perception, use narrow capability adapters with the same contracts.

   This promises independence from **story identity in executable rules**, not the absence of genre-shaped content. Presets are authoring conveniences that expand into the same validated capabilities and values; a runtime resolver must not inspect the preset name. No arbitrary expression DSL or executable YAML is required: start with typed fields, enums and a small registered predicate set. Rename a story/preset without changing expanded data and behavior must remain identical. Swap equivalent activity data across presets and the same object methods must execute. A preset that silently selects a story-specific implementation violates this contract.
8. Preserve the prior no-house-log/no-event-feed decision. Players learn through scenes and communication. Any optional case notebook contains only player-known evidence, not an omniscient simulation log.

### Confirmed owner decisions after proposal review (2026-09-27)

These decisions supersede a realism-first reading of earlier design text:

- Optimize for the most enjoyable dramatic scene within plausibility, including humor. A character may knowingly ditch work for a date and joke about the likely consequences; their work obligation is not silently erased.
- Before a player-requested skip passes important known events, list the affected events and ask for confirmation. Engine-to-player messages and player-to-engine commands use parentheses, separated from in-world dialogue.
- Default NPC autonomy to a tunable middle setting. More simulated time without player involvement allows more causally connected changes, including butterfly effects; this is not wall-clock simulation while the app is closed.
- Permit intentional lies. Generally provide observable hints whose strength depends on the character's deception ability and circumstances; skilled liars are harder to read. A nervous gesture is not proof of a lie.
- Allow tentative plans and genuine misunderstandings. Different characters may interpret the same exchange differently; canonical records must preserve what was said and decided rather than falsely manufacturing mutual agreement.

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
| `DeceptionProfile` / character expression | Lying skill, composure, stress response and expressive habits | `plan_deception()`, `express(intent, pressure)` propose speech and perceivable cues, not a public truth label |
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
| `DramaticPolicy` | Game-level weights for tension, surprise, humor, emotional payoff and repetition | `rank(plausible_opportunities)`; cannot overwrite character decisions or physical facts |
| `SkipPreview` / `EngineInteraction` | Requested target, affected player-known events, confirmation token, revision | `preview_skip()`, `confirm()`; engine communication does not enter character memories |
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

Each proposal includes session/request ID, actor, expected revision, source segment/evidence spans, ordered dependencies and typed arguments. Name resolution yields authored IDs. Unresolved actor identity or an irreversible player action needs clarification rather than a guessed target. Social ambiguity may remain unresolved and generate character-specific expectations as described in section 6; do not force every tentative exchange into a clarification prompt. A semantic `DecisionProvider` may interpret natural language using current extractor infrastructure; its confidence score is not authority.

Versioned events include sequence, operation ID, simulated time, actors, place, payload, source/cause IDs and ruleset version. Examples: `OfferMade`, `ParticipantDecided`, `TravelStarted`, `Arrived`, `ActivityPerformed`, `AssertionUttered`, `ObservationRecorded`, `RecordRead`, `ObligationResolved`, `DepartureCommitted`. `Event.truth` remains compatibility rendering. An utterance proves only that words were said.

### Turn algorithm

1. Load snapshot/revision and check durable request receipt. Same ID/payload returns the exact committed reply; same ID/different payload is rejected.
   Classify engine interaction separately from in-world action. A skip requiring confirmation produces an `EngineInteraction` preview before any world-time advancement, character decision, model-generated scene or outbox side effect. Persist the pending interaction/receipt only.
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

The initial execution profile below selects minimal approved wording rather than a repair-generation call; any later regeneration profile must publish a revised total call/attempt budget first.

Keep current source/agency filters as temporary defense and telemetry. Retire them fixture by fixture as object contracts cover the behavior; do not grow an endless English regex list.

### First concrete semantic gate: attributed statements and direct answers

Implement `SpeechGroundingValidator` against owner-visible utterance/observation records before attempting a general semantic truth checker. This is a proposed bounded design, not a solved arbitrary-language entailment claim.

1. A `ResponseObligation` holds addressed actor, question span, requested proposition/source and response kind. `SpeechPlan` selects answer/uncertain/refuse/correct-premise/defer and its evidence references. Defer must name an actual pending action or explicitly say no answer is currently available; it cannot invent a future record check.
2. The realization schema returns segments plus speech-act annotations: `speaker_id`, `addressee_id`, `obligation_ids`, `claim_refs`, `source_refs`, `decision_refs` and text spans. Treat annotations as model proposals, not proof; the validator inspects the entire final text, including unannotated clauses.
3. Deterministic checks reject nonexistent references, a speaker without a hearing/reading path, a source after the current time, changed actor identity, unauthorized disclosure and a decision polarity inconsistent with its agreement. A question/quotation/denial cannot be promoted into the source assertion. Unknown or truncated source text cannot justify an exact quotation. Preserve full canonical utterances; the current 240-character event truncation in `turn.py` is insufficient as the only semantic evidence.
4. One bounded semantic-verifier call receives only the public speech contract, exact permitted source excerpts and candidate response. It returns `supported`, `contradicted` or `unknown` for each consequential attribution and answer, with candidate/source spans and explicit speaker, polarity, time and speech-act comparisons. It must also identify unannotated attributions and unanswered obligations. Treat malformed verdicts and uncertainty as non-passing; never average away one unsupported consequential claim.
5. On a failed attribution, choose a deterministic source-safe formulation. If available, quote the exact heard words with their speaker and frame them as words spoken, not objective truth. Otherwise use an honest response such as “I don't have a source for that.” For a genuinely supported direct answer, render the approved answer proposition; do not replace it with evasive uncertainty just to pass the gate. A refusal is allowed only if the character selected refusal. Keep the obligation pending if a safe relevant response cannot be delivered.
6. Do not recursively call models until a result passes. The initial bounded profile uses no repair-generation call; use an approved fallback or abort the invalid subset as section 4 requires. An explicit `deceive` act validates against the intended utterance plan while recording it as testimony; it never needs or creates a fictional historical source event.

Example: source input “Did anyone check the footage?” cannot support IU saying “You told me you checked the footage.” Neither overlapping words nor a valid event ID is enough. A direct response “No, I haven't checked” may fulfill the question only if it matches the character's actual supported state or an explicit authorized deceptive act. Asking two questions and answering one leaves one obligation open.

The verifier can itself be wrong. Calibrate it with a labeled corpus covering questions versus assertions, negation, reported speech, ambiguous pronouns, conditional answers, invented qualifiers, lies, long utterances and omitted answers. Report false acceptance, false rejection and abstention separately. Critical source/consent fixtures must have zero accepted violations; voice/pacing quality remains a separate evaluation. Until calibration passes, consequential attributions use constrained approved wording instead of claiming free-form speech is verified. Deployment/model changes rerun this corpus. This gate targets O04/O08; it does not by itself solve O10 or all epistemics.

### Explicit model-call budget

Introduce application-owned `TurnInferenceBudget`, shared by all providers and retries. The following is the **proposed initial execution profile**, not a measurement of today's runtime or a promised response time:

| Request | Logical model calls | Maximum provider attempts |
|---|---:|---:|
| Explicit skip needing only a known-event preview | 0 | 0 |
| Ambiguous natural-language skip requiring interpretation before preview | 1 interpretation | 2 including one transport retry |
| Normal turn, six present characters, two pending objectives | 1 intent extraction + 1 public realization + 1 semantic verifier = 3 | 4 total, including at most one shared transport retry |
| Confirmed skip with deterministic offscreen progression and one final scene | Up to the same 3 | Same 4; not multiplied by NPC count or elapsed ticks |
| Exact retry of a committed request | 0 | 0 |

`Character.consider`, `plan_speech`, `project`, `CharacterMind.interpret` over already typed observations and `DramaticPolicy.rank` are local operations. The extractor interprets player language; character choice scores typed opportunities, and the realizer expresses public acts. An unfamiliar opportunity can be deferred or clarified instead of creating a hidden per-character provider loop. The verifier is online gameplay validation, not an arena judge. Its runtime implementation and evaluation are still proposed.

Budget rules apply to provider attempts, including timeouts and 429/5xx retries. A deadline or attempt-cap exhaustion chooses a safe fallback/abort; retries do not silently double the cap. Reserve capacity for validation before generation. Log per-stage attempts, latency, input/output tokens, fallback and total cost. Token caps are bounded per call and per turn, then sized with actual context fixtures; no unmeasured token-price claim is made.

In this profile, additional LLM context ranking, quote attribution, post-hoc translation, shadow providers and async extraction are disabled or replaced by local/index/event projections; requested output language is handled in realization. Existing functionality must be checked before switching profiles. Background work cannot hide uncounted spend: separately report its calls and require an explicit budget if enabled. The current handler contains optional dynamic context selection, quote attribution, translation, regeneration and background extraction, so today's count is not asserted to equal three.

Isolated private LLM decision-making is a future opt-in profile, not required by this object model or the default path. It must receive an explicit larger budget and measured latency approval before rollout; never exceed the default cap because a new character exists. User response-time preference and any grading-pilot preference are pending in section 15. A call cap alone is not evidence of latency viability.

## 6. Agreements, schedules and consequences

### Agreement semantics

Generalize two parties into explicit roles: proposer, required attendee, optional attendee, performer, beneficiary, informed observer. A unilateral promise binds its performer; informing its beneficiary does not bind them. Keep two-party calls as adapters.

Immutable `AgreementTerms` revisions specify activity ID, roles, venue/channel, earliest/latest start, expected duration, obligations, guest/privacy policy and conditions. A participant decision records actor, terms revision, accepted/declined/tentative/withdrawn status, source act and time. Conditional answers stay tentative until their condition resolves under an explicit policy.

Lifecycle: `proposed -> confirmed -> in_progress -> resolved`, with decline, cancellation and expiry branches. Individual obligations resolve as fulfilled, breached, excused, cancelled or unknown. An unanswered proposal can expire without a broken promise. Attendance alone does not prove fulfillment; missing evidence is not automatically breach.

Changing venue, time or participants creates an amendment requiring affected participants' decisions. Existing terms remain effective until amendment acceptance or explicit cancellation. A third person volunteering creates a join request; it cannot turn a private date into a group outing. Group quorum/unanimity is an activity policy, not a universal rule.

### Tentative plans and asymmetric expectations

Add character-owned `PlanExpectation` records referencing the actual exchange, proposed terms, the character's interpretation, confidence and believed participant commitments. These live in the character's mind/knowledge view; they do not independently mutate the agreement. A hopeful character may interpret “maybe tomorrow” as likely, while the speaker still considers it tentative. Interpretations depend on personality, relationship experience, context and evidence, with tunable misunderstanding probability and confidence calibration.

The objective record remains tentative until valid participant decisions exist. A character may nevertheless reserve their own time, prepare a surprise, turn up hoping to meet, or feel disappointed. Such acts are unilateral intentions with their own causes, not proof the other party consented. Appraisal can record subjective disappointment without declaring an objective breach by someone who never agreed. Do not invent private player beliefs: the player owns their interpretation and can correct others in dialogue.

An important ambiguous plan is an opportunity for drama or clarification, not an automatic engine prompt on every vague sentence. Characters can ask naturally, avoid asking, or confidently misunderstand according to policy. Later clarification updates beliefs and future actions while preserving the original exchange and already experienced consequences. Tests must distinguish intentional character misunderstanding from an extractor misclassifying a clear refusal.

### Real attendance

`CharacterSchedule` considers reservations, routine blocks, preparation and route time. Check interval overlap rather than exact due-time equality. `World.resolve_travel()` checks access, routes, availability and movement capabilities.

Confirmation schedules preparation/departure/arrival events against the terms revision. A character can negotiate, cancel or arrive late if travel becomes impossible. Do not directly place them at a venue merely because the due time passed. Closed venues, sleeping participants and ambiguous destinations produce explicit pending/failure outcomes rather than silence.

Separate physical impossibility from a costly personal choice. A shift at work can be skipped if the character chooses and the story permits it; the engine records the conflicting obligation and later consequences. A locked route remains physically unavailable unless a real alternative action opens it. Prefer a plausible dramatic choice over a boring automatic schedule rejection: “My boss is gonna kill me if I ditch work to go on a date with you!” can accompany a genuine, character-owned decision.

`ActivityDefinition` holds prerequisites, roles, resources, duration, interruptibility and completion predicates. Coffee, rehearsal, a witness interview and a repair appointment use this same machinery with different data. Calls use a communication channel rather than physical co-location.

### Time and appraisal

One chronological queue merges routine boundaries, travel, appointments, contacts and world changes. Tie order uses documented priorities and stable IDs. Revalidate event preconditions at execution; cancellation invalidates queued work by agreement revision.

Long skips process intermediate boundaries. Interrupt for a configured player choice or important event, report the reached time and wait for the player's next action. NPC-only events may resolve offscreen. A work cap checkpoints and resumes internally; it must not drop obligations or falsely claim the skip completed.

### Skip preview and parenthesized engine communication

Before any player-requested time advance (skip, sleep or a long activity) would pass an important known event or its latest feasible departure time, `SkipPreview` gathers the affected player-visible obligations and relevant tentative plans. Importance is policy-driven by player involvement, deadline and likely consequence. Include all affected events in one readable confirmation, with tentative events clearly identified. Hidden NPC plans must not appear as spoilers.

Example engine output: **(Skipping until tomorrow morning will miss your coffee with Yuki at 10 AM and your rehearsal with Mako at 3 PM. Continue?)** The player can answer **(Yes, skip anyway.)** or **(No, stop before coffee.)** No elapsed-time mutation, NPC progression or random draws occur while awaiting confirmation. This is a preflight read of known state, not a simulation of secret future outcomes.

Use typed `EngineInteraction` segments for reminders, confirmation, control instructions and errors; render their player-facing text in parentheses. Parse explicit parenthesized player-to-engine instructions into the engine channel. These exchanges do not become character utterances, observations, gossip or dialogue obligations. Ordinary parenthetical asides within an in-world sentence are not automatically commands: use the top-level interaction mode/recognized command intent, and clarify uncertain routing without advancing time. Support mixed input as separate engine and in-world segments with explicit order.

The confirmation binds session, requested interval, affected-event IDs/revisions and current world revision. A stale confirmation regenerates the preview. Duplicate confirmations advance once through the normal idempotent turn transaction. A bare in-world “yes” must not accidentally approve a pending skip. Declining leaves the clock unchanged and offers the requested shorter interval. Confirmation authorizes missing the listed events, not cancelling them: actual attendance/missed-plan consequences still execute. Do not immediately interrupt again for the same confirmed misses; a materially new event needing a player decision may still interrupt and use a new parenthesized prompt.

`RelationshipEdge.appraise()` consumes perceived outcome evidence, obligation importance, ability to comply, notice, explanation credibility and character values. Only the affected direction changes unless another actor independently appraises it. Apply once per event/actor/policy. Non-witnesses need a source path. Correcting a false rumor need not erase all emotional consequences.

## 7. Knowledge, testimony and investigations

### Extend the existing epistemic objects

`Proposition` gains subject IDs, predicate, typed value, polarity, valid-time interval and optional place; free text remains an attached gloss. Example: `entered(person_17, studio, interval_20_00_20_15)`. Natural-language equivalence is not established by identical words alone: uncertain mappings stay separate with a candidate-equivalence link pending evidence. “Not seen entering” is not equivalent to “did not enter.”

`Observation` references a committed event or entity surface revision, observer, channel, perceived details and observation time. `Assertion` references proposition, speaker, stance, utterance event and claimed source. `Transmission` records actual delivery, sender/recipient, parent and independent root source. `Belief` stores the owner's support/opposition references, confidence and unresolved alternatives. Confidence reflects evidence quality and source reliability; it is not proof of objective truth.

Use `EpistemicLedger.view_for(character_id)` as the character's only knowledge port. Adapt current `BeliefState`, memory store, session chunks and index retrieval to this writer. Memories are recall projections; assertions and observations are the evidence. A gossip loop repeating one root cannot count as three independent witnesses. A forged document can be a real observed document containing a false claim; reading it does not make its claim true.

### Truthful speech, mistakes and deliberate lies

`Character.plan_speech()` selects `disclose`, `uncertain`, `withhold`, `misremember` or `deceive` acts according to its knowledge and policies. Default factual assertions require support. A deliberate lie may lack truthful support, but requires an explicit decision tied to a motive and a perceived situation. An authored/seeded memory error references the remembered material and distortion, rather than manufacturing an arbitrary source after generation.

Store what was actually said separately from what the speaker claimed its source was. A permitted lie such as “you told me” must not create a fake historical player utterance or a fake observation. The hidden decision receipt can record deception intent; listeners only get what they heard. They can challenge the claim without the narrator revealing the lie. This preserves mystery and realistic dishonesty while preventing accidental hallucinations from becoming canon.

### Character-owned deception skill and readable hints

Compose `DeceptionProfile` and expressive behavior into the character: skill, composure, stress sensitivity, habitual tells and ability to maintain a story. Reuse existing authored `Character.tells` as cue material through a typed adapter. When a character chooses deception, `Character.express()` selects an observable cue from intent, pressure, familiarity and a recorded seeded draw. The default presentation generally gives the player a hint: a strained laugh, delayed answer, fidgeting or an inconsistent detail. Higher skill/composure reduces cue frequency or makes it subtler; pressure can expose a normally skilled liar.

The scene contract receives the approved visible behavior, not a flag saying “this character is lying.” Perception filters still apply: a phone call may expose a vocal hesitation but not a hidden hand gesture. Honest nervous characters can display similar cues, so body language is suggestive rather than a guaranteed lie detector. Tune hint availability for enjoyable play without requiring a tell in every line, and vary cues to avoid a repetitive “looks nervous” template. Character-owned humor may mask or reveal tension without changing the underlying assertion.

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

Default autonomy to `moderate`, with per-game and permitted character overrides. Progress is driven by elapsed simulated time and meaningful opportunities, not merely the number of player messages. Longer absences allow additional encounters and causal chains: an invitation changes a schedule, that encounter changes a belief, and that belief changes a later invitation. This is the intended butterfly effect. Small changes can diverge through accumulated decisions, but cannot randomly rewrite unrelated relationships or retroactively invent encounters.

Schedule reconsideration at relevant event boundaries with stable per-event random keys. Splitting an otherwise identical wait into smaller no-interaction steps should not create extra initiative opportunities solely because more turns occurred. Test that time partitioning preserves outcomes under unchanged information; actual player interactions may legitimately alter the chain. Event budgets bound computation, not simulated change: checkpoint rather than truncate. More time provides more opportunity, not a promise that drama grows monotonically or every relationship deteriorates. Only player-perceivable traces reach narration.

An offscreen action creates only actual perceptible traces and sourced reports. The scene selector can highlight a feasible consequence, but cannot invent a quarrel to hit an engagement target. A cancellation message is delivered through the same contact/knowledge channels as other communication.

### Drama-first opportunity selection

Add `DramaticPolicy` above opportunity/scene selection, composed with character policies. Rank plausible options by emotional stakes, tension, surprise, humor, meaningful player choice and payoff of earlier events; discount exhausted beats. Physical feasibility and information access are hard bounds, while schedule adherence, social caution and sensible behavior are negotiable character choices with consequences. Let characters make bad but understandable decisions.

Selection must not override willingness indirectly. Each character first generates an admissible set using its values, current goals, boundaries and a configured maximum deviation from its preferred choice. Include “continue current activity” or a quiet alternative when plausible. Only this set enters dramatic ranking; the director cannot keep regenerating candidates until it gets consent. Meaningful soft-obligation violations need an explicit motivation/cost record.

Use bounded, versioned score components for tension, humor, payoff, novelty and repetition. Repeated semantic beat families share a cooldown/penalty across paraphrases and templates, so wording changes cannot reset it. Reserve a configurable initiative budget and quiet/recovery opportunities; dramatic scoring does not monopolize every direct-answer turn. Precondition/target refusal is final for that decision point, not an invitation to reroll a different seed.

Deterministic selection: assign stable candidate IDs from actor, opportunity, causal event and ruleset version; clamp/quantize score components to specified integer ranges; sort by descending score, then a seeded hash of `(session_seed, decision_event_id, candidate_id, policy_version)`, then candidate ID. Persist the selected candidate and component scores. No wall time, iteration order or turn-count-only seed enters tie-breaking. Replay uses the recorded choice; resimulation uses the versioned formula. Permuting input candidates must not change the result.

Anti-railroading fixtures cover a cautious character refusing the highest-drama action, a contented character choosing quiet activity, repeated rejected proposals, paraphrased duplicate beats, and a strong humor/payoff option beating another argument. Inspect per-character action diversity and refusal rates over seeds. Dramatic weights cannot bypass these constraints even at their maximum permitted values.

Generate more than one plausible opportunity before ranking, so drama is not limited to embellishing an already dull outcome. Character values and independent participant decisions still govern execution; a dramatic score cannot coerce agreement, move someone impossibly or erase history. Favor heightened situations with traceable causes. Quiet or comic relief can earn a high score when it provides contrast or payoff, rather than maximizing conflict every turn. Narration realizes the selected event through character voice and situational humor.

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
| Dramatic selection | `DramaticPolicy`: tension, surprise, humor, emotional payoff and repetition weights | Default favors enjoyable plausible drama; optional neutral selection still respects causal constraints. |
| Skip reminders | `SkipPolicy`: important-event criteria, latest departure, tentative-plan inclusion | Confirmation before important known misses is the required default; disabling optional reminders must not silently bypass that contract. |
| Deception cues | Character `DeceptionProfile`: skill, composure, stress sensitivity, cue vocabulary; game hint strength | Default generally hints; skilled liars can hide cues. Disabling deceptive intents does not remove honest nervousness. |
| Misunderstanding | Character interpretation policy: ambiguity tolerance, optimism, clarification tendency | Tentative state and separate beliefs remain; setting misunderstanding rate to zero does not turn “maybe” into “yes.” |
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
    autonomy: moderate
    progression_basis: simulated_time_and_events
    max_unsolicited_acts_per_scene: 1
    target_cooldown_minutes: 180
  drama:
    priority: enjoyable_plausible_scenes
    humor: enabled
  skip:
    confirm_known_important_misses: true
    engine_channel_format: parentheses
  deception:
    cue_policy: generally_hint_character_skill_adjusted
  interpretation:
    allow_tentative_plans: true
    allow_asymmetric_expectations: true
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

### Release units, not an eight-phase prerequisite chain

The table below is an architectural dependency map, not a requirement to finish phases 1–3 before shipping. The program is too broad for one release. Every implementation change needs its own falsifiable behavior and hosted proof; creating fifteen empty classes is not a shippable milestone.

**First planned behavior-changing commit: correct the IU opening's malformed authored text (O12).** Reproduce the exact current data/rendering defect first, then repair `backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_story.json` and any demonstrated generic decoding defect at its owning boundary; preserve intentional escapes. Check raw segments and desktop/mobile rendering. Ship this isolated content fix with normal beta verification; no event migration, ruleset system or epistemic refactor is needed. This is the specified next implementation slice, not a commit created by this documentation task. If the defect no longer reproduces, document that evidence and skip the patch rather than changing correct content.

**First engine behavior slice: pending addressed responses (O08).** Add a small `ConversationState` component and owner-scoped `Character.response_context()` adapter using current character IDs, presence and prompt assembly. Capture question/addressee proposals in the existing extraction call, keep answer obligations across turns and render a safe relevant response when the addressed question would otherwise be omitted. The source/answer gate can operate on existing utterance observations; it does not require a rewritten ledger or full `Character.project()`. Verify a two-question exchange and an interrupted/resumed exchange on beta. This is a partial direct-answer improvement, not completion of arbitrary semantic validation.

**Phase 1 can ship independently as a reliability release.** Start with durable receipts plus session/outbox atomic commit using the current state shape; a complete event vocabulary for every old writer is not prerequisite to that transaction slice. Observable contract: after a lost HTTP response, retrying the same request returns the exact reply without another move, clock charge or NPC action. Inject a failure after commit, retry through the API and verify one stored effect and one visible turn. Later reducer migration is a separate release; do not label the whole authority phase complete after the receipt slice.

### Independent fallback tracks

O12 content correction, O09 narrow opening/agency repairs, O08 addressed-response tracking and O11 name/addressee continuity can ship through current objects without waiting for the general epistemic overhaul. Existing date work may ship its tested subset once actual hosted attendance is verified, with travel/misunderstanding limitations retained in BL-35. A blocked architecture milestone must not block these fixes.

Each narrow fix must identify its owning object/adapter, add meaningful regression evidence, and state remaining limitations. Do not introduce another authoritative store or declare a broad behavior solved by a phrase filter. The applicable feature backlog may close when all of its own criteria pass using either the old or new architecture; BL-38 is not a mandatory closure dependency. Full architecture acceptance still requires the shared-object contracts.

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

### Concrete migration and rollback drill (required before opting in old saves)

Use an isolated copy of a representative beta save, with identifiers sanitized and data kept outside git; never rehearse against the live session. Include the old two-party/one-due-time agreement model with one accepted future meeting, a tentative/player-only promise, a pending extraction job and the stored last-request reply. Add deterministic fixtures when live data does not cover each case.

1. Record old build/schema/content versions, snapshot checksum, current time, participant decisions, pending work and last receipt. Freeze the original copy as read-only backup.
2. Load it through the phase-1 compatible writer; advance one ordinary turn and retry it. Confirm one effect and unchanged pending obligations. Save this as the migration input, not an earlier stale snapshot.
3. Migrate to the phase-2 character/context representation. Assert no consent, venue or knowledge was invented; replay the stored reply, advance to the meeting and verify expected attendance/remaining unknowns. Restart the server and repeat reads.
4. Inject failures before writing migration output, after writing a checkpoint and before publishing the new schema marker. Recovery must select a complete consistent version, never mix old decisions with new components.
5. Roll back **before any new-schema turn** by restoring the exact migration input under the old compatible writer; verify its checksum and pending work. Re-run migration to prove idempotency.
6. Roll back **after a new-schema turn** by routing that save to the retained compatible newer writer. An old writer must reject it, not silently strip fields. If a tested lossless downgrade exists, run it and assert all new committed actions/receipts survive; otherwise explicitly report downgrade unsupported. Never restore the pre-migration backup and discard player progress as an automatic rollback.
7. Repeat with arrival already committed, cancellation pending, same request retried during cutover, and overlapping workers. Assert one writer/version per session, no duplicate outbox effects, no lost replies, and no second arrival.

Passing means all state/receipt assertions and restart checks pass, with a saved drill report. Run this on an isolated beta rehearsal deployment before real old-session opt-in. Production remains subject to an explicit release request; this proposal does not authorize migration of live production sessions. A schema downgrade that cannot preserve progress is not a passing rollback drill.

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
| O19 | Plausible drama and humor — owner decision | Given a work/date conflict, a character may choose a plausible dramatic exception with downstream costs; a comic line cannot silently cancel work, force consent or create an impossible route. Human review compares scene enjoyment, not just schedule compliance. |
| O20 | Skip preview and engine channel — owner decision | Multiple known important events trigger one parenthesized preview before time changes; tentative plans are labeled; hidden events do not leak; parenthesized control messages never enter NPC memory. Decline changes no time, stale tokens refresh, duplicate confirmation advances once, ordinary dialogue does not approve a skip. |
| O21 | Moderate autonomy and butterfly effects — owner decision | Longer simulated absences enable causal multi-step changes; equivalent partitioned waits preserve opportunity scheduling; changed player input can diverge outcomes; app-closed wall time does nothing. High/low tuning changes initiative within valid constraints. |
| O22 | Skill-dependent deception hints — owner decision | Low/high skill and pressure change cue distributions over fixed-seed fixtures; generally informative hints remain nonconclusive; honest nervousness is possible; unavailable visual cues never appear on voice-only calls. |
| O23 | Real misunderstandings — owner decision | One actor expects a meeting after “maybe” while the other's recorded decision remains tentative; voluntary hopeful attendance is allowed; disappointment is subjective, not a false breach or player-consent event. Clarification updates beliefs without rewriting the exchange. |
| O24 | Standalone release progress — review Q1/Q7 | O12 ships without new engine types; addressed-response tracking works through current adapters; a lost-response/retry transaction slice shows one effect without waiting for the full reducer or ledger migration. |
| O25 | Actual inference budget — review Q3 | Six characters/two objectives remain within three logical calls and four total attempts under the proposed default profile; explicit previews/replayed receipts make zero calls. Optional and background paths are accounted for or disabled; timeout fallbacks never exceed the shared cap. |
| O26 | Source/answer verifier calibration — review Q4 | Labeled questions, denials, paraphrases, omitted answers and explicit deceptive acts produce the expected verdict/fallback; corrupted/missing/truncated evidence cannot justify an attribution; report false accepts/rejects/abstentions. |
| O27 | Dramatic selection determinism — review Q5 | Candidate-order permutation preserves choice, refusal is not rerolled, quiet in-character choices remain admissible, and paraphrased duplicate beats share cooldowns. |
| O28 | Old-save cutover/rollback — review Q6 | Complete the section 12 isolated old-save drill before old-session opt-in, including pending agreements/jobs, crashes, concurrent requests, pre-turn rollback and post-turn compatible routing without lost progress. |

### Deterministic and model-level checks

Use state-machine/property tests for agreement transitions, temporal ordering, one-writer invariants, idempotency, containment and source graphs. Metamorphic tests vary an irrelevant secret, character name, story ID or voice while preserving equivalent mechanics. A new story name must not alter domain behavior. A different voice must not change consent.

Use fixed scripted provider outputs for deterministic integration tests and a separately budgeted real-model corpus for ambiguity, paraphrase, contextual refusals, unknown identity, multi-intent commands and player-agency violations. Test mechanical correctness and prose entailment independently. One passing generated response is focused evidence, not a universal fix.

Track direct-response completion, unsupported source claims, agency violations, attendance outcomes, repeated imagery, answer length, character distinction, NPC opportunity distribution and choice consequences. Denominators matter: an honest refusal is a completed response, an unanswered invitation is not a failed attendance, and unavailable evidence is not necessarily a progression bug. Record error examples rather than only aggregate scores.

Use blinded length-controlled comparisons plus human play review for engagement. Never accept a mechanically invalid run because a judge prefers its prose. Hard invariant fixtures require zero failures; qualitative improvements require a documented baseline/candidate comparison without regressions in logical consistency. Do not invent a universal numerical engagement threshold before calibration.

### Enjoyment grading without silently enabling arena runs

Keep `ARENA_LLM_ENABLED` off. The [promotion skill](../../.claude/skills/promote-to-prod/SKILL.md) explicitly says, “Don't set it on your own: ask the user first, every time.” This includes local/precheck arena commands, not only paid cloud judges. Runtime semantic validation is a different component, but adding it still requires its own implementation/cost measurements; it must not be mislabeled as a free deterministic check.

Iteration has two tracks. Deterministic fixtures and existing recorded transcripts provide rapid regression checks for meaningful choices, answered questions, causal consequences, repeated beats and invalid behavior. Those are quality proxies, not a measurement of enjoyment. For each dramatic-policy release, prepare a small blinded baseline/candidate packet: invitation versus work, an honest refusal, a lie under pressure, a tentative-plan misunderstanding and a quiet/comic payoff. Match setup and reading length, randomize order, and record preference/tie plus reasons for plausibility, character consistency, humor and desire to continue.

Agent play review is useful but must be labeled as agent judgment, not independent user validation. The user's ratings calibrate whether drama weights deliver the intended experience. Batch review at behavior milestones instead of asking for review after each refactor; reuse recorded baseline cases and cached deterministic fixtures between reviews. If review is unavailable, mark enjoyment unvalidated, keep new dramatic policies opt-in on beta, and continue independent correctness releases. There is no honest fully automatic substitute established by this document.

A separately approved, cost-capped judging pilot could accelerate comparisons after calibration against user ratings, but it is neither enabled nor assumed. The preferred review mode and response-time target were asked of the user during this revision; pending answers are recorded in section 15. No arena/model experiments ran as part of this documentation task.

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

## 15. Review questions and answers — 2026-09-27

The supplied review refers to BL-38/BL-39. Only BL-38 exists in this checkout at review time; these answers update that document. “Answered” below means the design decision is specified, not that its implementation or performance has been verified. Two user preferences remain pending; no missing empirical result is filled in with an invented answer.

### Q1. How is phase 1 independently shippable, and what is the first commit that changes hosted behavior?

**Answer:** The earlier table did not define sufficiently small release units. Section 12 now separates them. The first planned visible fix is O12: reproduce and correct the IU authored opening/rendering defect, then deploy and inspect it. It needs no new object graph. The first engine behavior slice adds addressed-response tracking through existing character/prompt adapters. Phase 1 itself can independently ship durable request receipts and atomic session/outbox commit: a lost-response retry must return the same reply with no second clock charge or movement. Full reducer migration is a later release. These are prospective commits, not work already implemented in this documentation task.

### Q2. Are presets merely story-specific branching moved into YAML?

**Answer:** The precise promise is no executable rule branching on story identity, not genre-independent content. A mystery preset is allowed to author investigation capabilities and omit courtship templates. It expands into ordinary typed fields; runtime objects cannot inspect the preset name or switch implementations by it. No general-purpose rules DSL is needed initially. Section 1 and O16 require renaming and cross-preset equivalence tests, which would catch identity coupling rather than merely checking that code lacks a literal story-ID comparison.

### Q3. How many model calls does a six-character turn with two pending objectives and a skip preview cost?

**Answer:** The new proposed default is zero calls for an explicit skip preview; one interpretation call if natural-language intent is ambiguous. A normal/resumed gameplay turn uses at most three logical calls: shared intent extraction, public realization and semantic verification. Allow at most four total provider attempts including a single shared transport retry. NPC count/objectives do not multiply calls: character decision, projection and dramatic scoring methods run locally on typed inputs. The preview pauses before the gameplay calls; confirmed execution is a separate request with the same gameplay cap.

Current code does not enforce that budget: inspection found optional context selection, attribution, regeneration, translation and background extraction. Section 5 requires accounting for or replacing/disabling these in the new profile. This call budget is an engineering proposal, not a measured cost or latency claim. **User answer pending:** preferred ordinary-response target (asked: usually within 10 seconds, within 20 seconds, or up to 30 seconds for quality). Measure p50/p95 against that target before declaring viability.

### Q4. What exactly validates attribution and answers rather than hand-waving semantic correctness?

**Answer:** Section 5 now specifies `SpeechGroundingValidator`: response obligations and annotated speech plans, deterministic reference/perspective/polarity checks, then one bounded semantic comparison against exact allowed source text. Its outputs are supported/contradicted/unknown with spans, including checks for unannotated claims and missing answers. Unknown/failure cannot pass a consequential attribution. Use an approved relevant fallback or keep the obligation pending; do not repeatedly regenerate until a judge accepts it. Explicit character lies remain claims, never fake historical sources.

This is a concrete testable first design, not a proof that arbitrary-language semantics is solved. The verifier requires a labeled adversarial corpus and false-accept/reject measurements. Until calibrated, consequential source claims use constrained approved wording. The current word-overlap filter and 240-character utterance truncation are insufficient as the sole evidence mechanism. O26 now makes that gap testable.

### Q5. How does dramatic scoring break ties reproducibly and avoid railroading character choices?

**Answer:** Section 8 now makes each character's admissible choice set precede dramatic scoring. Values, boundaries, motive and limited preference deviation constrain that set; the director cannot reroll a refusal. Rank bounded integer score components, break ties with a versioned seed keyed to the stable decision/candidate IDs, then stable ID order. Persist the selected outcome and score breakdown. Repeated semantic beat families share penalties/cooldowns, including paraphrases. Quiet/comic payoff remains a candidate. O27 tests input-order independence and maximum-drama settings that still respect character refusal.

Exact score weights are uncalibrated tuning values, not established facts. The user's drama-first direction determines the objective; play review determines whether a particular weighting succeeds.

### Q6. Where is the actual old-session migration and rollback drill?

**Answer:** Section 12 now defines one using an isolated representative beta save plus deterministic fixtures: old two-party agreement, player-only/tentative promise, pending extraction job and stored retry reply. Exercise a phase-1 turn/retry, migrate to phase 2, restart, progress to the meeting, inject cutover failures and test duplicate requests. Before new-schema play, restore the exact migration input. After new-schema play, retain a compatible newer writer or demonstrate a lossless downgrade; an old writer must reject unsupported saves. Restoring an earlier backup and losing player progress is not a valid automatic rollback. O28 requires a drill report before old-session opt-in. No live beta/production migration has run for this documentation task.

### Q7. Can narrow fixes ship if the ledger or Character.project refactor stalls?

**Answer:** Yes. Section 12 now explicitly allows O12 text repair, O08 response tracking, O09 narrow agency fixes and O11 identity continuity through existing objects/adapters. They do not depend on completing BL-38. The attendance work can ship its independently verified subset while remaining limitations stay in BL-35. A feature backlog closes on its own complete behavior/verification criteria, not on adoption of the new architecture. Adapters must avoid new competing writers and clearly label partial fixes.

### Q8. How is enjoyment graded without silently enabling LLM-arena judging, and does human review block everything?

**Answer:** Section 13 separates correctness proxies from actual enjoyment. Deterministic fixtures and recorded-transcript checks support rapid iteration; they cannot prove a scene is fun. Use small blinded baseline/candidate packets at dramatic-behavior milestones, with user preference/reasons for plausibility, consistency, humor and desire to continue. Agent play review is labeled as such. If user review is unavailable, keep enjoyment unvalidated and dramatic-policy changes opt-in on beta; independent correctness fixes can still ship. Do not claim an automatic enjoyment evaluator exists.

The existing promotion skill requires asking before every arena enablement, including local arena commands. No arena run was enabled. **User answer pending:** keep LLM-arena judging off and use playtest review, or plan a separately approved, cost-capped judging pilot. Planning a pilot is not permission to execute it; an eventual pilot needs concrete scope/cost and explicit run authorization. No latency benchmark, validator accuracy or enjoyment result is claimed by this proposal.
