# Realistic first meetings and slow-building closeness (engine first, Terrace configures)

**Principle (owner, 2026-09-30):** these items improve the *game engine's* characters, so every story gets more real, smarter people. They are not Terrace-only features. Build each as a generic mechanism on the Character / relationship / world-model objects, and let Terrace only configure it in story JSON. Terrace is the first test, not the owner of the code.

Owner direction 2026-09-30: this is a dating show. The opening is two opposite-gender Japanese strangers alone on camera, with funny, awkward energy. They don't know your name and don't act like friends. Falling in love takes days, not 5 turns. Design: [design/TERRACE_HOUSE.md §11](../design/TERRACE_HOUSE.md).

## BL-76 — Storyteller portrays closeness the relationship state does not allow (generic engine)
- **Open:** the numbers are already slow (romance `strangers` tier 0-25; `friends` gated on `days_known` 2; `committed` on 5), but the storyteller never sees the tier. In sim E5 (seed 0, local llama3.1-8b, 2026-09-30), Arisa uses "Sam" on turn 3, "smiles warmly, holding your gaze" on turn 4, and on turn 5 blushes and invents shared history ("one of the first people who really made an effort to get to know me"). `world_model/turn.py` passes only `_encounter_note` ("first time meeting the player") and `_name_note`. `turn.reaction_cues` "responds warmly" carries the same wording at every tier.
- **Next:**
  1. Optional per-tier `conduct` text in `social_tracks.tiers`, rendered into the scene contract once per present resident. Terrace authors `strangers` (polite, a little stiff, the player's persona name plus -san once heard, e.g. "Paul-san", never before hearing it; no shared history, no blushing, touching or stated feelings, interest is SHOWN through behavior and stays ambiguous, e.g. asking you more questions than anyone else, or teasing that could mean either thing; never narrated feelings like blushing or scooting closer; see design §12) and `friends` (first names, teasing, no romance unless the player starts it).
  2. Word reaction cues per tier ("polite, pleased" for strangers).
  3. NPC-initiated flirting and confessions are gated on that NPC's own tier toward the player.
  4. Tests: conduct appears only for authored tiers; a day-0 confession is refused at `strangers`; the name rule holds before and after the player introduces themselves.
  5. Optional, only if prompting is not enough: a Jev check for affection beyond the tier that regenerates the reply. Hold it to the ≥99% rule in `user_corrections.md`; a regex is not enough.
- **Touches:** `six_strangers_story.json` (`social_tracks`), `world_model/turn.py`, `world_model/standing.py`, the reaction-cue module, `design/SOCIAL_ENGINE.md`.

## BL-77 — Terrace opening text reads as mood, not two strangers on camera (content only)
- **Open:** `opening.segments` and the 17 `opening.first_resident` lines in `six_strangers_story.json` are gentle and near-affectionate (Arisa: "This room looks different with someone else in it. That's a good thing, I think."). Nothing marks the dating-show subtext or the stranger awkwardness.
- **Next:** rewrite the segments and all 17 greeter cues and lines around the real first-meeting ritual with light Japanese markers (owner choice): shoes off in the genkan, a camera in the corner, a simultaneous bow, a stiff "hajimemashite", surname first, not knowing whether to sit. State the subtext once (one man and one woman, a house built for romance, and both know it). Each line is awkward in that person's own way; none is warm. Update the opening tests that pin the text.
- **Touches:** `six_strangers_story.json` (`opening`), opening tests in `tests/backend/app/engine/`.

## BL-78 — Arrivals are a pasted roll call (generic opening arrivals; Terrace adds "what's your type?")
- **Open:** `opening_scene.opening_arrival_segments` pastes "The front door opens. X is the next resident to arrive." plus a fixed "I'm X." line into turns 2 to 5 (offsets 7/9/12/15). The model's answer to the player is tacked on after it. All intros share one template.
- **Next:**
  1. Space the offsets to about 8/14/20/26 so each pair gets two or three exchanges first.
  2. Keep the authored entrance cue. Pass the arrival to the storyteller as a must-address beat (the group stands and bows, then name, age, job) instead of pasting `entrance_lines`.
  3. Once all six are present, the show's "what's your type?" round runs (owner: yes), using an authored, vague `type_answer` per resident drawn from their real tastes.
  4. Measure before and after with a `--opening` first-meeting mode in `scripts/terrace_ollama_sim.py` (name given on turn 3). Count: the name used before it was given, intimacy and shared-history markers, and the scripted word share over the first 8 turns. Then read both transcripts.
- **Touches:** `engine/opening_scene.py`, `api/prompt_engine.py` (arrival wiring), `six_strangers_story.json`, `scripts/terrace_ollama_sim.py`, `tests/scripts/test_terrace_ollama_sim.py`.

## BL-84 — Opening-scene preferences, as one checklist for any story's first meeting (engine + content)
- **Open:** the owner's opening requirements were scattered, and the engine has no notion of "how well do these two people know each other" beyond `_encounter_note` and `_name_note` in `world_model/turn.py`. Strangers therefore behave like friends in any story, not just Terrace.
- **Next:** give the Character/relationship object a real acquaintance state (has met, knows the player's name or nickname, how formally they address them, shared history count) that feeds the scene contract for every story. Then hold every opening to this checklist:
  1. Strangers act like strangers: no name before it is heard, no shared past, no instant warmth. Use the persona's own name plus a polite suffix ("Paul-san").
  2. Humor is deadpan realism (silences, double bows, saying the obvious aloud), never jokes aimed at the audience.
  3. Show, never tell: interest appears as behavior (more questions than anyone else, teasing that could mean either thing), never narrated blushing or scooting closer. Keep it ambiguous: polite or interested?
  4. Group energy follows who was drawn: lively with extroverts, quiet with introverts. Nothing scripts it.
  5. Arrivals are encounters, not a roll call. No pasted template intros.
  6. The player is a Japanese cast member in Terrace; light Japanese markers only.
  7. The player gets no reliable read on anyone's feelings; first impressions can mislead.
  8. Nothing in the opening may run ahead of the relationship state: love takes days.
- **Touches:** `engine/state.py` or the Character model, `world_model/turn.py`, `engine/opening_scene.py`, story opening JSON, `design/CHARACTER_MEMORY.md`.
