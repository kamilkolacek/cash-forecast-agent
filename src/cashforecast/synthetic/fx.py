"""Daily FX rates (USD per unit of local currency) as a log random walk."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashforecast.synthetic._util import SimContext


def generate_fx(ctx: SimContext) -> pd.DataFrame:
    fx_cfg = ctx.cfg["fx"]
    dates = pd.date_range(ctx.start, ctx.end, freq="D")
    out = pd.DataFrame({"date": dates, "USD": 1.0})
    for ccy, start_rate in fx_cfg["start"].items():
        shocks = ctx.rng.normal(0.0, fx_cfg["daily_vol"], size=len(dates))
        shocks[0] = 0.0
        out[ccy] = start_rate * np.exp(np.cumsum(shocks))
    return out


class FxTable:
    """Fast rate lookup by currency and date."""

    def __init__(self, fx: pd.DataFrame):
        self._fx = fx.set_index("date")

    def rate(self, currency: str, dates: pd.Series | pd.Timestamp):
        series = self._fx[currency]
        if isinstance(dates, pd.Timestamp):
            return float(series.asof(dates))
        raw = pd.DatetimeIndex(dates).values
        lo, hi = series.index[0].to_datetime64(), series.index[-1].to_datetime64()
        idx = pd.DatetimeIndex(np.clip(raw, lo, hi)).normalize()
        return series.reindex(idx, method="ffill").to_numpy()
