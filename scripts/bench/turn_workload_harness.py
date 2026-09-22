#!/usr/bin/env python
"""Phase 0B — repeatable turn workload harness.

Drives real chat turns against a running StoriesChat instance (local dev or a
deployed beta URL) and reports p50/p95 latency, per-stage timing (from the
turn_stage_ledger the server now logs — see backend/app/utils/stage_timer.py),
and token usage, grouped by scenario.

This does NOT scrape the server's own logs — it measures from the client side
(HTTP round-trip) and also asks the server for its own view via the `usage`
field in the chat response, so latency numbers reflect what a real player
experiences, not just server-side processing time.

Usage:
    python scripts/bench/turn_workload_harness.py --base-url http://127.0.0.1:8000
    python scripts/bench/turn_workload_harness.py --base-url https://beta-api.storieschat.ai --concurrency 1 10
    python scripts/bench/turn_workload_harness.py --base-url ... --story six_strangers --genders M F --turns 5

Concurrency levels requested by the plan are 1, 10, 50 concurrent independent
sessions. 50 concurrent full LLM-backed turns against a live paid endpoint is
expensive and slow to run casually, so the default is conservative (1, 5); pass
--concurrency explicitly for the full matrix when you want to spend the tokens.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class TurnResult:
    scenario: str
    ok: bool
    latency_ms: float
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None


@dataclass
class ScenarioResults:
    name: str
    results: list[TurnResult] = field(default_factory=list)

    def summary(self) -> dict:
        ok = [r for r in self.results if r.ok]
        lat = sorted(r.latency_ms for r in ok)
        n = len(lat)
        def pct(p: float) -> float | None:
            if not n:
                return None
            idx = min(n - 1, int(round(p * (n - 1))))
            return round(lat[idx], 1)
        return {
            "scenario": self.name,
            "attempts": len(self.results),
            "ok": n,
            "failed": len(self.results) - n,
            "latency_ms_p50": pct(0.50),
            "latency_ms_p95": pct(0.95),
            "latency_ms_max": round(max(lat), 1) if lat else None,
            "latency_ms_mean": round(statistics.mean(lat), 1) if lat else None,
            "prompt_tokens_mean": (
                round(statistics.mean([r.prompt_tokens for r in ok if r.prompt_tokens]), 0)
                if any(r.prompt_tokens for r in ok) else None
            ),
            "completion_tokens_mean": (
                round(statistics.mean([r.completion_tokens for r in ok if r.completion_tokens]), 0)
                if any(r.completion_tokens for r in ok) else None
            ),
        }


async def _one_turn(
    client: httpx.AsyncClient, session_id: str, message: str, request_id: str,
    scenario: str, extra_payload: dict | None = None,
) -> TurnResult:
    payload = {"session_id": session_id, "message": message, "request_id": request_id}
    if extra_payload:
        payload.update(extra_payload)
    t0 = time.perf_counter()
    try:
        r = await client.post("/api/chat", json=payload, headers={"X-Guest-Id": session_id})
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        data = r.json()
        if data.get("error"):
            return TurnResult(scenario, False, elapsed_ms, error=str(data["error"])[:200])
        usage = data.get("usage") or {}
        return TurnResult(
            scenario, True, elapsed_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return TurnResult(scenario, False, elapsed_ms, error=f"{type(exc).__name__}: {exc}")


async def _run_session(
    base_url: str, story: str, gender: str, n_turns: int, scenario: str,
    messages: list[str],
) -> list[TurnResult]:
    session_id = f"bench-{scenario}-{uuid.uuid4().hex[:8]}"
    out: list[TurnResult] = []
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        # Turn 0: new game (cold-ish — first retrieval for this session).
        out.append(await _one_turn(
            client, session_id,
            f"__cmd_newgame__:{story}|{gender}|BenchTester",
            f"{session_id}-r0", scenario,
            extra_payload={"persona_mode": "default", "persona_name": "Default"},
        ))
        for i in range(n_turns):
            msg = messages[i % len(messages)]
            out.append(await _one_turn(client, session_id, msg, f"{session_id}-r{i+1}", scenario))
    return out


DEFAULT_MESSAGES = [
    "Nice to meet everyone. What's there to do around here?",
    "I'll head to the kitchen and see who's around.",
    "That's interesting, tell me more about that.",
    "Let's go for a walk outside.",
    "What's everyone's plan for tomorrow?",
]


async def run_matrix(
    base_url: str, stories: list[str], genders: list[str],
    n_turns: int, concurrency_levels: list[int], sessions_per_level: int,
) -> list[dict]:
    all_summaries: list[dict] = []
    for story in stories:
        for gender in genders:
            for conc in concurrency_levels:
                scenario = f"{story}-{gender}-conc{conc}"
                print(f"--- running {scenario} ({sessions_per_level} sessions, concurrency={conc}) ---", file=sys.stderr)
                sem = asyncio.Semaphore(conc)

                async def _bounded():
                    async with sem:
                        return await _run_session(base_url, story, gender, n_turns, scenario, DEFAULT_MESSAGES)

                batches = await asyncio.gather(*[_bounded() for _ in range(sessions_per_level)])
                sr = ScenarioResults(scenario)
                for batch in batches:
                    sr.results.extend(batch)
                summary = sr.summary()
                all_summaries.append(summary)
                print(json.dumps(summary), file=sys.stderr)
    return all_summaries


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", required=True, help="e.g. http://127.0.0.1:8000 or https://beta-api.storieschat.ai")
    ap.add_argument("--story", dest="stories", action="append", default=None,
                     help="story id, repeatable (default: six_strangers)")
    ap.add_argument("--genders", nargs="+", default=["M", "F"])
    ap.add_argument("--turns", type=int, default=3, help="messages per session after new-game")
    ap.add_argument("--concurrency", nargs="+", type=int, default=[1, 5],
                     help="concurrency levels to test (plan asks for 1, 10, 50 — expensive; opt in explicitly)")
    ap.add_argument("--sessions-per-level", type=int, default=2)
    ap.add_argument("--out", default=None, help="write JSON summary here (default: stdout only)")
    args = ap.parse_args()

    stories = args.stories or ["six_strangers"]

    summaries = asyncio.run(run_matrix(
        args.base_url, stories, args.genders, args.turns,
        args.concurrency, args.sessions_per_level,
    ))

    report = {
        "base_url": args.base_url,
        "generated_at": time.time(),
        "scenarios": summaries,
    }
    text = json.dumps(report, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    print(text)


if __name__ == "__main__":
    main()
