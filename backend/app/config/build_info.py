"""Deployed build identity — commit SHA, environment, content schema version.

Railway sets RAILWAY_GIT_COMMIT_SHA / RAILWAY_ENVIRONMENT_NAME automatically
on every deploy (see backend/app/api/auth.py for the same env var names used
in the OAuth debug payload). Locally, neither is set, so we fall back to
`git rev-parse HEAD` (best-effort, cached) and "local".
"""
import functools
import os
import subprocess

# Bump when the persisted state/content schema changes in a way that matters
# for support/debugging (not every commit — only breaking session/story shape
# changes).
CONTENT_SCHEMA_VERSION = 1


@functools.lru_cache(maxsize=1)
def _local_git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def get_build_info() -> dict:
    commit = os.getenv("RAILWAY_GIT_COMMIT_SHA", "") or _local_git_commit() or "unknown"
    environment = os.getenv("RAILWAY_ENVIRONMENT_NAME", "") or "local"
    return {
        "commit": commit,
        # RAILWAY_DEPLOYMENT_ID is set on EVERY Railway deploy, including CLI
        # (`railway up`) deploys that carry no git SHA (beta reported
        # commit="unknown" on 2026-09-23). The Jev game arena pins releases by
        # (commit, deployment_id) so a mid-experiment redeploy is detected
        # even then. Empty locally.
        "deployment_id": os.getenv("RAILWAY_DEPLOYMENT_ID", ""),
        "environment": environment,
        "content_schema_version": CONTENT_SCHEMA_VERSION,
    }
