"""Shared fixtures: one synthetic dataset per test session."""

from __future__ import annotations

import pandas as pd
import pytest

from cashforecast.config import load_yaml
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.data.validation import validate
from cashforecast.engine.forecast import run_forecast
from cashforecast.synthetic.generator import generate


@pytest.fixture(scope="session")
def generated(tmp_path_factory):
    out = tmp_path_factory.mktemp("data")
    generate(out)
    return out


@pytest.fixture(scope="session")
def dataset(generated):
    d = load_dataset(generated)
    m = load_manifest(generated)
    hold = load_dataset(generated, holdout=True)
    report = validate(
        d, load_yaml("company.yaml")["balance_sheet"]["opening_cash"], pd.Timestamp(m["as_of"])
    )
    return d, hold, m, report


@pytest.fixture(scope="session")
def live_forecast(dataset):
    d, _, m, _ = dataset
    return run_forecast(d, pd.Timestamp(m["as_of"]))
