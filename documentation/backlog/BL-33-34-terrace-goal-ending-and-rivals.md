# Terrace: the goal, its ending, and rivals (remaining evidence work)

The BL-33 offline coverage and the BL-34 rival mechanics shipped 2026-09-30 (as built: `design/SOCIAL_ENGINE.md`,
"Scene recall and visible rivals" and "Leave-together asks, choice cards and plans"). What is left needs real play.

## BL-34 — Rivals: hosted evidence and the gaps the fix does not cover
- **Open:** (1) Not yet seen on hosted beta: rivals now start with an aim (`couples.rival_aim`) and compete when the player wins the same person, but no hosted run over several story days has confirmed a visible counter-invitation, competing plan or rival beat with the real storyteller. (2) Residents who arrive later through cast rotation get no seeded aim (`rivals.seed_rival_aims` runs once at world build). (3) The passive-player director cut moved from days 95-135 to 93-156 across six seeded houses with aims (allowance 180); only six houses were measured. (4) The rival beat text is engine-side only; how well the storyteller plays "one small visible move" is unmeasured.
- **Next:** a hosted multi-day run per player gender that records the rival's agenda, any invitation agreement and the beat lines; seed aims for arrivals in `bootstrap.sync_membership`; measure the cut window over 12 houses and keep it inside 180; count rival beats per 25 turns in an arena replay and check none narrates private thoughts.
- **Touches:** `world_model/rivals.py`, `world_model/bootstrap.py`, `world_model/turn.py` (`sync_membership`, `BEAT_TEXT`), tests.

## BL-33 — Terrace win path on hosted beta
- **Open:** offline, seeded campaigns prove the earned win on both player genders (`test_terrace_campaigns.py`), and `test_terrace_win_paths.py` proves refusal then retry, wording that never changes the verdict, a long skip lapsing an open yes, a withdrawal removing the card, and a prose "yes" on a refusal being replaced. Never seen on hosted beta: the accepted path (mutual relationship, leave-together yes, confirmation, panel ending) and the female-player path with the real storyteller and Jev.
- **Next:** a hosted 20-turn campaign for each player gender that earns the win; it cannot be forced (standing needs days of real behaviour), so record commit, roster and turn count when one is achieved, then delete this section. Natural-language decision coverage (an extractor question, measured with Jev) is tracked with BL-46.
- **Touches:** evidence only, unless a run exposes a defect.
