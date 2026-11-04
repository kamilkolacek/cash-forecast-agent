"""Agent evals: run Claude Code headless on each case and grade the result.

Requires the Claude Code CLI and ANTHROPIC_API_KEY. Skipped otherwise, and excluded from
the default test run (`-m 'not eval'`). Run with `make eval`; results go to
outputs/evals/<timestamp>/report.json.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest
import yaml

from .graders import data_fingerprint, grade
from .harness import ROOT, generate_dataset, prepare_workspace, run_agent, run_setup

CASES = sorted((Path(__file__).parent / "cases").glob("*.yaml"))
REPORT_DIR = ROOT / "outputs" / "evals" / datetime.now().strftime("%Y%m%dT%H%M%S")

pytestmark = [
    pytest.mark.eval,
    pytest.mark.skipif(
        not os.environ.get("ANTHROPIC_API_KEY") or not shutil.which("claude"),
        reason="needs Claude Code CLI and ANTHROPIC_API_KEY",
    ),
]


@pytest.fixture(scope="session")
def dataset(tmp_path_factory) -> Path:
    return generate_dataset(tmp_path_factory.mktemp("evaldata") / "raw")


@pytest.mark.parametrize("case_path", CASES, ids=[p.stem for p in CASES])
def test_agent_case(case_path: Path, dataset: Path, tmp_path: Path):
    case = yaml.safe_load(case_path.read_text())
    ws = prepare_workspace(tmp_path / "ws", dataset)
    for step in case.get("setup", []):
        run_setup(ws, step)
    context = {"fingerprint": data_fingerprint(ws)}
    run = run_agent(case["prompt"], ws)
    results = grade(ws, run.response, case["checks"], context)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "id": case["id"],
        "prompt": case["prompt"],
        "exit_code": run.exit_code,
        "seconds": round(run.seconds, 1),
        "passed": all(r["passed"] for r in results),
        "checks": results,
        "response": run.response[:4000],
    }
    (REPORT_DIR / f"{case['id']}.json").write_text(json.dumps(report, indent=2))
    failed = [r for r in results if not r["passed"]]
    assert not failed, f"{case['id']}: {failed}"
