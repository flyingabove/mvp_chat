# Social engine: master design, v2 design, social mode, cast lifecycle

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../backlog/](../backlog/).

## BL-39 — Canonical proposal: reusable character-centered simulation engine

- **Type:** feature / engineering plan
- **Found:** 2026-09-27; consolidated by owner direction on 2026-09-28.
- **Severity:** high: unreliable outcomes, attribution and character agency undermine gameplay.
- **Status:** proposed, not implemented or calibrated by this documentation change.
- **Authority:** the single target architecture and roadmap. Replaces competing architectural portions of BL-38 and original BL-39. [BL-38](../backlog/BL-38-social-engine-atomic-transactions.md) remains an open correctness tracker, not a second design.
- **Navigation:** sections 1–3 ownership; 4–9 contracts; 10 release units; 11 acceptance; 12 owner answers.

### 1. Product goal

Build enjoyable, heightened, plausible drama around characters with different beliefs, tastes, voices, commitments and aims. Humor and surprising choices are welcome. A character can ditch work for a date and worry about their boss; the choice needs a possible route, believable motivation and consequences. Consistency supports drama, not a requirement to choose the dullest sensible action.

Use BL-39's Character → Heart → Bond model and perceive → appraise → feel → want → act loop. BL-38's atomic turns, provenance, consent, context isolation and migration become required contracts. Do not build competing appraisal engines or relationship stores.

[Terrace House](TERRACE_HOUSE.md) provides content: six residents from the authored 17-character pool, earned mutual departure, personal standards, NPC couples, director warning after two other couples leave and cut after three, and optional commentary. The mystery reuses characters, knowledge, evidence, questions, agendas and agreements. No story ID, character name, gender rule, romance threshold or panelist identity belongs in generic engine logic.

Owner choices: **hybrid LLM/Jev social judgment; at most two LLM calls per turn; gameplay before latency optimization; provisional 5% visible fallback ceiling.** Developer arena judging stays off for playtest review.

### 2. Code reuse and migration seams

| Existing component | Reuse / change |
|---|---|
| engine/state.py::Character | Authored identity, voice, goals and tells feed Profile and character components. |
| world_model/character.py::CharacterState | Physical/routine state becomes Body through an explicit adapter. Do not alias incompatible CharacterState and Character types. |
| character_graph.py::RelationshipEdge.state | Initially the identical object exposed by Bond.feelings; eventually a facade over bonds. No copied writable score. |
| world_model/memory.py, epistemics.py, gossip.py | Shared storage with character-scoped views and transmission/source provenance. |
| agreements.py, commitments.py, turn.py | Extend existing scheduling/turn seams. Preserve ongoing attendance work and prove its subset before replacing callers. |
| romance.py and six romance_* fields | Adapt evidenced decisions to agreements/outcomes; remove regex authority after typed acts pass parity. Never infer consent from score. |
| intentions.py, offscreen.py, speakers.py | Incrementally replace hard-coded thresholds/pair-average weights with actor agendas. |
| projection.py, api/prompt_engine.py, extractor registry | Add scoped proposal/context adapters at existing seams, not another prompt pipeline. |
| frontend/index.html, dialogue.js | Reuse request_id, three-dot indicator and dialogue renderer; add ending UI/client timing. |
| SQLite revision / compare-and-swap | Reuse concurrency protection; add atomic receipt/event/outbox persistence. CAS alone is not replay. |

Target APIs below are proposed. Older [social-v2](SOCIAL_ENGINE.md) and [character redesign](WORLD_MODEL.md) documents remain history/fixture references; this proposal governs conflicting future design.

### 3. Object ownership

| Object | Owned state and behavior |
|---|---|
| WorldModel | Aggregate: World, CharacterRegistry, EpistemicLedger, AgreementBook, immutable StoryRules, ConversationState, Outcome. |
| World | Simulation clock, places, physical events and ordered event sequence. |
| Character | Profile/VoiceProfile, Personality, DeceptionProfile, Standards, Heart, Persona, Agenda, Body, Presence and scoped views. |
| Heart / Bond | Directional target bonds: existing feelings, optional standings, cause-linked impression history. |
| Profile / Personality | Identity/attributes/voice; temperament, tastes, activity preferences and objectives. |
| Persona | Immutable self-claim history, not universal truth. |
| Agenda | Intentions, goals, cooldowns and subjective PlanExpectations. |
| Body / Presence | Place, route, routine, availability; onstage/offstage/commentator capabilities and channels. |
| Scoped views | Memories, beliefs, commitments and conversations backed by shared stores; prompt callers do not manually filter owner strings. |

The player is a Character whose voluntary decisions come from input. Never invent player preferences, emotions, actions or consent. External events may affect them without selecting their response. Director/panelists have specific perception/contact capabilities, not omniscient narration.

Character methods perform no provider I/O. Application services obtain typed semantic proposals and pass them in. Deterministic replay of supplied proposals does **not** mean utility arithmetic replaces nuanced judgment.

Proposed interfaces:
- Character.perceive(event, channel, view) → Perception or none.
- Character.appraise(perception, proposal, policy) → Appraisal: validate actor-local interpretation, calculate bounded effects/reactions.
- Bond.apply(impression, rules) → AppliedEffect: sole social-state writer, idempotent by effect ID.
- Character.consider(act, candidates, view) → DecisionProposal; respond(...) → Verdict: hybrid choice under standards, feasibility and consent.
- Character.plan_speech(obligations, verdict, view) → SpeechPlan; response_context(...) → CharacterContext: voice, disclosure, answers and deliberate deceptive intent.
- Agenda.choose(opportunity, proposals, seed) → ActionProposal or none.

SocialAct(kind, actor, participants, source_event_id, terms) represents invites, confessions, exclusivity, departure, acceptance and withdrawal through a closed extensible registry. Verdict(answer: accept/not_yet/reject/defer, private_reason_refs, disclosure_safe_hint, proposed_effects) remains tentative until the turn commits. Typed effects target the owning objects rather than patching arbitrary state fields. An accepted confession does not silently imply exclusivity; its actual offered terms and each participant's decisions determine the agreement.

Impressions explain an observer's changed opinion. Standing is optional progression derived from accepted effects; feelings retain trust/affection/fear/suspicion/jealousy. DramaticPolicy ranks **admissible** opportunities; it never writes feelings, creates evidence or overrides refusal. These responsibilities complement each other.

### 4. Hybrid judgment, standing and knowledge

#### Hybrid choices and drama

The extraction LLM interprets input and proposes acts, semantic appraisals and nuanced choices. Jev assists supported classification, relevance and candidate evaluation. Reconcile into typed proposals with actor, source spans, evidence IDs, uncertainty and reasons. Neither provider directly writes saves.

Construct feasible/admissible options **before** ranking. Standards and participant consent constrain acts; a threshold is eligibility, never automatic acceptance. Semantic proposals, preferences and DramaticPolicy then select plausible dramatic, quiet or comic responses. Local math enforces bounds and can rank; it is not the sole authority for nuanced foreground choices. Never reroll refusal until acceptance wins. Candidate order and paraphrased duplicate beats must not change seeded outcomes.

Private input stays actor-scoped. The extraction LLM may receive the public scene plus one designated actor's private decision view; private-informed decisions from that call are only for that actor. Others use independently scoped Jev tasks or explicit local policies/defer. One prompt containing all private minds is not isolation. Response generation receives public material and disclosure-safe SpeechPlans, not raw private bonds. No per-NPC LLM fan-out.

Before cutover compare hybrid, legacy and local utility on identical recorded work/date, refusal, tentative offer, jealousy, deception and comic/quiet fixtures. Hold knowledge and eligible options constant; record reasons, disagreement, enjoyment and invariant failures. Hybrid is already selected; comparisons validate/tune it. Extra offline model experiments need an explicit budget; this document authorizes none.

#### Standing, impressions and closed conditions

TrackSpec(id, tiers, daily_gain_cap, repeat_decay, neglect_decay), Tier(id, floor, ceiling, gate), Standing.apply(...), Requirement(...) and Condition.evaluate(Viewpoint) are pure typed components testable without providers or a running world.

Gain order: suppress when closed; apply same-tag/day diminishing returns; limit by remaining daily allowance; traverse only open tier gates; clip to reachable ceiling and discard surplus. Count actual accepted gain against the daily cap. Losses apply while closed and can lower tiers. Decay is an explicit ordered clock event, not a read-time side effect. Define stable ordering for simultaneous events.

Persist proposed/applied effects, cause/effect IDs, actor, target, dimension/track, tag, channel, simulation minute, sequence and policy version. Replay chronological **applied effects**, not uncapped proposals. Bound in-memory impressions with checkpoints and retained audit/cause references. Never recompute old effects under new tuning. Route legacy deltas through this writer once; never apply both a delta and derived impression for the same effect.

Closed Condition kinds: BelievedAttribute, EventCount, AgreementCount, Feeling, StandingAtLeast, TierReached, Knows, DaysKnown, DaysInTier, CounterAtLeast, Not, All, Any and typed committed-act/agreement predicates. No executable story expressions. Each kind has validation/explanation.
- Character Viewpoints see only their knowledge; engine truth Viewpoints are privileged and never enter prompts.
- Return true / false / unknown. Not(unknown) stays unknown, never a dealbreaker. Belief conditions require established belief, not testimony alone.
- Tier gates cap progression; dealbreakers close tracks under configured evidence/reopening rules. Neither overrides withdrawal.
- Stage is derived. Reject contradictory gates, invalid ranges, missing references and unreachable endings. Numbers remain tuning hypotheses.

#### Testimony, belief, lies and disclosure

Persona records SelfClaim(key, value, utterance_id, audience, asserted_at, valid_time). First claim is immutable **history**, not eternal truth. Changed circumstances, corrections and conflicting claims coexist. Profile truth seeds NPC self-knowledge, not knowledge for everyone.

Hearing creates attributed testimony/transmission. Belief acceptance is separate appraisal using evidence, reliability and skepticism. Contradiction creates dispute, not proof of lying. Distinguish suspicion, perceived deception, engine-established deliberate deception and honest mistakes. Consequences follow a character's justified perception, with uncertainty and repair.

Actual source, claimed source, transmission root and intent are distinct. Deliberate lies can name false sources without creating source events or laundering hearsay into truth. Circular gossip has one root, not independent corroboration. A believed lie may pass a preference gate; later evidence may change belief and decision.

DeceptionProfile controls tells by skill/stress/context. Generally hint, but nervousness is not proof and skilled liars need not visibly confess. Voice-only calls cannot reveal visual tells. DisclosurePolicy filters explanations before generation; hidden requirements do not leak because they influenced a verdict.

### 5. Atomic turns, speech and inference

#### Transaction boundary

1. Resolve (session_id, request_id) against durable receipt; reject the same ID with different normalized input. Exact committed retry returns saved reply without inference/mutation.
2. Load revision/pinned ruleset and create tentative snapshot. Extract ordered typed commands/questions with one extraction LLM plus bounded Jev.
3. Validate authority, source, presence, ambiguity and feasibility. Execute ordered travel/time, perception, appraisal, decisions and agreements tentatively. A skip requiring confirmation returns its preview before advancement.
4. Evaluate clocks/endings on that result, deduplicating event IDs. Produce scoped SpeechPlans, answer obligations, public beats and any panel dossier.
5. Single response LLM realizes those plans. Validate speaker/channel, consequential speech acts, attribution and answer coverage **before display**. Model annotations are proposals, not proof of equivalent meaning.
6. Use calibrated Jev/local checks and safe constrained substitutions within budget. If safe realization is unavailable, abort gameplay effects and return parenthesized error/clarification; retain a failed/no-effect receipt for retry and metrics.
7. Atomically CAS revision and persist state, event batch, utterances matching final text, outcome, exact reply receipt and outbox. Stale writers cannot overwrite newer state.
8. Deliver committed content. Outbox delivery is idempotent/retryable. Pre-commit crash exposes no effects; post-commit crash replays saved result.

This replaces act_confirmed as post-display repair. Atomicity prevents state/reply divergence; semantic validation separately proves the prose expresses the verdict. Endings are not a second post-reply transaction. A substitution must match committed effects or the tentative operation aborts.

The initial backend receipt slice wraps the supported existing boundary without a full reducer rewrite. Frontend already sends request_id. Crash tests prove storage atomicity, not an in-memory deduplication cache.

#### Character speech

ConversationState records source questions, addressees, pending/resolved/deferred state and interruptions. Resolve only through the addressee's answer, refusal, uncertainty or acknowledged deferral. Chatter is not an answer; multiple questions remain separately traceable.

VoiceProfile controls register/directness/expressiveness/length/examples. Voice changes preserve mechanical outcomes. CharacterContext contains perceived evidence and permitted plans, not a global notebook. Scene validates identity, introductions, encounters, presence and channels. Narration avoids invented player actions/emotion, repetitive decoration and fake return greetings.

Consequential attribution needs an admissible source set before semantic matching. Calibrate negation, pronouns, reported speech, qualifications, ambiguity and omitted answers; a keyword/event ID alone is insufficient. Unsupported claims use approved safe wording. Prefer in-character uncertainty/refusal in the normal response call; canned recovery is exceptional and measured.

#### Provider budget and quality

At most **two LLM provider attempts per gameplay turn**, including retries/background/shadow/translation: extraction assisted by Jev, then response. Reserve one attempt for response. No third verifier, repair, panel or per-character call. Receipt replay and deterministic engine previews need none.

TurnInferenceBudget counts attempts across callers, propagates cancellation/deadlines and separately bounds/batches Jev through existing registry/provider seams. Unsupported tasks abstain; only independent inputs run concurrently. Late results cannot commit after cancellation. Do not impose a two-second timeout or silently alter operational timeouts.

Repository defaults gate Jev through TYPESAFE_ENABLED with JEV_ENABLED_TASKS empty and JEV_SHADOW_SAMPLE_RATE zero; deployed overrides were not inspected. Existing small hand-built cases/smoke evidence do not calibrate every proposed relevance/attribution/answer task.

Calibrate each enabled task on labeled examples, including missing/truncated/corrupt evidence, ambiguity, false sources and denials. Report false acceptance/rejection/abstention. Test enabled, absent, timeout and malformed modes. With Jev unavailable, reuse extraction proposals plus deterministic checks where safe; otherwise clarify/defer uncertainty. No third LLM. Both games must remain playable under this fallback; that quality floor is not yet demonstrated.

**O26a rollout gate:** at most **5%** visible canned/constrained recovery among eligible gameplay turns, reported per game and separately for consequential scenes. Predeclare scenario mix/denominator; use at least 100 eligible turns per enabled game and report counts/uncertainty. Sample size is an engineering starting point, not a measured pass. Track invisible provider fallback, canned substitution, clarification, abort/error and dropped responses separately; aborting more turns cannot conceal poor quality. Compare voice/answer coverage with baseline. Critical source/consent violations remain zero. If the gate fails, fix context/false rejection or retain prior safe scope; never weaken validation to reach 5%.

### 6. Agreements, travel, time and independent life

AgreementBook owns participant roles, individual decisions, terms/revisions, conditions, invitations, amendments and fulfillment. Keep a two-party convenience API, not a second book. Benefiting from a promise does not imply acceptance; nobody consents for another. Private-plan joins require appropriate participants' new agreement.

Distinguish proposed, tentative, confirmed, withdrawn, cancelled, fulfilled, missed and excused. “Maybe after work” stays tentative. Character-owned PlanExpectation may be optimistic/mistaken without changing terms. Hopeful attendance can cause disappointment, not fabricated breach. Clarification updates expectations without rewriting history.

Body, Activity, Schedule and Route own availability, preparation, departure and arrival. Acceptance is a plan, not relocation. Future/conditional requests do not move anyone now. Charge travel once in input order: wait-then-go differs from go-then-wait. Attendance is not completion; record shared activity/witnesses. Consequences apply once, only to observers/informed actors.

Before skipping important player-known events, preview **all** affected known events in parentheses, tentative plans labeled: “(You will miss your date with Yuki and the tentative rehearsal with Mako. Continue?)”. Require revision-bound explicit confirmation. Stale previews refresh; decline advances no time; duplicates advance once; ordinary dialogue is not approval. Hidden events stay hidden. Player↔engine control messages are parenthesized and excluded from NPC memory.

One simulation clock processes commitments, routes, decay and opportunities chronologically. Moderate, tunable autonomy is default. More simulated elapsed time permits causal chains/butterfly effects, not merely bigger random rolls. Equivalent partitioned waits preserve opportunity scheduling; changed input can cause divergence. App-closed wall time does nothing.

Agenda combines social and career/personal aims. On/offscreen actions share consent/feasibility with bounded work and actor cooldowns; attention does not freeze others. Jev can assess scoped options; routine/offscreen scheduling uses documented local policies without per-tick LLM calls. NPC couples need both decisions, not high scores alone. Disinterest/inaction remain valid. Nobody plans from another's private feelings.

EvidenceEntity exposes actual inspect/request-footage/calendar/witness affordances. InvestigationTask persists pending/denied/completed state and evidence revisions. Missing records are not fabricated; unchanged surfaces do not yield repeat discoveries. Notebook remains player-scoped. Reuse the same event/evidence system, not a separate mystery truth store.

### 7. Endings, clocks and commentary

StoryRules declares typed Ending, Clock and Beat. Outcome is persisted with ending/reply in the same turn, evaluated once in declared priority order. Mutual departure requires an explicitly accepted agreement; refusal, withdrawal, solo exit and continued play differ. Replacement cast gets fresh identities/private state. Adapt supported existing outcomes first; scores/regex alone cannot manufacture consent.

Terrace: earned progression over simulated days, no fixed run timer or automatic day-one win. Director warns at two **other** happy couple departures and cuts at three; count unique committed departures excluding the player couple. Contact, counters and endings are reusable; numbers/romantic eligibility are content.

Panelists are commentator Characters. Camera channel admits filmed/public events under rules.filmed_places. Dossier contains only that evidence and each commentator's **own** appraisal. Subject impression logs, hidden standings/tiers, undisclosed conditions, memories and confessionals are not footage. Distinguish facts from opinions/inferences.

Retain named Terrace panelists. Owner rule 2026-10-01: the panel speaks only in the ~2,000-word finale when the player wins or loses (authored no-skip presentation); no mid-game asides or NPC departure segments. These are content settings, not universal response lengths. Judge conduct, not identity/personal worth.

Build dossier and 5–7-segment outline locally; Jev may assist scoped assessment. The **same response LLM call** renders exit scene, all panel segments and verdict lines. No outline/segment/verdict call chain. Validate evidence support before commit; IDs alone are insufficient. Allocate explicit finale output allowance; measure latency separately; never split into extra calls. Failed/truncated finales follow safe failure, not partial publication of uncommitted consequences.

Commentary is intended enabled for Terrace and default off elsewhere. Developer arena is separate and off for playtest review. This proposal authorizes no arena run.

### 8. Configuration, authoring and migration

StoryDefinition compiles immutable StoryRules/SimulationRuleset: engine defaults → capability preset → story overrides → permitted character/activity overrides. Validate fields/vocabularies/ranges/references/dependencies/reachability. Rename characters, story IDs and venues in fixtures: behavior must follow data, not names.

| Owner | Tuning / disabled behavior |
|---|---|
| Voice/Deception/Personality | Examples, tastes, skepticism, jealousy, forgiveness, activities, composure/cues. Neutral compatible defaults; no invented dealbreakers. |
| Standards/Bond | Optional tracks/gates/caps/decay/reopening. Disabled standing leaves consent explicit. |
| Agenda/DramaticPolicy | Moderate autonomy, aims, tension/humor/repetition, cooldowns/budgets. Disabling initiative does not abandon obligations. |
| Agreement/Schedule/Route | Grace periods, expiry, guests, routine, preparation/travel/flexibility. Static scenes cannot promise impossible travel. |
| Perception/Epistemics | Channels, barriers, attention, reliability, gossip/deception. Gossip may be off; source/visibility integrity cannot be. |
| Conversation/Narration | Answer priority/deferral, speakers, texture/length. Addressed response and player agency remain invariant. |
| Investigation/Needs | Optional affordances/fatigue/energy; do not require unused mechanics in every game. |
| Outcomes/Clocks/Commentary | Conditions, terminal/open-ended play, counters, filmed places/content. Off does not suppress ordinary world events. |
| Skip/Interpretation | Importance criteria, tentative expectations, clarification tendency. Unknown stays unknown; known-event confirmation cannot silently disappear. |

Phase D includes actual content migration: profiles for all 17 Terrace candidates, compatible mystery goals/voice from existing content. Implementing feature owner owns defaults/mappings/drafts/validation/fixtures. Sparse characters must behave plausibly with neutral defaults and no invented exclusions; a full tuning pass is not required to load/improve a story. Rich tastes/standards improve distinction. New significant lore/dealbreakers need content review. Numbers remain hypotheses until tested.

Pin schema, content/ruleset hash and policy version per save; authored edits never silently retune ongoing games. Phase B wraps existing graph state. At one tested cutover Bond becomes persisted owner and CharacterGraph forwards reads/commands; remove obsolete writers/serialization together. Migrate only evidenced agreements/outcomes; ambiguous legacy flags stay unknown/legacy, not new acceptance or backdated events.

Required drill: isolated old saves with pending agreements/jobs/disputes; migrate; compare identity/knowledge/consent/schedules; round-trip; inject crashes/concurrency/retries; replay hashes; exercise pre-turn rollback and compatible post-migration handling without lost progress. Mid-save disabling drains obligations, explicitly cancels with events or rejects the change. Incompatible old writers cannot write newer saves. Backups/version routing precede old-session opt-in.

### 9. Thinking feedback and latency

Source confirms existing three animated dots in frontend/index.html: typing-indicator/typing-bounce, shown before fetch, hidden on success/error. Preserve them. This is not a new browser lifecycle/accessibility test. Verify pending/success/error/cancellation/navigation and reduced-motion/accessibility in the UI slice. Added engine status wording belongs in parentheses.

Reuse backend/app/utils/stage_timer.py::StageTimer and stage ledger. Add client monotonic timestamps for submit, indicator paint, response completion, first meaningful result paint and final typewriter completion, correlated by request ID/build/ruleset. Include commit and total duration; existing pre-commit latency log is insufficient. Record LLM/Jev attempts/timing, errors/timeouts/cost separately. No private dialogue in timing telemetry or subtraction of unsynchronized clocks.

September 22 historical baseline: only 24 Terrace requests; cohort p50 ~3.09–3.95 s, p95 ~4.44–5.87 s. Not a current two-game baseline or proof of two-second capability. Measure desktop/mobile, warm/cold and ordinary/skip/finale workloads with sample sizes, p50/p95/p99/max and failures.

Current speed is owner-accepted. Earlier 1–2-second wish is future optimization context, not an immediate deadline or reason to sacrifice gameplay/extraction/validation. dialogue.js::revealBlocks is post-response typewriter, not server streaming. True streaming is deferred until validated segments, committed consequential decisions, reconnect sequence IDs and durable receipts are designed.

### 10. Release units and roadmap

Runtime changes follow ship-and-verify: integrated tests and actual hosted beta behavior. A proposal/unit test alone is not completion. Independent useful fixes need not wait for every phase.

| Independent unit | Small contract | Proof / dependencies |
|---|---|---|
| Opening text O12 | Reproduce IU escape/line-break defect; repair field or proven generic boundary; preserve literal escapes. | Raw segments and desktop/mobile. No new types. Skip patch if no longer reproducible. |
| Addressed answers O08 | ConversationState + character response-context adapter at extraction/prompt seams; persist questions/deferrals. | Two questions and interrupted/resumed exchange with grounded response/refusal/unknown. No full ledger migration. |
| Durable receipt O15/O24 | Backend transaction: supported state change + exact reply under current request_id; input hash/revision CAS. | Lost reply, restart, concurrent duplicate, same ID/different input, pre/post-commit crashes. No frontend ID redesign. |
| Continuity/agency O09/O11 | Narrow identity/presence/opening fixes through current objects. | No invented player actions/wrong addressee/absent speaker; independent of standings. |

BL-35 attendance may ship its proven subset separately; remaining travel/misunderstanding stays open. A–J leads gameplay; correctness contracts apply immediately when a phase touches their state.

| Phase | Deliverable | Gate |
|---|---|---|
| **A — Endings/UI** | Typed Outcome/Ending adapter over evidenced current decisions; structured payload, goal/ending card. | Atomic outcome/reply; no score-only win; accept/decline/solo/reload. Does not yet claim earned-standing progression. |
| **B — Character aggregate** | Profile/Body/Heart/Bond wrappers, legacy adapters, scoped views/context. | Identical graph state reference; no duplicates/private leakage/behavior change. |
| **C — Standing/conditions** | TrackSpec/Standing, tri-state conditions, Standards, ordered effect journal. | Caps/repetition/decay/replay; one writer; cause IDs. |
| **D — Perception/appraisal** | Hybrid adapter, tastes/temperament/reactions, 17-character Terrace content and mystery defaults. | Scoped provenance before activation; reaction matrix, rename tests, Jev outages/content review. |
| **E — Persona/belief** | Time-indexed claims, correction/dispute, reliability, deception/cues/disclosure. | Correction is not automatic lie exposure; actual/claimed sources, unknowns and privacy. |
| **F — Social acts/commitments** | Typed extraction, hybrid Verdict, participant decisions, tentative expectations, scheduling/travel. | Validate before display + atomic commit; no post-display act_confirmed; explicit consent; replace regex after parity. |
| **G — Agendas/cutover** | Shared on/offscreen acts, independent aims, NPC courtship, bounded scheduling, graph facade. | Both participants decide; fairness/replay/old-save drill; obsolete writers removed. |
| **H — Clocks/director** | Generic counters, warning/trigger beats, offstage contact. | Warn at two/cut at three other couples; no duplicates/player inclusion/leaks. |
| **I — Commentary** | Camera views, dossier/local outline, one-response-call panel, dialogue UI. | No private subject state; supported citations/output/failure tests; arena off. |
| **J — Projection/evidence/tuning** | Consolidated safe adapters, investigation affordances/tasks, focus policies, tuning/campaigns. | Applicable O gates plus earned win/cut/solo and both existing gender paths. Privacy is required earlier, never deferred to J. |

Reuse already-shipped correctness slices. Split substantial implementations into bounded ledger tasks with phase/API/acceptance IDs. Related defect items stay open until their own proof passes. No phase is completed by this consolidation.

### 11. Acceptance contract

Stable BL-38 acceptance IDs are retained below for tests and backlog references. All are required future evidence, not results of this documentation task.

| ID | Concern | Required evidence |
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
| O25 | Actual inference budget and latency — review Q3 | Six characters/two objectives use one extraction LLM call assisted by bounded Jev work, then one response LLM call; never more than two LLM attempts including retries/background work. Count Jev separately and test its failure fallback without a third LLM. Correlate existing server-stage timing with client wait/paint/reveal durations and measure the accepted current baseline. Report percentiles/max/errors; no immediate two-second gate or speed-driven gameplay simplification. |
| O26 | Source/answer verifier calibration — review Q4 | Labeled questions, denials, paraphrases, omitted answers and explicit deceptive acts produce the expected verdict/fallback; corrupted/missing/truncated evidence cannot justify an attribution; report false accepts/rejects/abstentions. |
| O26a | Visible fallback quality | Gate at <=5% visible canned/constrained recovery, measured per section 5 by game/consequential scene; distinguish provider fallback, clarifications, aborts and dropped turns. Zero critical consent/source violations. |
| O27 | Dramatic selection determinism — review Q5 | Candidate-order permutation preserves choice, refusal is not rerolled, quiet in-character choices remain admissible, and paraphrased duplicate beats share cooldowns. |
| O28 | Old-save cutover/rollback | Complete section 8 migration drill, including pending agreements/jobs, crashes, concurrency, pre-turn rollback and post-turn compatible routing without lost progress. |
| O29 | Thinking indicator — owner request | Preserve the existing three animated dots before results; verify pending/success/error/cancel/navigation lifecycle on desktop/mobile, distinguish typewriter reveal from streaming, and cover accessible status/reduced-motion behavior when changing the UI. Source presence is confirmed; full browser acceptance remains to run with the implementation slice. |

Additional BL-39 gates:
- Standing: cap order, discarded surplus, duplicate causes, losses while closed, decay, replay/checkpoints and policy versions. Conditions: unknown/negation under character and truth views.
- One flirt produces distinct target/partner/rival/stranger reactions with one engine. Remove a witness and perceived input changes. No duplicate effect from legacy deltas.
- High standing alone never creates consent. Hypothetical, conditional, quoted and third-party acts do not silently commit.
- Endings/warnings survive reload and fire once. NPC couples use the same participant rules. Seeded long simulations permit passive cuts, earned wins and plausible rejection without guaranteeing success.
- Camera dossier excludes hidden impressions/conditions/confessionals; commentary uses the existing response call and permissible evidence.
- Fault/replay checks cover safe substitutions, terminal/interrupted turns and state/speech agreement. Rename story content and exercise a minimal workplace fixture alongside both games.
- Hosted proof: complete Terrace and mystery campaigns, earned Terrace win/cut/solo paths, both existing gender paths, desktop/mobile, request traces, defects and human gameplay grades. Arena stays off.

### 11a. Implementation status (2026-09-29)

Built and pushed to beta, one commit per phase, each hosted-checked: independent units O12 (`26053bb`), O15/O24 receipts (`3dbbe90`), O08 addressed questions (`a554c5a`), O11 continuity (`a8987f1`/`d8f6a03`); phases A endings/UI (`33e9106`), B character aggregate (`24cbca2`), C standing/conditions (`2a0f482`), D appraisal + 17 Terrace personality drafts (`55cad21`), E claims/beliefs/tells (`e76a2a3`), F typed social acts (`4ac255b`), G agendas/NPC couples (`f45cd60`), H clocks/director (`83276f4`), I studio panel (`619b3b4`, `d1e28df`), J seeded campaigns + tuning (this commit). Seeded campaigns prove an earned win on both gender paths, a director cut for a passive player and a day-one solo exit.

Not done, tracked: O09 narration agency (BL-29, owner: backlog), relationship-graph storage cutover (BL-40), IU investigation records/interviews (BL-41, owner content), invites/dates/travel and the "2 completed dates" romance gate (BL-35), context-focus policies, true streaming, and the hosted 20-turn campaigns with human grading. Terrace personality numbers and the romance ladder are tuning drafts pending owner review. Target decisions use a documented local policy (standing + standards), not a model call.

**Hosted-play hardening shipped 2026-09-29 (beta `eb4cae1`, each covered by unit tests; suite 1511 pass):**
- **Invited movement** (`world_model/companions.py`, called from `begin_turn`): a present, awake, not-cold resident travels with the player only on an explicit invitation (named, or the sole person present); future or conditional invitations move nobody. Closes the "date happened in an empty room" hole for on-the-spot invitations; scheduled arrival stays in BL-35.
- **Question backstop** (`world_model/conversation.py`): `PendingQuestion.replies`, `MAX_DIRECTED_REPLIES = 1`; a question closes on the addressee's first reply, so no character answers twice (O08 follow-up, see BL-37).
- **Promises** (`commitments.py`, `promise_judge.py`, `turn.py`, `contact.py`): once-only reminders (`Memory.reminded`, `mark_reminded`), silent lapse for promise-derived plans, word-overlap completion deleted, Jev promise judge (choice + yes/no in one request, either says done; `PROMISE_JUDGE_ENABLED`, on by default and inert when Jev is off). Accuracy gate: `pytest -m integration tests/backend/integration/test_promise_judge_accuracy.py` (2% miss rate, nothing wrongly kept, never run on deploy); measured 0.6-1.2%. Design and evidence: `proposals/PROMISE_COMPLETION_JEV_2026_09_29.md`.
- **Update-reload loop** (`frontend/index.html` `appUpdateAction`): the version check reloads automatically at most once per server revision, then shows a tap-to-update bar; fixes the iPhone Safari "flashing Loading" loop (161 reloads in 52 s). `tests/frontend/app_update.test.cjs`.
- **Deterministic campaigns** (`tests/backend/app/api/test_terrace_campaigns.py`): the opening roster RNG is seeded and the passive-cut budget is 180 days; the unseeded roster had failed the deploy gate about one run in three.
- **Own-line replay guard** (`dialogue.py` `own_repeat_indexes`/`drop_own_repeated_lines`, `world_model/turn.py` `own_spoken_lines`, wired in `prompt_engine.py`): a character repeating a line of 6+ words they said earlier (read from the world model's dialogue memories, so it reaches beyond the last three messages) triggers the existing one-shot regeneration, and any leftover replay is dropped unless it would empty the reply. Fixes residents replaying their arrival introductions when greeted (BL-47 part 1).
- **Owner rules recorded** in `documentation/user_corrections.md` (2026-09-29): state trackers may forget but must never register a kept promise as unkept; semantic matching goes to Jev with a measured bar or is removed.
- **Opened from that play:** BL-43 (name and nickname matching via Jev), BL-44 (resume of a server-deleted session shows a blank chat), BL-45 (remaining promise-judge misses), BL-46 (a refused "leave this house" ask walks the player outdoors; fixed, see "Leave-together asks, choice cards and plans"), BL-47 (arrival introductions replayed, stock refusal lines).

### Leave-together asks, choice cards and plans (BL-46, as built)

Owner design 2026-09-29. Code: `world_model/choices.py`, `world_model/leave_meaning.py`, `social_acts.py`, `turn.py`
(`answer_choice`, `leave_meaning_subject`, `apply_leave_meaning`, `_offer_skip_to_plan`), `prompt_engine.py`.

- **`(...)` and `[...]` talk to the game master** (interchangeable). A question gets an author-voice answer; a command
  or action ("(I walk out onto the street)") is carried out and narrated in scene (`prompt_builder.py` "DIRECT CHANNEL").
- **Who moves the player.** A parenthesised movement command (`_engine_move_command`) always applies, even right after
  a refusal. A plain first-person performed move ("I go to the kitchen") still applies (`_match_world_destination`).
  On any turn that carries a typed social act (or a choice-card answer) the extractor's destination guess is ignored
  otherwise: an ask, invitation or confession never moves anyone before it is answered.
- **"Leave together" may be a walk or the win.** `leave_meaning.classify` (Jev, a bounded classifier, no extra LLM call;
  only when `NPC_DECISION_MODE` is `jev` or `compare`) reads `couple`, `outing` or `unclear`. `couple` runs the normal
  verdict (Terrace still needs the relationship via `requires_relationship`). `outing` and `unclear` are not typed acts:
  no verdict, no cooldown, nobody moves; the target answers the invitation or asks which is meant
  (`WorldModel.pending_notes`). No usable Jev answer, and in `rules` mode: a couple reads `couple`, anyone else `unclear`.
- **A decline names the room.** `directive(verdict, names, place)` adds "The scene stays at {place}; nobody leaves
  unless the player says so."
- **A yes opens a choice card, not an ending.** Accepting `ask_leave_together` records the yes and a persisted
  `WorldModel.pending_choice` (returned as `pending_choice` in the chat response and by the history endpoint, so a
  reload or resume shows it again). Options: `leave_now` (play the judges' ending) and `keep_talking`. The card is
  answered by an ordinary chat message, `__choice__:<id>:<option>` (bots and the arena use the same path), or by
  typing `[play ending]`/`(play credits)` while the card is open. `leave_now` queues a `Verdict(..., hint="confirmed")`;
  only that turn runs the finale directive and `commit_mutual_departure`. `keep_talking` is handled in the browser (a
  "Play ending" chip stays). The yes lapses at the end of that in-game day, or when the relationship ends or the
  partner is gone; the storyteller is told. Leaving needs the partner in the player's room.
- **Agreed future plans offer a skip.** When the previous exchange's commitments include a plan between the player and
  a resident more than 3 hours away, a `plan_skip` card offers "Skip to Saturday 12:00" / "Keep playing". Skipping
  runs the clock to the due time through the existing time-skip path, brings the resident to the player after the world
  steps (`pending_meet`), and everything in between happens off-screen. One card at a time: an open leave-together yes
  is never replaced. The meeting place is not tracked yet (BL-35). The card appears one turn after the agreement,
  because commitments are extracted from the previous exchange.
- **The player cannot end the run alone.** `leave_alone` (act, extractor rule, `left_alone` ending, solo-departure
  regex path) is removed. Only the director clock (`cut_by_director`) ends a losing run.
- **Chat responses carry `location_id`**, so tests and browser checks need not infer the place from narration.

### Scene recall and visible rivals (BL-47 part 2, BL-34, as built)

- **What a speaker "personally remembers" (BL-47).** `_build_view` (`world_model/turn.py`) ranks a speaker's memories for the
  scene with `MemoryStore.search(..., exclude=_is_resident_speech)`: other residents' spoken lines (dialogue memories not
  told by the player) are left out. The `@id` mention boost used to put a speaker's own latest refusal, and lines their
  listeners heard, back on top whenever the player named them, and the storyteller repeated it (25 of 25 turns in a
  scripted replay; 0 of 25 now). What the player told them, facts, promises and witnessed events still surface; the recent
  chat carries what was said, and `own_spoken_lines` (the replay guard) still reads dialogue memories.
- **Rivals compete with the player (BL-34).** `agenda.refresh_agendas` reads each holder's `crush` stances (P-08; the stance rule holds the
  interested tier, eligibility and the closed-to-player test) and counts the player as an admirer of anyone with a crush stance toward the
  player who is not in an NPC couple; every other resident drawn to that person gets `compete_for`. "Drawn to" now also includes a live `pursue` aim.
  `agenda.next_beat` offers a `compete_for` beat when the target is in the scene, at most once per character per in-game
  day (`BEAT_TEXT["compete_for"]`: one small, visible move, no confession, no private thoughts; without the daily limit a
  scripted afternoon produced 24 beats in 25 turns), and the existing in-scene invitation (`intentions.propose_agenda_invitations`)
  makes it a state event with a trace.
- **Independent aims (opt-in).** `social_tracks.couples.rival_aim` (0-1; Terrace 0.3; 0 or absent = off) makes
  `world_model/rivals.py` `seed_rival_aims` give each resident of the player's gender, at world build, one long-lived
  (`AIM_DAYS`) `pursue` intention on an opposite-gender resident, chosen deterministically from the house seed. Aims may
  overlap and usually do. It is an intention, not a feeling: no standing is invented. `bootstrap.seed_rival_aims_for_state`
  is called at world build and again from `turn.sync_membership`, so a resident who moves in later, or a rival whose target
  moved out or coupled up, gets an aim too; it is idempotent and only rivals without a live aim (target still in the house
  and free) receive one. Pace check (12 seeded houses, passive player, one `DAY` skip per turn): the director cut came on days 95-136 without aims and on days 95-173 with aims at 0.3, inside the 180-day allowance but with only 7 days of margin in the slowest house.

### Acquaintance ladder: strangers act like strangers (BL-76 / BL-84, as built 2026-09-30)

Generic, any story. `acquaintance.levels` in story JSON (`engine/rules/acquaintance.py`) is an ordered ladder of
`{id, min_days, min_turns, conduct}`. A character reaches a level when BOTH thresholds hold: days since they met the
player (`WorldModel.first_met_day`) and turns spent in the player's company (`WorldModel.turns_together`, persisted,
counted once per turn they are present). The highest level reached wins. `turn._conduct_note` appends that level's
conduct text to the character's line of the scene contract (`TurnView.cards`) every turn.

It is independent of any romance track, so closeness is earned by time together and a model's default warmth cannot
skip it (sim 2026-09-30: a resident used the player's name on turn 3 and blushed on turn 5). Many turns on one day
never reach a level that needs a later day. Validation: first level at 0/0, strictly increasing, distinct ids, every
level has conduct. Stories without `acquaintance` are unchanged. Terrace declares four levels: strangers, acquaintances,
familiar (1 day, 30 turns), close (3 days, 80 turns). Tests: `test_acquaintance.py`.

### Affinity signals: liking shows as ambiguous behaviour (BL-84, as built 2026-10-01)

Generic, any story with a standing track. `world_model/signals.py` decides, deterministically per (seed, turn, person),
whether one present person shows an affinity signal this turn: a small behaviour ("asks one more question than they
ask anyone else", "teases in a way that could be fondness or mockery", "ends up a little nearer"), passed to the
storyteller through must-address as "show it only as behaviour, never explain or label it: it could be politeness or
interest". Interest is the person's standing toward the player as a fraction of the track below its last tier. The
person who likes the player most signals about 4x as often as others, but others sometimes do too (polite decoys), so
the player never gets a reliable read. Intensity (levels 1-3) grows with interest and is capped by temperament
(`openness` of at most 0.3 never passes level 2, at least 0.7 shows a notch more); `pride` lowers the rate; a person
does not signal twice within 3 turns (`WorldModel.last_signal_turn`, persisted). Eligibility follows the appraisal
policy (`eligible`), so romance signals never come from same-gender residents. A story may replace the wording with
`signals.catalogue` (levels 1-3); Terrace uses the engine default. Tests: `test_signals.py`.

### Personality model: type and strategy (BL-80, as built 2026-10-01)

Generic, any story. A character's `personalities[key]` may add `type` (four letters, e.g. "ENFP") and `strategy`
(`open`, `fast_mover`, `patient`, `scheming`, `safe_pick`, `career_first`). The type supplies DEFAULTS for three new
temperament dials (`rules/personality.py`): sociability (E 0.8 / I 0.25), candor (T 0.7 / F 0.4), planfulness
(J 0.75 / P 0.3); explicit dials in `temperament` always win. Consumers, all existing mechanisms:
- `rivals.seed_rival_aims` scales each rival's starting aim by the strategy (`STRATEGIES` aim_scale: fast_mover 1.35,
  open 1.0, patient 0.7, career_first 0.5);
- affinity signals show more often for sociable people (rate x (0.7 + 0.6 sociability));
- the room's energy (`TurnView.energy`, "lively" when most present are outgoing, "quiet" when most are reserved) goes
  to the storyteller's scene section, so a house of introverts plays quiet and a house of extroverts plays lively;
- the dials appear in Jev's target view of a person (`npc_decision._TRAIT_WORDS`), so type shapes how an ask or
  confession is judged.
`scheming` and `safe_pick` are accepted and stored; their extra behaviour arrives with BL-81..83. Tests:
`test_personality_model.py`.

### Personality model: goals (P-07, as built 2026-10-01)

Generic, any story. `personalities[key].goals` is a list of `{id, kind, weight, target?, text?, shifts?}`
(`world_model/goals.py`, parsed and validated by `rules/personality.py` when the story loads). `kind` is one of `GOAL_KINDS`
(love, career, status, belonging, keep_secret, revenge, protect, chaos) or a kind the story adds in `goal_kinds`; `weight`
is within 0..1; `target` must be a character; a `shift` is `{when: <condition>, delta: -1..1, reason}`. An unknown kind, a
weight outside 0..1, a bad target, a duplicate id or an unknown condition raises at story load.
- **Shifts** use the ordinary condition language (`rules/conditions.py`) judged from the HOLDER's own viewpoint with the
  goal's target as subject, so nobody's weight moves because of a feeling they cannot see. A shift fires once, clamped to
  0..1. `GoalBook` (on the `WorldModel`, persisted as `goals`, absent in old saves) is the only writer of live weights.
  A weight is stored only after its first change, as an `EvolvingTrait` whose history holds the authored value and then
  each shift with its reason and minute; the shift id in that history is the once-only latch.
- **The card.** `Person.goals()` and `Person.active_goal()` give the live view. The heaviest goal (ties: lowest id; zero
  weight is not an aim) goes on that person's scene card as `private aim: ...; never announce it`, "(strong)" at 0.7 or
  more and "(faint)" at 0.3 or less.
- **Behaviour.** `agenda_scale` multiplies the priority of the holder's `pursue` and `compete_for` intentions by
  `1 + 0.5 x (love weight - strongest other weight)`, so a career-first person pursues less (0.55 at career 0.9). With no
  goals the scale is exactly 1.0. Nothing else reads goals yet; stances (P-08) and scene wants (P-11) will.
- The free-text `goal` trait on `Character` (from `motive`) is unchanged and still feeds the identity block; weighted goals
  are the structured layer beside it.
- Terrace authors goals for all seventeen residents from their motives, plus a love shift when a couple leaves the house.
  The decision golden record was regenerated for it: only agenda priorities of standing-derived aims changed, and one
  scene's offered beat moved from Hikaru to Makoto as a result.
Tests: `test_goals.py`.

### Stances: typed, explainable attitudes derived from the holder's own view (P-08 slice 1, as built 2026-10-02)

`world_model/stances.py`: `Stance(kind, holder, target, strength, about, cause_ids, since_day)` and `StanceBook` on the
`WorldModel` (persisted; old saves load with none). The book is **recomputed from scratch every turn** in `begin_turn`
(right after goal shifts) by rules in `rules/stance_defaults.json`, a generic pack a story overrides under `stances.rules`
(same id replaces, new id adds, `"disabled": true` removes; a default whose `$variable` the story lacks simply does not
apply, while an author's own incomplete rule fails loudly). A rule is a weighted sum of conditions judged from the HOLDER's
`Viewpoint`; the sum is the strength and the stance exists at `min_strength`. Rules run in order and later ones see earlier
results (`has_stance`), so `rival` (scope `triple`, third party from the holder's `crush` stances) falls out of two crushes.
Every stance records the terms that held (`rule#index`) and the world events they rest on, and keeps the day it began.

New closed condition kinds (all with parse validation and `explain()`): `trait`, `strategy`, `goal_weight`, `has_stance`,
`witnessed`, `acquaintance_at_least`, `in_couple`, `eligible`; `event_count.within_days`; `feeling`, `standing_at_least` and
`tier_reached` gain `toward` (holder | subject | third). Privacy by construction: no condition reads another person's feelings.

Generic pack now: crush, rival, ally, distrusts, suspects (resents, protective_of, owes, ex, admires follow with the
migrations). Slice 1 changes **no behaviour**: nothing reads stances yet; the next slices move rival seeding, `compete_for`,
fallout and the `intentions.py`/`offscreen.py` rival blocks onto them.

### Courtship and intensity: who can court or compete, and how hard a story leans on it (P-08 slice 2, as built 2026-10-06)

The engine holds no literal gender test for romance. `world_model/courtship.py` `Courtship(policy, genders, intensity)` answers
the two questions every mechanic asks, from the story's appraisal policy (`social_tracks.appraisal.eligible`: `any` or
`opposite_gender`) and each person's `gender` attribute: `eligible(a, b)` (can `a` be drawn to `b`) and `competes(a, b, partner)`
(both can court `partner`, so each is the other's rival). `rivals.seed_rival_aims`, `intentions.propose_rival_invitations`,
`offscreen.outcome_weights`, `act_fallout.apply_fallout`, `romance._eligible_present` and `turn.rivalry_context` all read it
(`rivalry_context` now carries a `courtship`; hand-built contexts holding only genders fall back to `Courtship.opposite`). A story
with no appraisal policy has no courtship; a story whose policy is `any` (or unknown genders) lets everyone compete.

`social_tracks.intensity` tunes it: `"high"` sets both knobs, or `{"romance": "low", "rivalry": 0.8}` sets each (a preset `off` 0,
`low` 0.35, `medium` 0.65, `high` 1.0, or a number 0 to 1). `romance` scales the cost of a refused confession (witness and refuser
standing loss); `rivalry` scales rival aims, a rival taking an opening after a refusal, the off-screen contest boost (plan x2 and
affection x1.5 at 1.0) and rival invitations (off at 0). A stance rule may carry `"family": "romance"|"rivalry"`: it forms on the
unscaled sum and its stored strength is multiplied by that knob (0 removes it); the pack tags `crush` romance and `rival` rivalry.
A story that does not say reads as `high` (the behaviour before the knob), and dating games (Terrace sets `"intensity": "high"`)
keep it there; a workplace story with no couples policy has none of these mechanics, and one with rivalry but no romance sets
`{"romance": "off"}`. Tests: `test_courtship.py`, `test_stances.py` (family scaling), the golden record unchanged.

### Motivated testimony: people with a stake speak in their own interest (BL-83 part 1, as built 2026-10-01)

Generic, any story with agendas. `world_model/stakes.py`: when the player's message names someone, each present person who
holds a live `pursue`/`compete_for` intention toward that person (or a live `pursue` toward the player, who is asking
about someone else) gets a private must-address note: they speak in their own interest, may play things down, play
them up or leave things out, never admit to it, and never state what the person privately feels as certain fact.
`scheming` strategy adds "steers on purpose"; high candor adds "would rather withhold than say something false".
Strongest stakes first, at most two notes a turn. The engine's truth and the player-visible state are untouched. Tests:
`test_stakes.py`.

### Fallout of a declined act and "drawn to someone else" (BL-82 part 1, as built 2026-10-01)

Generic, any story with `social_acts`. `world_model/act_fallout.py`, called from `social_acts.commit` when a
target-needing act is not accepted: every witness covered by the appraisal policy loses standing toward the player
(`failed_confession`, 2.0 x (0.6 + 0.8 x skepticism) points, so skeptics judge harder); on a clear no the person who
refused cools too (2.5); witnesses who share the player's gender and are free get a `pursue` aim on the person who
refused ("saw an opening", scaled by strategy). A yes and an act with no witnesses have none; absent people hear only
through existing gossip. `social_acts.assess` also words a soft "not yet" as "they like you but are also drawn to
someone else, and they will not say who" when the target holds a live aim on another person they rate higher than the
player. Tests: `test_act_fallout.py`.

### Decision golden record: the refactor safety net (P-03, as built 2026-10-01)

`tests/backend/app/engine/world_model/test_decision_golden.py` replays the seeded Terrace houses (seeds 0-11, both
player genders, a passive player skipping whole days, one scripted public confession on day 3, and one longer run of the
house that forms an NPC couple) through the real turn pipeline with no model calls, and compares to
`tests/backend/app/engine/world_model/golden/terrace_decisions.json`. Per story day it records each character's live
intentions, the beat offered, invitations queued, off-screen outcomes (kind, pair, place), fallout (including the
standing loss it proposed, which the book can clamp to zero), every non-zero standing, agreements, couples formed and
departed, the cast and the director's counters. Nothing is stubbed except the model: the recorders wrap the real
functions (`resolve_offscreen`, `next_beat`, `queue_contacts`, `apply_fallout`) and delegate. About 25 seconds.

A deliberate behaviour change regenerates the record in the same commit, with the reason in the message:
`UPDATE_DECISION_GOLDEN=1 python -m pytest tests/backend/app/engine/world_model/test_decision_golden.py`. Any other diff
means a refactor changed behaviour. Stances (P-08) must keep this record unchanged apart from intended, tested changes.

### Script rubric: is it engaging drama? (P-05, as built 2026-10-01)

`backend/app/sim/rubric.py`, generic (no story knowledge). Nineteen items from BL-87, each one bounded Jev question
with five anchored answers (1-5, reported as 2-10): scene S1-S8 (value turn, conflict, true to character, subtext,
heightening, plausibility, hook, emotional pull), day E1-E6 (threads, progressing complications, payoff, ensemble,
cliffhanger, tones), season R1-R5 (arc, change, earned twists, premise, bingeability). They go through the shared
decision resolver like `promise_judge.py` (a bounded classifier, task `script_rubric`, never a language model call).
`judge_level` scores one scene, day or season; `score_season` scores a whole run (scenes, then days, then the season) and
returns a `SeasonReport`. A level with any unanswered item is `Unscored`, never partially scored. Verdict: Recommend
at mean 8+, no item below 5 and plausibility 8+ (a day or season uses the lowest scene S6, and without it cannot be
Recommended); Consider at mean 6+; else Pass.

Calibration: `tests/eval_cases/script_rubric/` holds 40 dev and 20 held-out real Terrace scenes, labelled 1-5 per item by
Claude at the owner's instruction (README there). `python -m scripts.eval.script_rubric_eval` prints the anchors, counts labels and (live Jev,
free) reports agreement per item against a bar fixed in advance: within one point on 80% of scenes per item, 70%
verdict agreement. `rubric.CALIBRATED` was set on 2026-10-01 after the bar held on the held-out set (every item within
one point on 100% of the 20 scenes; exact agreement 25% on S7 up to 95% on S1; verdict agreement 100%; dev likewise, with
S6 at 95%). **Limit:** all 60 labelled scenes are Pass-level, so this shows Jev agrees on weak scenes and says nothing yet
about strong ones (BL-96). `pytest -m integration tests/backend/integration/test_script_rubric.py` enforces the bar and
never runs on deploy.

### Pilot season on a real model (P-06, as built 2026-10-01)

`python -m scripts.run_season` runs the headless `SeasonRunner` (P-04) on an authored story with a language model
writing every scene, then scores the result with the script rubric. Pieces, all generic:

- `backend/app/sim/story_loader.py` `build_season(story_id, seed)`: the story's own world model through the same
  `bootstrap.build_world_model` a real game uses (residents, routines, homes, place names), a roster chosen from the seed
  (`CastLifecycleState.choose_initial_roster(rng=...)`, repeatable), the player's slot reserved, and no human. It also returns
  the authored facts a writer may use (`CastNote`: name, role, motive, personality type), the place names and the clock.
- `backend/app/sim/llm_writer.py` `LLMWriter`: two model calls per scene through the provider switch (`llm/chat.py`). One
  writes the prose from a neutral prompt (setting, the two residents' authored facts, a format rule; no drama nudges,
  those are the P-12 knobs), one reads it back as JSON (a summary and feeling changes). A reply that is not JSON becomes a
  summary-only update and is counted, never guessed. Feeling changes are clamped to 0.3; the runner still rejects any that
  name someone who was not in the scene. The runner is synchronous and the shared HTTP client belongs to one event loop,
  so the script runs the runner on a worker thread and `bridge_chat` hands every call back to the main loop.
- `SceneRecord.text` keeps the prose (the rubric scores prose, not the summary).
- The script prints `HARD CAP n model calls, this run needs up to m` before anything starts and refuses a run whose need
  (`2 x days x scenes-per-day`) exceeds `--call-cap` (default 20); the writer enforces the cap again before each call. A run
  that resolves to OpenAI, including the silent fall-back when no Gemini key is set, is refused without `--allow-openai`.
  A failed call is reported as a failure and scores nothing.
- Artifacts: `data/season_runs/<stamp>/season.jsonl` (gitignored): `run`, `scene` (prose, summary, applied feeling changes,
  rejections), `day`, `state` (relationships at the end) and `rubric` rows.

Limits of this baseline writer, on the record: the prompt carries no earlier scenes and no relationship state, so a
scene cannot build on the last; every resident pair that shares a room can meet (no camera ranking, P-13); feeling
changes go to an in-memory table, not the character graph (P-10); a scene can invent a consequence (for example someone
announcing they are leaving) that the engine does not act on.

### Season baseline (P-06, run 2026-10-01)

Every later stage must beat this. Run: commit `f97068f`, `python -m scripts.run_season --days 2 --scenes-per-day 3
--seed pilot-1 --model gemini-3.5-flash-lite`, story `six_strangers`, provider Gemini + Jev (both free), 12 model calls,
6 scenes written, 0 invariant violations, 0 rejected updates, 0 unparsable extractions. The default `gemini-3.8-flash` was
over its free quota (HTTP 429) at the time, so the run used the fall-back model the game itself uses on a 429. Artifacts:
`data/season_runs/baseline-pilot-1/season.jsonl` (gitignored, local). Rubric scores are on the 2 to 10 scale.

| Level | Verdict (mean) |
|---|---|
| Day 1 scenes | Consider 7.8 · Pass 5.8 · Recommend 8.2 |
| Day 1 | Pass 5.7 (E2 4, E3 2, others 6 to 8) |
| Day 2 scenes | Recommend 8.5 · Consider 6.2 · Recommend 8.2 |
| Day 2 | Consider 6.7 |
| Season | Pass 2.0 (R1 to R5 all 2) |

What the numbers do and do not say. The baseline engine writes competent, in-character scenes (residents talk about their
authored jobs) but the scene-level verdicts flatter it: **all six scenes have the same shape** (two residents at a quiet
shared task, ending on a lingering touch of hands or an invitation to leave together), and four of them score Recommend.
A scene-level reader cannot see that repetition; it shows up only at day and season level (day 1 E3 "escalation" 2, season
2 on every item: nothing accumulates, because no scene knows about the earlier ones). The scene scores also come from a
rubric calibrated only on flat scenes (BL-96), so treat the upper range as unverified. The honest target for the next
stages is therefore the day and season rows and a repetition measure, not the scene verdicts.

### 12. Decision log and review answers

| Question | Answer / evidence status |
|---|---|
| Which plan leads? | This combined BL-39 is the master; BL-38 tracks open correctness work. No independent competing implementations. |
| Impressions versus appraisal versus drama? | Character appraisal proposes impressions; Bond alone applies; optional Standing records progression; DramaticPolicy selects admissible opportunities. |
| Who decides NPC behavior? | Owner chose hybrid extraction LLM + Jev proposals under character/engine constraints. Character objects still perform no provider I/O. **Built 2026-09-29 as a switch:** `NPC_DECISION_MODE` = `rules` (default) / `jev` / `compare`, Jev bounded by the rules; see [NPC_DECISION_MODES](JEV.md). First comparison: Jev is correctly ordered but very cautious (1 of 8 fixtures yes vs 6 of 8 for the rules); calibration is an open owner decision. |
| What gives if two seconds is exceeded? | The immediate target, not correctness/gameplay. Current speed is accepted; current two-game p50/p95 remains to be measured. |
| Which Jev tasks are calibrated? | Limited task/smoke evidence is not plan-wide calibration. Enable task by task after labeled/outage tests; deployed overrides were not inspected. |
| Quality floor without Jev? | Existing extraction proposal + safe deterministic checks, otherwise clarify/defer uncertainty; no third LLM. Full quality comparison remains unmeasured. |
| Fallback ceiling? | Owner accepted 5%; provisional O26a gate with zero critical source/consent errors. Not a measured result. |
| Who authors profiles? | Feature implementer owns defaults/mappings/drafts; D includes all 17 Terrace candidates and mystery compatibility. New significant lore needs review; neutral defaults support sparse characters. |
| Independent fixes? | Section 10 opening, addressed answers, receipts and continuity ship without waiting for all A–J. |
| Does hearing/contradiction prove truth/lying? | No. Testimony, belief, dispute, evidence and deliberate deception differ. First claim is history. |
| How are acceptance and narration aligned? | Scoped proposal, semantic checks before display, atomic effects/outcome/reply commit. No post-display act_confirmed patch. |
| Can panelists see hidden state or make extra calls? | No. Camera/public evidence and their own appraisals; local outline and existing response call. Default off elsewhere; developer arena off for review. |
| Missing thinking dots? | Source confirms they exist. Preserve and lifecycle-test; add correlated client/server measurement. True streaming is deferred. |

Historical questions/evidence remain in the first review and second review. They are audit records, not competing instructions. Design choices are resolved; implementation, calibration, migration and hosted proof remain open.

---

## Social engine v2: causality, knowledge, and consequential relationships

> **Target-design authority, 2026-09-28:** [consolidated BL-39](SOCIAL_ENGINE.md) supersedes conflicting future architecture here. Preserve this document's implementation history and P-series acceptance evidence; it does not authorize a second relationship writer or deterministic-only replacement of hybrid NPC judgment.

Status: engineering target with an initial implementation in progress, 2026-09-26. Section 18 records implemented slices and remaining acceptance gaps. Scope: a reusable engine for Terrace and other social stories, with epistemic infrastructure reusable by IU. No four-week deadline is enabled by this proposal.

### 1. Architectural decision

Refactor the existing world model incrementally. Keep its deterministic world, routines, cast lifecycle, graph, persistence, and retrieval infrastructure. Introduce typed domain operations and one authoritative commit boundary. Do not build a second simulator or turn every resident into a separate autonomous LLM agent.

The central contract is: **an utterance is an event; its content is a claim, not automatically a fact.** NPC actions use their own information. World feasibility uses actual state. The drama selector controls which feasible opportunity receives attention, not what becomes true.

### 2. Current code and gaps

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

### 3. State contracts

All IDs below are scoped by game instance; names are presentation only. Records carry schema version. Durable history lives in storage; bounded objects/graphs and derived retrieval caches remain in memory, following the existing epistemic storage policy.

#### World events and proposals

`ActionProposal(id, actor, kind, arguments, source_turn, evidence_spans, expected_revision)` describes an attempted action. It grants no authority by itself.

`DomainEvent(id, sequence, turn_id, operation_id, minute, kind, actor_ids, place_id, payload, cause_ids)` describes a validated occurrence. Examples: `InvitationProposed`, `InvitationAccepted`, `AttendanceRecorded`, `UtteranceDelivered`, `MessageRead`, `RelationshipDecision`, `DepartureCommitted`.

Reducers apply each event exactly once. IDs derive from session/turn/operation, not a global counter or unstable model ordering. Corrections append superseding events; they do not rewrite witnessed history. Mechanical outcomes replay from accepted events; reproducing the original prose or model inference is not required for replay.

#### Epistemic objects and edges

* `Proposition(id, subject, predicate, value, valid_time, qualifiers)` represents a claimable statement. Negation and temporal scope are explicit. Not every proposition has a known truth value.
* `Observation(id, observer, event_id, channel, perceived_details, minute)` records what was perceivable, not everything in the event. Seeing two people leave together does not establish a date.
* `Assertion(id, speaker, proposition_id, stance, utterance_event_id)` records what someone asserted. Stance can affirm, deny, hedge, or quote.
* `Transmission(id, assertion_id, sender, recipients, channel, delivery_event_id, parent_transmission_id, disclosed_source)` records how information travels. Engine provenance is separate from the source the speaker claims.
* `BeliefEdge(owner, proposition_id, stance, confidence, support_ids, opposing_ids, revised_at)` records a character's current assessment. Confidence is their certainty, not an omniscient truth probability.
* `DisclosurePolicy(content_id, owner, permitted_audience, secrecy_commitment_id, classification)` separates protected content from ordinary fictional secrets.

Private confessionals/system material are never eligible for NPC transmission. A fictional secret may be disclosed by a character who knows it and chooses to betray confidence. Do not reinterpret the existing `private` boolean as leakable during migration; ambiguous legacy content stays protected.

The service API is `observe`, `assert_claim`, `transmit`, `revise_belief`, `perspective`, `can_disclose`. No retrieval result may directly call a canonical-truth setter. Unknown authored knowledge defaults to unavailable for consequential claims unless an explicit acquisition path or authored knowledge permission exists; inferred prior dialogue is testimony, not proof of acquisition.

#### Agreements, relationships and intentions

`Agreement(id, proposer, participants, activity, place, time_window, participant_decisions, status, obligations, source_event_ids, supersedes)` is authoritative. States: proposed, accepted, declined, cancelled, completed, breached, expired. Rescheduling creates a revised proposal requiring affected parties to accept. Partial attendance resolves individual obligations rather than marking every participant guilty.

Unspecified dates remain tentative windows. "Sometime this week" must not silently become a precise appointment. A proposal reserves no exclusive slot; acceptance checks schedules and travel. Intentional double-booking is allowed as a recorded conflict, never silently repaired. Breach requires a specific due obligation and evidence; co-presence alone does not prove a cooking lesson occurred.

Relationship graph edges remain directional. Keep trust/affection; introduce attraction only where enabled, and represent compatibility through supported preference matches/conflicts rather than an arbitrary accumulating score. Attachment and jealousy can be derived appraisals initially. Exclusivity is a bilateral agreement, not a high numeric edge. NPC-to-player feelings cannot be inferred from player-to-NPC affection. Repeated equivalent compliments have bounded effects.

`Intention(owner, objective, target, priority, prerequisites, deadline, status)` supports romance, work, friendship and independence. `ConflictThread(id, participants, cause_ids, stakes, stage, unresolved_questions, cooldown, resolution_ids)` links drama to history. Neither record may expose hidden motives in player UI.

### 4. Turn transaction and narration

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

### 5. Gossip example and non-negotiable invariants

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

### 6. NPC initiative and drama selection

Use a small action library: invite, accept, decline, keep/cancel a commitment, ask, disclose, conceal, confront, apologize, withdraw, pursue a personal milestone. Each action declares preconditions, knowledge requirements, duration, effects, visibility and cooldown. Story data supplies preferences and boundary weights; no Terrace names in engine branches.

Candidate utility combines personal-goal progress, expected social benefit, obligation pressure, risk and effort. The NPC estimates social outcomes using its beliefs, not the full relationship graph. Preferences and risk tolerance create different rival behavior. Seeded bounded randomness breaks ties; record selected candidates and reasons for replay.

The drama selector ranks only feasible candidates using unresolved stakes, urgency, player relevance, novelty and time since last focus. It cannot create evidence, alter affection, force agreement, or teleport witnesses. Start with at most one major complication per scene, configurable cooldowns, and quiet/payoff scenes after escalation. Mandatory consequences outrank drama pacing. Rejection must remain possible; repair must remain possible; success need not trigger immediate sabotage.

### 7. Scalability and observability

* Index observations/claims by owner, proposition, root source and time; agreements by participant and due boundary; conflicts by participants and status.
* Process a priority queue of due boundaries rather than every simulated minute. Generate encounter candidates from co-location and active intentions rather than all character pairs.
* For long skips, coalesce uneventful routine intervals but retain ordering for causal events. Bound work and resume internally at a checkpoint; never silently discard due obligations to satisfy a cap.
* Keep active residents and relevant unresolved threads hot. Archive departed residents while preserving references, provenance and unresolved obligations.
* Batch semantic extraction and narration where views permit it. No per-resident LLM call every turn. Use isolated calls only where sensitive perspective decisions require them; measure cost and latency before expanding.
* Maintain bounded perspective retrieval. Filter authorization before ranking and again before rendering. Summaries preserve claim/source IDs and uncertainty; they cannot turn rumor into fact.
* Record debug receipts: proposed/rejected actions with reason codes, event IDs, actual time interval, witnesses, belief changes, source chains, relationship causes, scene selection and state revision. Private debug access stays separate from the player API.
* Measure p50/p95 latency, model calls/tokens, snapshot size, active-claim count, event queue work and retrieval latency across 6/30/100-character fixtures. These are test sizes, not performance promises.

### 8. Package boundaries and rollout

Keep `world_model/turn.py` as a facade. Introduce pure modules gradually: `commands.py` (schemas/validation), `reducer.py` (event application), `epistemics.py` (claim/observation graph service), `agreements.py` (state machines), `intentions.py` (candidate generation), `appraisal.py` (caused relationship changes), `drama.py` (selection only), `scene_contract.py` (perspective projection). Put durable transaction/outbox handling at the existing service/persistence boundary, not inside pure world-model functions.

1. **Authority and receipts:** versioned proposals/events, idempotency, one clock, read-only projection, causal audit. Existing behavior remains behind adapters. Gates: retry/concurrent-turn tests and save/resume replay.
2. **Epistemic spine:** observation/assertion/transmission separation and owner-filtered views. Start with conversation and gossip. Gates: secrecy, false rumor, circular corroboration, disjoint perspectives. Benefits IU testimony immediately.
3. **Agreements and calendar:** replace paired promise ownership; validate attendance, reschedules, conflicts and time skips. Gates: cooking promise versus concert across save/resume; no automatic acceptance or fulfillment.
4. **NPC intentions and appraisal:** directional attraction/trust, autonomous invitations and distinct rival policies. Gates: equal opportunity across rosters, independently motivated actions, no privileged knowledge in planning.
5. **Conflict pacing and endings:** escalation/repair linked to causes; bilateral relationship/departure state machine. Gates: explicit mutual decisions, current eligibility, atomic cast changes, rejection and solo endings.

Roll out per capability and per story, pinned to session schema/ruleset version. New sessions opt in first. Migration converts unambiguous legacy promises to tentative agreements, preserves uncertain provenance as legacy/unknown, and never retroactively grants secret knowledge. Use one canonical writer with read adapters rather than long-lived dual writes. Shadow planning can compare candidate actions without applying them. A v2 save must not be loaded by a v1 writer; rollback routes compatible sessions or performs an explicit tested downgrade, never just toggles a flag.

### 9. Proof, not only prose quality

Deterministic/property tests cover event idempotency, revision conflict, time monotonicity, participant-specific obligations, missing witnesses, delivery, source loops, schema migration and replay hashes. Metamorphic tests remove a witness or change an unrelated secret and assert that an uninformed NPC's available knowledge/planning input does not change. Model-level tests separately measure whether generated dialogue respects those views.

Scenario replays cover: rejected date; rival invitation while player is away; intentional double-booking; honest cancellation; lie discovered through a real witness; rumor disproved but trust still damaged; reconciliation; mutually agreed departure; cast replacement; interruption during a long skip. Run the same seeds over both player-gender paths and varied active rosters. IU gets a testimony contradiction and false-date-evidence fixture.

Engagement evaluation uses blinded equal-length comparisons plus human review: meaningful choices, differentiated NPC aims, consequences recalled, conflict resolution, repetitive filler and agency violations. More arguments or longer replies are not success metrics. Mechanical invariants gate release even when an engagement judge prefers the broken version.

### 10. Backlog mapping

Existing [BL-30](../backlog/BL-30-narrative-clock-vs-game-clock.md), [BL-31](../backlog/BL-31-36-41-iu-mystery.md), [BL-33](../backlog/BL-33-terrace-win-path-hosted.md), BL-34 (now part of [BL-86](../backlog/BL-86-headless-season-simulation.md)), [BL-35](../backlog/BL-35-45-terrace-plans-and-promises.md), [BL-36](../backlog/BL-31-36-41-iu-mystery.md), and [BL-37](../backlog/BL-37-terrace-repetition-and-stock-lines.md) retain their scopes. The cross-cutting transaction and epistemic work is tracked in BL-38. Implement slices with regression evidence; this design does not close those items.

### 11. Implementation sequence and shared release contract

Implement **Phase 1 first**, including its scenario harness. Follow 1 → 2 → 3 → 4 → 5. Phase 5 has separate pacing and ending gates so one cannot conceal a failure in the other. These expand the five phases in §8; they are not additional competing roadmaps. Each phase must deliver a usable vertical slice through state, persistence, projection and hosted behavior before the next phase depends on it. All phases below are planned, not completed.

Every phase uses three layers of proof:

1. **Deterministic domain scenarios:** explicit starting state, commands, clock advances and expected event/state assertions. No model required; failures must reproduce from a fixture and seed.
2. **Integration and model scenarios:** the real turn pipeline, extraction, persistence and prompt projection. Record structured proposals and actual replies. A deterministic test cannot establish that the model obeys a knowledge boundary.
3. **Hosted beta acceptance:** verify the deployed commit, exercise the relevant scenario in the real UI/API, inspect the response and authorized debug receipts, save/reload, and repeat the consequential action. A mocked response or successful health check does not prove gameplay.

Store reusable fixtures and expected invariants in the repository's existing test layout, with a scenario ID, story/ruleset version, initial state, seed, inputs, checkpoints and assertions. Store raw live transcripts/debug artifacts using the existing evidence policy, outside committed runtime data. Reports reference the artifact location and deployed SHA. Expectations assert meaning and IDs, not exact generated wording.

Common exit requirements: required scenarios pass; no unexplained critical invariant failures; existing relevant regression tests and required repository checks pass; migration/retry tests pass; hosted proof exists for the changed behavior. An attractive transcript cannot override a mechanical failure. Record any deferred scope in its existing backlog item and do not label the whole phase complete if a required gate is missing.

For stochastic behavior, use a fixed declared seed matrix and paired baseline/candidate runs, reporting all outcomes rather than rerolling until success. Pin acceptance thresholds before reviewing candidate results. Hard invariants require zero violations in the test matrix; this is evidence within that matrix, not a claim of universal correctness. Engagement scores are secondary evidence with sample size and uncertainty reported.

### 12. Phase 1 — Authoritative turns, clock and replay

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

### 13. Phase 2 — Observations, testimony, beliefs and gossip

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

### 14. Phase 3 — Agreements, schedules and consequential choices

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

### 15. Phase 4 — Independent NPC aims and relationship appraisal

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

### 16. Phase 5 — Conflict arcs, pacing and validated endings

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
| P5-08 Alternate outcome | Player ends a relationship (the player cannot leave alone; BL-46). | Coherent recorded state without falsely declaring romantic success. |
| P5-09 Long skip ending | Advance across an agreed departure boundary and another scheduled event. | Deterministic ordering, correct interruption/ending, no scenes after the terminal transition. |

**Hosted proof:** finish one genuine mutual-departure run, one refusal/solo run and one repair arc; test reload at the last decision. Perform a separate adversarial false-victory attempt. Use both player-gender paths and more than one active roster across the acceptance set.

**Exit / handoff:** both 5A and 5B pass. Blinded review must show meaningful choices and remembered consequences without increased epistemic/agency violations. Full implementation does not require every proposed activity template, but does require the complete validated gameplay loop. Owners: BL-33, BL-37 and existing agency work; do not close unrelated remaining scope merely because this phase ships.

### 17. Cross-phase acceptance campaign and completion record

Carry earlier phase scenarios forward as regression gates. After Phase 5, run three sustained campaigns: (A) honest courtship with a rival and mutual departure, (B) double-booking plus circulating misinformation and repair or breakup, (C) IU conflicting testimony and new corroborating evidence. Use at least 20 consequential player turns per social campaign unless a valid terminal state occurs earlier; this minimum provides continuity coverage, not a statistical quality guarantee. Include save/resume and a multi-day skip. Record every player input, returned segment, state delta, knowledge acquisition and unresolved commitment at checkpoints.

Run synthetic 6/30/100-character scale fixtures after each phase that changes planning, retrieval or persistence. Compare against the recorded pre-phase baseline for p50/p95 latency, model usage, state growth and processed event counts. Set numerical budgets from the Phase 1 baseline before later phase implementation; do not invent acceptable regressions after seeing results. Synthetic no-model throughput and real-model latency must be reported separately. Confirm that long skips and archived characters preserve provenance without unbounded hot-memory growth.

Each phase completion entry appended below must contain: status (planned/in progress/blocked/complete), implementation commits, exact enabled scope, deterministic/integration scenario IDs and results, hosted SHA and artifact references, migration/rollback result, performance comparison, remaining backlog items, and the next permitted phase. A checked box without evidence is not a completion record. For a rollback, re-run the compatible-session routing scenario and preserve committed outcomes rather than loading newer saves into an older writer.

**Current status:** A cross-phase implementation is in progress. The initial implementation covers event IDs and cause links, durable request/reply persistence, observed speech and gossip provenance, canonical agreements, rival invitations, conflict focus, and explicit relationship/departure decisions. The entire acceptance campaign above has not passed; the numbered phases are not marked complete.

### 18. Cross-phase implementation record, 2026-09-26

The current change set adds an idempotent event adapter, a versioned world-model snapshot, and an epistemic ledger with observations, assertions, transmissions, and root sources. Gossip can retain the original source across relays, and a second independent account can remain distinct. Protected confessional content and unheard remote speech are excluded from ordinary housemate memory. The session save stores state and the exact reply under the same request ID; a retry can return that reply. This is a useful compatibility bridge, not a full event-replayed transaction: world operations still have multiple mutation paths, the JSONL side log is separate, and cross-worker optimistic concurrency is not implemented.

Plans now have canonical proposal/decision/status records while legacy promise memories act as projections. Due scenes do not automatically fulfill agreements; accepted plans can expire, and completed actions require direct player performance. NPC testimony alone is insufficient. Rival invitations and a conflict focus are bounded and deterministic. The romance path records independently stated relationship and departure choices, validates the eligible present cast, supports withdrawal and solo departure, and bases victory on saved state. A successful ending removes the couple from the world and records a terminal cast departure for the partner without recruiting a replacement after the game ends. These literal speech adapters do not yet cover all natural paraphrases or a fully typed action/consent protocol.

The remaining mandatory acceptance work includes one canonical reducer for all consequential writes, same-turn scene validation before presentation, revision-checked commit/replay across workers, source reliability and contradictory belief support, delivery/read gating for all channels, detailed obligation attendance, complete NPC intention and activity libraries, stronger dramatic cooldown/arc logic, IU evidence-ledger integration, time-skip interruption, 6/30/100-character scale runs, and the three hosted campaigns in Section 17. Keep BL-33 through BL-38 open until their own acceptance criteria pass. Test and hosted evidence for this change set should be appended here after verification rather than presumed from unit tests.

The first hosted slice ran on beta `1045464`: 1,232 local pytest cases passed (one expected failure), 10 frontend tests passed, and local desktop Chromium/iPhone WebKit/standalone WebKit feature checks passed. Ten fresh Terrace and ten IU turns on the hosted API are documented in SOCIAL_V2_HOSTED_PLAY_2026_09_26.md (removed; see git history). They found an unparsed natural wait, a false 7 pm narration after a 24-hour skip, unknown speaker dialogue in an empty room, a bystander volunteering for a private plan, player-feeling narration, invented IU testimony provenance and a rediscovered clue. The corrective natural-wait parser and social scene guard have local tests; their hosted results require a subsequent SHA. This run does not satisfy the Phase 1–5 exit gates or the 20-turn/scale campaigns in Section 17.

The next IU source-check slice grounds generated first-hand player attributions in utterance events observed by the speaking NPC. Questions and denials are excluded as support for a claimed assertion. When the model invents a source, the dialogue admits uncertainty rather than treating its assertion as world truth. This is limited string-level repair; the canonical assertion/transmission projection, contradiction journal and deliberate-lie representation in Phase 2 remain open. Do not mark P2 complete until those scenarios and the hosted IU campaign pass.

The corrective beta `c1050c9` passed 1,234 local pytest cases (one expected failure), the hosted natural-wait/empty-room replay, IU reinspection replay, and hosted desktop Chromium/iPhone WebKit/standalone WebKit UI flows. Its successful replay is limited to those specific cases. Source attribution, broader player agency, direct-answer pacing, one canonical event reducer, replay/concurrency and Section 17's full campaigns are still open.

The next corrective slice (implementation in progress, 2026-09-26) addresses observed boundaries: ISO story start times silently falling back to January 1 (IU now starts January 22, after its January 14–15 death clue), explicit first-person duration/same-day waits and wrong leading scene-clock narration, a narrow narrator-agency/echo filter, and explicit self-named second speakers placed inside another cast member's dialogue beat. This is a defect slice, not completion of any phase. The phase checklist and final-playthrough gate are tracked in the backlog (BL-88) and section 11a above; all phase acceptance boxes remain open until the scenarios and hosted campaigns pass.

Phase 1 continuation adds an additive `game_sessions.revision` compare-and-swap under SQLite `BEGIN IMMEDIATE`. A turn reads the stored revision, refreshes stale in-memory state, and can only commit its state/reply against that revision; a concurrent winner makes the loser retry from the new state. This addresses the cross-worker overwrite slice of P1-02. The full transaction/outbox, deterministic event reducer, fault injection and replay gates remain open.

---

## Social Mode Design — Ensemble Slice-of-Life Games

> **What this doc is for:** Describes the optional `mode` object in story JSON, how it's wired into the prompt engine, and how to author a Terrace-House-style ensemble/slice-of-life game using the existing engine primitives. Edit this doc when the `mode` schema changes or a new mode `type` is added.

### 1. Why this exists

The engine's four primitives (State, Time, Incentives, Constraints — see `design/ROADMAP_NOT_BUILT.md (game design systems)`) were built and battle-tested against murder-mystery stories: one central NPC (`is_main: true`), a handful of suspects, a truth to uncover. Nothing about those primitives is mystery-specific, but nothing previously told the storyteller model *not* to treat every game like a mystery either — the base prompt talks about "the investigation," "corrections," "canon," etc. in ways that read fine for a murder mystery and slightly oddly for a slice-of-life house sim.

The `mode` object is a small, purely additive prompt layer that gives the storyteller model the right tone and conventions for non-mystery ensemble games, without touching anything else. If a story doesn't declare `mode`, nothing changes — this is the backward-compatibility guarantee, and it's enforced by a test (`test_mode_context_section_byte_identical_prompt_for_existing_story` in `tests/backend/app/engine/test_prompt_builder.py`).

#### Terrace relationship objective (2026-09-25)

Terrace now has a player-facing `goal.win_text_rule` and optional `mode.romance_goal` with `enabled`, `partner_gender: "opposite_player"`, `rival_gender: "same_as_player"`, and `outcome: "leave the house together"`. The mode prompt projects only active cast members matching the player-selected gender into potential partners and rivals; queued cast stays hidden. Author-time `characters[].gender` is retained in the canonical session story config for that projection. A date, friendliness or a player's wish does not satisfy the goal. There is no `win_detection.regex`: the opted-in runtime records a mutual romantic relationship and separate first-person player/NPC departure decisions. The conservative literal decision adapter and final cast transition still need broader validation (BL-33).

The world-model offscreen encounter resolver can weight a feasible rival/partner encounter toward a plan or growing affection when the player has already shown interest in that partner **and** the rival has independent interest. The event still requires co-location, availability, elapsed time and the seeded outcome draw; it commits through the existing event, memory and relationship-edge path. In a shared on-screen scene, an interested rival can issue a recorded invitation; the target's answer remains pending until accepted. BL-34 tracks broader independent aims, variation and outcome calibration.

### 2. The `mode` schema

Optional top-level key in story JSON:

```json
"mode": {
  "type": "social_sim",
  "setting": "shared_house",
  "open_ended": true,
  "cast_size": 3,
  "confessional": {
    "enabled": true,
    "convention": "The player may address an unseen listener directly as a private aside (e.g. prefixed like a diary entry, or wrapped in [confessional: ...]); other characters never hear or react to these asides."
  },
  "daily_rhythm": [
    "Mornings are rushed — someone's always looking for their keys.",
    "Evenings are the real social currency of the house.",
    "Weekends drift."
  ],
  "narrator_asides": {
    "enabled": true,
    "style": "Every so often, step outside the scene for a brief, wry, warm aside in the voice of an unseen documentary crew quietly observing the house, then drop back into the scene."
  }
}
```

Field-by-field:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `type` | string | yes (to activate the layer) | Names the mode. Currently one value is given special phrasing: `"social_sim"`. Any other non-empty string still activates a generic fallback sentence (`This story runs in '<type>' mode (<setting>).`) so the schema is forward-compatible with modes not yet designed. |
| `setting` | string | no | Free-text setting label, e.g. `"shared_house"`. Rendered in prose with underscores turned to spaces. |
| `open_ended` | bool | no | When true, the layer tells the storyteller there's no fixed win condition and to focus on daily life/relationships instead of a goal. This is prose-only — it does not by itself omit `goal`/`win_detection`; you still omit those keys yourself (see §4). |
| `cast_size` | int | no | Recurring-cast size, surfaced in prose ("The cast includes N recurring housemates..."). Purely descriptive. |
| `confessional.enabled` | bool | no | Turns on the confessional-convention paragraph. |
| `confessional.convention` | string | no | Custom convention text. If omitted while `enabled: true`, a sensible default sentence is used. |
| `daily_rhythm` | string[] | no | Up to a few flavor lines describing typical daily texture (used for prompt tone only, not simulated). |
| `narrator_asides.enabled` | bool | no | Turns on the narrator-aside instruction — an occasional, brief moment where the *storyteller itself* (not the player) steps outside the scene into a wry, external observer voice (e.g. a documentary-crew aside), then returns to the scene. Added for `six_strangers`; introduced additively the same way `confessional` was, so stories that omit it (including The Common Room) render byte-identical prompts to before this field existed — see `test_mode_context_section_narrator_asides_absent_by_default` in `tests/backend/app/engine/test_prompt_builder.py`. |
| `narrator_asides.style` | string | no | Custom description of the aside's voice/style. If omitted while `enabled: true`, a sensible default sentence is used. This is deliberately distinct from `confessional`: confessional is the *player* addressing an unseen listener in-scene; `narrator_asides` is the *storyteller* briefly breaking from the scene in its own voice. |

Implementation: `backend/app/engine/prompt_builder.py::_mode_context_section(state)`. It reads `state.story_cfg["mode"]` and returns `""` when the key is absent/empty/malformed — so a story with no `mode` key, an empty `{}` `mode`, or a `mode` missing `type` all fall back to zero-length output.

Wiring: `backend/app/api/prompt_engine.py::_canonicalize_story_cfg` copies the raw JSON `mode` object into `story_cfg["mode"]` (it was previously not in the whitelist of keys copied into `story_cfg`, so this had to be added explicitly), and `_seed_noncanonical_story_details_to_transient` excludes `mode` from the generic "dump unknown top-level keys into transient/FAISS-ish story details" path so it isn't double-injected in raw JSON form alongside the dedicated prose layer.

### 3. Prompt layer order

The mode layer sits in `system_prompt()` immediately after `base_prompt` (the storyteller contract / narrator-voice rules) and before the scene brief:

1. Base prompt (narrator contract, style, canon-correction rules)
2. **`mode_context` (NEW — this layer)**
3. Scene brief (`SCENE BRIEF` — cast present, time, location)
4. Knowledge stack (retrieved FAISS/BM25 chunks + labeled epistemic stack)
5. Relationship context (character graph prose)
6. Character self-knowledge (identity facts — see §5 for the ensemble caveat)
7. Truth override (debug mode only)

This mirrors the position described in `documentation/design/PROMPT_PIPELINE.md` / the MEMORY "System Prompt Layers" list — logically it belongs right next to the base prompt/style layer, since it's tone-setting context the model should internalize before anything else, and its position is now also reflected there and in `design/PROMPT_PIPELINE.md (message flow)`.

`build_messages()`'s `return_debug=True` path also exposes it as `prompt_layers["mode_context"]` for the debug UI, alongside the existing `base_prompt`, `character_identity`, etc. keys.

### 4. Mapping engine primitives onto ensemble/slice-of-life play

No new mechanics were built. Everything below reuses primitives that already exist for the mystery genre:

| Primitive | Mystery usage | Ensemble/slice-of-life usage |
|---|---|---|
| `world` locations | Crime-scene rooms, offices | House rooms (kitchen, living room, bedrooms, a quiet balcony) |
| `character_self_knowledge` (per-character `self_knowledge`) | The one central NPC's identity facts | Each present housemate's own identity facts (see §5 — per-character, gated by scene presence for non-main characters) |
| `epistemic_seed.canonical_facts` | Case facts, alibis | House lore/history everyone knows (`known_by: ["all_characters"]`), plus each housemate's private secret (`known_by: [<that character's key>]`) that the player can discover through conversation |
| `epistemic_seed.belief_seeds` | Suspects' self-serving beliefs | Housemates' private, sometimes self-deceiving beliefs about themselves or the house |
| `relationships.edges` | Suspect↔victim/detective trust-fear-affection-suspicion | Housemate↔player bonds **and** housemate↔housemate bonds (NPC-NPC edges), so the graph is genuinely ensemble, not hub-and-spoke |
| `opening.text` | The crime discovery scene | Move-in day — first impressions of the house and every housemate |
| `goal`/`win_detection` | A confession goal and regex | Omitted for an open-ended game. Terrace now has a romance/departure goal but no regex win detector; BL-33 tracks the validated ending. |
| `motive` (character field) | Why a suspect might have done it | Repurposed as a personal-life-goal/insecurity summary for authoring flavor (surfaced via the same transient story-detail path suspects already use — it isn't read by any dedicated prompt layer for either genre) |

### 5. `character_self_knowledge` is per-character, gated by scene presence (BL-07, resolved)

This used to be a single-character limitation — flagged and deliberately deferred as BL-07 while building the `mode` layer — and has since been fixed. Documented here for anyone reading older commits/discussions that reference the old constraint.

**Current behavior:**
- Each `characters[]` entry may declare its own `self_knowledge: [...]` array (parsed by `Character.from_dict()` in `state.py`, round-tripped by `Character.to_dict()`, and preserved through `StoryDefinition.from_dict()`'s normalization pass).
- `backend/app/api/prompt_engine.py`'s two character-roster-construction sites (new-game path in `_chat_handler_impl`, restore path in `_try_load_session_from_db`) apply this precedence: **a character's own authored `self_knowledge` always wins when present.** The top-level story-wide `character_self_knowledge` array remains a fallback used ONLY for whichever character is `is_main` and has no per-character `self_knowledge` of its own — this is exactly the backward-compatible path that keeps all 5 pre-existing mystery stories (which only ever set the top-level key) unchanged.
- `_character_identity_section()` in `prompt_builder.py` injects one `### CHARACTER IDENTITY — {name}` block per qualifying character:
  - The **main character's** block is always included when they have `self_knowledge`, unconditionally (not gated by scene presence — a ghost NPC who isn't tied to a location still gets their identity section, same as before this change).
  - **Every other character** (not main, not `"player"`) who is currently present in the scene (per `_get_people_present_keys(state)`) AND has non-empty `self_knowledge` gets their own block too, in deterministic (sorted-by-key) order.
- Net effect: a story where only the main character declares `self_knowledge` produces byte-identical prompt output to before this change (regression-tested against `iu_murder_mystery`). A story like The Common Room, where every housemate now authors their own `self_knowledge`, gets a genuinely ensemble identity layer — present housemates each speak their own first-person truths, not just the one the loader happened to assign `is_main`.

The Common Room now demonstrates this directly: Mina, Dae-ho, and Priya each have their own `self_knowledge` array on their `characters[]` entry. Mina still ends up `is_main` (via the existing BUG-13 loader fallback, since none of the three declare `is_main: true` — `is_main` remains a narrative "focal lens" concept for scene-brief phrasing, but is no longer the *gate* on who gets an identity section). Dae-ho and Priya's inner lives are carried by their own `self_knowledge` now, in addition to:
- their `motive` field (authoring flavor, same mechanism suspects use),
- their private secret as an `epistemic_seed.canonical_facts` entry scoped to just them (`known_by: ["daeho"]` etc.), discoverable through play — self_knowledge is about identity/personality/history, not a place to spoil the secret fact itself,
- their `belief_seeds`,
- and their relationship edges (including the two NPC-NPC edges).

**Touches:** `backend/app/engine/state.py` (`Character`), `backend/app/api/prompt_engine.py`, `backend/app/engine/prompt_builder.py`, `backend/app/stories/6_common_room/common_room_story.json`.

### 6. Confessional convention: prompt convention, not a bracket command

Per `documentation/ai_learnings_mistakes/AI_CREATE_NEW_FLAG.md`, a "bracket command" (`[D]`, `[M]`, `[C]`, ...) is a mechanical toggle/one-shot action intercepted in `prompt_engine.py` *before* any LLM call, and it requires matching frontend wiring (`COMMAND_PATTERNS` in `frontend/index.html`) so the client recognizes it and skips normal message handling.

The confessional aside doesn't need any of that. The player is still writing a normal in-character message; they're just narratively framing part of it as an aside to an unseen listener (a documentary-crew fourth wall, a diary entry, whatever framing the convention text describes). This is exactly the kind of "instruction to the storyteller model about how to *interpret* ordinary text" that a prompt layer is for — no parsing, no frontend change, no new state. **Decision: confessional is implemented purely as a prompt convention** (the `mode.confessional` block in §2), not a bracket command. This was chosen because:
- it requires zero frontend changes (simpler, less surface area to maintain);
- it composes for free with the existing OOC `(...)`/`[...]` convention (OOC breaks the fourth wall entirely and talks to "the author"; confessional stays in-scene and talks to an unseen in-universe listener — different registers, both handled by prompt instructions rather than parsing);
- a mechanical bracket-command version would need a real command grammar (start/end markers, escaping) to know where the confessional aside begins and ends inside a longer message, which is unnecessary complexity for what is fundamentally a tone instruction to the model, not a state change.

### 7. How to author your own `social_sim` game

Using `backend/app/stories/6_common_room/` (**The Common Room**) as the reference:

1. **Folder & files**: `backend/app/stories/<n>_<slug>/<slug>_story.json` + `<slug>_world.json`. Use the next available numeric prefix (check the highest existing one) or a descriptive folder name. The declared `id` field (not the filename) is what the content registry (`story_loader.py::build_story_registry()`) keys on — see `AI_GAME_STRUCTURE.md`.
2. **World**: model your rooms as locations with short travel edges (1-3 minutes within a house). Tag at least one location `"private"`/`"quiet"` for confessional-style private conversations (see `rooftop_balcony` in Common Room's world JSON).
3. **Cast**: author a manageable recurring ensemble (Common Room uses three NPCs; Six Strangers uses six), each with a `role`, a `motive` (repurposed as a personal-life-goal/insecurity summary, not a crime motive), and no `is_suspect`/`tells` (those are mystery-genre vocabulary and are optional fields — `Character.from_dict` in `backend/app/engine/state.py` doesn't require them). If you don't set `is_main` explicitly on anyone, the loader's BUG-13 fallback assigns it to the first character listed — but that no longer determines who gets an identity section (see §5), so list order only matters for that narrative "focal lens" framing, not for self_knowledge.
4. **`self_knowledge`**: give each character you want an identity section their own `self_knowledge` array on their `characters[]` entry — 2-4 first-person "You are..." identity facts, same style as the mystery stories. Non-main characters only surface their block when they're present in the current scene (see §5); the main character's block is unconditional.
5. **`epistemic_seed.canonical_facts`**: house lore everyone knows (`known_by: ["all_characters"]`) plus one private-secret fact per character (`known_by: [<key>]`) for things the player should discover through conversation, not be told upfront.
6. **`relationships.edges`**: seed every housemate→player edge, and at least one NPC-NPC edge, so `ROOM DYNAMICS` prose reflects real ensemble relationships when multiple characters share a scene.
7. **`opening.text`**: write real, evocative move-in-day (or equivalent) prose — this is a creative deliverable, not boilerplate.
8. **Goal and ending**: an open-ended game omits `goal`/`win_detection`. Terrace now authors `goal.win_text_rule` and `mode.romance_goal`; it still omits regex `win_detection` because a string match cannot prove mutual departure. BL-33 tracks the remaining validated endgame transition.
9. **`mode`**: add the block from §2 with `type: "social_sim"`. Optionally add `narrator_asides` (see §2) if your game wants the storyteller to occasionally step outside the scene in its own wry, external-observer voice — `six_strangers` no longer uses it (its studio panel speaks only in the finale); The Common Room does not use it and is unaffected (backward-compatible, see the field's test above).
10. **Test**: the parametrized `test_every_catalogued_story_initializes_end_to_end` in `tests/backend/app/api/test_prompt_engine.py` picks up every catalogued story. For open-ended stories, test that `win_condition_detected` remains false without `win_detection`. For Terrace, assert the authored goal and active, gender-eligible prompt context while arbitrary prose still cannot declare victory. Add per-character identity/voice checks when authoring an ensemble.

### 8. Explicit limitations (read before assuming more exists)

- **No quest/schedule/resource engine.** Chore wheels, jobs, daily routines, etc. are narrative content NPCs can reference in conversation — they are not mechanically simulated (no calendar, no NPC schedules, no resource meters). See `design/ROADMAP_NOT_BUILT.md (game design systems)` and `documentation/backlog/`.
- **Relationship drift is asymmetric.** Only player→NPC relationship edges are updated by structured turn extraction today; NPC→player and NPC↔NPC edges are seeded at game start but not mechanically driven during play (only the main NPC has a narrative-tag-driven affection path). Tracked in `documentation/backlog/`.
- **`character_self_knowledge` per-character injection is scene-presence-gated for non-main characters** (§5, BL-07) — a housemate's own identity block only appears when they're present in the current scene; the main character's block is unconditional. This bounds prompt length but means an absent housemate's self_knowledge contributes nothing to that turn's prompt (their `motive` + canonical facts/belief seeds/relationship edges still shape their characterization when they're the one being discussed but not present).

### 9. Six Strangers: Tokyo cast adaptation (2026-09-18)

`7_six_strangers` now authors all 17 members from the user-supplied
`terrace_house_boys_girls_in_the_city_season1.md` dossier (sections 1–2 and
4.1–4.6): Makoto Hasegawa, Minori Nakada, Yuki Adachi, Mizuki Shida, Tatsuya
"Uchi" Uchihara, and Yuriko Hayata. The dossier supplied the public cast
identities, occupations, observational format, and Higashi-Gotanda / Shinagawa,
Tokyo setting. Six are active at game start and eleven are stored as upcoming
members in season-entry order. Later episode outcomes are not a script for
play. Dialogue, inner lives, local venues, and the detailed floor plan are
fictional game content, identified as such in the story metadata.

The opening takes place in September 2015. The player is one of six residents
as one of the six residents, sharing the gender-matched bedroom; the five NPC
housemates
remain NPCs (`mode.cast_size = 6`). This replaces the old four fictional
housemates and empty-sixth-bedroom legend. Two opposite-gender housemates from
the randomized opening roster greet the player at `front_entry` (see §10); the
first greeter is the opening focal NPC and other housemates are encountered
naturally throughout the house. Initial relationships represent new acquaintances, with
no predetermined romance or later-show knowledge. Every NPC has a distinct
identity block, private concern, belief, and relationships in both directions
with the player. Private concerns are invented, character-scoped information,
not biographical claims about the real cast.

The world includes shared bedrooms, an open kitchen/living/dining space, rooftop,
garage with two shared cars, and reachable neighborhood, station, cafe, salon,
and dance studio locations. World edges are directed: each walkable connection
is authored in both directions. The PNG map is a schematic of this game world,
not an architectural reconstruction of the filming location. Public map text
does not expose private character concerns. The existing `social_sim` mode
provides observational pacing. (Mid-game panel-style asides were removed from Terrace; the panel speaks only in the finale.) The generic cast lifecycle, persistence, scene filtering, replacement
operation, and private Cast menu are documented in `design/SOCIAL_ENGINE.md (cast lifecycle)`.
Automatic committed-intent detection and next-day scheduling remain the next
integration phase.

Start a new game to use the revised roster and locations. Existing sessions
retain their saved characters and world snapshots; this content change does
not migrate old saves. The story ID and title remain `six_strangers` / Six
Strangers.

### 10. Engine-backed opening welcome party (2026-09-24)

Any story can decide, in the engine, who is physically with the player when the
game starts by authoring `opening.welcome_party`:

```json
"opening": {"welcome_party": {"size": 2, "gender": "opposite_player", "exclusive": true}}
```

| Field | Meaning |
|---|---|
| `size` | Number of greeters (default 2). |
| `gender` | `any` \| `opposite_player` \| `same_as_player` \| `M` \| `F`. Uses each character's authored `gender` (`"M"`/`"F"`). If too few match, the party is filled from the other candidates. |
| `exclusive` | Default `true`: every other NPC in the player's start location is moved out, so the people present are exactly the party. |
| `fallback_location_id` | Where displaced NPCs go; defaults to `cast_lifecycle.initial_active_location_id`. |

`backend/app/engine/opening_scene.py::stage_opening_scene()` runs at new-game
time after the cast lifecycle and start locations are seeded. It chooses from
the active roster (lifecycle stories) or all NPCs, then writes real state:
the greeters' `character_locations` = the player's start location, the focal
`main_character_id` = the first greeter, and `GameState.opening_cast`. Because
of that, every consumer agrees without special cases:

- authored opening `segments` resolve `@greeter` / `@second` to `opening_cast`;
- the per-turn people-present computation (from `character_locations`) lists
  exactly the greeters in the first SCENE BRIEF;
- `opening_scene_brief()` adds a first-reply-only line telling the storyteller
  to continue the conversation with those greeters;
- `opening_cast` and `main_character_id` persist in the saved state, so a
  restored session keeps the same room and focal lens.

Terrace in the City authors `gender` on all 17 members and
`{"size": 2, "gender": "opposite_player", "exclusive": true}`: a male player is
greeted by two women, a female player by two men. Stories without
`welcome_party` keep the previous random-greeter behavior.

---

## Cast Lifecycle Design

> **What this doc is for:** Defines the reusable, story-authored system for games whose recurring characters enter, leave, or temporarily become unavailable. Edit this document when lifecycle states, slot rules, transition validation, prompt eligibility, persistence, or player-facing roster behavior changes.

### 1. Goal and boundary

The engine needs to support a stable catalog of authored characters while only a
subset participates in the current world. Six Strangers is the first consumer:
the source format keeps six NPC residents in three men and three women slots,
then fills a vacated slot with the next eligible resident from the same group.

The engine vocabulary is deliberately generic. It knows `slot_groups`,
capacities, membership status, transition events, and replacement policies. It
does not know gender, a house, television seasons, eliminations, or Terrace
House. Another story can use the same system for a rotating expedition crew,
school cohort, sports lineup, workplace team, or political cabinet.

Lifecycle changes are world-state changes. Only engine validation may apply
them. A narrated departure without an applied transition does not remove a
character; an upcoming character mentioned by name does not become active.

### 2. Static authoring schema

Stories opt in with a top-level `cast_lifecycle` object:

```json
{
  "cast_lifecycle": {
    "enabled": true,
    "arrival_location_id": "front_entry",
    "replacement_policy": "same_slot_next",
    "departure_policy": "committed_intent",
    "slot_groups": {
      "men": {"capacity": 3, "label": "Men's resident slots"},
      "women": {"capacity": 3, "label": "Women's resident slots"}
    },
    "members": {
      "makoto": {"slot_group": "men", "initial_status": "active", "sequence": 0},
      "arman": {"slot_group": "men", "initial_status": "upcoming", "sequence": 1}
    }
  }
}
```

Rules:

- Every lifecycle member key must match one `characters[].key`.
- Every referenced slot group must exist and have a positive capacity.
- Initial active membership cannot exceed a group's capacity.
- Sequence values must be non-negative integers and unique within a group.
- `arrival_location_id` must exist in the story world.
- Stories without this object behave exactly as they do today: every authored
  character is active and scene-eligible.
- The authored character catalog contains identity and private knowledge for
  all potential members. Lifecycle status determines whether any of it may
  enter a prompt or player-visible output.

### 3. Runtime model

`GameState.cast_lifecycle` holds a `CastLifecycleState` when the story opts in.

#### Statuses

| Status | Meaning | Scene eligible | May become active |
|---|---|---:|---:|
| `upcoming` | Authored but has never joined this run | no | yes |
| `active` | Current participant/resident | yes | already active |
| `inactive` | Temporarily unavailable, with accumulated state retained | no | yes |
| `departed` | Permanently left under current story rules | no | no by default |

Each member runtime record contains:

- `status`
- `slot_group`
- `sequence`
- `activated_minute`
- `departed_minute`
- `departure_reason`

The lifecycle also stores append-only transition history. Each record contains
an event id, event type, departing member if any, arriving member if any,
vacated slot group, reason summary, minute, and resulting statuses. Event ids
make retries idempotent.

### 4. Validated operations

The lifecycle module is a pure domain service with primitive JSON round trips:

- `active_ids(slot_group=None)`
- `is_scene_eligible(character_id)`
- `vacancies(slot_group)`
- `next_up(slot_group)`
- `activate(character_id, minute)`
- `deactivate(character_id, minute, reason)`
- `depart(character_id, minute, reason)`
- `replace(departing_id, arriving_id=None, minute, reason, event_id)`

`replace` validates the complete change before mutating anything:

1. Lifecycle is enabled and the event id has not already been applied.
2. Departing member exists and is active.
3. The member's slot group exists.
4. The requested arrival is upcoming, belongs to the same slot group, and does
   not violate capacity; otherwise choose the lowest-sequence eligible member
   when policy is `same_slot_next`.
5. Arrival location exists.

After domain validation, the API integration helper removes the old member's
runtime location and transient markers, places the replacement at the authored
arrival location, and changes the focal character if the prior focal member
departed. Relationship and epistemic history are retained rather than deleted.

### 5. Trigger policy

The authored interactive policy is `committed_intent`:

- A resident can discuss uncertainty without triggering departure.
- A player cannot evict an NPC through ordinary dialogue.
- The lifecycle domain and API integration helper are implemented and tested.
- Automatic prose-to-transition extraction is the next integration phase. It
  must propose a departure only when the previous assistant reply contains a
  clear first-person commitment to leave, and may apply at most one event per
  turn.
- Replacement selection is deterministic story data; arrival can occur in the
  same transition response or after an authored vacancy beat, according to the
  story's configured timing policy.

The lifecycle service does not parse prose. Future authored schedules, quest
rewards, administrator tools, or simulations must call the same validated
operations rather than adding alternative mutation paths.

### 6. Prompt and knowledge eligibility

Lifecycle filtering is defense in depth:

- Character mention detection ignores upcoming, inactive, and departed members.
- People-present calculation includes only active members at the current
  location.
- On-call and scene speaker markers for ineligible members are ignored and
  cleared during transitions.
- Identity, belief, private fact, relationship, room-dynamics, and scene-cast
  prompt layers include only active characters unless a dedicated historical
  reference explicitly requests departed public information.
- Upcoming names and biographies never appear in player-visible cast output.
- The character graph retains all nodes and accumulated edges; rendering filters
  by eligibility.
- The turn extractor's `allowed_character_keys` catalog
  (`prompt_engine.py`'s `character_key_to_name`) is filtered through the same
  `_cast_scene_eligible` predicate before being sent to the LLM-backed
  extractor — an upcoming/departed character's key and real name are not
  handed to the extractor as a candidate, matching every other eligibility
  gate in this section (2026-09-19 fix; previously this one call site built
  the catalog from the full unfiltered roster).
- A canonical fact whose *only* `known_by` owner is a still-`upcoming`
  character (e.g. that character's private concern/biography) is excluded
  from both `_knowledge_chunks_from_state` and `_canonical_facts_for_speaker`
  in `prompt_builder.py`, even if something in the scene would otherwise
  surface it as "known by" the speaker. Facts shared with `all`/
  `all_characters`, or owned by at least one already-active character, are
  unaffected. Departed characters' facts remain visible to characters who
  already knew them — this filter only blocks a character who has *never yet
  arrived* from leaking their private facts early.

- The speaker contract's `Cast IDs` list and the structured-output
  `speaker_id` enum (`dialogue.py` `_contract_cast_ids`) contain only
  scene-eligible members. Before 2026-09-24 all 17 Six Strangers names were
  listed, and the model placed unarrived residents in the story ("Yuto should
  be back from practice").
- Authored self-knowledge lines that name a member who is not scene-eligible
  (for example "no predetermined feelings for Hikaru") are withheld until that
  member arrives (`prompt_builder.py` `_without_absent_cast_names`).
- Resident whereabouts are authoritative prompt data. For resident-slot
  stories the scene brief lists every active resident as man or woman with
  their room (`_resident_whereabouts_line`), and the per-turn user header
  repeats it next to the player's message (`_resident_whereabouts_header`),
  saying "Nobody is out, away, upstairs" when everyone is present. The system
  block alone did not work: live gpt-4o-mini runs still invented absences and
  people ("Keiji and Taro went out"). With the header and the opening change
  below, 5 of 5 live runs answered truthfully.

The authored `is_main` flag remains a starting preference, not permanent
membership. If that member departs, the runtime focal moves to the replacement,
or to the deterministic first active character when the queue is empty. Static
authoring flags are not mutated.

For a lifecycle-enabled story, the main character's identity block
(`_character_identity_section`) and "focal lens" framing
(`_storyteller_scene_section`'s scene brief) are now also gated on the main
character actually being present in the current scene
(`_main_character_scene_eligible`, `prompt_builder.py`), not injected
unconditionally. Non-lifecycle stories are unaffected — they keep the legacy
always-inject-main behavior (an always-present ghost/narrator NPC not tied to
a location remains supported). This fixes the audit-reported bug where an
explicit solitary scene ("I go to the rooftop alone") still had the focal NPC
narrated as present, because the identity/framing layers ignored scene
presence entirely for the main character.

### 7. Persistence and compatibility

State JSON adds `cast_lifecycle`. The existing `main_character_id` acts as the
runtime focal pointer; restore replaces it when its member is no longer active.

No database schema migration is required because session state is stored as
JSON. Restore rules:

- A saved lifecycle snapshot is authoritative; later edits to queue order do not
  rewind a run.
- Saved snapshots validate against their recorded members and history. Catalog
  reconciliation for characters added after a save is a future schema migration
  and is intentionally not implicit.
- A lifecycle-enabled story save created before this feature initializes from
  current authoring: the original configured cast is active and the rest are
  upcoming.
- Stories without lifecycle configuration treat all characters as active.
- Unknown saved ids remain in the snapshot for audit/history but are never scene
  eligible if the current story no longer authors them.

### 8. Player-facing roster

A read-only cast view may show:

- current active residents the player has met,
- vacant slot labels,
- departed residents the player previously met.

It never reveals upcoming members or queue order. The normal player interface
does not include an eviction control. If a story later allows player-managed
lineups, that is an explicit story policy using the same validated transition
service.

### 9. Six Strangers rules profile

The supplied Boys & Girls in the City dossier establishes these format rules:

1. Six NPC residents are active: three men and three women.
2. They share a furnished Tokyo house and coordinate two shared cars.
3. They continue outside jobs, school, training, creative work, friendships,
   and dates.
4. There are no imposed challenges, eliminations, prize, fixed romance, or win
   condition.
5. Cooking, chores, work, outings, quiet time, friendship, and romance emerge
   from choices. Invitations and affection require consent.
6. A resident may voluntarily leave after clearly deciding they are ready; no
   vote, failure, or romantic outcome is required.
7. One new resident fills the vacated same-gender slot. Arrival order follows
   the supplied season chronology; timing and every relationship remain
   emergent.
8. Housemates do not know private concerns, future entrants, or televised
   outcomes. Audience asides cannot leak that information.

The current game makes the player one of the six residents, sharing the
gender-matched bedroom. Whether that player
occupies a lifecycle slot is a product
decision recorded in the story's profile, not an engine assumption.

Opening placement (updated 2026-09-29): the five randomly selected NPCs and
player immediately reserve all three men and three women slots. The Terrace
story's reusable `opening.arrival_sequence` starts the player and one random
opposite-gender resident in the living room at 3 pm; the four other selected
residents remain unplaced, hidden from player-facing cast data, and unable to
speak until their timed entrances. Ordinary conversation stops at the next
arrival minute (Terrace: 8, 18, 28, 38, about two to three exchanges apart) so the residents enter one at a time. Explicit
waits can cross several entrance times. Entrances update tracked location,
first-meeting state and save data; the capacity and replacement queue never
change during the reveal. The story does not author fixed
`world.character_start_locations`, since the opening roster is randomized.

### 10. Verification contract

Implemented tests cover schema validation, initial capacity, deterministic
next-up selection, wrong-slot rejection without partial mutation, idempotent
event replay, departure/location cleanup, arrival placement, focal replacement,
state serialization, roster privacy, legacy behavior, and the full Six
Strangers invariant of 17 authored characters with six active and eleven
upcoming before any transition. The automatic committed-intent trigger and
next-day scheduler require extractor and time-boundary tests when that phase is
implemented.

Live beta verification for this phase must exercise initial roster privacy and
ordinary scene behavior. A later live pass must exercise the automatic
departure trigger, next-day replacement, and server-backed resume after that
scheduler exists.
