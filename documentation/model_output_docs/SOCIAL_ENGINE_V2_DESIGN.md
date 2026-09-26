# Social engine v2: causality, knowledge, and consequential relationships

Status: engineering proposal, 2026-09-26. This document specifies future work; it does not describe a shipped v2. Scope: a reusable engine for Terrace and other social stories, with epistemic infrastructure reusable by IU. No four-week deadline is enabled by this proposal.

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
