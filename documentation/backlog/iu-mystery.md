# IU mystery: named NPCs, evidence, records

## BL-31 — Named NPC dialogue can be "Unknown voice" with empty presence (IU)
- **Open:** IU turns 9-12 on `67d9c4d`: narration introduced receptionist Jisoo and manager Yoo Min-ho in the EDAM lobby, every dialogue segment had `speaker_id: null` ("Unknown voice") and `people_present` was empty. Terrace speaker attribution is fine in current play; the IU mismatch and less explicit speaker mixing were never re-verified hosted.
- **Next:** an IU regression (reception to manager arrival) checking names, ids and presence across turns; an explicit policy for incidental named NPCs. Never populate presence by trusting model-generated names.
- **Touches:** `dialogue.py`, `world_model/speakers.py`, scene/presence in `prompt_engine.py`, IU locations.

## BL-36 — IU needs sourced evidence and unresolved contradictions
- **Open:** testimony, observation and corroboration merge. A partial post-generation repair rejects "the player told X" claims unless that NPC actually heard it, and reinspection no longer counts as a fresh discovery. Still unresolved: invented testimony provenance (paraphrase and reported speech), a player-visible evidence journal with source, speaker, time, confidence and conflict status, independent confirmation, third-person self-reference of the present player. A suspect's shifting answer must remain possible, not be "corrected" into honesty.
- **Touches:** `world_model/evidence.py`, `events.py`, `memory.py`, IU leads, journal route, tests. Needs BL-30/31.

## BL-41 — IU leads unlock records and interviews that do not exist
- **Open:** `1_iu_murder_mystery` `leads[].unlocks` names `manager_interview`, `sojin_schedule`, `aster_meeting`, `han_pressure_call`, `driver_log` with no entity, record or interview behind them (only `closet_scuff` and `cctv_side_entrance` are executable); `tests/backend/app/engine/test_leads_content.py::KNOWN_UNAUTHORED` pins the list.
- **Next:** owner authors each record (holder, access, what it truthfully shows); engine gets a generic `RecordSource` capability and a persistent `InvestigationTask` requested through the existing extraction call; missing records resolve honestly as unavailable; remove each id from `KNOWN_UNAUTHORED` as authored. The engine must never invent footage or logs.
