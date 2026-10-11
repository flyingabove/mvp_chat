# Roadmap: designed but not built

> This file merges several design documents (each keeps its own section, with its original status notes). Open work is in [../backlog/](../backlog/).

## Phase 2 — reusable backend: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md (removed; see git history)` Phase 2, matching the
detail level of the Jev design docs.

**Status: design only. Nothing here is implemented.**

Phase 2 is the plan's own stated prerequisite for Phase 4
(`Phase 2 DecisionProvider → Phase 4 Jev` in the sequencing diagram). The Jev
provider architecture (`design/JEV.md (provider architecture)`) was designed
first and describes a compatible seam, but this document is the one that must
actually exist and be stable before Jev's `resolve()` has anywhere real to plug
into beyond `TurnExtractor` alone.

---

### 1. What exists today, verified

#### 1.1 New-game and restore duplicate construction, by design comment admission

`_chat_handler_impl`'s `__cmd_newgame__` branch (`prompt_engine.py:2290`) and
`_try_load_session_from_db` (`prompt_engine.py:1505`) both: call `load_story`,
call `init_state()`, set `story`/`gender`/`player_name`/`instance`, load the
world runtime via `WorldLoader`, and rebuild the character roster from
`StoryDefinition`. The restore path's own docstring says it directly:
*"Rebuild full GameState from saved primitives (mirrors `__cmd_newgame__`
setup)."* Two independent code paths, hand-synchronized by comment, is exactly
the duplication `SessionFactory` exists to remove.

#### 1.2 `StoryDefinition` already exists but is not "validated immutable content"

`backend/app/engine/story_loader.py:34` defines `StoryDefinition` as a
dataclass with `id`, `raw`, `title`, `theme`, `instance`, `characters`,
`relationships`. It has a `from_dict` constructor. It has **no validation** —
malformed story JSON produces a `StoryDefinition` with empty/default fields
silently, not a rejection. `build_story_registry()` reparses on every lookup
(confirmed in the earlier engineering-plan measurement: 2.13ms p50 — cheap, and
deliberately not cached per `story_loader.py:180`'s own comment that draft
stories must appear immediately).

#### 1.3 `TurnExtractor` already has the shape `DecisionProvider` needs

The Jev design (steps 2–3 of its own implementation order) already specifies
extracting `TurnExtractor`'s HTTP call into `backend/app/llm/providers/`. Phase
2's job is to make that extraction *load-bearing* — i.e. `TurnExtractor` is the
first and, for now, only consumer of the `DecisionProvider` pattern, not a
one-off.

#### 1.4 The journal projection now has a shared policy; the roster does not fully share it

Phase 1.4 (shipped) added `player_visible_character_ids()` and
`player_visible_arrival_minute()` to `prompt_engine.py`, and the journal
endpoint uses them. `_cast_roster_payload()` (`prompt_engine.py:468`)
implements an **equivalent but separately-coded** policy (its own
`active_ids()` + `DEPARTED` walk) with a richer active/vacancy/departed shape.
`PlayerView` in this design is the single source of truth both should read from
— not a third implementation.

#### 1.5 The 1,256-line handler's actual sections, measured

```
backend/app/api/prompt_engine.py:1913  chat_handler()          (thin lock wrapper)
backend/app/api/prompt_engine.py:1931  _chat_handler_impl()    starts
  ~2000-2050   dedup / BL-02 replay check
  ~2050-2290   command dispatch (RESET, [CAST], [T], [ES], [SKIP], map, etc.)
  2290-2470    __cmd_newgame__ construction               <- SessionFactory
  2470-2660    session/state reinit-on-missing fallback   <- SessionFactory
  2660-2760    retrieval + extraction                     <- DecisionProvider
  2760-3090    apply pipeline (movement, relationships,
               departures, shifts, cast lifecycle)         <- stays in engine
  3090-3210    storyteller call + decode                   <- TextProvider
  3210-3260    commit (Phase 1.1 clone-and-publish)        <- TurnService
  3260-3310    background extraction enqueue               <- TurnService
```

This is the decomposition order the original plan named ("command dispatch →
session load/restore → retrieval assembly → prompt composition → provider call
→ commit → background enqueue"), now mapped to concrete line ranges rather than
stated abstractly.

---

### 2. Package layout

```
backend/app/
  application/                    NEW
    __init__.py
    session_factory.py            SessionFactory
    snapshot_codec.py             SnapshotCodec
    turn_service.py                TurnService
    player_view.py                 PlayerView
    commands.py                    the command dispatch table (§7)

  engine/
    story_loader.py                StoryDefinition gains .validate() (§4)
    extractors/
      turn_extractor.py            unchanged signature; internals already
                                    being reshaped by the Jev design's steps 2-3

  llm/                             from the Jev design; DecisionProvider /
                                    TextProvider protocols live here (§5)

  api/
    prompt_engine.py                shrinks: chat_handler() calls
                                     application.turn_service, application.commands
```

`application/` sits between `api/` (HTTP) and `engine/` (pure state). Dependency
direction, matching the plan's constraint: `api` → `application` → `engine`,
`application` → `llm` (for `DecisionProvider`/`TextProvider`), `engine` never
imports `application`, `llm`, `api`, `db`, or `httpx`.

---

### 3. `SessionFactory` + `SnapshotCodec`

#### 3.1 Contract

```python
# backend/app/application/session_factory.py

@dataclass(frozen=True)
class NewGameRequest:
    story_id: str
    gender: str                      # "M" | "F"
    player_name: str
    user_id: str                     # already resolved: real uid or DEFAULT_USER_ID
    persona_mode: str = "temp"
    persona_name: str = ""
    persona_other: str = ""

@dataclass(frozen=True)
class SessionInitResult:
    state: GameState
    log: list[dict]
    warnings: tuple[str, ...] = ()   # e.g. "world file missing, no travel available"

class SessionFactory:
    """The ONE path that turns story content + player choices into a GameState.
    Both __cmd_newgame__ and DB restore call this — restore additionally
    replays a snapshot on top (see SnapshotCodec below)."""

    def new_game(self, request: NewGameRequest) -> SessionInitResult:
        """Raises StoryNotFoundError if request.story_id doesn't resolve.
        Never raises for a malformed-but-loadable story — degrades via
        `warnings`, matching today's tolerant behavior (e.g. missing world
        file -> no world_runtime, not a crash)."""

    def restore(self, snapshot: "Snapshot", user_id: str) -> SessionInitResult:
        """Rebuilds via new_game() using the snapshot's story_id/gender/
        player_name, THEN applies the snapshot's diverged fields (minute,
        location_id, turns, character_graph, cast_lifecycle, ...) via
        SnapshotCodec.apply(). This is what makes the "mirrors __cmd_newgame__
        setup" comment obsolete — it no longer mirrors, it CALLS it."""
```

#### 3.2 `SnapshotCodec`

```python
# backend/app/application/snapshot_codec.py

SNAPSHOT_VERSION = 1   # bump on any incompatible field change

@dataclass(frozen=True)
class Snapshot:
    version: int
    story_id: str
    gender: str
    player_name: str
    instance: int
    fields: dict[str, Any]        # everything _serialize_state already
                                    # captures today: minute, location_id,
                                    # turns, over, character_graph, cast_lifecycle,
                                    # recent_behavior_log, session_chunk_store, ...

class SnapshotCodec:
    def encode(self, state: GameState) -> Snapshot:
        """Successor to _serialize_state (prompt_engine.py:1459). Same field
        set; wrapped in a versioned envelope instead of a bare dict."""

    def decode(self, raw_json: str) -> Snapshot:
        """Raises SnapshotDecodeError on unparseable JSON (today: silent
        None return -> 'session expired' to the player). Raises
        SnapshotVersionError if version > SNAPSHOT_VERSION (a newer process
        wrote it; this process must not guess at unknown fields)."""

    def migrate(self, snapshot: Snapshot) -> Snapshot:
        """Version N -> SNAPSHOT_VERSION, N < SNAPSHOT_VERSION. One migration
        function per version step, composed. Empty today (only version 1
        exists) — this method exists so migration is a place to add code to,
        not a redesign later."""

    def apply(self, state: GameState, snapshot: Snapshot) -> None:
        """Mutates `state` in place with snapshot.fields. Successor to the
        ~80-line inline restoration block in _try_load_session_from_db."""
```

#### 3.3 The hard requirement: tested restoration of EXISTING saved games

The plan's exit criterion is explicit: *"Tested restoration of existing saved
games is the hard requirement."* Concretely: `SNAPSHOT_VERSION = 1` must decode
every `state_json` blob currently sitting in the production `game_sessions`
table, produced by the *pre-refactor* `_serialize_state`. This is verified by:

- **TC-SF-01:** Take 10 real anonymized `state_json` values from a beta DB
  snapshot (or, if unavailable, 10 synthetically constructed ones matching
  today's exact `_serialize_state` output shape). Decode each through the new
  `SnapshotCodec.decode`. Assert no exception and every field present in the
  old blob is present in the decoded `Snapshot.fields`.
- **TC-SF-02:** Round-trip: `encode(decode(old_blob).apply_to_fresh_state())`
  produces a blob `json.loads`-equal to the original modulo key ordering.
- **TC-SF-03:** A `state_json` with `version` key absent (every blob written
  before this migration) is treated as version 1 implicitly — `decode` must
  default missing `version` to 1, not raise.

#### 3.4 Test plan

| Test | Assertion |
| --- | --- |
| `test_new_game_and_restore_produce_equivalent_state` | Build via `new_game()`, immediately `encode()` → `decode()` → `restore()`; resulting `GameState` matches the original on every field `_serialize_state` currently captures |
| `test_new_game_missing_story_raises` | unknown `story_id` → `StoryNotFoundError`, not a bare `None` |
| `test_new_game_missing_world_file_degrades_not_crashes` | matches today's tolerant behavior, `warnings` non-empty |
| `test_restore_unknown_snapshot_version_raises` | `SnapshotVersionError`, never silently truncates |
| `test_restore_missing_version_key_defaults_to_1` | TC-SF-03 |
| `test_snapshot_round_trip_is_lossless` | TC-SF-02 |
| `test_ten_real_saved_blobs_decode` | TC-SF-01 |
| `test_player_persona_construction_matches_today` | the `make_player_character` / persona_mode branch (`prompt_engine.py:2370-2404`) produces the same `Character` node |

---

### 4. `StoryDefinition` validation

The plan calls for "validated immutable content." Concretely, `.validate()`
added to the existing class, called once by `SessionFactory.new_game()` (not by
the registry — registry parsing stays fast and permissive per §1.2's confirmed
2.13ms measurement; validation is a gate at *use* time, not *list* time):

```python
@dataclass(frozen=True)
class StoryDefinition:
    # ...existing fields, unchanged...

    def validate(self) -> tuple[str, ...]:
        """Returns a tuple of error strings; empty tuple = valid.
        Does not raise — callers decide whether to reject or degrade.
        Checks:
          - id non-empty
          - at least one character, exactly one is_main
          - cast_lifecycle (if present): slot_capacities sum matches
            character count assigned to slot_groups; player_bedrooms values
            exist in the world's locations (needs world_cfg cross-check,
            done by SessionFactory after both are loaded, not here)
          - world.file (if present) resolves to an existing file
        """
```

`SessionFactory.new_game()` calls `story_def.validate()`; a non-empty result
becomes `SessionInitResult.warnings` (today's tolerant behavior — a broken
story shouldn't 500 the endpoint) unless the error is `id non-empty` or `no
characters`, which raise `StoryNotFoundError`-equivalent (nothing playable
exists).

**Six-resident rule stays deterministic code**, per the plan: `validate()`
checks the *shape* (capacities sum, bedrooms resolve) but the actual
displacement logic remains `CastLifecycleState.reserve_player_slot()`
(Phase 1 shipped, tested, live-verified with the six_strangers fix). Not
touched by this design.

---

### 5. `DecisionProvider` / `TextProvider`

These protocols are defined **once**, in `backend/app/llm/`, shared by the Jev
design and by Phase 2's restructuring — this is the literal seam the plan's
sequencing diagram names.

```python
# backend/app/llm/protocols.py

class DecisionProvider(Protocol):
    """Resolves bounded decisions. Jev's DecisionResolver (see
    design/JEV.md (provider architecture) §4) IS a DecisionProvider — this
    protocol is what makes it swappable/mockable without TurnExtractor
    knowing Jev exists."""
    async def resolve(
        self, batches: Sequence[DecisionBatch], legacy_request: LegacyExtractionRequest,
    ) -> DecisionOutcome: ...

class TextProvider(Protocol):
    """Generates prose. The storyteller call and the Chinese translation
    call both become TextProvider implementations — same interface, so
    Phase 3's 'lifespan-managed HTTP clients' item (persistent clients) is
    implemented ONCE here, not per call site."""
    async def generate(
        self, *, model: str, system: str, messages: list[dict], max_tokens: int, temperature: float,
    ) -> TextResult: ...
```

**Before this refactor:** `TurnExtractor` (movement/etc.) and the storyteller
call and the Chinese translator each build their own `httpx.AsyncClient`,
hardcode their own URL, and have no shared contract. **After:** all three are
`TextProvider` or `DecisionProvider` implementations constructed once at
lifespan (Phase 3 dependency, noted, not built here) and injected. This is not
new scope invented for this document — it is the plan's own Phase 3 "Task-
specific model configuration" and "Lifespan-managed HTTP clients" items, now
given the concrete interface they were missing.

`TurnExtraction` stays a validated internal result — the protocol returns
`DecisionOutcome`/`TextResult`, and `TurnExtractor`'s existing assembler (from
the Jev design) converts that into `TurnExtraction`. No provider wire format
(Jev's `choice`/`score`/`noul`, or OpenAI's `chat/completions` JSON) ever
reaches `prompt_engine.py` or the apply pipeline.

---

### 6. `PlayerView`

#### 6.1 Unifying the roster and journal policies

```python
# backend/app/application/player_view.py

@dataclass(frozen=True)
class PlayerVisibleCharacter:
    id: str
    name: str
    role: str
    status: Literal["active", "departed", "player"]

@dataclass(frozen=True)
class PlayerView:
    """The ONE object both the roster and journal render from. Constructed
    once per request from GameState; both existing endpoints become thin
    formatters over this, instead of two separately-coded policies."""
    visible_characters: tuple[PlayerVisibleCharacter, ...]
    vacancies: tuple[dict, ...]              # {"group": str, "label": str} per open slot
    arrival_minute: Mapping[str, int]         # char_id -> activated_minute (Phase 1.4's function)

    @classmethod
    def build(cls, state: GameState) -> "PlayerView":
        """Successor to player_visible_character_ids() +
        player_visible_arrival_minute() (Phase 1.4, prompt_engine.py) AND
        _cast_roster_payload()'s active/departed walk. Both existing
        functions' logic is ABSORBED here, not duplicated a third time."""
```

`_cast_roster_payload()` becomes: `PlayerView.build(state)` → format into the
existing `{"title", "labels", "active", "vacancies", "departed"}` response
shape. `get_journal()` becomes: `PlayerView.build(state)` → filter
`goal.history`/`disposition.history` entries by `visible_characters` and
`arrival_minute`, exactly as Phase 1.4 already does, just reading from one
object instead of calling two module-level functions.

**Compatibility guarantee:** both endpoints' JSON response shapes are
byte-identical before and after. This is a pure internal consolidation.

#### 6.2 Test plan

| Test | Assertion |
| --- | --- |
| `test_roster_and_journal_agree_on_visible_characters` | for the same `GameState`, the roster's active+departed ids and the journal's visible ids are the same set — this is the ACTUAL bug class Phase 1.4 fixed for the journal alone; this test guards the roster from regressing the same way independently |
| `test_playerview_build_matches_existing_roster_endpoint_output` | characterization test: real six_strangers session, `_cast_roster_payload(state)` output == `PlayerView.build(state)` formatted the same way |
| `test_playerview_build_matches_existing_journal_endpoint_output` | same, against Phase 1.4's journal tests in `test_user_sessions.py` |
| all four Phase 1.4 regression tests (`test_journal_hides_upcoming_character_goal_history`, etc.) | re-run unmodified against the new `PlayerView` path — must still pass |

---

### 7. `TurnService` and command dispatch

#### 7.1 `TurnService` formalizes Phase 1.1

Phase 1.1 (shipped) already implements the clone-and-publish mechanism inline
in `_chat_handler_impl`. `TurnService` is that mechanism given a name and a
boundary, not new behavior:

```python
# backend/app/application/turn_service.py

@dataclass(frozen=True)
class TurnRequest:
    session_id: str
    user_id: str
    request_id: str
    message: str

@dataclass(frozen=True)
class TurnResult:
    reply: dict                       # today's exact chat response shape
    committed: bool                   # False on validation/provider/persistence failure
    failure_kind: Literal["none", "validation", "provider", "persistence"] = "none"

class TurnService:
    def __init__(self, decision_provider: DecisionProvider, text_provider: TextProvider,
                 session_factory: SessionFactory, ...): ...

    async def run_turn(self, request: TurnRequest, sess: dict) -> TurnResult:
        """Extracts Phase 1.1's clone -> mutate -> publish-on-success body
        (prompt_engine.py's `working_state = copy.deepcopy(state)` through
        the `sess["state"] = state` publish line) into one method.
        `failure_kind` distinguishes what the plan's Phase 2 exit criterion
        asks for: validation (bad input) vs provider (Jev/storyteller down)
        vs persistence (DB write failed after a successful turn) — today
        these are three different `return {"error": ...}` shapes with no
        common discriminator."""
```

**This does not re-implement Phase 1.1's correctness guarantee — it relocates
already-shipped, already-tested code.** The acceptance test is that every one
of Phase 1.1's 5 shipped tests
(`test_failed_storyteller_call_does_not_mutate_live_session`,
`test_successful_turn_publishes_a_new_state_object_and_advances_turns`, etc.)
passes unmodified against `TurnService.run_turn` instead of
`_chat_handler_impl` directly.

#### 7.2 Command dispatch

The ~240-line `if msg.startswith(...)` / `_is_X(msg)` chain
(`prompt_engine.py:~2050-2290`, and the toggle/roster/map blocks scattered
through the function) becomes a table:

```python
# backend/app/application/commands.py

@dataclass(frozen=True)
class Command:
    matches: Callable[[str], bool]
    handle: Callable[[GameState, dict, str], dict]   # (state, session_dict, msg) -> response

COMMAND_TABLE: tuple[Command, ...] = (
    Command(matches=lambda m: m == "__cmd_reset__", handle=_handle_reset),
    Command(matches=_is_cast_roster_request, handle=_handle_cast_roster),
    Command(matches=_is_truth_toggle, handle=_handle_truth_toggle),
    Command(matches=_is_epistemic_toggle, handle=_handle_epistemic_toggle),
    Command(matches=lambda m: m.startswith("__cmd_newgame__:"), handle=_handle_newgame),
    Command(matches=lambda m: m.startswith("__cmd_skip__:"), handle=_handle_time_skip),
    # ... one row per existing branch, moved verbatim, not rewritten
)

def dispatch(msg: str, state: GameState, sess: dict) -> dict | None:
    """Returns a response dict if a command matched, else None (falls
    through to the normal turn pipeline). Preserves EXACT existing match
    order — several of today's `_is_X` checks are order-sensitive (e.g. the
    map command must be checked before the general roster check)."""
    for cmd in COMMAND_TABLE:
        if cmd.matches(msg):
            return cmd.handle(state, sess, msg)
    return None
```

Each `_handle_*` function's body is moved, not rewritten — this step is
mechanical extraction, and the test plan proves it with characterization tests
taken *before* the move.

#### 7.3 Test plan

| Test | Assertion |
| --- | --- |
| `test_command_dispatch_order_preserved` | construct a message matching two commands' naive patterns; assert the table returns the SAME one today's if-chain would (regression guard for reordering during extraction) |
| `test_every_existing_command_still_produces_identical_response` | for each of the ~10 existing commands (`[CAST]`, `[T]`, `[ES]`, `__cmd_reset__`, `__cmd_skip__:*`, map, etc.), same input -> byte-identical response dict, before and after extraction |
| `test_turn_service_failure_kind_validation` | retrieval error -> `failure_kind == "validation"` (today: `{"error": "knowledge retrieval failed"}`) |
| `test_turn_service_failure_kind_provider` | storyteller 503 -> `failure_kind == "provider"` |
| `test_turn_service_failure_kind_persistence` | DB write raises after a successful storyteller call -> `failure_kind == "persistence"`, reply still returned to the player (today's behavior: `logger.exception(...)`, turn is NOT lost to the player even though the DB write failed — this nuance must be preserved, not "fixed" into a harder failure) |
| Phase 1.1's 5 existing tests | re-run unmodified against `TurnService.run_turn` |

---

### 8. Migration order (mechanical extraction, one seam at a time)

Each step: write characterization tests against current `_chat_handler_impl`
behavior *before* moving code, move the code, confirm the same tests pass
unmodified.

| Step | Extract | Depends on |
| --- | --- | --- |
| 1 | `PlayerView` (§6) — smallest, already has Phase 1.4 tests to characterize against | nothing |
| 2 | Command dispatch table (§7.2) — mechanical, no logic change | nothing |
| 3 | `SessionFactory` + `SnapshotCodec` (§3) — the highest-value one, removes the duplication in §1.1 | nothing |
| 4 | `DecisionProvider`/`TextProvider` protocols (§5) | Jev design's steps 2-3 (already speced) |
| 5 | `TurnService` (§7.1) — last, because it composes 1-4 | 1, 2, 3, 4 |
| 6 | Import-direction test (already speced in the Jev architecture doc §2) | 4 |

---

### 9. Exit criteria (unchanged from the plan, restated precisely)

- Existing endpoints and saved games behave identically — verified by §3.3's
  ten-real-blob test and §6.2/§7.3's characterization tests, not by inspection.
- Deterministic tests pass for both genres and a full cast rotation — the
  existing six_strangers cast-rotation tests (Phase 1's shipped work) must pass
  unmodified through `TurnService`.
- An import-direction test proves `engine/` imports no API, HTTP, or storage
  module — this closes the gap `design/JEV.md (provider architecture)` §2
  found: the test does not exist yet; it ships in step 6 above.

### 10. What this design deliberately does not do

- Does not touch `frontend/index.html` (Phase 5).
- Does not implement any Jev call — `DecisionProvider` is a protocol; Jev's
  concrete `DecisionResolver` implementing it is the Jev design's own scope.
- Does not change `StoryDefinition`'s six-resident enforcement logic, only adds
  a validation pass around it.
- Does not attempt a `PlayerView` that unifies retrieval-time character
  filtering (the prompt-builder's own scene-eligibility logic,
  `_cast_scene_eligible`) — that is a *prompt composition* concern, not a
  *public response* concern, and conflating them was explicitly warned against
  by keeping "operator views are separate" in the original plan.

---

## Phase 3 — measured optimization: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md (removed; see git history)` Phase 3's 11-row table,
matching the detail level of the Jev design docs.

**Status: design only. Nothing here is implemented.**

The plan's own rule for this phase is the strictest in the whole document:
*"Every item requires Phase 0 before/after evidence. Any item whose
measurement shows a small win is dropped."* This design honors that by
specifying, per item, **the exact measurement to take and the exact threshold
that decides ship vs. drop** — not by assuming every row ships.

---

### 0. Measurement infrastructure this phase depends on

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

### 1. Lifespan-managed HTTP clients

#### Current state, verified
18 construction sites (per the audit; re-confirmed: `httpx.AsyncClient(...)` at
`prompt_engine.py:1166,2920(ish, now inside the extraction stage)`,
`dialogue_extractor.py`, `location_extractor.py` ×2, `turn_extractor.py`,
`knowledge_resolution_extractor.py`, `debug_engine.py` ×6, plus Jev's own
`JevClient` once it's built per the provider architecture design).

#### Design
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

#### Measurement to take before shipping
Run the harness at concurrency 1, 10, 50 (BL-15's deferred full matrix — **this
row is the reason to finally run it**) with and without the registry. Record
p50/p95 `storyteller` stage time and CPU. **Ship threshold:** ≥5% p95
improvement at concurrency ≥10, since TLS+connection setup overhead only shows
up under concurrent load, not at concurrency 1 (where the audit itself notes
the effect is per-call, not compounding).

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_registry_reuses_client_for_same_name` | two `.get("jev", ...)` calls return the same object |
| `test_registry_separate_clients_per_provider` | `.get("jev", ...)` and `.get("storyteller", ...)` are different objects with independently-set timeouts |
| `test_close_all_closes_every_client` | after `close_all()`, each client's `.is_closed` is True |
| `test_lifespan_closes_clients_on_shutdown` | integration: `TestClient` context exit triggers `close_all` (mirrors the existing pattern for `_guest_cleanup_loop`/`_fact_extraction_periodic_sweep_loop` task cancellation on shutdown) |

---

### 2. Task-specific model configuration

#### Current state, verified
`dialogue_extractor.py` (memory extraction) reads
`STORY_MASTER_BASE_URL`/`STORY_MASTER_API_KEY` but the hardcoded `OPENAI_MODEL`
name — so pointing the storyteller at a local Ollama instance (a documented,
supported local-dev mode) makes the memory extractor silently request a model
name Ollama does not have, while using Ollama's URL/key. This is the plan's
"correctness-adjacent" P1, not a performance item — it can produce a request
that 404s or picks an arbitrary Ollama model depending on that server's
behavior.

#### Design
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

#### Measurement
This is correctness, not performance — no before/after threshold. Ship
criterion: a test proving local-mode (Ollama URL) config no longer silently
requests an OpenAI-shaped model for memory extraction.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_memory_extraction_respects_its_own_model_override` | `MEMORY_EXTRACTION_MODEL` env var changes what `dialogue_extractor` requests, independent of `STORY_MASTER_MODEL` |
| `test_startup_warns_on_local_url_with_default_model` | Ollama-shaped `base_url` + unchanged model name → warning logged |
| `test_each_task_config_is_independently_overridable` | changing one `TaskModelConfig` entry does not affect another |

---

### 3. Bounded retrieval executor

#### Current state, verified (Phase 1.3 already fixed the worst of this)
Phase 1.3 (shipped) fixed the *cold-start* blocking (15.9s → warmed
background). What Phase 1.3 did **not** touch: warm retrieval still runs
**synchronously on the event loop** inside the `retrieval` stage. Measured
originally: ~69ms warm, 10 concurrent sessions → ~176ms p50 loop lag. This
row is the *remaining* item — an order of magnitude less urgent than the cold
start Phase 1.3 already shipped, which is exactly why the plan sequences it
after 1.3 and into Phase 3.

#### Design
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

#### Measurement to take before shipping
Harness at concurrency 10 and 50 (again, BL-15's deferred matrix), comparing
event-loop lag (the same probe technique used to measure Phase 1.3's fix) with
retrieval on-loop vs off-loop. **Ship threshold:** measurable p50 loop-lag
reduction at concurrency ≥10 with no p95 retrieval latency regression >20ms
(thread handoff has its own small overhead — the win must exceed it).

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_retrieve_knowledge_async_returns_same_result_as_sync` | same query, same namespace → identical output between `retrieve_knowledge` and `retrieve_knowledge_async` |
| `test_retrieval_does_not_block_event_loop` | same technique as Phase 1.3's `test_startup_warm_up_does_not_block_the_event_loop`: a probe coroutine keeps ticking during a concurrent retrieval call |
| `test_concurrent_retrievals_reuse_the_locked_embedder` | N concurrent `retrieve_knowledge_async` calls trigger exactly one embedder load (Phase 1.3's lock, now exercised across threads) |
| `test_executor_worker_count_is_bounded` | pool size matches `RETRIEVAL_EXECUTOR_WORKERS`, does not grow unbounded |

---

### 4. `SessionChunkStore` ID dedup

#### Current state, verified (already reclassified as correctness in the plan)
Measured in the original audit pass: the same `chunk_id` added 5 times via
`add_chunks()` produces `len() == 5`, not 1. `SessionChunkStore.add_chunks()`
(`backend/app/knowledge/runtime/session_chunk_store.py`) appends
unconditionally.

#### Design
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

#### Measurement
Correctness fix, not a performance item — no before/after threshold needed.
Ship criterion: the reproduction test from the original finding now asserts
`len() == 1`, not `== 5`.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_add_chunks_same_id_twice_deduplicates` | the exact reproduction: same `chunk_id` added 5× → `len() == 1` |
| `test_add_chunks_same_id_keeps_newest_text` | re-add with different `text` → the newer text wins |
| `test_all_chunks_and_query_unaffected_by_storage_change` | existing `SessionChunkStore` tests (already passing) continue to pass unmodified |
| `test_idempotent_retry_does_not_duplicate` | simulate Phase 1.2's retry path calling `add_chunks` twice with the same extracted chunks → store ends with one copy each |

---

### 5. Cache story registry / BM25 tokenization — **DROPPED, restated**

Already measured and dropped in the engineering plan (§0.3): 2.13ms and 2.05ms
respectively, against a multi-second storyteller call. **No design follows.**
This row exists in this document only so Phase 3's table has an entry for
every original row — the disposition is unchanged: do not build this. Revisit
only if a session's `SessionChunkStore` exceeds ~1,000 chunks in real telemetry
(watch for this in Phase 0B's ongoing ledger, not a new measurement task).

---

### 6. Indexed history pagination — **gated, design deferred**

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

### 7. Source-aware memory merge

#### Current state, verified
`retrieve.py:_merge_session_chunks` (`backend/app/knowledge/runtime/retrieve.py:141`):
session (dialogue-extracted) chunks fill only the **remaining** slots after
canonical (BM25/FAISS) results, up to `k_final` (default 8). If canonical
retrieval alone fills all 8 slots, session memory contributes **zero** results
regardless of relevance — confirmed by reading the exact `remaining = max(0,
k_final - len(main_results))` / `if remaining == 0: return main_results, 0`
logic.

#### Design — explicitly a quality experiment, not a performance change
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

#### Measurement — an A/B, not a latency number
This item cannot be evaluated by the stage ledger; it needs a **quality**
signal. Concretely: run the same fixed conversation transcript (or several)
through both the old and new merge policy, and manually or LLM-graded compare
whether player-revealed facts that should be retrievable in a later turn
actually appear in the prompt's retrieved-chunk list. **Ship threshold:** the
new policy retrieves at least as many relevant session facts as the old one on
a fixed test transcript, with zero instances of a session-sourced chunk being
treated as canonical truth (checked by asserting `confidence` tags are
preserved through the merge, unchanged).

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_reserved_budget_never_starves_session_chunks_when_canonical_fills` | 8 canonical hits + relevant session chunks available → session chunks still appear (today: they do not) |
| `test_reserved_budget_does_not_exceed_k_final` | total results still ≤ `k_final` regardless of how many session chunks exist |
| `test_session_chunks_retain_non_canonical_confidence_tag_through_merge` | the actual invariant — player-stated facts are never re-tagged as canonical by the merge |
| `test_dedup_by_chunk_id_still_applies_across_merge` | a session chunk with the same id as a canonical hit does not duplicate (uses row 4's fixed dedup) |

---

### 8. Reduce duplicated prompt inputs and sampled diagnostics

#### Current state
No single measurement exists yet distinguishing "duplicated" tokens from
necessary ones — this is a token-audit task, not a known bug. The plan's
protection requirement — *"compare story behavior and visibility; never remove
relevant memory just to shrink input"* — means this row's actual first step is
**instrumentation**, not a code change:

#### Design
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

#### Measurement
Per-layer token counts, captured from real six_strangers turns via the new
debug breakdown, reviewed by hand before deciding which layer (if any) has
genuine duplication worth removing. **This row's exit criterion is the
measurement itself + a decision, not a guaranteed code change** — it may
conclude "nothing here is actually duplicated," which is a valid, plan-
consistent outcome (cf. row 5).

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_prompt_debug_includes_per_layer_token_counts` | the new breakdown appears in `prompt_debug`, sums to the total prompt token count |
| `test_full_prompt_logging_gated_by_env_var` | `LOG_FULL_PROMPTS=false` → `user_msg`/`assistant_reply_preview` absent or truncated in the logged event; `true` → present |
| `test_log_full_prompts_defaults_false_in_production_shape` | mirrors the pattern of `LANGSMITH_TRACING`/`TYPESAFE_ENABLED` — off by default, explicit opt-in |

---

### 9. Bounded durable memory worker

#### Current state
Phase 1.2 (shipped) already built the durable outbox, the lease-based
`claim_pending`, and the periodic sweep. The plan's remaining ask —
*"Formalizes Phase 1.2's queue"* — is really about **bounding concurrency**:
today, `_extract_and_store_durable` fires via
`asyncio.ensure_future` with no cap on how many can run at once if many turns
complete in a short window.

#### Design
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
`design/JEV.md (extractor redesign)` §6). Not duplicated as separate design
work.

#### Measurement
Harness at concurrency 50 (BL-15's deferred tier), comparing peak concurrent
extraction tasks and DB connection contention with and without the semaphore.
**Ship threshold:** no increase in `mark_failed` rate (the semaphore must not
starve legitimate work) and a measurable cap on peak concurrent SQLite writes.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_extraction_concurrency_is_bounded` | N+1 simultaneous turns → at most `EXTRACTION_MAX_CONCURRENT` extraction tasks running at once (probed via a counter incremented/decremented around the semaphore) |
| `test_bounded_concurrency_does_not_change_durability_guarantees` | Phase 1.2's existing durability tests (`test_mark_done_with_chunks_persists_chunks_and_marks_done_atomically`, etc.) pass unmodified with the semaphore in place |
| `test_semaphore_does_not_deadlock_under_sustained_load` | harness run at concurrency 50 completes without hanging tasks |

---

### 10. Stable instruction prefixes for prompt caching

#### Current state, verified
`prompt_builder.py` interleaves stable instructions with changing state (the
11-layer order documented in `design/PROMPT_PIPELINE.md (layer coverage)`/
`design/PROMPT_PIPELINE.md (message flow)` mixes static rules with per-turn
relationship/location state within the same contiguous prompt, rather than
ordering all-static-first). Independently confirmed via the live turn measured
for the Jev cost model: `cached_tokens: 0` on a real turn (from
`PHASE_0B_BASELINE_NOTES_2026_09_22.md (removed; see git history)`), i.e. **zero prompt caching is
currently happening at all**, on any provider that supports it.

#### Design
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

#### Measurement to take before shipping
Two consecutive turns in the same session, before and after reordering,
reading `usage.prompt_tokens_details.cached_tokens` from the real OpenAI
response (the exact field already surfaced in
`PHASE_0B_BASELINE_NOTES_2026_09_22.md (removed; see git history)`'s baseline). **Ship threshold:**
`cached_tokens > 0` on the second turn after reordering, where it was
confirmed `0` before. If reordering alone does not produce a nonzero value
(the stable prefix may still be under the provider's minimum cacheable
length, or per-turn retrieved-knowledge content placed too early still
breaks the prefix), this row is **not shipped** until the actual byte-level
prefix is confirmed stable — no guessing.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_stable_layers_are_byte_identical_across_turns_same_session` | base prompt + self-knowledge output is `==` across two turns with no cast change |
| `test_layer_reordering_preserves_full_prompt_content` | the SET of text in the reordered prompt equals the set in today's order — nothing is dropped or duplicated, only moved |
| `test_cached_tokens_nonzero_on_second_turn` | integration test against a real (or faithfully mocked, if run in CI without a live key) provider response, asserting the measured field |

---

### 11. Immediate/full-reply and reduced-motion rendering

#### Current state
Frontend-only. Explicitly overlaps **BL-13** (the deferred iOS/mobile overhaul
backlog item) — the plan says to re-audit BL-13 before acting, since that
audit's own P1 finding (broken portraits) already proved stale once. **No
design is written here** for the same reason row 6 has none: acting before
re-auditing would risk designing against another stale finding.

**Action item, not a design:** re-run BL-13's audit steps (per its own
"What's needed" note) before this row gets a design. This belongs to Phase 5
(frontend), not Phase 3 — flagged here only because the original plan table
listed it under Phase 3; it is cross-referenced from
`design/ROADMAP_NOT_BUILT.md (Phase 5)` §6 where the frontend
work actually lives.

---

### 12. Sequencing within Phase 3

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

### 13. Exit criteria (unchanged from the plan, restated precisely)

- Quality and correctness unchanged — verified by each row's own
  characterization tests against current behavior.
- p95 and RSS meet or beat baseline — verified against the Phase 0B baseline
  already captured (`PHASE_0B_BASELINE_2026_09_22.json (removed; see git history)`).
- Every shipped optimization has before/after evidence — this document names
  the exact measurement per row; a row without a passing measurement does not
  ship, per row 10's explicit "not shipped until confirmed" language as the
  model for the rest.
- Every dropped item has a recorded measurement justifying the drop — rows 5
  already has one; row 6 and 11 have an explicit deferral reason instead of a
  measurement, which is the correct disposition when the measurement itself
  hasn't been taken yet, not a violation of this criterion.

---

## Phase 5 — reusable frontend and coherent assets: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md (removed; see git history)` Phase 5.

**Status: design only. Nothing here is implemented.**

---

### 1. Correction to the original plan's factual claims

The plan states: *"the current index does not load that module or consume
`world_map`; it still uses the older image path"* and *"the webhook's asset
list also omits those files."* **Both are now stale**, verified against the
current tree:

- `frontend/index.html:1284,1687` load `world-map.css`/`world-map.js`.
- `backend/app/main.py:408-417` serves both via explicit FastAPI routes
  (`@app.get("/world-map.js")` / `.css`, plus `/beta/` variants).
- `index.html:2784` reads `meta.world_map_image_revision` — the map *is*
  wired to live data, not the older static image path alone.
- The gitwebhook's asset list is moot regardless: Phase 0A established that
  mechanism has no live listener (Railway serves everything). Its omitted
  file list can't cause a production asset gap because it never runs.

This correction matters for scope: the map is **integrated**, not unfinished.
This phase's asset-manifest work (§5) is about giving `world-map.js/css` (and
`dialogue.js/css`) a declared place in one manifest, not about finishing an
integration that already shipped. Verify current live state before doing
manifest work, in case another parallel session's commits have moved further.

---

### 2. Current state, measured

`frontend/index.html`: **3,772 lines** (measured 2026-09-22; the plan's cited
3,798 was accurate at audit time — 26 lines moved since, consistent with the
ongoing parallel map-related commits visible in git log). One file: markup,
CSS, and all JS state/network/rendering code together, IIFE-wrapped, no build
step (this is a deliberate project constraint per `AI_UI_WORKFLOW.md`, not
something this phase removes).

`sendMessage()` at `index.html:2901` already has, from prior shipped work:
- a `request_id` generated per logical send (`genUUID()`, reused only for a
  genuine retry per its own comment) — this is the frontend half of BL-02,
  already wired to Phase 1.1's backend dedup.
- The gap the plan names: **no visible retry UI**. A failed `fetch` shows an
  error message; the player must retype and resend, not tap "retry" on the
  exact same `request_id`.

---

### 3. What this phase does NOT do

Per the plan's explicit instruction, repeated here because it is a hazard for
this specific phase: **preserve the existing appearance before any product
change.** This phase is an internal file-boundary refactor. No visual diff is
an acceptable outcome of any step below; a visual diff is a bug to fix, not a
byproduct to explain away.

No bundler/build step is introduced. `AI_UI_WORKFLOW.md`'s existing constraint
(single-file, no build) becomes single-*directory*, still no build — modules
are separate `<script>`-tag-loaded files (matching how `dialogue.js` and
`world-map.js` already work today), not ES modules requiring a bundler.

---

### 4. Module extraction

#### 4.1 Target layout

```
frontend/
  index.html          shell: markup + <script src> tags in dependency order,
                       shrinks from ~3,772 lines toward markup + wiring only
  app/
    api.js             fetch wrapper, apiHeaders(), request_id generation,
                       retry queue (§4.4)
    session-store.js    localStorage read/write for storieschat_sessions,
                       storieschat_profile, storieschat_stats
  features/
    chat.js            sendMessage, addMessage, typing indicator, dialogue
                       rendering hookup (calls into existing dialogue.js)
    catalogue.js        home screen story cards, story fetch/render
    journal.js           journal modal fetch/render (already a self-contained
                       block per its own modal pattern — lowest-risk first
                       extraction)
    roster.js            cast roster modal fetch/render
    map.js               inline world-map wiring (renderInlineWorldMap etc.) —
                       coordinates with the EXISTING world-map.js, does not
                       replace it
    auth.js              login modal, guest-bypass toggle, ?token= callback
  shared/
    dialogs.js           generic modal open/close helpers used by 4+ features
    formatting.js         genUUID, timestamp/display-name helpers
    motion.js             reduced-motion preference read/write (§6)
  dialogue.js           UNCHANGED — already its own file
  dialogue.css          UNCHANGED
  world-map.js          UNCHANGED — already its own file, already loaded
  world-map.css         UNCHANGED
```

#### 4.2 Extraction order — smallest blast radius first

| Step | Module | Why first/last |
| --- | --- | --- |
| 1 | `shared/formatting.js` | Pure functions (`genUUID`, display-name helpers), zero DOM coupling, easiest to verify byte-identical behavior |
| 2 | `shared/dialogs.js` | Generic modal helpers reused by journal/roster/map modals — extracting this before those three avoids triplicating the extraction |
| 3 | `features/journal.js` | Already the most self-contained feature (one fetch, one modal, no cross-feature state) — Phase 1.4's shipped journal work makes this the best-understood surface to move first |
| 4 | `features/roster.js` | Same modal pattern as journal, second-lowest risk |
| 5 | `app/session-store.js` | Used by many features but itself has no feature logic — extracting it before `chat.js`/`catalogue.js` means those two don't each reimplement localStorage access |
| 6 | `app/api.js` | The retry-queue work (§4.4) lands here — do this before `chat.js` since `chat.js` will call into it |
| 7 | `features/catalogue.js` | Home screen, independent of chat state |
| 8 | `features/map.js` | Coordinates with `world-map.js` (unchanged) — must come after `app/api.js` since map data comes from a fetch |
| 9 | `features/auth.js` | Touches the guest-bypass flag and login modal; left late because Phase 0's auth design (`design/PLATFORM.md (auth and persistence)`) is the authority here and any surprise interaction should surface after simpler extractions are proven safe |
| 10 | `features/chat.js` | Largest, most stateful, done last — by this point six other modules exist and chat.js mostly becomes wiring between them |

Each step: copy the relevant functions into the new file unchanged, add a
`<script src="app/formatting.js">`-style tag in `index.html` in dependency
order, delete the now-duplicated code from `index.html`, and run the full
browser verification in §7 before moving to the next step. **One module per
commit** — this phase produces ~10 small, independently revertible commits,
not one large one.

#### 4.3 How modules communicate without a build step

No ES `import`/`export` (would require `type="module"` and CORS-sensitive
`file://` behavior during local dev, plus stricter script-order requirements
than the current tolerant global-scope pattern). Instead: each module attaches
its public surface to one namespace object, matching the existing pattern
`dialogue.js` already uses (verified: it exposes functions the main script
calls directly, no module system).

```js
// app/api.js
window.StoriesChat = window.StoriesChat || {};
window.StoriesChat.api = {
  send: async function(payload) { ... },
  apiHeaders: function() { ... },
};
```

`index.html`'s remaining wiring code calls `StoriesChat.api.send(...)` instead
of a bare `sendMessage`'s old inline fetch. This is the minimum-risk
compromise between "no build step" and "no global namespace pollution" — one
namespace, not dozens of bare globals.

#### 4.4 Pending-request persistence + retry UX

The actual new behavior this phase adds (not just extracted, genuinely new):

```js
// app/api.js
StoriesChat.api.send = async function(sessionId, text, options) {
  const requestId = (options && options.requestId) || StoriesChat.formatting.genUUID();
  const pending = { sessionId, text, requestId, ts: Date.now() };
  StoriesChat.sessionStore.savePendingRequest(pending);   // localStorage, survives a reload

  try {
    const result = await fetch(CHAT_URL, { method: "POST", body: JSON.stringify({
      session_id: sessionId, message: text, request_id: requestId,
    })});
    StoriesChat.sessionStore.clearPendingRequest(sessionId);
    return result;
  } catch (err) {
    // pending request stays in localStorage; caller shows retry UI
    throw new PendingRetryableError(requestId, err);
  }
};
```

On chat screen load, `StoriesChat.sessionStore.getPendingRequest(sessionId)`
is checked: a leftover pending request (page was closed/crashed mid-send)
surfaces a "Resend?" banner using the **same `requestId`** — which Phase 1.1's
backend dedup (already shipped) will either replay the completed reply for
(if it actually succeeded server-side before the client lost the response) or
process fresh (if it genuinely never reached the server). This is the
"pending-request persistence plus timeout/retry UX, paired with Phase 1.1's
request-ID dedup so a user-visible retry is safe by construction" the plan
calls for, made concrete.

**Timeout UX:** a fetch exceeding a client-side timeout (recommend 45s,
comfortably above the storyteller's own 30s server-side timeout so the client
never "gives up" before the server would have) shows the same retry banner
rather than a bare error, using the identical `requestId`.

#### 4.5 Test plan (module extraction)

Frontend tests in this repo are Node (`.test.cjs`, per `tests/frontend/`) plus
Python-driven browser checks (per `test_cast_roster_ui.py` etc.) — this phase
follows both existing patterns, adds none new.

| Test | Assertion |
| --- | --- |
| `formatting.test.cjs` | `genUUID()` produces the same format as today's inline version; existing display-name helpers unchanged |
| `api_retry.test.cjs` | `StoriesChat.api.send` persists a pending request before the fetch resolves, clears it on success, leaves it on failure |
| `test_pending_request_survives_reload.py` (Playwright) | simulate a network failure mid-send, reload the page, assert the retry banner appears with the same `requestId` (inspect via `page.evaluate` reading `localStorage`) |
| `test_retry_uses_same_request_id.py` (Playwright) | click "Resend", assert the outgoing request's `request_id` matches the original (network intercept) |
| one characterization test per extracted module | before/after: call the function through the OLD inline location vs the NEW module path with identical inputs, assert identical output — written before each step 1-10 extraction, per the plan's general "characterization tests before moving behavior" rule |

---

### 5. Asset manifest

#### 5.1 Problem, restated correctly (per §1's correction)

The real gap is not "the map isn't wired" (it is). The real gap is that
**there is no single declared list** of which static files the frontend
depends on — `index.html`'s own `<script src>`/`<link>` tags are the only
place this exists today, duplicated by nothing (the previously-cited webhook
asset list is dead code per Phase 0A and irrelevant to what actually ships).
So the risk this row protects against is real but different from how the
plan described it: **a future asset added to `index.html` with no
corresponding cache-busting/service-worker awareness**, not a deployment-path
omission.

#### 5.2 Design

```json
// frontend/asset-manifest.json — new, single source of truth
{
  "version": 6,
  "assets": [
    {"path": "dialogue.js", "cache": "versioned"},
    {"path": "dialogue.css", "cache": "versioned"},
    {"path": "world-map.js", "cache": "versioned"},
    {"path": "world-map.css", "cache": "versioned"},
    {"path": "manifest.json", "cache": "shell"},
    {"path": "sw.js", "cache": "shell"}
  ]
}
```

Three consumers, each reading this file instead of hardcoding a list:

1. **`index.html`**: a small inline script reads `asset-manifest.json` at load
   and appends `?v={version}` to each `<script src>`/`<link href>` — replacing
   today's manually-typed `?v=1` query strings (verified present:
   `world-map.css?v=1`, `world-map.js?v=1`). One version bump in the manifest
   updates every asset's cache-buster at once, instead of hand-editing each
   tag.
2. **`backend/app/main.py`**: the existing per-file `FileResponse` routes stay
   (no route consolidation — that would be a bigger, riskier change than this
   phase's scope), but a new test (§5.3) asserts every `path` in the manifest
   has a corresponding route, so an asset can't be added to the manifest
   without also being served.
3. **`sw.js`**: `SHELL_URLS` (currently a hardcoded array,
   `frontend/sw.js:5`) is generated from the manifest's `"cache": "shell"`
   entries at build-time-equivalent (a small script run manually or in CI,
   since there's no bundler) rather than hand-maintained.

`CACHE_NAME` in `sw.js` (currently `'storieschat-v5'`, hand-incremented) is
tied to `asset-manifest.json`'s `"version"` field going forward — one number
to bump, not two files to remember to keep in sync.

#### 5.3 Test plan

| Test | Assertion |
| --- | --- |
| `test_every_manifest_asset_has_a_backend_route` | for each `path` in `asset-manifest.json`, `backend/app/main.py` defines a `FileResponse` route serving it (reflection over the FastAPI route table, or a simple grep-based check — either is acceptable, the point is CI catches a mismatch) |
| `test_sw_shell_urls_generated_from_manifest` | `sw.js`'s `SHELL_URLS` array matches the manifest's `"cache": "shell"` entries |
| `test_index_html_uses_manifest_version_for_cache_busting` | the inline version-read script appends the manifest's current version to each asset URL (Playwright: inspect actual `<script>` `src` attributes after page load) |
| `test_world_map_assets_still_referenced` (already exists: `test_world_map_assets.py`) | re-run unmodified — confirms this phase does not regress the already-shipped map integration |

---

### 6. Accessible motion settings

#### 6.1 Current state — corrected after verification

The plan's phrasing ("preserve... the existing animation option") turned out
to describe real, already-shipped functionality more extensive than an
initial search suggested. Verified in `index.html`:

```js
var TYPEWRITER_SPEED_KEY = "storieschat_typewriter_speed";
var TYPEWRITER_SPEEDS = [10, 4, 2.5];      // ms per character, 3 user-selectable speeds

function getTypewriterDelay(){
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return 0;
  var idx = parseInt(localStorage.getItem(TYPEWRITER_SPEED_KEY) || "1", 10);
  ...
  return TYPEWRITER_SPEEDS[idx];
}
```

So today: (1) the OS-level `prefers-reduced-motion: reduce` is **already
respected** and forces instant (0-delay) reveal; (2) a 3-speed typewriter
setting already exists and is already localStorage-backed; (3) history replay
already passes `skipTypewriter: true` (`index.html:2637,2697`) so loaded past
messages never re-animate.

**The actual, narrower gap:** there is no **in-app override** independent of
the OS setting. A player on a shared/managed device without OS-level access,
or one who simply wants instant reveal without changing system accessibility
settings, has no in-app "always skip animation" control — only the 3 speed
levels, none of which is "off," and the only "off" path is the OS setting
`getTypewriterDelay()` already checks. This is a much smaller change than a
new motion subsystem — it is one more value alongside the existing 3 speeds.

#### 6.2 Design

```js
// shared/motion.js — wraps the EXISTING mechanism, does not replace it
window.StoriesChat = window.StoriesChat || {};
StoriesChat.motion = {
  // Index 3 = new "instant" option, appended after the existing 3 speeds
  // so TYPEWRITER_SPEED_KEY's stored values (0/1/2, real player data) stay
  // valid and unchanged in meaning.
  SPEEDS: TYPEWRITER_SPEEDS.concat([0]),

  getDelay: function() {
    // Preserves getTypewriterDelay()'s exact OS-check-first order; the only
    // change is reading from the extended SPEEDS array.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return 0;
    var idx = parseInt(localStorage.getItem(TYPEWRITER_SPEED_KEY) || "1", 10);
    if (!Number.isFinite(idx) || idx < 0 || idx >= this.SPEEDS.length) idx = 1;
    return this.SPEEDS[idx];
  },
};
```

`getTypewriterDelay()` becomes a thin call into `StoriesChat.motion.getDelay()`
(one of §4.2's extraction steps, folded into `shared/motion.js` rather than
staying inline) — same OS-check-first order, same storage key, same stored
value semantics for existing players (index 0/1/2 unchanged), with index 3
added as the new always-instant option in whatever settings UI already
exposes the 3-speed picker.

**This does not touch BL-13's larger scope** (keyboard-safe shell, map/sheet
redesign) — those remain deferred pending BL-13's own re-audit, per §1's
finding that re-auditing before acting is the standing instruction for that
backlog item specifically.

#### 6.3 Test plan

| Test | Assertion |
| --- | --- |
| `motion.test.cjs` | `getDelay()` returns 0 when `matchMedia` reports reduced motion, REGARDLESS of stored speed index (OS check must stay first, matching today's exact order) |
| `motion.test.cjs` | `getDelay()` returns each of the 4 `SPEEDS` values for stored indices 0-3 |
| `test_existing_speed_settings_unaffected.py` (Playwright) | a player with `storieschat_typewriter_speed=0` stored from BEFORE this change still gets the same slow speed after it (index semantics preserved) |
| `test_new_instant_option_skips_reveal_animation.py` (Playwright) | selecting the new 4th option renders a new NPC reply in full immediately |
| `test_reduced_motion_still_forces_instant.py` (Playwright, `prefers-reduced-motion: reduce` emulated) | unchanged existing behavior, re-verified after the extraction |

---

### 7. Verification protocol (unchanged from AGENTS.md section 3, restated as this phase's own checklist)

Per each extraction step in §4.2 and each of §5/§6's additions:

1. **Desktop Chromium** against local dev server — visual diff check (none
   expected) + the specific characterization test for that step.
2. **iPhone-sized WebKit session** — same page, same checks. This is where a
   module-loading order mistake (a `<script>` tag moved before its dependency)
   would most likely surface as a console error, per BL-13's history of
   mobile-specific findings.
3. After all steps land locally and pass both modes: push to beta, repeat both
   modes against the live hosted beta site (not just local dev server) —
   **this is the step Phase 4's `BL-03` incident (referenced in
   `ship-and-verify`'s own skill doc) exists to prevent skipping**: a bug that
   only exists in the deployed/browser context, not in local dev or pytest.

**Exit criteria (unchanged from the plan):** desktop Chromium and iPhone-sized
WebKit checks per AGENTS.md section 3, local then live beta; no duplicate send;
guest/auth resume, history, roster, map, journal, and offline upgrade all
work; stale-cache upgrade and rollback tested on both hosts (the asset-
manifest version bump from §5.2 is the concrete mechanism this last item
tests against).

### 8. What this phase deliberately does not do

- Does not introduce a bundler, transpiler, or `npm run build` step.
- Does not touch `dialogue.js`/`world-map.js` internals — both are already
  separate files with working integrations (§1); this phase only gives them a
  declared place in the manifest.
- Does not act on BL-13's keyboard-safe-shell or map/sheet-redesign items —
  those need BL-13's own re-audit first, per that backlog entry's explicit
  instruction.
- Does not change the PWA's `manifest.json`/`sw.js` *behavior*, only how
  `sw.js`'s asset list is generated (from the new manifest instead of
  hand-maintained).

---

## Phase 6 — delivery and documentation: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md (removed; see git history)` Phase 6.

**Status: design only. Nothing here is implemented.**

---

### 1. Runtime version alignment

#### Current state, verified
`Dockerfile:1` — `FROM python:3.10-slim`.
`.github/workflows/tests.yml:18,39` — `python-version: "3.11"` (both jobs).

#### Design
Pin **3.11** everywhere — it is what CI already validates against, so aligning
the Dockerfile to it (rather than the reverse) means zero new test exposure.

```dockerfile
FROM python:3.11-slim
```

**Ship criterion:** the full test suite (`python -m pytest tests/ -q`,
currently 801 passed / 1 xfailed) passes unmodified under 3.11 inside the
container, matching what CI already proves outside it. Any dependency in
`backend/requirements.txt` that has a 3.10-specific pin gets bumped alongside
(discovered by running the build, not guessed here).

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_docker_build_succeeds_on_3_11` | CI step: `docker build .` completes, including the existing build-time pytest gate (`RUN ... pytest /srv/tests`) |
| existing full suite | passes inside the built image, not just in CI's bare Python 3.11 job — this is the "same tested artifact reaches beta" exit criterion, checked at build time, not assumed from CI parity |

---

### 2. Dockerfile layer ordering

#### Current state, verified
```dockerfile
COPY backend/ /srv/backend/
COPY frontend/ /srv/frontend/
COPY tests/ /srv/tests/
COPY scripts/ /srv/scripts/

RUN pip install --no-cache-dir -r /srv/backend/requirements.txt
```
Confirmed: `COPY` of all source happens **before** `pip install`. Docker layer
caching invalidates every layer from the first changed `COPY` onward — so any
source edit (including a one-line frontend CSS tweak) invalidates the `pip
install` layer too, forcing a full dependency reinstall on every build
regardless of whether `requirements.txt` changed.

#### Design
```dockerfile
# ------------------------------------------------------------
# Install dependencies FIRST (cached unless requirements.txt changes)
# ------------------------------------------------------------
COPY backend/requirements.txt /srv/backend/requirements.txt
RUN pip install --no-cache-dir -r /srv/backend/requirements.txt

# ------------------------------------------------------------
# Copy code (clean, deterministic) — AFTER dependency install
# ------------------------------------------------------------
RUN echo "🔥 Resetting /srv and /tmp" \
    && find /srv -mindepth 1 -maxdepth 1 ! -name requirements.txt -exec rm -rf {} + \
    && rm -rf /tmp && mkdir -p /tmp && chmod 1777 /tmp

WORKDIR /srv
COPY backend/ /srv/backend/
COPY frontend/ /srv/frontend/
COPY tests/ /srv/tests/
COPY scripts/ /srv/scripts/
```

**Caveat, stated plainly:** the existing `rm -rf /srv` reset step must not
delete the just-installed Python package directory if `pip install` targets
system site-packages (it does, by default, not `/srv`) — verified this is
safe: `pip install` without `--target`/`--user` installs to the interpreter's
site-packages, not the working directory, so resetting `/srv` after install
does not remove installed packages. The adjusted reset command above
preserves `requirements.txt` specifically only so a rebuild's diff is easy to
read; it is not required for correctness.

#### Measurement
Build the image twice: once changing only a frontend file, once changing only
`requirements.txt`. **Ship criterion:** the frontend-only change's build
reuses the cached pip-install layer (visible in `docker build` output as
`CACHED`); the requirements-only change's build does not.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_frontend_only_change_reuses_dependency_layer` | CI or manual: two builds, second reuses the pip-install layer per Docker's own cache-hit reporting |
| existing build-time pytest gate | still runs, still fails the build on a real test failure (unchanged behavior, reordered layers only) |

---

### 3. Dependency set separation + lock

#### Current state, verified
`backend/requirements.txt`: **34 lines**, all pinned with `==`, but runtime
(`fastapi`, `httpx`, `torch`, `sentence-transformers`, `faiss-cpu`, ...),
build-time (nothing currently separate — `torch`/`sentence-transformers` are
both build-time-needed for embedding and runtime-needed for retrieval, so the
split is genuinely blurred today), and test-only (`pytest`, `pytest-asyncio` —
notably **not even in this file**; CI's own `pip install pytest
pytest-asyncio` step installs them separately, meaning the test-runner
versions aren't pinned at all and could silently drift between CI and a local
dev environment).

#### Design

```
backend/
  requirements.txt          runtime + build (unchanged from today — genuinely
                             one set, since the embedder needs torch/
                             sentence-transformers at BOTH build-index time
                             and request time)
  requirements-test.txt     NEW: pytest==<pinned>, pytest-asyncio==<pinned>,
                             plus anything else CI installs ad hoc today
  requirements.lock.txt     NEW: pip freeze output, full transitive closure,
                             regenerated whenever requirements.txt or
                             requirements-test.txt changes
```

CI's install step changes from `pip install pytest pytest-asyncio` (unpinned)
to `pip install -r backend/requirements-test.txt` (pinned) — this is the
concrete fix for the drift risk above, and the smallest actual change in this
row; the "separate runtime/build/test sets" framing mostly documents that
runtime and build are correctly *not* separated (both need the same heavy ML
deps), while test genuinely was ungoverned and now isn't.

**Lock file generation** is a manual/CI step, not hand-maintained:
```bash
pip install -r backend/requirements.txt -r backend/requirements-test.txt
pip freeze > backend/requirements.lock.txt
```
Docker's `pip install` continues to use `requirements.txt` directly (not the
lock file) for the runtime image — the lock file is a **reproducibility
record and CI drift-detector**, not the thing Docker installs, since pinning
the full transitive closure in the image build risks fighting the base
image's own preinstalled package versions in ways the current `==`-pinned
top-level list does not.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_ci_uses_pinned_test_dependencies` | CI workflow YAML installs from `requirements-test.txt`, not an ad hoc `pip install` line |
| `test_lock_file_matches_current_environment` | CI step: `pip freeze` diffed against `requirements.lock.txt` — mismatch fails CI with a clear "regenerate the lock file" message, catching silent drift before it reaches a deploy |

---

### 4. Recovery off the readiness-critical path

#### Current state, verified
`backend/app/main.py`'s `lifespan()`:
```python
init_db()
_startup_checks()
await _fact_extraction_recovery_sweep()      # <- AWAITED, blocks readiness
cleanup_task = asyncio.create_task(...)
extraction_sweep_task = asyncio.create_task(...)
warm_task = asyncio.create_task(_warm_embedder())   # <- NOT awaited (Phase 1.3's fix)
yield
```
`_fact_extraction_recovery_sweep()` is still `await`ed before `yield` — the
exact pattern Phase 1.3 already fixed for the embedder is **not yet applied
here**. On a deploy following an outage with many pending outbox rows, this
sweep could take meaningfully long, delaying container readiness the same way
the pre-Phase-1.3 embedder delayed the first request.

Separately, the Dockerfile's `CMD` runs
`python -m backend.app.knowledge.build.build_index` **before** `exec uvicorn`
— the whole container's startup, not just FastAPI's readiness, blocks on index
build every single deploy, even when the index content hasn't changed since
the last build.

#### Design

**4a. Recovery sweep, same pattern as Phase 1.3's embedder fix:**
```python
async def lifespan(app: FastAPI):
    init_db()
    _startup_checks()
    cleanup_task = asyncio.create_task(_guest_cleanup_loop())
    extraction_sweep_task = asyncio.create_task(_fact_extraction_periodic_sweep_loop())
    warm_task = asyncio.create_task(_warm_embedder())
    # Fire-and-forget, matching warm_task's established pattern: readiness
    # does not wait on however many rows a prior crash left pending.
    recovery_task = asyncio.create_task(_fact_extraction_recovery_sweep())
    yield
    cleanup_task.cancel()
    extraction_sweep_task.cancel()
    warm_task.cancel()
    recovery_task.cancel()
```
**Caveat, stated plainly (mirrors Phase 1.3's own honest framing of its
tradeoff):** a request arriving before the recovery sweep completes could, in
principle, re-trigger extraction for a session whose facts are mid-recovery.
Phase 1.2's `mark_done_with_chunks`'s atomicity and `claim_pending`'s
lease-based locking (both shipped) already make this race safe — a row
already claimed by the recovery sweep is not claimable by anything else until
its lease expires, so no double-processing occurs even though this change
removes the "recovery finishes before any request is served" ordering
guarantee. This is not a new risk introduced by this change; it is the same
risk profile the periodic sweep (also not awaited) already has today.

**4b. Index prebuild + fingerprint, so `CMD` skips redundant work:**
```python
# backend/app/knowledge/build/build_index.py — additive, not a rewrite
def _content_fingerprint() -> str:
    """Hash of every story/knowledge source file's mtime+size. Cheap
    (stat, not read) and changes iff content that would change the built
    index changes."""
    ...

def main():
    fp = _content_fingerprint()
    marker = INDEX_DIR / ".fingerprint"
    if marker.exists() and marker.read_text().strip() == fp:
        print(f"index fingerprint unchanged ({fp[:12]}...), skipping rebuild")
        return
    _do_build()   # existing logic, unchanged
    marker.write_text(fp)
```
Dockerfile's `CMD` calls this unchanged (`python -m
backend.app.knowledge.build.build_index`) — the skip logic is internal to the
script, so no Dockerfile change is needed for 4b, only for the fingerprint
file to persist across container restarts if desired (it lives under
`KNOWLEDGE_CACHE_DIR`, which is already the Railway-persistent-volume path
per the existing `ENV KNOWLEDGE_CACHE_DIR=/data/knowledge_cache`, so it
already survives restarts without any new volume configuration).

#### Measurement
Time `lifespan()`'s pre-`yield` duration (a simple `time.perf_counter()`
bracket logged at INFO, temporary instrumentation for this change's own
validation, not a permanent addition) before and after 4a, under a
constructed scenario with ~100 pending outbox rows (matching the periodic
sweep's own `limit=200` batch size for realism). **Ship threshold:** pre-yield
duration drops to near-zero (only `init_db`/`_startup_checks` remain
synchronous); the recovery work still completes, verified by the existing
Phase 1.2 recovery-sweep tests re-run unmodified.

For 4b: time two consecutive container starts with no content change.
**Ship threshold:** second start's `build_index` step reports "skipping
rebuild" and completes in under 1 second (stat-only fingerprint check) versus
today's full rebuild time on every start.

#### Test plan
| Test | Assertion |
| --- | --- |
| `test_recovery_sweep_does_not_block_readiness` | `lifespan()`'s pre-yield phase completes without awaiting `_fact_extraction_recovery_sweep`; a probe confirms the app is "ready" while the sweep task is still running (same technique as Phase 1.3's `test_startup_warm_up_does_not_block_the_event_loop`) |
| Phase 1.2's existing recovery-sweep tests | re-run unmodified — the sweep's own correctness is untouched, only its await point moved |
| `test_fingerprint_unchanged_skips_rebuild` | two calls to `main()` with no content change → second is a no-op, verified via a call-count spy on `_do_build` |
| `test_fingerprint_changes_on_content_edit` | modifying a story JSON's mtime/size changes the fingerprint → rebuild runs |
| `test_fingerprint_persists_across_restart` | fingerprint marker survives a simulated restart (same directory reused) |

---

### 5. CI frontend checks

#### Current state, verified
`tests/frontend/*.test.cjs` (Node, no browser) and
`tests/frontend/test_*.py` (Python-driven, presumably Playwright-based per
AGENTS.md section 3's browser-automation references) both exist as **files** but
`.github/workflows/tests.yml` runs only `pytest tests/ -v
--ignore=tests/backend/integration/` — which **does** collect and run the
Python frontend tests (they're under `tests/`, not excluded), but does **not**
run the `.test.cjs` Node tests at all (no `node` or `npm test` step in the
workflow).

#### Design
```yaml
  frontend-node-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Run frontend Node tests
        run: |
          for f in tests/frontend/*.test.cjs; do
            echo "=== $f ==="
            node "$f" || exit 1
          done
```
One new CI job, parallel to `unit-tests`/`integration-tests`. No new test
framework — reuses the existing `node <file>.test.cjs` invocation pattern
already used manually (confirmed working: `node tests/frontend/world_map.test.cjs`
→ `3 pass` in prior session verification).

**The Python frontend tests are not Playwright-based, verified.**
`test_cast_roster_ui.py` (and, checked as representative of the pattern:
static-file string assertions, no browser) reads `frontend/index.html` as text
and asserts on literal strings/patterns within it — e.g. confirming a specific
`sendMessage(...)` call and its options object appear verbatim. No `Page`,
no `browser`, no network. These already run correctly under CI's existing
`pytest tests/` step with zero additional infrastructure, because they need
none. **No CI change needed for this half of row 5** — resolved by reading the
test file rather than guessing from its name.

The real Playwright-driven browser checks AGENTS.md section 3 requires (desktop
Chromium + iPhone-sized WebKit against a running dev server or live beta) are
a **manual/agent-invoked verification step** in this project's workflow
(`ship-and-verify`'s skill doc, the Playwright MCP plugin), not a `pytest`-
collected test suite — so there is nothing of that kind to add to CI here.
That verification stays where the project already puts it: local pre-commit
and post-deploy, per `ship-and-verify`, not this row.

#### Test plan
| Test | Assertion |
| --- | --- |
| new `frontend-node-tests` CI job | fails the workflow if any `.test.cjs` file's process exits nonzero |

---

### 6. Documentation updates

Per the plan's own list, each doc gets a specific addition, not a rewrite:

| Doc | Addition |
| --- | --- |
| `design/PLATFORM.md (infrastructure)` | Phase 0A's empirical finding (Railway serves both environments; cPanel path confirmed dead) + LangSmith/TypeSafe env var names (not values) |
| `AI_FATAL_MISTAKES.md` | 0A.4's decision record: webhook secret in git history, rotation via BL-14, history-rewrite explicitly rejected and why |
| `design/CHARACTER_MEMORY.md (data models)` | `extracted_chunks` table (Phase 1.2) and the `Snapshot`/`SnapshotCodec` versioned envelope (Phase 2, if implemented) |
| `design/PROMPT_PIPELINE.md (message flow)` | `TurnService`/command dispatch (Phase 2, if implemented) — and the stable-prefix layer reordering (Phase 3 row 10, if shipped), since that doc is the authority on layer order |
| `design/PLATFORM.md (auth and persistence)` | Phase 1.5's exact-eviction fix and the per-session lock coordination |
| `documentation/backlog/` | close BL-01c (already done, 2026-09-22); reconcile BL-13 per its own re-audit instruction; add BL-16 (already done) |

**This row ships alongside whichever phase actually lands the corresponding
code** — not as a batch at the end. A doc update for work that hasn't shipped
yet would itself violate the project's own doc-truthfulness norms
(`AI_DOC_INDEX_CATALOGUE.md`'s entire purpose). Listed here for completeness
of Phase 6's scope, not as deferred work to batch later.

---

### 7. Sequencing within Phase 6

```
Row 1 (Python version)      ── do FIRST, alone: smallest, most isolated, and
                                every other row's CI/build verification runs
                                cleaner on one aligned version
Row 2 (layer ordering)       ── independent, no code dependency
Row 3 (dependency lock)      ── independent, but do AFTER row 1 (the lock
                                file's content depends on which Python version
                                produced it)
Row 4a (recovery off-path)   ── independent; same PATTERN as Phase 1.3, no
                                new mechanism to design, low risk
Row 4b (index fingerprint)   ── independent of 4a; can ship separately
Row 5 (CI frontend checks)   ── independent; do the empirical Playwright-in-CI
                                check FIRST, before writing the conditional
                                install-step change
Row 6 (doc updates)          ── ongoing, alongside whichever phase ships the
                                corresponding code, not batched here
```

### 8. Exit criteria (unchanged from the plan, restated precisely)

- The same tested artifact reaches beta — verified by row 1's build-time
  pytest gate running inside the aligned-version image, not just in CI
  outside it.
- Content, asset, and build identities agree — the asset manifest (Phase 5
  §5) and the index fingerprint (row 4b) are the two concrete mechanisms that
  make "identity" a checkable fact rather than an assumption.
- Production release remains separately requested — unchanged; nothing in
  this phase touches the beta→prod approval gate in AGENTS.md section 4.

---

## Game Design Systems

> **What this doc is for:** Technical game-design mechanics — how the world state works, how time drives change, how quests trigger, how difficulty modes differ, and how the post-game loop works. Edit this doc when adding or changing core gameplay systems, quest tiers, difficulty modes, or win conditions.

---

### Four Universal Primitives

The engine runs on four primitives that scale to any game and genre:

1. **State** — the single ground truth
2. **Time** — the only automatic driver of change
3. **Incentives** — why characters act
4. **Constraints** — what prevents nonsense

Everything else emerges.

---

### 1. World State (Single Ground Truth)

Worlds can opt into a reusable researched atlas and shortest-time routing via
their world JSON. Atomic locations drive both map exploration and gameplay;
area containers never become travel destinations. Straight-line geography and
estimated travel minutes are separate data. See [design/WORLD_MODEL.md (atlas)](WORLD_MODEL.md).

Each game defines:
- characters
- locations
- relationships
- resources
- evidence / artifacts
- flags

There is **one canonical world state**.

The player never sees the full state. They only see:
- observations
- dialogue
- evidence
- inference

The LLM may *interpret* and *describe* state, but may never invent or overwrite it.

---

### 2. Time Is the Only Engine

- Every player action costs time:
  - dialogue
  - movement
  - investigation
- Time passing enables:
  - NPC decisions
  - opportunity loss
  - decay (evidence, memory, access)

There is no scripted event loop.
Time advances → incentives resolve → state updates.

---

### 3. Characters Are Defined by Incentives

Each character has:
- **Goals** (what they want)
- **Fears** (what they avoid)
- **Constraints** (what they cannot do)
- **Resources** (what they can use)
- **Knowledge** (what they believe to be true)

At decision points, characters act probabilistically based on incentives and constraints.
No character has:
- a fixed arc
- a required outcome
- prewritten future dialogue

---

### 4. Constraints Enforce Reality

Constraints replace story scripting:
- time cost
- access control
- information asymmetry
- risk
- irreversibility

Examples:
- Evidence decays because time passes
- NPCs act because pressure accumulates
- Secrets remain hidden unless conditions reveal them

---

### Two-Call Turn Architecture

Every player turn uses **two distinct LLM calls**, in a fixed order.

#### Call 1 — Extractor (State Mutation Only)

**Purpose:** Detect *what happened* structurally in this turn.

**Runs:** Every turn.

**Input:**
- current user message
- recent conversation window (last ~6–8 messages)
- bounded world-state summary
- quest trigger definitions (natural language conditions)
- extraction schema

**Output (structured JSON only):**
- location / movement intent
- quest triggers fired
- quest progress updates
- quest completions
- any other structured signals

**Rules:**
- Extractor may **only propose** state changes.
- Engine validates all proposals.
- No extractor output may overwrite ground truth improperly.

#### Call 2 — Main Narrative LLM (Presentation Only)

**Purpose:** Render dialogue, description, emotion, and story.

**Runs:** After extractor updates the state.

**Input:**
- updated world state
- player-observable knowledge only
- difficulty / mode constraints

**Rules:**
- May describe, emote, speculate, or mislead (in-character)
- May not invent new state
- May not bypass extractor logic

This separation guarantees **epistemic integrity** and scalability.

---

### Quest System (Trigger-Based, Extractor-Driven)

Quests are **not scripted scenes**. They are **latent possibilities** defined by triggers.

#### Quest Triggers
- Each quest defines:
  - natural-language trigger conditions
  - allowed state changes
  - tier (1–5)
- Triggers are evaluated **every turn** by the extractor.

#### Quest Tiers

**Tier 1 — Main Quest**
- Always detectable from initial state.
- Represents the dominant conflict.

**Tier 2 — Standard Side Quests**
- Easy to discover.
- Quest start + name announced.

**Tier 3 — Conditional Side Quests**
- Triggered only when rare conditions are met.
- Quest start + name announced.

**Tier 4 — Ultra-Secret Quests**
- Trigger silently.
- Player only learns of them upon completion.
- Award secret achievement badge (name + rarity only).

**Tier 5 — Unknown Quests (?????)**
- Exist as latent possibilities.
- No one has unlocked them yet.
- Represent the frontier of the system.

---

### Difficulty & Modes (Narrative Resistance)

Difficulty controls **forgiveness**, not content.

#### Game Mode (Canon Enabled)

**Hard**
- No rerolls
- Non-deterministic outcomes
- Missed info stays missed

**Normal**
- Limited rerolls
- Rerolls affect tone/minor branches only
- Ground truth immutable

**Easy / Casual**
- More rerolls
- Slower decay
- Larger grace windows
- Truth still enforced

#### Roleplay Mode (God Mode)
- One-way downgrade
- Unlimited flexibility
- Achievements and canon disabled

---

### "100% Cleared"

A run is **100% cleared** if:
1. You complete all quests discovered at least once in this world history, and
2. You discover and complete at least one new quest

If no undiscovered quests remain:
- 100% cleared = complete all quests

---

### Main Milestone ("Ganon") Is Not the End

Solving the main conflict:
- flips world state
- unlocks harder, stranger content
- does not end the game

The world continues.

---

### Post-Milestone Forever Loop

1. Use curated follow-up arcs if they exist
2. Otherwise generate provisional arcs from state + incentives
3. Early clearers co-author future directions (guided by LLM prompts)
4. Multiple arcs compete
5. Best arcs consolidate into canon
6. Repeat forever

---

### MVP Scope

- Single-player
- In-memory state
- No login, credits, or leaderboards
- Extractor runs every turn
- Two-call architecture enforced
- No prewritten future story text
- Scales to many games with minimal hardcoding

---

## NPC Workflow + Sidequest Design

> **What this doc is for:** Design of NPC lifecycle and sidequest trigger system. Edit this doc when NPC behavior, sidequest triggers, or quest logic changes.

Last updated: 2026-02-27

---

### Part I — Philosophy

#### What is an NPC hallucination, really?

When the LLM introduces a character the author never defined — "a nervous-looking man at the end of the bar" — it isn't making an error. It's worldbuilding. The player's curiosity created a narrative need; the LLM filled it plausibly.

The engine should treat these emergent characters as **real**, persistent participants. Discarding them (letting them vanish between turns) breaks immersion and wastes the relationship information already building around them. Capturing and persisting them is the right move.

The distinction that matters is not *authored vs. hallucinated* but **shallow vs. deep**:
- A shallow NPC is a plausible detail: a name, a face, a mood. Enough to make the world feel inhabited.
- A deep NPC has motivation, secrets, a history with the player. They can anchor a sidequest.

Shallow NPCs remain shallow until the player shows interest. **Depth is earned through engagement, not pre-written.**

---

#### When should backstory be generated?

Never speculatively. Backstory should only be generated when the player's actions signal genuine interest. Three signals matter:

1. **Repeated engagement** — the player has talked to the NPC multiple times (meeting_count ≥ 3). They're not just passing through.
2. **Emotional investment** — the player's attitude toward the NPC has warmed (affection ≥ 0.3 or trust ≥ 0.3 on the player→NPC edge).
3. **Direct inquiry** — the player explicitly asks about the NPC's past, motivations, or secrets.

Any one of these signals is sufficient to trigger backstory generation. The result is locked immediately — it becomes canonical for the session and cannot be contradicted by future LLM responses.

The corollary: **do not pre-generate backstory for every NPC at spawn time**. Most NPCs will remain shallow and that's fine. Pre-generation wastes tokens and creates unused content.

---

#### Sidequests: authorized hallucination

The LLM should not hallucinate sidequests freely. Unauthorized sidequest generation would break narrative coherence — the author spent time crafting the main story arc, and random LLM diversions dilute it.

But **authorized sidequest hallucination** is a feature, not a bug. The conditions for authorization:

1. **Familiarity threshold** — player and NPC have met enough times (meeting_count ≥ 3) and the relationship has some warmth
2. **Narrative readiness** — a minimum number of main story turns have passed (prevents sidequests in the first 5 minutes)
3. **Player curiosity signal** — player asks about the NPC beyond surface-level conversation

When all three conditions are met, the engine can signal to the LLM that a sidequest is available for this NPC. The LLM proposes it; the engine stores it; the player decides.

Sidequests should be:
- **Small**: 3–7 turns to complete, not sprawling arcs
- **Personal**: about the specific NPC, not abstract tasks
- **Emergent**: grown from facts already established (canonical facts, relationship history)
- **Optional**: never blocking the main story

---

#### The familiarity curve

Familiarity is the bridge between "stranger" and "ally with secrets." It moves slowly, which is intentional. A player who asks an NPC one question hasn't earned their backstory. A player who has spoken to them four times, learned their name, and shown warmth toward them — that player has.

```
meeting_count:  1         2         3         4+
familiarity:    "stranger" → "acquaintance" → "familiar" → "confident"
backstory:      none        none            pending       available
sidequest:      locked      locked          available     available
```

Familiarity is not stored as a single number. It is derived at query time from:
- `meeting_count` (engine-tracked on the player→NPC edge)
- `player_attitude` (`affection`, `trust` on the player→NPC edge, updated by `RelationshipStateUpdate`)

This means familiarity can grow quickly through warmth (trust/affection escalating from player's words) even with few encounters — or slowly through cold repeated meetings.

---

### Part II — Technical Architecture

#### NPC as a Character subtype

The existing `CharacterType.NPC` enum value already models incidental characters. What's missing is lifecycle metadata on `Character`:

```
Character (additions needed):
  generation_source: str = "authored"
    # "authored"        — defined in story JSON
    # "llm_hallucinated" — introduced by LLM during gameplay
    # "engine_auto"     — created by engine (e.g. make_player_character)

  backstory_status: str = "none"
    # "none"       — no backstory generated yet
    # "pending"    — trigger conditions met, generation queued
    # "generated"  — backstory exists and is locked as canonical

  introduced_at_minute: Optional[int] = None
    # game minute when first mentioned (set on first add_character call)
```

These fields let the engine:
1. Track the origin of every character (author vs. runtime)
2. Know whether backstory generation has been triggered
3. Avoid re-generating backstory for the same NPC

---

#### When is a hallucinated NPC captured?

The LLM is already constrained by the `previous_scene.speakers` field extracted by `TurnExtractor`. Characters mentioned in the NPC's reply are recorded as speakers. But they're not automatically added to `CharacterGraph` — they're just string keys in the scene buffer.

The capture pipeline should be:
```
1. TurnExtractor extracts previous_scene.speakers (already done)
2. prompt_engine.py: for each speaker key not in character_graph.characters:
     - Create a minimal Character(key=key, character_type=NPC,
         name=infer_name_from_reply(), generation_source="llm_hallucinated",
         introduced_at_minute=current_minute)
     - character_graph.add_character(new_npc)
     - Create player→NPC edge via process_first_meetings (already done)
3. NPC persists for the session in the character_graph
```

The name inference is simple: scan the previous assistant reply for capitalized proper nouns near the key mention.

---

#### Backstory generation trigger

Called after each turn, checked per NPC:

```python
def should_generate_backstory(player_edge: RelationshipEdge, npc: Character) -> bool:
    if npc.backstory_status != "none":
        return False  # already done
    if npc.character_type != CharacterType.NPC:
        return False  # authored chars already have backstory
    meeting_count = player_edge.meeting_count
    familiarity = player_edge.state.affection + player_edge.state.trust
    return meeting_count >= 3 or familiarity >= 0.30
```

When triggered:
1. `npc.backstory_status = "pending"` immediately (prevent re-trigger)
2. A background call is made to generate a minimal NPC backstory (role, motivation, 1 secret, 1 connection to main story)
3. Result is stored as `npc.self_knowledge` entries (same field as canonical characters)
4. `npc.backstory_status = "generated"` — locked, canonical for the session

The backstory generator is given context: the main story scenario, the NPC's key, the player's current relationship state toward them, and any canonical facts already established. This ensures the backstory fits the world.

---

#### Sidequest authorization

A sidequest becomes available for an NPC when:

```python
def sidequest_available(player_edge: RelationshipEdge, npc: Character, game_minute: int) -> bool:
    MIN_TURNS_BEFORE_SIDEQUEST = 10  # no sidequests in opening sequence
    if game_minute < MIN_TURNS_BEFORE_SIDEQUEST:
        return False
    if npc.backstory_status != "generated":
        return False  # must have backstory first
    familiarity = player_edge.state.trust + player_edge.state.affection
    return player_edge.meeting_count >= 3 and familiarity >= 0.20
```

When available, the engine injects a subtle signal into the NPC's system prompt:
```
[SIDEQUEST AVAILABLE]
{npc_name} has a personal matter that could use the player's help. You may
hint at it if the conversation reaches an appropriate opening. Keep it small
and personal to {npc_name}'s backstory. Do not force it — let the player ask.
```

This is authorized hallucination: the LLM knows it's allowed to propose a sidequest. It doesn't do it randomly — it waits for a natural opening. The player can ignore it.

---

#### Where sidequests are stored

A sidequest, once offered and accepted, is stored in `GameState.active_sidequests` (not yet implemented — pending):

```
Sidequest:
  id: str                  # canonical key
  npc_key: str             # which NPC anchors it
  title: str               # brief label ("Help Mia find the missing letter")
  steps: List[str]         # 3-7 high-level steps
  status: str              # "offered" | "active" | "completed" | "abandoned"
  offered_at_minute: int
  completed_at_minute: Optional[int]
```

Sidequest progress is tracked via the existing epistemic/transient knowledge system — each completed step is recorded as a canonical fact (locked, not updatable). The final step completion marks the sidequest as done.

---

#### Relationship between familiarity and main quest pacing

Sidequests compete with main story pacing. A design guardrail:
- No more than 1 active sidequest at a time per NPC
- Sidequests cannot interrupt a main-story "critical path" scene (flagged by author in story JSON as `locked_scene: true`)
- Sidequest content should reference and reinforce main story facts — never contradict them

The author controls the critical path lock. The engine controls sidequest eligibility timing. The LLM controls the moment of offer (within the authorized window).

---

### Implementation Order (recommended)

| Priority | Work item |
|---|---|
| 1 | Add `generation_source`, `backstory_status`, `introduced_at_minute` to `Character` |
| 2 | Capture hallucinated NPCs in `prompt_engine.py` from `previous_scene.speakers` |
| 3 | Implement `should_generate_backstory()` + minimal backstory generator |
| 4 | Implement `sidequest_available()` + prompt injection signal |
| 5 | `GameState.active_sidequests` storage + step tracking |
| 6 | Author `locked_scene` flag on story JSON critical path scenes |

Items 1–2 are prerequisites for everything else. Items 3–6 can be built incrementally.
