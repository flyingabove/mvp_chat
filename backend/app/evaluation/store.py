# backend/app/evaluation/store.py
"""Experiment artifact store (JEV_GAME_ARENA_DESIGN.md §10).

Layout under <root>/<experiment_id>/:
  manifest.json            immutable; re-opening with a different hash fails
  arms/<arm_id>.json       one file per finished arm (written atomically)
  judgments/<pair_id>.json one file per judged pair (default judge)
  judgments/<judge>/<pair_id>.json  same, per additional judge (e.g. "llm")
  events.jsonl             append-only progress log
  report.json / report.html
  STOP                     create this file to cancel a running batch

Atomic writes (tmp + os.replace) mean a crash never leaves a half-written
artifact, and resume = "skip arms/pairs whose file exists".
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from backend.app.evaluation.contracts import ArmTranscript, ExperimentManifest


def default_root() -> Path:
    return (Path("/data") if Path("/data").exists() else Path("./data")) / "eval_arena"


class ManifestConflictError(RuntimeError):
    pass


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


class ArtifactStore:
    def __init__(self, root: Path, experiment_id: str) -> None:
        self.dir = Path(root) / experiment_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---- manifest ----
    @property
    def manifest_path(self) -> Path:
        return self.dir / "manifest.json"

    def save_manifest(self, manifest: ExperimentManifest) -> None:
        if self.manifest_path.exists():
            existing = ExperimentManifest.from_json(json.loads(self.manifest_path.read_text(encoding="utf-8")))
            if existing.manifest_hash != manifest.manifest_hash:
                raise ManifestConflictError(
                    f"{self.manifest_path} already holds a different experiment "
                    f"({existing.manifest_hash[:12]} != {manifest.manifest_hash[:12]})"
                )
            return
        write_json_atomic(self.manifest_path, {**manifest.to_json(), "manifest_hash": manifest.manifest_hash})

    def load_manifest(self) -> ExperimentManifest:
        return ExperimentManifest.from_json(json.loads(self.manifest_path.read_text(encoding="utf-8")))

    # ---- arms ----
    def arm_path(self, arm_id: str) -> Path:
        return self.dir / "arms" / f"{arm_id}.json"

    def save_arm(self, arm: ArmTranscript) -> None:
        write_json_atomic(self.arm_path(arm.arm_id), arm.to_json())

    def load_arm(self, arm_id: str) -> ArmTranscript | None:
        p = self.arm_path(arm_id)
        if not p.exists():
            return None
        return ArmTranscript.from_json(json.loads(p.read_text(encoding="utf-8")))

    def discard_arm(self, arm_id: str, reason: str) -> None:
        """Keep invalid evidence (renamed) so a rerun doesn't destroy it (§4)."""
        p = self.arm_path(arm_id)
        if p.exists():
            os.replace(p, p.with_suffix(f".invalid{int(time.time())}.json"))
            self.log("arm_discarded", arm_id=arm_id, reason=reason)

    # ---- judgments ----
    def judgment_path(self, pair_id: str, judge: str = "") -> Path:
        base = self.dir / "judgments"
        return (base / judge if judge else base) / f"{pair_id}.json"

    def save_judgment(self, pair_id: str, payload: dict[str, Any], judge: str = "") -> None:
        write_json_atomic(self.judgment_path(pair_id, judge), payload)

    def load_judgment(self, pair_id: str, judge: str = "") -> dict[str, Any] | None:
        p = self.judgment_path(pair_id, judge)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    # ---- reports / events / cancel ----
    def save_report(self, report: dict[str, Any], html: str | None = None) -> None:
        write_json_atomic(self.dir / "report.json", report)
        if html is not None:
            tmp = self.dir / "report.html.tmp"
            tmp.write_text(html, encoding="utf-8")
            os.replace(tmp, self.dir / "report.html")

    def log(self, event: str, **fields: Any) -> None:
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": event, **fields}, default=str)
        with open(self.dir / "events.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    @property
    def cancel_requested(self) -> bool:
        return (self.dir / "STOP").exists()
