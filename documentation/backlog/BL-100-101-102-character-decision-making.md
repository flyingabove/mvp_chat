# Character decision-making: what the engine still ignores (generic engine)

Found in the 2026-10-11 review after P-08: stances exist for ten kinds, but only `crush` changes anything a character does
(`agenda.refresh_agendas`, `rival_move.py`); the rest only print on the person's card (`turn._stance_note`). Related plan
work: P-09 (the mind), P-11 (scene wants, which replaces `next_beat`), P-14 (delayed answers), P-15 (multi-step plans).

## BL-100 — Stances other than `crush` do not drive any decision
- **Bucket:** C (engine)
- **Open:** `resents`, `protective_of`, `distrusts`, `suspects`, `owes`, `ex`, `admires`, `ally` are derived each turn (`rules/stance_defaults.json`) and shown on the card, but no intention, beat, speaker or verdict reads them. The only intention kinds are `pursue`, `compete_for` and `test_loyalty` (`world_model/agenda.py`), so a character who resents or distrusts someone never avoids, confronts or snubs them, and a protective one never steps in.
- **Next:** derive intentions from stances the way `crush` does, as data: `resents` gives `confront`/`snub`, `protective_of` gives `defend`, `owes` gives `repay`, `ex` gives `avoid`, `distrusts` gives `withhold` (the character shares less with them). Add each beat's `BEAT_TEXT`, keep the one-move-a-day cap, scale by a new intensity family. A test per kind; the golden record changes only where those stances exist. Needs an arena gate (behaviour change). Subsumed later by P-11 wants; do it first only as the cheapest visible step.
- **Touches:** `world_model/agenda.py`, `turn.py` (`BEAT_TEXT`), `rules/stance_defaults.json`, `rules/tracks.py` (intensity), tests.

## BL-101 — Who speaks ignores stances, goals and stakes
- **Bucket:** C (engine)
- **Open:** `speakers.select_speakers` scores addressed (+5), mentioned (+2), warmth to the player, open-thread overlap and recency only. A rival does not cut in when their crush is addressed, a resentful or protective character is no likelier to speak when their target is the subject, and a person with a heavy goal (P-07) gets no push to pursue it. Characters feel like a round-robin of polite answerers, which is the main reason "decisions" read as flat in play.
- **Next:** add score terms from the speaker's own stances toward whoever is addressed or mentioned (rival, protective_of, resents: +), goal weight about the topic (+), and `distrusts` toward the player (reply short or not at all); bounded (each term at most about 1.5) so an addressed person still answers. Tests with fixed seeds; check the sweep and a hosted play for variety.
- **Touches:** `world_model/speakers.py`, `world_model/model.py` (`SpeakerPlan.reason`), `tests/backend/app/engine/world_model/`.

## BL-102 — A character's choices cannot be explained or tuned
- **Bucket:** C (engine)
- **Open:** stances record their causes, but the choices built on them (which beat fired, who was picked to speak and why, why a rival aim was seeded) leave no trace. `next_beat` picks "waited longest, then priority" and the Theatre cannot show why a resident did a thing, so tuning drama (BL-87) is blind.
- **Next:** a bounded per-turn `decisions` list on the model (kind, character, chosen option, runner-up, the stance and goal ids that scored it), cleared each turn, shown only in the operator Theatre and debug views (never to players, per the no-house-log rule). Test that removing a cause changes the entry.
- **Touches:** `world_model/model.py`, `agenda.py`, `speakers.py`, `sim/theatre.py`, `frontend/drama.html`.
