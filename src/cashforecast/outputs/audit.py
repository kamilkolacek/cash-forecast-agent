"""Audit trail: what produced a run, so any figure can be traced to its exact inputs."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cashforecast import __version__
from cashforecast.config import CONFIG_DIR, PROJECT_ROOT


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _git() -> dict[str, Any]:
    def run(*args: str) -> str | None:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain", "--", "src", "config", "scripts")
    return {
        "commit": commit,
        "uncommitted_code_or_config_changes": bool(status) if commit else None,
    }


def data_fingerprint(data_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(data_dir).glob("*.parquet")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


class Audit:
    """Collects step timings during a run, then writes audit.json into the run directory."""

    def __init__(self, data_dir: Path, **params: Any):
        self.data_dir = Path(data_dir)
        self.params = params
        self.started = datetime.now(UTC)
        self.steps: list[dict[str, Any]] = []
        self._t = self.started

    def step(self, name: str) -> None:
        now = datetime.now(UTC)
        self.steps.append({"step": name, "seconds": round((now - self._t).total_seconds(), 2)})
        self._t = now

    def write(self, run_dir: Path) -> Path:
        manifest_path = self.data_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        record = {
            "run_id": Path(run_dir).name,
            "started_utc": self.started.isoformat(timespec="seconds"),
            "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "parameters": self.params,
            "command": " ".join(Path(a).name if i == 0 else a for i, a in enumerate(sys.argv)),
            "code": {"package_version": __version__, **_git()},
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "config_sha256": {p.name: _sha(p) for p in sorted(CONFIG_DIR.glob("*.yaml"))},
            "data": {
                "directory": str(self.data_dir),
                "fingerprint": data_fingerprint(self.data_dir),
                "seed": manifest.get("seed"),
                "as_of": manifest.get("as_of"),
                "anomalies_injected": [a.get("type") for a in manifest.get("anomalies", [])],
            },
            "steps": self.steps,
            "artifacts_sha256": {
                p.name: _sha(p)
                for p in sorted(Path(run_dir).iterdir())
                if p.is_file() and p.name != "audit.json"
            },
        }
        path = Path(run_dir) / "audit.json"
        path.write_text(json.dumps(record, indent=2, default=str))
        return path
