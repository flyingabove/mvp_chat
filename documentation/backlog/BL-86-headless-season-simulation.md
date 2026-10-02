# Headless season simulation and admin watch mode (generic engine proof)

Owner vision, 2026-10-01. Run a whole game with no human player: character objects (BL-85) move between real
locations, pursue their goals and meet each other. The LLM writes every scene, and the result is judged as drama
(BL-87). Terrace House is the first season. The runner is generic and works for any story.

## BL-86 — Headless season runner and admin watch mode
- **Open:**
  - Nothing can run a story without a player. `scripts/terrace_ollama_sim.py` drives a scripted player against
    local Ollama only.
  - NPC-to-NPC encounters off-screen are resolved by a weighted dice roll (`world_model/offscreen.py`) and never
    written.
  - There is no admin view of a running world.
- **Owner decisions (2026-10-01):**
  - **Purpose.** Two uses: an integration test, and a watch mode for admins. It is never a player-facing house or
    event log; a developer or admin season report is allowed.
  - **Providers.** Gemini + Jev is the default and OpenAI + Jev the alternative, through the existing
    `LLM_PROVIDER`. The Ollama path is off by default behind `OLLAMA_ENABLED` (built: `backend/app/llm/ollama_switch.py`, `design/PLATFORM.md`).
  - **Every scene is written.** Each encounter of two or more characters in a location becomes one LLM-written
    scene, prompted from the people's parts and the scene dynamics. Extraction (Jev-assisted) writes the
    consequences back to state. Interruptions (someone walks in) are written realistically.
  - **Fog of war.** Characters move by their goals, plans and routines, and know only what they perceived or were
    told (BL-85 mind). They search, miss each other, and act on stale beliefs.
  - **Cast rules are data.** Terrace always holds exactly 6 residents. When a couple leaves, or someone storms out,
    a replacement arrives through the existing cast lifecycle; never more than 6. Other stories may have more,
    with rotation in and out.
  - **The player slot.** It is held by an AI resident with goals, under the same `Person` rules. The panel speaks
    only at the end of that resident's run (win or cut).
- **Design:**
  1. **Built (P-04): `SeasonRunner(story, seed, writer, days, scenes_per_day, budget)`** in `backend/app/sim/runner.py`,
     pure orchestration over existing services: the world stepper (`world_model/stepper.py`) advances time and drives
     every character's routine, including the player slot (an AI resident is just another routine-follower, no code
     assumes a human); co-located awake pairs form an encounter with `offscreen.find_encounters()`'s pairing rule; a
     `Writer` (`backend/app/sim/writer.py`, protocol `write_scene`/`extract`) is asked for the scene; the extracted
     `SceneUpdate` (summary, relationship deltas, movements) commits through the model's own primitives
     (`world.add_event`, `epistemics.observe_event`, `memories.add`, relationship `adjust()`) -- one code path, not a
     second engine. A delta or movement naming someone who was not in the scene is rejected, not applied (grounding
     check). Hard caps: `scenes_per_day` per day, `budget` on total writer calls, checked before each scene so a run
     never stops mid-write. Three pure invariants (`backend/app/sim/invariants.py`) run after every simulated day:
     exact cast size via the cast lifecycle, no memory without a matching epistemic observation, no
     `<act>_accepted` event without a logged consent verdict. Proven on a deterministic `FakeWriter` (unit tests,
     `tests/backend/app/sim/`); the real writer, the camera, the social-act proposal path from a scene, group (3+)
     encounters, and `npc_movements` parsed from LLM prose are later work (P-06 onward) -- this slice only proves the
     day-loop, commit and invariant plumbing offline.
  2. **Still open:** extraction must accept richer NPC-to-NPC updates once a real writer lands (absorbs BL-06 and
     BL-24): relationship and behaviour changes between NPCs beyond a simple delta, and NPC movements described in
     prose rather than returned structurally. The older social-sim story `6_common_room` gets this path too.
  3. **The camera.** Not every encounter is equally interesting. Rank encounters by scene tension (BL-85 dynamics)
     and write the top N per day in full. The rest are summarized in one line by the same writing call, so the
     story still advances everywhere. N is a knob (BL-87).
  4. **Season artifacts:** per-day scenes, state diffs, plans, mind changes, and the rubric scores (BL-87), written
     as JSONL plus a readable HTML episode view.
  5. **Admin watch mode.** An admin-only screen, behind the existing operator auth, to start or stop a season and
     to read it as episodes (day by day, scene by scene). It can also show any character's mind (what they know and
     what they think others know) and stance graph. It is never shown to players.
  6. **Integration test.** `pytest -m integration` runs a short Terrace season (for example 5 days, capped). It
    asserts:
     - structural invariants: always 6 residents, no telepathy, consent rules, no story names in engine code;
     - a minimum rubric score (BL-87).

     It also checks the rival evidence absorbed from BL-34: over several story days the season report must show
     rivals visibly competing (counter-invitations, competing plans, a rival seeking out the courted person), and
     absence is reported as absence. It is never run on deploy. Separately, the unit gate runs a scripted fake writer, so the runner's plumbing is
     tested offline.
- **Next:**
  - The real writer (`backend/app/sim/llm_writer.py`), the authored-story loader and `scripts/run_season.py` are built
    (P-06) and the baseline is recorded in `design/SOCIAL_ENGINE.md` ("Season baseline"). Next: the camera, the
    HTML episode view and the admin watch mode; scenes still cannot build on earlier ones (every scene ends on the same
    quiet-touch beat) and feeling changes land in an in-memory table, not the character graph (P-10).
  - Depends on BL-85 P1–P4 for rich prompts. A first version can run on today's prompt builder.
  - A thin, operator-only debug viewer for the `FakeWriter` season already exists at `/beta/debug` ("Season Sim"
    tab): `backend/app/api/season_debug.py` (`POST /beta/debug/season/run`, `GET /beta/debug/season/fixtures`),
    `backend/app/sim/fixtures.py` (the fixture, moved out of `tests/` so production code can build it), and a
    `SceneRecord` field on `DayReport` (`backend/app/sim/runner.py`) that keeps each scene's real encounter/update
    instead of discarding it. It only runs the fixed Terrace fixture on `FakeWriter` and renders the real
    day-by-day log (scenes, deltas, movements, rejections, invariant results) — no real writer, no camera ranking,
    no persisted artifacts. This is scoped narrowly on purpose and is not item 5 ("Admin watch mode") above:
    whoever picks up the camera/artifacts/watch-mode work should treat it as a starting reference, not something to
    extend in place without reconsidering scope.
- **Touches:** new `backend/app/sim/{runner,camera,artifacts}.py`, the operator routes (`api/debug_engine.py`
  pattern), `frontend/debug.html` (watch view), `world_model/offscreen.py` (replaced by written scenes),
  `scripts/terrace_ollama_sim.py` (switch), `backend/app/config/settings.py`, `tests/backend/integration/`.
