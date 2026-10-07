# The engaged game is easy: rivals never beat the player to the target

## BL-98 — A scripted engaged player wins in 12 to 18 days on every house, whatever the rivals' strength
- **Bucket:** C (engine)
- **Open:** the P-08 sweep (`scripts/sweep_terrace_difficulty.py`, 2026-10-06 build, 12 houses x both genders x `rival_aim` 0, 0.3, 0.6) won 24 of 24 in a median 12.5 days (max 18) at every strength, and no rival coupled with the player's target first. Rival aims make rivals visible (`compete_for` beats) but a beat changes nothing about the target's standing or the target's choice, so rivalry is flavour, not pressure. Owner goal: hard for an engaged player.
- **Next:** make a rival's move cost the player something derived from stances: a rival who is `compete_for`-ing and is liked by the target should move the target's standing or take the target's time (an NPC couple forms when both decide, see `couples_ready`); then re-run the sweep and pick the strength that moves the win day without pushing the passive cut past 180. Needs an arena gate (behaviour change).
- **Touches:** `world_model/agenda.py` (`couples_ready`, `compete_for`), `world_model/offscreen.py`, `scripts/sweep_terrace_difficulty.py`.
