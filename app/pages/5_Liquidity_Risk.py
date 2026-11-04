"""Liquidity: low points, headroom by scenario, revolver."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.charts import COVENANT, FLOOR, INK, _layout, threshold_lines
from components.kpis import kpi_row, m, md, status_badge
from components.loaders import artifact, select_run

st.set_page_config(page_title="Liquidity & Risk", page_icon="💵", layout="wide")
run = select_run()
s = artifact(run, "summary.json")
sc = artifact(run, "scenarios.json")
weekly = artifact(run, "weekly.csv").set_index("line")
weeks = [c for c in weekly.columns if c.startswith("W")]
floor, cov = s["min_cash_threshold_usd"], s["covenant_min_liquidity_usd"]
st.title("Liquidity and risk")

revolver = next(iter(sc["scenarios"].values()))["revolver_available_usd"] if sc else 0.0
kpi_row(
    [
        ("Lowest cash (base)", m(s["min_cash_usd"]), s["min_cash_date"]),
        ("Headroom to floor", m(s["min_cash_usd"] - floor), None),
        ("Headroom to covenant", m(s["min_cash_usd"] - cov), None),
        ("Undrawn revolver", m(revolver), None),
    ]
)
status_badge(s["min_cash_usd"], floor, cov)

lows = weekly.loc["Minimum daily cash", weeks]
colors = [COVENANT if v < cov else FLOOR if v < floor else INK for v in lows]
fig = go.Figure(
    go.Bar(
        x=[f"{w} · {s['week_ending'][w][5:]}" for w in weeks],
        y=(lows / 1e6).tolist(),
        marker_color=colors,
        hovertemplate="%{y:$,.1f}M",
    )
)
st.plotly_chart(
    _layout(threshold_lines(fig, floor, cov), "Lowest daily cash in each week (base)"),
    width="stretch",
)

if sc:
    df = pd.DataFrame(sc["scenarios"]).T
    df = df.sort_values("min_cash_usd")
    hf = go.Figure()
    hf.add_bar(
        y=df.index.tolist(),
        x=(df["floor_headroom_usd"] / 1e6).tolist(),
        orientation="h",
        name="Headroom to floor",
        marker_color=[COVENANT if v < 0 else INK for v in df["floor_headroom_usd"]],
        hovertemplate="%{x:$,.1f}M",
    )
    hf.add_vline(x=0, line_color=FLOOR)
    lay = _layout(hf, "Headroom to the internal floor at each scenario's low point", yaxis="")
    lay.update_xaxes(title="$M")
    st.plotly_chart(lay, width="stretch")

    st.subheader("Worst case")
    worst = df.iloc[0]
    msg = (
        f"**{df.index[0].replace('_', ' ')}**: {worst['description']}. Low point "
        f"{m(worst['min_cash_usd'])} on {worst['min_cash_date']}, "
        f"{m(worst['floor_headroom_usd'])} vs the floor. Total liquidity at that point including "
        f"the undrawn revolver: {m(worst['total_liquidity_at_low_point_usd'])}."
    )
    if worst["suggested_revolver_draw_usd"] > 0:
        st.error(md(msg + f" Suggested revolver draw: {m(worst['suggested_revolver_draw_usd'])}."))
    else:
        st.success(md(msg + " No draw needed."))
