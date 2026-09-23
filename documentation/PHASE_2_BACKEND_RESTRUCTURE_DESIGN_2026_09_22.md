# Phase 2 — reusable backend: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md` Phase 2, matching the
detail level of the Jev design docs.

**Status: design only. Nothing here is implemented.**

Phase 2 is the plan's own stated prerequisite for Phase 4
(`Phase 2 DecisionProvider → Phase 4 Jev` in the sequencing diagram). The Jev
provider architecture (`JEV_PROVIDER_ARCHITECTURE_2026_09_22.md`) was designed
first and describes a compatible seam, but this document is the one that must
actually exist and be stable before Jev's `resolve()` has anywhere real to plug
into beyond `TurnExtractor` alone.

---

## 1. What exists today, verified

### 1.1 New-game and restore duplicate construction, by design comment admission

`_chat_handler_impl`'s `__cmd_newgame__` branch (`prompt_engine.py:2290`) and
`_try_load_session_from_db` (`prompt_engine.py:1505`) both: call `load_story`,
call `init_state()`, set `story`/`gender`/`player_name`/`instance`, load the
world runtime via `WorldLoader`, and rebuild the character roster from
`StoryDefinition`. The restore path's own docstring says it directly:
*"Rebuild full GameState from saved primitives (mirrors `__cmd_newgame__`
setup)."* Two independent code paths, hand-synchronized by comment, is exactly
the duplication `SessionFactory` exists to remove.

### 1.2 `StoryDefinition` already exists but is not "validated immutable content"

`backend/app/engine/story_loader.py:34` defines `StoryDefinition` as a
dataclass with `id`, `raw`, `title`, `theme`, `instance`, `characters`,
`relationships`. It has a `from_dict` constructor. It has **no validation** —
malformed story JSON produces a `StoryDefinition` with empty/default fields
silently, not a rejection. `build_story_registry()` reparses on every lookup
(confirmed in the earlier engineering-plan measurement: 2.13ms p50 — cheap, and
deliberately not cached per `story_loader.py:180`'s own comment that draft
stories must appear immediately).

### 1.3 `TurnExtractor` already has the shape `DecisionProvider` needs

The Jev design (steps 2–3 of its own implementation order) already specifies
extracting `TurnExtractor`'s HTTP call into `backend/app/llm/providers/`. Phase
2's job is to make that extraction *load-bearing* — i.e. `TurnExtractor` is the
first and, for now, only consumer of the `DecisionProvider` pattern, not a
one-off.

### 1.4 The journal projection now has a shared policy; the roster does not fully share it

Phase 1.4 (shipped) added `player_visible_character_ids()` and
`player_visible_arrival_minute()` to `prompt_engine.py`, and the journal
endpoint uses them. `_cast_roster_payload()` (`prompt_engine.py:468`)
implements an **equivalent but separately-coded** policy (its own
`active_ids()` + `DEPARTED` walk) with a richer active/vacancy/departed shape.
`PlayerView` in this design is the single source of truth both should read from
— not a third implementation.

### 1.5 The 1,256-line handler's actual sections, measured

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

## 2. Package layout

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

## 3. `SessionFactory` + `SnapshotCodec`

### 3.1 Contract

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

### 3.2 `SnapshotCodec`

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

### 3.3 The hard requirement: tested restoration of EXISTING saved games

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

### 3.4 Test plan

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

## 4. `StoryDefinition` validation

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

## 5. `DecisionProvider` / `TextProvider`

These protocols are defined **once**, in `backend/app/llm/`, shared by the Jev
design and by Phase 2's restructuring — this is the literal seam the plan's
sequencing diagram names.

```python
# backend/app/llm/protocols.py

class DecisionProvider(Protocol):
    """Resolves bounded decisions. Jev's DecisionResolver (see
    JEV_PROVIDER_ARCHITECTURE_2026_09_22.md §4) IS a DecisionProvider — this
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

## 6. `PlayerView`

### 6.1 Unifying the roster and journal policies

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

### 6.2 Test plan

| Test | Assertion |
| --- | --- |
| `test_roster_and_journal_agree_on_visible_characters` | for the same `GameState`, the roster's active+departed ids and the journal's visible ids are the same set — this is the ACTUAL bug class Phase 1.4 fixed for the journal alone; this test guards the roster from regressing the same way independently |
| `test_playerview_build_matches_existing_roster_endpoint_output` | characterization test: real six_strangers session, `_cast_roster_payload(state)` output == `PlayerView.build(state)` formatted the same way |
| `test_playerview_build_matches_existing_journal_endpoint_output` | same, against Phase 1.4's journal tests in `test_user_sessions.py` |
| all four Phase 1.4 regression tests (`test_journal_hides_upcoming_character_goal_history`, etc.) | re-run unmodified against the new `PlayerView` path — must still pass |

---

## 7. `TurnService` and command dispatch

### 7.1 `TurnService` formalizes Phase 1.1

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

### 7.2 Command dispatch

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

### 7.3 Test plan

| Test | Assertion |
| --- | --- |
| `test_command_dispatch_order_preserved` | construct a message matching two commands' naive patterns; assert the table returns the SAME one today's if-chain would (regression guard for reordering during extraction) |
| `test_every_existing_command_still_produces_identical_response` | for each of the ~10 existing commands (`[CAST]`, `[T]`, `[ES]`, `__cmd_reset__`, `__cmd_skip__:*`, map, etc.), same input -> byte-identical response dict, before and after extraction |
| `test_turn_service_failure_kind_validation` | retrieval error -> `failure_kind == "validation"` (today: `{"error": "knowledge retrieval failed"}`) |
| `test_turn_service_failure_kind_provider` | storyteller 503 -> `failure_kind == "provider"` |
| `test_turn_service_failure_kind_persistence` | DB write raises after a successful storyteller call -> `failure_kind == "persistence"`, reply still returned to the player (today's behavior: `logger.exception(...)`, turn is NOT lost to the player even though the DB write failed — this nuance must be preserved, not "fixed" into a harder failure) |
| Phase 1.1's 5 existing tests | re-run unmodified against `TurnService.run_turn` |

---

## 8. Migration order (mechanical extraction, one seam at a time)

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

## 9. Exit criteria (unchanged from the plan, restated precisely)

- Existing endpoints and saved games behave identically — verified by §3.3's
  ten-real-blob test and §6.2/§7.3's characterization tests, not by inspection.
- Deterministic tests pass for both genres and a full cast rotation — the
  existing six_strangers cast-rotation tests (Phase 1's shipped work) must pass
  unmodified through `TurnService`.
- An import-direction test proves `engine/` imports no API, HTTP, or storage
  module — this closes the gap `JEV_PROVIDER_ARCHITECTURE_2026_09_22.md` §2
  found: the test does not exist yet; it ships in step 6 above.

## 10. What this design deliberately does not do

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
