# Jev provider architecture — implementation design

September 22, 2026. Implementation-level design for routing bounded decisions to
Jev with automatic, per-request fallback to the existing generative path.

**Status: implementation started 2026-09-22.** Steps 1–5 of §12's
implementation order are shipped (see that section for exact commits and
live-verification evidence). Steps 6–9 (the remaining abilities) are not
started. `TYPESAFE_ENABLED=false` remains the shipped default — nothing here
is live in production regardless of what's implemented.

Companion to:
- `JEV_EXTRACTOR_REDESIGN_2026_09_22.md` — *which* abilities move to Jev (the
  ability chart and per-ability test cases). Read that first.
- `ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md` — the surrounding
  phases. This document is the concrete form of that plan's
  `DecisionProvider` / `TextProvider` contract (Phase 2) and Jev pilot
  (Phase 4).

This document answers three questions the ability chart did not:
1. What does the codebase look like after Jev?
2. What exactly is `call_jev()`, and how does fallback work per request?
3. How is it flagged, rolled out, and rolled back?

---

## 1. Measured facts this design is built on

All measured on 2026-09-22 against live `jev-1.13.0` and live `gpt-4o-mini`
from the same machine over the same network connection.

### Latency is flat in question count

| Questions in one request | p50 latency | input tokens |
| ---: | ---: | ---: |
| 1 | 190 ms | 408 |
| 8 | 221 ms | 863 |
| 16 | 227 ms | 1,401 |
| 30 | 214 ms | 2,353 |
| 50 | 210 ms | 3,713 |

**Fan-out is free in latency terms.** Jev is non-autoregressive — it evaluates
every question against the state in parallel. Adding questions costs tokens, not
time. This single fact drives the batching design in §5: prefer **more questions
in fewer requests**, bounded only by token cost and the docs' warning about
irrelevant state.

### Against the current extractor

| | p50 | range | tokens |
| --- | ---: | ---: | --- |
| Current `TurnExtractor` (1 × gpt-4o-mini) | **3,600 ms** | 2,353–4,048 | ~4,371 in + 700 out |
| Jev batch (any size up to 50 questions) | **~210 ms** | 168–285 | ~2,100 in, output free |

**Read this as a ratio, not as absolute production numbers.** Both were measured
from a developer machine whose connection to `api.openai.com` is slower than
Railway's. The ratio (~17×) is fair because both legs used the same connection;
the absolute 3,600 ms is pessimistic for production.

**Action item (cheap, do this first):** the Phase 0B stage ledger
(`backend/app/utils/stage_timer.py`) currently instruments `retrieval`,
`storyteller`, and `commit` but **not** extraction. Add an `extraction` stage so
production extractor latency is a recorded fact rather than an inference. Until
then, treat the turn-latency benefit as *expected* rather than *established* —
Phase 0B's measured total turn p50 of 3.1–3.9 s is not reconcilable with a
3,600 ms production extractor, which is itself evidence that production is
faster than this local measurement.

### Incidental finding: `confidence` is already broken

In the measurement above the current extractor returned `movement_intent=MOVE`,
`destination_id=terrace` — correct — with **`confidence=0.0`**. The model does
not reliably populate the self-reported confidence field the prompt asks for.
This independently justifies ability 3 in the redesign doc (delete the field;
use Jev's native `confidence` / `probabilities`).

---

## 2. What the world looks like after Jev

### Before

```
prompt_engine._chat_handler_impl
        │
        ├─ retrieve_knowledge(...)                      [sync, blocking]
        │
        ├─ TurnExtractor.extract(...)                   ← 1 LLM call, ~3.6 s
        │     builds a 5,790-char system prompt inline
        │     builds its own httpx.AsyncClient inline
        │     parses one JSON blob into TurnExtraction
        │     returns TurnExtraction() on ANY failure
        │
        ├─ apply pipeline (movement, relationships, departures, shifts…)
        └─ storyteller call
```

Problems this design fixes, beyond cost: `engine/extractors/turn_extractor.py`
imports `httpx` and hardcodes an OpenAI URL, violating the plan's "engine must
not import HTTP clients" constraint; the prompt is a string literal inside the
method; and every failure collapses to the same silent empty result.

### After

```
prompt_engine._chat_handler_impl
        │
        ├─ retrieve_knowledge(...)
        │
        ├─ TurnExtractor.extract(...)                   ← unchanged signature,
        │     │                                            unchanged return type
        │     ├─ build_decision_batches(state, msg, …)  [pure, no I/O]
        │     ├─ await resolver.resolve(batches)        ← Jev or fallback
        │     └─ assemble_turn_extraction(outcomes)     [pure, no I/O]
        │
        ├─ apply pipeline                               ← UNTOUCHED
        └─ storyteller call                             ← UNTOUCHED
```

**The compatibility guarantee:** `TurnExtractor.extract()` keeps its signature
and keeps returning a `TurnExtraction`. `prompt_engine`'s ~400 lines of apply
logic, and every existing test that drives it, are unmodified. The only
`TurnExtraction` schema changes are the two the redesign doc justifies:
`destination_text` deleted (dead field), `confidence` re-sourced from the
provider instead of the model's self-report.

### New package layout

```
backend/app/llm/                     ← NEW. All provider I/O lives here.
  __init__.py
  providers/
    __init__.py
    jev.py            JevClient        — raw POST /v1/systemone, no policy
    openai_chat.py    OpenAIChatClient — raw chat/completions, no policy
    base.py           shared timeout/retry/usage plumbing
  decisions/
    __init__.py
    types.py          Decision, DecisionBatch, DecisionAnswer, DecisionOutcome,
                      Criticality, Provider, FallbackReason
    resolver.py       DecisionResolver.resolve()   ← THE call_jev() core (§4)
    health.py         JevCircuitBreaker            ← §6
  usage.py            UsageLedger — tokens/cost/provider, feeds stage_timer

backend/app/engine/extractors/
  turn_extractor.py   becomes: batch builder + assembler + legacy prompt.
                      NO httpx import. NO hardcoded URL.
  decision_registry.py  ← NEW. Pure data: every Decision definition (§9).
```

Dependency direction: `engine/` defines decisions as **pure data** and assembles
results; `llm/` performs I/O. `engine/` never imports `llm/` — the resolver is
**injected** into `TurnExtractor.__init__`, defaulting to a module-level
singleton constructed in `llm/`. That also makes the resolver trivially mockable
in tests.

**The purity constraint is currently violated and unenforced.** The engineering
plan states "the engine stays pure... enforced by a test, not convention", but
that test does not exist — verified by search. Three files under `engine/`
import `httpx` today:

```
backend/app/engine/extractors/turn_extractor.py:7
backend/app/engine/extractors/location_extractor.py:9
backend/app/engine/extractors/knowledge_resolution_extractor.py:7
```

Step 3 of §12 removes the import from `turn_extractor.py` (the file this design
touches) and **adds the missing enforcement test** — an import-direction test
asserting no module under `backend/app/engine/` imports `httpx`, `fastapi`, or
`backend.app.db`. That test will initially need `location_extractor.py` and
`knowledge_resolution_extractor.py` on an explicit, documented allowlist, since
neither is in this design's scope: `location_extractor` is legacy-but-still-
referenced by playback/tests, and `knowledge_resolution_extractor` is flagged by
the audit as possibly unused on the live path. Shrinking that allowlist to empty
is follow-up work, not a silent expansion of this one.

---

## 3. The core contract

```python
# backend/app/llm/decisions/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Mapping, Sequence


class Criticality(Enum):
    """Decides fallback granularity when a Jev answer is unusable. See §5."""
    CRITICAL = "critical"      # an engine invariant depends on it -> full
                               # legacy re-extraction for the whole turn
    DEGRADABLE = "degradable"  # absence is already a valid state today ->
                               # leave the field at its dataclass default


class Provider(Enum):
    JEV = "jev"
    LEGACY_LLM = "legacy_llm"
    DEFAULT = "default"        # nothing answered; dataclass default used


class FallbackReason(Enum):
    NONE = "none"
    FLAG_DISABLED = "flag_disabled"        # task not enabled -> never tried Jev
    CIRCUIT_OPEN = "circuit_open"          # breaker open -> skipped Jev
    SHADOW_MODE = "shadow_mode"            # Jev ran, answer deliberately unused
    TIMEOUT = "timeout"
    HTTP_ERROR = "http_error"
    MALFORMED_RESPONSE = "malformed_response"
    MISSING_ANSWER = "missing_answer"      # question id absent from answers
    INVALID_OPTION = "invalid_option"      # choice not in `allowed`
    BELOW_THRESHOLD = "below_threshold"    # confidence/probability too low


@dataclass(frozen=True)
class Decision:
    """One bounded question. Pure data — no I/O, no provider knowledge."""
    id: str                                   # stable; used as the Jev question key
    task: str                                 # rollout flag group, e.g. "movement"
    kind: Literal["choice", "score", "noul"]
    instructions: str
    criteria: Mapping[str, str] | Sequence[str]
    criticality: Criticality

    # --- validation, applied to whatever provider answered ---
    allowed: frozenset[str] | None = None     # choice: valid option ids
    none_option: str | None = None            # choice: the "no answer" option
    min_confidence: float | None = None       # choice/score: reject below this
    true_threshold: float | None = None       # noul: p >= this means True

    # --- how the legacy LLM answer maps onto this decision ---
    legacy_path: tuple[str, ...] = ()         # e.g. ("movement", "intent")


@dataclass(frozen=True)
class DecisionBatch:
    """Decisions sharing one `state` blob, sent as ONE Jev request."""
    name: str                                 # "current_message" | "previous_reply" | "ripe_window"
    state: str
    decisions: tuple[Decision, ...]


@dataclass(frozen=True)
class DecisionAnswer:
    """Provider-independent answer for one Decision."""
    decision_id: str
    provider: Provider
    # exactly one of these is populated per `kind`
    choice: str | None = None
    score: float | None = None
    probability: float | None = None
    # always populated when the provider supplies it
    confidence: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    fallback_reason: FallbackReason = FallbackReason.NONE

    @property
    def usable(self) -> bool:
        return self.fallback_reason is FallbackReason.NONE


@dataclass(frozen=True)
class DecisionOutcome:
    """Everything one turn's resolution produced. Consumed by the assembler."""
    answers: Mapping[str, DecisionAnswer]     # decision_id -> answer
    legacy_raw: dict[str, Any] | None         # legacy JSON, if the legacy path ran
    provider_used: Provider                   # dominant provider for this turn
    jev_latency_ms: float | None
    legacy_latency_ms: float | None
    jev_usage: Mapping[str, int] | None       # input/output tokens
    fallback_reasons: Mapping[str, FallbackReason]
    shadow_disagreements: Mapping[str, tuple[Any, Any]]  # id -> (jev, legacy)
```

---

## 4. `resolve()` — the `call_jev()`-with-fallback core

This is the function the user asked for. It is deliberately the **only** place
that decides between providers; no call site ever branches on "is Jev up".

```python
# backend/app/llm/decisions/resolver.py

class DecisionResolver:
    def __init__(
        self,
        jev: JevClient,
        legacy: LegacyExtractionCallable,   # the existing one-shot LLM call
        health: JevCircuitBreaker,
        config: JevConfig,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None: ...

    async def resolve(
        self,
        batches: Sequence[DecisionBatch],
        legacy_request: LegacyExtractionRequest,
    ) -> DecisionOutcome:
        """Resolve every decision in `batches`.

        ALWAYS returns a usable DecisionOutcome. Never raises. Never surfaces
        provider state to the caller. `legacy_request` carries everything the
        legacy one-shot LLM call needs, so fallback requires no extra plumbing
        at the call site.
        """
```

### Exact control flow

```
resolve(batches, legacy_request):

 1. PARTITION by flag (§7)
    For each decision, look up its `task`:
      - task in JEV_ENABLED_TASKS  -> route to Jev
      - task in JEV_SHADOW_TASKS   -> route to Jev AND force legacy; use legacy
      - otherwise                  -> legacy only
    If no decision routes to Jev at all:
        -> run legacy once, map via legacy_path, return. DONE.
           (This is the "no-Jev" mode: byte-identical behaviour to today.)

 2. CIRCUIT CHECK (§6) — costs nothing, no network
    if health.state is OPEN:
        record FallbackReason.CIRCUIT_OPEN for all Jev-routed decisions
        -> run legacy once, map, return. DONE. (No timeout penalty paid.)

 3. CALL JEV — all batches CONCURRENTLY
    asyncio.gather(*[jev.ask(b, timeout=config.timeout_ms) for b in batches],
                   return_exceptions=True)
    Concurrency is safe and correct: batches are independent by construction
    (§5), and latency is flat in question count, so N concurrent batches cost
    ~one batch of latency.

 4. PER-BATCH OUTCOME
    exception / timeout / non-2xx / unparseable  -> health.record_failure()
                                                    every decision in that batch
                                                    gets the matching
                                                    FallbackReason
    success                                      -> health.record_success()

 5. PER-ANSWER VALIDATION  (runs on Jev answers only)
    missing question id                    -> MISSING_ANSWER
    choice not in decision.allowed         -> INVALID_OPTION
    choice == decision.none_option         -> USABLE, means "no answer" (not a
                                              failure — this is the designed
                                              escape hatch, see TC-04)
    confidence < decision.min_confidence   -> BELOW_THRESHOLD
    noul probability -> bool via decision.true_threshold (never a failure;
                                              a low probability is a valid False)

 6. DECIDE FALLBACK GRANULARITY  (§5 — the important rule)
    unusable_critical = [d for d in jev_routed
                         if not answers[d.id].usable
                         and d.criticality is CRITICAL]

    if unusable_critical:
        -> run legacy ONCE for the whole turn
        -> use legacy answers for EVERY decision, discard all Jev answers
        -> provider_used = LEGACY_LLM
        Rationale: the legacy prompt is monolithic and cannot be cheaply asked
        for a subset. One known-good call beats a partial blend, and avoids
        maintaining a second "partial" prompt variant forever.
    else:
        -> keep every usable Jev answer
        -> every unusable DEGRADABLE decision gets Provider.DEFAULT, and the
           assembler leaves that field at its dataclass default. This is
           EXACTLY today's behaviour when the LLM omits a field, so it is not
           a new failure mode.
        -> provider_used = JEV

 7. SHADOW RECONCILIATION (only if any task is in shadow mode)
    Both ran. Return the LEGACY answers. Record per-decision
    (jev_value, legacy_value) pairs in shadow_disagreements for offline review.
    Never let a shadow answer reach game state.

 8. EMIT TELEMETRY (§10) and return the DecisionOutcome.
```

### Timeout budget, and the honest cost of the failure path

| Setting | Value | Why |
| --- | --- | --- |
| `JEV_TIMEOUT_MS` | **1000** | ~4.8× measured p50 (210 ms) and ~3.5× measured max (285 ms). Chosen over a looser 1500 ms to cap the failure-path regression at 1.0 s. See the flapping caveat below. |
| `JEV_CONNECT_TIMEOUT_MS` | 500 | A connect failure is not a slow answer; fail fast. |
| retries within a turn | **0** | Do not retry Jev inside a turn. A retry costs another timeout window before fallback. The circuit breaker is the retry mechanism, across requests. |

**Worst case, stated plainly:** Jev hangs to the full 1,000 ms, then legacy runs
normally. That turn costs `1000 ms + legacy`, i.e. a ~1.0 s regression versus not
using Jev at all. This is acceptable **only** because the circuit breaker (§6)
caps how many requests can pay it: after 3 consecutive failures the breaker
opens and subsequent requests skip Jev entirely at zero latency cost. A sustained
Jev outage therefore costs ~3 slow turns, then nothing.

**The tradeoff this timeout makes, and how to validate it.** 1,000 ms is 3.5×
the highest latency observed across the measurement runs (285 ms), which is
comfortable but tighter than the 1,500 ms originally proposed. Two consequences
to watch:

- A genuinely slow-but-valid Jev response between 1,000 and 1,500 ms would be
  discarded and pay for a legacy call it did not need. Cheap (correctness is
  unaffected — the legacy answer is used) but wasteful.
- Repeated latency spikes near the cut-off could trip the breaker on *timeouts*
  rather than real outages, flapping CLOSED → OPEN → CLOSED.

Both are measurable before going live: **shadow mode records real Jev latency
per turn without applying its answers** (§7). The concrete validation step is to
read the observed **p99** from shadow telemetry and confirm it sits well under
1,000 ms before promoting any task from shadow to live. If p99 turns out to
approach the cut-off, raise the timeout rather than accept the flapping — and
note that raising it is a one-env-var change, no deploy.

If that 1.5 s worst case is judged unacceptable for the critical path, the
documented alternative is **hedging**: start the legacy call at `t=400 ms` if
Jev has not answered, and use whichever returns first. That halves worst-case
latency at the cost of sometimes paying for both calls. Recommendation: **do not
hedge initially** — ship sequential-with-breaker, measure real failure rates from
the telemetry in §10, and only add hedging if the observed failure rate makes the
expected cost worth it.

---

## 5. Criticality assignments and batch composition

### Why criticality exists

Fallback granularity is the single most important engineering decision in this
document. Per-question fallback is impossible cheaply (the legacy prompt is
monolithic); all-or-nothing fallback on any hiccup would throw away Jev's savings
whenever one low-stakes tag question came back fuzzy. Criticality splits the
difference along the line that already exists in the code: **does the engine
enforce an invariant on this field?**

| Decision group | Criticality | Justification |
| --- | --- | --- |
| `movement_intent`, `destination_id` | **CRITICAL** | Drives player position. A wrong/missing answer is player-visible and affects scene composition. |
| `departure_certainty_*` | **CRITICAL** | Can schedule a cast replacement. The plan names fabricated departures as a hard gate. |
| `shift_certainty`, `shift_scope`, `shift_subject` | **CRITICAL** | Rewrites a character's goal/disposition into player-visible journal state. |
| `previous_reply_location` | **CRITICAL** | Seeds scene knowledge that later turns read. |
| `spoke_*` (speaker detection) | DEGRADABLE | Today an empty speaker list is normal and handled. |
| `knows_*` (knowledge updates) | DEGRADABLE | Today an empty `knowledge_updates` is the common case. |
| `rel_history_*` | DEGRADABLE | Prompt already says "omit if ambiguous". |
| `attitude_*`, `attitude_strength_*` | DEGRADABLE | Prompt already says "omit the entry if neutral". |
| `behavior_tag_*` | DEGRADABLE | Prompt already says "omit if no clear behavior". |

Every DEGRADABLE assignment above is justified by an **existing** rule in the
current extractor prompt that already permits omission. Nothing becomes newly
optional because of Jev.

### Batch composition

Batches are split by **which state the decisions need**, not by field grouping —
because Jev's docs warn accuracy falls as state grows with unrelated content, and
because latency is flat so splitting costs nothing but a little duplicated state.

| Batch | State contents | Decisions | Measured size |
| --- | --- | --- | --- |
| `current_message` | current user message, scene roster, **reachable** locations, active residents | movement intent, destination, attitude + strength per NPC in scene, player→NPC behavior tags, rel-history gate, departure per active resident | ~16 q, 1,197 in |
| `previous_reply` | previous assistant reply, candidate chunks, roster | previous location, `spoke_*` per cast, `knows_*` per chunk, NPC→X tags for detected speakers | ~25 q, 906 in |
| `ripe_window` *(conditional)* | the one ripe pair's tag window + that character's current goal/disposition | shift certainty / scope / subject / target | ~4 q, 552 in |

`ripe_window` is built only when `_ripe_behavior_pairs()` returns non-empty —
reusing the existing pure heuristic unchanged, so most turns send two batches.

**Reachable-location prefilter (new, and worth it on its own):** the current
extractor ships all 102 six_strangers locations (~1,300 tokens) on every turn.
The world graph already knows which are reachable from the player's position.
Sending only those shrinks the batch and, per the docs, improves accuracy. This
is a strict improvement independent of Jev and could be applied to the legacy
prompt too.

### Fan-out ceiling

Question count scales with scene size, so it needs a hard bound.

- `JEV_MAX_QUESTIONS_PER_BATCH` = **60** (measured fine at 50; 60 leaves headroom).
- On overflow, drop in this order, and **log every drop**:
  1. `behavior_tag_*` for non-speaking actors
  2. `rel_history_*` beyond the first N scene-present pairs
  3. `knows_*` beyond the first 12 chunks (already capped at 12 upstream)
- **Never** drop a CRITICAL decision to fit the cap. If CRITICAL decisions alone
  would exceed the cap, split into an additional batch instead — latency is flat,
  so an extra concurrent batch is nearly free.

---

## 6. Circuit breaker — "each request automatically knows"

The requirement is that a Jev outage is detected automatically and every
subsequent request routes around it without paying a timeout. That is a circuit
breaker over **shared in-process state**, consulted for free.

```python
# backend/app/llm/decisions/health.py

class BreakerState(Enum):
    CLOSED = "closed"        # normal: use Jev
    OPEN = "open"            # Jev presumed down: skip it, zero latency cost
    HALF_OPEN = "half_open"  # cooldown elapsed: let exactly ONE probe through


class JevCircuitBreaker:
    """Per-process. Single uvicorn worker is the documented deployment
    assumption (same one _SESSION_LOCKS already relies on — see
    prompt_engine.py's A12 comment). If the service ever scales to multiple
    workers, each gets its own breaker: acceptable (each converges
    independently) but it means N workers each pay their own trip cost.
    Noted, not solved here.
    """
    def state(self) -> BreakerState: ...
    def allow_request(self) -> bool: ...        # also performs HALF_OPEN admission
    def record_success(self) -> None: ...
    def record_failure(self, reason: FallbackReason) -> None: ...
    def snapshot(self) -> dict: ...            # for /api/health and telemetry
```

### Parameters

| Setting | Default | Meaning |
| --- | --- | --- |
| `JEV_BREAKER_FAIL_THRESHOLD` | 3 | consecutive failures before opening |
| `JEV_BREAKER_FAIL_WINDOW_S` | 60 | rolling window for the rate trip below |
| `JEV_BREAKER_FAIL_RATE_COUNT` | 5 | failures within the window also opens |
| `JEV_BREAKER_COOLDOWN_S` | 30 | OPEN → HALF_OPEN delay |
| `JEV_BREAKER_COOLDOWN_MAX_S` | 300 | cap on exponential backoff |

### Transitions

```
CLOSED  --3 consecutive failures OR 5 failures/60s-->  OPEN
OPEN    --cooldown elapsed-------------------------->  HALF_OPEN
HALF_OPEN --probe succeeds------------------------->  CLOSED   (counters reset,
                                                                cooldown reset)
HALF_OPEN --probe fails---------------------------->  OPEN     (cooldown doubled,
                                                                capped at 300 s)
```

Only **transport/availability** failures trip the breaker: timeout, connect
error, non-2xx, unparseable body. Answer-quality failures
(`BELOW_THRESHOLD`, `INVALID_OPTION`, `MISSING_ANSWER`) do **not** — Jev is up
and answering; it just gave an answer we chose not to use. Conflating the two
would open the breaker during ordinary threshold tuning.

`allow_request()` is called once per turn and touches only process memory, so a
fully-open breaker adds **zero** latency — that is the property that makes a
sustained outage cost ~3 turns rather than every turn.

### Exposure

`GET /api/health` gains a non-authoritative `jev` block:

```json
"jev": {"enabled": true, "state": "closed", "consecutive_failures": 0,
        "opened_at": null, "cooldown_s": 30, "model": "jev-1.13.0"}
```

Useful for the ship-and-verify step and for confirming a rollback took effect
without reading logs.

---

## 7. Flags and rollout modes

Three independent controls, all read through `credentials.py` / `settings.py`
exactly like every other config value, so Railway env vars override `.env.test`.

| Env var | Type | Default | Meaning |
| --- | --- | --- | --- |
| `TYPESAFE_API_KEY` | secret | — | already implemented (commit `68646ae`) |
| `TYPESAFE_MODEL` | string | `jev-latest` | **pin to `jev-1.13.0` before any threshold tuning** |
| `TYPESAFE_ENABLED` | bool | `false` | already implemented. Global kill switch. False ⇒ byte-identical to today. |
| `JEV_ENABLED_TASKS` | csv | `""` | per-task allowlist. `""` = none, `*` = all. |
| `JEV_SHADOW_TASKS` | csv | `""` | run Jev, log it, **use legacy**. |
| `JEV_SHADOW_SAMPLE_RATE` | float | `0.0` | 0.0–1.0 fraction of turns shadowed (shadow costs both calls). |
| `JEV_TIMEOUT_MS` | int | `1000` | §4. Validate against shadow-mode p99 before going live. |
| `JEV_MAX_QUESTIONS_PER_BATCH` | int | `60` | §5 |

Task ids (the `Decision.task` values), matching the redesign doc's abilities:
`movement`, `prev_scene`, `knowledge`, `rel_history`, `rel_state`, `departure`,
`behavior_tags`, `social_shift`.

### Three modes, and the precedence rule

```
TYPESAFE_ENABLED = false      -> OFF.     No Jev call ever. Today's behaviour.
task in JEV_SHADOW_TASKS      -> SHADOW.  Both run; legacy is used; both logged.
task in JEV_ENABLED_TASKS     -> LIVE.    Jev used, legacy on fallback.
neither                       -> OFF for that task.
```

Precedence: `TYPESAFE_ENABLED=false` beats everything. `JEV_SHADOW_TASKS` beats
`JEV_ENABLED_TASKS` for the same task — if a task is listed in both, it shadows.
This makes "promote a task from shadow to live" a single removal, and makes an
accidental double-listing fail *safe* rather than live.

### Rollback

Rollback is one env var: `TYPESAFE_ENABLED=false`, or removing a task id from
`JEV_ENABLED_TASKS`. No deploy, no code change, no data migration — nothing Jev
writes is stored in a Jev-specific shape. That is the plan's "one-step rollback
works" gate, satisfied by construction.

---

## 8. Provider clients

```python
# backend/app/llm/providers/jev.py

class JevClient:
    """Raw transport. No flags, no breaker, no fallback — policy lives in the
    resolver. Uses the lifespan-managed shared httpx.AsyncClient (Phase 3's
    persistent-client item), not a per-call client."""

    async def ask(self, batch: DecisionBatch, *, timeout_ms: int) -> JevRawResult:
        """POST /v1/systemone. Raises JevTransportError on
        timeout/connect/non-2xx/unparseable. Returns the parsed
        answers + usage + resolved model id on success."""
```

Request body, exactly as verified against the live API:

```json
{
  "model": "<TYPESAFE_MODEL>",
  "state": "<batch.state>",
  "questions": {
    "<decision.id>": {
      "type": "choice" | "score" | "noul",
      "instructions": "<decision.instructions>",
      "criteria": { "<option_id>": "<description>" }
    }
  }
}
```

`criteria` is a **map** for `choice` (option id → description) and for `noul`
(`true`/`false` → description), and an **array** of level descriptions for
`score`. Answers return under the same question ids. `usage` is reported once
for the whole request.

The resolved model id from every response (`"model": "jev-1.13.0"`) must be
logged — the plan requires knowing which version answered, and `jev-latest` is a
moving alias.

---

## 9. Decision registry — concrete definitions

`backend/app/engine/extractors/decision_registry.py`. Pure data, no I/O.
Ability numbers refer to the redesign doc's chart.

| Decision id | Task | Kind | Criticality | Criteria / options | Validation |
| --- | --- | --- | --- | --- | --- |
| `movement_intent` | movement | choice | CRITICAL | `MOVE`, `NONE` | must be in allowed |
| `movement_destination` | movement | choice | CRITICAL | reachable location ids + `none_of_these` | `none_of_these` ⇒ intent coerced NONE; id re-validated against world graph |
| `prev_scene_location` | prev_scene | choice | CRITICAL | all location ids + `none_of_these` | re-validated |
| `spoke_<char_key>` | prev_scene | noul | DEGRADABLE | true: "has ≥1 line of spoken dialogue"; false: "does not speak" | `true_threshold` (start 0.5, tune) |
| `knows_<chunk_id>` | knowledge | noul | DEGRADABLE | true: "dialogue explicitly states/confirms this fact"; false: "not addressed" | chunk id must be one we supplied |
| `rel_history_gate` | rel_history | noul | DEGRADABLE | true: "this turn reveals something about a past/current romance between two characters" | gate: false ⇒ **skip all pair fan-out** |
| `rel_hist_<a>_<b>_prior` | rel_history | noul | DEGRADABLE | explicit past romance between these two | both ids in cast |
| `rel_hist_<a>_<b>_intimacy` | rel_history | noul | DEGRADABLE | explicit past sexual intimacy | both ids in cast |
| `rel_hist_<a>_<b>_current` | rel_history | noul | DEGRADABLE | explicitly together *now* | both ids in cast |
| `attitude_<npc>` | rel_state | choice | DEGRADABLE | `none`, `trust`, `distrust`, `warmth`, `coldness`, `fear`, `suspicion`, `jealousy` | `none` ⇒ no delta |
| `attitude_strength_<npc>` | rel_state | score | DEGRADABLE | 3 levels: none / mild / strong | **code** maps (attitude, level) → delta band |
| `departure_<resident>` | departure | choice | CRITICAL | `NONE`, `WISH`, `DECISION` | resident must be in `active_ids()` |
| `behavior_tag_<from>_<to>` | behavior_tags | choice | DEGRADABLE | story-authored vocabulary + `none` | must be in the story's vocabulary |
| `shift_certainty` | social_shift | choice | CRITICAL | `NONE`, `WISH`, `SHIFT` | `min_confidence` — see note |
| `shift_scope` | social_shift | choice | CRITICAL | `goal`, `disposition`, `neither` | — |
| `shift_subject` | social_shift | choice | CRITICAL | ripe-pair character ids | must be in cast |
| `shift_target` | social_shift | choice | CRITICAL | ripe-pair character ids + `none` | required when scope=disposition |

**Threshold note, from measurement:** 20 of the 21 verified questions returned
confidence ≈1.0. The single exception was `shift_certainty` at **0.73** on a
genuinely ambiguous window. Set `min_confidence` **per decision**, not globally —
a global threshold tuned for `shift_certainty` would be far too loose for
`movement_intent`, and one tuned for `movement_intent` would reject every real
shift. Initial values are guesses until the labeled dataset exists (§13).

### Two invariants that are code's job, not Jev's

1. **Delta arithmetic.** `attitude_*` + `attitude_strength_*` give a category and
   a level. Python maps that pair to a dimension and a delta inside the existing
   `REL_TRAIT_DELTA_MIN/MAX` band, and still clamps. Jev is never asked for a
   number — this respects its documented arithmetic weakness.
2. **Every existing validation in `_parse_json` is retained**, re-pointed at
   decision answers instead of JSON fields: unknown location ⇒ intent NONE;
   `from_id` must be `"player"` for relationship state; departure only for
   active residents; `SHIFT` without `new_value` coerced to NONE; disposition
   shift requires an already-established edge. Jev choosing something does not
   make it legal.

---

## 10. Observability

Extends the Phase 0B ledger rather than adding a parallel system.

**Per-turn, one new JSONL line `kind: "decision_resolution"`:**

```json
{"kind":"decision_resolution","req_id":"…","session_id":"…","turn":7,
 "provider_used":"jev","jev_model":"jev-1.13.0",
 "batches":[{"name":"current_message","questions":16,"latency_ms":214,
             "usage":{"input_tokens":1197,"output_tokens":282}}],
 "jev_latency_ms":227,"legacy_latency_ms":null,
 "fallback_reasons":{},
 "breaker_state":"closed",
 "degraded_decisions":[],
 "dropped_for_cap":[]}
```

**Also required:**
- Add an `extraction` stage to `stage_timer` (the §1 action item) so
  extraction latency appears in `turn_stage_ledger` alongside retrieval /
  storyteller / commit.
- Extend `UsageLedger` to attribute tokens per provider, so "cost per
  successfully committed turn" (the plan's Phase 0B metric) splits into
  storyteller / Jev / legacy-extraction / memory.
- Log every breaker transition at INFO with the reason.
- Log every shadow disagreement with both values — this is the raw material for
  the parity gate (TC-20).

---

## 11. Test plan

Ability-level correctness tests are TC-01…TC-20 in the redesign doc. This
section covers the **provider machinery**, which those cases do not touch. All
use a fake `JevClient` — no network.

### Resolver

| Test | Assertion |
| --- | --- |
| `test_all_tasks_disabled_never_calls_jev` | `TYPESAFE_ENABLED=false` ⇒ fake Jev records zero calls; result byte-identical to legacy-only |
| `test_jev_success_uses_jev_answers` | all usable ⇒ `provider_used == JEV`, legacy never called |
| `test_critical_failure_falls_back_wholesale` | one CRITICAL answer invalid ⇒ legacy called exactly once, **all** fields from legacy, Jev answers discarded |
| `test_degradable_failure_keeps_jev_and_defaults` | one DEGRADABLE answer invalid ⇒ legacy **not** called; that field at dataclass default; others from Jev |
| `test_none_option_is_usable_not_failure` | `none_of_these` ⇒ `usable is True`, no fallback, intent coerced NONE |
| `test_missing_question_id_is_failure` | id absent from answers ⇒ `MISSING_ANSWER` |
| `test_invalid_choice_is_failure` | choice outside `allowed` ⇒ `INVALID_OPTION` |
| `test_below_min_confidence_is_failure` | confidence under threshold ⇒ `BELOW_THRESHOLD` |
| `test_noul_low_probability_is_false_not_failure` | p=0.02 ⇒ usable answer meaning False |
| `test_batches_run_concurrently` | two batches with 100 ms fake delay each complete in <150 ms |
| `test_resolver_never_raises` | fake Jev raising arbitrary exceptions ⇒ always a usable outcome |

### Circuit breaker

| Test | Assertion |
| --- | --- |
| `test_opens_after_consecutive_failures` | 3 transport failures ⇒ OPEN |
| `test_open_breaker_skips_jev_with_no_latency` | OPEN ⇒ zero Jev calls, `CIRCUIT_OPEN` recorded, no timeout paid |
| `test_half_open_admits_one_probe` | after cooldown, exactly one request reaches Jev |
| `test_half_open_success_closes_and_resets` | probe succeeds ⇒ CLOSED, counters and cooldown reset |
| `test_half_open_failure_reopens_with_backoff` | probe fails ⇒ OPEN, cooldown doubled, capped at max |
| `test_quality_failures_do_not_trip_breaker` | 10 × `BELOW_THRESHOLD` ⇒ still CLOSED |
| `test_breaker_state_in_health_endpoint` | `/api/health` reflects the current state |

### Flags

| Test | Assertion |
| --- | --- |
| `test_per_task_allowlist` | only listed tasks route to Jev; others legacy |
| `test_shadow_uses_legacy_answer` | shadowed task ⇒ game state matches legacy exactly, Jev answer only in `shadow_disagreements` |
| `test_shadow_beats_enabled_when_both_listed` | task in both lists ⇒ shadow (fail safe) |
| `test_shadow_sample_rate_zero_never_shadows` | rate 0.0 ⇒ Jev never called for shadow |
| `test_global_kill_switch_overrides_task_flags` | `TYPESAFE_ENABLED=false` + `JEV_ENABLED_TASKS=*` ⇒ no Jev |

### Fan-out cap

| Test | Assertion |
| --- | --- |
| `test_cap_drops_degradable_first` | overflow ⇒ behavior tags dropped before knowledge |
| `test_cap_never_drops_critical` | CRITICAL-only overflow ⇒ extra batch created, nothing dropped |
| `test_drops_are_logged` | every dropped decision id appears in `dropped_for_cap` |

### Equivalence — the adoption gate

| Test | Assertion |
| --- | --- |
| `test_turn_extraction_schema_unchanged_except_planned` | `TurnExtraction` fields == today's minus `destination_text`; every other name/type identical |
| `test_existing_apply_pipeline_tests_unmodified` | the **30** existing extraction-related tests in `test_prompt_engine.py` (counted 2026-09-22) pass **unmodified** with the resolver injected and Jev disabled. This is step 3's acceptance criterion: if any needs editing, the seam changed behaviour and is wrong. |
| `test_parity_on_replay_set` | on a fixed replay set, Jev and legacy agree on all CRITICAL decisions; disagreements are listed individually, not averaged |

---

## 12. Implementation order

Each step is independently shippable and independently revertible. Steps 1–3
contain **no** Jev call at all, so they are safe to ship before any pilot.

| Step | Deliverable | Ships behind | Status |
| --- | --- | --- | --- |
| **1** | `extraction` stage added to `stage_timer`; extractor latency visible in production | nothing — pure observability | ✅ Shipped `da0ab43`, live-verified on beta |
| **2** | `backend/app/llm/` skeleton: types, `JevClient`, `OpenAIChatClient` (extracted from the existing inline sites), `UsageLedger`. No call sites changed. | nothing — dead code until wired | ✅ Shipped `1bbc10c`, 57 tests, live-verified |
| **3** | `TurnExtractor` refactored into *batch builder → resolver → assembler*, with a resolver whose only provider is the **existing legacy call**. `httpx` import removed from `turn_extractor.py`; the missing import-direction test added (with the documented allowlist from §2). **Behaviour byte-identical; all existing tests must pass unmodified.** | nothing — this is the seam, no Jev | ✅ Shipped 2026-09-22. All 30 pre-existing extraction tests in `test_prompt_engine.py` and all 27 in `test_turn_extractor.py` pass **unmodified**. |
| **4** | `JevCircuitBreaker` + flags + telemetry. Still no task enabled. | `TYPESAFE_ENABLED=false` | ✅ Shipped 2026-09-22. `/api/health` gains the `jev` block from §6. |
| **5** | Register + enable abilities **1, 2, 5** (`movement`, `prev_scene`) — pure `choice`, no fan-out, no vocabulary, no arithmetic. | `JEV_SHADOW_TASKS=movement,prev_scene` first, then `JEV_ENABLED_TASKS` | ✅ Shipped 2026-09-22 — **default OFF** (`TYPESAFE_ENABLED=false`), verified end-to-end against the **live Jev API** in both shadow and live mode (see below). **Correction: the reachable-location prefilter was NOT landed** — `TurnExtractor.extract()`'s existing signature has no current-location/world-graph access, and adding it would have meant a signature change beyond this step's "behaviour byte-identical" scope. `movement_destination` uses the full location list, documented as a known limitation in `decision_registry.py`. |
| **6** | Fan-outs: `knowledge`, `departure` (abilities 7, 10) | shadow → live, per task | Not started |
| **7** | `rel_state` (ability 9, level→delta mapping) and `rel_history` (ability 8, gated fan-out) | shadow → live | Not started |
| **8** | `behavior_tags` (ability 11). **Requires BL-16's story-authored vocabulary first.** | shadow → live | Not started |
| **9** | `social_shift` (ability 12) + the conditional generative `new_value` call | shadow → live | Not started |

**Step 5's real caveat, stated plainly:** with only abilities 1/2/5 registered,
the legacy call still runs on **every** turn regardless of Jev's outcome — 9 of
12 `TurnExtraction` fields have no Decision registered yet, so `extract()`
explicitly calls `legacy_request.invoke()` whenever the resolver didn't already
need it (see `turn_extractor.py`'s `extract()` method and its inline comment).
This means **enabling `movement`/`prev_scene` live today does not yet reduce
cost** — it only lets Jev's answer override the legacy one. This is exactly the
"hybrid trap" `JEV_EXTRACTOR_REDESIGN_2026_09_22.md` warns against, and is
unavoidable until either more abilities are registered (steps 6–9) or the legacy
prompt itself is shrunk to stop asking for what Jev already answers — the
latter is deliberately not done in this pass. `TYPESAFE_ENABLED=false` (shipped
default) means none of this is live in production regardless.

**Live-API verification performed while building step 5** (not committed as
tests — no network in CI, but real evidence this integration works, not just
mocks):
- Shadow mode: a real Jev call for "I'm heading to the terrace right now to
  cool off" correctly answered `MOVE`/`terrace`; `shadow_disagreements` recorded
  `('MOVE', 'NONE')` against a deliberately-wrong fake legacy answer, and the
  final `TurnExtraction` correctly used the legacy value, never the shadow one.
- Live mode: the same real Jev call's answer was correctly **applied**
  (`provider_used=JEV`, legacy never called), overriding what the fake legacy
  answer would have said.

Out of scope here, tracked separately: the **offline grader** pilot and the
**memory-extraction gate** (both in the redesign doc's Table B). Both are better
first pilots than any of step 5–9 because neither touches the live turn path —
but both reuse the `llm/` package from step 2, so this ordering does not block
them.

---

## 13. What still blocks going live

1. **Labeled dataset (unchanged).** Every `min_confidence` and `true_threshold`
   in §9 is currently a guess. The plan's gate 1 wants ≥1,000 labeled cases
   across both stories, including negation, sarcasm, multi-speaker attribution,
   offscreen references, and CJK. 21 hand-built passing cases are encouraging;
   they are not a recall measurement. **Steps 1–4 do not need it. Step 5 onward
   needs it before going live (shadow mode does not).**
2. **CJK untested.** Every verified case is English. TypeSafe documents English
   as strongest and says CJK needs separate evaluation — and this game has a
   Japanese language theme with honorific handling.
3. **BL-16** must land before step 8 (behavior tags need the closed vocabulary).
4. **Production extractor latency unmeasured** — step 1 fixes this, and it should
   land before anyone quotes the 17× ratio as a production number.

## 14. Decisions deliberately deferred

Recorded so they are not silently re-litigated:

- **Hedging** (start legacy at 400 ms rather than waiting out the Jev timeout).
  Deferred until telemetry shows the real failure rate. §4.
- **Cross-process breaker state.** Single-worker deployment makes per-process
  state correct today; noted in §6 if that changes.
- **Per-question retry.** Rejected: the breaker is the retry mechanism. §4.
- **Partial legacy prompt** (asking the legacy model for only the fields Jev
  failed). Rejected: a second prompt variant to maintain forever, for a rare
  path. §4 step 6.
- **Jev for the memory-extraction gate.** In scope for the project, out of scope
  for this document — it is a new decision, not a `TurnExtractor` ability.
