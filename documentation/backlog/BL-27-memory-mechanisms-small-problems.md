# Memory and knowledge mechanisms: small problems

## BL-27 — Memory and knowledge mechanisms: small problems
Fix one row at a time; delete a row when fixed; delete the entry when empty. Rows 2, 4, 10, 11, 12 and 15 change what the model sees (need the hosted arena gate); 3, 5, 6, 7, 8 are refactors touching the save format (keep old saves loading). No house or event log.
1. Static index (`retrieve.py` to `RETRIEVED_MEMORY`): chunks carry no `known_by`; one bundle per story (main character only).
2. Canonical facts (`prompt_builder.py` "others" group, ~L441-492): the focal NPC's prompt includes "Known by others — the focal character does not know this", a leak; visibility matching uses exact text.
3. `canonical_truth`: a `List[str]` duplicate of the canonical facts, used only in truth mode; derive it.
4. `BeliefState`: only the main character's beliefs are written and read; unbounded; the `[:10]` slice cuts claims.
5. `epistemic_log`: duplicates beliefs; only a playback scenario reads it; not persisted.
6. `observation_log`: dead; only `belief_seeds` write it, nothing reads it, yet it is persisted.
7. `transient_entries`: `id`/`scope`/`meta` ignored; only the debug panel reads them.
8. Room presence stored as marker strings in `transient_entries` and parsed back; needs a typed field.
9. `SceneKnowledge` (`state.scene_knowledge_entries`): an 8-item queue overwritten three times per turn.
10. `SessionChunkStore`: unbounded, no speaker or visibility tag (player claims become facts), lossy persistence, DB copy never read back.
11. Jev selection (`dynamic_context.py`): `_eligible` is a no-op (no `not_known_by`); on an exception up to 200 candidates reach the prompt unselected.
12. Conversation log: only the last 6 messages are sent (`MEMORY_TURNS`); nothing summarizes older turns (design work).
13. Graph edges: `edge.narrative` is never written during play. (The unread `disposition` and non-main characters' attitudes reaching the prompt moved to BL-85 stances.)
14. `recent_behavior_log`: part of its output is never read (see 13).
15. `Character.tells`: loaded from the story, never put into the prompt (render it or remove the field; Terrace uses `world_model/deception.py` instead).
- **Touches:** `state.py`, `prompt_builder.py`, `character_graph.py`, `prompt_engine.py`, `knowledge/runtime/{retrieve,dynamic_context,session_chunk_store}.py`.
