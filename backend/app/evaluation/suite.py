# backend/app/evaluation/suite.py
"""The versioned benchmark suite (JEV_GAME_ARENA_DESIGN.md §9).

Both active games, two starting conditions each (player gender selects a
different Six Strangers slot/bedroom, and a different IU persona opening),
so every stratum has at least two scenario clusters for the bootstrap.
Diagnostic stress fixtures (refusals, blocked routes, capacity) belong in
response-fork suites and are kept out of this headline mix.
"""
from __future__ import annotations

from backend.app.evaluation.contracts import ScenarioSpec

SUITE_VERSION = "arena-suite-0.2"

# Every game (episode) is at least MIN_TURNS player actions: shorter games
# barely get past the opening scene (user decision 2026-09-24).
MIN_TURNS = 10


def default_scenarios(max_player_turns: int = MIN_TURNS) -> list[ScenarioSpec]:
    return [
        ScenarioSpec("iu.opening_m", "iu_murder_mystery", "M", "Alex", max_player_turns),
        ScenarioSpec("iu.opening_f", "iu_murder_mystery", "F", "Jamie", max_player_turns),
        ScenarioSpec("six.opening_m", "six_strangers", "M", "Alex", max_player_turns),
        ScenarioSpec("six.opening_f", "six_strangers", "F", "Jamie", max_player_turns),
    ]


# Run sizes. API calls scale with pairs x turns (player + storyteller +
# extractor per turn) plus 2 judge calls per pair per window. `gate` is the
# cheap default for promotion decisions; `pilot` is for measurement;
# `smoke` checks the plumbing (and is the only size practical on local Ollama).
PROFILES: dict[str, dict] = {
    "smoke": {"scenarios": ("iu.opening_m", "six.opening_m"), "personas": ("direct_investigator",),
              "replicates": 1, "turns": MIN_TURNS},
    "gate": {"scenarios": None, "personas": ("exploratory_newcomer", "direct_investigator", "boundary_tester"),
             "replicates": 1, "turns": MIN_TURNS},
    "pilot": {"scenarios": None, "personas": None, "replicates": 2, "turns": 12},
}


def profile_scenarios(profile: str, turns: int | None = None, stories: list[str] | None = None) -> list[ScenarioSpec]:
    spec = PROFILES[profile]
    horizon = turns or spec["turns"]
    picked = [s for s in default_scenarios(horizon)
              if (spec["scenarios"] is None or s.scenario_id in spec["scenarios"])
              and (not stories or s.story_id in stories)]
    return picked
