#!/usr/bin/env python
"""The work board: how parallel agents find, claim and finish tasks from `documentation/plan/`.

The plan is one small file per task, read from `origin/beta` (always current, no pull needed). Claims live on a
separate `work` branch so taking a task never pushes to `beta` (a beta push redeploys Railway). A claim is a file
`claims/<id>.json` committed with git plumbing and pushed WITHOUT force: git itself is the lock, so two agents can
never both win the same task. Claims carry a lease and expire, so a crashed agent cannot block a task forever.

    python scripts/work.py status            what is ready, blocked, claimed
    python scripts/work.py next              the unblocked tasks you could take, best first
    python scripts/work.py claim [P-07]      take a task (the best one if no id) and print its spec
    python scripts/work.py renew P-07        extend your lease
    python scripts/work.py release P-07      give a task back without finishing it
    python scripts/work.py done P-07         after your fixing commit is on origin/beta
    python scripts/work.py gc                drop claims whose task is finished or whose lease ran out
    python scripts/work.py check             validate the plan files in your checkout

Identity: `--agent`, else `WORK_AGENT`, else the checkout folder name. Several agents in ONE checkout must each set
`WORK_AGENT`. Standard library only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

PLAN_DIR = "documentation/plan"
CLAIMS_DIR = "claims"
DEFAULT_HOURS = 4.0
MAX_RETRIES = 6
TASK_FILE = re.compile(r"^(P-\d+)(?:-[\w.-]*)?\.md$")
SIZES = ("S", "M", "L")
NL = "\n"
REJECTED = ("rejected", "non-fast-forward", "fetch first", "stale info", "already exists")


class BoardError(RuntimeError):
    """Something the caller should read and act on (never a traceback)."""


# ----------------------------------------------------------------------------------------------- plan files
@dataclass
class Task:
    id: str
    title: str
    stage: int
    size: str
    depends_on: list[str] = field(default_factory=list)
    touches: list[str] = field(default_factory=list)
    backlog: str = ""
    path: str = ""
    body: str = ""


def _list(value: str) -> list[str]:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [item.strip().strip("'\"") for item in value.split(",") if item.strip().strip("'\"")]


def parse_task(path: str, text: str) -> Task:
    """Front matter is `key: value` lines between two `---` lines; lists are `[a, b]`."""
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n") or "\n---\n" not in text[4:] + "\n":
        raise BoardError(f"{path}: missing front matter (--- ... ---)")
    head, _, body = text[4:].partition("\n---\n")
    fields: dict[str, str] = {}
    for line in head.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, sep, value = line.partition(":")
            if not sep:
                raise BoardError(f"{path}: bad front matter line {line!r}")
            fields[key.strip()] = value.strip()
    for key in ("id", "title", "stage", "size", "touches"):
        if not fields.get(key):
            raise BoardError(f"{path}: front matter needs {key!r}")
    if not re.fullmatch(r"P-\d+", fields["id"]):
        raise BoardError(f"{path}: id must look like P-07, got {fields['id']!r}")
    if not fields["stage"].isdigit():
        raise BoardError(f"{path}: stage must be a whole number")
    if fields["size"] not in SIZES:
        raise BoardError(f"{path}: size must be one of {SIZES}")
    base = Path(path).name
    match = TASK_FILE.match(base)
    if not match or match.group(1) != fields["id"]:
        raise BoardError(f"{path}: file name must start with the task id {fields['id']}")
    return Task(fields["id"], fields["title"], int(fields["stage"]), fields["size"], _list(fields.get("depends_on", "")),
                _list(fields["touches"]), fields.get("backlog", ""), path, body.strip("\n"))


def _norm(touch: str) -> str:
    return touch.replace("\\", "/").strip().rstrip("*").rstrip("/")


def overlaps(a: list[str], b: list[str]) -> Optional[tuple[str, str]]:
    """The first pair of paths where one equals or contains the other (directories are prefixes)."""
    for x in a:
        for y in b:
            nx, ny = _norm(x), _norm(y)
            if nx and ny and (nx == ny or nx.startswith(ny + "/") or ny.startswith(nx + "/")):
                return x, y
    return None


def rank(task: Task) -> tuple[int, int]:
    return task.stage, int(task.id[2:])


# ------------------------------------------------------------------------------------------------- claims
@dataclass
class Claim:
    id: str
    agent: str
    claimed_at: str
    lease_until: str
    note: str = ""

    def live(self, now: datetime) -> bool:
        return datetime.fromisoformat(self.lease_until) > now

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True) + "\n"


def default_agent(root: Path) -> str:
    return os.environ.get("WORK_AGENT") or root.name


class Board:
    def __init__(self, root: Path, remote: str = "origin", plan_branch: str = "beta", claims_branch: str = "work",
                 now: Optional[Callable[[], datetime]] = None) -> None:
        self.root, self.remote = Path(root), remote
        self.plan_branch, self.claims_branch = plan_branch, claims_branch
        self.now = now or (lambda: datetime.now(timezone.utc))

    # -- git plumbing
    def git(self, *args: str, input: Optional[str] = None, env: Optional[dict] = None,
            check: bool = True) -> subprocess.CompletedProcess:
        merged = {**os.environ, **(env or {})}
        done = subprocess.run(["git", *args], cwd=self.root, input=input, text=True, encoding="utf-8",
                              capture_output=True, env=merged)
        if check and done.returncode != 0:
            raise BoardError(f"git {' '.join(args[:2])} failed: {(done.stderr or done.stdout).strip()}")
        return done

    def _fetch(self, branch: str) -> Optional[str]:
        """Fetch one remote branch; its commit id, or None when the branch does not exist yet."""
        done = self.git("fetch", self.remote, f"+refs/heads/{branch}:refs/remotes/{self.remote}/{branch}", check=False)
        if done.returncode != 0:
            if "couldn't find remote ref" in done.stderr:
                return None
            raise BoardError(f"cannot reach {self.remote} (the board needs the network): {done.stderr.strip()}")
        return self.git("rev-parse", f"refs/remotes/{self.remote}/{branch}").stdout.strip()

    def _names(self, ref: str, prefix: str) -> list[str]:
        done = self.git("ls-tree", "-r", "--name-only", ref, "--", prefix, check=False)
        return [n for n in done.stdout.splitlines() if n] if done.returncode == 0 else []

    def _show_many(self, ref: str, paths: list[str]) -> dict[str, str]:
        """The text of several files at `ref` through ONE git process (git is slow to start, especially on Windows)."""
        if not paths:
            return {}
        request = "".join(f"{ref}:{p}{NL}" for p in paths).encode()
        done = subprocess.run(["git", "cat-file", "--batch"], cwd=self.root, input=request, capture_output=True)
        if done.returncode != 0:
            raise BoardError(f"git cat-file failed: {done.stderr.decode(errors='replace').strip()}")
        data, texts = done.stdout, {}
        for path in paths:
            end = data.index(b"\n")
            header = data[:end].decode().split()
            if len(header) != 3 or header[1] != "blob":
                raise BoardError(f"cannot read {path} at {ref}")
            size = int(header[2])
            texts[path] = data[end + 1:end + 1 + size].decode("utf-8")
            data = data[end + 1 + size + 1:]
        return texts

    # -- the plan (from origin/beta)
    def plan(self) -> dict[str, Task]:
        tip = self._fetch(self.plan_branch)
        if tip is None:
            raise BoardError(f"{self.remote}/{self.plan_branch} does not exist")
        tasks: dict[str, Task] = {}
        names = [n for n in self._names(tip, PLAN_DIR) if TASK_FILE.match(Path(n).name)]
        for name, text in self._show_many(tip, names).items():
            task = parse_task(name, text)
            if task.id in tasks:
                raise BoardError(f"duplicate task id {task.id}")
            tasks[task.id] = task
        return tasks

    def known_ids(self, current: set[str]) -> set[str]:
        """Every task id that ever existed: current files plus those added in history (finished = file deleted)."""
        done = self.git("log", f"refs/remotes/{self.remote}/{self.plan_branch}", "--diff-filter=A", "--name-only",
                        "--format=", "--", PLAN_DIR, check=False)
        seen = {m.group(1) for n in done.stdout.splitlines() if (m := TASK_FILE.match(Path(n).name))}
        return seen | current

    # -- claims (from origin/work)
    def _read_claims(self, tip: Optional[str]) -> dict[str, Claim]:
        if tip is None:
            return {}
        claims = {}
        names = [n for n in self._names(tip, CLAIMS_DIR) if n.endswith(".json")]
        for text in self._show_many(tip, names).values():
            claim = Claim(**json.loads(text))
            claims[claim.id] = claim
        return claims

    def claims(self) -> dict[str, Claim]:
        return self._read_claims(self._fetch(self.claims_branch))

    def _commit(self, tip: Optional[str], changes: dict[str, Optional[str]], message: str, agent: str) -> str:
        """A commit on top of `tip` with `changes` (path -> new text, None = delete), built without touching the checkout."""
        workdir = tempfile.mkdtemp(prefix="work-board-")
        env = {"GIT_INDEX_FILE": str(Path(workdir) / "index"), "GIT_AUTHOR_NAME": agent[:60] or "agent",
               "GIT_AUTHOR_EMAIL": "work-board@localhost", "GIT_COMMITTER_NAME": agent[:60] or "agent",
               "GIT_COMMITTER_EMAIL": "work-board@localhost"}
        try:
            if tip:
                self.git("read-tree", tip, env=env)
            for path, text in changes.items():
                if text is None:
                    self.git("update-index", "--force-remove", path, env=env)
                else:
                    blob = self.git("hash-object", "-w", "--stdin", input=text, env=env).stdout.strip()
                    self.git("update-index", "--add", "--cacheinfo", f"100644,{blob},{path}", env=env)
            tree = self.git("write-tree", env=env).stdout.strip()
            parents = ["-p", tip] if tip else []
            return self.git("commit-tree", tree, *parents, "-m", message, env=env).stdout.strip()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _push(self, sha: str) -> bool:
        done = self.git("push", self.remote, f"{sha}:refs/heads/{self.claims_branch}", check=False)
        if done.returncode == 0:
            return True
        if any(word in done.stderr for word in REJECTED):
            return False
        raise BoardError(f"cannot push the claim (the board needs the network): {done.stderr.strip()}")

    def _mutate(self, agent: str, build: Callable[[dict[str, Claim]], tuple[dict[str, Optional[str]], str]]) -> None:
        """Fresh claims -> `build` decides (or raises) -> one commit -> push without force; on a race, start over."""
        for _ in range(MAX_RETRIES):
            tip = self._fetch(self.claims_branch)
            changes, message = build(self._read_claims(tip))
            if self._push(self._commit(tip, changes, message, agent)):
                return
        raise BoardError("the board is too busy (other agents keep winning the race); try again")

    # -- decisions
    def _satisfied(self, task: Task, plan: dict[str, Task], known: set[str]) -> list[str]:
        """Dependencies not yet done (a dependency whose file is gone from the plan is done)."""
        return [d for d in task.depends_on if d in plan or d not in known]

    def _conflict(self, task: Task, agent: str, claims: dict[str, Claim], plan: dict[str, Task]) -> Optional[str]:
        now = self.now()
        for other in claims.values():
            if other.id == task.id or other.agent == agent or not other.live(now) or other.id not in plan:
                continue
            clash = overlaps(task.touches, plan[other.id].touches)
            if clash:
                return f"{task.id} touches {clash[0]}, which {other.id} ({other.agent}, until {other.lease_until}) is changing ({clash[1]})"
        return None

    def ready(self, agent: str, plan: Optional[dict[str, Task]] = None) -> list[Task]:
        plan = plan if plan is not None else self.plan()
        known, claims, now = self.known_ids(set(plan)), self.claims(), self.now()
        out = []
        for task in sorted(plan.values(), key=rank):
            held = claims.get(task.id)
            if self._satisfied(task, plan, known) or (held and held.live(now) and held.agent != agent):
                continue
            if not self._conflict(task, agent, claims, plan):
                out.append(task)
        return out

    def claim(self, task_id: Optional[str], agent: str, hours: float = DEFAULT_HOURS, note: str = "") -> Task:
        plan = self.plan()
        if task_id is None:
            ready = self.ready(agent, plan)
            if not ready:
                raise BoardError("no task is ready right now (run `status` to see what is blocked or held)")
            task_id = ready[0].id
        task = plan.get(task_id)
        if task is None:
            raise BoardError(f"{task_id} is not in the plan on {self.remote}/{self.plan_branch} (finished, or not pushed yet)")
        waiting = self._satisfied(task, plan, self.known_ids(set(plan)))
        if waiting:
            raise BoardError(f"{task_id} is blocked by {', '.join(waiting)}")

        def build(claims: dict[str, Claim]):
            held = claims.get(task_id)
            if held and held.live(self.now()) and held.agent != agent:
                raise BoardError(f"{task_id} is claimed by {held.agent} until {held.lease_until}")
            clash = self._conflict(task, agent, claims, plan)
            if clash:
                raise BoardError(clash)
            start = self.now()
            claim = Claim(task_id, agent, start.isoformat(), (start + timedelta(hours=hours)).isoformat(), note)
            return {f"{CLAIMS_DIR}/{task_id}.json": claim.to_json()}, f"claim {task_id} for {agent}"

        self._mutate(agent, build)
        return task

    def renew(self, task_id: str, agent: str, hours: float = DEFAULT_HOURS) -> None:
        def build(claims: dict[str, Claim]):
            held = claims.get(task_id)
            if held is None or held.agent != agent:
                raise BoardError(f"you do not hold {task_id}" + (f" ({held.agent} does)" if held else "; claim it first"))
            held.lease_until = (self.now() + timedelta(hours=hours)).isoformat()
            return {f"{CLAIMS_DIR}/{task_id}.json": held.to_json()}, f"renew {task_id} for {agent}"

        self._mutate(agent, build)

    def release(self, task_id: str, agent: str, force: bool = False, message: str = "release") -> None:
        def build(claims: dict[str, Claim]):
            held = claims.get(task_id)
            if held is None:
                raise BoardError(f"{task_id} has no claim")
            if held.agent != agent and not force:
                raise BoardError(f"{task_id} is held by {held.agent}; only they (or --force) can release it")
            return {f"{CLAIMS_DIR}/{task_id}.json": None}, f"{message} {task_id} ({agent})"

        self._mutate(agent, build)

    def done(self, task_id: str, agent: str, force: bool = False) -> None:
        if not force and task_id in self.plan():
            raise BoardError(f"{task_id} is still in the plan on {self.remote}/{self.plan_branch}. Delete its file in your "
                             f"fixing commit (message: 'Closes {task_id}'), push to beta, then run `done` again.")
        self.release(task_id, agent, force=force, message="done")

    def gc(self, agent: str) -> list[str]:
        plan, removed = self.plan(), []

        def build(claims: dict[str, Claim]):
            removed.clear()
            removed.extend(sorted(c.id for c in claims.values() if c.id not in plan or not c.live(self.now())))
            if not removed:
                return {}, "gc"
            return {f"{CLAIMS_DIR}/{i}.json": None for i in removed}, f"gc {', '.join(removed)}"

        self._mutate(agent, build)
        return list(removed)

    # -- views
    def status_lines(self, agent: str) -> list[str]:
        plan = self.plan()
        known, claims, now = self.known_ids(set(plan)), self.claims(), self.now()
        lines = []
        for task in sorted(plan.values(), key=rank):
            held, waiting = claims.get(task.id), self._satisfied(task, plan, known)
            if held and held.live(now):
                state = "yours" if held.agent == agent else f"claimed by {held.agent}"
                state += f" until {held.lease_until[:16]}"
            elif waiting:
                state = f"blocked by {', '.join(waiting)}"
            elif self._conflict(task, agent, claims, plan):
                state = "waiting on overlapping files"
            else:
                state = "ready" + (f" (lease of {held.agent} expired)" if held else "")
            lines.append(f"{task.id}  stage {task.stage}  {task.size}  {state:<40} {task.title}")
        orphans = sorted(c.id for c in claims.values() if c.id not in plan)
        if orphans:
            lines.append(f"stale claims for finished tasks: {', '.join(orphans)} (run `gc`)")
        return lines or ["the plan is empty"]


def check_plan(root: Path, board: Optional[Board] = None) -> list[str]:
    """Problems in the plan files of THIS checkout (run before pushing a new or edited task)."""
    problems, tasks = [], {}
    folder = Path(root) / PLAN_DIR
    for path in sorted(folder.glob("*.md")):
        if not TASK_FILE.match(path.name):
            continue
        try:
            task = parse_task(str(path.relative_to(root)).replace("\\", "/"), path.read_text(encoding="utf-8"))
        except BoardError as error:
            problems.append(str(error))
            continue
        if task.id in tasks:
            problems.append(f"duplicate id {task.id}")
        tasks[task.id] = task
    known = board.known_ids(set(tasks)) if board else set(tasks)
    for task in tasks.values():
        for dep in task.depends_on:
            if dep == task.id:
                problems.append(f"{task.id} depends on itself")
            elif dep not in known:
                problems.append(f"{task.id} depends on unknown task {dep}")
    state: dict[str, int] = {}

    def visit(task_id: str, trail: list[str]) -> None:
        if state.get(task_id) == 2 or task_id not in tasks:
            return
        if state.get(task_id) == 1:
            problems.append("dependency cycle: " + " -> ".join(trail + [task_id]))
            return
        state[task_id] = 1
        for dep in tasks[task_id].depends_on:
            visit(dep, trail + [task_id])
        state[task_id] = 2

    for task_id in sorted(tasks):
        visit(task_id, [])
    return problems


# ------------------------------------------------------------------------------------------------------ CLI
def repo_root() -> Path:
    done = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent,
                          text=True, capture_output=True)
    if done.returncode != 0:
        raise BoardError("run this inside the project's git checkout")
    return Path(done.stdout.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Work board for parallel agents (see the module docstring).")
    parser.add_argument("--agent", help="who you are (default: WORK_AGENT or the checkout folder name)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "next", "gc", "check"):
        sub.add_parser(name)
    claim = sub.add_parser("claim")
    claim.add_argument("task_id", nargs="?")
    claim.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    claim.add_argument("--note", default="")
    renew = sub.add_parser("renew")
    renew.add_argument("task_id")
    renew.add_argument("--hours", type=float, default=DEFAULT_HOURS)
    for name in ("release", "done"):
        item = sub.add_parser(name)
        item.add_argument("task_id")
        item.add_argument("--force", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None, root: Optional[Path] = None) -> int:
    args = _parser().parse_args(argv)
    try:
        root = root or repo_root()
        board = Board(root, plan_branch=os.environ.get("WORK_PLAN_BRANCH", "beta"),
                      claims_branch=os.environ.get("WORK_CLAIMS_BRANCH", "work"))
        agent = args.agent or default_agent(root)
        if args.command == "status":
            print(f"agent: {agent}")
            print("\n".join(board.status_lines(agent)))
        elif args.command == "next":
            ready = board.ready(agent)
            print("\n".join(f"{t.id}  stage {t.stage}  {t.size}  {t.title}" for t in ready) or "nothing is ready")
        elif args.command == "claim":
            task = board.claim(args.task_id, agent, args.hours, args.note)
            print(f"claimed {task.id} as {agent} for {args.hours:g}h. Renew with `work.py renew {task.id}` if you need longer.\n"
                  f"Touches: {', '.join(task.touches)}\n\n{task.body}")
        elif args.command == "renew":
            board.renew(args.task_id, agent, args.hours)
            print(f"renewed {args.task_id} for {args.hours:g}h")
        elif args.command in ("release", "done"):
            getattr(board, args.command)(args.task_id, agent, force=args.force)
            print(f"{args.command}: {args.task_id}")
        elif args.command == "gc":
            removed = board.gc(agent)
            print("removed claims: " + (", ".join(removed) or "none"))
        elif args.command == "check":
            problems = check_plan(root, board)
            print("\n".join(problems) if problems else "plan files are valid")
            return 1 if problems else 0
        return 0
    except BoardError as error:
        print(f"work: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
