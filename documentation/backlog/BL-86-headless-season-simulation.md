# Headless season simulation and admin watch mode (generic engine proof)

Owner vision, 2026-10-01. Run a whole game with no human player: character objects (BL-85) move between real
locations, pursue their goals and meet each other. The LLM writes every scene, and the result is judged as drama
(BL-87). Terrace House is the first season. The runner is generic and works for any story.

## BL-86 — Headless season runner, admin watch mode, provider switch
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
    `LLM_PROVIDER`. A switch turns the Ollama path off, and it is off for now.
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
  1. **`SeasonRunner(story, seed, provider, days, budget)`**, pure orchestration over existing services:
     - the world stepper advances time;
     - each person's plan picks where to go;
     - co-located awake people form an encounter;
     - `Scene` (BL-85) builds the prompt;
     - one writing call;
     - extraction plus Jev;
     - the commit goes through the existing single writers.

     The same turn transaction as player turns: one code path, not a second engine. **The extractor therefore must
     accept NPC-to-NPC updates** (absorbs BL-06 and BL-24):
     - relationship and behaviour changes between NPCs, not only player-to-NPC;
     - NPC movements described in the prose (a new `npc_movements` field; it does not exist yet).

     Both apply through the same validated writers. The older social-sim story `6_common_room` gets this path too. A per-day cap on scenes, and a
     hard cost cap per run.
  2. **The camera.** Not every encounter is equally interesting. Rank encounters by scene tension (BL-85 dynamics)
     and write the top N per day in full. The rest are summarized in one line by the same writing call, so the
     story still advances everywhere. N is a knob (BL-87).
  3. **Season artifacts:** per-day scenes, state diffs, plans, mind changes, and the rubric scores (BL-87), written
     as JSONL plus a readable HTML episode view.
  4. **Admin watch mode.** An admin-only screen, behind the existing operator auth, to start or stop a season and
     to read it as episodes (day by day, scene by scene). It can also show any character's mind (what they know and
     what they think others know) and stance graph. It is never shown to players.
  5. **Integration test.** `pytest -m integration` runs a short Terrace season (for example 5 days, capped). It
    asserts:
     - structural invariants: always 6 residents, no telepathy, consent rules, no story names in engine code;
     - a minimum rubric score (BL-87).

     It also checks the rival evidence absorbed from BL-34: over several story days the season report must show
     rivals visibly competing (counter-invitations, competing plans, a rival seeking out the courted person), and
     absence is reported as absence. It is never run on deploy. Separately, the unit gate runs a scripted fake writer, so the runner's plumbing is
     tested offline.
- **Next:**
  - The provider switch (`SIM_OLLAMA_ENABLED=false`, with the arena's local Ollama path respecting it), with a test.
  - `SeasonRunner` on the fake writer (unit tests), then on Gemini + Jev for a 2-day pilot season, then the camera,
    the artifacts and the watch mode.
  - Depends on BL-85 P1–P4 for rich prompts. A first version can run on today's prompt builder.
- **Touches:** new `backend/app/sim/{runner,camera,artifacts}.py`, the operator routes (`api/debug_engine.py`
  pattern), `frontend/debug.html` (watch view), `world_model/offscreen.py` (replaced by written scenes),
  `scripts/terrace_ollama_sim.py` (switch), `backend/app/config/settings.py`, `tests/backend/integration/`.
