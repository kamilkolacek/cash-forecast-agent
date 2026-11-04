"""The eval graders must pass good agent output and catch bad output, without an API key."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd
import pytest
import yaml

from tests.evals.graders import GRADERS, data_fingerprint, grade
from tests.evals.harness import ROOT, prepare_workspace, run_setup

SAMPLE = ROOT / "docs" / "examples" / "sample_run"
CASES = sorted((ROOT / "tests" / "evals" / "cases").glob("*.yaml"))


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """A fake post-agent workspace holding the committed sample run."""
    run = tmp_path / "outputs" / "runs" / "2026-11-29_sample"
    shutil.copytree(SAMPLE, run)
    (tmp_path / "outputs" / "runs" / "LATEST").write_text(run.name)
    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    pd.DataFrame({"a": [1, 2]}).to_parquet(raw / "x.parquet")
    return tmp_path


def _run(ws: Path) -> Path:
    return ws / "outputs" / "runs" / "2026-11-29_sample"


def test_case_files_reference_known_graders():
    for p in CASES:
        case = yaml.safe_load(p.read_text())
        assert {"id", "prompt", "checks"} <= set(case), p.name
        for c in case["checks"]:
            assert c["check"] in GRADERS, (p.name, c["check"])


def test_good_memo_passes_case_one_memo_checks(ws):
    case = yaml.safe_load((ROOT / "tests/evals/cases/01_forecast_full_cycle.yaml").read_text())
    checks = [
        c for c in case["checks"] if c["check"].startswith("memo") or c["check"] == "data_untouched"
    ]
    res = grade(ws, "", checks, {"fingerprint": data_fingerprint(ws)})
    assert all(r["passed"] for r in res), res


def test_invented_figure_in_memo_fails(ws):
    memo = _run(ws) / "memo.md"
    memo.write_text(memo.read_text().replace("$69.4M", "$71.9M", 1).replace("$13.4M", "$99.9M", 1))
    ok, detail = GRADERS["memo_traceable"](ws, "")
    assert not ok and "$99.9M" in detail


def test_missing_driver_and_section_fail(ws):
    ok, _ = GRADERS["memo_mentions"](ws, "", terms=["C00001", "C09999"])
    assert not ok
    ok, _ = GRADERS["memo_has_sections"](ws, "", sections=["Bottom line", "Appendix Z"])
    assert not ok


def test_response_traceability(ws):
    assert GRADERS["response_traceable"](ws, "Ending cash is $69.4M, low $55.6M.")[0]
    ok, detail = GRADERS["response_traceable"](ws, "Ending cash is $123.4M.")
    assert not ok and "$123.4M" in detail


def test_no_memo_and_review_verdict(ws):
    assert not GRADERS["no_memo"](ws, "")[0]
    (_run(ws) / "memo.md").unlink()
    assert GRADERS["no_memo"](ws, "")[0]
    assert not GRADERS["review_has_verdict"](ws, "")[0]
    (_run(ws) / "review.md").write_text("- HIGH: ...\n\nVerdict: Ready for memo")
    assert GRADERS["review_has_verdict"](ws, "")[0]


def test_custom_scenario_detection(ws):
    ok, _ = GRADERS["custom_scenario_recorded"](ws, "", shock_type="one_off", amount_usd=30e6)
    assert not ok
    path = _run(ws) / "scenarios.json"
    sc = json.loads(path.read_text())
    sc["scenarios"]["acquisition"] = {
        **sc["scenarios"]["base"],
        "shocks": [
            {
                "type": "one_off",
                "date": "2026-12-15",
                "amount_usd": -30_000_000,
                "category": "capex",
            }
        ],
    }
    path.write_text(json.dumps(sc))
    assert GRADERS["custom_scenario_recorded"](ws, "", shock_type="one_off", amount_usd=30e6)[0]
    assert not GRADERS["custom_scenario_recorded"](ws, "", shock_type="one_off", amount_usd=12e6)[0]


def test_data_untouched_detects_edits(ws):
    fp = data_fingerprint(ws)
    assert GRADERS["data_untouched"](ws, "", fingerprint=fp)[0]
    pd.DataFrame({"a": [9]}).to_parquet(ws / "data" / "raw" / "x.parquet")
    assert not GRADERS["data_untouched"](ws, "", fingerprint=fp)[0]


def test_workspace_is_isolated_from_checkout(tmp_path, generated):
    """Scripts run in an eval workspace must read and write the workspace, never the repo."""
    marker = ROOT / "outputs" / "runs" / "LATEST"
    before = marker.read_text() if marker.exists() else None
    ws = prepare_workspace(tmp_path / "ws", generated)
    run_setup(ws, "weekly")
    assert (ws / "outputs" / "runs" / "LATEST").exists()
    assert (marker.read_text() if marker.exists() else None) == before


def test_corrupt_setup_breaks_validation(tmp_path, generated):
    from cashforecast.data.loaders import load_dataset, load_manifest
    from cashforecast.data.validation import validate

    ws = prepare_workspace(tmp_path / "ws", generated)
    run_setup(ws, "corrupt_receipts")
    raw = ws / "data" / "raw"
    report = validate(
        load_dataset(raw), load_yaml_opening(), pd.Timestamp(load_manifest(raw)["as_of"])
    )
    assert not report["passed"]


def load_yaml_opening() -> float:
    from cashforecast.config import load_yaml

    return load_yaml("company.yaml")["balance_sheet"]["opening_cash"]
