# Smarter, self-interested characters: strategy, scheming, intrigue and confession fallout (generic engine)

**Principle (owner, 2026-09-30):** these items improve the *game engine's* characters, so every story gets more real, smarter people. They are not Terrace-only features. Build each as a generic mechanism on the Character / relationship / world-model objects, and let Terrace only configure it in story JSON. Terrace is the first test, not the owner of the code.

From the owner interview of 2026-09-30, written up in [design/TERRACE_HOUSE.md §12](../design/TERRACE_HOUSE.md). Decisions should mix Jev, hard rules and model interpretation, never an LLM alone. Before designing, read [design/SOCIAL_ENGINE.md](../design/SOCIAL_ENGINE.md) and [design/WORLD_MODEL.md](../design/WORLD_MODEL.md). Memory channels (`witnessed`, `told_by`, `overheard`), gossip provenance and rival aims already exist.

## BL-80 — Personality model: goals, goal shifts and strategy behaviour still missing (generic Character object)
- **Open:** built 2026-10-01: four-letter `type` (defaults for sociability, candor, planfulness), `strategy` (scales rival aims), room energy, signal rate, Jev target view (see SOCIAL_ENGINE.md "Personality model"). Still missing: (a) `goal_weights` (love versus career) and the conditions that shift them (competition heats up, a good moment), so a career-first person can fall for someone; (b) behaviour for `scheming` and `safe_pick` (needs BL-81..83); (c) `planfulness` and `candor` are stored and shown to Jev but nothing else consumes them yet (planfulness should affect how reliably someone keeps plans; candor how directly they speak and disclose); (d) three types are designer-assigned (Yuto, Momoka, Masako) and two sourced types rest on 3-4 votes (Arisa, Yuuki Byrnes); re-check if better sources appear.
- **Next:** author `goals` per character with shift rules and wire them into `agenda.refresh_agendas`; consume `planfulness` in promise/plan reliability and `candor` in disclosure and storyteller voice; choose which residents scheme once BL-83 exists.
- **Touches:** `rules/personality.py`, `world_model/agenda.py`, `world_model/commitments`, story JSON, `design/SOCIAL_ENGINE.md`.

## BL-81 — Asynchronous off-screen thinking for any character (generic)
- **Open:** NPC reasoning happens only inside a turn (at most 2 calls), so rivals cannot form plans deeper than one turn allows.
- **Next:** after a turn's bounded decision step, start a background job when a trigger fires (a confession, a betrayal opening, a rival noticing the player's interest). The job writes a plan with concrete, physically executable steps (talk to X, call Y, go to a room, plant a rumor). A finished plan executes unless the player acts first. No telepathy: every step uses a conversation, a call or a location. Needs job persistence across saves and deploys, a cost cap, and determinism in tests.
- **Touches:** `world_model/` (agendas, off-screen resolver), a new job runner, `prompt_engine.py`, `design/WORLD_MODEL.md`.

## BL-82 — Outcomes of high-stakes social acts and their fallout (generic; confession is the first)
- **Open:** `social_acts` `confess` requires the `interested` tier and only gates yes or no. "Still thinking", "I like someone else more", keeping both on the line, rival safe-pick confessions, rare NPC-initiated confessions and failure fallout (gossip, lower value with other residents who heard, rivals emboldened) are not modeled.
- **Next:**
  1. Detect the situation with Jev.
  2. Decide the outcome from personality, standing and competing standings, using rules plus Jev.
  3. Nudge the storyteller context.
  4. Spread the fallout as real events and gossip, following who actually heard.
  5. Tune the pace so a run takes about 60-400 turns from edge growth, not thresholds, and check it with the simulator.
- **Touches:** `social_acts` handling, `world_model/standing.py`, gossip, `scripts/terrace_ollama_sim.py`.

## BL-83 — Characters lie, stage and spy for their own ends: what is left (generic epistemics and movement)
- **Open:** built 2026-10-01: motivated testimony (`world_model/stakes.py`, see SOCIAL_ENGINE.md): people with a stake in someone speak about them in their own interest. Still missing: (a) claims passed on between characters do not carry the speaker's belief and intent (sincere, exaggerated, false, staged), so a lie never persists as a lie in memory or gossip provenance; (b) nobody stages a conversation to be overheard; (c) suspicion of the player never makes a character physically follow or eavesdrop, and the player cannot catch them by walking in.
- **Next:** (a) tag each told claim in `memories` with `intent`; gossip keeps the tag and the engine's truth stays separate; test that a false rumor stays false in the engine. (b) an NPC action `stage_talk(listener, within_earshot_of=player)` using real rooms. (c) a `watch` intention that moves the NPC to an adjoining room for a few turns, with a scene beat when the player enters. Needs BL-81 for planning.
- **Touches:** `world_model/memory.py`, gossip/offscreen, `world_model/agenda.py`, `world_model/movement`, the scene contract.
