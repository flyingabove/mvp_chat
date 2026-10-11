"""The work board: claims are a real git race on a real (local, bare) remote; no network, no mocks of git."""
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.work import Board, BoardError, check_plan, main, overlaps, parse_task

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def task_text(task_id, stage=1, depends="", touches="backend/a.py", size="S", title="Do it"):
    return (f"---\nid: {task_id}\ntitle: {title}\nstage: {stage}\nsize: {size}\ndepends_on: [{depends}]\n"
            f"touches: [{touches}]\n---\nBody of {task_id}.\n")


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True).stdout


class Clock:
    def __init__(self):
        self.value = NOW

    def __call__(self):
        return self.value


@pytest.fixture(scope="module")
def _built(tmp_path_factory):
    """Built once (git is slow on Windows): a bare origin with a `beta` branch holding the plan, and three clones."""
    tmp_path = tmp_path_factory.mktemp("board")
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "--bare", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", str(origin), str(seed))
    for key, value in (("user.name", "t"), ("user.email", "t@t")):
        git(seed, "config", key, value)
    plan = seed / "documentation" / "plan"
    plan.mkdir(parents=True)
    (plan / "P-01-first.md").write_text(task_text("P-01", 1, touches="backend/a.py"))
    (plan / "P-02-second.md").write_text(task_text("P-02", 1, touches="backend/b.py"))
    (plan / "P-03-third.md").write_text(task_text("P-03", 2, depends="P-01", touches="backend/c.py"))
    (plan / "P-04-clash.md").write_text(task_text("P-04", 2, touches="backend/a.py"))
    git(seed, "add", "-A")
    git(seed, "commit", "-m", "plan")
    git(seed, "push", "origin", "HEAD:refs/heads/beta")
    clones = {"seed": seed, "origin": origin, "sha": git(seed, "rev-parse", "HEAD").strip()}
    for name in ("alice", "bob"):
        git(tmp_path, "clone", "-b", "beta", str(origin), str(tmp_path / name))
        for key, value in (("user.name", name), ("user.email", f"{name}@t")):
            git(tmp_path / name, "config", key, value)
        clones[name] = tmp_path / name
    return clones


@pytest.fixture
def world(_built):
    """Every test starts from the original plan and an empty claims branch (the clones are only read through
    `origin/...`; the two helpers that use a working tree reset it themselves)."""
    git(_built["origin"], "update-ref", "refs/heads/beta", _built["sha"])
    subprocess.run(["git", "update-ref", "-d", "refs/heads/work"], cwd=_built["origin"], capture_output=True)
    return _built


def reset(world, name):
    git(world[name], "fetch", "origin", "+refs/heads/beta:refs/remotes/origin/beta")
    git(world[name], "reset", "--hard", world["sha"])


def board(world, who, clock=None):
    return Board(world[who], now=clock or Clock())


def finish(world, task_id, filename):
    """Another agent's fixing commit: the task file is deleted on beta."""
    seed = world["seed"]
    reset(world, "seed")
    git(seed, "rm", f"documentation/plan/{filename}")
    git(seed, "commit", "-m", f"Closes {task_id}")
    git(seed, "push", "origin", "HEAD:refs/heads/beta")


# ------------------------------------------------------------------------------------------------ parsing
def test_parse_task_reads_front_matter_and_body():
    task = parse_task("documentation/plan/P-07-x.md", task_text("P-07", 3, "P-01, P-02", "a/, b.py", "L", "Hello"))
    assert (task.id, task.title, task.stage, task.size) == ("P-07", "Hello", 3, "L")
    assert task.depends_on == ["P-01", "P-02"] and task.touches == ["a/", "b.py"] and task.body == "Body of P-07."


@pytest.mark.parametrize("text, message", [
    ("no front matter", "front matter"),
    ("---\nid: P-01\ntitle: t\nstage: 1\nsize: S\n---\n", "touches"),
    ("---\nid: nope\ntitle: t\nstage: 1\nsize: S\ntouches: [a]\n---\n", "P-07"),
    ("---\nid: P-01\ntitle: t\nstage: one\nsize: S\ntouches: [a]\n---\n", "stage"),
    ("---\nid: P-01\ntitle: t\nstage: 1\nsize: XL\ntouches: [a]\n---\n", "size"),
])
def test_parse_task_rejects_bad_files(text, message):
    with pytest.raises(BoardError, match=message):
        parse_task("documentation/plan/P-01-x.md", text)


def test_parse_task_requires_file_name_to_match_id():
    with pytest.raises(BoardError, match="file name"):
        parse_task("documentation/plan/P-09-x.md", task_text("P-01"))


@pytest.mark.parametrize("a, b, clash", [
    (["backend/a.py"], ["backend/a.py"], True),
    (["backend/"], ["backend/a.py"], True),
    (["backend/a.py"], ["backend"], True),
    (["backend/*"], ["backend/x/y.py"], True),
    (["backend/a.py"], ["backend/ab.py"], False),
    (["frontend/"], ["backend/"], False),
])
def test_overlap_means_equal_or_containing_paths(a, b, clash):
    assert bool(overlaps(a, b)) is clash


# ------------------------------------------------------------------------------------------ ordering
def test_next_lists_unblocked_tasks_by_stage_then_id(world):
    ids = [t.id for t in board(world, "alice").ready("alice")]
    assert ids == ["P-01", "P-02", "P-04"]   # P-03 waits on P-01; stage 1 comes before stage 2


def test_finished_dependency_unblocks_its_dependants(world):
    finish(world, "P-01", "P-01-first.md")
    assert [t.id for t in board(world, "alice").ready("alice")] == ["P-02", "P-03", "P-04"]


def test_claim_without_id_takes_the_best_ready_task(world):
    assert board(world, "alice").claim(None, "alice").id == "P-01"
    assert board(world, "bob").claim(None, "bob").id == "P-02"


# ---------------------------------------------------------------------------------------- the race
def test_second_agent_cannot_take_a_held_task(world):
    board(world, "alice").claim("P-01", "alice")
    with pytest.raises(BoardError, match="claimed by alice"):
        board(world, "bob").claim("P-01", "bob")


def test_blocked_task_cannot_be_claimed(world):
    with pytest.raises(BoardError, match="blocked by P-01"):
        board(world, "alice").claim("P-03", "alice")


def test_overlapping_files_wait_for_the_holder(world):
    board(world, "alice").claim("P-01", "alice")
    with pytest.raises(BoardError, match="touches backend/a.py"):
        board(world, "bob").claim("P-04", "bob")
    assert "P-04" not in [t.id for t in board(world, "bob").ready("bob")]
    assert "P-04" in [t.id for t in board(world, "alice").ready("alice")]   # the holder is not blocked by their own claim


def test_a_lost_race_is_retried_against_fresh_claims(world):
    """Bob's claim is built from a stale view: alice pushes in between. Bob's retry must see it and take the other task."""
    alice, bob = board(world, "alice"), board(world, "bob")
    real_push, calls = bob._push, []

    def racing_push(sha):
        if not calls:
            calls.append(1)
            alice.claim("P-02", "alice")             # alice wins the push race for P-02 first
        return real_push(sha)

    bob._push = racing_push
    with pytest.raises(BoardError, match="claimed by alice"):
        bob.claim("P-02", "bob")
    assert alice.claims()["P-02"].agent == "alice"
    bob._push = real_push
    assert bob.claim("P-01", "bob").id == "P-01"


def test_unrelated_claims_both_land_after_a_race(world):
    alice, bob = board(world, "alice"), board(world, "bob")
    real_push, calls = bob._push, []

    def racing_push(sha):
        if not calls:
            calls.append(1)
            alice.claim("P-01", "alice")
        return real_push(sha)

    bob._push = racing_push
    bob.claim("P-02", "bob")
    assert {c.id: c.agent for c in alice.claims().values()} == {"P-01": "alice", "P-02": "bob"}


# ------------------------------------------------------------------------------------------- leases
def test_expired_lease_frees_the_task(world):
    clock = Clock()
    board(world, "alice", clock).claim("P-01", "alice", hours=4)
    clock.value = NOW + timedelta(hours=5)
    assert board(world, "bob", clock).claim("P-01", "bob").id == "P-01"
    assert board(world, "bob", clock).claims()["P-01"].agent == "bob"


def test_renew_extends_only_your_own_lease(world):
    clock = Clock()
    mine = board(world, "alice", clock)
    mine.claim("P-01", "alice", hours=1)
    clock.value = NOW + timedelta(minutes=50)
    mine.renew("P-01", "alice", hours=4)
    clock.value = NOW + timedelta(hours=3)
    with pytest.raises(BoardError, match="claimed by alice"):
        board(world, "bob", clock).claim("P-01", "bob")
    with pytest.raises(BoardError, match="alice does"):
        board(world, "bob", clock).renew("P-01", "bob")


def test_release_is_for_the_owner_unless_forced(world):
    board(world, "alice").claim("P-01", "alice")
    with pytest.raises(BoardError, match="only they"):
        board(world, "bob").release("P-01", "bob")
    board(world, "bob").release("P-01", "bob", force=True)
    assert board(world, "bob").claims() == {}


# ------------------------------------------------------------------------------------------- done / gc
def test_done_requires_the_task_file_to_be_gone_from_beta(world):
    mine = board(world, "alice")
    mine.claim("P-01", "alice")
    with pytest.raises(BoardError, match="still in the plan"):
        mine.done("P-01", "alice")
    finish(world, "P-01", "P-01-first.md")
    mine.done("P-01", "alice")
    assert mine.claims() == {}


def test_gc_removes_claims_of_finished_tasks_and_expired_leases(world):
    clock = Clock()
    board(world, "alice", clock).claim("P-01", "alice", hours=1)
    board(world, "bob", clock).claim("P-02", "bob", hours=10)
    finish(world, "P-01", "P-01-first.md")
    clock.value = NOW + timedelta(hours=2)
    assert board(world, "bob", clock).gc("bob") == ["P-01"]
    assert list(board(world, "bob", clock).claims()) == ["P-02"]


def test_status_shows_each_state(world):
    board(world, "alice").claim("P-01", "alice")
    text = "\n".join(board(world, "bob").status_lines("bob"))
    assert "claimed by alice" in text and "blocked by P-01" in text and "waiting on overlapping files" in text
    assert "ready" in text


# ---------------------------------------------------------------------------------------------- check
def write_plan(root, files):
    plan = Path(root) / "documentation" / "plan"
    plan.mkdir(parents=True)
    for name, text in files.items():
        (plan / name).write_text(text)


def test_check_accepts_a_valid_plan(tmp_path):
    write_plan(tmp_path, {"P-01-a.md": task_text("P-01"), "P-02-b.md": task_text("P-02", depends="P-01")})
    assert check_plan(tmp_path) == []


def test_check_finds_unknown_dependencies_cycles_and_duplicates(tmp_path):
    write_plan(tmp_path, {"P-01-a.md": task_text("P-01", depends="P-02"), "P-02-b.md": task_text("P-02", depends="P-01"),
                          "P-03-c.md": task_text("P-03", depends="P-99"), "P-04-d.md": task_text("P-04", depends="P-04"),
                          "P-05-e.md": "broken"})
    problems = "\n".join(check_plan(tmp_path))
    assert "dependency cycle" in problems and "unknown task P-99" in problems
    assert "depends on itself" in problems and "front matter" in problems


def test_check_allows_a_dependency_that_was_finished_earlier(world):
    finish(world, "P-01", "P-01-first.md")
    alice = world["alice"]
    git(alice, "pull", "--rebase", "origin", "beta")
    try:
        assert check_plan(alice, board(world, "alice")) == []   # P-03 still names the finished P-01
    finally:
        reset(world, "alice")


# ------------------------------------------------------------------------------------------------- CLI
def test_cli_claim_prints_the_spec_and_status_shows_the_claim(world, capsys, monkeypatch):
    monkeypatch.setenv("WORK_AGENT", "alice")
    assert main(["claim"], root=world["alice"]) == 0
    assert "claimed P-01" in capsys.readouterr().out
    assert main(["status"], root=world["alice"]) == 0
    assert "yours until" in capsys.readouterr().out


def test_cli_reports_errors_without_a_traceback(world, capsys):
    assert main(["--agent", "bob", "claim", "P-99"], root=world["bob"]) == 1
    assert "not in the plan" in capsys.readouterr().err
