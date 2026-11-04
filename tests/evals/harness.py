"""Run Claude Code headless against an isolated copy of the project.

Each eval case gets a fresh workspace: the repo (no .git, outputs or venv) plus a
generated dataset, so the agent can do anything without touching the real checkout.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SKIP = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}


def IGNORE(directory: str, names: list[str]) -> set[str]:
    """Skip caches everywhere, and outputs/ and data/ only at the project root
    (src/cashforecast/data is code and must be copied)."""
    top = {"outputs", "data"} if Path(directory).resolve() == ROOT else set()
    return {n for n in names if n in _SKIP or n in top}


# Override with CF_CLAUDE_ARGS if your Claude Code version uses different flags.
DEFAULT_ARGS = ["--output-format", "json", "--permission-mode", "bypassPermissions"]


@dataclass
class AgentRun:
    prompt: str
    workspace: Path
    exit_code: int
    response: str
    raw: dict | None
    seconds: float


def prepare_workspace(dest: Path, dataset: Path) -> Path:
    """Copy the project and a pre-generated dataset into dest."""
    shutil.copytree(ROOT, dest, ignore=IGNORE)
    shutil.copytree(dataset, dest / "data" / "raw")
    (dest / "outputs").mkdir()
    return dest


def generate_dataset(dest: Path) -> Path:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate.py"), "--out", str(dest)],
        check=True,
        capture_output=True,
        cwd=ROOT,
    )
    return dest


def workspace_env(ws: Path) -> dict[str, str]:
    """Make scripts in the workspace import the workspace's own code, not the checkout's."""
    return {**os.environ, "CLAUDE_PROJECT_DIR": str(ws), "PYTHONPATH": str(ws / "src")}


def run_setup(ws: Path, step: str) -> None:
    """Named setup steps a case can request before the agent runs."""
    env = workspace_env(ws)
    if step == "weekly":
        subprocess.run(
            [sys.executable, "scripts/run_weekly.py"],
            cwd=ws,
            env=env,
            check=True,
            capture_output=True,
        )
    elif step == "weekly_week4":
        subprocess.run(
            [sys.executable, "scripts/run_weekly.py", "--simulate-week", "4"],
            cwd=ws,
            env=env,
            check=True,
            capture_output=True,
        )
    elif step == "corrupt_receipts":
        import pandas as pd

        p = ws / "data" / "raw" / "receipts.parquet"
        df = pd.read_parquet(p)
        df.drop(index=df.index[-5:]).to_parquet(p, index=False)  # bank no longer ties to AR
    else:
        raise ValueError(f"unknown setup step {step!r}")


def run_agent(prompt: str, ws: Path, timeout: int = 900) -> AgentRun:
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("Claude Code CLI not found on PATH")
    extra = (
        shlex.split(os.environ["CF_CLAUDE_ARGS"])
        if "CF_CLAUDE_ARGS" in os.environ
        else DEFAULT_ARGS
    )
    env = workspace_env(ws)
    t0 = time.time()
    proc = subprocess.run(
        [claude, "-p", prompt, *extra],
        cwd=ws,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    raw = None
    response = proc.stdout
    try:
        raw = json.loads(proc.stdout)
        response = raw.get("result", proc.stdout) if isinstance(raw, dict) else proc.stdout
    except json.JSONDecodeError:
        pass
    (ws / "outputs" / "agent_transcript.json").write_text(
        json.dumps(
            {
                "prompt": prompt,
                "exit_code": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr[-5000:],
            },
            indent=2,
        )
    )
    return AgentRun(prompt, ws, proc.returncode, response or "", raw, time.time() - t0)
