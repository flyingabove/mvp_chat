# Narration restates the player and invents feelings

## BL-29 — Narration restates the player's action and invents their feelings
- **Open:** about 20% of turns open by restating the player's typed action in second person; hosted recurrence 2026-09-29 ("Inviting her to join you in the Living Room. As you lead the way ..."). The bounded lexical echo trimmer misses paraphrases and gerund forms; invented feelings ("making your stomach grumble", "your eyes scanning its surface") bypass the filter. Any prompt change needs its own arena gate and must not trim narration that adds new information.
- **Next:** prompt rule plus a normalized first-to-second-person backstop beside `drop_player_echo`; the two verbatim examples as unit cases; an end-to-end case.
- **Touches:** `prompt_builder.py`, `dialogue.py` (`ground_social_scene`), `prompt_engine.py`.
