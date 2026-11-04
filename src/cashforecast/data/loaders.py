"""Load a generated (or adapter-produced) dataset from disk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from cashforecast.data.schemas import SCHEMAS


def load_dataset(data_dir: Path | str, holdout: bool = False) -> dict[str, pd.DataFrame]:
    folder = Path(data_dir) / "holdout" if holdout else Path(data_dir)
    if not folder.exists():
        raise FileNotFoundError(f"No dataset at {folder}. Run `make data` or /generate-data first.")
    names = [p.stem for p in folder.glob("*.parquet")] if holdout else list(SCHEMAS)
    return {
        n: pd.read_parquet(folder / f"{n}.parquet")
        for n in names
        if (folder / f"{n}.parquet").exists()
    }


def load_manifest(data_dir: Path | str) -> dict[str, Any]:
    return json.loads((Path(data_dir) / "manifest.json").read_text())
