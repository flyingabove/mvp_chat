# backend/app/evaluation/local_release.py
"""Run two releases of the game on this machine for OFFLINE arena tests.

Each release is a real `uvicorn backend.app.main:app` process (the same app
the hosted services run), started from either the current checkout or a git
worktree of a ref (e.g. origin/prod). Every model call is routed to the local
Ollama server through the env overrides the app honors:

  OPENAI_BASE_URL / OPENAI_MODEL            extractors, translation
  STORY_MASTER_BASE_URL / STORY_MASTER_MODEL storyteller
  TYPESAFE_ENABLED=false                     no Jev (cloud) in the game

Startup mirrors the Dockerfile: build the knowledge index, then serve. Each
release gets its own knowledge cache, and RAILWAY_DEPLOYMENT_ID is set to a
synthetic id so the arena's release pinning works exactly as on Railway.

A ref older than the OPENAI_BASE_URL routing change would still send its
extractor calls to OpenAI, so offline mode refuses such refs instead of
silently going online.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

OLLAMA_V1 = "http://127.0.0.1:11434/v1"
OFFLINE_MARKER = "OPENAI_BASE_URL"          # present in settings.py once calls are routable


class OfflineIncapableRelease(RuntimeError):
    pass


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def ollama_env(model: str, base_url: str = OLLAMA_V1) -> dict[str, str]:
    return {
        "OPENAI_BASE_URL": base_url, "OPENAI_MODEL": model, "OPENAI_API_KEY": "ollama",
        "STORY_MASTER_BASE_URL": base_url, "STORY_MASTER_MODEL": model, "STORY_MASTER_API_KEY": "ollama",
        "TYPESAFE_ENABLED": "false", "TYPESAFE_API_KEY": "", "JEV_ENABLED_TASKS": "", "JEV_SHADOW_TASKS": "",
    }


@dataclass
class LocalRelease:
    label: str                       # "beta" | "prod" (arena side)
    ref: str | None                  # None = the current checkout
    port: int
    repo: Path
    work_root: Path                  # where worktrees + logs live
    model: str
    ollama_base_url: str = OLLAMA_V1

    process: subprocess.Popen | None = None
    directory: Path | None = None
    commit: str = ""

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def prepare(self) -> Path:
        if self.ref is None:
            self.directory = self.repo
            self.commit = git("rev-parse", "HEAD", cwd=self.repo)
        else:
            self.commit = git("rev-parse", self.ref, cwd=self.repo)
            self.directory = self.work_root / "worktrees" / self.commit[:12]
            if not self.directory.exists():
                self.directory.parent.mkdir(parents=True, exist_ok=True)
                git("worktree", "add", "--detach", str(self.directory), self.commit, cwd=self.repo)
        settings = (self.directory / "backend" / "app" / "config" / "settings.py").read_text(encoding="utf-8")
        if OFFLINE_MARKER not in settings:
            raise OfflineIncapableRelease(
                f"{self.label} ({self.ref or 'checkout'} @ {self.commit[:12]}) predates {OFFLINE_MARKER} routing; "
                "its extractor calls would reach OpenAI. Compare against a newer ref for offline runs.")
        return self.directory

    def env(self) -> dict[str, str]:
        cache = self.work_root / "knowledge_cache" / self.commit[:12]
        return {
            **os.environ,
            **ollama_env(self.model, self.ollama_base_url),
            "PYTHONPATH": str(self.directory),
            "KNOWLEDGE_CACHE_DIR": str(cache),
            "RAILWAY_DEPLOYMENT_ID": f"local-{self.label}-{self.commit[:12]}",
            "RAILWAY_ENVIRONMENT_NAME": f"local-{self.label}",
            "RAILWAY_GIT_COMMIT_SHA": self.commit,
            "PYTHONIOENCODING": "utf-8",
        }

    def start(self) -> None:
        log_path = self.work_root / f"server_{self.label}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        env = self.env()
        log = open(log_path, "a", encoding="utf-8")
        subprocess.run([sys.executable, "-m", "backend.app.knowledge.build.build_index"], cwd=self.directory,
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=self.directory, env=env, stdout=log, stderr=subprocess.STDOUT)

    async def wait_healthy(self, timeout_s: float = 240.0) -> None:
        deadline = time.monotonic() + timeout_s
        async with httpx.AsyncClient() as client:
            while time.monotonic() < deadline:
                if self.process and self.process.poll() is not None:
                    raise RuntimeError(f"{self.label} server exited early (see server_{self.label}.log)")
                try:
                    r = await client.get(f"{self.url}/api/health", timeout=5.0)
                    if r.status_code == 200:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(2.0)
        raise TimeoutError(f"{self.label} server not healthy after {timeout_s:.0f}s")

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.process.kill()


async def ollama_models(base_url: str = OLLAMA_V1) -> list[str]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{base_url}/models", timeout=5.0)
            return [m.get("id", "") for m in (r.json().get("data") or [])]
    except (httpx.HTTPError, ValueError):
        return []
