# backend/app/evaluation/report.py
"""Arena report (JEV_GAME_ARENA_DESIGN.md §8, §11 step 5).

build_report() is pure: manifest + arms + pair judgments -> JSON-able dict.
render_html() turns that dict into one self-contained page (no external
assets) with drill-down to transcripts, applied checks and raw judge
distributions. Headline quality never hides correctness regressions,
coverage, cost or latency.
"""
from __future__ import annotations

import html
from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from backend.app.evaluation.aggregate import summarize
from backend.app.evaluation.contracts import BETA, PROD, ArmTranscript, ExperimentManifest
from backend.app.evaluation.pipeline import episode_outcomes
from backend.app.evaluation.rubric import Rubric
from backend.app.llm.usage import estimate_cost_usd



def pct(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def critical_regressions(judgments: Sequence[Mapping[str, Any]], rubric: Rubric) -> tuple[list[str], dict]:
    counts: dict[str, dict[str, int]] = {}
    for j in judgments:
        seen: dict[str, set[str]] = defaultdict(set)
        for w in j.get("windows") or []:
            for probe_id, sides in w["probes"].items():
                for side, r in sides.items():
                    if r["confirmed"]:
                        seen[probe_id].add(side)
        for side in (BETA, PROD):
            for f in (j.get("checks") or {}).get(side, []):
                if f["severity"] == "critical":
                    seen[f["check_id"]].add(side)
        for key, sides in seen.items():
            c = counts.setdefault(key, {BETA: 0, PROD: 0})
            for side in sides:
                c[side] += 1
    titles = {p.id: p.title for p in rubric.critical_probes}
    regressions = [f"{titles.get(k, k)} (beta {v[BETA]} vs prod {v[PROD]} episodes)"
                   for k, v in sorted(counts.items()) if v[BETA] > v[PROD]]
    return regressions, counts


def length_confound(judgments, arms) -> dict[str, dict[str, Any]]:
    """How often the release with longer replies won, per game. The judge
    prefers length despite instructions (see calibration 'shorten'), so a
    verdict that tracks length should be read with that bias in mind."""
    out: dict[str, dict[str, Any]] = {}
    for j in judgments:
        if j.get("outcome") not in ("beta_win", "prod_win"):
            continue
        words = {}
        for side in (BETA, PROD):
            arm = arms.get(f"{j['pair_id']}.{side}")
            if not arm or not arm.turns:
                break
            words[side] = sum(len(t.reply.split()) for t in arm.turns) / len(arm.turns)
        if len(words) != 2 or words[BETA] == words[PROD]:
            continue
        row = out.setdefault(j["story_id"], {"decided": 0, "longer_side_wins": 0, "diffs": []})
        row["decided"] += 1
        row["longer_side_wins"] += (j["outcome"] == "beta_win") == (words[BETA] > words[PROD])
        row["diffs"].append(words[BETA] - words[PROD])
    for row in out.values():
        diffs = row.pop("diffs")
        row["longer_side_win_rate"] = row["longer_side_wins"] / row["decided"]
        row["mean_beta_minus_prod_words"] = round(sum(diffs) / len(diffs), 1)
    return out


def dimension_table(judgments: Sequence[Mapping[str, Any]], rubric: Rubric) -> list[dict[str, Any]]:
    rows = []
    for dim in rubric.dimensions:
        values, reasons = [], Counter()
        scores: dict[str, list[float]] = {BETA: [], PROD: []}
        for j in judgments:
            for w in j.get("windows") or []:
                cell = w["dimensions"][dim.id]
                reasons[cell["reason"].split(":")[0]] += 1
                if cell["value"] is not None:
                    values.append(cell["value"])
                for side in (BETA, PROD):
                    if cell["scores"].get(side) is not None:
                        scores[side].append(cell["scores"][side])
        total = sum(reasons.values())
        rows.append({
            "dimension": dim.id, "title": dim.title, "weight": dim.weight,
            "windows": total, "resolved": len(values),
            "beta_share": (sum(values) / len(values)) if values else None,
            "unresolved_reasons": {k: v for k, v in reasons.items() if k != "resolved"},
            # 0-4 ordinal bands normalized by 4; a diagnostic, NOT a win probability
            "beta_band": (sum(scores[BETA]) / len(scores[BETA]) / 4) if scores[BETA] else None,
            "prod_band": (sum(scores[PROD]) / len(scores[PROD]) / 4) if scores[PROD] else None,
        })
    return rows


def build_report(manifest: ExperimentManifest, arms: Mapping[str, ArmTranscript],
                 judgments: Sequence[Mapping[str, Any]], rubric: Rubric, *,
                 calibration: Mapping[str, Any] | None = None, iterations: int = 2000) -> dict[str, Any]:
    story_ids = sorted({j["story_id"] for j in judgments})
    weights = {s: 1.0 for s in story_ids}              # both games equally weighted (§12 default)
    regressions, critical_counts = critical_regressions(judgments, rubric)
    outcomes = episode_outcomes(judgments)
    summary = summarize(outcomes, weights, critical_regressions=regressions, seed=manifest.seed,
                        iterations=iterations, calibrated=manifest.calibration_version != "uncalibrated")

    strata = {}
    for sid in story_ids:
        sub = [o for o in outcomes if o.stratum == sid]
        s = summarize(sub, {sid: 1.0}, seed=manifest.seed, iterations=iterations)
        strata[sid] = {"counts": s.counts, "p": s.p, "elo_delta": s.to_json()["elo_delta"],
                       "elo_interval": s.to_json()["elo_interval"]}
    personas: dict[str, Counter] = defaultdict(Counter)
    for j in judgments:
        personas[j["persona"]][j["outcome"]] += 1

    check_counts: dict[str, dict[str, int]] = defaultdict(lambda: {BETA: 0, PROD: 0})
    for j in judgments:
        for side in (BETA, PROD):
            for f in (j.get("checks") or {}).get(side, []):
                check_counts[f"{f['check_id']} ({f['severity']})"][side] += 1

    reliability = {}
    for side in (BETA, PROD):
        side_arms = [a for a in arms.values() if a.side == side]
        lat = [t.latency_ms for a in side_arms for t in a.turns if not t.error]
        story_tokens = sum(int(t.usage.get("total_tokens") or 0) for a in side_arms for t in a.turns)
        reliability[side] = {
            "arms": len(side_arms),
            "statuses": dict(Counter(a.status.value for a in side_arms)),
            "turns": sum(len(a.turns) for a in side_arms),
            "turn_errors": sum(1 for a in side_arms for t in a.turns if t.error),
            "latency_p50_ms": pct(lat, 0.5), "latency_p95_ms": pct(lat, 0.95),
            "storyteller_tokens": story_tokens,
        }

    judge_tokens = sum(c["input_tokens"] for j in judgments for c in j.get("judge_calls") or [])
    judge_models = sorted({c["model"] for j in judgments for c in j.get("judge_calls") or [] if c["model"]})
    player_tokens = sum(int(t.usage.get("player_tokens") or 0) for a in arms.values() for t in a.turns)
    s = summary.to_json()
    headline = headline_text(s)
    return {
        "experiment_id": manifest.experiment_id,
        "manifest_hash": manifest.manifest_hash,
        "mode": manifest.mode,
        "observational": manifest.observational,
        "targets": manifest.targets,
        "judge": {"requested_model": manifest.judge_model, "resolved_models": judge_models,
                  "rubric_version": manifest.rubric_version, "rubric_hash": manifest.rubric_hash,
                  "calibration_version": manifest.calibration_version},
        "player": {"model": manifest.player_model, "prompt_version": manifest.player_prompt_version},
        "notes": list(manifest.notes),
        "headline": headline,
        "summary": s,
        "strata": strata,
        "personas": {k: dict(v) for k, v in personas.items()},
        "dimensions": dimension_table(judgments, rubric),
        "length_confound": length_confound(judgments, arms),
        "critical": {"regressions": regressions, "counts": critical_counts},
        "checks": dict(check_counts),
        "reliability": reliability,
        "cost": {
            "judge_input_tokens": judge_tokens,
            # None for unpriced (e.g. local Ollama) models
            "judge_usd_estimate": (lambda c: round(c, 4) if c is not None else None)(
                estimate_cost_usd(manifest.judge_model, {"input_tokens": judge_tokens})),
            "player_tokens": player_tokens,
        },
        "calibration": calibration,
        "pairs": [{k: v for k, v in j.items()} for j in judgments],
    }


def fmt_elo(x: Any) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, str):
        return x
    return f"{x:+.0f}"


def fmt_num(x: Any, spec: str = ".2f") -> str:
    return "n/a" if x is None else format(x, spec)


def headline_text(s: Mapping[str, Any]) -> str:
    counts = s["counts"]
    if s["p"] is None:
        return f"No resolved episodes yet | decision: {s['decision']}"
    lo, hi = s["elo_interval"] or ("n/a", "n/a")
    unresolved = counts.get("unresolved", 0)
    total = s["n_pairs"]
    return (f"Beta {fmt_elo(s['elo_delta'])} Elo-equivalent vs prod | {s['p']:.0%} match score | "
            f"95% interval {fmt_elo(lo)} to {fmt_elo(hi)} | {total} paired episodes | "
            f"{unresolved} unresolved | decision: {s['decision']}")


# --------------------------------------------------------------------------- HTML

CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--beta:#2563eb;--prod:#b45309;--good:#15803d;--bad:#b91c1c;--chip:#f0f0ec}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#121214;--panel:#1b1b1f;--ink:#ececef;--muted:#9a9aa3;--line:#2c2c33;--beta:#60a5fa;--prod:#f59e0b;--good:#4ade80;--bad:#f87171;--chip:#26262c;color-scheme:dark}}
:root[data-theme="dark"]{color-scheme:dark;--bg:#121214;--panel:#1b1b1f;--ink:#ececef;--muted:#9a9aa3;--line:#2c2c33;--beta:#60a5fa;--prod:#f59e0b;--good:#4ade80;--bad:#f87171;--chip:#26262c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "IBM Plex Sans",system-ui,-apple-system,"Segoe UI",sans-serif}
.stat b,td,.head{font-variant-numeric:tabular-nums}.stat b{font-family:"IBM Plex Mono",ui-monospace,Consolas,monospace}h1,h2{text-wrap:balance}
main{max-width:1060px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:32px 0 10px}
.muted{color:var(--muted)}.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px;margin:12px 0}
.head{font-size:18px;font-weight:600}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px}.stat b{display:block;font-size:22px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-weight:500}.scroll{overflow-x:auto}.beta{color:var(--beta)}.prod{color:var(--prod)}.bad{color:var(--bad)}.good{color:var(--good)}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 8px;font-size:12px;margin:1px}
details{border-top:1px solid var(--line);padding:8px 0}summary{cursor:pointer}.tx{white-space:pre-wrap;font-size:13px;background:var(--chip);border-radius:8px;padding:8px;margin:4px 0}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media (max-width:700px){.cols{grid-template-columns:1fr}}
.bar{height:8px;background:var(--chip);border-radius:4px;position:relative}.bar i{position:absolute;top:0;bottom:0;left:0;background:var(--beta);border-radius:4px}
"""


def esc(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def share_bar(v: float | None) -> str:
    if v is None:
        return '<span class="muted">n/a</span>'
    return f'<div class="bar" title="{v:.2f}"><i style="width:{v*100:.0f}%"></i></div> {v:.2f}'


def render_arm(arm: ArmTranscript | None) -> str:
    if arm is None:
        return '<p class="muted">missing</p>'
    out = [f'<p class="muted">{esc(arm.status.value)} {esc(arm.status_detail)}</p>',
           f'<div class="tx"><b>Opening</b>\n{esc(arm.opening)}</div>']
    for t in arm.turns:
        meta = " · ".join(x for x in (t.observed.location, t.observed.timestamp, f"{t.latency_ms} ms") if x)
        out.append(f'<div class="tx"><b>Player {t.index}:</b> {esc(t.player_message)}</div>'
                   f'<div class="tx"><span class="muted">{esc(meta)}</span>\n{esc(t.reply or t.error)}</div>')
    return "".join(out)


FONTS = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@500'
         '&family=IBM+Plex+Sans:wght@400;600&display=swap">')


def render_html(report: Mapping[str, Any], arms: Mapping[str, ArmTranscript], *, fragment: bool = False,
                lead: str = "", extra_sections: str = "") -> str:
    """Full standalone document, or (fragment=True) title+style+main only
    for hosts that supply their own document skeleton. `lead` is inserted
    under the title (e.g. the release gate), `extra_sections` before the
    episode drill-down (e.g. other judges' summaries)."""
    s = report["summary"]
    t = report["targets"]
    stats = [
        ("Elo-equivalent", fmt_elo(s["elo_delta"])),
        ("Match score", f"{s['p']:.0%}" if s["p"] is not None else "n/a"),
        ("95% interval", " to ".join(fmt_elo(x) for x in (s["elo_interval"] or ["n/a", "n/a"]))),
        ("Decision", s["decision"]),
        ("Coverage", f"{s['coverage']:.0%}"),
        ("Pairs", str(s["n_pairs"])),
    ]
    head = f"<title>Jev Game Arena</title>{FONTS}<style>{CSS}</style>"
    opener = (f"{head}<main>" if fragment else
              f"<!doctype html><html lang=en><head><meta charset=utf-8>"
              f"<meta name=viewport content='width=device-width,initial-scale=1'>{head}</head><body><main>")
    parts = [opener,
             f"<h1>Jev game arena: beta vs prod</h1><p class=muted>{esc(report['experiment_id'])} · mode "
             f"{esc(report['mode'])}{' · observational' if report['observational'] else ''} · manifest "
             f"{esc(report['manifest_hash'][:12])}</p>",
             lead,
             f"<div class='panel head'>{esc(report['headline'])}</div>",
             "<div class=grid>" + "".join(f"<div class=stat><span class=muted>{esc(k)}</span><b>{esc(v)}</b></div>"
                                          for k, v in stats) + "</div>"]
    parts.append("<div class=panel><b>Why this decision</b><ul>" +
                 "".join(f"<li>{esc(r)}</li>" for r in s["reasons"]) + "</ul>"
                 f"<p class=muted>Pessimistic / optimistic match score (all unresolved to prod / beta): "
                 f"{esc(round(s['p_pessimistic'], 3) if s['p_pessimistic'] is not None else 'n/a')} / "
                 f"{esc(round(s['p_optimistic'], 3) if s['p_optimistic'] is not None else 'n/a')}</p></div>")
    parts.append("<h2>Releases</h2><div class='panel scroll'><table><tr><th></th><th>URL</th><th>Commit</th>"
                 "<th>Deployment</th><th>Environment</th><th>Extractor</th></tr>" +
                 "".join(f"<tr><td class={k}>{k}</td><td>{esc(v.get('base_url'))}</td><td>{esc(str(v.get('commit'))[:12])}</td>"
                         f"<td>{esc(str(v.get('deployment_id') or '-')[:12])}</td><td>{esc(v.get('environment'))}</td>"
                         f"<td>{esc(v.get('extractor_model') or '-')}</td></tr>" for k, v in t.items()) +
                 f"</table><p class=muted>Judge: requested {esc(report['judge']['requested_model'])}, resolved "
                 f"{esc(', '.join(report['judge']['resolved_models']) or 'n/a')} · rubric {esc(report['judge']['rubric_version'])} "
                 f"· {esc(report['judge']['calibration_version'])} · player {esc(report['player']['model'])}</p>" +
                 "".join(f"<p class=muted>Note: {esc(n)}</p>" for n in report["notes"]) + "</div>")
    crit = report["critical"]
    parts.append("<h2>Critical gates</h2><div class=panel>" +
                 ("".join(f"<p class=bad>Blocking: {esc(r)}</p>" for r in crit["regressions"])
                  or "<p class=good>No critical regression (beta never exceeds prod on a critical probe or check).</p>") +
                 "<table><tr><th>Critical finding</th><th class=beta>beta episodes</th><th class=prod>prod episodes</th></tr>" +
                 "".join(f"<tr><td>{esc(k)}</td><td>{v[BETA]}</td><td>{v[PROD]}</td></tr>" for k, v in crit["counts"].items()) +
                 "</table></div>")
    parts.append("<h2>Dimensions</h2><div class='panel scroll'><table><tr><th>Dimension</th><th>Weight</th>"
                 "<th>Beta share of resolved votes</th><th>Resolved</th><th>Unresolved reasons</th>"
                 "<th>Band beta / prod</th></tr>" +
                 "".join(f"<tr><td>{esc(d['title'])}</td><td>{d['weight']:.0%}</td><td>{share_bar(d['beta_share'])}</td>"
                         f"<td>{d['resolved']}/{d['windows']}</td><td>" +
                         "".join(f"<span class=chip>{esc(k)} {v}</span>" for k, v in d["unresolved_reasons"].items()) +
                         f"</td><td>{fmt_num(d['beta_band'])} / {fmt_num(d['prod_band'])}</td></tr>"
                         for d in report["dimensions"]) +
                 "</table><p class=muted>Beta share: 1 = beta better, 0.5 = tie, 0 = prod better, over order-agreeing votes. "
                 "Bands are ordinal 0-4 diagnostics divided by 4, not probabilities.</p></div>")
    lc = report.get("length_confound") or {}
    if lc:
        parts.append("<h2>Length check</h2><div class='panel scroll'><table><tr><th>Game</th><th>Decided</th>"
                     "<th>Longer side won</th><th>Beta minus prod words per reply</th></tr>" +
                     "".join(f"<tr><td>{esc(k)}</td><td>{v['decided']}</td><td>{v['longer_side_win_rate']:.0%}</td>"
                             f"<td>{v['mean_beta_minus_prod_words']:+.0f}</td></tr>" for k, v in lc.items()) +
                     "</table><p class=muted>The judge is told not to reward length but still favors it "
                     "(see the calibration shorten row). A win rate far above 50% means the verdict is "
                     "confounded with reply length.</p></div>")
    parts.append("<h2>By game and persona</h2><div class='panel cols'><div><table><tr><th>Game</th><th>Beta/Tie/Prod/Unres.</th><th>Elo</th></tr>" +
                 "".join(f"<tr><td>{esc(k)}</td><td>{v['counts']['beta_win']}/{v['counts']['tie']}/{v['counts']['prod_win']}/"
                         f"{v['counts']['unresolved']}</td><td>{esc(fmt_elo(v['elo_delta']))}</td></tr>" for k, v in report["strata"].items()) +
                 "</table></div><div><table><tr><th>Persona</th><th>Outcomes</th></tr>" +
                 "".join(f"<tr><td>{esc(k)}</td><td>" + "".join(f"<span class=chip>{esc(o)} {n}</span>" for o, n in v.items()) +
                         "</td></tr>" for k, v in report["personas"].items()) + "</table></div></div>")
    rel = report["reliability"]
    parts.append("<h2>Reliability, latency, cost</h2><div class='panel scroll'><table><tr><th></th><th>Arms</th><th>Turns</th>"
                 "<th>Turn errors</th><th>p50 ms</th><th>p95 ms</th><th>Storyteller tokens</th><th>Statuses</th></tr>" +
                 "".join(f"<tr><td class={k}>{k}</td><td>{v['arms']}</td><td>{v['turns']}</td><td>{v['turn_errors']}</td>"
                         f"<td>{esc(v['latency_p50_ms'])}</td><td>{esc(v['latency_p95_ms'])}</td><td>{v['storyteller_tokens']}</td><td>" +
                         "".join(f"<span class=chip>{esc(a)} {b}</span>" for a, b in v["statuses"].items()) + "</td></tr>"
                         for k, v in rel.items()) +
                 f"</table><p class=muted>Judge input tokens {report['cost']['judge_input_tokens']:,} "
                 f"(~${report['cost']['judge_usd_estimate'] if report['cost']['judge_usd_estimate'] is not None else 'n/a'}) "
                 f"· player tokens {report['cost']['player_tokens']:,}</p>"
                 "<table><tr><th>Deterministic check</th><th class=beta>beta</th><th class=prod>prod</th></tr>" +
                 "".join(f"<tr><td>{esc(k)}</td><td>{v[BETA]}</td><td>{v[PROD]}</td></tr>" for k, v in sorted(report["checks"].items())) +
                 "</table></div>")
    cal = report.get("calibration")
    if cal:
        parts.append("<h2>Judge calibration (mutation sensitivity)</h2><div class='panel scroll'><table><tr><th>Test</th>"
                     "<th>Passed</th><th>Failed</th><th>Unresolved</th><th>Pass rate (resolved)</th></tr>" +
                     "".join(f"<tr><td>{esc(k)}</td><td>{v['passed']}</td><td>{v['failed']}</td><td>{v['unresolved']}</td>"
                             f"<td>{fmt_num(v['pass_rate_resolved'], '.0%')}</td></tr>"
                             for k, v in cal["summary"].items()) + "</table></div>")
    parts.append(extra_sections)
    parts.append("<h2>Episodes</h2><div class=panel>")
    for j in report["pairs"]:
        vote = j.get("episode_vote") or {}
        point = vote.get("point")
        label = f"{j['pair_id']} — <b>{esc(j['outcome'])}</b>" + (f" · vote {point:.2f}" if point is not None else "") + \
                (f" · {esc(j.get('reason'))}" if j.get("reason") else "")
        dims = ""
        for w in j.get("windows") or []:
            dims += f"<p class=muted>Window {w['window']}</p>" + "".join(
                f"<span class=chip>{esc(k)}: {esc(v['reason'] if v['value'] is None else {1.0: 'beta', 0.5: 'tie', 0.0: 'prod'}[v['value']])}</span>"
                for k, v in w["dimensions"].items())
        checks = "".join(f"<div class=muted>{side}: {esc(f['check_id'])} t{f['turn_index']} {esc(f['message'])}</div>"
                         for side in (BETA, PROD) for f in (j.get("checks") or {}).get(side, []))
        parts.append(f"<details><summary>{label}</summary>{dims}{checks}<div class=cols>"
                     f"<div><h3 class=beta>beta</h3>{render_arm(arms.get(j['pair_id'] + '.beta'))}</div>"
                     f"<div><h3 class=prod>prod</h3>{render_arm(arms.get(j['pair_id'] + '.prod'))}</div></div></details>")
    parts.append("</div><p class=muted>Advisory only: promotion stays manual. Elo-equivalent is the expected match score "
                 "under this suite and tie policy, not a share of humans who prefer beta.</p></main>"
                 + ("" if fragment else "</body></html>"))
    return "".join(parts)


# --------------------------------------------------------------------------- multi-judge

def build_arena_report(manifest: ExperimentManifest, arms: Mapping[str, ArmTranscript],
                       judgments_by_judge: Mapping[str, Sequence[Mapping[str, Any]]], rubric: Rubric, *,
                       calibration: Mapping[str, Any] | None = None, iterations: int = 2000,
                       gate_judges: Sequence[str] | None = None) -> dict[str, Any]:
    """One build_report per judge over the SAME played arms, plus the release
    gate computed from `gate_judges` only (others are reported as advisory).
    If none of the configured gate judges ran, every judge that ran counts."""
    from backend.app.evaluation.aggregate import release_gate

    per_judge = {name: build_report(manifest, arms, js, rubric, calibration=calibration, iterations=iterations)
                 for name, js in judgments_by_judge.items()}
    games = sorted({j["story_id"] for js in judgments_by_judge.values() for j in js})
    regressions = sorted({f"[{name}] {r}" for name, rep in per_judge.items() for r in rep["critical"]["regressions"]})
    counted = [n for n in per_judge if gate_judges is None or n in gate_judges] or list(per_judge)
    gate = release_gate({name: {g: per_judge[name]["strata"].get(g, {}).get("p") for g in games}
                         for name in counted}, games,
                        [r for r in regressions if any(r.startswith(f"[{n}]") for n in counted)])
    gate["judges_counted"] = counted
    gate["advisory_judges"] = [n for n in per_judge if n not in counted]
    return {"experiment_id": manifest.experiment_id, "judges": per_judge, "gate": gate}


def gate_panel(gate: Mapping[str, Any]) -> str:
    status = "good" if gate["passed"] else "bad"
    rows = "".join(
        f"<tr><td>{esc(game)}</td><td>" +
        " · ".join(f"{esc(j)} {fmt_num(p, '.0%')}" for j, p in g["match_score_by_judge"].items()) +
        f"</td><td class={'good' if g['passed'] else 'bad'}>{esc(', '.join(g['beta_wins_under']) or 'none')}</td></tr>"
        for game, g in gate["per_game"].items())
    return (f"<div class=panel><div class='head {status}'>Release gate: {'PASS' if gate['passed'] else 'FAIL'}</div>"
            f"<p class=muted>{esc(gate['rule'])}. Counted: {esc(', '.join(gate.get('judges_counted', [])))}"
            f"{'; advisory: ' + esc(', '.join(gate['advisory_judges'])) if gate.get('advisory_judges') else ''}</p>"
            f"<div class=scroll><table><tr><th>Game</th>"
            f"<th>Beta match score by judge</th><th>Beta wins under</th></tr>{rows}</table></div>" +
            "".join(f"<p class=bad>{esc(r)}</p>" for r in gate["reasons"]) + "</div>")


def judge_summary(name: str, report: Mapping[str, Any]) -> str:
    s = report["summary"]
    dims = "".join(f"<tr><td>{esc(d['title'])}</td><td>{share_bar(d['beta_share'])}</td>"
                   f"<td>{d['resolved']}/{d['windows']}</td></tr>" for d in report["dimensions"])
    games = "".join(f"<tr><td>{esc(k)}</td><td>{v['counts']['beta_win']}/{v['counts']['tie']}/"
                    f"{v['counts']['prod_win']}/{v['counts']['unresolved']}</td><td>{esc(fmt_elo(v['elo_delta']))}</td></tr>"
                    for k, v in report["strata"].items())
    return (f"<h2>Judge: {esc(name)}</h2><div class='panel head'>{esc(report['headline'])}</div>"
            f"<div class='panel scroll'><table><tr><th>Game</th><th>Beta/Tie/Prod/Unres.</th><th>Elo</th></tr>{games}"
            f"</table><table><tr><th>Dimension</th><th>Beta share</th><th>Resolved</th></tr>{dims}</table>"
            f"<p class=muted>Resolved model(s): {esc(', '.join(report['judge']['resolved_models']) or 'n/a')} · "
            f"judge input tokens {report['cost']['judge_input_tokens']:,} · decision {esc(s['decision'])}</p></div>")


def render_arena_html(arena: Mapping[str, Any], arms: Mapping[str, ArmTranscript], *, fragment: bool = False) -> str:
    """Primary judge renders the full page; the gate leads it and every other
    judge adds a summary section (transcripts are shown once)."""
    names = list(arena["judges"])
    primary = arena["judges"][names[0]]
    extra = "".join(judge_summary(n, arena["judges"][n]) for n in names[1:])
    lead = gate_panel(arena["gate"]) + f"<p class=muted>Detailed sections below use judge: {esc(names[0])}</p>"
    return render_html(primary, arms, fragment=fragment, lead=lead, extra_sections=extra)


def precheck_verdict(arena: Mapping[str, Any]) -> dict[str, Any]:
    """Cheap offline screen (tier 1). Judged on engine RELIABILITY and the
    deterministic checks only - quality verdicts from a small local model are
    reported but never decide it. Beta must not fail more than its baseline:
    no extra target failures or turn errors, no deterministic check firing
    more often, and at least one completed arm."""
    first = next(iter(arena["judges"].values()))
    rel = first["reliability"]
    reasons: list[str] = []
    fails = {side: rel[side]["statuses"].get("target_failure", 0) for side in (BETA, PROD)}
    if fails[BETA] > fails[PROD]:
        reasons.append(f"beta target failures {fails[BETA]} > baseline {fails[PROD]}")
    if rel[BETA]["turn_errors"] > rel[PROD]["turn_errors"]:
        reasons.append(f"beta turn errors {rel[BETA]['turn_errors']} > baseline {rel[PROD]['turn_errors']}")
    for check, counts in sorted(first["checks"].items()):
        if counts[BETA] > counts[PROD]:
            reasons.append(f"{check}: beta {counts[BETA]} > baseline {counts[PROD]}")
    played = rel[BETA]["statuses"].get("complete", 0) + rel[BETA]["statuses"].get("ended", 0)
    if not played:
        reasons.append("beta completed no games")
    return {"passed": not reasons, "reasons": reasons,
            "rule": "no new target failures, turn errors or deterministic-check findings vs baseline",
            "quality_advisory": {name: rep["headline"] for name, rep in arena["judges"].items()}}
