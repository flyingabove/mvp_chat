# Engine plans: second review, historical evidence and resolution

**Resolved 2026-09-28:** the owner selected BL-39 as the combined master with BL-38 correctness contracts, hybrid extraction LLM + Jev choices under engine constraints, and a provisional 5% visible fallback ceiling. Origin/beta through 2cc10fe was pulled and merged in f3b8489. [Consolidated BL-39](../backlog/BL-39-character-centric-social-engine.md) now governs; its final section answers these questions. The findings below describe the earlier review state, not continuing implementation blocks. “Pending,” branch locations, and section numbers below are historical. No runtime calibration or implementation completion is implied.

2026-09-28. Documentation review only. No engine changes, model experiments, live configuration inspection or production migration. The sibling checkout was read, never edited. This report answers the seven second-round questions and records the conflicts that must be settled before implementing shared social state.

## 1. Which plan is authoritative, and do impressions replace appraisal or drama?

**Repository finding:** fetching `origin/beta` from the Codex checkout returned `44cb623`, containing the expanded BL-38 and no BL-39. The sibling `mvp_chat` local `beta` is five commits ahead, ending at `2694e95`; BL-39 is present there. Its blob is identical to the file at the supplied `9812df3` commit (`f7877e129c3e91f40078041dfd5d3e4a740140d9`). Thus the reviewer correctly found another plan, but local branch name `beta` and shared remote `origin/beta` are not the same version. Earlier “only BL-38 exists” statements were checkout-scoped and must not imply no other plan exists.

No commit date or document length establishes architectural authority. Confirmed owner decisions take precedence over both plans. **The overlapping replacement of Character/relationships must remain unimplemented until the owner selects the consolidation direction.** Independent defect fixes need not stop. Do not fetch/merge the sibling's work or choose its design silently.

Recommended reconciliation, awaiting owner choice:

- Use BL-39's `Character -> Heart -> Bond` vocabulary for character-owned social state, with scoped views over shared knowledge and agreements.
- Keep BL-38's atomic turn, source/consent, migration and object-context contracts.
- `Character.appraise(perception)` computes cause-linked `Impression` proposals. One `Bond.apply(impression)` writer updates the directional feelings and any enabled standing tracks. `CharacterGraph` becomes a read/command adapter to those same bonds during migration, never a second independently writable feelings store.
- `Standing` is optional, story-declared progression derived from accepted effects; it is not a replacement for all five feeling dimensions. `DramaticPolicy` ranks admissible opportunities and never applies feelings or standing. These are different responsibilities, not interchangeable scoring systems.
- Keep track/tier/clock/panel configuration optional. Terrace values and finale structure are content, not universal engine rules.

### Conflicts requiring reconciliation

| Area | Conflict | Recommended contract, not yet owner-approved consolidation |
|---|---|---|
| Relationship owner | BL-38 keeps the graph authoritative; BL-39 moves ownership into Bond and makes the graph a facade. | Exactly one writer. Initially wrap existing graph state; migrate ownership once, with graph reads/commands forwarding to the same state. Never two copies. |
| Standing arithmetic | BL-39 says capped sum of impressions but also discards gated surplus and applies chronological daily caps/decay. | Store raw proposed and accepted applied effects with policy/version and order. Replay chronological accepted effects; do not recompute standing by naively summing uncapped raw deltas. Summaries retain replay checkpoint and audit references. |
| Truth versus belief | BL-39 says a heard claim becomes belief and conflicting claims expose a lie. | Hearing records testimony; belief acceptance is separate. A contradiction establishes dispute, not necessarily deception. Intentional lie, honest correction, changed fact and mistaken source remain distinct. |
| First-claim lock | BL-39 locks the first self-claim. BL-38 allows time-indexed belief/correction. | Preserve first claim as immutable history, not eternal truth. Story rules may score inconsistencies, but mutable attributes need valid time and correction semantics. |
| Turn boundary | BL-39 describes pre-narration commits and evaluates endings after commit. BL-38 commits state/outcome/reply together. | Compute on a tentative snapshot; commit social effects, ending and delivered reply atomically. No displayed acceptance with an uncommitted outcome. |
| Call count | BL-39 panel uses outline -> segments -> verdicts LLM calls; owner later capped gameplay at extraction LLM + Jev and response LLM. | No extra per-turn LLM calls. Fold panel output into the allowed response call or propose an explicit separate experience for owner review. Do not quietly exempt finales from the cap. |
| Knowledge scope | Panel dossier uses bonds/impression logs, but commentators may know only filmed/public events. | Build the dossier from camera-visible evidence; hidden bond scores and private impressions are not footage. Panelists appraise their own view, not the subject's private mind. |
| Agreement shape | BL-39's shared two-party book versus BL-38's participant roles/amendments. | Two-party API can adapt to a general participant model; do not build two agreement books. |
| NPC decisions | Both plans describe deterministic character choice; explicit owner approval for replacing nuanced LLM choices is missing here. | Decide model before cutover; compare alternatives using identical fixtures and preserve one authority boundary. |

## 2. What gives when two seconds is exceeded? Is there a baseline?

**The immediate latency target gives, not facts, validation or gameplay quality.** The owner's latest instruction accepts current speed, prioritizes gameplay and defers optimization/streaming. The two-call architecture remains requested, but two seconds is not a new abort or release gate. Do not truncate useful dialogue or weaken extraction just to hit it.

There is a **historical**, small hosted beta benchmark, not today's p50/p95. Source: [raw September 22 baseline](../archive/PHASE_0B_BASELINE_2026_09_22.json) and [notes](../archive/PHASE_0B_BASELINE_NOTES_2026_09_22.md). Prefer JSON where notes differ:

| Scenario | Requests | p50 | p95 |
|---|---:|---:|---:|
| Terrace male, concurrency 1 | 6 | 3.666 s | 4.818 s |
| Terrace male, concurrency 3 | 6 | 3.738 s | 4.436 s |
| Terrace female, concurrency 1 | 6 | 3.090 s | 4.619 s |
| Terrace female, concurrency 3 | 6 | 3.954 s | 5.873 s |

24 requests total, including new-game requests; one game, short sessions, tiny groups, no representative long skips or error cases. These are round-trip measurements; they do not isolate ordinary dialogue or measure frontend text reveal. Six-sample tail estimates are weak. Do not pool percentile values or claim these describe the current build. A fresh benchmark has not run in this review.

Current source has extraction plus other stages instrumented in `StageTimer`. Extend request-correlated client timing, preserve thinking dots, and establish a comparable current baseline during ordinary hosted verification. Do not present the old Jev microbenchmark or a 1,000 ms timeout configuration as full-turn latency.

## 3. Which Jev tasks are calibrated? What happens with Jev off?

**No task-specific production-quality calibration is established by the evidence found.** There are useful small live tests and deterministic integration tests, which are not the same thing:

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| [Provider architecture](../reference/JEV_PROVIDER_ARCHITECTURE_2026_09_22.md), measured facts and sections 12–13 | September 22 Jev 1.13.0 microbenchmarks, about 190–227 ms p50 for small batches; 21 hand-built passing questions; movement/previous-scene routing smoke verification. | Held-out task error rates, robust calibration, CJK coverage, today's service performance or unlimited fan-out. Its own text says thresholds are guesses and labeled data remains required. |
| [Extractor redesign](../reference/JEV_EXTRACTOR_REDESIGN_2026_09_22.md) | Inline sample outputs for choice/score/noul and candidate-based task decomposition. | A representative confusion matrix or calibrated probability threshold for each task. |
| [Dynamic context design](../reference/JEV_DYNAMIC_CONTEXT_DESIGN.md) | Implemented optional relevance selection and deterministic fallback; design explicitly leaves shadow calibration open. | Proven relevance improvement across both games, calibrated attribution or answer checking. |
| Resolver/provider tests | Transport, flags, circuit breaker, output validation and fallback contracts. | Real-model semantic accuracy or user-perceived quality under outage. |
| Historical developer-arena pilot | Some evaluation of build comparisons, with known verbosity bias. | Calibration of extraction, attribution or answer-verification tasks. Do not reuse its scores as that evidence. |

`settings.py` defaults are off/empty; actual live environment overrides were not inspected. Therefore say **default-off**, not “proved no live task is running.” The current resolver uses legacy extraction when routing is off or the breaker is open, and falls back for failed critical decisions. That provides an existing mechanical fallback path; it is not proof the proposed engine has measured quality parity without Jev.

Required floor: every critical state/consent/source fixture passes with Jev enabled, disabled, timed out and malformed. Reuse the single extraction LLM result rather than invoking another fallback LLM. Optional relevance/initiative enhancements may degrade locally; critical unknowns remain unknown or ask for clarification. Compare direct-answer coverage, fallback rate, agency/source errors and character voice against the current baseline in both games. If an enabled task fails these gates, keep that task off; the whole game must remain playable. No claim that this quality comparison has already passed.

Task rollout needs a versioned evidence manifest: task ID, provider/model version, dataset and label versions, language/game strata, threshold policy, false accepts/rejects/abstention, and test date. New attribution and response-check tasks start uncalibrated, not enabled merely because Jev is fast.

## 4. What fallback rate is acceptable, and is it a gate?

**It should be a rollout gate, not just telemetry. The number requires a product decision/calibration.** Asked the owner for a provisional ceiling: 5% of eligible turns and no worse than baseline, 1%, or choose after reviewing examples. Five percent is a proposed starting point, not an approved requirement or measured rate. A 15% visible fallback rate cannot be called acceptable without review.

Measure separately: provider fallback that still yields normal dialogue, constrained sentence substitution, full canned response, clarification and dropped/aborted turn. Denominator for visible validator repair is all turns eligible for that validator, with per-game and critical-scene breakdowns; report repaired segments as well. Do not hide a high rate on dramatic scenes by averaging with greetings or excluding abstentions. Preselect fixtures and minimum sample coverage before a release judgment; small samples are inconclusive.

Keep factual/consent invariants hard gates independent of rate. When quality exceeds the agreed fallback ceiling, retain the last known safe policy/constrained feature scope and fix false positives or context quality; do not weaken validation or ship robotic dialogue as a successful feature. Prefer character-owned uncertainty/refusal acts realized in the normal response call; deterministic substitutions are exceptional recovery, not a normal voice system. The final visible text and committed speech records must agree. Do not spend a third LLM call repairing it.

## 5. Who authors profiles? What about unconfigured characters?

This was underspecified in BL-38. BL-39 explicitly includes authoring personality for Terrace's 17 characters in phase D; that is real content work, not automatically generated truth. The implementer migrating each enabled mechanic owns its minimal typed defaults/adapters, candidate content and fixture coverage. The owner reviews gameplay-significant choices (new dealbreakers, romance requirements, cut rules); LLM-suggested profile numbers are drafts, not approved lore.

Add an explicit content migration deliverable before enabling appraisal/choice changes:

- Preserve existing authored voice, self-knowledge, goals, tells and routines; do not require every author to populate every new numeric field.
- Missing fields use versioned conservative defaults: neutral tastes, no invented hard standards or deception motive, existing ordinary schedules, and the requested moderate autonomy. Optional standing tracks/panel stay disabled unless authored.
- Defaults must be mechanically safe and permit ordinary interactions; they are not promised to produce distinctive dramatic personalities. Verify unconfigured-character smoke scenarios in each game, then tune active casts for differentiation.
- Validate bounds, references, missing overrides and provenance at authoring time. Never let a migration silently invent a reason to reject the player.
- Compare before/after behavior for each enabled character. Roll out gradually; a full rewrite of both casts is not prerequisite for an opening or receipt fix.

## 6. Was replacing NPC judgment with utility math an owner decision?

**Not established by this conversation.** Object-centered design, deterministic state integrity and character-owned decisions do not by themselves authorize moving every nuanced social judgment out of the LLM. Older project design says characters do not call models, but a pure character object can still consume an application-provided proposal. Neither that architectural boundary nor the user's two-call cap settles who chooses a nuanced answer.

Owner choice requested: deterministic character rules choose and LLM voices, or a hybrid where rules enforce feasibility/consent while extraction LLM plus Jev proposes nuanced choices. For a hybrid, use per-character sanitized candidate contexts and the existing extraction budget; do not expose every private mind in one shared prompt or add per-NPC calls. Where safe partitioning is impossible within budget, defer the decision or use a documented local policy, not silent leakage. Precise provider/context orchestration must follow the selected model.

Before replacing current behavior, compare recorded fixtures for local utility versus LLM/Jev judgment: work/date tradeoff, gentle refusal, tentative offer, jealousy, deception, quiet/comic response and both game casts. Hold snapshot, information permissions and eligible options constant. Record decision, causal reason, subsequent response quality, invariant failures, disagreement and owner preference. Shadow candidates do not mutate the live game. Additional comparative model calls require their own explicit test budget, never hidden in the two-call gameplay cap; arena judging remains off. No cutover until the owner chooses the model and evidence supports it.

## 7. Can an implementer use this without reading hundreds of lines?

Yes, the proposal should be navigable release contracts plus one canonical architecture, not a growing transcript. Condense BL-38 section 15 to a current decision summary and move detailed first-round Q&A into a linked review record. Preserve questions/answers for traceability without making them implementation instructions.

After the plan-authority decision, publish small release contracts for O12 opening cleanup, O08 addressed responses and the backend receipt slice. Each needs scope/non-goals, owning files/objects, dependencies, exact fixtures, migration impact and hosted proof. Reuse feature backlogs where possible; coordinate new backlog numbers with the sibling work before adding them. Do not invent a competing release hierarchy while authority is unresolved.

Immediate navigation remains BL-38 section 12's independently shippable units; these do not require BL-39 standing or the shared Character refactor. A shared-state implementer must resolve the conflicts in section 1 first.

## Pending owner answers

1. Consolidation authority: combined contract (recommended), BL-38 primary, or BL-39 primary.
2. NPC decision model: hybrid proposals under engine constraints (recommended) or deterministic rules with LLM realization.
3. Visible validator-fallback ceiling: proposed 5%, 1%, or decide after reviewing examples.

These questions do not block documentation/evidence work or independent low-coupling fixes. They do block choosing the replacement social-state writer and NPC decision policy on the owner's behalf.
