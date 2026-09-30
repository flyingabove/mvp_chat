# NPC relationships, schedules and narration-driven movement

## BL-11 — NPC-to-NPC relationship edges are not authored (content)
- **Open:** `six_strangers_story.json` authors only `player->X` edges (`character_graph.get_edge("makoto", "mizuki")` is `None`), so `SocialShiftSignal` has nothing to attach an NPC-to-NPC disposition to (the safe no-op is locked by `test_social_shift_disposition_no_edge_is_safe_noop`).
- **Next:** author NPC-NPC `relationships.edges` for the pairs that matter; no engine change needed.

## BL-06 — NPC-initiated and NPC-to-NPC drift is not driven by the extractor
- **Open:** the turn extractor only accepts player-to-NPC relationship updates. Appraisal and off-screen resolution now drive NPC-side change for Terrace (`world_model/appraisal.py`, `offscreen.py`), but the extractor schema itself and the older social_sim stories (`6_common_room`) are unchanged.
- **Next:** decide whether the extractor should also propose NPC-side deltas or whether the world model fully replaces that path, then apply the same way player-facing deltas are applied.

## BL-08 — No quest, trigger or resource engine
- **Open:** per-character routines, sleep, off-screen life and commitments exist (`engine/world_model/`, declared in story JSON). Quests, flag-gated triggers and resource tracking do not ([design/ROADMAP_NOT_BUILT.md](../design/ROADMAP_NOT_BUILT.md) game design systems and sidequests).

## BL-24 — NPC moves that only appear in narration are not tracked
- **Open:** routines move residents by authored blocks and `state.character_locations` mirrors the world index (`turn.py` `mirror_locations`), with residents in the scene protected from vanishing. Missing: an extractor field for narration-driven NPC moves (`npc_movements` has no hits), and per-NPC last-seen place and time so "where is Yuriko?" answers from what each character knows. No live check with an NPC leaving the room has been run.
