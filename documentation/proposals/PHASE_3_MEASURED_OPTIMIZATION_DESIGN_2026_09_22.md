# Phase 3 — measured optimization: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md` Phase 3's 11-row table,
matching the detail level of the Jev design docs.

**Status: design only. Nothing here is implemented.**

The plan's own rule for this phase is the strictest in the whole document:
*"Every item requires Phase 0 before/after evidence. Any item whose
measurement shows a small win is dropped."* This design honors that by
specifying, per item, **the exact measurement to take and the exact threshold
that decides ship vs. drop** — not by assuming every row ships.

---

## 0. Measurement infrastructure this phase depends on

Two things must exist before any row below can be evaluated, and both already
do:

- **The stage ledger** (`backend/app/utils/stage_timer.py`, shipped, now
  covering `retrieval`/`extraction`/`storyteller`/`commit` as of the
  `extraction` stage added 2026-09-22) — gives before/after timing per stage.
- **The workload harness** (`scripts/bench/turn_workload_harness.py`, shipped)
  — drives repeatable load at 1/5/10/50 concurrency. BL-15 (open) tracks
  running its full matrix; several rows below explicitly require that before
  shipping, not before designing.

Nothing in this phase ships without a harness run showing the specific
before/after numbers named per row.

---

## 1. Lifespan-managed HTTP clients

### Current state, verified
18 construction sites (per the audit; re-confirmed: `httpx.AsyncClient(...)` at
`prompt_engine.py:1166,2920(ish, now inside the extraction stage)`,
`dialogue_extractor.py`, `location_extractor.py` ×2, `turn_extractor.py`,
`knowledge_resolution_extractor.py`, `debug_engine.py` ×6, plus Jev's own
`JevClient` once it's built per the provider architecture design).

### Design
`backend/app/llm/providers/base.py` (already named in the Jev architecture
doc's package layout) gains a **lifespan-scoped client registry**:

```python
class ClientRegistry:
    """One httpx.AsyncClient per (base_url, provider) pair, constructed at
    app startup and closed at shutdown. Providers request a client by name;
    nothing constructs its own."""
    def __init__(self) -> None:
        self._clients: dict[str, httpx.AsyncClient] = {}

    def get(self, name: str, *, base_url: str, timeout_s: float,
            max_connections: int = 20) -> httpx.AsyncClient:
        if name not in self._clients:
            self._clients[name] = httpx.AsyncClient(
                base_url=base_url, timeout=timeout_s,
                limits=httpx.Limits(max_connections=max_connections,
                                     max_keepalive_connections=max_connections),
            )
        return self._clients[name]

    async def close_all(self) -> None:
        for c in self._clients.values():
            await c.aclose()
```

Wired into `backend/app/main.py`'s `lifespan()`, alongside the existing warm-up
and cleanup tasks: `app.state.clients = ClientRegistry()` on startup,
`await app.state.clients.close_all()` on shutdown. Every provider
(`JevClient`, `OpenAIChatClient`, the storyteller call, translation) requests
its client from the registry instead of opening its own per call.

**Per-provider config, kept distinct** (the plan's own protection
requirement): each provider has its own `timeout_s` and `max_connections` —
Jev's should be tight (per `JEV_TIMEOUT_MS=1000`), the storyteller's stays at
its current 30s, translation keeps 30s. The registry does not force one
timeout onto every client.

### Measurement to take before shipping
Run the harness at concurrency 1, 10, 50 (BL-15's deferred full matrix — **this
row is the reason to finally run it**) with and without the registry. Record
p50/p95 `storyteller` stage time and CPU. **Ship threshold:** ≥5% p95
improvement at concurrency ≥10, since TLS+connection setup overhead only shows
up under concurrent load, not at concurrency 1 (where the audit itself notes
the effect is per-call, not compounding).

### Test plan
| Test | Assertion |
| --- | --- |
| `test_registry_reuses_client_for_same_name` | two `.get("jev", ...)` calls return the same object |
| `test_registry_separate_clients_per_provider` | `.get("jev", ...)` and `.get("storyteller", ...)` are different objects with independently-set timeouts |
| `test_close_all_closes_every_client` | after `close_all()`, each client's `.is_closed` is True |
| `test_lifespan_closes_clients_on_shutdown` | integration: `TestClient` context exit triggers `close_all` (mirrors the existing pattern for `_guest_cleanup_loop`/`_fact_extraction_periodic_sweep_loop` task cancellation on shutdown) |

---

## 2. Task-specific model configuration

### Current state, verified
`dialogue_extractor.py` (memory extraction) reads
`STORY_MASTER_BASE_URL`/`STORY_MASTER_API_KEY` but the hardcoded `OPENAI_MODEL`
name — so pointing the storyteller at a local Ollama instance (a documented,
supported local-dev mode) makes the memory extractor silently request a model
name Ollama does not have, while using Ollama's URL/key. This is the plan's
"correctness-adjacent" P1, not a performance item — it can produce a request
that 404s or picks an arbitrary Ollama model depending on that server's
behavior.

### Design
```python
# backend/app/config/settings.py — new, additive
TASK_MODELS: dict[str, TaskModelConfig] = {
    "storyteller":       TaskModelConfig(base_url=STORY_MASTER_BASE_URL, api_key=STORY_MASTER_API_KEY, model=STORY_MASTER_MODEL),
    "memory_extraction": TaskModelConfig(base_url=STORY_MASTER_BASE_URL, api_key=STORY_MASTER_API_KEY,
                                          model=os.getenv("MEMORY_EXTRACTION_MODEL", OPENAI_MODEL)),
    "turn_extraction":   TaskModelConfig(base_url="https://api.openai.com/v1", api_key=OPENAI_API_KEY, model=OPENAI_MODEL),
    "translation":       TaskModelConfig(base_url="https://api.openai.com/v1", api_key=OPENAI_API_KEY, model=OPENAI_MODEL),
}
```

`MEMORY_EXTRACTION_MODEL` is new and **independent** of `STORY_MASTER_MODEL` —
this is the actual fix: today `dialogue_extractor.py` imports `OPENAI_MODEL`
directly (verified: `from backend.app.config.settings import ... OPENAI_MODEL`
at `dialogue_extractor.py`'s existing import), so it already does NOT follow
`STORY_MASTER_MODEL` even in the correct case — it's hardcoded to the OpenAI
default regardless of story-master routing. The bug is real but its shape is
"ignores the override entirely," not "silently follows it to the wrong
provider." Corrected from the plan's original phrasing.

**Validation, per the plan's protection requirement:** at startup, for each
`TaskModelConfig` whose `base_url` is not `api.openai.com`, log a warning if
`model` still equals the OpenAI default — this is the actual signal that a
local-Ollama override was only partially applied.

### Measurement
This is correctness, not performance — no before/after threshold. Ship
criterion: a test proving local-mode (Ollama URL) config no longer silently
requests an OpenAI-shaped model for memory extraction.

### Test plan
| Test | Assertion |
| --- | --- |
| `test_memory_extraction_respects_its_own_model_override` | `MEMORY_EXTRACTION_MODEL` env var changes what `dialogue_extractor` requests, independent of `STORY_MASTER_MODEL` |
| `test_startup_warns_on_local_url_with_default_model` | Ollama-shaped `base_url` + unchanged model name → warning logged |
| `test_each_task_config_is_independently_overridable` | changing one `TaskModelConfig` entry does not affect another |

---

## 3. Bounded retrieval executor

### Current state, verified (Phase 1.3 already fixed the worst of this)
Phase 1.3 (shipped) fixed the *cold-start* blocking (15.9s → warmed
background). What Phase 1.3 did **not** touch: warm retrieval still runs
**synchronously on the event loop** inside the `retrieval` stage. Measured
originally: ~69ms warm, 10 concurrent sessions → ~176ms p50 loop lag. This
row is the *remaining* item — an order of magnitude less urgent than the cold
start Phase 1.3 already shipped, which is exactly why the plan sequences it
after 1.3 and into Phase 3.

### Design
```python
# backend/app/knowledge/runtime/retrieve.py — wrapping, not rewriting
_RETRIEVAL_EXECUTOR = ThreadPoolExecutor(max_workers=RETRIEVAL_EXECUTOR_WORKERS)  # default 4

async def retrieve_knowledge_async(query: str, **kwargs) -> Tuple[list, dict]:
    """Drop-in async wrapper. The existing synchronous retrieve_knowledge()
    is UNCHANGED — this just runs it off the loop, matching the
    asyncio.to_thread pattern already used for every DB repo call."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_RETRIEVAL_EXECUTOR, functools.partial(retrieve_knowledge, query, **kwargs))
```

Call site: `prompt_engine.py`'s `with stage_timer.stage("retrieval"):` block
calls `retrieve_knowledge_async` instead of `retrieve_knowledge`. One line
changed at the call site; the retrieval internals (BM25/FAISS/embedder) are
untouched.

**Why a `ThreadPoolExecutor` and not `asyncio.to_thread`:** `to_thread` uses
the default executor, shared with every other `to_thread` call in the process
(DB repos, etc.) — under load, CPU-bound retrieval work would compete with
I/O-bound DB work for the same limited pool. A dedicated pool with a small
worker count isolates retrieval's CPU cost from DB latency. `RETRIEVAL_EXECUTOR_WORKERS`
defaults to 4, tunable, capped low deliberately — the plan explicitly warns
against "raising thread counts blindly."

**Safe embedder init, per the plan's protection requirement:** Phase 1.3's
`_MODEL_LOCK` (shipped) already makes `_get_model()` safe for concurrent
callers from different threads — this executor change is exactly the scenario
that lock was built for, now actually exercised by concurrent threads rather
than concurrent coroutines on one thread.

### Measurement to take before shipping
Harness at concurrency 10 and 50 (again, BL-15's deferred matrix), comparing
event-loop lag (the same probe technique used to measure Phase 1.3's fix) with
retrieval on-loop vs off-loop. **Ship threshold:** measurable p50 loop-lag
reduction at concurrency ≥10 with no p95 retrieval latency regression >20ms
(thread handoff has its own small overhead — the win must exceed it).

### Test plan
| Test | Assertion |
| --- | --- |
| `test_retrieve_knowledge_async_returns_same_result_as_sync` | same query, same namespace → identical output between `retrieve_knowledge` and `retrieve_knowledge_async` |
| `test_retrieval_does_not_block_event_loop` | same technique as Phase 1.3's `test_startup_warm_up_does_not_block_the_event_loop`: a probe coroutine keeps ticking during a concurrent retrieval call |
| `test_concurrent_retrievals_reuse_the_locked_embedder` | N concurrent `retrieve_knowledge_async` calls trigger exactly one embedder load (Phase 1.3's lock, now exercised across threads) |
| `test_executor_worker_count_is_bounded` | pool size matches `RETRIEVAL_EXECUTOR_WORKERS`, does not grow unbounded |

---

## 4. `SessionChunkStore` ID dedup

### Current state, verified (already reclassified as correctness in the plan)
Measured in the original audit pass: the same `chunk_id` added 5 times via
`add_chunks()` produces `len() == 5`, not 1. `SessionChunkStore.add_chunks()`
(`backend/app/knowledge/runtime/session_chunk_store.py`) appends
unconditionally.

### Design
```python
def add_chunks(self, chunks: list[dict]) -> None:
    """Now dedupes by chunk_id: a re-add of an existing id REPLACES it
    (keeps the newest text/confidence for that id) rather than
    accumulating duplicates. Matches the semantics Phase 1.2's
    extracted_chunks table already uses (INSERT OR REPLACE keyed by
    (session_id, chunk_id, extractor_version))."""
    for chunk in chunks:
        cid = chunk.get("chunk_id")
        if not cid:
            continue
        self._by_id[cid] = chunk   # dict, not list — O(1) dedup by construction
    self._chunks = list(self._by_id.values())  # preserve existing .all_chunks() contract
```

Internal storage changes from a bare list to an id-keyed dict backing the same
list-shaped public surface (`all_chunks()`, `query()`, `__len__` all keep their
current signatures) — no caller outside this class changes.

**Idempotent re-extraction, the plan's explicit protection requirement:** this
is directly exercised by Phase 1.2's already-shipped retry path (a failed
extraction retried re-runs both message halves and calls `add_chunks` again
with the same `chunk_id`s) — this fix makes that retry idempotent at the
in-memory layer too, matching what `mark_done_with_chunks`'s `INSERT OR
REPLACE` already guarantees at the durable layer. The two layers were
inconsistent; this closes that gap.

### Measurement
Correctness fix, not a performance item — no before/after threshold needed.
Ship criterion: the reproduction test from the original finding now asserts
`len() == 1`, not `== 5`.

### Test plan
| Test | Assertion |
| --- | --- |
| `test_add_chunks_same_id_twice_deduplicates` | the exact reproduction: same `chunk_id` added 5× → `len() == 1` |
| `test_add_chunks_same_id_keeps_newest_text` | re-add with different `text` → the newer text wins |
| `test_all_chunks_and_query_unaffected_by_storage_change` | existing `SessionChunkStore` tests (already passing) continue to pass unmodified |
| `test_idempotent_retry_does_not_duplicate` | simulate Phase 1.2's retry path calling `add_chunks` twice with the same extracted chunks → store ends with one copy each |

---

## 5. Cache story registry / BM25 tokenization — **DROPPED, restated**

Already measured and dropped in the engineering plan (§0.3): 2.13ms and 2.05ms
respectively, against a multi-second storyteller call. **No design follows.**
This row exists in this document only so Phase 3's table has an entry for
every original row — the disposition is unchanged: do not build this. Revisit
only if a session's `SessionChunkStore` exceeds ~1,000 chunks in real telemetry
(watch for this in Phase 0B's ongoing ledger, not a new measurement task).

---

## 6. Indexed history pagination — **gated, design deferred**

The plan gates this explicitly: *"gated on Phase 0 showing real transcript
sizes justify it."* That measurement has not been taken (BL-15's deferred
matrix does not include it; it needs a distinct measurement — real JSONL file
sizes for long-lived sessions, not turn latency).

**Design is deliberately not written here.** Writing an indexing scheme before
knowing whether any real session's JSONL exceeds a few hundred KB would be
designing against a guess, which this phase's entire discipline exists to
avoid. **Action item, not a design:** add one line to the Phase 0B workload
harness (or a one-off script) that reports `_jsonl_path` file sizes across
real beta sessions. If the largest is under ~200KB (a reasonable read-the-
whole-file-fast threshold), this row is dropped like row 5. If not, this
document gets an update with the actual design, sized to the actual problem.

---

## 7. Source-aware memory merge

### Current state, verified
`retrieve.py:_merge_session_chunks` (`backend/app/knowledge/runtime/retrieve.py:141`):
session (dialogue-extracted) chunks fill only the **remaining** slots after
canonical (BM25/FAISS) results, up to `k_final` (default 8). If canonical
retrieval alone fills all 8 slots, session memory contributes **zero** results
regardless of relevance — confirmed by reading the exact `remaining = max(0,
k_final - len(main_results))` / `if remaining == 0: return main_results, 0`
logic.

### Design — explicitly a quality experiment, not a performance change
Per the plan: *"Quality change, not a perf win — needs A/B on story behavior;
player claims must never become canonical."* Two candidate merge policies,
both preserving the existing non-canonical confidence tagging
(`dialogue_fact`/`player_stated`/`ai_stated` — Phase 1.2's `ExtractionResult`
chunks already carry this):

**Policy A — reserved budget:** `k_final` unchanged at 8, but reserve a fixed
sub-budget (e.g. 2 of 8) for session chunks unconditionally, even when
canonical fills the rest:

```python
def _merge_session_chunks_reserved(main_results, session_store, query, k_final, reserved=2):
    canonical_budget = k_final - reserved
    session_hits = session_store.query(query, top_k=reserved + 4) if session_store else []
    kept_canonical = main_results[:canonical_budget]
    added = [c for c in session_hits if c["chunk_id"] not in {c["chunk_id"] for c in kept_canonical}][:k_final - len(kept_canonical)]
    return kept_canonical + added, len(added)
```

**Policy B — source-aware ranking:** merge and re-rank canonical + session by
score, tie-broken toward canonical (never letting session-sourced (i.e.
player-stated) content outrank an equally-scored canonical fact — the "player
claims never become canonical" guarantee expressed as a tie-break rule rather
than a strict slot reservation).

**Recommendation: implement Policy A first.** It is simpler, its behavior
change is easier to reason about in an A/B (a fixed reserved slot vs. none),
and Policy B's re-ranking introduces a scoring-comparability question (BM25
score vs. session-store keyword-overlap score aren't on the same scale) that
would need its own normalization design before it's safe to ship — not
detailed here because it is Policy A's job to first prove the *reservation
concept* is worth having before investing in re-ranking sophistication.

### Measurement — an A/B, not a latency number
This item cannot be evaluated by the stage ledger; it needs a **quality**
signal. Concretely: run the same fixed conversation transcript (or several)
through both the old and new merge policy, and manually or LLM-graded compare
whether player-revealed facts that should be retrievable in a later turn
actually appear in the prompt's retrieved-chunk list. **Ship threshold:** the
new policy retrieves at least as many relevant session facts as the old one on
a fixed test transcript, with zero instances of a session-sourced chunk being
treated as canonical truth (checked by asserting `confidence` tags are
preserved through the merge, unchanged).

### Test plan
| Test | Assertion |
| --- | --- |
| `test_reserved_budget_never_starves_session_chunks_when_canonical_fills` | 8 canonical hits + relevant session chunks available → session chunks still appear (today: they do not) |
| `test_reserved_budget_does_not_exceed_k_final` | total results still ≤ `k_final` regardless of how many session chunks exist |
| `test_session_chunks_retain_non_canonical_confidence_tag_through_merge` | the actual invariant — player-stated facts are never re-tagged as canonical by the merge |
| `test_dedup_by_chunk_id_still_applies_across_merge` | a session chunk with the same id as a canonical hit does not duplicate (uses row 4's fixed dedup) |

---

## 8. Reduce duplicated prompt inputs and sampled diagnostics

### Current state
No single measurement exists yet distinguishing "duplicated" tokens from
necessary ones — this is a token-audit task, not a known bug. The plan's
protection requirement — *"compare story behavior and visibility; never remove
relevant memory just to shrink input"* — means this row's actual first step is
**instrumentation**, not a code change:

### Design
Add a debug-only breakdown to the existing `prompt_debug` block already logged
in `chat_request` (`prompt_engine.py`, existing `_log({"kind": "chat_request",
..., "prompt_debug": ...})`): per-layer token counts for the 11 documented
system-prompt layers (base, retrieved knowledge, self-knowledge, canonical
memories, relationship context, location, belief context, character details,
truth override, first-turn hint, required tail — from
`MEMORY_TO_PROMPT_FLOW_TRACE.md`'s documented layer order). This surfaces which
layer is actually large before anyone guesses at "duplication."

The "sampled diagnostic payloads" half is more concrete and independently
actionable: `_log()` calls throughout `prompt_engine.py` already log full
`user_msg`/`assistant_reply_preview` on every turn regardless of environment.
**Add `LOG_FULL_PROMPTS` env var (default false in production, true in local
dev)** gating the full-prompt/full-reply fields — this is also the "full-
prompt logging gated behind operator diagnostics" item the original audit's
follow-ups section separately names, so this row absorbs that item too rather
than tracking it twice.

### Measurement
Per-layer token counts, captured from real six_strangers turns via the new
debug breakdown, reviewed by hand before deciding which layer (if any) has
genuine duplication worth removing. **This row's exit criterion is the
measurement itself + a decision, not a guaranteed code change** — it may
conclude "nothing here is actually duplicated," which is a valid, plan-
consistent outcome (cf. row 5).

### Test plan
| Test | Assertion |
| --- | --- |
| `test_prompt_debug_includes_per_layer_token_counts` | the new breakdown appears in `prompt_debug`, sums to the total prompt token count |
| `test_full_prompt_logging_gated_by_env_var` | `LOG_FULL_PROMPTS=false` → `user_msg`/`assistant_reply_preview` absent or truncated in the logged event; `true` → present |
| `test_log_full_prompts_defaults_false_in_production_shape` | mirrors the pattern of `LANGSMITH_TRACING`/`TYPESAFE_ENABLED` — off by default, explicit opt-in |

---

## 9. Bounded durable memory worker

### Current state
Phase 1.2 (shipped) already built the durable outbox, the lease-based
`claim_pending`, and the periodic sweep. The plan's remaining ask —
*"Formalizes Phase 1.2's queue"* — is really about **bounding concurrency**:
today, `_extract_and_store_durable` fires via
`asyncio.ensure_future` with no cap on how many can run at once if many turns
complete in a short window.

### Design
```python
# backend/app/llm/ (or application/) — a small addition, not a new subsystem
_EXTRACTION_SEMAPHORE = asyncio.Semaphore(EXTRACTION_MAX_CONCURRENT)  # default 8

async def _extract_and_store_durable(...):
    async with _EXTRACTION_SEMAPHORE:
        # existing Phase 1.2 body, UNCHANGED
        ...
```

One semaphore acquired at the top of the existing (already correct) function
body. This bounds "uncontrolled background concurrency" (the plan's phrase)
without touching the durability/atomicity Phase 1.2 already shipped and
tested.

**Verify combining two texts preserves extraction quality — the plan's stated
open question:** this refers to whether batching the user-message and
AI-reply extraction into one Jev-style combined call (rather than the current
two separate `extract_facts_with_status` calls per turn) changes recall. This
is a Jev-design-adjacent question, not a bounding-concurrency one — flagged
here as **out of this row's scope**, folded instead into the Jev extractor
redesign's Call B (which already combines candidate-chunk knowledge questions
with previous-reply speaker detection in one batch, per
`JEV_EXTRACTOR_REDESIGN_2026_09_22.md` §6). Not duplicated as separate design
work.

### Measurement
Harness at concurrency 50 (BL-15's deferred tier), comparing peak concurrent
extraction tasks and DB connection contention with and without the semaphore.
**Ship threshold:** no increase in `mark_failed` rate (the semaphore must not
starve legitimate work) and a measurable cap on peak concurrent SQLite writes.

### Test plan
| Test | Assertion |
| --- | --- |
| `test_extraction_concurrency_is_bounded` | N+1 simultaneous turns → at most `EXTRACTION_MAX_CONCURRENT` extraction tasks running at once (probed via a counter incremented/decremented around the semaphore) |
| `test_bounded_concurrency_does_not_change_durability_guarantees` | Phase 1.2's existing durability tests (`test_mark_done_with_chunks_persists_chunks_and_marks_done_atomically`, etc.) pass unmodified with the semaphore in place |
| `test_semaphore_does_not_deadlock_under_sustained_load` | harness run at concurrency 50 completes without hanging tasks |

---

## 10. Stable instruction prefixes for prompt caching

### Current state, verified
`prompt_builder.py` interleaves stable instructions with changing state (the
11-layer order documented in `LAYER_COVERAGE_MAPPING.md`/
`MESSAGE_TO_PROMPT_FLOW_TRACE.md` mixes static rules with per-turn
relationship/location state within the same contiguous prompt, rather than
ordering all-static-first). Independently confirmed via the live turn measured
for the Jev cost model: `cached_tokens: 0` on a real turn (from
`PHASE_0B_BASELINE_NOTES_2026_09_22.md`), i.e. **zero prompt caching is
currently happening at all**, on any provider that supports it.

### Design
Reorder `system_prompt()`'s layer composition (not its *content* — each
layer's text is unchanged) so **all layers whose content is identical across
consecutive turns of the same session appear first**, and layers that change
every turn appear last:

```
STABLE PREFIX (identical turn-to-turn within a session):
  1. base prompt (rules, style, behavior, language)          <- story-invariant
  2. character self-knowledge                                 <- changes only on cast rotation
  3. retrieved knowledge                                       <- changes per query, NOT stable — moves below
CHANGING SUFFIX:
  retrieved knowledge (per-turn query results)
  canonical memories (grows over the session but doesn't change past content)
  relationship context (mutates every turn)
  location description
  belief context
  character details
  truth override
  first-turn hint
  required tail
```

This is a **reordering**, not a rewrite: `system_prompt()`'s existing
per-layer builder functions are called in a different sequence and their
outputs concatenated in that new order. The 11 layers' individual content
generation is untouched.

**Measure cached tokens — the plan's explicit protection requirement, because
a cache key does not guarantee a hit:** OpenAI's prompt caching activates
automatically for prefixes ≥1024 tokens that are byte-identical across
requests within the provider's cache TTL window; it is not something this
codebase requests, only something this codebase can make *possible* by
ordering. Verification is entirely in the token accounting, not in code
behavior.

### Measurement to take before shipping
Two consecutive turns in the same session, before and after reordering,
reading `usage.prompt_tokens_details.cached_tokens` from the real OpenAI
response (the exact field already surfaced in
`PHASE_0B_BASELINE_NOTES_2026_09_22.md`'s baseline). **Ship threshold:**
`cached_tokens > 0` on the second turn after reordering, where it was
confirmed `0` before. If reordering alone does not produce a nonzero value
(the stable prefix may still be under the provider's minimum cacheable
length, or per-turn retrieved-knowledge content placed too early still
breaks the prefix), this row is **not shipped** until the actual byte-level
prefix is confirmed stable — no guessing.

### Test plan
| Test | Assertion |
| --- | --- |
| `test_stable_layers_are_byte_identical_across_turns_same_session` | base prompt + self-knowledge output is `==` across two turns with no cast change |
| `test_layer_reordering_preserves_full_prompt_content` | the SET of text in the reordered prompt equals the set in today's order — nothing is dropped or duplicated, only moved |
| `test_cached_tokens_nonzero_on_second_turn` | integration test against a real (or faithfully mocked, if run in CI without a live key) provider response, asserting the measured field |

---

## 11. Immediate/full-reply and reduced-motion rendering

### Current state
Frontend-only. Explicitly overlaps **BL-13** (the deferred iOS/mobile overhaul
backlog item) — the plan says to re-audit BL-13 before acting, since that
audit's own P1 finding (broken portraits) already proved stale once. **No
design is written here** for the same reason row 6 has none: acting before
re-auditing would risk designing against another stale finding.

**Action item, not a design:** re-run BL-13's audit steps (per its own
"What's needed" note) before this row gets a design. This belongs to Phase 5
(frontend), not Phase 3 — flagged here only because the original plan table
listed it under Phase 3; it is cross-referenced from
`PHASE_5_FRONTEND_MODULARIZATION_DESIGN_2026_09_22.md` §6 where the frontend
work actually lives.

---

## 12. Sequencing within Phase 3

```
Row 4 (SessionChunkStore dedup)  ──── independent, ship first (pure correctness, no measurement gate)
Row 2 (task-specific model config) ── independent, ship early (correctness, no measurement gate)
Row 1 (lifespan HTTP clients)  ─────┐
Row 3 (bounded retrieval executor) ─┼── both need the harness's concurrency 10/50 tier (BL-15)
Row 9 (bounded memory worker)  ─────┘
Row 10 (stable prefix caching)  ──── independent, needs only a 2-turn same-session measurement
Row 7 (source-aware merge)  ──────── independent, needs a quality A/B transcript, not the load harness
Row 8 (dedup prompt inputs)  ─────── independent, needs the new per-layer debug breakdown first
Row 5, 6, 11  ─────────────────────  no design (dropped / gated / deferred to Phase 5)
```

Rows 1, 3, 9 share a dependency: **running BL-15's deferred concurrency 10/50
harness tier**, which is real paid-provider load and was explicitly left as a
deliberate follow-up rather than an unattended background run. Scheduling that
harness run is this phase's actual first action, not writing more code.

## 13. Exit criteria (unchanged from the plan, restated precisely)

- Quality and correctness unchanged — verified by each row's own
  characterization tests against current behavior.
- p95 and RSS meet or beat baseline — verified against the Phase 0B baseline
  already captured (`PHASE_0B_BASELINE_2026_09_22.json`).
- Every shipped optimization has before/after evidence — this document names
  the exact measurement per row; a row without a passing measurement does not
  ship, per row 10's explicit "not shipped until confirmed" language as the
  model for the rest.
- Every dropped item has a recorded measurement justifying the drop — rows 5
  already has one; row 6 and 11 have an explicit deferral reason instead of a
  measurement, which is the correct disposition when the measurement itself
  hasn't been taken yet, not a violation of this criterion.
