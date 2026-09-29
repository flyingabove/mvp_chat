# BL-41 — IU leads unlock records and interviews that do not exist yet

- **Type:** owner action + follow-up
- **Found:** 2026-09-29, BL-39 phase J (O05 investigation stalls)
- **Severity:** medium: the mystery promises leads the player cannot act on.

## Problem
`backend/app/stories/1_iu_murder_mystery/iu_murder_mystery_story.json` `leads[].unlocks` names `manager_interview`, `sojin_schedule`, `aster_meeting`, `han_pressure_call` and `driver_log`, but no entity, record or interview with those ids exists. Only `closet_scuff` and `cctv_side_entrance` are executable (inspectable `world_model.entities`). `tests/backend/app/engine/test_leads_content.py::KNOWN_UNAUTHORED` pins this list so it cannot grow silently.

## Fix direction
1. Owner authors what each record/interview actually contains (who holds it, access policy, what it truthfully shows, retention). The engine must never invent footage or logs (BL-39 section 6).
2. Engine: a generic `RecordSource` entity capability (access policy, coverage, delay) and `InvestigationTask` (pending / denied / completed, survives reload), requested through a typed extraction field in the existing call; results become observations with sources; missing records resolve honestly as unavailable.
3. Remove each id from `KNOWN_UNAUTHORED` as it is authored. Acceptance: BL-39 O05/O06.

## Why deferred / cautions
Content is mystery-solution truth and must come from the owner. Building the mechanism without content would be dead code.

## Touches
IU story JSON, `backend/app/engine/world_model/evidence.py`/`entities.py`, turn extractor, `world_model/turn.py`, tests.
