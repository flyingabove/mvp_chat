# Smarter, self-interested characters: strategy, scheming, intrigue and confession fallout (generic engine)

**Principle (owner, 2026-09-30):** these items improve the *game engine's* characters, so every story gets more real, smarter people. They are not Terrace-only features. Build each as a generic mechanism on the Character / relationship / world-model objects, and let Terrace only configure it in story JSON. Terrace is the first test, not the owner of the code.

From the owner interview of 2026-09-30, written up in [design/TERRACE_HOUSE.md §12](../design/TERRACE_HOUSE.md). Decisions should mix Jev, hard rules and model interpretation, never an LLM alone. Before designing, read [design/SOCIAL_ENGINE.md](../design/SOCIAL_ENGINE.md) and [design/WORLD_MODEL.md](../design/WORLD_MODEL.md). Memory channels (`witnessed`, `told_by`, `overheard`), gossip provenance and rival aims already exist.

## BL-80 — Characters get a personality model and a strategy of their own (generic Character object)
- **Open:** characters have likes, dislikes, a voice and a motive, but no personality type and no explicit strategy, so behavior under competition (scheme, move faster, betray, play safe) is not grounded.
- **Next:** research public MBTI estimates for the 17 real cast members (cite sources). Author `personality.mbti`, a `strategy` (schemer, fast mover, patient, safe-pick seeker…), goal weights (love versus career) and the conditions that change them. Add a generic schema plus a validator.
- **Touches:** story JSON characters, story schema/loader, `design/SOCIAL_ENGINE.md`.

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

## BL-83 — Characters lie, stage and spy for their own ends (generic epistemics and movement)
- **Open:** gossip carries its provenance, but speakers don't lie or exaggerate for their own goals. Nobody stages a conversation to be overheard. Suspicion never makes anyone physically follow or eavesdrop on the player.
- **Next:**
  - Each claim a speaker passes on carries the speaker's belief and intent (sincere, exaggerated, false, staged).
  - Suspicion of the player can schedule a real surveillance action: the NPC moves to an adjoining room and listens.
  - The player can find them there by walking in.
  - Overhearing requires the right place and time.
  - Tests: a false rumor stays false in the engine's truth; a watcher is physically present in the scene.
- **Touches:** `world_model/` memory and movement, gossip, the scene contract.
