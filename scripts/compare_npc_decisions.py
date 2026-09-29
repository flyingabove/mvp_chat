"""Side-by-side: how the rules and Jev answer the same Terrace confession / leave-together ask.

Each fixture is built through the real engine (real Terrace story data, real
appraisal so the "what you noticed" history is genuine), then answered by
both deciders under identical information. Prints one row per fixture and a
summary. Jev calls are small classifications (no language model); set
TYPESAFE_ENABLED=true and a TYPESAFE_API_KEY (.env.test has one) to run them.

    python scripts/compare_npc_decisions.py            # rules vs live Jev
    python scripts/compare_npc_decisions.py --rules-only
    python scripts/compare_npc_decisions.py --show-view 2
"""
import argparse
import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.getcwd())
if "--rules-only" not in sys.argv:
    os.environ.setdefault("TYPESAFE_ENABLED", "true")
sys.stdout.reconfigure(encoding="utf-8")

from backend.app.engine.character_graph import CharacterGraph  # noqa: E402
from backend.app.engine.rules.personality import personalities  # noqa: E402
from backend.app.engine.rules.tracks import social_rules  # noqa: E402
from backend.app.engine.story_loader import build_story_registry  # noqa: E402
from backend.app.engine.world_model import npc_decision  # noqa: E402
from backend.app.engine.world_model.appraisal import appraise_behaviors  # noqa: E402
from backend.app.engine.world_model.persona import SelfClaim  # noqa: E402
from backend.app.engine.world_model.social_acts import SocialAct, act_specs, assess  # noqa: E402
from backend.app.engine.world_model.standing import Standing  # noqa: E402
from tests.backend.app.engine.world_model.helpers import make_model  # noqa: E402

CFG = build_story_registry()["six_strangers"]["raw"]
NAMES = {c["key"]: c["name"] for c in CFG["characters"]}
GOOD = ["helpful", "attentive", "supportive_of_goals", "honest"]
BAD = ["rude", "boastful", "pushy", "dismissive"]

# id, target, act, standing, behaviors the target noticed, feelings (trust, affection, suspicion), claims, note
FIXTURES = [
    ("warm and ready", "masako", "confess", 52, GOOD, (0.5, 0.5, 0.0), [], "everything points to yes"),
    ("ready on paper, cold in practice", "natsumi", "confess", 52, BAD, (-0.1, 0.1, 0.5), [], "score is there, behavior is not"),
    ("just inside the tier, no history", "yuriko", "confess", 47, [], (0.1, 0.1, 0.0), [], "thin evidence"),
    ("caught in a contradiction", "hayato", "confess", 55, GOOD[:2], (0.3, 0.3, 0.6),
     [("smokes", "no", 1), ("smokes", "yes", 2)], "conflicting claims"),
    ("great behavior, below the tier", "momoka", "confess", 30, GOOD, (0.6, 0.6, 0.0), [], "rules: not yet; Jev may say yes -> clamped"),
    ("a couple ready to leave", "masako", "ask_leave_together", 82, GOOD, (0.7, 0.8, 0.0), [], "partner, 82"),
    ("a couple, but pushy lately", "natsumi", "ask_leave_together", 82, BAD[:3], (0.2, 0.3, 0.3), [], "partner, recent friction"),
    ("a couple, standing not enough", "riko", "ask_leave_together", 68, GOOD, (0.6, 0.6, 0.0), [], "partner, 68 < 70"),
]


def build(row):
    name, target, kind, value, behaviors, (trust, affection, suspicion), claims, _ = row
    others = [c for c in ("makoto", "yuki") if c != target][:1]
    model = make_model({target: "kitchen", **{c: "kitchen" for c in others}})
    for cid in model.characters:
        model.characters[cid].name = NAMES.get(cid, cid)
    model.player_name = "Paul"
    rules = social_rules(CFG)
    model.standing.bind(rules.tracks)
    tags = [SimpleNamespace(from_id="player", to_id=target, tag=t) for t in behaviors]
    genders = {c["key"]: c["gender"] for c in CFG["characters"]}
    genders["player"] = "F" if genders[target] == "M" else "M"
    appraise_behaviors(model, rules, personalities(CFG), tags, set(model.characters), None, turn_key="c",
                       genders=genders)
    model.standing.standings[(target, "player", "romance")] = Standing(value=value)
    model.first_met_day[target] = 0
    model.world.minute = 6 * 24 * 60
    for key, val, turn in claims:
        model.persona.claim(SelfClaim("player", key, val, (target,), turn, turn))
    if kind == "ask_leave_together":
        model.romance_relationship_partner = target
    graph = CharacterGraph.from_dict({"edges": [{"from_id": target, "to_id": "player", "state": {
        "trust": trust, "affection": affection, "suspicion": suspicion}}]})
    act = SocialAct(kind, target)
    spec = act_specs(CFG)[kind]
    assessment = assess(model, spec, act, {target})
    view = npc_decision.target_view(model, spec, act, CFG, model.names(), graph, ready=assessment.can_accept)
    return act, assessment, view


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules-only", action="store_true")
    parser.add_argument("--show-view", type=int, help="print the target's own-view text for fixture N (1-based)")
    args = parser.parse_args()

    rows = []
    for index, row in enumerate(FIXTURES, 1):
        act, assessment, view = build(row)
        if args.show_view == index:
            print(f"--- own view for fixture {index} ({row[0]}) ---\n{view}\n")
        judgment = None
        if not args.rules_only and not assessment.hard:
            judgment = await npc_decision.judge(npc_decision.jev_decision(act.target, act), view)
        verdict, record = npc_decision.merge(assessment, "jev", judgment)
        rows.append((row, assessment, judgment, verdict, record))

    print(f"{'#':>2} {'fixture':34} {'act':19} {'rules':8} {'jev (raw)':9} {'conf':5} {'P(yes)':6} {'jev mode':8} note")
    for index, (row, assessment, judgment, verdict, record) in enumerate(rows, 1):
        raw = judgment.choice if judgment and judgment.choice else ("-" if judgment is None else "n/a")
        conf = f"{judgment.confidence:.2f}" if judgment and judgment.confidence is not None else "-"
        p_yes = dict(judgment.probabilities).get("accept") if judgment else None
        p_yes = f"{p_yes:.2f}" if p_yes is not None else "-"
        flag = " [clamped]" if record.clamped else (f" [{record.note}]" if record.note and record.note != "hard rule" else "")
        print(f"{index:>2} {row[0]:34} {row[2]:19} {assessment.verdict.answer:8} {raw:9} {conf:5} {p_yes:6} {verdict.answer:8}{flag}")

    judged = [r for r in rows if r[2] is not None and r[2].choice]
    stricter = sum(1 for r in judged if r[4].final != r[1].verdict.answer)
    print(f"\nrules-only mode: {sum(1 for r in rows if r[1].verdict.answer == 'accept')}/{len(rows)} yes | "
          f"jev mode: {sum(1 for r in rows if r[3].answer == 'accept')}/{len(rows)} yes")
    if args.rules_only:
        return 0
    agree = sum(1 for r in judged if r[2].choice == r[1].verdict.answer)
    print(f"jev answered {len(judged)}/{len(rows)} judged fixtures; agrees with rules on {agree}; "
          f"changes the outcome on {stricter}; clamped {sum(1 for r in rows if r[4].clamped)}")
    unavailable = [r for r in rows if r[2] is not None and not r[2].choice]
    if unavailable:
        print(f"jev unavailable for {len(unavailable)} fixture(s): {sorted({r[2].reason for r in unavailable})}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
