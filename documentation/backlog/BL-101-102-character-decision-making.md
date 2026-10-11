# Character decision-making: what the engine still ignores (generic engine)

Found in the 2026-10-11 review after P-08. Related plan
work: P-09 (the mind), P-11 (scene wants, which replaces `next_beat`), P-14 (delayed answers), P-15 (multi-step plans).

## BL-101 — Who speaks ignores goals and stakes
- **Bucket:** C (engine)
- **Open:** `speakers.select_speakers` now reads the speaker's stances (rival, protective_of, resents, distrusts), but not a person's goals: someone with a heavy goal (P-07) about the topic gets no push to speak or to pursue it.
- **Next:** add a goal-weight term about the topic, bounded like `STANCE_CAP` (1.5), once P-07 goals expose a per-topic weight; test with fixed seeds.
- **Touches:** `world_model/speakers.py`, `tests/backend/app/engine/world_model/test_speakers.py`.

## BL-102 — A character's choices cannot be explained or tuned
- **Bucket:** C (engine)
- **Open:** stances record their causes, but the choices built on them (which beat fired, who was picked to speak and why, why a rival aim was seeded) leave no trace. `next_beat` picks "waited longest, then priority" and the Theatre cannot show why a resident did a thing, so tuning drama (BL-87) is blind.
- **Next:** a bounded per-turn `decisions` list on the model (kind, character, chosen option, runner-up, the stance and goal ids that scored it), cleared each turn, shown only in the operator Theatre and debug views (never to players, per the no-house-log rule). Test that removing a cause changes the entry.
- **Touches:** `world_model/model.py`, `agenda.py`, `speakers.py`, `sim/theatre.py`, `frontend/drama.html`.
