# Terrace gameplay loop: findings from the offline Ollama simulation (2026-09-30)

Evidence and method: `design/TERRACE_HOUSE.md` section 10 (`scripts/terrace_ollama_sim.py`, local `llama3.1-8b-ctx16k`, seed 0,
male player, 24-36 turns per run, one run per setting). The reaction cues that came out of it shipped; these three did not.

## BL-72 — Finding a resident costs turns and the game gives no help
- **Open:** after a one-day skip the target was in the player's scene on only 36% of turns (E5, 28 turns, 6 days); four of the six days produced no gain at all because the scripted player never found her. `[CAST]` lists who lives in the house but not where they are, and the only way to find someone is to guess a room.
- **Next:** a player-facing way to locate a housemate, for example `(find Arisa)` or "where is Arisa" answered from `world.place_of` for residents the player would plausibly know about, optionally moving the player there with travel time; or locations in the cast list. Decide what the player is allowed to know (a shared house is small; a resident out at work should read as away, not as a room). Failing-first test through `/api/chat`; re-run E5 with a policy that uses it and compare target-present share and gain per day.
- **Touches:** `prompt_engine.py` (command parsing), `world_model/` place queries, `frontend/index.html` (cast list), `design/WORLD_MODEL.md`.

## BL-73 — No daily rhythm: a natural session never leaves day 0
- **Open:** at the story's pacing (5 minutes plus 0.2 per word, about 8 game minutes per turn) a day is about 68 turns, so 36 natural turns stayed on day 0 (E1). Compressing turns to 20 game minutes did not help (E4: still day 0, 83% zero-gain turns), because progress is limited by liked, varied behaviour per day (tag gains halve on each repeat and reset only at the next day), not by the clock. The only way to start a new day is the menu's skip or an explicit "I go to sleep", which nothing prompts.
- **Next:** an end-of-day offer using the choice-card path (the plan-skip card is the model): when stale cues pile up (two or more `stale` reactions today) or the clock passes about 22:30, offer "Call it a night" / "Keep going"; accepting sleeps to the next morning through the existing sleep/skip path (`_parse_plan_skip` is the pattern). Measure with the simulator by adding a policy that accepts the card, comparing standing per 100 turns and days per 100 turns with E1 and E5. Guards: promises due times, routines, the opening arrival pace.
- **Touches:** `world_model/choices.py`, `world_model/turn.py`, `api/prompt_engine.py`, `frontend/index.html`, `scripts/terrace_ollama_sim.py`.

## BL-74 — Extractor tag coverage is low and skewed (local model); hosted rate unmeasured
- **Open:** with the local 8B extractor only 11 of 24 warm turns produced any behaviour tag (E2 and E3 alike), and `complimentary` dominated, which is worth 0 to residents like Arisa. The hosted extractor's coverage and tag mix are unknown. Low coverage makes the reaction cues and standing feel unresponsive regardless of the engine.
- **Next:** a fixed probe set of about 30 player lines (compliments, help, honesty, jokes, support for a stated goal, rudeness) with the intended tags; measure tag recall and precision for the hosted extractor and the local one (`scripts/eval/` like `promise_judge_eval.py`); gate at a stated bar before changing prompts; consider mapping untagged kind acts to `warm` or `attentive`.
- **Touches:** `engine/extractors/turn_extractor.py` (behavior tag rules), `scripts/eval/`, `tests/eval_cases/`.
