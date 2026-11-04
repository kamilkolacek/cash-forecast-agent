"""Forecast accuracy from the latest walk-forward backtest."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.charts import grouped_bars
from components.kpis import kpi_row
from components.loaders import latest_backtest

st.set_page_config(page_title="Backtest", page_icon="💵", layout="wide")
st.title("Forecast accuracy")
bt = latest_backtest()
if not bt:
    st.info(
        "No backtest results yet. Run `make backtest` (about 20 seconds) or `/backtest`, "
        "then refresh."
    )
    st.stop()

st.caption(
    f"{bt['cutoffs']} past forecasts, every two weeks from {bt['first_cutoff']} to "
    f"{bt['last_cutoff']}, each scored against what actually happened. "
    "Error = WAPE (total absolute error ÷ total actual). Lower is better. "
    "Naive = trailing 13-week average held flat."
)
t = bt["targets"]
kpi_row(
    [
        (
            "Closing-cash error, weeks 1-4",
            f"{t['weeks_1_4']['engine']:.1%}",
            f"target ≤ {t['weeks_1_4']['target']:.0%}",
        ),
        (
            "Closing-cash error, weeks 5-13",
            f"{t['weeks_5_13']['engine']:.1%}",
            f"target ≤ {t['weeks_5_13']['target']:.0%}",
        ),
        ("Avg closing-cash miss", f"${bt['closing_balance_mean_abs_error_usd'] / 1e6:,.1f}M", None),
        ("Targets", "PASS" if all(x["passed"] for x in t.values()) else "FAIL", None),
    ]
)

cb = bt["by_week"]["closing_balance"]
wk = sorted(cb, key=int)
st.plotly_chart(
    grouped_bars(
        [f"W{w}" for w in wk],
        {"Engine": [cb[w]["engine"] for w in wk], "Naive": [cb[w]["naive"] for w in wk]},
        "Closing-cash error by weeks ahead",
        yaxis="WAPE",
        scale=0.01,
        fmt="%{y:.1f}%",
    ),
    width="stretch",
)


def pct_table(d: dict) -> pd.DataFrame:
    df = pd.DataFrame(d).T
    return df.map(lambda v: f"{v:.1%}")


c1, c2 = st.columns(2)
with c1:
    st.markdown("**Weekly error by component**")
    st.dataframe(pct_table(bt["by_group"]), width="stretch")
with c2:
    st.markdown("**Cumulative error** (timing slips inside the horizon cancel out)")
    st.dataframe(pct_table(bt["cumulative"]), width="stretch")
st.caption(bt["note"])
if "live" in bt:
    st.subheader("Live forecast vs the 13 held-back weeks")
    st.dataframe(pct_table(bt["live"]["by_group"]), width="stretch")
