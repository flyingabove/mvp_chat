# Social engine v2: causality, knowledge, and consequential relationships

Status: engineering target with an initial implementation in progress, 2026-09-26. Section 18 records implemented slices and remaining acceptance gaps. Scope: a reusable engine for Terrace and other social stories, with epistemic infrastructure reusable by IU. No four-week deadline is enabled by this proposal.

## 1. Architectural decision

Refactor the existing world model incrementally. Keep its deterministic world, routines, cast lifecycle, graph, persistence, and retrieval infrastructure. Introduce typed domain operations and one authoritative commit boundary. Do not build a second simulator or turn every resident into a separate autonomous LLM agent.

The central contract is: **an utterance is an event; its content is a claim, not automatically a fact.** NPC actions use their own information. World feasibility uses actual state. The drama selector controls which feasible opportunity receives attention, not what becomes true.

## 2. Current code and gaps

Code inspected on beta for this proposal:

| Existing code | Reuse / change |
|---|---|
| `world_model/events.py::Event` | Frozen event currently carries free-text `truth`, participants, visibility. Add typed payloads, causal links, turn/operation identity and revision. Text becomes a presentation field. |
| `world_model/memory.py::MemoryStore` | Owner-scoped recall and references are useful. Memories must become derived recall of observations/claims; they must not own agreement state. |
| `world_model/gossip.py::share_memory` | Currently copies recent shareable text, rewrites first-person pronouns, multiplies confidence by 0.8, and skips known event IDs. Replace with explicit transmissions and proposition-level support. Hearing another account of a known event can matter. |
| `world_model/commitments.py` | Currently paired promise memories, inferred due minute, twelve-hour expiry, separate status mutations. Replace with one agreement object, participant decisions and per-obligation outcomes. |
| `world_model/turn.py::begin_turn/end_turn` | Retain API facade; split command resolution, event application, observation, planning and projection. Remove authoritative mutation from view construction. |
| `engine/extractors/turn_extractor.py::CommitmentUpdate` and `api/prompt_engine.py` | Previous-exchange extraction is useful as a compatibility adapter. New gameplay-critical operations need same-turn validation, evidence spans and idempotency. |
| `world_model/stepper.py`, `offscreen.py`, `threads.py`, `contact.py` | Reuse temporal boundaries and encounter eligibility. Convert effects to proposed commands/events; prevent bypass writes. |
| `BeliefState`, knowledge-resolution updates, session retrieval and world memories | Reconcile through one epistemic service; do not create a third independent truth/knowledge writer. |

Some older social-design limitations predate the world model. This proposal uses the inspected implementation rather than assuming schedules, NPC relationships or commitments are entirely absent.

## 3. State contracts

All IDs below are scoped by game instance; names are presentation only. Records carry schema version. Durable history lives in storage; bounded objects/graphs and derived retrieval caches remain in memory, following the existing epistemic storage policy.

### World events and proposals

`ActionProposal(id, actor, kind, arguments, source_turn, evidence_spans, expected_revision)` describes an attempted action. It grants no authority by itself.

`DomainEvent(id, sequence, turn_id, operation_id, minute, kind, actor_ids, place_id, payload, cause_ids)` describes a validated occurrence. Examples: `InvitationProposed`, `InvitationAccepted`, `AttendanceRecorded`, `UtteranceDelivered`, `MessageRead`, `RelationshipDecision`, `DepartureCommitted`.

Reducers apply each event exactly once. IDs derive from session/turn/operation, not a global counter or unstable model ordering. Corrections append superseding events; they do not rewrite witnessed history. Mechanical outcomes replay from accepted events; reproducing the original prose or model inference is not required for replay.

### Epistemic objects and edges

* `Proposition(id, subject, predicate, value, valid_time, qualifiers)` represents a claimable statement. Negation and temporal scope are explicit. Not every proposition has a known truth value.
* `Observation(id, observer, event_id, channel, perceived_details, minute)` records what was perceivable, not everything in the event. Seeing two people leave together does not establish a date.
* `Assertion(id, speaker, proposition_id, stance, utterance_event_id)` records what someone asserted. Stance can affirm, deny, hedge, or quote.
* `Transmission(id, assertion_id, sender, recipients, channel, delivery_event_id, parent_transmission_id, disclosed_source)` records how information travels. Engine provenance is separate from the source the speaker claims.
* `BeliefEdge(owner, proposition_id, stance, confidence, support_ids, opposing_ids, revised_at)` records a character's current assessment. Confidence is their certainty, not an omniscient truth probability.
* `DisclosurePolicy(content_id, owner, permitted_audience, secrecy_commitment_id, classification)` separates protected content from ordinary fictional secrets.

Private confessionals/system material are never eligible for NPC transmission. A fictional secret may be disclosed by a character who knows it and chooses to betray confidence. Do not reinterpret the existing `private` boolean as leakable during migration; ambiguous legacy content stays protected.

The service API is `observe`, `assert_claim`, `transmit`, `revise_belief`, `perspective`, `can_disclose`. No retrieval result may directly call a canonical-truth setter. Unknown authored knowledge defaults to unavailable for consequential claims unless an explicit acquisition path or authored knowledge permission exists; inferred prior dialogue is testimony, not proof of acquisition.

### Agreements, relationships and intentions

`Agreement(id, proposer, participants, activity, place, time_window, participant_decisions, status, obligations, source_event_ids, supersedes)` is authoritative. States: proposed, accepted, declined, cancelled, completed, breached, expired. Rescheduling creates a revised proposal requiring affected parties to accept. Partial attendance resolves individual obligations rather than marking every participant guilty.

Unspecified dates remain tentative windows. "Sometime this week" must not silently become a precise appointment. A proposal reserves no exclusive slot; acceptance checks schedules and travel. Intentional double-booking is allowed as a recorded conflict, never silently repaired. Breach requires a specific due obligation and evidence; co-presence alone does not prove a cooking lesson occurred.

Relationship graph edges remain directional. Keep trust/affection; introduce attraction only where enabled, and represent compatibility through supported preference matches/conflicts rather than an arbitrary accumulating score. Attachment and jealousy can be derived appraisals initially. Exclusivity is a bilateral agreement, not a high numeric edge. NPC-to-player feelings cannot be inferred from player-to-NPC affection. Repeated equivalent compliments have bounded effects.

`Intention(owner, objective, target, priority, prerequisites, deadline, status)` supports romance, work, friendship and independence. `ConflictThread(id, participants, cause_ids, stakes, stage, unresolved_questions, cooldown, resolution_ids)` links drama to history. Neither record may expose hidden motives in player UI.

## 4. Turn transaction and narration

1. Load snapshot revision and acquire per-session serialization or optimistic revision control. Deduplicate client request ID.
2. Interpret player input into typed proposals, distinguishing speech, questions, hypotheticals, attempted actions and explicit decisions. Ambiguous consequential intent produces clarification, not a guessed commitment.
3. Validate against current state; resolve elapsed time and movement through one clock API. Process due events chronologically, including travel, routines and agreements. If a significant interruption occurs, stop an optional time skip at the decision point and report the actual elapsed interval.
4. Generate observations from actual presence, hearing, line of sight or delivered communication. Apply belief revision and event-triggered relationship appraisal.
5. Generate a bounded set of NPC proposals from local intentions and belief slices. Validate physical feasibility against world state. An NPC may attempt a plan based on a false belief; the world can reject the attempt without silently telling the NPC hidden truth.
6. Select a scene opportunity from eligible proposals/conflicts. Reserve any invitations or other semantic outcomes the response will express in a tentative batch.
7. Build a scene contract: actual clock/location, approved actions, mandatory consequences, selected speakers, each speaker's permitted evidence, and player-visible facts. Generate structured dialogue/narration consistent with it. Speech acts such as accepting, declining or disclosing reference approved proposal/claim IDs.
8. Validate speaker, knowledge, action and speech-act references. Reject unsupported new consequential facts. Allow a bounded repair; if that fails use a grounded fallback without extra actions. Never present a rejected draft as established history.
9. Atomically commit accepted events, state revision and the final response record; return that response. On retry return the stored response. Publish analytics/retrieval indexing through an idempotent outbox after commit.

This is a target pipeline, not an assumption that arbitrary prose can be perfectly verified. Typed operations provide hard guarantees; unsupported paraphrase/inference remains a model risk measured by adversarial evaluation. Start by buffering consequential scenes before display; cosmetic streaming may follow later. Avoid announcing an accepted date before its transaction can succeed.

No database lock should be held across a model call: prepare against a revision, then compare-and-swap at commit; concurrent changes force bounded re-planning. Failed generation leaves the tentative batch uncommitted. The accepted event batch and response must share the same durable transaction boundary.

## 5. Gossip example and non-negotiable invariants

Illustrative fictional game scene, not a claim about the real cast:

1. At 18:00, Arisa and the player leave for a concert. Yuki sees them leave but does not hear their plans.
2. Yuki forms a low-confidence inference: "They may be on a date." This is a separate proposition from the observation.
3. Yuki tells Minori, "I think they went on a date." Minori gains testimony with Yuki as source. She does not gain knowledge of the concert, an exclusivity agreement, or the player's intentions.
4. Minori repeats it to another resident, who repeats it back. The root support is still Yuki's single observation. Three repetitions are not three independent witnesses.
5. The player explains the concert. That explanation is another assertion. A ticket or a second direct observation may corroborate part of it. None proves the absence of romantic interest.
6. Minori may remain hurt by a broken cooking promise even if the dating rumor is disproved. Factual revision does not erase emotional history.

Mandatory rules:

* Hearing an assertion proves it was said, not that it is true.
* Absence of knowledge is neither disbelief nor knowledge of negation.
* A lie, mistaken inference, disputed testimony and outdated fact are distinct.
* Recirculation retains root provenance; copied testimony cannot manufacture corroboration.
* Belief updates consider source reliability, directness, ambiguity and independent support. Do not globally multiply certainty by 0.8 per hop or use truth to secretly correct everyone's beliefs.
* NPCs may believe mutually inconsistent claims; expose the uncertainty rather than forcing a premature winner.
* Assertions about past and present relationships need temporal scope; changed circumstances are not automatically lies.
* A message is not learned when queued; it must be delivered/read according to channel policy.
* Public events are observable to eligible witnesses, not telepathically broadcast to all residents.
* Private speaker context cannot leak through a shared narrator prompt. A scene-wide renderer receives only player-visible facts and approved dialogue acts. Sensitive NPC planning uses separate bounded views; it may require an isolated generation call for that speaker.

## 6. NPC initiative and drama selection

Use a small action library: invite, accept, decline, keep/cancel a commitment, ask, disclose, conceal, confront, apologize, withdraw, pursue a personal milestone. Each action declares preconditions, knowledge requirements, duration, effects, visibility and cooldown. Story data supplies preferences and boundary weights; no Terrace names in engine branches.

Candidate utility combines personal-goal progress, expected social benefit, obligation pressure, risk and effort. The NPC estimates social outcomes using its beliefs, not the full relationship graph. Preferences and risk tolerance create different rival behavior. Seeded bounded randomness breaks ties; record selected candidates and reasons for replay.

The drama selector ranks only feasible candidates using unresolved stakes, urgency, player relevance, novelty and time since last focus. It cannot create evidence, alter affection, force agreement, or teleport witnesses. Start with at most one major complication per scene, configurable cooldowns, and quiet/payoff scenes after escalation. Mandatory consequences outrank drama pacing. Rejection must remain possible; repair must remain possible; success need not trigger immediate sabotage.

## 7. Scalability and observability

* Index observations/claims by owner, proposition, root source and time; agreements by participant and due boundary; conflicts by participants and status.
* Process a priority queue of due boundaries rather than every simulated minute. Generate encounter candidates from co-location and active intentions rather than all character pairs.
* For long skips, coalesce uneventful routine intervals but retain ordering for causal events. Bound work and resume internally at a checkpoint; never silently discard due obligations to satisfy a cap.
* Keep active residents and relevant unresolved threads hot. Archive departed residents while preserving references, provenance and unresolved obligations.
* Batch semantic extraction and narration where views permit it. No per-resident LLM call every turn. Use isolated calls only where sensitive perspective decisions require them; measure cost and latency before expanding.
* Maintain bounded perspective retrieval. Filter authorization before ranking and again before rendering. Summaries preserve claim/source IDs and uncertainty; they cannot turn rumor into fact.
* Record debug receipts: proposed/rejected actions with reason codes, event IDs, actual time interval, witnesses, belief changes, source chains, relationship causes, scene selection and state revision. Private debug access stays separate from the player API.
* Measure p50/p95 latency, model calls/tokens, snapshot size, active-claim count, event queue work and retrieval latency across 6/30/100-character fixtures. These are test sizes, not performance promises.

## 8. Package boundaries and rollout

Keep `world_model/turn.py` as a facade. Introduce pure modules gradually: `commands.py` (schemas/validation), `reducer.py` (event application), `epistemics.py` (claim/observation graph service), `agreements.py` (state machines), `intentions.py` (candidate generation), `appraisal.py` (caused relationship changes), `drama.py` (selection only), `scene_contract.py` (perspective projection). Put durable transaction/outbox handling at the existing service/persistence boundary, not inside pure world-model functions.

1. **Authority and receipts:** versioned proposals/events, idempotency, one clock, read-only projection, causal audit. Existing behavior remains behind adapters. Gates: retry/concurrent-turn tests and save/resume replay.
2. **Epistemic spine:** observation/assertion/transmission separation and owner-filtered views. Start with conversation and gossip. Gates: secrecy, false rumor, circular corroboration, disjoint perspectives. Benefits IU testimony immediately.
3. **Agreements and calendar:** replace paired promise ownership; validate attendance, reschedules, conflicts and time skips. Gates: cooking promise versus concert across save/resume; no automatic acceptance or fulfillment.
4. **NPC intentions and appraisal:** directional attraction/trust, autonomous invitations and distinct rival policies. Gates: equal opportunity across rosters, independently motivated actions, no privileged knowledge in planning.
5. **Conflict pacing and endings:** escalation/repair linked to causes; bilateral relationship/departure state machine. Gates: explicit mutual decisions, current eligibility, atomic cast changes, rejection and solo endings.

Roll out per capability and per story, pinned to session schema/ruleset version. New sessions opt in first. Migration converts unambiguous legacy promises to tentative agreements, preserves uncertain provenance as legacy/unknown, and never retroactively grants secret knowledge. Use one canonical writer with read adapters rather than long-lived dual writes. Shadow planning can compare candidate actions without applying them. A v2 save must not be loaded by a v1 writer; rollback routes compatible sessions or performs an explicit tested downgrade, never just toggles a flag.

## 9. Proof, not only prose quality

Deterministic/property tests cover event idempotency, revision conflict, time monotonicity, participant-specific obligations, missing witnesses, delivery, source loops, schema migration and replay hashes. Metamorphic tests remove a witness or change an unrelated secret and assert that an uninformed NPC's available knowledge/planning input does not change. Model-level tests separately measure whether generated dialogue respects those views.

Scenario replays cover: rejected date; rival invitation while player is away; intentional double-booking; honest cancellation; lie discovered through a real witness; rumor disproved but trust still damaged; reconciliation; mutually agreed departure; cast replacement; interruption during a long skip. Run the same seeds over both player-gender paths and varied active rosters. IU gets a testimony contradiction and false-date-evidence fixture.

Engagement evaluation uses blinded equal-length comparisons plus human review: meaningful choices, differentiated NPC aims, consequences recalled, conflict resolution, repetitive filler and agency violations. More arguments or longer replies are not success metrics. Mechanical invariants gate release even when an engagement judge prefers the broken version.

## 10. Backlog mapping

Existing [BL-30](../backlog/BL-30-live-narrative-clock-divergence.md), [BL-31](../backlog/BL-31-named-npcs-unknown-speaker-empty-presence.md), [BL-33](../backlog/BL-33-terrace-relationship-goal-and-ending.md), [BL-34](../backlog/BL-34-terrace-rivals-with-independent-aims.md), [BL-35](../backlog/BL-35-commitment-knowledge-and-relationship-followthrough.md), [BL-36](../backlog/BL-36-iu-evidence-ledger-and-source-checks.md), and [BL-37](../backlog/BL-37-social-and-mystery-reply-pacing.md) retain their scopes. The cross-cutting transaction and epistemic work is tracked in BL-38. Implement slices with regression evidence; this design does not close those items.

## 11. Implementation sequence and shared release contract

Implement **Phase 1 first**, including its scenario harness. Follow 1 → 2 → 3 → 4 → 5. Phase 5 has separate pacing and ending gates so one cannot conceal a failure in the other. These expand the five phases in §8; they are not additional competing roadmaps. Each phase must deliver a usable vertical slice through state, persistence, projection and hosted behavior before the next phase depends on it. All phases below are planned, not completed.

Every phase uses three layers of proof:

1. **Deterministic domain scenarios:** explicit starting state, commands, clock advances and expected event/state assertions. No model required; failures must reproduce from a fixture and seed.
2. **Integration and model scenarios:** the real turn pipeline, extraction, persistence and prompt projection. Record structured proposals and actual replies. A deterministic test cannot establish that the model obeys a knowledge boundary.
3. **Hosted beta acceptance:** verify the deployed commit, exercise the relevant scenario in the real UI/API, inspect the response and authorized debug receipts, save/reload, and repeat the consequential action. A mocked response or successful health check does not prove gameplay.

Store reusable fixtures and expected invariants in the repository's existing test layout, with a scenario ID, story/ruleset version, initial state, seed, inputs, checkpoints and assertions. Store raw live transcripts/debug artifacts using the existing evidence policy, outside committed runtime data. Reports reference the artifact location and deployed SHA. Expectations assert meaning and IDs, not exact generated wording.

Common exit requirements: required scenarios pass; no unexplained critical invariant failures; existing relevant regression tests and required repository checks pass; migration/retry tests pass; hosted proof exists for the changed behavior. An attractive transcript cannot override a mechanical failure. Record any deferred scope in its existing backlog item and do not label the whole phase complete if a required gate is missing.

For stochastic behavior, use a fixed declared seed matrix and paired baseline/candidate runs, reporting all outcomes rather than rerolling until success. Pin acceptance thresholds before reviewing candidate results. Hard invariants require zero violations in the test matrix; this is evidence within that matrix, not a claim of universal correctness. Engagement scores are secondary evidence with sample size and uncertainty reported.

## 12. Phase 1 — Authoritative turns, clock and replay

**Direction:** establish one reliable path from an attempted action to a persisted event and displayed response. Do not add richer gossip or romantic behavior yet. Start with a small existing movement/speech action slice, then route existing consequential writers through the same contract.

**Deliverables:** typed proposal/event schemas; stable operation IDs; pure reducers; one clock mutation API; read-only view construction; response/state atomic commit; revision conflict handling; durable outbox; schema/ruleset versioning; debug receipts. Map every existing state writer and give it either the canonical path or an explicitly tested compatibility adapter. Add a reusable scenario runner that can stop/reload at checkpoints and compare normalized state/event hashes.

| Scenario | Setup and action | Required proof |
|---|---|---|
| P1-01 Retry after lost response | Commit one move, drop the network response, resend the same request ID. | Same stored reply; one movement event, one time charge and one revision transition. |
| P1-02 Concurrent turns | Two different requests plan against the same revision. | Serialize or explicitly re-plan/reject stale work; neither overwrites accepted state. |
| P1-03 Failure boundary | Inject failure before commit, during persistence and after commit before outbox delivery. | Before commit: no partial outcome. After commit: retry returns accepted response; outbox side effects occur once. |
| P1-04 Clock agreement | Walk, speak, sleep and skip across routine boundaries. | Events ordered by actual minute; scene header, presence and narration contract use the same resulting time. |
| P1-05 Read-only projection | Build the same view twice without applying a command. | No fulfilled promises, relationship changes, time movement or other state mutation. |
| P1-06 Resume/replay | Save midway, reload and apply the same accepted event sequence. | Same normalized world/relationship state; no repeated events. Exclude caches and presentation timestamps from hash comparison. |
| P1-07 Model repair | Draft contains an unauthorized action; force repair failure. | Grounded fallback, no rejected action committed or shown as completed. |
| P1-08 Legacy session | Load supported old saves and an unsupported future version. | Tested migration for supported data; explicit compatible routing/error for unsupported data, never silent destructive downgrade. |

**Hosted proof:** one normal action plus a same-request retry, followed by save/resume; compare response/event IDs and clock. Run fault injection locally, not against other users' hosted sessions. Smoke-test both Terrace and IU for ordinary dialogue/movement compatibility.

**Exit / handoff:** all consequential writes in the enabled slice have traceable accepted events; retries and view construction cannot change outcomes. Phase 2 can consume stable event IDs and delivery records. Owner: BL-38; clock behavior overlaps BL-30.

## 13. Phase 2 — Observations, testimony, beliefs and gossip

**Direction:** make knowledge acquisition explicit before NPC initiative becomes more powerful. Convert existing conversation/gossip paths to observations, assertions and transmissions. Reconcile BeliefState and MemoryStore through one writer and read adapters; do not retain two competing belief authorities.

**Deliverables:** proposition IDs with temporal scope; assertion/transmission ancestry; owner-filtered belief projection; uncertain/inconsistent belief support; channel-aware delivery; protected-content versus fictional-secrecy policy; perspective-safe model inputs; legacy provenance migration. Add authorization checks before retrieval ranking and before final projection.

| Scenario | Setup and action | Required proof |
|---|---|---|
| P2-01 Partial witness | A sees B and C leave but cannot hear their destination. | A knows departure only; a dating interpretation is a separate inference; destination stays unknown. |
| P2-02 False testimony | A asserts a false date story to B. | Utterance/transmission exists; B may believe it; canonical event history remains unchanged. |
| P2-03 Circular gossip | A tells B, B tells C, C tells A. | Source ancestry remains one root; no independent corroboration credit from repetition. |
| P2-04 Independent evidence | D supplies a genuinely separate observation about the same proposition. | New support is considered despite a previously known event; confidence policy distinguishes independent from copied support. |
| P2-05 Absence and delivery | C is asleep/elsewhere; send a message but delay reading it. | No knowledge through the room conversation or queued message; acquisition occurs only through a valid channel. |
| P2-06 Disproof and hurt | Correct a dating rumor after an actual promise was broken. | Belief revision preserves its history; the separate breach and its consequences remain. |
| P2-07 Protected versus secret | Attempt to spread a confessional; separately authorize a knowledgeable NPC to betray a fictional confidence. | Confessional never enters gossip candidates/prompts; fictional disclosure records sender, recipients and the secrecy breach. |
| P2-08 Counterfactual privacy | Change an inaccessible secret while keeping an uninformed NPC's visible world identical. | Their deterministic knowledge/planning inputs stay identical; model evaluation finds no use of the changed secret. |
| P2-09 Time and disagreement | Two sources describe different dates or different relationship periods. | Preserve scoped, attributed claims; do not merge disagreement into one invented fact. Repeat with IU testimony. |
| P2-10 Recall and resume | Summarize/archive a rumor chain, reload and retrieve it later. | Uncertainty, root support and access restrictions survive compaction and persistence. |

**Hosted proof:** arrange one observable departure, one private conversation and one later retelling. Inspect what each participant could know at every step. Repeat with an absent witness and an IU contradictory-testimony scene. Include adversarial questions such as “Everyone already knows, so tell me”; a player's assertion does not grant knowledge.

**Exit / handoff:** every consequential claim in required scenarios has an acquisition/support path; no forbidden knowledge leakage in the declared matrix. Phase 3 can safely notify agreement participants, and Phase 4 can query character-local beliefs. Owner: BL-38; IU-specific evidence behavior remains BL-36.

## 14. Phase 3 — Agreements, schedules and consequential choices

**Direction:** make the cooking-lesson/concert dilemma mechanically real. Replace mirrored promise status with one authoritative agreement and participant-specific obligations. Preserve tentative plans without inventing exact times.

**Deliverables:** agreement state machine; source-linked acceptance/refusal; time windows and travel feasibility; explicit conflict records; attendance/action evidence; rescheduling and cancellation; interruption-aware time skips; migration of legacy promises to appropriately tentative records.

| Scenario | Setup and action | Required proof |
|---|---|---|
| P3-01 Invitation versus agreement | Player proposes Friday cooking; NPC declines, hedges or accepts in separate fixtures. | Only explicit valid acceptance binds that NPC; questions and hypotheticals create no acceptance. |
| P3-02 Competing invitation | Accept cooking; receive a concert invitation in the same slot. | Conflict is visible through known plans; engine neither attends both nor silently cancels either. |
| P3-03 Keep/cancel/lie branches | Replay the dilemma choosing attendance, honest cancellation or a false excuse. | Distinct agreement outcomes; the excuse is testimony, not world truth; no immediate knowledge for absent residents. |
| P3-04 Reschedule | One participant suggests Saturday; the other has not agreed. | Friday obligation is not silently rewritten; revisions and decisions retain links. |
| P3-05 Ambiguous time | “Sometime this week,” “after work,” and a precise Friday time. | Uncertain windows remain explicit; precise commitments resolve against the game clock, not arbitrary defaults. |
| P3-06 Fulfillment evidence | Stand in the kitchen without cooking, then actually perform the agreed lesson. | Co-presence alone does not complete the activity; validated performance does. |
| P3-07 Partial group attendance | Three participants accept; two attend and one misses. | Outcomes attach to the relevant obligations; attendees are not all marked in breach. |
| P3-08 Skip and travel | Skip across a due appointment; separately accept two distant activities with insufficient travel time. | Significant choice interrupts optional skip; chronology and travel conflicts are preserved; no dropped due obligations. |
| P3-09 Persistence and duplicate extraction | Reload immediately after acceptance; process the same extraction again. | One agreement, consistent status for all participants, no duplicate penalty. |

**Hosted proof:** play the cooking/concert dilemma through at least two branches from equivalent fixtures; save/reload after acceptance and inspect next-day follow-through. Include an NPC refusal. Confirm consequences in state and subsequent dialogue, not merely a one-turn mention.

**Exit / handoff:** proposals, accepted commitments and outcomes are distinguishable and durable; Phase 4 can pursue dates against real availability. Owner: BL-35, with BL-30 for time consistency.

## 15. Phase 4 — Independent NPC aims and relationship appraisal

**Direction:** make residents pursue their own lives and generate opposition without omniscience or universal hostility. Start with invite/decline/keep/cancel and a small personal-goal set; add richer action types only after those paths work.

**Deliverables:** bounded intention/action candidates; local-belief utility inputs; directional attraction/trust appraisal with event causes; preference/boundary configuration; seeded selection and receipts; diminishing repeated-action effects; active-cast filtering. Candidate ranking must not read hidden truth as though the actor knew it.

| Scenario | Setup and action | Required proof |
|---|---|---|
| P4-01 Active rival | Rival and player independently like the same person; rival has a feasible opportunity. | Seed matrix contains independently initiated invitations with valid causes; rejection is possible; no guaranteed affection gain. |
| P4-02 No overlapping interest | Rival prefers another person or a work goal. | No automatic sabotage triggered solely by shared gender. |
| P4-03 False belief | Rival wrongly believes the target is free or interested. | Attempt reflects that belief; actual constraints can reject it without granting hidden explanatory knowledge. |
| P4-04 Directionality | Player likes NPC; NPC distrusts player. | Player affection does not become reciprocal attraction or acceptance. |
| P4-05 Repetition exploit | Repeat equivalent praise ten times. | Bounded appraisal prevents unlimited relationship farming; distinct meaningful actions can still matter. |
| P4-06 Competing priorities | A date conflicts with an NPC's important work milestone. | Personality and priorities can produce refusal, negotiation or alternative timing with recorded reasons. |
| P4-07 Witnessed consequences | Reveal a breach to one NPC but not another. | Only informed characters appraise that information; later transmission can change the second character. |
| P4-08 Cast and identity variation | Swap genders/eligible roles, rotate a resident out, vary seeded rosters. | Generic policies work across variants; absent/queued residents do not act; role-equivalent fixtures behave equivalently under matching preferences. |

**Hosted proof:** observe a rival initiative over multiple turns and its later consequence, then run a contrasting fixture with no overlapping interest. Do not manufacture proof by choosing only favorable random seeds. Inspect why actions were selected and whether replies express the accepted state.

**Exit / handoff:** NPC actions are feasible, independently motivated and epistemically justified; relationship deltas are attributable and directional. Phase 5 receives real unresolved conflicts rather than invented drama. Owner: BL-34; relationship follow-through overlaps BL-35.

## 16. Phase 5 — Conflict arcs, pacing and validated endings

**Direction:** turn causal events into engaging scenes, then complete the relationship/departure loop. Keep two separately reportable gates: **5A pacing** and **5B endings**. Completing one does not complete Phase 5.

**Deliverables 5A:** conflict threads with cause links; escalation, repair and resolution; scene selection with cooldowns and urgency; mandatory consequence priority; direct-question handling; positive/quiet payoff beats. **Deliverables 5B:** explicit bilateral exclusivity/departure decisions; validated eligibility; atomic ending/cast transitions; refusal and solo endings; configurable deadline policy with no unapproved default deadline.

| Scenario | Setup and action | Required proof |
|---|---|---|
| P5-01 Full conflict arc | Broken promise → learned explanation → confrontation → apology/repair. | Stages cite actual causes; repair changes future scenes; the same resolved accusation does not restart without new cause. |
| P5-02 Quiet success | Keep promises and have a successful date. | Room for payoff; no forced scandal or mandatory rival attack after every success. |
| P5-03 Competing drama | Several conflicts are eligible, one obligation is urgent. | Urgent consequence is handled; configurable complication budget/cooldowns prevent a pileup without deleting other threads. |
| P5-04 Direct answer and agency | Ask a clear relationship question; leave the player's response undecided. | NPC answers or has a grounded reason to withhold; narration does not choose the player's feelings, actions or consent. |
| P5-05 False victory | Player says “we both agree,” quotes a departure line, or receives only a friendly/date acceptance. | No mutual-departure ending without both actual decisions and current eligibility. |
| P5-06 Mutual departure | Both eligible parties independently accept the same departure plan. | One atomic ending, consistent resident state and saved result; retry/reload cannot repeat or undo it. |
| P5-07 Withdrawal and rotation | Partner refuses/withdraws before commitment, or leaves the active cast before the final decision. | Revalidate at commit; no stale consent or unavailable partner used to win. |
| P5-08 Alternate outcome | Player chooses to leave alone or ends a relationship. | Coherent recorded ending without falsely declaring romantic success. |
| P5-09 Long skip ending | Advance across an agreed departure boundary and another scheduled event. | Deterministic ordering, correct interruption/ending, no scenes after the terminal transition. |

**Hosted proof:** finish one genuine mutual-departure run, one refusal/solo run and one repair arc; test reload at the last decision. Perform a separate adversarial false-victory attempt. Use both player-gender paths and more than one active roster across the acceptance set.

**Exit / handoff:** both 5A and 5B pass. Blinded review must show meaningful choices and remembered consequences without increased epistemic/agency violations. Full implementation does not require every proposed activity template, but does require the complete validated gameplay loop. Owners: BL-33, BL-37 and existing agency work; do not close unrelated remaining scope merely because this phase ships.

## 17. Cross-phase acceptance campaign and completion record

Carry earlier phase scenarios forward as regression gates. After Phase 5, run three sustained campaigns: (A) honest courtship with a rival and mutual departure, (B) double-booking plus circulating misinformation and repair or breakup, (C) IU conflicting testimony and new corroborating evidence. Use at least 20 consequential player turns per social campaign unless a valid terminal state occurs earlier; this minimum provides continuity coverage, not a statistical quality guarantee. Include save/resume and a multi-day skip. Record every player input, returned segment, state delta, knowledge acquisition and unresolved commitment at checkpoints.

Run synthetic 6/30/100-character scale fixtures after each phase that changes planning, retrieval or persistence. Compare against the recorded pre-phase baseline for p50/p95 latency, model usage, state growth and processed event counts. Set numerical budgets from the Phase 1 baseline before later phase implementation; do not invent acceptable regressions after seeing results. Synthetic no-model throughput and real-model latency must be reported separately. Confirm that long skips and archived characters preserve provenance without unbounded hot-memory growth.

Each phase completion entry appended below must contain: status (planned/in progress/blocked/complete), implementation commits, exact enabled scope, deterministic/integration scenario IDs and results, hosted SHA and artifact references, migration/rollback result, performance comparison, remaining backlog items, and the next permitted phase. A checked box without evidence is not a completion record. For a rollback, re-run the compatible-session routing scenario and preserve committed outcomes rather than loading newer saves into an older writer.

**Current status:** A cross-phase implementation is in progress. The initial implementation covers event IDs and cause links, durable request/reply persistence, observed speech and gossip provenance, canonical agreements, rival invitations, conflict focus, and explicit relationship/departure decisions. The entire acceptance campaign above has not passed; the numbered phases are not marked complete.

## 18. Cross-phase implementation record, 2026-09-26

The current change set adds an idempotent event adapter, a versioned world-model snapshot, and an epistemic ledger with observations, assertions, transmissions, and root sources. Gossip can retain the original source across relays, and a second independent account can remain distinct. Protected confessional content and unheard remote speech are excluded from ordinary housemate memory. The session save stores state and the exact reply under the same request ID; a retry can return that reply. This is a useful compatibility bridge, not a full event-replayed transaction: world operations still have multiple mutation paths, the JSONL side log is separate, and cross-worker optimistic concurrency is not implemented.

Plans now have canonical proposal/decision/status records while legacy promise memories act as projections. Due scenes do not automatically fulfill agreements; accepted plans can expire, and completed actions require direct player performance. NPC testimony alone is insufficient. Rival invitations and a conflict focus are bounded and deterministic. The romance path records independently stated relationship and departure choices, validates the eligible present cast, supports withdrawal and solo departure, and bases victory on saved state. A successful ending removes the couple from the world and records a terminal cast departure for the partner without recruiting a replacement after the game ends. These literal speech adapters do not yet cover all natural paraphrases or a fully typed action/consent protocol.

The remaining mandatory acceptance work includes one canonical reducer for all consequential writes, same-turn scene validation before presentation, revision-checked commit/replay across workers, source reliability and contradictory belief support, delivery/read gating for all channels, detailed obligation attendance, complete NPC intention and activity libraries, stronger dramatic cooldown/arc logic, IU evidence-ledger integration, time-skip interruption, 6/30/100-character scale runs, and the three hosted campaigns in Section 17. Keep BL-33 through BL-38 open until their own acceptance criteria pass. Test and hosted evidence for this change set should be appended here after verification rather than presumed from unit tests.

The first hosted slice ran on beta `1045464`: 1,232 local pytest cases passed (one expected failure), 10 frontend tests passed, and local desktop Chromium/iPhone WebKit/standalone WebKit feature checks passed. Ten fresh Terrace and ten IU turns on the hosted API are documented in [SOCIAL_V2_HOSTED_PLAY_2026_09_26.md](SOCIAL_V2_HOSTED_PLAY_2026_09_26.md). They found an unparsed natural wait, a false 7 pm narration after a 24-hour skip, unknown speaker dialogue in an empty room, a bystander volunteering for a private plan, player-feeling narration, invented IU testimony provenance and a rediscovered clue. The corrective natural-wait parser and social scene guard have local tests; their hosted results require a subsequent SHA. This run does not satisfy the Phase 1–5 exit gates or the 20-turn/scale campaigns in Section 17.

The corrective beta `c1050c9` passed 1,234 local pytest cases (one expected failure), the hosted natural-wait/empty-room replay, IU reinspection replay, and hosted desktop Chromium/iPhone WebKit/standalone WebKit UI flows. Its successful replay is limited to those specific cases. Source attribution, broader player agency, direct-answer pacing, one canonical event reducer, replay/concurrency and Section 17's full campaigns are still open.
