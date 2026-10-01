# NPC-to-NPC edges and the quest/trigger engine

NPC-side drift (formerly BL-06) and narration-driven movement plus last-seen places (formerly BL-24) moved into
BL-86 (extraction of NPC scenes) and BL-85 (each character's mind).

## BL-11 — NPC-to-NPC relationship edges are not authored (content)
- **Open:** `six_strangers_story.json` authors only `player->X` edges (`character_graph.get_edge("makoto", "mizuki")` is `None`), so `SocialShiftSignal` has nothing to attach an NPC-to-NPC disposition to (the safe no-op is locked by `test_social_shift_disposition_no_edge_is_safe_noop`).
- **Next:** author NPC-NPC `relationships.edges` for the pairs that matter; no engine change needed.

## BL-08 — No quest, trigger or resource engine
- **Open:** per-character routines, sleep, off-screen life and commitments exist (`engine/world_model/`, declared in story JSON). Quests, flag-gated triggers and resource tracking do not ([design/ROADMAP_NOT_BUILT.md](../design/ROADMAP_NOT_BUILT.md) game design systems and sidequests).
