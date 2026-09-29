# BL-39 — Canonical proposal: reusable character-centered simulation engine

- **Type:** feature / engineering plan
- **Found:** 2026-09-27; consolidated by owner direction on 2026-09-28.
- **Severity:** high: unreliable outcomes, attribution and character agency undermine gameplay.
- **Status:** proposed, not implemented or calibrated by this documentation change.
- **Authority:** the single target architecture and roadmap. Replaces competing architectural portions of BL-38 and original BL-39. [BL-38](BL-38-social-engine-authority-and-epistemic-transactions.md) remains an open correctness tracker, not a second design.
- **Navigation:** sections 1–3 ownership; 4–9 contracts; 10 release units; 11 acceptance; 12 owner answers.

## 1. Product goal

Build enjoyable, heightened, plausible drama around characters with different beliefs, tastes, voices, commitments and aims. Humor and surprising choices are welcome. A character can ditch work for a date and worry about their boss; the choice needs a possible route, believable motivation and consequences. Consistency supports drama, not a requirement to choose the dullest sensible action.

Use BL-39's Character → Heart → Bond model and perceive → appraise → feel → want → act loop. BL-38's atomic turns, provenance, consent, context isolation and migration become required contracts. Do not build competing appraisal engines or relationship stores.

[Terrace House](../game_modes/TERRACE_HOUSE.md) provides content: six residents from the authored 17-character pool, earned mutual departure, personal standards, NPC couples, director warning after two other couples leave and cut after three, and optional commentary. The mystery reuses characters, knowledge, evidence, questions, agendas and agreements. No story ID, character name, gender rule, romance threshold or panelist identity belongs in generic engine logic.

Owner choices: **hybrid LLM/Jev social judgment; at most two LLM calls per turn; gameplay before latency optimization; provisional 5% visible fallback ceiling.** Developer arena judging stays off for playtest review.

## 2. Code reuse and migration seams

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

Target APIs below are proposed. Older [social-v2](../reference/SOCIAL_ENGINE_V2_DESIGN.md) and [character redesign](../reference/CHARACTER_WORLD_MODEL_REDESIGN.md) documents remain history/fixture references; this proposal governs conflicting future design.

## 3. Object ownership

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

## 4. Hybrid judgment, standing and knowledge

### Hybrid choices and drama

The extraction LLM interprets input and proposes acts, semantic appraisals and nuanced choices. Jev assists supported classification, relevance and candidate evaluation. Reconcile into typed proposals with actor, source spans, evidence IDs, uncertainty and reasons. Neither provider directly writes saves.

Construct feasible/admissible options **before** ranking. Standards and participant consent constrain acts; a threshold is eligibility, never automatic acceptance. Semantic proposals, preferences and DramaticPolicy then select plausible dramatic, quiet or comic responses. Local math enforces bounds and can rank; it is not the sole authority for nuanced foreground choices. Never reroll refusal until acceptance wins. Candidate order and paraphrased duplicate beats must not change seeded outcomes.

Private input stays actor-scoped. The extraction LLM may receive the public scene plus one designated actor's private decision view; private-informed decisions from that call are only for that actor. Others use independently scoped Jev tasks or explicit local policies/defer. One prompt containing all private minds is not isolation. Response generation receives public material and disclosure-safe SpeechPlans, not raw private bonds. No per-NPC LLM fan-out.

Before cutover compare hybrid, legacy and local utility on identical recorded work/date, refusal, tentative offer, jealousy, deception and comic/quiet fixtures. Hold knowledge and eligible options constant; record reasons, disagreement, enjoyment and invariant failures. Hybrid is already selected; comparisons validate/tune it. Extra offline model experiments need an explicit budget; this document authorizes none.

### Standing, impressions and closed conditions

TrackSpec(id, tiers, daily_gain_cap, repeat_decay, neglect_decay), Tier(id, floor, ceiling, gate), Standing.apply(...), Requirement(...) and Condition.evaluate(Viewpoint) are pure typed components testable without providers or a running world.

Gain order: suppress when closed; apply same-tag/day diminishing returns; limit by remaining daily allowance; traverse only open tier gates; clip to reachable ceiling and discard surplus. Count actual accepted gain against the daily cap. Losses apply while closed and can lower tiers. Decay is an explicit ordered clock event, not a read-time side effect. Define stable ordering for simultaneous events.

Persist proposed/applied effects, cause/effect IDs, actor, target, dimension/track, tag, channel, simulation minute, sequence and policy version. Replay chronological **applied effects**, not uncapped proposals. Bound in-memory impressions with checkpoints and retained audit/cause references. Never recompute old effects under new tuning. Route legacy deltas through this writer once; never apply both a delta and derived impression for the same effect.

Closed Condition kinds: BelievedAttribute, EventCount, AgreementCount, Feeling, StandingAtLeast, TierReached, Knows, DaysKnown, DaysInTier, CounterAtLeast, Not, All, Any and typed committed-act/agreement predicates. No executable story expressions. Each kind has validation/explanation.
- Character Viewpoints see only their knowledge; engine truth Viewpoints are privileged and never enter prompts.
- Return true / false / unknown. Not(unknown) stays unknown, never a dealbreaker. Belief conditions require established belief, not testimony alone.
- Tier gates cap progression; dealbreakers close tracks under configured evidence/reopening rules. Neither overrides withdrawal.
- Stage is derived. Reject contradictory gates, invalid ranges, missing references and unreachable endings. Numbers remain tuning hypotheses.

### Testimony, belief, lies and disclosure

Persona records SelfClaim(key, value, utterance_id, audience, asserted_at, valid_time). First claim is immutable **history**, not eternal truth. Changed circumstances, corrections and conflicting claims coexist. Profile truth seeds NPC self-knowledge, not knowledge for everyone.

Hearing creates attributed testimony/transmission. Belief acceptance is separate appraisal using evidence, reliability and skepticism. Contradiction creates dispute, not proof of lying. Distinguish suspicion, perceived deception, engine-established deliberate deception and honest mistakes. Consequences follow a character's justified perception, with uncertainty and repair.

Actual source, claimed source, transmission root and intent are distinct. Deliberate lies can name false sources without creating source events or laundering hearsay into truth. Circular gossip has one root, not independent corroboration. A believed lie may pass a preference gate; later evidence may change belief and decision.

DeceptionProfile controls tells by skill/stress/context. Generally hint, but nervousness is not proof and skilled liars need not visibly confess. Voice-only calls cannot reveal visual tells. DisclosurePolicy filters explanations before generation; hidden requirements do not leak because they influenced a verdict.

## 5. Atomic turns, speech and inference

### Transaction boundary

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

### Character speech

ConversationState records source questions, addressees, pending/resolved/deferred state and interruptions. Resolve only through the addressee's answer, refusal, uncertainty or acknowledged deferral. Chatter is not an answer; multiple questions remain separately traceable.

VoiceProfile controls register/directness/expressiveness/length/examples. Voice changes preserve mechanical outcomes. CharacterContext contains perceived evidence and permitted plans, not a global notebook. Scene validates identity, introductions, encounters, presence and channels. Narration avoids invented player actions/emotion, repetitive decoration and fake return greetings.

Consequential attribution needs an admissible source set before semantic matching. Calibrate negation, pronouns, reported speech, qualifications, ambiguity and omitted answers; a keyword/event ID alone is insufficient. Unsupported claims use approved safe wording. Prefer in-character uncertainty/refusal in the normal response call; canned recovery is exceptional and measured.

### Provider budget and quality

At most **two LLM provider attempts per gameplay turn**, including retries/background/shadow/translation: extraction assisted by Jev, then response. Reserve one attempt for response. No third verifier, repair, panel or per-character call. Receipt replay and deterministic engine previews need none.

TurnInferenceBudget counts attempts across callers, propagates cancellation/deadlines and separately bounds/batches Jev through existing registry/provider seams. Unsupported tasks abstain; only independent inputs run concurrently. Late results cannot commit after cancellation. Do not impose a two-second timeout or silently alter operational timeouts.

Repository defaults gate Jev through TYPESAFE_ENABLED with JEV_ENABLED_TASKS empty and JEV_SHADOW_SAMPLE_RATE zero; deployed overrides were not inspected. Existing small hand-built cases/smoke evidence do not calibrate every proposed relevance/attribution/answer task.

Calibrate each enabled task on labeled examples, including missing/truncated/corrupt evidence, ambiguity, false sources and denials. Report false acceptance/rejection/abstention. Test enabled, absent, timeout and malformed modes. With Jev unavailable, reuse extraction proposals plus deterministic checks where safe; otherwise clarify/defer uncertainty. No third LLM. Both games must remain playable under this fallback; that quality floor is not yet demonstrated.

**O26a rollout gate:** at most **5%** visible canned/constrained recovery among eligible gameplay turns, reported per game and separately for consequential scenes. Predeclare scenario mix/denominator; use at least 100 eligible turns per enabled game and report counts/uncertainty. Sample size is an engineering starting point, not a measured pass. Track invisible provider fallback, canned substitution, clarification, abort/error and dropped responses separately; aborting more turns cannot conceal poor quality. Compare voice/answer coverage with baseline. Critical source/consent violations remain zero. If the gate fails, fix context/false rejection or retain prior safe scope; never weaken validation to reach 5%.

## 6. Agreements, travel, time and independent life

AgreementBook owns participant roles, individual decisions, terms/revisions, conditions, invitations, amendments and fulfillment. Keep a two-party convenience API, not a second book. Benefiting from a promise does not imply acceptance; nobody consents for another. Private-plan joins require appropriate participants' new agreement.

Distinguish proposed, tentative, confirmed, withdrawn, cancelled, fulfilled, missed and excused. “Maybe after work” stays tentative. Character-owned PlanExpectation may be optimistic/mistaken without changing terms. Hopeful attendance can cause disappointment, not fabricated breach. Clarification updates expectations without rewriting history.

Body, Activity, Schedule and Route own availability, preparation, departure and arrival. Acceptance is a plan, not relocation. Future/conditional requests do not move anyone now. Charge travel once in input order: wait-then-go differs from go-then-wait. Attendance is not completion; record shared activity/witnesses. Consequences apply once, only to observers/informed actors.

Before skipping important player-known events, preview **all** affected known events in parentheses, tentative plans labeled: “(You will miss your date with Yuki and the tentative rehearsal with Mako. Continue?)”. Require revision-bound explicit confirmation. Stale previews refresh; decline advances no time; duplicates advance once; ordinary dialogue is not approval. Hidden events stay hidden. Player↔engine control messages are parenthesized and excluded from NPC memory.

One simulation clock processes commitments, routes, decay and opportunities chronologically. Moderate, tunable autonomy is default. More simulated elapsed time permits causal chains/butterfly effects, not merely bigger random rolls. Equivalent partitioned waits preserve opportunity scheduling; changed input can cause divergence. App-closed wall time does nothing.

Agenda combines social and career/personal aims. On/offscreen actions share consent/feasibility with bounded work and actor cooldowns; attention does not freeze others. Jev can assess scoped options; routine/offscreen scheduling uses documented local policies without per-tick LLM calls. NPC couples need both decisions, not high scores alone. Disinterest/inaction remain valid. Nobody plans from another's private feelings.

EvidenceEntity exposes actual inspect/request-footage/calendar/witness affordances. InvestigationTask persists pending/denied/completed state and evidence revisions. Missing records are not fabricated; unchanged surfaces do not yield repeat discoveries. Notebook remains player-scoped. Reuse the same event/evidence system, not a separate mystery truth store.

## 7. Endings, clocks and commentary

StoryRules declares typed Ending, Clock and Beat. Outcome is persisted with ending/reply in the same turn, evaluated once in declared priority order. Mutual departure requires an explicitly accepted agreement; refusal, withdrawal, solo exit and continued play differ. Replacement cast gets fresh identities/private state. Adapt supported existing outcomes first; scores/regex alone cannot manufacture consent.

Terrace: earned progression over simulated days, no fixed run timer or automatic day-one win. Director warns at two **other** happy couple departures and cuts at three; count unique committed departures excluding the player couple. Contact, counters and endings are reusable; numbers/romantic eligibility are content.

Panelists are commentator Characters. Camera channel admits filmed/public events under rules.filmed_places. Dossier contains only that evidence and each commentator's **own** appraisal. Subject impression logs, hidden standings/tiers, undisclosed conditions, memories and confessionals are not footage. Distinguish facts from opinions/inferences.

Retain named Terrace panelists and content modes: brief asides, ~300-word NPC departures, ~2,000-word finale on player win/cut/solo exit with authored no-skip presentation. These are content settings, not universal response lengths. Judge conduct, not identity/personal worth.

Build dossier and 5–7-segment outline locally; Jev may assist scoped assessment. The **same response LLM call** renders exit scene, all panel segments and verdict lines. No outline/segment/verdict call chain. Validate evidence support before commit; IDs alone are insufficient. Allocate explicit finale output allowance; measure latency separately; never split into extra calls. Failed/truncated finales follow safe failure, not partial publication of uncommitted consequences.

Commentary is intended enabled for Terrace and default off elsewhere. Developer arena is separate and off for playtest review. This proposal authorizes no arena run.

## 8. Configuration, authoring and migration

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

## 9. Thinking feedback and latency

Source confirms existing three animated dots in frontend/index.html: typing-indicator/typing-bounce, shown before fetch, hidden on success/error. Preserve them. This is not a new browser lifecycle/accessibility test. Verify pending/success/error/cancellation/navigation and reduced-motion/accessibility in the UI slice. Added engine status wording belongs in parentheses.

Reuse backend/app/utils/stage_timer.py::StageTimer and stage ledger. Add client monotonic timestamps for submit, indicator paint, response completion, first meaningful result paint and final typewriter completion, correlated by request ID/build/ruleset. Include commit and total duration; existing pre-commit latency log is insufficient. Record LLM/Jev attempts/timing, errors/timeouts/cost separately. No private dialogue in timing telemetry or subtraction of unsynchronized clocks.

[September 22 historical baseline](../archive/PHASE_0B_BASELINE_2026_09_22.json): only 24 Terrace requests; cohort p50 ~3.09–3.95 s, p95 ~4.44–5.87 s. Not a current two-game baseline or proof of two-second capability. Measure desktop/mobile, warm/cold and ordinary/skip/finale workloads with sample sizes, p50/p95/p99/max and failures.

Current speed is owner-accepted. Earlier 1–2-second wish is future optimization context, not an immediate deadline or reason to sacrifice gameplay/extraction/validation. dialogue.js::revealBlocks is post-response typewriter, not server streaming. True streaming is deferred until validated segments, committed consequential decisions, reconnect sequence IDs and durable receipts are designed.

## 10. Release units and roadmap

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

## 11. Acceptance contract

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

## 11a. Implementation status (2026-09-29)

Built and pushed to beta, one commit per phase, each hosted-checked: independent units O12 (`26053bb`), O15/O24 receipts (`3dbbe90`), O08 addressed questions (`a554c5a`), O11 continuity (`a8987f1`/`d8f6a03`); phases A endings/UI (`33e9106`), B character aggregate (`24cbca2`), C standing/conditions (`2a0f482`), D appraisal + 17 Terrace personality drafts (`55cad21`), E claims/beliefs/tells (`e76a2a3`), F typed social acts (`4ac255b`), G agendas/NPC couples (`f45cd60`), H clocks/director (`83276f4`), I studio panel (`619b3b4`, `d1e28df`), J seeded campaigns + tuning (this commit). Seeded campaigns prove an earned win on both gender paths, a director cut for a passive player and a day-one solo exit.

Not done, tracked: O09 narration agency (BL-29, owner: backlog), relationship-graph storage cutover (BL-40), IU investigation records/interviews (BL-41, owner content), invites/dates/travel and the "2 completed dates" romance gate (BL-35), panel asides and NPC departure segments, context-focus policies, true streaming, and the hosted 20-turn campaigns with human grading. Terrace personality numbers and the romance ladder are tuning drafts pending owner review. Target decisions use a documented local policy (standing + standards), not a model call.

## 12. Decision log and review answers

| Question | Answer / evidence status |
|---|---|
| Which plan leads? | This combined BL-39 is the master; BL-38 tracks open correctness work. No independent competing implementations. |
| Impressions versus appraisal versus drama? | Character appraisal proposes impressions; Bond alone applies; optional Standing records progression; DramaticPolicy selects admissible opportunities. |
| Who decides NPC behavior? | Owner chose hybrid extraction LLM + Jev proposals under character/engine constraints. Character objects still perform no provider I/O. |
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

Historical questions/evidence remain in the [first review](../research/ENGINE_PLAN_FIRST_REVIEW_QA_2026_09_28.md) and [second review](../research/ENGINE_PLAN_ROUND_TWO_REVIEW_2026_09_28.md). They are audit records, not competing instructions. Design choices are resolved; implementation, calibration, migration and hosted proof remain open.
