"""Shared helpers for the synthetic data generator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class SimContext:
    """Everything a generator module needs: config, randomness, and the time window."""

    cfg: dict[str, Any]
    rng: np.random.Generator
    start: pd.Timestamp  # first day of history
    as_of: pd.Timestamp  # forecast date; history ends the day before
    end: pd.Timestamp  # last simulated day (as_of + holdout)


def bday(d: pd.Timestamp) -> pd.Timestamp:
    """Roll a date forward to the next business day (weekends only)."""
    return pd.Timestamp(np.busday_offset(np.datetime64(d.date(), "D"), 0, roll="forward"))


def bday_series(s: pd.Series) -> pd.Series:
    """Vectorized version of bday for a datetime Series."""
    arr = s.values.astype("datetime64[D]")
    return pd.Series(pd.to_datetime(np.busday_offset(arr, 0, roll="forward")), index=s.index)


def month_starts(start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start.replace(day=1), end, freq="MS")


def lognormal_to_total(rng: np.random.Generator, n: int, total: float, sigma: float = 0.6):
    """n positive draws with a right skew, scaled to sum to total."""
    if n == 0:
        return np.array([])
    x = rng.lognormal(mean=0.0, sigma=sigma, size=n)
    return x / x.sum() * total
