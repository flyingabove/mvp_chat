# backend/app/engine/world/travel_rules.py
import random
from typing import List
from .edge import PathEdge


class TravelRules:
    """
    Encodes non-AI travel logic:
    - fork resolution
    - seeded randomness
    """

    def __init__(self, seed: int):
        self.random = random.Random(seed)

    def choose_edge(self, edges: List[PathEdge]) -> PathEdge:
        """
        Choose exactly one valid edge.
        """
        valid = [e for e in edges if not e.blocked]
        if not valid:
            raise RuntimeError("No valid travel paths available")
        return self.random.choice(valid)
