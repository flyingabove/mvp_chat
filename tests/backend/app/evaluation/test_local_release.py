"""Tests for the offline local-release launcher (no servers are started)."""
import subprocess
from pathlib import Path

import pytest

from backend.app.evaluation.local_release import (
    LocalRelease, OfflineIncapableRelease, ollama_env,
)


def make_repo(path: Path, settings_text: str) -> Path:
    (path / "backend" / "app" / "config").mkdir(parents=True)
    (path / "backend" / "app" / "config" / "settings.py").write_text(settings_text, encoding="utf-8")
    for cmd in (["init", "-q"], ["add", "."], ["-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
        subprocess.run(["git", *cmd], cwd=path, check=True, capture_output=True)
    return path


def test_ollama_env_routes_every_model_call_and_disables_jev():
    env = ollama_env("llama3.1:8b")
    assert env["OPENAI_BASE_URL"] == env["STORY_MASTER_BASE_URL"] == "http://127.0.0.1:11434/v1"
    assert env["OPENAI_MODEL"] == env["STORY_MASTER_MODEL"] == "llama3.1:8b"
    assert env["TYPESAFE_ENABLED"] == "false" and env["JEV_SHADOW_TASKS"] == ""


def test_release_older_than_routing_change_is_refused(tmp_path):
    repo = make_repo(tmp_path / "old", 'OPENAI_MODEL = "gpt-4o-mini"\n')
    rel = LocalRelease("prod", None, 8812, repo, tmp_path / "work", "llama3.1:8b")
    with pytest.raises(OfflineIncapableRelease):
        rel.prepare()


def test_offline_capable_release_gets_isolated_cache_and_synthetic_pin(tmp_path):
    repo = make_repo(tmp_path / "new", 'OPENAI_BASE_URL = "x"\n')
    rel = LocalRelease("beta", None, 8811, repo, tmp_path / "work", "llama3.1:8b")
    assert rel.prepare() == repo
    env = rel.env()
    assert env["RAILWAY_DEPLOYMENT_ID"] == f"local-beta-{rel.commit[:12]}"
    assert env["RAILWAY_GIT_COMMIT_SHA"] == rel.commit
    assert env["KNOWLEDGE_CACHE_DIR"].endswith(rel.commit[:12])
    assert env["OPENAI_API_KEY"] == "ollama" and rel.url == "http://127.0.0.1:8811"


def test_ref_release_uses_a_git_worktree(tmp_path):
    repo = make_repo(tmp_path / "repo", 'OPENAI_BASE_URL = "x"\n')
    rel = LocalRelease("prod", "HEAD", 8812, repo, tmp_path / "work", "llama3.1:8b")
    directory = rel.prepare()
    assert directory != repo and (directory / "backend" / "app" / "config" / "settings.py").exists()
    subprocess.run(["git", "worktree", "remove", "--force", str(directory)], cwd=repo, check=True)


def test_context_model_name_is_stable_and_ollama_safe():
    from backend.app.evaluation.local_release import context_model_name

    assert context_model_name("llama3.1:8b") == "llama3.1-8b-ctx16k"
