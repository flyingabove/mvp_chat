# Arena: judge calibration, length bias, server receipts

## BL-19 — Arena Phase 2: server receipts, controlled init, snapshots, response forks
- **Open:** the arena is observational (public `/api/chat` plus the `[D]` box). Not built: per-turn server receipts (applied events, pre/post state hashes, component versions), seeded initialization, snapshot export/restore, the identical-state response-fork track. Checks needing them (`cast_capacity`, `rng_stream_parity`, `state_transition_legality`, `snapshot_round_trip`) report "not measured". Belongs with the `SessionFactory`/`SnapshotCodec`/`TurnService` restructure ([design/ROADMAP_NOT_BUILT.md](../design/ROADMAP_NOT_BUILT.md) Phase 2); prod needs them deployed for controlled hosted parity (an explicit release decision).
- **Touches:** `api/prompt_engine.py`, `api/eval_capabilities.py`, `.claude/skills/promote-to-prod/arena/`.

## BL-20 — Arena judge needs human calibration (owner action)
- **Open:** rubric weights, the episode margin (0.55) and the critical-probe threshold (0.5) are proposals; agreement with human judgment is unmeasured, so every report says "uncalibrated: advisory only". Needs about 200 human-labeled pairs (two labelers on ambiguous cases, adjudicated).
- **Next:** label from real arena artifacts (`arena/calibration.py` `HUMAN_LABEL_FIELDS`, JSONL), add an agreement report, freeze weights and thresholds, bump `calibration_version`.

## BL-23 — Arena judge (Jev) prefers longer replies
- **Open:** the `shorten` control lost to the longer original in 3 of 3 resolved cases despite instructions; reports carry a per-game "longer side won" table.
- **Next, in order:** length-matched evidence (clip both arms to the shorter side per turn, disclosed in the packet); a length covariate in aggregation; human labels (BL-20). Then re-run the Six Strangers comparison (BL-22).
- **Touches:** `arena/evidence.py`, `aggregate.py`, `calibration.py`.
