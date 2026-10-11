"""Run a capped pilot season of an authored story on a real language model, then score it with the Jev script rubric.

LOCAL ONLY. Never run this from the Dockerfile, CI or app startup: it calls a live model and live Jev.

    python -m scripts.run_season                              # Terrace, 2 story days, Gemini + Jev (free)
    python -m scripts.run_season --days 3 --call-cap 30       # a longer run needs its cap raised on purpose
    python -m scripts.run_season --fake --no-score            # offline plumbing check: scripted writer, no network

Each scene is two model calls (write, then read back as consequences), so a run needs `2 x days x scenes-per-day`
calls. That number is printed before anything starts and the run is refused when it exceeds `--call-cap` (default
`DEFAULT_CALL_CAP`). Gemini and Jev are free; OpenAI costs money, so a run that resolves to OpenAI (including the silent
fall-back when no Gemini key is set) is refused unless `--allow-openai` is given, and that needs the owner's say-so.

Artifacts go to `data/season_runs/<stamp>/season.jsonl` (gitignored), one JSON object per line: `run` (the settings),
`scene` (who, where, when, the prose, the summary, feeling changes and whether each was applied), `day` (violations and
rejections), `state` (the relationship table at the end) and `rubric` (scene, day and season scores and verdicts).
Record the baseline result in `documentation/design/SOCIAL_ENGINE.md` ("Season baseline").
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DEFAULT_CALL_CAP = 20
CALLS_PER_SCENE = 2
OUT_ROOT = ROOT / "data" / "season_runs"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--story", default="six_strangers")
    parser.add_argument("--days", type=int, default=2)
    parser.add_argument("--scenes-per-day", type=int, default=3)
    parser.add_argument("--seed", default="pilot-1")
    parser.add_argument("--call-cap", type=int, default=DEFAULT_CALL_CAP, help="hard cap on model calls for the whole run")
    parser.add_argument("--provider", default=None, help="gemini (default), openai or ollama; else LLM_PROVIDER")
    parser.add_argument("--model", default=None)
    parser.add_argument("--allow-openai", action="store_true", help="OpenAI costs money: only with the owner's approval")
    parser.add_argument("--fake", action="store_true", help="offline: the scripted FakeWriter, no model call")
    parser.add_argument("--no-score", action="store_true", help="skip the Jev rubric")
    parser.add_argument("--out", type=Path, default=None, help="artifact directory (default data/season_runs/<stamp>)")
    return parser.parse_args(argv)


def planned_calls(args: argparse.Namespace) -> int:
    return CALLS_PER_SCENE * args.days * args.scenes_per_day


def refusal(args: argparse.Namespace, provider: str) -> Optional[str]:
    """Why this run must not start, or None. Checked before any model call."""
    if args.days < 1 or args.scenes_per_day < 1:
        return "--days and --scenes-per-day must be at least 1"
    if planned_calls(args) > args.call_cap:
        return (f"refusing: {args.days} day(s) x {args.scenes_per_day} scene(s) needs up to {planned_calls(args)} model "
                f"calls, over the cap of {args.call_cap}; lower the run or raise --call-cap on purpose")
    if provider == "openai" and not args.allow_openai:
        return "refusing: this would run on OpenAI, which costs money; use Gemini, or pass --allow-openai with the owner's approval"
    return None


def resolve_provider(args: argparse.Namespace) -> tuple[str, str]:
    """(provider, model) the run would really use, including the Gemini-key-missing fall-back to OpenAI."""
    if args.fake:
        return "fake", "scripted"
    from backend.app.llm.chat import resolve_chat_config
    config = resolve_chat_config(args.provider, args.model)
    return config.provider, config.model


def calls_made(writer) -> int:
    """Model calls a writer has made: the LLM writer counts them, the fake one keeps a list of prompts."""
    calls = getattr(writer, "calls", 0)
    return len(calls) if isinstance(calls, list) else int(calls or 0)


def artifact_rows(args: argparse.Namespace, setup, result, provider: str, model: str, rubric_report, writer) -> list[dict]:
    rows: list[dict[str, Any]] = [{
        "type": "run", "story": args.story, "seed": args.seed, "days": args.days, "scenes_per_day": args.scenes_per_day,
        "call_cap": args.call_cap, "provider": provider, "model": model, "calls_used": calls_made(writer),
        "scenes_written": sum(d.scenes_written for d in result.days), "stopped_early": result.stopped_early,
        "unparsed_extractions": getattr(writer, "unparsed", 0),
        "cast": {cid: asdict(note) for cid, note in setup.cast.items()}}]
    for day in result.days:
        for index, record in enumerate(day.scenes):
            applied = [asdict(d) for d in record.update.relationship_deltas
                       if not any(f"{d.a}-{d.b}" in why for why in record.rejections)]
            rows.append({"type": "scene", "day": day.day, "scene": index, "a": record.encounter.a, "b": record.encounter.b,
                         "place": record.encounter.place, "minute": record.encounter.minute,
                         "clock": setup.clock(record.encounter.minute), "text": record.text,
                         "summary": record.update.summary, "relationship_deltas_applied": applied,
                         "movements": [list(m) for m in record.update.movements], "rejections": record.rejections})
        rows.append({"type": "day", "day": day.day, "scenes_written": day.scenes_written,
                     "scenes_summarized": day.scenes_summarized, "violations": day.violations,
                     "rejections": day.rejections})
    relationships = getattr(setup.story.relationships, "state", {})
    rows.append({"type": "state", "relationships": {f"{a}>{b}": feelings for (a, b), feelings in sorted(relationships.items())}})
    rows.append({"type": "rubric", "report": rubric_report.to_dict() if rubric_report is not None else None})
    return rows


def write_artifacts(out: Path, rows: list[dict]) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / "season.jsonl"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    return path


WriterFactory = Callable[[asyncio.AbstractEventLoop, Any, int], Any]


def default_writer_factory(args: argparse.Namespace) -> WriterFactory:
    if args.fake:
        from backend.app.sim.writer import FakeWriter
        return lambda loop, setup, cap: FakeWriter()
    from backend.app.sim.llm_writer import LLMWriter, bridge_chat
    return lambda loop, setup, cap: LLMWriter(bridge_chat(loop, args.provider, args.model), setup, cap)


async def execute(args: argparse.Namespace, setup, writer, resolver) -> tuple[Any, Any]:
    """Run the season on a worker thread (the runner is synchronous), then score what was written."""
    from backend.app.sim import rubric
    from backend.app.sim.runner import SeasonRunner
    runner = SeasonRunner(setup.story, args.seed, writer, days=args.days, scenes_per_day=args.scenes_per_day,
                          budget=args.days * args.scenes_per_day)
    result = await asyncio.to_thread(runner.run)
    texts = [[scene.text for scene in day.scenes] for day in result.days if day.scenes]
    if args.no_score or not texts:
        return result, None
    return result, await rubric.score_season(texts, resolver)


def main(argv: Optional[list[str]] = None, writer_factory: Optional[WriterFactory] = None, resolver: Any = None) -> int:
    args = parse_args(argv)
    provider, model = resolve_provider(args)
    reason = refusal(args, provider)
    if reason:
        print(reason, file=sys.stderr)
        return 2
    print(f"season: {args.story}, seed {args.seed}, {args.days} day(s) x up to {args.scenes_per_day} scene(s); "
          f"provider {provider} ({model}); HARD CAP {args.call_cap} model calls, this run needs up to {planned_calls(args)}")
    if not args.no_score:
        os.environ.setdefault("TYPESAFE_ENABLED", "true")     # CLI only: importing this module must not change settings
    from backend.app.sim.story_loader import build_season
    setup = build_season(args.story, args.seed)
    factory = writer_factory or default_writer_factory(args)
    holder: dict[str, Any] = {}

    async def go():
        holder["writer"] = factory(asyncio.get_running_loop(), setup, args.call_cap)
        return await execute(args, setup, holder["writer"], resolver)

    try:
        result, report = asyncio.run(go())
    except Exception as exc:                                    # a failed run is reported as a failure, never as a score
        print(f"season FAILED after {calls_made(holder.get('writer'))} model call(s): "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    out = args.out or OUT_ROOT / time.strftime("%Y%m%d-%H%M%S")
    path = write_artifacts(out, artifact_rows(args, setup, result, provider, model, report, holder["writer"]))
    written = sum(d.scenes_written for d in result.days)
    print(f"wrote {written} scene(s) over {result.completed_days} day(s); violations: {len(result.all_violations)}; "
          f"rejected updates: {len(result.all_rejections)}; artifacts: {path}")
    print(report.render() if report is not None else "rubric: not scored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
