# Drama direction knobs and the Jev script rubric (generic engine)

**Owner tone rule (2026-10-01), every game mode:** real life, dramatized. Everything is plausible, but it plays like
a shot drama (Terrace House, Friends, K-drama). The engine **nudges** toward that and never scripts outcomes.
Every nudge has a tuning knob. "Good" means engaging enough to be a Netflix script, judged by Jev.

## BL-87 — Showrunner knobs that nudge scenes, and a script rubric Jev scores them with
- **Bucket:** C (engine)
- **Open:** pacing and drama are a handful of hard-coded engine nudges:
  - beat text (`turn.BEAT_TEXT`);
  - room energy;
  - affinity signals;
  - the acquaintance ladder.

  Nothing measures whether a scene or a day is engaging. The arena judges beta against prod, not drama quality.
- **How the craft does it** (research, 2026-10-01):
  - **Coverage readers and the Black List** score premise, plot, character, dialogue and setting from 1 to 10 and
    give a verdict of Pass, Consider or Recommend. A score of 8 or more is excellent. Readers look for distinct,
    honest characters, subtext, and conflict that escalates.
  - **McKee:** every scene must *turn a value* (positive to negative or the reverse) through conflict. If nothing
    turns, the scene is a non-event. Complications must progress, not repeat.
  - **K-drama:** a lead couple, second leads as foils, and third leads for comedy. A beat schedule over the season:
    meet, ally-and-antagonist friction, attraction denied, a pinch point (the opposing force shows its power), the
    first move, the midpoint (passive becomes active), the "tower" (the worst fear comes true), separation, crisis,
    the big gesture. A cliffhanger ends every episode; dramatic irony and secrets come up again and again. Makjang
    devices (overheard talk, "accidental" meetings, revealed secrets) heighten the drama, and the stories balance
    outrageousness with relatability.
  - **Sitcoms (Friends):** an A story, a B story and C runners; three acts; a goal, a failed first attempt, a new
    approach. The improv "game of the scene" finds the unusual thing and heightens it. Callbacks pay off.
  - **Reality TV (Terrace House):** producers suggest topics and *edit* the story out of real footage. The drama
    comes from selection, not invention.
- **Design:**
  1. **`drama` profile** in story JSON. Engine defaults, then a mode preset (`reality`, `kdrama`, `sitcom`,
     `thriller`), then story overrides. Each knob is a number from 0 to 1 or a small integer, rendered as nudges in
     the scene prompt or used by the camera (BL-86) to choose scenes. The knobs:
     - `heat`: realistic up to makjang exaggeration. Default 0.7, per the owner's "very dramatic".
     - `comedy`: game-of-the-scene heightening and banter.
     - `irony_bias`: the camera prefers secret-held and dramatic-irony dynamics (BL-85).
     - `escalation`: each time a dynamic comes back, it must go further.
     - `coincidence_budget`: overheard talk or "accidental" meetings per day. The engine stages these only where
       they are physically plausible: rooms in earshot, overlapping routines.
     - `callback_rate`: runners.
     - `cliffhanger`: the end of each story day leaves an open question.
     - `threads`: how many parallel threads the camera tracks (A, B, C).
     - `scenes_per_day`: N.
     - `arc_template`: `kdrama_16`, `sitcom_episode` or `reality_season`. Each template is a list of beats keyed
       to the fraction of the run and to state, such as "pinch point: let the opposing force show its power". A
       beat is a nudge offered to the scene's existing dynamics, never a forced event.
     - `romance_pace`: earliest days for the first move and for a confession. It works with the acquaintance
       ladder.
  2. **Script rubric:** built (P-05); its items, verdict rule and calibration are in `design/SOCIAL_ENGINE.md` ("Script rubric"). BL-96 covers what the calibration does not show.
  3. **Tuning loop.** `SeasonRunner` (BL-86) sweeps knob values per preset across seeds and picks settings by
     rubric score. The results table goes in `design/SOCIAL_ENGINE.md`.
- **Next:**
  - Add the `drama` profile with defaults that reproduce today's prompts (a no-op), then switch on knobs one at a
    time, each with an arena gate.
- **Sources (researched 2026-10-01):**
  - Script coverage, [Wikipedia](https://en.wikipedia.org/wiki/Script_coverage) and
    [The Script Lab](https://thescriptlab.com/?p=38102): concept, character, structure, dialogue, plot; Pass,
    Consider or Recommend.
  - The Black List's 1–10 scores on premise, plot, character, dialogue and setting
    ([guide](https://reviewmyscript.com/decoding-the-black-list-a-screenwriters-guide/)).
  - McKee on value turns and progressive complications ([mckeestory.com](https://mckeestory.com/do-your-scenes-turn/),
    [charges](https://www.socreate.it/en/blogs/screenwriting/how-to-use-positive-and-negative-charges-to-structure-great-scenes)).
  - The K-drama rom-com beat sheet and cast structure
    ([Substack](https://excitedmark.substack.com/p/how-to-write-a-kdrama-romcom-romantic-comedy)).
  - Makjang devices ([Dramabeans](https://dramabeans.com/2017/07/changing-tastes-real-life-is-sometimes-more-bizarre-than-makjang-dramas),
    [JoongAng Daily](https://www.koreajoongangdaily.com/korea/soap-operas-with-a-korean-twist/10977104)).
  - KOCCA contest criteria: originality, completion, marketability
    ([Korea Times](https://www.koreatimes.co.kr/lifestyle/trends/20210614/kocca-on-the-hunt-for-creative-stories-for-its-annual-awards)).
  - A, B and C stories ([TV Calling](https://www.tv-calling.com/what-are-a-b-and-c-stories-in-screenwriting-tv-writing-101/),
    [GL Coverage](https://glcoverage.com/2024/06/25/a-b-and-c-plots/)).
  - The game of the scene and "heighten and explore"
    ([Hoopla](https://www.hooplaimpro.com/quick-guide-game-of-scene),
    [Funny How](https://funnyhow.substack.com/p/heighten-and-explore)).
  - Dan Harmon's story circle ([Dabble](https://dabblewriter.com/the-story-circle)).
  - Terrace House producers' topic direction and editing
    ([Wikipedia](https://en.wikipedia.org/wiki/Terrace_House),
    [Japan Today](https://japantoday.com/category/entertainment/update1-fuji-tv-had-deal-with-terrace-house-cast-on-how-scenes-played-out)).
- **Touches:** new `engine/rules/drama.py` (profile and presets; note `engine/world_model/drama.py` already exists, so check names before building: plan P-12) and `backend/app/sim/rubric.py` (Jev questions),
  `prompt_builder.py` / `turn.py` (nudge rendering), story JSON (`drama`), `tests/eval_cases/`, `scripts/eval/`,
  `design/SOCIAL_ENGINE.md`.
