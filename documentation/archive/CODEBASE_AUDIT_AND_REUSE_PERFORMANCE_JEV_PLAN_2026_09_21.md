# Codebase audit and implementation plan

September 21, 2026 — planning only; no implementation or deployment authorized by this document.

The recommended order is: protect state and memory correctness, measure complete turn cost, extract reusable services, remove unnecessary work, then evaluate Jev for bounded decisions. Keep the existing storyteller until a separate quality evaluation justifies changing it.

## Scope and evidence

This is a repository-wide architecture and source audit of the current working tree, including the uncommitted Terrace House changes. The inventory covered 202 Python, JavaScript, HTML, CSS, PHP, JSON, and YAML files across the application, frontend, scripts, tests, and deployment directory: approximately 45,400 lines. CI, Docker, configuration, architecture documentation, and the product North Star were also reviewed. Images and generated research artifacts were excluded from these counts.

Detailed review traced new-game initialization, session restoration, a normal chat turn, retrieval, model extraction, narration, background memory, cast rotation, public projections, browser rendering, and deployment. Findings below identify source behavior; this was not a line-by-line verification of every test, a production penetration test, or a load benchmark. No live model calls, provider purchases, production data inspections, tests, or deployments were performed during this audit. Existing test results from earlier work do not establish production latency or Jev quality.

Repository defaults use `gpt-4o-mini`; the storyteller permits environment overrides. The actual deployed model configuration, traffic, token distribution, and monthly bill were not inspected. Savings examples are explicitly hypothetical.

## What is already reusable and should be preserved

- The pure cast lifecycle, atomic same-slot replacements, world graph, travel rules, calendar, and evolving traits are good domain components.
- `SceneContext` already centralizes scene eligibility. Build on it instead of introducing another presence system.
- Story content is largely declarative, with a shared registry and authoring checks.
- Retrieval bundles are cached by character, and active-bundle selection uses a `ContextVar`; it is not an ordinary global session selector.
- SQLite work is already offloaded through `asyncio.to_thread` in repository methods, and WAL is enabled. Do not describe all database calls as blocking or replace SQLite without evidence.
- Per-session locks and recent-request deduplication exist. Strengthen their failure guarantees rather than recreating them.
- Dialogue has a shared presentation module, structured speaker metadata, frame-based animation, and a full-reply button. An older claim that it necessarily creates one DOM node per letter is stale.

## Audit findings and planned responses

Priority meanings: P0 = address before relying on the affected production path; P1 = correctness, cost, or scalability work before broader optimization; P2 = incremental maintainability or measured optimization.

| Priority | Evidence in the current code | Planned response |
| --- | --- | --- |
| P0 | [Deployment webhook](C:/Users/Christian/Documents/Projects/mvp_chat/deployment/gitwebhook.php:9) contains a literal signing secret. Whether that value is still active was not checked. [.cpanel.yml](C:/Users/Christian/Documents/Projects/mvp_chat/.cpanel.yml:8) contains broad directory deletion and copies one checkout to both beta and production, conflicting with the branch-specific webhook. | Treat the source credential as exposed until verified; replace and rotate it if active. Establish one branch-isolated deployment process, explicit file ownership, exit-code checks, and immutable release identities. Do not execute the destructive legacy path. This is proposed work only; no secret is reproduced here. |
| P1 | The [chat pipeline](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/prompt_engine.py:1926) mutates relationships, time, lifecycle state, and `turns` before the storyteller succeeds. Upstream HTTP or dialogue-decoding failures return without restoring the original in-memory state. State saving, JSONL logging, outbox enqueueing, and request deduplication are separate writes. | Stage a turn against an isolated working state. Commit validated state, completed reply/request ID, canonical turn record, and extraction job together. Publish the new in-memory state only after commit. Export JSONL from committed records if retained. Test failure at every boundary. |
| P1 | [Background extraction](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/prompt_engine.py:3070) changes the in-memory chunk store after the session snapshot is saved, then marks the job done. [Startup recovery](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/main.py:107) can mark jobs done without a loaded session or durable extracted results. [The extractor](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/knowledge/runtime/dialogue_extractor.py:82) turns provider failures into `[]`. | Store extracted chunks durably, keyed by session/message/extractor version; mark jobs done in the same transaction as those results. Distinguish successful empty extraction from retryable failure. Add bounded retries, leases, and periodic recovery. Preserve claim/source metadata in snapshots and retrieval. |
| P1 | [Journal projection](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/user_sessions.py:58) walks every character’s goal history without lifecycle or player-knowledge filtering. Upcoming characters have authored goals. | Create one player-visible projection policy for journal, roster, history metadata, and other public views. Keep future contestants and undiscovered/private goals hidden; retain legitimately learned history about former residents. Merely checking whether a character is currently active is insufficient. |
| P1 | [Chat API](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/prompt_engine.py:1926) is a 1,255-line function in a 3,181-line module. New-game and restore flows separately build characters, world state, persona, and relationships. Session endpoints import the chat module to access state. | Extract an application-level turn service, session factory, versioned snapshot codec, public projections, and command dispatcher. Preserve API contracts with compatibility wrappers while moving one responsibility at a time. |
| P1 | [Turn extraction](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/engine/extractors/turn_extractor.py:490), storytelling, translation, and memory each create HTTP clients. Provider/model selection differs: memory uses the storyteller URL/key but the fixed OpenAI model name. Only storyteller usage reaches the normal chat response. | Add task-specific model configuration and a shared async provider layer with persistent clients, deadlines, response validation, usage accounting, concurrency limits, and explicit fallback rules. A provider change must not silently select an unsupported model for another task. |
| P1 | [Retrieval](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/prompt_engine.py:2523) executes synchronously inside the async route. It includes [CPU embedding](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/knowledge/build/embedder.py:9), full BM25 scoring/sorting, and possible cold loading. | Move retrieval into a bounded executor; initialize the embedder safely and measure concurrent requests. Pass bundle identity explicitly. Do not parallelize dependent state mutations or raise thread counts blindly. |
| P1 | [Memory merging](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/knowledge/runtime/retrieve.py:141) uses session memories only when the canonical result list has spare slots. Eight canonical hits can suppress all dialogue-memory retrieval. | Evaluate a source-aware merge or reserved memory budget. Test that relevant learned facts remain available while player claims never become canonical truth. Treat this as a relevance/quality change, not an automatic performance win. |
| P1 | [Session and lock dictionaries](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/api/prompt_engine.py:1899) grow without general bounded eviction. [Guest cleanup](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/main.py:86) evicts every cached guest session whenever any expired guest rows were deleted. | Bound cached sessions and retire unused locks safely. Evict the exact expired/deleted session IDs, coordinate with in-flight turns and workers, and verify a late task cannot resurrect a deleted session. Keep one process until cross-process concurrency control exists. |
| P2 | [SessionChunkStore](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/knowledge/runtime/session_chunk_store.py:34) appends without ID deduplication and rebuilds tokenization/BM25 on each query. [History pagination](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/db/repos.py:556) reads and parses the whole JSONL file per page. | Deduplicate by stable chunk ID; cache tokenization and rebuild the memory index only when its version changes. Use indexed turn records for history pagination, or a measured indexed JSONL alternative. Keep durable history separate from bounded hot memory. |
| P2 | [Story registry](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/engine/story_loader.py:180) reparses the catalogue on lookup. Story graphs are mutable runtime objects. [Prompt assembly](C:/Users/Christian/Documents/Projects/mvp_chat/backend/app/engine/prompt_builder.py:1369) interleaves stable instructions with changing state and includes story-specific examples in the general engine. | Cache validated, immutable story definitions with explicit draft/reload invalidation. Instantiate fresh session state. Separate static prompt templates from state projections and move story-specific examples into content. Measure token changes and cache hits. |
| P2 | [Frontend index](C:/Users/Christian/Documents/Projects/mvp_chat/frontend/index.html:1) has 3,798 lines of layout, styling, state, network code, and features. [sendMessage](C:/Users/Christian/Documents/Projects/mvp_chat/frontend/index.html:2911) waits for the full JSON response; the retry ID is local and is not retained by a visible retry workflow. | Extract API transport, session store, chat, catalogue, journal, map, and authentication modules. Add pending-request persistence, timeout/retry UX, and accessible motion settings. Preserve the existing appearance before making product changes. |
| P2 | Untracked `world-map.js/css` and backend map payload work are present, but the current index does not load that module or consume `world_map`; it still uses the older image path. The webhook’s asset list also omits those files. [Service worker](C:/Users/Christian/Documents/Projects/mvp_chat/frontend/sw.js:1) caches static assets by URL. | Treat the map as unfinished integration, not dead code. Define a single frontend asset manifest used by HTML, backend serving, deployment, and service-worker versioning. Test stale-cache upgrade and rollback on both hosts. |
| P2 | [CI](C:/Users/Christian/Documents/Projects/mvp_chat/.github/workflows/tests.yml:1) uses Python 3.11 while [Docker](C:/Users/Christian/Documents/Projects/mvp_chat/Dockerfile:1) uses 3.10. Application files are copied before dependency installation, so ordinary source changes invalidate that layer. Build-time testing and startup index preparation are substantial. | Align and pin a tested runtime; put dependency installation before application copies; separate runtime/build/test dependency sets with a lock. Keep required test coverage, but build a tested runtime artifact once. Move recovery off the readiness-critical startup path and prebuild/fingerprint indexes. |

Additional audit follow-ups: validate chat/history request schemas and size limits before allocating locks or spending tokens; measure anonymous/guest request budgets; gate full-prompt logging behind operator diagnostics; replace raw upstream error bodies with stable public errors. Existing authentication and ownership checks must remain intact. Review the unused live-path `KnowledgeResolutionExtractor` and legacy `LocationExtractor` separately: playback/tests still reference the latter, so deleting it does not automatically save production API calls.

## Target organization for reuse

Keep a modular application in one deployable service. No microservice split, frontend-framework rewrite, or general plugin framework is required to gain reuse.

```text
backend/app/
  api/                  HTTP validation, authentication, public response schemas
  application/          proposed: turn service, commands, session factory, projections
  engine/               pure state transitions, cast, relationships, world, visibility
    prompts/            proposed: named templates and prompt composition
  llm/                  proposed: task contracts, provider adapters, routing, usage
  db/                   repositories, migrations, transactional turn and memory records
  knowledge/            retrieval, indexing, immutable content bundles
  workers/              proposed: durable memory jobs and recovery
  stories/              story rules, cast, maps, language/style content

frontend/
  index.html            application shell
  app/                  proposed: bootstrap, API client, session state
  features/             proposed: chat, catalogue, journal, roster, map, auth
  shared/               proposed: dialogs, avatars, formatting, motion preferences
```

Dependency direction: HTTP and workers call application services; application services call pure engine operations and injected provider/repository contracts. The engine must not import FastAPI routes, HTTP clients, or storage implementations. Preserve existing working modules and move files only when extracting real responsibilities.

Reusable contracts to define first:

1. **SessionFactory + SnapshotCodec:** one initialization path, versioned migrations, typed player identity, stable story-content version, tested restoration of older saves.
2. **TurnService:** accepts an authenticated identity, session ID, request ID, and command/message; returns a committed turn result. Distinguish validation failure, provider failure, and persistence failure.
3. **DecisionProvider / TextProvider:** separate bounded decisions from generated prose. Keep `TurnExtraction` as a validated internal result, not a provider response format embedded throughout the game.
4. **PlayerView:** visibility-filtered data shared by roster, journal, prompt inputs where appropriate, and API responses; operator views are separate.
5. **StoryDefinition:** validated immutable content; configurable slot groups, player capacity, bedrooms, arrival timing, and exhaustion policy. The six-resident rule remains deterministic code driven by Terrace House configuration.

Do not force one schema onto all stories. Preserve free-text goals and behavior tags; require content-authored categories only for features that can actually use them.

## Performance and cost work, in execution order

First record timing and token usage by stage: lock wait, restore, retrieval, turn extraction, prompt composition, storyteller, commit, translation, and background memory. Capture input/cached/output tokens, actual provider/model version, retries, fallback reason, and cost per successful committed turn. Background and evaluation spend belong in the ledger too.

Benchmark both stories, both Terrace House player genders, new/resumed sessions, short/long conversations, movement, time skip, queue exhaustion, and provider errors. Measure cold and warm starts; use 1, 10, and 50 concurrent independent sessions, plus concurrent requests to the same session. Record p50/p95 latency, time to first visible text, event-loop lag, CPU, RSS, queue age, and database write time. These are proposed tests, not measured production results.

Then implement these small changes independently:

| Change | Expected benefit | Required protection |
| --- | --- | --- |
| Reuse lifespan-managed HTTP clients | Avoid repeated connection setup across model calls | Per-provider configuration, clean shutdown, bounded connections and retries. HTTPX explicitly recommends scoped reusable clients for pooling. [HTTPX documentation](https://www.python-httpx.org/async/) |
| Move retrieval off the event loop | Better responsiveness across sessions during CPU work | Bounded executor, safe model initialization, isolation tests, CPU saturation measurements |
| Cache immutable definitions and versioned memory indexes | Less repeated parsing/tokenization | Invalidate on content edits or chunk changes; never share mutable session graphs |
| Reduce duplicated prompt inputs and sampled diagnostic payloads | Lower tokens, serialization cost, and log volume | Compare story behavior and visibility; do not remove relevant memory simply to shrink inputs |
| Group independent memory work behind a bounded durable worker | Less job latency and uncontrolled background concurrency | Idempotent results, correct provenance, durable completion; verify whether combining two texts preserves extraction quality |
| Use indexed history and bound hot caches | Predictable behavior in long sessions | Migration and deletion tests; durable memory must outlive cache eviction |
| Stable instruction prefixes for supported model caching | Potential input-cost and processing reduction | Measure cached tokens; a session or cache key does not guarantee a hit. [OpenAI prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching) |
| Offer immediate/full-reply or reduced-motion rendering | Lower perceived wait after the response arrives | Preserve speaker order, scrolling, accessibility, and the existing animation option |

Consider streaming only after turn transactions and frontend transport are reliable. Structured dialogue needs valid framing, buffering, cancellation semantics, and a defined policy for incomplete responses. Streaming improves time to first text; it does not automatically reduce tokens or time to completion.

Do not parallelize retrieval, extraction, state application, and narration indiscriminately: later stages consume earlier results. Do not expand workers/replicas until session revision checks and shared job ownership protect against cross-process races.

## Jev assessment

The model identified is **TypeSafe AI Jev**, currently documented as `jev-1.13.0`. Its API evaluates supplied state using Choice, Score, and Noul questions; it does not generate narration. Questions can share state in one request. [TypeSafe introduction](https://docs.typesafe.ai/introduction)

TypeSafe currently lists **$0.042 per million input tokens, with output free**. Limits are 64k tokens for state plus all questions and 32k for state plus the longest question. English is strongest; CJK use needs its own evaluation. Pin the tested version instead of relying on a moving alias. [Model reference](https://docs.typesafe.ai/models)

Vercel currently advertises a free promotional window ending September 25, 2026. Use normal pricing for the business case; provider limits and access must be checked when the pilot begins. [Vercel listing](https://vercel.com/ai-gateway/models/jev)

| Game task | Fit | Proposed treatment |
| --- | --- | --- |
| Clear movement intent and choosing among allowed destinations | Promising bounded decision | Parse exact commands locally first. Jev can select an allowed candidate or NONE/UNKNOWN; code validates travel. |
| Whether a message contains a fact worth sending to the memory extractor | Promising cost gate | Pilot with very high recall; ambiguous messages still use the existing extractor. Measure avoided calls, not just classifier price. |
| Determining whether supplied dialogue supports a candidate knowledge claim | Potential fit, sensitive to mistakes | Use explicit evidence and an uncertain outcome. Never let probability alone grant a character access to a secret. |
| Departure NONE/WISH/DECISION | Possible later pilot | Use the resident’s own attributed words. Preserve the existing eligibility, timing, replacement, and 3–3 checks in code. |
| Rubric scoring in offline playback | Best first pilot | Replace selected bounded grader judgments; retain human review and a generative explanation only when needed. |
| Writing dialogue, new factual sentences, novel goals, free-text behavior descriptions, or translation | Unsuitable direct replacement | Keep a generative model. These outputs cannot be replaced by setting a new model name. |
| Counting residents, queue order, dates, identity, authorization | No model needed | Continue deterministic code. |

The current `TurnExtractor` combines bounded choices with free-text fields. Replacing only its movement judgment with Jev while still running the whole old extractor would add cost and latency. A hybrid design must genuinely omit or shrink an existing call, and preserve every required field. Do not turn the deliberately open-ended social simulation into a fixed list of canned goals just to fit Jev.

Jev’s API is `POST https://api.typesafe.ai/v1/systemone`, with state and typed questions, not the existing chat-completions schema. Add a separate async adapter with its own credentials and task configuration; retain a validated provider-independent result. The HTTP response includes model identity and usage. [API reference](https://docs.typesafe.ai/api)

Confidence is not a guarantee of correctness. Choice/Score confidence summarizes their probability distributions; Noul returns a probability without that confidence field. Tune thresholds on labeled game data for each task and model version. [Confidence documentation](https://docs.typesafe.ai/confidence)

TypeSafe documents weaknesses with arithmetic, dates, indirection, adversarial state, irrelevant long context, and text generation. That makes code-enforced invariants and compact evidence essential. Do not adopt its headline vendor speed ratios as this game’s expected speedup. [Known limitations](https://docs.typesafe.ai/model-jaggedness/jev-1.13)

### Illustrative economics, not a current-bill estimate

The repository’s `gpt-4o-mini` default currently costs $0.15/M uncached input, $0.075/M cached input, and $0.60/M output tokens. The deployed storyteller may differ. [OpenAI model pricing](https://developers.openai.com/api/docs/models/gpt-4o-mini)

Assume 100,000 **eligible bounded-decision calls** currently use 3,000 uncached input and 400 output tokens each. Assume the equivalent Jev task uses 2,000 billable input tokens, and 10% require the original fallback:

| Scenario | Model cost for 100,000 eligible calls |
| --- | ---: |
| Existing model: `(3,000 × $0.15 + 400 × $0.60) / 1,000,000` each | $69.00 |
| Jev: `2,000 × $0.042 / 1,000,000` each | $8.40 |
| Jev plus 10% existing-model fallback | $15.30 |
| Reduction for this hypothetical operation | $53.70 / 77.8% |

That is not a 77.8% reduction in the whole game bill. If those operations account for 20% of total spend, the same assumptions yield about 15.6% total reduction. Cached baseline inputs, larger question sets, retained free-text generation, mistakes, retries, and added evaluation work can reduce or erase the gain.

Use the measured equation:

`new cost = Jev cost + fallback fraction × fallback cost + retained generation + retries`

Compare against actual cost per successful, quality-acceptable turn. For a memory gate, include both the gate cost and the fraction of messages that still require extraction. If the gate mostly says “extract,” it may not pay for itself.

### Pilot and rollout gates

1. Build at least 1,000 labeled cases from synthetic or appropriately approved/redacted examples across both games: normal conversation, negation, sarcasm, multi-speaker attribution, offscreen references, deliberate attempts to invent departures, and English/Japanese/Korean/Chinese cases relevant to actual use.
2. Start with offline grader judgments and memory-extraction eligibility. Record each question’s quality, latency, tokens, version, and fallback rate; assess total question fan-out cost.
3. Run Jev in shadow mode for selected turns: observe answers without applying changes. No broad duplication of every live call indefinitely.
4. Adopt a task only when it reduces measured spend, preserves the accepted quality baseline, and does not worsen p95 latency beyond the predeclared tolerance. Proposed gates: zero deterministic invariant violations; no new false departures or secret disclosures in the critical test set; at least 99% recall for a gate that would otherwise discard useful memory. A finite clean test set does not prove zero production errors.
5. Enable each task behind an independent flag, initially for a small beta cohort. Log resolved model version and fallback causes. Restore the existing provider automatically on timeout or invalid output. Use internal fallback rather than repeatedly interrupting the player for model uncertainty.
6. Re-evaluate version changes. Treat sensitive state transitions more conservatively than offline scoring. Verify provider access and data handling before sending real player content.

## Delivery sequence and acceptance criteria

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| 0. Record baseline and protect release paths | Confirm active deployment mechanism; plan credential rotation; capture architecture, model-call ledger, existing behavior, and repeatable workloads | Approved baseline and scoped, reproducible failure cases; beta/prod remain isolated |
| 1. Correctness foundation | Atomic turn commit, durable extracted facts, visibility-filtered journal, exact session cleanup | Failed/retried/interrupted turns cannot double-advance; facts survive immediate restart; future/private content stays hidden |
| 2. Reusable backend | Turn service, session factory/codec, public projections, provider contracts; compatibility wrappers | Existing endpoints and saved games behave the same; deterministic tests pass for both genres and full cast rotation |
| 3. Measured backend optimization | Persistent HTTP clients, bounded retrieval executor, versioned caches, indexed history, lightweight production telemetry | Comparable quality and correctness; p95 and memory use meet baseline; each optimization has before/after evidence |
| 4. Jev pilot | Offline evaluation, shadow metrics, then independent beta task flags | Demonstrated savings after fallback and retained calls; task-specific quality gates pass; one-step rollback works |
| 5. Reusable frontend and coherent assets | Extract feature modules, durable retry workflow, motion options, asset manifest and map integration | Desktop and iPhone-sized browser checks; no duplicate send; guest/auth resume, history, roster, map, journal, and offline upgrade work |
| 6. Delivery and documentation cleanup | Aligned Python versions, locked dependencies, efficient Docker layers, validated CI conditions, authoring/schema checks | Same tested artifact reaches beta; content/assets/build identity agree; production release remains separately requested |

Phases should be divided into small, independently reviewable changes. Add characterization tests before moving behavior. Test lifecycle balance, privacy, travel, persistence, retry semantics, and provider failure before evaluating style/latency. Use dependency checks to keep the engine independent of API/storage code. Add frontend checks to CI rather than relying entirely on historical screenshots.

Reconcile existing backlog items about mobile rendering, memory recovery, and model pacing against this current tree. Some prior work is already present; the untracked map work is incomplete integration. Preserve other in-progress changes and do not bundle unrelated cleanup into these phases.

**Recommended first implementation package, when requested:** baseline instrumentation plus the turn-commit and memory-durability tests; resolve the deployment credential/path findings before shipping it. Jev’s first evaluation should target offline grading and a memory gate, with the storyteller unchanged.
