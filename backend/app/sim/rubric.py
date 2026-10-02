"""The script rubric: is a scene, a day, a season engaging drama? (P-05, design: BL-87)

Each rubric item is one bounded question with five anchored answers (1 to 5, reported as 2 to 10, the Black List
scale where 8 or more is excellent). Jev answers them through the shared decision resolver, the same path and
pattern as `world_model/promise_judge.py`: a bounded classifier, never free prose, never a language model call.

Three levels, scored from the text a `SeasonRunner` (or a hosted session) leaves behind:
- scene  S1-S8: one written scene;
- day    E1-E6: one story day, the episode, seen as its scenes in order;
- season R1-R5: the whole run, seen as one digest per day.

Verdict (coverage-reader style): Recommend when the mean is at least 8, no item is below 5 and plausibility is at
least 8; Consider when the mean is at least 6; otherwise Pass. A day or season is Recommended only with a plausibility
figure, the lowest S6 over its scenes. While `CALIBRATED` is False (fewer than `LABELS_REQUIRED` human-labelled scenes
agree with Jev, see `tests/eval_cases/script_rubric/README.md`) every report says it is advisory.

Generic: nothing here knows a story, a character or a mode.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from backend.app.llm.decisions.types import Criticality, Decision, DecisionBatch, FallbackReason, Provider

TASK = "script_rubric"
LEVELS = ("scene", "day", "season")
CHOICES = ("1", "2", "3", "4", "5")
RECOMMEND_MEAN, CONSIDER_MEAN, RECOMMEND_FLOOR, RECOMMEND_PLAUSIBILITY = 8.0, 6.0, 5, 8
PLAUSIBILITY_ITEM = "S6"
LABELS_REQUIRED = 60          # human-labelled scenes before the rubric may gate anything
CALIBRATED = False            # flip only when the agreement bar in script_rubric_eval.py holds on the held-out set
ADVISORY_NOTE = ("ADVISORY: the rubric has not been calibrated against human labels yet "
                 f"(needs {LABELS_REQUIRED} labelled scenes, see tests/eval_cases/script_rubric/README.md); "
                 "use it to compare runs, not to gate anything.")
SCENE_CLIP, DAY_CLIP, SEASON_CLIP = 1800, 900, 700      # characters of each part shown to the judge


@dataclass(frozen=True)
class Item:
    id: str
    level: str
    title: str
    question: str
    anchors: tuple[str, str, str, str, str]      # what a 1, 2, 3, 4 and 5 look like


ITEMS: tuple[Item, ...] = (
    # ---------------------------------------------------------------------------------------------------- scene
    Item("S1", "scene", "Value turn",
         "Does something important to a character turn (hope to fear, trust to suspicion, closeness to distance, "
         "or the reverse) because of what happens in this scene?",
         ("Nothing changes; pleasantries or description only.",
          "A faint shift that is mentioned but costs nobody anything.",
          "A clear small change in how someone stands or feels.",
          "A real turn in someone's position, caused by the characters' own choices.",
          "A sharp turn that reframes the situation and cannot be undone.")),
    Item("S2", "scene", "Clear conflict",
         "Is there a want running into an obstacle (a person, a secret, a rule, a feeling) that the reader can name?",
         ("No want and no obstacle.",
          "A want is hinted but nothing stands in its way.",
          "One want and one obstacle, but low stakes or only implied.",
          "A clear want against a clear obstacle with something at stake.",
          "Competing wants collide with high, specific stakes the reader can name at once.")),
    Item("S3", "scene", "True to character, distinct voices",
         "Do the characters act on their own personality, goals and history, and could you tell who is speaking "
         "without the name?",
         ("Interchangeable voices; characters do whatever the scene needs.",
          "Mostly generic, with one or two personal touches.",
          "Recognisable traits, but voices blur together.",
          "Each acts from who they are; most lines sound like their speaker.",
          "Every choice and line is unmistakably theirs and surprising yet inevitable.")),
    Item("S4", "scene", "Subtext and irony",
         "Do feelings and intentions show through behaviour and what is left unsaid, with something the reader "
         "understands that a character does not?",
         ("Everyone says exactly what they feel and mean.",
          "Mostly stated; one gesture hints at more.",
          "Some subtext, but the key feelings are still announced.",
          "Real gap between words and meaning; at least one beat works through behaviour alone.",
          "Sustained subtext and dramatic irony; the unsaid is the scene.")),
    Item("S5", "scene", "Heightening",
         "Does the tension or comedy build inside the scene, each beat going a step further than the last?",
         ("Flat, or the same beat repeated.",
          "A beat or two of movement, then it stalls.",
          "Some build, but it plateaus or resolves too soon.",
          "A steady build to a peak.",
          "Each beat raises the last; the scene ends at its highest point.")),
    Item("S6", "scene", "Plausibility",
         "Exaggerated is fine, but is it believable as real people in this situation: no telepathy, nobody knowing "
         "what they could not know, no invented facts, no one acting out of character?",
         ("Breaks the world: knows hidden things, contradicts established facts, or acts impossibly.",
          "Several implausible moments that pull the reader out.",
          "Mostly believable with one clear slip.",
          "Believable throughout; any exaggeration is earned by the situation.",
          "Dramatic yet entirely believable; every reaction and piece of knowledge is grounded.")),
    Item("S7", "scene", "Ends on a hook",
         "Does the scene end on an open question, a turn or an unresolved feeling that makes you want the next scene?",
         ("Ends flatly or trails off.",
          "Ends on a polite closing beat.",
          "A mild loose end.",
          "Ends on a clear open question or turn.",
          "Ends on a hook that demands the next scene.")),
    Item("S8", "scene", "Emotional pull",
         "Does the scene make you feel something (tension, laughter, tenderness, dread, embarrassment)?",
         ("Nothing; inert.",
          "Faint interest only.",
          "A moment or two of feeling.",
          "Strong feeling in more than one moment.",
          "Gripping; you feel it throughout.")),
    # ------------------------------------------------------------------------------------------------------- day
    Item("E1", "day", "A, B and C threads",
         "Do the day's scenes carry more than one storyline (a main thread, a secondary one, a light runner), with at "
         "least one thread that returns?",
         ("One undifferentiated stream of scenes.",
          "Two threads in name, never interleaved.",
          "A main and a secondary thread, no runner.",
          "Main and secondary threads interleaved, with a runner that returns.",
          "A main, a secondary and a runner, interwoven so each scene serves more than one.")),
    Item("E2", "day", "Complications progress",
         "Does each scene complicate the situation further rather than repeat an earlier beat?",
         ("The same beat over and over.",
          "Mostly repetition with small variations.",
          "Some progress, some repeated beats.",
          "Each scene adds something new that matters to the next.",
          "Every scene escalates or reverses the one before it.")),
    Item("E3", "day", "Setup pays off",
         "Is something planted earlier in the day (or carried in from before) paid off later in it?",
         ("Nothing planted, nothing paid.",
          "Something is planted and forgotten.",
          "A small payoff, mostly by coincidence.",
          "A planted detail pays off clearly.",
          "A setup pays off in a way that recontextualises an earlier scene.")),
    Item("E4", "day", "Ensemble balance",
         "Do several characters get meaningful moments, with second leads and foils mattering, and nobody who matters "
         "forgotten?",
         ("One or two characters hog every scene; the rest are furniture.",
          "A lopsided ensemble with token appearances.",
          "Most characters appear, but only two or three matter.",
          "Most characters matter and some act as foils.",
          "A balanced ensemble where every appearance moves someone's story.")),
    Item("E5", "day", "Cliffhanger",
         "Does the day end on an open question or turn that makes you want the next day?",
         ("Ends flatly; everything is settled.",
          "Ends on a quiet closing image.",
          "A mild loose end.",
          "Ends on a clear open question.",
          "Ends on a cliffhanger that demands the next episode.")),
    Item("E6", "day", "Mix of tones",
         "Does the day move between tones (comic, tender, tense, awkward) rather than staying in one register?",
         ("One flat register throughout.",
          "Two tones, one barely present.",
          "A couple of tones in separate blocks.",
          "Several tones that contrast well.",
          "Tones shift with timing that makes each land harder.")),
    # ----------------------------------------------------------------------------------------------------- season
    Item("R1", "season", "Follows its arc",
         "Do the days follow an arc: meeting, friction, a first move, a midpoint where someone turns active, a crisis, "
         "a payoff?",
         ("No arc; days are interchangeable.",
          "Events occur but without order or build.",
          "Some arc shape, with key beats missing or out of order.",
          "Most arc beats are present and in a sensible order.",
          "A clear arc whose beats arrive on time and build on each other.")),
    Item("R2", "season", "Characters change",
         "Do the main characters end the season different from how they began, because of what happened?",
         ("No one changes.",
          "Superficial changes only.",
          "One character visibly changes.",
          "Several characters change in ways earned by events.",
          "Characters are transformed, and the change is what the season is about.")),
    Item("R3", "season", "Twists are earned",
         "Are the surprises set up and plausible, so that looking back they feel inevitable?",
         ("No surprises, or surprises from nowhere.",
          "Surprises are arbitrary.",
          "A surprise or two with partial setup.",
          "Surprises are set up and believable.",
          "Surprises are planted early and recontextualise what came before.")),
    Item("R4", "season", "Premise delivers",
         "Does the season deliver what its premise promises (the situation, the relationships, the stakes)?",
         ("The premise is absent from the story.",
          "The premise is visible but barely used.",
          "The premise delivers in parts.",
          "The premise delivers its main promises.",
          "The premise delivers fully and surprises beyond its obvious promises.")),
    Item("R5", "season", "Bingeability",
         "Would a viewer want the next episode, and the one after?",
         ("No.",
          "Only out of obligation.",
          "Maybe, if nothing else is on.",
          "Yes, there is a pull to continue.",
          "Yes; it is hard to stop.")),
)
BY_ID = {item.id: item for item in ITEMS}


def items_for(level: str) -> tuple[Item, ...]:
    if level not in LEVELS:
        raise ValueError(f"unknown rubric level {level!r}; expected one of {LEVELS}")
    return tuple(item for item in ITEMS if item.level == level)


def decision_for(item: Item) -> Decision:
    """The item as one bounded choice question: the five anchors are the options."""
    return Decision(
        id=f"rubric_{item.id}",
        task=TASK,
        kind="choice",
        instructions=(f"You are a script reader scoring drama. Criterion: {item.title}. {item.question} "
                      "Choose the one description that best fits the text, judging only what is on the page. "
                      "Do not reward length. Rate flat, repetitive or merely pleasant text low and reserve "
                      "5 for work you would show to others."),
        criteria={choice: anchor for choice, anchor in zip(CHOICES, item.anchors)},
        criticality=Criticality.DEGRADABLE,
        allowed=frozenset(CHOICES),
        none_option=None,
    )


# ---------------------------------------------------------------------------------------------------- the text
def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def scene_view(text: str, setting: str = "") -> str:
    head = f"Setting: {setting}\n\n" if setting.strip() else ""
    return f"{head}The scene:\n{_clip(text, SCENE_CLIP)}"


def day_view(scenes: Sequence[str]) -> str:
    return "One story day, its scenes in order:\n" + "\n".join(
        f"[Scene {i}] {_clip(scene, DAY_CLIP)}" for i, scene in enumerate(scenes, 1))


def season_view(days: Sequence[str]) -> str:
    return "A whole season, one digest per story day, in order:\n" + "\n".join(
        f"[Day {i}] {_clip(day, SEASON_CLIP)}" for i, day in enumerate(days, 1))


# ------------------------------------------------------------------------------------------------------ scoring
@dataclass(frozen=True)
class ItemScore:
    item_id: str
    choice: Optional[int] = None         # 1-5, None when Jev gave no usable answer
    confidence: Optional[float] = None
    reason: str = ""

    @property
    def score(self) -> Optional[int]:
        return None if self.choice is None else 2 * self.choice


@dataclass(frozen=True)
class LevelScore:
    level: str
    items: tuple[ItemScore, ...]
    plausibility: Optional[int]
    mean: Optional[float]
    low: Optional[int]
    verdict: str                         # Recommend | Consider | Pass | Unscored

    @property
    def complete(self) -> bool:
        return all(i.choice is not None for i in self.items)

    def scores(self) -> dict[str, Optional[int]]:
        return {i.item_id: i.score for i in self.items}


def verdict_for(mean: Optional[float], low: Optional[int], plausibility: Optional[int]) -> str:
    """Recommend: mean >= 8, no item below 5, plausibility >= 8. Consider: mean >= 6. Otherwise Pass."""
    if mean is None or low is None:
        return "Unscored"
    if mean >= RECOMMEND_MEAN and low >= RECOMMEND_FLOOR and plausibility is not None \
            and plausibility >= RECOMMEND_PLAUSIBILITY:
        return "Recommend"
    return "Consider" if mean >= CONSIDER_MEAN else "Pass"


def aggregate(level: str, items: Sequence[ItemScore], plausibility: Optional[int] = None) -> LevelScore:
    """Mean and floor over the level's items; a level with any unanswered item is Unscored, never a partial score."""
    scores = [i.score for i in items]
    complete = bool(scores) and all(s is not None for s in scores)
    if level == "scene":
        plausibility = next((i.score for i in items if i.item_id == PLAUSIBILITY_ITEM), None)
    mean = sum(scores) / len(scores) if complete else None
    low = min(scores) if complete else None
    return LevelScore(level, tuple(items), plausibility, mean, low, verdict_for(mean, low, plausibility))


_resolver: Any = None


def default_resolver() -> Any:
    global _resolver
    if _resolver is None:
        from backend.app.engine.world_model.npc_decision import build_resolver
        _resolver = build_resolver(TASK)
    return _resolver


def reset_resolver_for_tests() -> None:
    global _resolver
    _resolver = None


def _chunks(decisions: Sequence[Decision]) -> list[tuple[Decision, ...]]:
    from backend.app.config import settings
    size = max(1, int(getattr(settings, "JEV_MAX_QUESTIONS_PER_BATCH", 60)))
    return [tuple(decisions[i:i + size]) for i in range(0, len(decisions), size)]


def _item_score(item: Item, answer: Any, reason: Optional[FallbackReason]) -> ItemScore:
    usable = answer is not None and answer.provider is Provider.JEV and answer.usable and answer.choice in CHOICES
    if usable:
        return ItemScore(item.id, int(answer.choice), answer.confidence)
    return ItemScore(item.id, None, None, reason.value if reason is not None else "unanswered")


async def judge_items(level: str, view: str, resolver: Any = None) -> list[ItemScore]:
    """Ask every item of `level` about `view`. Never raises; an item Jev cannot settle comes back with no choice."""
    from backend.app.llm.protocols import LegacyExtractionRequest
    resolver = resolver or default_resolver()
    items = items_for(level)
    decisions = {item.id: decision_for(item) for item in items}
    answers: dict[str, Any] = {}
    reasons: dict[str, FallbackReason] = {}
    for part in _chunks(list(decisions.values())):
        batch = DecisionBatch(name=f"{TASK}_{level}", state=view, decisions=part)
        try:
            outcome = await resolver.resolve([batch], LegacyExtractionRequest(
                user_msg="", world_locations={}, character_key_to_name={}))
        except Exception:
            for decision in part:
                reasons[decision.id] = FallbackReason.HTTP_ERROR
            continue
        answers.update(outcome.answers)
        reasons.update(outcome.fallback_reasons)
    return [_item_score(item, answers.get(decisions[item.id].id), reasons.get(decisions[item.id].id))
            for item in items]


async def judge_level(level: str, view: str, resolver: Any = None, plausibility: Optional[int] = None) -> LevelScore:
    return aggregate(level, await judge_items(level, view, resolver), plausibility)


# ------------------------------------------------------------------------------------------------ whole season
@dataclass(frozen=True)
class SeasonReport:
    scenes: tuple[tuple[LevelScore, ...], ...]       # per day, per scene
    days: tuple[LevelScore, ...]
    season: LevelScore
    advisory: bool

    def render(self) -> str:
        lines = [ADVISORY_NOTE] if self.advisory else []
        for d, (scenes, day) in enumerate(zip(self.scenes, self.days), 1):
            lines.append(f"day {d}: {_line(day)}")
            lines.extend(f"  scene {s}: {_line(scene)}" for s, scene in enumerate(scenes, 1))
        lines.append(f"season: {_line(self.season)}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        def level(score: LevelScore) -> dict:
            return {"level": score.level, "verdict": score.verdict, "mean": score.mean, "low": score.low,
                    "plausibility": score.plausibility, "scores": score.scores()}
        return {"advisory": self.advisory, "note": ADVISORY_NOTE if self.advisory else "",
                "scenes": [[level(s) for s in day] for day in self.scenes],
                "days": [level(d) for d in self.days], "season": level(self.season)}


def _line(score: LevelScore) -> str:
    mean = "n/a" if score.mean is None else f"{score.mean:.1f}"
    missing = "" if score.complete else f" ({sum(1 for i in score.items if i.choice is None)} item(s) unanswered)"
    return f"{score.verdict} mean {mean}{missing}"


async def score_season(days: Sequence[Sequence[str]], resolver: Any = None, concurrency: int = 3) -> SeasonReport:
    """Score every scene, every day and the season. `days` is a list of days, each a list of scene texts."""
    gate = asyncio.Semaphore(max(1, concurrency))

    async def bounded(coro):
        async with gate:
            return await coro

    scene_scores = [list(await asyncio.gather(*[bounded(judge_level("scene", scene_view(text), resolver))
                                                 for text in scenes])) for scenes in days]
    day_scores = []
    for scenes, scored in zip(days, scene_scores):
        floor = [s.plausibility for s in scored if s.plausibility is not None]
        plausibility = min(floor) if floor and len(floor) == len(scored) else None
        day_scores.append(await judge_level("day", day_view(scenes), resolver, plausibility))
    digests = [" / ".join(_clip(t, 200) for t in scenes) for scenes in days]
    plaus = [d.plausibility for d in day_scores if d.plausibility is not None]
    season = await judge_level("season", season_view(digests), resolver,
                               min(plaus) if plaus and len(plaus) == len(day_scores) else None)
    return SeasonReport(tuple(tuple(s) for s in scene_scores), tuple(day_scores), season, advisory=not CALIBRATED)
