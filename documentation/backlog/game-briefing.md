# Game briefing before the first scene

Owner design session 2026-09-29, from the BL-46 discussion. Like BL-46, the agreed design lives here until it ships,
then moves to `design/` and this section is deleted.

## BL-49 — Every game opens with a briefing: map, controls, goal, then Start

- **Open:** a new game goes straight from the character modal (`#modal-onboard`, `frontend/index.html`
  `launchChat`) to the first generated scene. Nobody tells the player that `(...)`/`[...]` talk to the game master
  (BL-46), that `[map]` opens the map, or how to win; the goal only sits in the collapsed goal pill. The public
  endpoint `/api/story/{id}` (`api/story.py` `get_story_meta`) returns only `goal.win_text_rule`, and the player
  agent's brief (`debug_engine.py` `_build_player_brief`) hard-codes "YOUR GOAL: Discover what happened and who is
  responsible." for every story, which is wrong for Terrace.

### Agreed design (owner decisions)

1. **A canonical `briefing` block in every story JSON**, validated when the story loads; the authoring checklist
   fails a story without one:
   - `goal`: player-facing text that reveals a good amount without numbers or spoilers. Terrace: "Get into a romantic
     relationship with a housemate of the opposite gender, then ask them to leave the house with you: just the two of
     you. Other residents may want the same person. If three other couples leave before you, the director cuts you."
     No standing scores, tiers or cooldowns; mystery stories give the goal, not the answer.
   - `controls`: the shared default cards (below) plus any per-game extras.
   - `endings`: optional list of the possible ending titles and kinds (win / loss / neutral), from `endings`.
   - The map is not duplicated: the briefing uses the story's existing `world.world_map_image` and atlas; a story
     with no map image shows its list of places instead.
2. **Default controls (every game):**
   - Plain text is you speaking or acting in the scene.
   - `(...)` or `[...]` talks to the game master: ask a question, or give a command such as
     `(I walk out onto the street)`.
   - `[map]`, `(map)` or `/map` opens the map; the 3-dot menu has the map, cast, journal and time skip.
   - Choice cards in the chat (like "leave together now?") are answered by tapping.
3. **Flow:** character modal → **briefing screen** (tabs or swipe on phone: Map, Controls, Goal) → **[Start game]** →
   the new-game request and first scene. It is shown for every new game.
4. **Skippable, but never silent.** A Skip button is allowed. Whether viewed or skipped, the first thing in the chat
   (before the opening scene) is a compact "How to play" system card: the two basic controls (`(...)` game master,
   `[map]`) and the goal in one or two lines.
5. **Later access:** "How to play" in the 3-dot menu reopens the briefing.
6. **Existing sessions:** a game started before this ships shows the briefing once on its next resume (tracked on
   the saved session), then never again for that session.
7. **Bots see the same thing.** `/api/story/{id}` returns `briefing`; `_build_player_brief` is built from it (goal,
   controls) instead of the hard-coded mystery goal, keeping the rule that the player agent knows only what a real
   player sees.

- **Next:** add `briefing` to both stories (`7_six_strangers`, `1_iu_murder_mystery`), a loader validator plus
  authoring-checklist rule with tests, return it from `/api/story/{id}`, build the briefing screen and "How to play"
  card and menu item, add the `/map` alias, rebuild `_build_player_brief` from it. Browser check: desktop Chromium and
  iPhone-sized WebKit, both new game and resume.
- **Touches:** `backend/app/stories/*/*_story.json`, the story loader / `engine/authoring_checklist.py`,
  `api/story.py`, `api/debug_engine.py`, `frontend/index.html`, `design/` doc for the story schema.
