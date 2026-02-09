Layer Coverage Mapping (IU scenario)
====================================

Goal: show which narrative segments exercise each epistemic layer and how tests assert necessity.

Sources
- Narrative source: documentation/human_north_star_docs/epistemic_state/EpistemicStateIUIntegrationTestExample.md
- Harness scenario: backend/app/integration_playback/scenarios/scenario_epistemic_iu.py
- Toggle test: tests/backend/integration/test_epistemic_layers_toggle.py

Layer→Segment mapping
- Truth: Round 4 confessions and knife disposal (Steve/Bob) become canonical facts; asserted in scenario validation.
- Belief: Round 1 denials, Round 3 contradictions, and Round 4 confessions populate epistemic_log and per-character beliefs; assertions ensure claims exist and contested/resolved counts behave.
- Narrative: Playback emission of chat-style steps across rounds; suppression verified by toggling narrative flag in integration test.
- Retrieval: Observation snippets (neighbor, CCTV) and formatted memory block in toggle test ensure retrieval/text blocks stay present when enabled.

Test alignment
- scenario_epistemic_iu asserts contested/resolved claims, canonical facts, and observations are present (truth/belief coverage).
- test_epistemic_layers_toggle flips master and per-layer switches; expects failures when any layer is off and passes when all are on (truth/belief/narrative/retrieval coverage).

Next doc tasks
- Keep this mapping updated when scenario steps or IU script segments change.
- Add UI/export references once playback JSON export is consumed by frontend.
