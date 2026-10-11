---
id: P-10
title: Extraction accepts NPC-to-NPC updates and narration-driven NPC movement
stage: 3
size: M
depends_on: [P-04, P-09]
touches: [backend/app/engine/extractors/turn_extractor.py, backend/app/engine/world_model/turn.py, backend/app/engine/world_model/appraisal.py, backend/app/engine/world_model/world.py]
backlog: BL-86, BL-06 (absorbed), BL-24 (absorbed)
---
**Goal:** a written NPC-only scene must be able to change state, through the same validated writers as player turns.

**Read first:** `documentation/backlog/BL-86-headless-season-simulation.md` (design 1: the extractor must accept NPC-to-NPC updates),
`engine/extractors/turn_extractor.py` (today only player-to-NPC relationship updates; no `npc_movements` field exists),
`world_model/appraisal.py`, `turn.py` (`record_behaviors`, `mirror_locations`), P-09's mind.

**Build**
- Extend the turn extraction schema (still ONE extraction call, Jev-assisted) with: behaviours between NPCs (actor, target, tag
  from the story's closed vocabulary), relationship deltas between NPCs, and `npc_movements` (who went where, grounded in the
  prose). Everything is validated against presence, known places and travel rules before it is applied.
- Apply through the existing writers only: `appraise_behaviors`, `graph.update_edge`, `StandingBook`, the world index. Residents
  in the scene are protected from vanishing. Older social-sim stories (`6_common_room`) get the same path.
- Update the minds (P-09) of everyone who perceived each update.

**Tests first:** an NPC-to-NPC compliment appraised by each witness; a described walk-out moves the NPC and nobody hears the rest of
the conversation; an invented place or absent character is rejected; replay is idempotent. Run the extraction accuracy check the
`user_corrections.md` rules require before relying on it: a labelled set, never tuned against its held-out half.

**Done when:** suite green; BL-86's extractor sentence moves to as-built; BL-24 (narration moves) and BL-06 are fully covered
(both were removed from the backlog when absorbed, so check `design/WORLD_MODEL.md` P7 note and update it).
