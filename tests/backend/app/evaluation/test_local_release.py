"""Tests for the offline local-release launcher (no servers are started)."""
from pathlib import Path

import pytest

from backend.app.evaluation.local_release import (
    LocalRelease, OfflineIncapableRelease, ollama_env,
)


SHA = "0123456789abcdef0123456789abcdef01234567"


def make_repo(path: Path, settings_text: str) -> Path:
    (path / "backend" / "app" / "config").mkdir(parents=True)
    (path / "backend" / "app" / "config" / "settings.py").write_text(settings_text, encoding="utf-8")
    return path


@pytest.fixture
def fake_git(monkeypatch):
    """The Docker build image has no git binary, so the launcher's git calls
    are replaced by a fake: rev-parse returns SHA, worktree add copies the repo."""
    import shutil

    import backend.app.evaluation.local_release as lr

    calls = []

    def git(*args, cwd):
        calls.append(args)
        if args[0] == "rev-parse":
            return SHA
        if args[:2] == ("worktree", "add"):
            shutil.copytree(cwd / "backend", Path(args[3]) / "backend")
            return ""
        raise AssertionError(args)

    monkeypatch.setattr(lr, "git", git)
    return calls


def test_ollama_env_routes_every_model_call_and_disables_jev():
    env = ollama_env("llama3.1:8b")
    assert env["OPENAI_BASE_URL"] == env["STORY_MASTER_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert env["OPENAI_MODEL"] == env["STORY_MASTER_MODEL"] == "llama3.1:8b"
    assert env["TYPESAFE_ENABLED"] == "false" and env["JEV_SHADOW_TASKS"] == ""


def test_release_older_than_routing_change_is_refused(tmp_path, fake_git):
    repo = make_repo(tmp_path / "old", 'OPENAI_MODEL = "gpt-4o-mini"\n')
    rel = LocalRelease("prod", None, 8812, repo, tmp_path / "work", "llama3.1:8b")
    with pytest.raises(OfflineIncapableRelease):
        rel.prepare()


def test_offline_capable_release_gets_isolated_cache_and_synthetic_pin(tmp_path, fake_git):
    repo = make_repo(tmp_path / "new", 'OPENAI_BASE_URL = "x"\n')
    rel = LocalRelease("beta", None, 8811, repo, tmp_path / "work", "llama3.1:8b")
    assert rel.prepare() == repo
    env = rel.env()
    assert env["RAILWAY_DEPLOYMENT_ID"] == f"local-beta-{rel.commit[:12]}"
    assert env["RAILWAY_GIT_COMMIT_SHA"] == rel.commit
    assert env["KNOWLEDGE_CACHE_DIR"].endswith(rel.commit[:12])
    assert env["OPENAI_API_KEY"] == "ollama" and rel.url == "http://127.0.0.1:8811"


def test_ref_release_uses_a_git_worktree(tmp_path, fake_git):
    repo = make_repo(tmp_path / "repo", 'OPENAI_BASE_URL = "x"\n')
    rel = LocalRelease("prod", "origin/prod", 8812, repo, tmp_path / "work", "llama3.1:8b")
    directory = rel.prepare()
    assert directory == tmp_path / "work" / "worktrees" / SHA[:12]
    assert (directory / "backend" / "app" / "config" / "settings.py").exists()
    assert ("worktree", "add", "--detach", str(directory), SHA) in fake_git
    rel.prepare()                                 # reuse: no second worktree add
    assert sum(1 for c in fake_git if c[:2] == ("worktree", "add")) == 1


def test_context_model_name_is_stable_and_ollama_safe():
    from backend.app.evaluation.local_release import context_model_name

    assert context_model_name("llama3.1:8b") == "llama3.1-8b-ctx16k"
