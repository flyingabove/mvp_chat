"""Export registered playback scenarios to JSON for UI/playback clients."""
from __future__ import annotations

import argparse
from pathlib import Path

from backend.app.integration_playback.scenario_registry import export_scenarios_json

DEFAULT_OUTPUT = Path(__file__).resolve().parent / "build" / "scenario_index.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export integration playback scenarios to JSON")
    parser.add_argument(
        "--out",
        dest="out",
        type=str,
        default=str(DEFAULT_OUTPUT),
        help="Output path for JSON index (default: %(default)s)",
    )
    args = parser.parse_args()

    target = Path(args.out)
    path = export_scenarios_json(target)
    print(f"Wrote scenario index to {path}")


if __name__ == "__main__":
    main()
