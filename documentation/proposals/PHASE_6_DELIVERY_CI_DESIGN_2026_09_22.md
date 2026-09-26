# Phase 6 — delivery and documentation: implementation design

September 22, 2026. Implementation-level design for
`ENGINEERING_PLAN_REUSE_PERFORMANCE_JEV_2026_09_21.md` Phase 6.

**Status: design only. Nothing here is implemented.**

---

## 1. Runtime version alignment

### Current state, verified
`Dockerfile:1` — `FROM python:3.10-slim`.
`.github/workflows/tests.yml:18,39` — `python-version: "3.11"` (both jobs).

### Design
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

### Test plan
| Test | Assertion |
| --- | --- |
| `test_docker_build_succeeds_on_3_11` | CI step: `docker build .` completes, including the existing build-time pytest gate (`RUN ... pytest /srv/tests`) |
| existing full suite | passes inside the built image, not just in CI's bare Python 3.11 job — this is the "same tested artifact reaches beta" exit criterion, checked at build time, not assumed from CI parity |

---

## 2. Dockerfile layer ordering

### Current state, verified
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

### Design
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

### Measurement
Build the image twice: once changing only a frontend file, once changing only
`requirements.txt`. **Ship criterion:** the frontend-only change's build
reuses the cached pip-install layer (visible in `docker build` output as
`CACHED`); the requirements-only change's build does not.

### Test plan
| Test | Assertion |
| --- | --- |
| `test_frontend_only_change_reuses_dependency_layer` | CI or manual: two builds, second reuses the pip-install layer per Docker's own cache-hit reporting |
| existing build-time pytest gate | still runs, still fails the build on a real test failure (unchanged behavior, reordered layers only) |

---

## 3. Dependency set separation + lock

### Current state, verified
`backend/requirements.txt`: **34 lines**, all pinned with `==`, but runtime
(`fastapi`, `httpx`, `torch`, `sentence-transformers`, `faiss-cpu`, ...),
build-time (nothing currently separate — `torch`/`sentence-transformers` are
both build-time-needed for embedding and runtime-needed for retrieval, so the
split is genuinely blurred today), and test-only (`pytest`, `pytest-asyncio` —
notably **not even in this file**; CI's own `pip install pytest
pytest-asyncio` step installs them separately, meaning the test-runner
versions aren't pinned at all and could silently drift between CI and a local
dev environment).

### Design

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

### Test plan
| Test | Assertion |
| --- | --- |
| `test_ci_uses_pinned_test_dependencies` | CI workflow YAML installs from `requirements-test.txt`, not an ad hoc `pip install` line |
| `test_lock_file_matches_current_environment` | CI step: `pip freeze` diffed against `requirements.lock.txt` — mismatch fails CI with a clear "regenerate the lock file" message, catching silent drift before it reaches a deploy |

---

## 4. Recovery off the readiness-critical path

### Current state, verified
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

### Design

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

### Measurement
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

### Test plan
| Test | Assertion |
| --- | --- |
| `test_recovery_sweep_does_not_block_readiness` | `lifespan()`'s pre-yield phase completes without awaiting `_fact_extraction_recovery_sweep`; a probe confirms the app is "ready" while the sweep task is still running (same technique as Phase 1.3's `test_startup_warm_up_does_not_block_the_event_loop`) |
| Phase 1.2's existing recovery-sweep tests | re-run unmodified — the sweep's own correctness is untouched, only its await point moved |
| `test_fingerprint_unchanged_skips_rebuild` | two calls to `main()` with no content change → second is a no-op, verified via a call-count spy on `_do_build` |
| `test_fingerprint_changes_on_content_edit` | modifying a story JSON's mtime/size changes the fingerprint → rebuild runs |
| `test_fingerprint_persists_across_restart` | fingerprint marker survives a simulated restart (same directory reused) |

---

## 5. CI frontend checks

### Current state, verified
`tests/frontend/*.test.cjs` (Node, no browser) and
`tests/frontend/test_*.py` (Python-driven, presumably Playwright-based per
CLAUDE.md §9's browser-automation references) both exist as **files** but
`.github/workflows/tests.yml` runs only `pytest tests/ -v
--ignore=tests/backend/integration/` — which **does** collect and run the
Python frontend tests (they're under `tests/`, not excluded), but does **not**
run the `.test.cjs` Node tests at all (no `node` or `npm test` step in the
workflow).

### Design
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

The real Playwright-driven browser checks CLAUDE.md §9 requires (desktop
Chromium + iPhone-sized WebKit against a running dev server or live beta) are
a **manual/agent-invoked verification step** in this project's workflow
(`ship-and-verify`'s skill doc, the Playwright MCP plugin), not a `pytest`-
collected test suite — so there is nothing of that kind to add to CI here.
That verification stays where the project already puts it: local pre-commit
and post-deploy, per `ship-and-verify`, not this row.

### Test plan
| Test | Assertion |
| --- | --- |
| new `frontend-node-tests` CI job | fails the workflow if any `.test.cjs` file's process exits nonzero |

---

## 6. Documentation updates

Per the plan's own list, each doc gets a specific addition, not a rewrite:

| Doc | Addition |
| --- | --- |
| `INFRASTRUCTURE.md` | Phase 0A's empirical finding (Railway serves both environments; cPanel path confirmed dead) + LangSmith/TypeSafe env var names (not values) |
| `AI_FATAL_MISTAKES.md` | 0A.4's decision record: webhook secret in git history, rotation via BL-14, history-rewrite explicitly rejected and why |
| `DATA_MODEL_INVENTORY.md` | `extracted_chunks` table (Phase 1.2) and the `Snapshot`/`SnapshotCodec` versioned envelope (Phase 2, if implemented) |
| `MESSAGE_TO_PROMPT_FLOW_TRACE.md` | `TurnService`/command dispatch (Phase 2, if implemented) — and the stable-prefix layer reordering (Phase 3 row 10, if shipped), since that doc is the authority on layer order |
| `AUTH_AND_PERSISTENCE_DESIGN.md` | Phase 1.5's exact-eviction fix and the per-session lock coordination |
| `BACKLOG.md` | close BL-01c (already done, 2026-09-22); reconcile BL-13 per its own re-audit instruction; add BL-16 (already done) |

**This row ships alongside whichever phase actually lands the corresponding
code** — not as a batch at the end. A doc update for work that hasn't shipped
yet would itself violate the project's own doc-truthfulness norms
(`AI_DOC_INDEX_CATALOGUE.md`'s entire purpose). Listed here for completeness
of Phase 6's scope, not as deferred work to batch later.

---

## 7. Sequencing within Phase 6

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

## 8. Exit criteria (unchanged from the plan, restated precisely)

- The same tested artifact reaches beta — verified by row 1's build-time
  pytest gate running inside the aligned-version image, not just in CI
  outside it.
- Content, asset, and build identities agree — the asset manifest (Phase 5
  §5) and the index fingerprint (row 4b) are the two concrete mechanisms that
  make "identity" a checkable fact rather than an assumption.
- Production release remains separately requested — unchanged; nothing in
  this phase touches the beta→prod approval gate in CLAUDE.md §8.
