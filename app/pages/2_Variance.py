"""Forecast vs actual with timing / permanent split."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.charts import grouped_bars, waterfall
from components.kpis import kpi_row, m, money_table
from components.loaders import artifact, select_run

st.set_page_config(page_title="Variance", page_icon="💵", layout="wide")
run = select_run()
v = artifact(run, "variance.json")
st.title("Forecast vs actual")
if not v:
    st.info("This run has no variance analysis. Runs from `make weekly` or `/forecast` include it.")
    st.stop()

vs = v["summary"]
st.caption(
    f"Window {vs['window']}, forecast made {vs['prior_cutoff']}. "
    f"Permanent = {vs['permanent_definition']}."
)
kpi_row(
    [
        ("Forecast closing cash", m(vs["forecast_closing_cash_usd"]), None),
        ("Actual closing cash", m(vs["actual_closing_cash_usd"]), m(vs["total_variance_usd"])),
        ("Timing (still coming)", m(vs["timing_usd"]), None),
        ("Permanent (not coming)", m(vs["permanent_usd"]), None),
    ]
)

drivers = pd.read_csv(run / "variance_drivers.csv")
top = drivers.reindex(drivers["variance"].abs().sort_values(ascending=False).index).head(6)
other = vs["total_variance_usd"] - top["variance"].sum()
labels = ["Forecast close"] + [
    f"{d} ({'whale' if w else t})" if t == "customer" else d.replace("_", " ")
    for d, t, w in zip(top["driver"], top["type"], top["is_whale"], strict=True)
]
labels += ["All other", "Actual close"]
values = [
    vs["forecast_closing_cash_usd"],
    *top["variance"].tolist(),
    other,
    vs["actual_closing_cash_usd"],
]
st.plotly_chart(
    waterfall(labels, values, "Bridge: forecast to actual closing cash"), width="stretch"
)

big = drivers.reindex(
    (drivers["variance"].abs() + drivers["permanent"].abs()).sort_values(ascending=False).index
).head(10)
st.plotly_chart(
    grouped_bars(
        big["driver"].tolist(),
        {"Timing": big["timing"].tolist(), "Permanent": big["permanent"].tolist()},
        "Timing vs permanent by driver",
        scale=1e3,
        yaxis="$K",
        fmt="%{y:$,.0f}K",
    ),
    width="stretch",
)

st.subheader("Drivers")
cols = [
    "driver",
    "type",
    "archetype",
    "is_whale",
    "forecast_window",
    "actual_window",
    "variance",
    "timing",
    "permanent",
    "classification",
    "forecast_basis",
]
st.dataframe(
    money_table(
        drivers[cols].head(25),
        ["forecast_window", "actual_window", "variance", "timing", "permanent"],
        2,
    ),
    width="stretch",
    hide_index=True,
)
st.subheader("By bank category")
st.dataframe(
    money_table(pd.DataFrame(v["by_category"]), ["forecast", "actual", "variance"], 2),
    width="stretch",
    hide_index=True,
)
