Epistemic Harness and Layer Coverage Plan (summary)
==================================================

Status
- Harness: Step supports mode/payload/cached_response; runner handles structured user/system/llm steps and respects narrative toggle; JSON export available via backend/app/integration_playback/exporter.py and scenario_registry.export_scenarios_json.
- Toggles: master + truth/belief/narrative/retrieval implemented in backend/app/config/epistemic_flags.py; state helpers gate mutations.
- Tests: tests/backend/integration/test_epistemic_layers_toggle.py validates layer toggles; scenario_epistemic_iu asserts contested/resolved claims and canonical facts.
- Docs: Layer mapping captured in documentation/model_output_docs/layer_coverage_mapping.md.

Planned stages
1) Harness overhaul
   - Scenario/Step registry with live/cached LLM/extractor step types. (partial: types present; live LLM still gated in playback)
   - JSON export/cache refresh; UI playback consumes the same registry. (done: export_scenarios_json + exporter CLI; UI wiring pending)
   - Extend runner to handle step kinds and cached payloads (no bespoke test-only outputs). (partial: structured steps + cached LLM supported; live calls still blocked)

2) Layer coverage design
   - Map EpistemicStateIUIntegrationTestExample.md segments to the four layers. (done)
   - Document which assertions hit which layer to show necessity. (done)

3) Toggles (master + per-layer)
   - One master switch to disable all epistemic behavior. (done)
   - Four sub-switches to disable each layer independently (truth, belief/observation, narrative log gating, retrieval provenance use). (done)
   - Single-file switch definitions; minimal gating hooks across code. (done)

4) New integration test
   - Uses IU script; passes when layers are on, fails when a layer (or master) is off. (done)
   - Per-layer checks to prove each layer is necessary. (done)

Next steps
- Wire frontend/playback to read exported scenario index; refresh cache during CI or release packaging.
- Add optional live LLM/extractor path outside playback mode if needed.
- Keep layer mapping doc updated when scenario steps or IU script change.
