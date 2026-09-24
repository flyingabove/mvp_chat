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

SUITE_VERSION = "arena-suite-0.1"


def default_scenarios(max_player_turns: int = 8) -> list[ScenarioSpec]:
    return [
        ScenarioSpec("iu.opening_m", "iu_murder_mystery", "M", "Alex", max_player_turns),
        ScenarioSpec("iu.opening_f", "iu_murder_mystery", "F", "Jamie", max_player_turns),
        ScenarioSpec("six.opening_m", "six_strangers", "M", "Alex", max_player_turns),
        ScenarioSpec("six.opening_f", "six_strangers", "F", "Jamie", max_player_turns),
    ]
