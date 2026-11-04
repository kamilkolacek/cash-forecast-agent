"""Saved scenarios plus a live what-if built from sliders."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.charts import balance_lines
from components.kpis import kpi_row, m, money_table, status_badge
from components.loaders import artifact, base_forecast, select_run

st.set_page_config(page_title="Scenarios", page_icon="💵", layout="wide")
run = select_run()
s = artifact(run, "summary.json")
sc = artifact(run, "scenarios.json")
floor, cov = s["min_cash_threshold_usd"], s["covenant_min_liquidity_usd"]
st.title("Scenarios")


def weekly_series(wc: dict) -> pd.Series:
    out = pd.Series(wc)
    out.index = [pd.Timestamp(s["week_ending"][w]) for w in out.index]
    return out


if sc:
    names = list(sc["scenarios"])
    picked = st.multiselect(
        "Show scenarios",
        names,
        default=[n for n in ("base", "downside", "severe_downside", "upside") if n in names],
    )
    st.plotly_chart(
        balance_lines(
            {n: weekly_series(sc["weekly_closing"][n]) for n in picked},
            floor,
            cov,
            "Week-end cash by scenario",
        ),
        width="stretch",
    )
    df = pd.DataFrame(sc["scenarios"]).T.reset_index(names="scenario")
    df["flagged weeks"] = df["flags"].map(len)
    cols = [
        "scenario",
        "description",
        "ending_cash_usd",
        "change_vs_base_usd",
        "min_cash_usd",
        "min_cash_date",
        "floor_headroom_usd",
        "covenant_headroom_usd",
        "suggested_revolver_draw_usd",
        "flagged weeks",
    ]
    st.dataframe(
        money_table(
            df[cols],
            [
                "ending_cash_usd",
                "change_vs_base_usd",
                "min_cash_usd",
                "floor_headroom_usd",
                "covenant_headroom_usd",
                "suggested_revolver_draw_usd",
            ],
        ),
        width="stretch",
        hide_index=True,
    )
    st.caption(sc["note"])

st.divider()
st.subheader("Build a what-if")
st.caption(
    "Sliders apply shocks to this run's forecast with the same engine Claude uses for "
    "`/scenario`. Nothing is saved; use `/scenario` to record one."
)
c1, c2, c3 = st.columns(3)
whale_days = c1.slider("Largest whales pay late (days)", 0, 90, 0, 5)
whales_n = c1.radio("Which whales", ["Top 1", "All 5"], horizontal=True)
churn = c2.slider("Renewal cash lost to churn (%)", 0, 40, 0, 5)
slow = c2.slider("All collections slower (days)", -10, 30, 0, 1)
payroll = c3.slider("Payroll change from week 3 (%)", -10, 10, 0, 1)
one_off = c3.number_input("One-off outflow ($M)", 0.0, 100.0, 0.0, 1.0)
one_off_date = c3.date_input(
    "One-off date",
    pd.Timestamp(s["as_of"]) + pd.Timedelta(weeks=6),
    min_value=pd.Timestamp(s["as_of"]),
    max_value=pd.Timestamp(s["horizon_end"]),
)

shocks: list[dict] = []
if whale_days:
    shocks.append(
        {
            "type": "customer_delay",
            "delay_days": whale_days,
            "target": "top_whale" if whales_n == "Top 1" else "top_whales",
        }
    )
if churn:
    shocks.append({"type": "churn", "pct_renewals_lost": churn / 100})
if slow:
    shocks.append({"type": "collections_delay", "delay_days": slow})
if payroll:
    shocks.append({"type": "payroll_adjust", "pct_change": payroll / 100, "effective_week": 3})
if one_off:
    shocks.append(
        {
            "type": "one_off",
            "date": str(one_off_date),
            "amount_usd": -one_off * 1e6,
            "category": "capex",
            "note": "dashboard what-if",
        }
    )

if shocks:
    from cashforecast.engine.scenarios import run_scenarios

    with st.spinner("Running the engine..."):
        base, data = base_forecast(s["as_of"])
        res = run_scenarios(base, data, names=["base"], custom={"what_if": shocks})
    r = res["scenarios"]["what_if"]
    kpi_row(
        [
            ("Ending cash", m(r["ending_cash_usd"]), m(r["change_vs_base_usd"])),
            ("Lowest cash", m(r["min_cash_usd"]), r["min_cash_date"]),
            ("Headroom to floor", m(r["floor_headroom_usd"]), None),
            ("Suggested revolver draw", m(r["suggested_revolver_draw_usd"]), None),
        ]
    )
    status_badge(r["min_cash_usd"], floor, cov)
    st.plotly_chart(
        balance_lines(
            {
                "What-if": weekly_series(res["weekly_closing"]["what_if"]),
                "Base": weekly_series(res["weekly_closing"]["base"]),
            },
            floor,
            cov,
            "What-if vs base",
        ),
        width="stretch",
    )
    with st.expander("Shocks applied (paste into /scenario to save)"):
        st.json(shocks)
else:
    st.info("Move a slider to run a what-if.")
