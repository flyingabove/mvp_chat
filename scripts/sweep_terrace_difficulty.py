"""Difficulty sweep of the seeded Terrace campaigns (no model calls): rival strength x house seed x player gender.

    python -m scripts.sweep_terrace_difficulty --aims 0 0.3 0.6 --seeds 12

Per cell it plays the strategic player (days to the win, or why not) and the passive player (day the director cuts).
Rival strength is `social_tracks.couples.rival_aim`. Prints a table and writes `data/sweeps/terrace_difficulty.json`.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sweep(aims, seeds, genders, passive_cap=180):
    import pytest
    from tests.backend.app.api.campaign_harness import make_campaign, run_passive, run_strategic
    rows = []
    for aim in aims:
        for seed in seeds:
            for gender in genders:
                for kind in ("strategic", "passive"):
                    with pytest.MonkeyPatch.context() as mp, tempfile.TemporaryDirectory() as tmp:
                        from backend.app.config import settings
                        mp.setattr(settings, "TYPESAFE_ENABLED", False)     # the sweep never reaches a model: same pins as
                        mp.setattr(settings, "TYPESAFE_API_KEY", "")        # the unit tests (tests/conftest.py)
                        mp.setenv("GEMINI_ROUTER", "off")
                        c = make_campaign(mp, Path(tmp), seed)
                        sid = f"{kind}-{aim}-{seed}-{gender}"
                        if kind == "strategic":
                            r = run_strategic(c, sid, gender, rival_aim=aim)
                            won = bool(r["ending"] and r["ending"]["id"] == "left_together")
                            rows.append({"aim": aim, "seed": seed, "gender": gender, "kind": kind, "won": won, "day": r["day"],
                                         "target_coupled": r["target_coupled"], "ending": (r["ending"] or {}).get("id")})
                        else:
                            r = run_passive(c, sid, gender, cap=passive_cap, rival_aim=aim)
                            cut = bool(r["ending"] and r["ending"]["id"] == "cut_by_director")
                            rows.append({"aim": aim, "seed": seed, "gender": gender, "kind": kind, "cut": cut, "day": r["day"]})
                print(f"aim={aim} seed={seed} {gender} done", file=sys.stderr, flush=True)
    return rows


def summarise(rows):
    out = []
    for aim in sorted({r["aim"] for r in rows}):
        strat = [r for r in rows if r["aim"] == aim and r["kind"] == "strategic"]
        passive = [r for r in rows if r["aim"] == aim and r["kind"] == "passive"]
        wins = [r["day"] for r in strat if r["won"]]
        cuts = [r["day"] for r in passive if r["cut"]]
        out.append({"aim": aim, "cells": len(strat), "wins": len(wins),
                    "win_day_median": statistics.median(wins) if wins else None, "win_day_max": max(wins, default=None),
                    "lost_to_a_rival": sum(1 for r in strat if r["target_coupled"] and not r["won"]),
                    "cuts": len(cuts), "cut_day_median": statistics.median(cuts) if cuts else None,
                    "cut_day_max": max(cuts, default=None), "passive_uncut": len(passive) - len(cuts)})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--aims", type=float, nargs="+", default=[0.0, 0.3, 0.6])
    parser.add_argument("--seeds", type=int, default=12)
    parser.add_argument("--genders", nargs="+", default=["M", "F"])
    args = parser.parse_args(argv)
    rows = sweep(args.aims, range(args.seeds), args.genders)
    summary = summarise(rows)
    out = ROOT / "data" / "sweeps"
    out.mkdir(parents=True, exist_ok=True)
    (out / "terrace_difficulty.json").write_text(json.dumps({"rows": rows, "summary": summary}, indent=1), "utf-8")
    for line in summary:
        print(line)


if __name__ == "__main__":
    main()
