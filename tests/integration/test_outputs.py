"""Excel workbook and Streamlit dashboard, built from a fresh run."""

from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook

from cashforecast.engine.scenarios import run_scenarios
from cashforecast.engine.variance import run_variance
from cashforecast.outputs.artifacts import (
    write_facts,
    write_forecast,
    write_scenarios,
    write_validation,
    write_variance,
)
from cashforecast.outputs.workbook import write_workbook

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def full_run(tmp_path_factory, dataset, live_forecast):
    d, _, m, report = dataset
    as_of = pd.Timestamp(m["as_of"])
    out = tmp_path_factory.mktemp("outputs")
    run = write_forecast(live_forecast, out / "runs")
    write_validation(run, report)
    write_variance(run, run_variance(d, as_of - pd.Timedelta(days=7), as_of, as_of))
    write_scenarios(run, run_scenarios(live_forecast, d))
    write_facts(run)
    return out, run, write_workbook(run)


def test_workbook_structure_and_formulas(full_run):
    _, run, path = full_run
    wb = load_workbook(path)
    assert wb.sheetnames == [
        "Summary",
        "13-Week Forecast",
        "Daily (Wks 1-2)",
        "Variance",
        "Scenarios",
        "Assumptions",
    ]
    ws = wb["13-Week Forecast"]
    labels = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    closing, opening = labels["Closing cash"], labels["Opening cash"]
    # Roll-forward is live: W2 opening = W1 closing; closing = opening + net.
    assert ws.cell(opening, 3).value == f"=B{closing}"
    assert ws.cell(closing, 2).value.startswith(f"=B{opening}+B")
    assert wb["Summary"]["B11"].value.startswith("='13-Week Forecast'!")
    assert (
        wb["Summary"]["B15"].value
        == json.loads((run / "summary.json").read_text())["min_cash_threshold_usd"]
    )


def _python_rollforward(path: Path) -> float:
    """Evaluate the forecast sheet's roll-forward in Python (CI has no Excel engine)."""
    ws = load_workbook(path)["13-Week Forecast"]
    rows = {ws.cell(r, 1).value: r for r in range(1, ws.max_row + 1)}
    weeks = range(2, 15)
    body = [
        r for r in range(5, rows["Net cash flow"]) if isinstance(ws.cell(r, 2).value, int | float)
    ]
    cash = ws.cell(rows["Opening cash"], 2).value
    for col in weeks:
        cash += sum(ws.cell(r, col).value for r in body)
    return cash


def test_workbook_rolls_to_engine_ending_cash(full_run):
    _, run, path = full_run
    ending = json.loads((run / "summary.json").read_text())["ending_cash_usd"]
    assert abs(_python_rollforward(path) - ending) < 1.0


@pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("libreoffice") is None,
    reason="LibreOffice not installed",
)
def test_workbook_recalculates_without_errors(full_run, tmp_path):
    _, run, path = full_run
    copy = tmp_path / path.name
    shutil.copy(path, copy)
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    subprocess.run(
        [exe, "--headless", "--convert-to", "xlsx", "--outdir", str(tmp_path / "o"), str(copy)],
        check=True,
        capture_output=True,
        timeout=120,
    )
    wb = load_workbook(tmp_path / "o" / path.name, data_only=True)
    ending = json.loads((run / "summary.json").read_text())["ending_cash_usd"]
    assert abs(wb["Summary"]["B11"].value - ending) < 1.0
    assert wb["Summary"]["B21"].value == "OK"
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                assert not (isinstance(c.value, str) and c.value.startswith("#")), (ws.title, c)


def test_every_dashboard_page_renders(full_run, generated):
    from streamlit.testing.v1 import AppTest

    out, _, _ = full_run
    os.environ["CF_OUTPUTS_DIR"] = str(out)
    os.environ["CF_DATA_DIR"] = str(generated)
    sys.path.insert(0, str(ROOT / "app"))
    try:
        for f in [
            ROOT / "app" / "Home.py",
            *sorted(Path(p) for p in glob.glob(str(ROOT / "app/pages/*.py"))),
        ]:
            at = AppTest.from_file(str(f), default_timeout=120).run()
            assert not at.exception, (f.name, [e.value for e in at.exception])
    finally:
        os.environ.pop("CF_OUTPUTS_DIR")
        os.environ.pop("CF_DATA_DIR")
