# BL-40 — Make Bond the persisted owner of feelings (graph becomes a facade)

- **Type:** tech-debt
- **Found:** 2026-09-29, BL-39 phase G implementation
- **Severity:** low: storage-only; feelings already have exactly one writer.

## Problem
BL-39 section 8 plans one tested cutover where `world_model/heart.py::Bond` becomes the persisted owner of feelings and `engine/character_graph.py::CharacterGraph` forwards reads/commands to it. Today (phases B–G) `Bond.feelings` IS the graph's `RelationshipEdge.state` object, `CharacterGraph` is still what `_serialize_state` saves, and every feeling change goes through `CharacterGraph.update_edge` (appraisal, off-screen `GraphRelationships.adjust`, extractor deltas). So there is one writer and one stored copy, but the owner is still the graph.

## Fix direction
Move serialization of directional feelings into the character aggregate, make `CharacterGraph.get_edge/update_edge` read and write through `Cast`/`Heart`, and remove the graph's separate feelings serialization in the same commit. Required first: the BL-39 section 8 old-save migration drill (isolated old saves with pending agreements, relationship edges, standings; migrate, round-trip, crash/retry, rollback routing), O17/O28 evidence.

## Why deferred / cautions
No player-facing effect and real old-save risk: every saved Terrace/IU session carries graph edges. Do it only with the migration drill and version routing; never dual-write.

## Touches
`backend/app/engine/character_graph.py`, `backend/app/engine/world_model/heart.py`, `person.py`, `api/prompt_engine.py` (`_serialize_state`, `_try_load_session_from_db`), migration tests.
