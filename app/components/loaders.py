"""Data access for the dashboard. Every page reads run artifacts through these helpers."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Overridable so tests (and other deployments) can point the app at another location.
OUTPUTS = Path(os.environ.get("CF_OUTPUTS_DIR", ROOT / "outputs"))
RUNS = OUTPUTS / "runs"
BACKTESTS = OUTPUTS / "backtest"
DATA = Path(os.environ.get("CF_DATA_DIR", ROOT / "data" / "raw"))


def list_runs() -> list[str]:
    if not RUNS.exists():
        return []
    return sorted((p.name for p in RUNS.iterdir() if (p / "summary.json").exists()), reverse=True)


def select_run() -> Path | None:
    """Sidebar run picker shared across pages (defaults to the latest run)."""
    runs = list_runs()
    if not runs:
        st.warning(
            "No forecast runs yet. Run `make data` then `make weekly` "
            "(or `/forecast` in Claude Code), then refresh."
        )
        st.stop()
    latest = (RUNS / "LATEST").read_text().strip() if (RUNS / "LATEST").exists() else runs[0]
    default = st.session_state.get("run_id", latest if latest in runs else runs[0])
    run_id = st.sidebar.selectbox(
        "Forecast run", runs, index=runs.index(default), help="Run folders under outputs/runs/"
    )
    st.session_state["run_id"] = run_id
    st.sidebar.caption("Synthetic data: Northwind Cloud, Inc.")
    return RUNS / run_id


@st.cache_data
def read_json(path: str, mtime: float) -> dict:
    return json.loads(Path(path).read_text())


@st.cache_data
def read_csv(path: str, mtime: float, **kw) -> pd.DataFrame:
    return pd.read_csv(path, **kw)


@st.cache_data
def read_parquet(path: str, mtime: float) -> pd.DataFrame:
    return pd.read_parquet(path)


def artifact(run: Path, name: str, **kw):
    """Load a run artifact by file name, or None if this run doesn't have it."""
    p = run / name
    if not p.exists():
        return None
    m = p.stat().st_mtime
    if name.endswith(".json"):
        return read_json(str(p), m)
    if name.endswith(".csv"):
        return read_csv(str(p), m, **kw)
    if name.endswith(".parquet"):
        return read_parquet(str(p), m)
    return p.read_text()


@st.cache_resource
def dataset_for(as_of: str) -> dict[str, pd.DataFrame]:
    """The dataset as seen by a run: history, plus holdout if the run is a simulated later week."""
    from cashforecast.data.loaders import load_dataset, load_manifest
    from cashforecast.data.timeline import combine_with_holdout

    data = load_dataset(DATA)
    if pd.Timestamp(as_of) > pd.Timestamp(load_manifest(DATA)["as_of"]):
        data = combine_with_holdout(data, load_dataset(DATA, holdout=True))
    return data


@st.cache_resource
def base_forecast(as_of: str):
    """Re-run the engine for a run's date (used by live scenario sliders)."""
    from cashforecast.data.loaders import load_manifest
    from cashforecast.engine.forecast import run_forecast

    data = dataset_for(as_of)
    return run_forecast(data, pd.Timestamp(as_of), pd.Timestamp(load_manifest(DATA)["as_of"])), data


def latest_backtest() -> dict | None:
    if not BACKTESTS.exists():
        return None
    runs = sorted(p for p in BACKTESTS.iterdir() if (p / "summary.json").exists())
    return (
        json.loads((runs[-1] / "summary.json").read_text()) | {"_dir": runs[-1].name}
        if runs
        else None
    )
