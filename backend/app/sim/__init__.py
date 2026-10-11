"""Headless season simulation (BL-86): run a story with no human player, offline.

`SeasonRunner` (runner.py) advances a `WorldModel` day by day with the existing
stepper and off-screen pairing logic, asks a `Writer` (writer.py) for each
scene, and commits the result through the model's own mutation primitives
(events, memories, the epistemic ledger, relationship edges) -- never a
second engine. `invariants.py` holds the pure, independently testable checks
run after every simulated day.
"""
