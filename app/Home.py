"""Cash Forecast Agent: dashboard home."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.charts import balance_lines
from components.kpis import kpi_row, m, md, status_badge
from components.loaders import artifact, select_run

st.set_page_config(page_title="Cash Forecast", page_icon="💵", layout="wide")

run = select_run()
s = artifact(run, "summary.json")
weekly = artifact(run, "weekly.csv").set_index("line")
weeks = [c for c in weekly.columns if c.startswith("W")]

st.title("13-Week Cash Forecast")
st.caption(
    f"Northwind Cloud, Inc. (synthetic) · {s['as_of']} to {s['horizon_end']} · run {s['run_id']}"
)

floor, cov = s["min_cash_threshold_usd"], s["covenant_min_liquidity_usd"]
kpi_row(
    [
        ("Opening cash", m(s["opening_cash_usd"]), None),
        ("Ending cash", m(s["ending_cash_usd"]), m(s["ending_cash_usd"] - s["opening_cash_usd"])),
        ("Lowest cash", m(s["min_cash_usd"]), s["min_cash_date"]),
        ("Headroom to floor", m(s["min_cash_usd"] - floor), None),
    ]
)
status_badge(s["min_cash_usd"], floor, cov)

daily = artifact(run, "daily.parquet")
series = {"Daily closing cash": daily.set_index("date")["closing_balance_usd"]}
scen = artifact(run, "scenarios.json")
if scen:
    for name in ("downside", "severe_downside"):
        if name in scen["weekly_closing"]:
            wc = pd.Series(scen["weekly_closing"][name])
            wc.index = [pd.Timestamp(s["week_ending"][w]) for w in wc.index]
            series[f"{name.replace('_', ' ').title()} (week-end)"] = wc
st.plotly_chart(
    balance_lines(series, floor, cov, "Projected cash vs floor and covenant"), width="stretch"
)

left, right = st.columns([3, 2])
with left:
    st.subheader("Where the cash goes")
    cats = weekly[~weekly.index.str.startswith(("Total", "Net", "Opening", "Closing", "Minimum"))]
    totals = cats[weeks].sum(axis=1)
    totals = totals[totals.abs() > 1].sort_values(key=abs, ascending=False).head(10)
    st.dataframe(
        pd.DataFrame({"13-week total": totals.map(m)}).rename_axis("Category"), width="stretch"
    )
with right:
    st.subheader("Data findings")
    val = artifact(run, "validation.json")
    if val:
        for f in val["findings"]:
            if f["severity"] == "WARNING" and not f["passed"]:
                st.warning(md(f"**{f['check'].split(':')[1].replace('_', ' ')}**: {f['detail']}"))
            elif f["severity"] == "INFO":
                st.info(md(f["detail"]))
    else:
        st.caption("No validation results saved with this run.")
    var = artifact(run, "variance.json")
    if var:
        vs = var["summary"]
        st.subheader("Last week vs forecast")
        st.metric(
            "Variance",
            m(vs["total_variance_usd"]),
            md(f"timing {m(vs['timing_usd'])} · permanent {m(vs['permanent_usd'])}"),
            delta_color="off",
        )

memo = artifact(run, "memo.md")
st.divider()
if memo:
    with st.expander("CFO memo for this run", expanded=True):
        st.markdown(md(memo))
else:
    st.caption("No memo yet for this run. In Claude Code, run `/cash-memo`.")

xlsx = next(run.glob("cash_forecast_*.xlsx"), None)
if xlsx:
    st.download_button(
        "Download Excel workbook",
        xlsx.read_bytes(),
        file_name=xlsx.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
