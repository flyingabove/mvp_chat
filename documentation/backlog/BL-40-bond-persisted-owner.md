# Make Bond the persisted owner of feelings

## BL-40 — Make Bond the persisted owner of feelings
- **Bucket:** C (engine)
- **Open:** `Bond.feelings` is the graph's `RelationshipEdge.state`, `CharacterGraph` is still what `_serialize_state` saves, and every change goes through `CharacterGraph.update_edge`: one writer, one stored copy, owner still the graph. Storage-only, no player-facing effect.
- **Next:** move directional-feeling serialization into the character aggregate and make the graph forward to `Cast`/`Heart`, removing the separate serialization in the same commit; only after the old-save migration drill (isolated old saves with pending agreements, edges, standings; round-trip, crash/retry, rollback routing). Never dual-write.
- **Touches:** `character_graph.py`, `world_model/heart.py`, `person.py`, `prompt_engine.py` (`_serialize_state`, `_try_load_session_from_db`).
