# Engineering plan — reuse, correctness, performance, Jev

September 21, 2026. Derived from `CODEBASE_AUDIT_AND_REUSE_PERFORMANCE_JEV_PLAN_2026_09_21.md`.

**Status: execution started 2026-09-21.** See the Execution Log at the end of
this document for what has actually shipped. Phases not marked shipped there are
still plan-only and are requested separately. Each phase is requested separately and follows `.claude/skills/ship-and-verify/SKILL.md` (local pass → beta → live beta verification). No production merge without explicit approval.

---

## 0. What changed between the audit and this plan

The audit was a source review. Before planning I re-verified its findings against the current working tree and ran three experiments on this machine. Most findings confirmed; four changed priority because measurement contradicted the assumption.

### Verified against current code

| Audit claim | Verified | Note |
| --- | --- | --- |
| `gitwebhook.php` contains a literal signing secret | Yes | **Worse than stated** — see 0.1 |
| `.cpanel.yml` does `rm -rf` on both prod and beta from one checkout | Yes | Lines 7–8, still tracked |
| Turn mutates state before the storyteller succeeds | Yes | `state.turns += 1` at `prompt_engine.py:2893`; storyteller POST at `:2917`; both error paths `return` without rollback |
| Raw upstream error body returned to client | Yes | `prompt_engine.py:2929` returns `r.text` |
| Extraction marks done after in-memory-only chunk write | Yes | `prompt_engine.py:3085` — `_store.add_chunks(...)` then `mark_done(...)` |
| Extractor converts provider failure to `[]` | Yes | `dialogue_extractor.py:122` — success-empty and failure indistinguishable |
| Journal walks all characters with no visibility filter | Yes | `user_sessions.py:78` iterates `state.characters` unfiltered |
| Guest cleanup evicts every cached guest session | Yes | `main.py:97` filters on prefix, not on deleted IDs |
| `_chat_handler_impl` is ~1,255 lines | Yes | Measured 1,256 |
| Each task builds its own `httpx.AsyncClient` | Yes | 18 construction sites across backend |
| `SessionChunkStore` does not dedupe by chunk ID | Yes | Measured: same ID added 5× → `len == 5` |
| History pagination parses the whole JSONL per page | Yes | `repos.py:_load_page` — but correctly `to_thread`-offloaded |
| Retrieval runs synchronously on the event loop | Yes | **Much worse than stated** — see 0.2 |

Also confirmed: per-session locks exist (`prompt_engine.py:1899`) with an accurate in-code comment that request-ID dedup is *not* implemented; the outbox and startup sweep from BL-01b exist, so Phase 1 extends prior work rather than starting fresh.

### 0.1 P0 escalation — the webhook secret is in git history

The audit said "whether that value is still active was not checked." Stronger finding: `deployment/gitwebhook.php` is **a tracked file**, and the secret is present across five commits (`2caee48`, `57c1a9a`, `612d104`, `0fa402e`, `0578a87`). Removing it from the working tree does not remove it from history.

Consequence: rotation is mandatory, not conditional on the value still being active. Anyone with repository read access has the deploy-trigger secret. Treat this as the gating item for everything else — it is listed first in Phase 0 and the secret value is not reproduced here.

`.cpanel.yml` remains independently dangerous: `/bin/rm -rf $DEPLOYPATH/*` against `/home/storvrfx/public_html` with no exit-code check, copying one checkout to both prod and beta. This contradicts the webhook's branch routing, so which mechanism is actually live must be established before either is touched.

### 0.2 P1 → P0 escalation — measured event-loop blocking

The audit correctly identified retrieval as blocking but rated it P1 alongside ordinary optimization. Measured on this machine:

```
embedder import:         196.1 ms
embedder cold call:    15916.0 ms   ← first retrieval after any deploy
embedder warm p50:        68.9 ms
embedder warm max:        77.0 ms
10 sync retrievals on loop: 632.9 ms total
event-loop lag p50:      175.65 ms   max: 206.91 ms
```

`backend/app/knowledge/build/embedder.py` lazily constructs a real `SentenceTransformer` (`intfloat/e5-base-v2`, CPU) inside `_get_model()`. Nothing warms it — `grep` over `main.py` and `prompt_engine.py` finds no startup call. So:

- The **first** player to trigger retrieval after each deploy blocks the single event loop for ~16 seconds. Every other concurrent session — including health checks and unrelated endpoints — stalls for that entire window. This is an availability defect, not a latency preference.
- `_get_model()` has no lock. Two concurrent cold requests can both enter the `if _MODEL is None` branch and each load a full model, doubling peak RSS on a memory-capped Railway container.
- Steady state, each retrieval blocks ~69 ms. Ten concurrent sessions produce ~176 ms p50 loop lag, so warm blocking is real but an order of magnitude less urgent than cold start.

This reorders the work: embedder warm-up and the `_get_model()` lock move into Phase 1 as correctness/availability items. The bounded executor stays in Phase 3 as a measured optimization.

### 0.3 P2 → deprioritized — measured parsing costs are small

```
build_story_registry()          p50   2.13 ms
SessionChunkStore.query n=10    p50   0.18 ms
SessionChunkStore.query n=50    p50   0.56 ms
SessionChunkStore.query n=200   p50   2.05 ms
SessionChunkStore.query n=500   p50   5.06 ms
```

The audit's "reparses the catalogue on lookup" and "rebuilds tokenization/BM25 on each query" are accurate descriptions of cheap operations. At a realistic 200-chunk session, BM25 rebuild costs 2 ms — against a storyteller call measured in seconds. `story_loader.py:180` even carries a comment explaining the deliberate non-caching (draft stories must appear immediately), which is a correct tradeoff.

Planned response: **do not cache either for performance.** Fix the `SessionChunkStore` ID-duplication bug (a correctness issue — duplicate facts inflate the prompt and can crowd out distinct memories) and leave the rebuild alone. Revisit only if a session exceeds ~1,000 chunks in the Phase 0 baseline. This removes two items from the audit's scope and avoids adding cache-invalidation risk for ~7 ms.

### 0.4 Confirmed-but-reframed — history pagination

`_load_page` does read and parse the entire JSONL per page, but through `asyncio.to_thread`, so it does not block the loop. The real exposure is CPU and peak memory on long sessions, not responsiveness. It stays P2 and is gated on a baseline measurement of actual transcript sizes — if the largest real session is a few hundred KB, this is not worth an index.

---

## Guiding constraints

1. **Correctness before cost.** No optimization ships before the turn commit and memory durability it could mask are in place.
2. **One responsibility per change.** The 1,256-line handler is decomposed by moving one concern at a time behind a compatibility wrapper, with a characterization test written *before* the move.
3. **Measure, then change.** Every performance item carries before/after evidence from the Phase 0 harness. Items whose measurement shows a small win get dropped, as in 0.3.
4. **The engine stays pure.** No FastAPI, httpx, or storage imports under `backend/app/engine/`. Enforced by a test, not convention.
5. **Storyteller unchanged.** Jev is evaluated only for bounded decisions and offline grading. Narration, new factual sentences, goals, and translation keep a generative model.
6. **No skipped tests.** `conftest.py` converts any skip to a failure; every phase adds passing tests in every environment.

---

## Phase 0 — Release safety and baseline

Gates every later phase. Two independent tracks.

### 0A. Deployment credential and path remediation (blocking)

| Step | Action | Acceptance |
| --- | --- | --- |
| 0A.1 | Determine which mechanism is live: cPanel `.cpanel.yml`, the PHP webhook, or Railway only. Inspect the GitHub webhook delivery log for the repo. | A written statement of the actual live deploy path for beta and for prod |
| 0A.2 | Rotate the webhook secret regardless of whether it is active. Generate a new value, set it in the GitHub webhook config and the host environment. | Old secret rejected; new secret accepted on a test delivery |
| 0A.3 | Move the secret out of source: read from a host env var or an untracked config file outside the web root. Remove the literal from the working tree. | `git grep` for the literal returns nothing in the working tree |
| 0A.4 | History remains contaminated. Document it in `AI_FATAL_MISTAKES.md`. Decide with the user: accept (rotation makes it inert) or rewrite history. Default recommendation: **accept + rotate**, since history rewriting breaks the parallel-agent workflow in CLAUDE.md §7. | Decision recorded with rationale |
| 0A.5 | Do not execute `.cpanel.yml`'s destructive path. Replace `rm -rf $PATH/*` with explicit file ownership, per-branch isolation, and `set -e`-equivalent exit-code checks. Beta and prod must not derive from one checkout. | A dry-run shows beta and prod receiving distinct, branch-correct artifacts; no unbounded delete remains |
| 0A.6 | Stop returning raw upstream bodies. `prompt_engine.py:2929` → stable public error + full detail to server logs only. | Test asserting no provider text reaches an HTTP response |

`0A.2` and `0A.6` are owner actions requiring credentials I do not hold; they go to `BACKLOG.md` with explicit owner assignment if not completed in the same pass.

### 0B. Baseline instrumentation

Purpose: make Phases 3 and 4 decidable. Without it, "improved p95" is unverifiable and the Jev business case has no denominator.

**Per-stage timing and token ledger.** Instrument each turn stage: lock wait, session restore, retrieval, turn extraction, prompt composition, storyteller, commit, translation, background memory. For every model call record input/cached/output tokens, resolved provider and model version, retry count, fallback reason, and latency. Attribute cost to a single "cost per successfully committed turn" figure that includes background and evaluation spend.

Implementation note: emit through the existing `_log`/jlog JSONL path with a new `kind`, so no new transport is introduced in Phase 0. Full-prompt logging is gated behind an operator-diagnostics flag (audit follow-up) and is off by default.

**Repeatable workload harness.** A script driving: both stories; both Terrace House player genders; new and resumed sessions; short and long conversations; movement; time skip; queue exhaustion; and injected provider errors. Run at 1, 10, and 50 concurrent independent sessions, plus concurrent requests against one session. Cold and warm start measured separately — 0.2 shows these differ by three orders of magnitude, so a single averaged number would be meaningless.

Record p50/p95 latency, time to first visible text, event-loop lag, CPU, RSS, background queue age, and DB write time.

**Exit criteria:** live beta baseline captured for every workload; the cold-start figure in 0.2 reproduced or corrected against real Railway hardware; beta and prod confirmed isolated; reproducible failure cases scoped for Phase 1.

---

## Phase 1 — Correctness foundation

Four independent deliverables. Each lands as its own reviewable change with characterization tests first.

### 1.1 Atomic turn commit

**Problem.** `state.turns += 1` (`:2893`) and the relationship/time/lifecycle mutations before it execute against live cached state. The storyteller POST (`:2917`) follows. Both the HTTP-error path (`:2929`) and the dialogue-decode path (`:2936`) `return` without restoring anything. A failed turn therefore leaves time advanced, the turn counter incremented, and relationships mutated, with no reply. The player retries and double-advances. The in-code comment at `:1897` already acknowledges retried requests apply twice.

**Design.** Introduce `TurnService` in a new `backend/app/application/`:

1. Deep-copy (or structurally clone) the session state into an isolated working state.
2. Run all staging — retrieval, extraction, mutation, prompt composition — against the working state only.
3. Call the storyteller. On any failure, discard the working state; live state is untouched by construction.
4. On success, commit as one unit: validated state, completed reply keyed by request ID, canonical turn record, and the extraction job.
5. Publish the working state into `SESSIONS` only after commit succeeds.

Request-ID dedup becomes natural: a committed reply keyed by request ID means a retry returns the stored reply instead of re-running the turn. This closes the gap the `:1897` comment leaves open.

JSONL stays as an export from committed records, not a parallel write.

**Risk.** Cloning `GameState` per turn costs CPU and memory. The Phase 0 harness measures it before this ships; if clone cost is material, fall back to an explicit journalled-mutation undo. Cloning is preferred first because it is far harder to get subtly wrong.

**Tests.** Injected failure at each boundary — retrieval, extraction, storyteller HTTP, decode, persistence — asserting time, `turns`, relationships, and lifecycle are byte-identical to pre-turn state. A retried identical request ID returns the original reply and does not advance state twice.

### 1.2 Durable extracted facts

**Problem.** `_extract_and_store` writes chunks into the in-memory store, then marks the outbox row done (`:3085`). A crash between those two lines loses the facts while the row reads `done`. Separately, `dialogue_extractor.py:122` returns `[]` for both "nothing to extract" and "provider failed," so a provider outage is silently recorded as a successful empty extraction and never retried.

**Design.**
- Persist extracted chunks to SQLite keyed by `(session_id, message_id, extractor_version)`, and mark the outbox row done **in the same transaction**. Never done-without-results.
- Change the extractor's contract to a result type distinguishing `Extracted(chunks)`, `EmptySuccess`, and `Failed(reason)`. Only the first two mark done; `Failed` schedules a bounded retry.
- Add leases so a periodic sweep can reclaim rows whose worker hung. This closes **BL-01c**, already tracked.
- Preserve claim/source metadata through snapshots and retrieval so a player-asserted claim is never promoted to canonical truth.
- Extractor version in the key means a prompt change re-extracts rather than silently mixing schema generations.

**Tests.** Kill between chunk write and mark-done → facts present after restart. Provider failure → row retryable, not done. Empty success → done, not retried. Lease expiry reclaims a hung row. Restart immediately after a turn → facts survive.

### 1.3 Embedder availability (escalated from P1 per 0.2)

- Add a lock (or `functools.lru_cache`-equivalent single-flight) inside `_get_model()` so concurrent cold requests load one model, not two.
- Warm the embedder during startup, off the readiness-critical path: begin loading in the lifespan handler, but do not gate readiness on it; retrieval awaits the warm-up if a request arrives first. This converts a 16-second stall for one unlucky player into background work.
- Assert the model cache directory is writable at startup and log clearly if not. `cache_dir = "/app/.model_cache"` is Docker-specific and silently re-downloads if absent, which plausibly explains part of the 15.9 s.

**Tests.** Two concurrent cold retrievals construct exactly one model (patched constructor with a call counter). Startup warm-up does not block readiness. Retrieval arriving during warm-up returns correct results rather than racing.

### 1.4 Player-visible projection policy

**Problem.** `get_journal` (`user_sessions.py:78`) iterates every character's goal history with no lifecycle or knowledge filter. Terrace House authors goals for *upcoming* contestants, so the journal can leak characters the player has not met and private goals they have not learned.

**Design.** One `PlayerView` projection policy shared by journal, roster, history metadata, and any other public response. Rules: future/unarrived contestants hidden; undiscovered or private goals hidden; legitimately learned history about former residents retained. Operator/debug views are a separate, explicitly-named projection.

As the audit notes, "is this character currently active" is insufficient — a departed resident the player knew must remain visible, and an unarrived one must not.

**Tests.** A session with unarrived contestants exposes none of them in journal or roster. A departed known resident remains. A private goal appears only after the discovery event. Full cast rotation end-to-end asserts no leak at any stage.

### 1.5 Exact session eviction

**Problem.** `main.py:97` deletes expired guest rows, then evicts *every* cached session whose `user_id` starts with `guest:` — including active players mid-turn.

**Design.** Evict exactly the session IDs the delete returned. Coordinate with the per-session lock so eviction cannot land mid-turn, and ensure a late background task cannot resurrect a deleted session. Bound `SESSIONS` and `_SESSION_LOCKS` with eviction that respects in-flight turns; retire locks only when uncontended.

Keep one process. Cross-process concurrency needs DB-level revision checks, which is out of scope here and noted in `prompt_engine.py:1893`.

**Tests.** Expiring guest A does not evict active guest B. Eviction during an in-flight turn cannot corrupt the commit. A late extraction task targeting a deleted session is dropped, not resurrected. Lock dictionary does not grow unbounded across many sessions.

**Phase 1 exit criteria:** failed, retried, and interrupted turns cannot double-advance; extracted facts survive immediate restart; future and private content never appears in player views; cold start no longer blocks the loop for seconds; eviction is precise.

---

## Phase 2 — Reusable backend

Pure restructuring. No behavior change; characterization tests written before each move, and API contracts preserved by compatibility wrappers.

Target layout (from the audit, adopted as-is):

```text
backend/app/
  api/            HTTP validation, auth, public response schemas
  application/    turn service, commands, session factory, projections
  engine/         pure state transitions (no FastAPI/httpx/storage imports)
    prompts/      named templates and composition
  llm/            task contracts, provider adapters, routing, usage accounting
  db/             repositories, migrations, transactional turn/memory records
  knowledge/      retrieval, indexing, immutable content bundles
  workers/        durable memory jobs and recovery
  stories/        story rules, cast, maps, language/style content
```

Contracts, in dependency order:

1. **SessionFactory + SnapshotCodec** — one initialization path for new and restored games (currently duplicated), versioned migrations, typed player identity, stable story-content version. Tested restoration of existing saved games is the hard requirement.
2. **TurnService** — formalizes Phase 1.1. Takes identity, session ID, request ID, command/message; returns a committed result. Distinguishes validation, provider, and persistence failure.
3. **DecisionProvider / TextProvider** — separates bounded decisions from generated prose. This is the seam Phase 4 plugs Jev into; without it, a Jev pilot means editing the turn pipeline. `TurnExtraction` stays a validated internal result, not a provider wire format leaking through the game.
4. **PlayerView** — formalizes Phase 1.4.
5. **StoryDefinition** — validated immutable content; configurable slot groups, player capacity, bedrooms, arrival timing, exhaustion policy. The six-resident rule stays deterministic code driven by Terrace House configuration.

Decomposition order for the 1,256-line handler, each behind a wrapper: command dispatch → session load/restore → retrieval assembly → prompt composition → provider call → commit → background enqueue.

Per the audit, free-text goals and behavior tags are preserved. Content-authored categories are required only for features that can actually use them — the open-ended social simulation is not flattened into a fixed goal list.

**Exit criteria:** existing endpoints and saved games behave identically; deterministic tests pass for both genres and a full cast rotation; an import-direction test proves `engine/` imports no API, HTTP, or storage module.

---

## Phase 3 — Measured optimization

Every item requires Phase 0 before/after evidence. Any item whose measurement shows a small win is dropped, following 0.3.

| Change | Rationale | Protection | Status |
| --- | --- | --- | --- |
| Lifespan-managed HTTP clients | 18 construction sites; each pays TLS + connection setup per model call. HTTPX explicitly recommends scoped reusable clients. | Per-provider config, clean shutdown, bounded connections and retries | Planned |
| Task-specific model configuration | Memory extraction uses the storyteller URL/key with the hardcoded OpenAI model name — pointing the storyteller at Ollama silently requests a model that provider may not have. Correctness-adjacent. | A provider change must never silently select an unsupported model for another task; explicit per-task config with validation | Planned — high value, low risk |
| Bounded retrieval executor | Warm retrieval blocks ~69 ms; 10 concurrent sessions → ~176 ms p50 loop lag | Bounded executor, safe init (Phase 1.3 first), isolation tests, CPU saturation measurement | Planned, after 1.3 |
| `SessionChunkStore` ID dedup | **Correctness** — measured 5 copies of one chunk ID. Duplicates inflate prompts and crowd out distinct memories. | Dedupe by stable ID; assert idempotent re-extraction | Planned — reclassified from P2 perf to correctness |
| Cache story registry / BM25 tokenization | Measured 2.13 ms and 2.05 ms | — | **Dropped** (0.3). Revisit only if a session exceeds ~1,000 chunks |
| Indexed history pagination | Whole-file parse per page, but `to_thread`-offloaded | Migration and deletion tests; durable history must outlive cache eviction | **Gated** on Phase 0 showing real transcript sizes justify it |
| Source-aware memory merge | `retrieve.py:_merge_session_chunks` gives session memories only leftover slots; 8 canonical hits suppress all dialogue memory | Reserved memory budget or source-aware ranking. **Quality change, not a perf win** — needs A/B on story behavior; player claims must never become canonical | Planned as a quality experiment |
| Reduce duplicated prompt inputs and sampled diagnostics | Lower tokens, serialization, log volume | Compare story behavior and visibility; never remove relevant memory just to shrink input | Planned |
| Bounded durable memory worker | Formalizes Phase 1.2's queue | Idempotent results, correct provenance, durable completion; verify combining two texts preserves extraction quality | Planned |
| Stable instruction prefixes for prompt caching | `prompt_builder.py` interleaves stable instructions with changing state, defeating prefix caching | Measure *cached* token counts — a cache key does not guarantee a hit | Planned, measurement-gated |
| Immediate/full-reply and reduced-motion rendering | Lower perceived wait after the response arrives | Preserve speaker order, scrolling, accessibility, existing animation option. Overlaps **BL-13**; re-audit per that entry before acting | Planned |

Streaming is deferred until turn transactions (1.1) and frontend transport (Phase 5) are reliable. Structured dialogue needs valid framing, buffering, cancellation semantics, and an incomplete-response policy. Streaming improves time to first text; it does not reduce tokens or total time.

Dependent stages — retrieval → extraction → state application → narration — are **not** parallelized; later stages consume earlier results. Workers and replicas are not expanded until session revision checks and shared job ownership exist.

**Exit criteria:** quality and correctness unchanged; p95 and RSS meet or beat baseline; every shipped optimization has before/after evidence; every dropped item has a recorded measurement justifying the drop.

---

## Phase 4 — Jev evaluation

Depends on Phase 2's `DecisionProvider` seam and Phase 0's cost ledger. Without both, savings are unverifiable and integration means surgery on the turn pipeline.

### Facts carried forward from the audit

TypeSafe AI Jev, documented as `jev-1.13.0`. `POST https://api.typesafe.ai/v1/systemone`, with state plus typed Choice/Score/Noul questions — not a chat-completions schema. It evaluates supplied state; it does not generate narration. Limits: 64k tokens for state plus all questions, 32k for state plus the longest question. Listed at $0.042/M input, output free. English strongest; CJK needs its own evaluation. Pin the tested version rather than a moving alias. Documented weaknesses: arithmetic, dates, indirection, adversarial state, irrelevant long context, text generation.

Vercel's free promotional window ends September 25, 2026 — four days from this plan's date. **The business case uses normal pricing.** The promo is too short to build a rollout on and may lapse before Phase 4 begins.

Confidence is not correctness: Choice/Score confidence summarizes a probability distribution; Noul returns a probability with no confidence field. Thresholds are tuned per task and per model version on labeled game data.

### Task fit

| Task | Treatment |
| --- | --- |
| Rubric scoring in offline playback | **First pilot.** No player-facing risk; a wrong answer costs a bad grade, not a corrupted save. Retain human review. |
| Memory-extraction eligibility gate | **Second pilot.** Very high recall required; ambiguous messages still reach the existing extractor. Measure *avoided calls*, not classifier price. |
| Movement intent among allowed destinations | Parse exact commands locally first. Jev may select an allowed candidate or NONE/UNKNOWN; code validates travel. |
| Dialogue supporting a candidate knowledge claim | Sensitive. Explicit evidence plus an uncertain outcome. Probability alone must never grant access to a secret. |
| Departure NONE/WISH/DECISION | Later pilot. Uses the resident's own attributed words; existing eligibility, timing, replacement, and 3–3 checks stay in code. |
| Dialogue, new factual sentences, novel goals, free-text behavior, translation | **Unsuitable.** Keep a generative model. |
| Counting residents, queue order, dates, identity, authorization | **No model.** Deterministic code. |

### The hybrid trap

`TurnExtractor` (`turn_extractor.py`, 520 lines) combines bounded choices with free-text fields in one call. Replacing only its movement judgment with Jev while still running the whole extractor **adds** cost and latency. A hybrid design must genuinely omit or shrink an existing call and preserve every required field. Recorded as an explicit gate, not a caveat.

The open-ended social simulation is not reduced to canned goals to fit Jev's question format.

### Economics

Using the repository's `gpt-4o-mini` default ($0.15/M uncached in, $0.075/M cached in, $0.60/M out) and the audit's hypothetical of 100,000 eligible bounded-decision calls at 3,000 in / 400 out, versus Jev at 2,000 billable input with 10% fallback:

| Scenario | Cost per 100,000 eligible calls |
| --- | ---: |
| Existing model | $69.00 |
| Jev only | $8.40 |
| Jev + 10% fallback | $15.30 |
| Reduction on this operation | $53.70 / 77.8% |

**This is not a 77.8% bill reduction.** If those operations are 20% of spend, total reduction is ~15.6%. Cached baseline inputs, larger question sets, retained generation, mistakes, retries, and added evaluation work all erode it. The deployed model may not even be `gpt-4o-mini` — Phase 0 establishes that.

Decision equation: `new cost = Jev cost + fallback fraction × fallback cost + retained generation + retries`, compared against measured cost per successful, quality-acceptable turn. For the memory gate, include gate cost plus the fraction still requiring extraction; if the gate mostly says "extract," it does not pay for itself.

### Gates

1. ≥1,000 labeled cases from synthetic or approved/redacted examples across both games: normal conversation, negation, sarcasm, multi-speaker attribution, offscreen references, deliberate attempts to invent departures, and English/Japanese/Korean/Chinese cases relevant to actual use.
2. Offline grader judgments and memory-gate eligibility first. Record per-question quality, latency, tokens, version, fallback rate, and total question fan-out cost.
3. Shadow mode on selected turns — observe without applying. No indefinite duplication of every live call.
4. Adopt only when measured spend falls, the quality baseline holds, and p95 does not regress beyond a predeclared tolerance. Hard gates: zero deterministic invariant violations; no new false departures or secret disclosures in the critical set; ≥99% recall for a gate that would otherwise discard useful memory. A clean finite test set does not prove zero production errors.
5. Independent per-task flags, small beta cohort first. Log resolved model version and fallback cause. Automatic fallback to the existing provider on timeout or invalid output — internal fallback, never interrupting the player with model uncertainty.
6. Re-evaluate on every version change. Sensitive state transitions treated more conservatively than offline scoring. Verify provider access and data handling **before** sending real player content.

**Exit criteria:** demonstrated savings after fallback and retained calls; task-specific quality gates pass; one-step rollback verified.

### LangSmith and this phase

The LangSmith key is now stored (see §Appendix A). Its natural use is exactly Phase 0's ledger and Phase 4's offline evaluation: per-stage traces, token accounting, and labeled-dataset grading runs. Tracing is **off by default** — `is_langsmith_enabled()` requires an explicit `LANGSMITH_TRACING` flag, so holding the key never ships player content to a third party. Before enabling it against real player turns, the data-handling review in gate 6 applies to LangSmith too, not only to Jev.

---

## Phase 5 — Reusable frontend and coherent assets

`frontend/index.html` is 3,798 lines of layout, styling, state, network code, and features. `sendMessage` (`:2911`) awaits the full JSON response, and the retry ID is local with no visible retry workflow.

- Extract API transport, session store, chat, catalogue, journal, map, auth modules. **Preserve the existing appearance** before any product change.
- Pending-request persistence plus timeout/retry UX, paired with Phase 1.1's request-ID dedup so a user-visible retry is safe by construction.
- Accessible motion settings. Overlaps **BL-13** — re-run that audit's steps first, since its portrait-404 finding already proved stale.
- Single frontend asset manifest consumed by HTML, backend serving, deployment, and service-worker versioning. `frontend/sw.js` caches by URL; the webhook's asset list omits the untracked `world-map.js/css`.
- The untracked map work is **unfinished integration, not dead code**: `index.html` does not load the module or consume `world_map`, still using the older image path. Finish or explicitly park it — do not delete.

**Exit criteria:** desktop Chromium and iPhone-sized WebKit checks per CLAUDE.md §9, local and then live beta; no duplicate send; guest/auth resume, history, roster, map, journal, and offline upgrade all work; stale-cache upgrade and rollback tested on both hosts.

---

## Phase 6 — Delivery and documentation

- Align and pin the runtime: CI uses Python 3.11, `Dockerfile` uses 3.10. Pick one tested version.
- `Dockerfile` copies application files before installing dependencies, so any source edit invalidates the dependency layer. Reorder.
- Separate runtime/build/test dependency sets with a lock. Keep required test coverage but build the tested runtime artifact once.
- Move recovery off the readiness-critical startup path (pairs with Phase 1.3); prebuild and fingerprint indexes.
- Add frontend checks to CI rather than relying on historical screenshots.
- Doc updates per `AI_DOC_INDEX_CATALOGUE.md`: `INFRASTRUCTURE.md` (deploy path, env vars, LangSmith), `AI_FATAL_MISTAKES.md` (0A.4), `DATA_MODEL_INVENTORY.md` (durable chunk table, turn records), `MESSAGE_TO_PROMPT_FLOW_TRACE.md` (TurnService), `AUTH_AND_PERSISTENCE_DESIGN.md` (eviction), `BACKLOG.md` (close BL-01c; reconcile BL-13).

**Exit criteria:** the same tested artifact reaches beta; content, asset, and build identities agree; production release remains separately requested.

---

## Sequencing and dependencies

```
Phase 0A (credential/path)  ──┐
                              ├─→ everything (hard gate)
Phase 0B (baseline)  ─────────┘
        │
        ├─→ Phase 1.1 atomic commit ──→ Phase 2 TurnService ──→ Phase 3 optimizations
        ├─→ Phase 1.2 durable facts ──→ Phase 3 memory worker
        ├─→ Phase 1.3 embedder  ──────→ Phase 3 retrieval executor
        ├─→ Phase 1.4 PlayerView ─────→ Phase 2 projections
        └─→ Phase 1.5 eviction
                                        Phase 2 DecisionProvider ──→ Phase 4 Jev
                                        Phase 1.1 + Phase 5 transport ──→ streaming (deferred)
```

Phases split into small, independently reviewable changes. Characterization tests precede every behavior move. Lifecycle balance, privacy, travel, persistence, retry semantics, and provider failure are tested before style or latency work begins.

Existing in-progress changes are preserved. Unrelated cleanup is not bundled into these phases. The untracked Terrace House world/map work continues on its own track.

## Recommended first package

Per the audit's own recommendation, confirmed by my verification:

1. **Phase 0A.1–0A.3 + 0A.6** — establish the live deploy path, rotate the webhook secret (mandatory: it is in five commits of git history), remove the literal from source, stop leaking upstream error bodies.
2. **Phase 0B** — the ledger and workload harness.
3. **Phase 1.1 + 1.2 tests first** — characterization tests for turn commit and memory durability before either implementation.
4. **Phase 1.3** — the embedder lock and startup warm-up. Small, self-contained, and it removes a measured 16-second full-service stall per deploy.

I would add 1.3 to the audit's recommended package: it is the cheapest change in this plan with the largest measured availability effect, and it is independent of the restructuring.

Jev's first evaluation targets offline grading and the memory gate, storyteller unchanged.

---

## Appendix A — LangSmith credential storage (completed 2026-09-21)

Stored following the existing secret pattern exactly; no new mechanism introduced.

- **Value** → `.env.test` (gitignored, confirmed via `git check-ignore`) as `LANGSMITH_API_KEY`, plus `LANGSMITH_PROJECT=storieschat-beta`. Never committed.
- **Accessors** → `backend/app/config/credentials.py`: `get_langsmith_api_key()`, `get_langsmith_project()` (defaults to `"storieschat"`), `is_langsmith_enabled()`. All route through the existing `_get_env_with_fallback`, so Railway/CI env vars win over `.env.test` and case-only key mismatches are tolerated, same as the Google/JWT keys.
- **Exports** → `backend/app/config/settings.py`: `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_TRACING_ENABLED`.
- **Opt-in by design.** `is_langsmith_enabled()` returns `False` unless `LANGSMITH_TRACING` is explicitly truthy (`1/true/yes/on`). Holding the key does not start sending player content to an external service — a deliberate choice, locked by a regression test.
- **Tests** → 11 added to `tests/backend/app/config/test_credentials.py`, covering live-env priority, `.env.test` fallback, empty-when-unset, project default, and the full truthy/falsy flag matrix. `python -m pytest tests/backend/app/config/ -q` → 35 passed.
- **For beta/prod:** set `LANGSMITH_API_KEY` (and `LANGSMITH_TRACING` if tracing is wanted there) as Railway env vars. No code change needed — the loader already prefers them.

No LangSmith SDK dependency was added. Instrumentation is Phase 0B work and is not authorized by this document.

## Appendix B — Reproducing the measurements

Scripts are in the session scratchpad, not the repo (they are throwaway probes, not tests). To reproduce:

- **Embedder / event-loop lag:** time `backend.app.knowledge.build.embedder.embed_texts` for import, first call, and 10 warm calls; then run 10 synchronous calls on an asyncio loop while an `asyncio.sleep(0.005)` probe records overshoot. Overshoot is the stall other sessions experience.
- **Parsing hotspots:** median of 20 `build_story_registry()` calls; median of 10 `SessionChunkStore.query()` calls at n = 10/50/200/500; add the same `chunk_id` five times and assert `len()`.

All figures in 0.2 and 0.3 are from this Windows development machine, single process, CPU only. **They establish orders of magnitude, not production values** — Railway hardware, container memory limits, and a cold model cache will differ, which is precisely what Phase 0B measures.

---

## Execution log

### Shipped — Phase 0A (release safety) + Phase 1.3 (embedder), commit `c0d8b45`, beta 2026-09-21

**0A.1 — live deploy mechanism established.** The plan listed this as an open
question. Settled empirically: `storieschat.ai` and `beta-api.storieschat.ai`
both return `x-railway-edge` / `x-railway-request-id`, with no Apache/LiteSpeed/
cPanel signature, and `backend/app/main.py` serves `frontend/index.html` itself.
**Both environments are Railway-only; the cPanel/PHP path is dead code.** That
means the destructive `.cpanel.yml` never runs — but the leaked secret is still
live, so 0A.2 remains mandatory.

**0A.3 / 0A.5 — quarantined.** `deployment/gitwebhook.php` and `.cpanel.yml`
moved to `deployment/legacy_cpanel_unused/*.disabled`. The literal secret is
replaced with `getenv("GITWEBHOOK_SECRET")` and the webhook now **fails closed**
(503) when unset. Both `rm -rf` lines removed. `README_DISABLED.md` records the
header evidence and forbids restoring them as-is.

**0A.6 — upstream error leak closed.** The chat endpoint no longer returns
`f"upstream HTTP {status}: {r.text}"` to the browser; it returns the
provider-agnostic `_PUBLIC_UPSTREAM_ERROR`. The full body is still logged with
`req_id`. The second site (`chinese_translation_error`) was audited and is
log-only, so it never reached a client.

**1.3 — embedder availability.** Single-flight `threading.Lock` around
`_get_model()`, writability-checked `_resolve_cache_dir()` (the old hardcoded
`/app/.model_cache` silently forced a re-download off-container), plus
`is_loaded()`/`warm_up()` and a fire-and-forget `_warm_embedder()` task in
lifespan that runs via `asyncio.to_thread` and is deliberately **not awaited**,
so readiness never waits on the model.

Measured before → after (local):

| Metric | Before | After |
| --- | ---: | ---: |
| Event-loop lag during cold model load | 15,916 ms fully blocked | p50 **10.8 ms** (max 197 ms) |
| Startup → ready | — | **0.25 s**, `/api/health` 200, model still loading |
| 8 concurrent `_get_model()` after warm | — | 4.7 ms, one shared instance |

Live beta verification after deploy: `/api/health` 0.19–0.26 s across 5 serial
and 10 parallel requests; a real guest session played two turns (new game +
message) with retrieval in 5.0 s and no cold-start stall; the quarantined deploy
files return 404.

Tests: 722 passed, 1 xfailed. New `tests/backend/app/knowledge/test_embedder_warmup.py`
(10 tests, fake model — nothing downloaded) covers the 8-thread cold-start
stampede constructing exactly one model, cache-dir fallback, and an asyncio test
asserting the warm-up keeps the loop ticking.

### Outstanding owner action

**0A.2 — rotate the webhook secret.** Not done; needs GitHub repo-settings
access. Tracked as **BL-14**. The secret is in history across five commits, so
it must be treated as public regardless of the working-tree fix.

### Plan corrections found during execution

- **BL-02 request-ID dedup already exists** (`prompt_engine.py` ~1956 and ~3169)
  and is persisted to SQLite. Phase 1.1 is therefore smaller than written: the
  remaining gap is that the dedup token is written *after* the turn's mutations
  commit, and only for non-anon users, so it replays a completed reply but does
  not protect a turn that failed partway. Phase 1.1 should extend this
  mechanism rather than introduce a parallel one.
- **Prompt caching is confirmed unclaimed.** A live beta turn reported
  `prompt_tokens: 4831` with `cached_tokens: 0`, so the Phase 3 stable-prefix
  item has real headroom rather than assumed headroom.
