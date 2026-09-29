# BL-38 first-review Q&A record

Preserved 2026-09-28 to keep the implementation proposal navigable. This is a historical discussion record, not the current decision authority. In particular, the sibling checkout's BL-39 has now been inspected. See [second-review findings](ENGINE_PLAN_ROUND_TWO_REVIEW_2026_09_28.md) for conflicts and pending owner decisions, and [BL-38](../backlog/BL-38-social-engine-authority-and-epistemic-transactions.md) for the current proposal.
## 15. Review questions and answers — 2026-09-27

The supplied review refers to BL-38/BL-39. Only BL-38 exists in this checkout at review time; these answers update that document. “Answered” means specified, not implemented or performance-verified. Latest owner direction: current response speed is acceptable; prioritize gameplay, keep extraction LLM + Jev and response LLM within two LLM calls, measure latency, preserve thinking dots, and defer optimization/streaming. The earlier 1–2-second aspiration is not an immediate release gate. Playtest arena judging is off.

### Q1. How is phase 1 independently shippable, and what is the first commit that changes hosted behavior?

**Answer:** The earlier table did not define sufficiently small release units. Section 12 now separates them. The first planned visible fix is O12: reproduce and correct the IU authored opening/rendering defect, then deploy and inspect it. It needs no new object graph. The first engine behavior slice adds addressed-response tracking through existing character/prompt adapters. Phase 1 itself can independently ship durable request receipts and atomic session/outbox commit: a lost-response retry must return the same reply with no second clock charge or movement. Full reducer migration is a later release. These are prospective commits, not work already implemented in this documentation task.

### Q2. Are presets merely story-specific branching moved into YAML?

**Answer:** The precise promise is no executable rule branching on story identity, not genre-independent content. A mystery preset is allowed to author investigation capabilities and omit courtship templates. It expands into ordinary typed fields; runtime objects cannot inspect the preset name or switch implementations by it. No general-purpose rules DSL is needed initially. Section 1 and O16 require renaming and cross-preset equivalence tests, which would catch identity coupling rather than merely checking that code lacks a literal story-ID comparison.

### Q3. How many model calls does a six-character turn with two pending objectives and a skip preview cost?

**Answer (revised after the owner's Jev decision):** Use one extraction LLM call plus Jev assistance, then one response LLM call: at most two LLM attempts per gameplay turn, with Jev separately bounded/accounted. No per-character LLM, third verifier/repair/translation call or hidden background LLM call. Explicit control previews/replayed receipts need no model; ambiguous skip input can use the extraction stage before returning a preview. The earlier three-call design and one-call/local-extraction alternative are superseded. Batch Jev and overlap independent work, while preserving extraction-before-response dependencies.

Current code does not enforce that budget: inspection found extraction and optional extra calls. Section 5 requires accounting for/replacing them in the proposed profile. The user's latest instruction accepts current speed and defers latency optimization: measure the baseline, preserve gameplay and treat the earlier 1–2 seconds as an aspiration rather than a current gate. Future streaming gets a separate first-content metric.

### Q4. What exactly validates attribution and answers rather than hand-waving semantic correctness?

**Answer:** Section 5 specifies `SpeechGroundingValidator`: obligations, annotated speech plans, local reference/perspective/polarity checks and calibrated Jev checks where supported. No third LLM verifier call. When semantic coverage is inadequate, constrain consequential wording or keep the obligation pending; do not repeatedly regenerate. Explicit character lies remain claims, never fake historical sources. Jev results require evaluation and may abstain; using Jev does not establish comprehensive semantic understanding.

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

**User answer:** turn arena judging off for playtest review; it is not important here. No judging pilot is part of this task, and no arena run was enabled. The user-described arena-judge gameplay mechanic is intended for Terrace House for now and available but default-off in other games; it is not the developer build-comparison runner. Its existing implementation was not established by this inspection. Section 13 records this separation and keeps story capability flags independent of evaluation enablement. No latency benchmark, validator accuracy or enjoyment result is claimed by this proposal.

### Follow-up Q9. What does “response time” mean?

**Answer:** How long the player waits in real seconds after submitting an action before the game returns its complete reply. It is unrelated to story time. The user initially suggested 1–2 seconds, then clarified that current speed is good and gameplay should take priority. Measure it without making latency optimization a prerequisite.

### Follow-up Q10. Can we control latency enough to make it very fast, around 1–2 seconds maximum?

**Answer:** We control call count, model/provider selection, prompt/output size, local work, connections and retrieval; remote timing still varies. Preserve extraction LLM plus Jev, then response LLM, and measure the complete path. Latest direction is to prioritize gameplay because current speed is good, not to optimize to a hard two-second limit now. Streaming remains future work. No runtime optimization or benchmark was performed in this documentation update.

### Follow-up Q11. Can we use Jev extensively while keeping at most two LLM calls?

**Answer / owner decision:** Yes: retain an LLM for extraction with Jev assistance and an LLM for response generation. Use Jev preferentially for supported additional decision/checking tasks, batching independent work and bounding fan-out. Account for Jev and LLM calls separately; all contribute to latency/cost. Never route a failed Jev task into a third LLM call. This architecture remains required while speed optimization is deferred. Playtest arena judging stays off.

### Follow-up Q12. Are thinking dots already present, and can we measure latency while focusing on gameplay?

**Answer:** Yes. Source inspection found the three staggered animated dots in `frontend/index.html`, shown before the chat fetch and hidden on reply/error. Preserve that UI and verify other lifecycle/accessibility cases during browser QA; no new indicator implementation is needed from this finding alone. Server `StageTimer` instrumentation already exists. Section 5 adds client-to-server-correlated measurement requirements, separating request wait from typewriter reveal and future streaming. Current speed is accepted; gameplay is the priority, with optimization and true streaming deferred. This was a code inspection/documentation update, not a new hosted test or runtime change.
