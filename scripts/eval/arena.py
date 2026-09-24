"""Jev game arena CLI. See backend/app/evaluation/cli.py and
documentation/model_output_docs/JEV_GAME_ARENA_DESIGN.md.

Example (pilot, beta vs prod, all personas, both games):
    python -m scripts.eval.arena all --experiment-id arena_pilot_01
"""
from backend.app.evaluation.cli import main

if __name__ == "__main__":
    main()
