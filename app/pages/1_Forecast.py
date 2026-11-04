"""13-week view, weeks 1-2 daily, and drill-down to source lines."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from components.charts import cash_bars_and_balance
from components.kpis import m, money_table
from components.loaders import artifact, select_run

st.set_page_config(page_title="Forecast", page_icon="💵", layout="wide")
run = select_run()
s = artifact(run, "summary.json")
weekly = artifact(run, "weekly.csv")
w = weekly.set_index("line")
weeks = [c for c in weekly.columns if c.startswith("W")]

st.title("13-week forecast")
labels = [f"{wk} · {s['week_ending'][wk][5:]}" for wk in weeks]
dis = (
    w.loc["Total operating disbursements", weeks]
    + w.loc["Total non-operating disbursements", weeks]
)
st.plotly_chart(
    cash_bars_and_balance(
        labels,
        w.loc["Total receipts", weeks].tolist(),
        dis.tolist(),
        w.loc["Closing cash", weeks].tolist(),
        "Weekly receipts, disbursements and closing cash",
    ),
    width="stretch",
)

st.subheader("Category by week ($M)")
show = weekly.copy()
show["line"] = show["line"].str.replace("_", " ")
show = show[(show[weeks].abs().sum(axis=1) > 1) | show["section"].eq("summary")]
table = money_table(show.drop(columns=["section"]).set_index("line"), weeks)
st.dataframe(table, width="stretch", height=min(38 * (len(table) + 1), 900))

st.subheader("Weeks 1-2, daily")
dd = artifact(run, "daily_detail.csv", parse_dates=["date"])
dd["day"] = dd["date"].dt.strftime("%a %b %d")
st.plotly_chart(
    cash_bars_and_balance(
        dd["day"].tolist(),
        dd["receipts_usd"].tolist(),
        dd["disbursements_usd"].tolist(),
        dd["closing_balance_usd"].tolist(),
    ),
    width="stretch",
)

st.subheader("Drill into a number")
lines = artifact(run, "lines.parquet")
c1, c2 = st.columns(2)
cats = sorted(lines["category"].unique())
cat = c1.selectbox(
    "Category",
    cats,
    index=cats.index("customer_collections_existing_ar")
    if "customer_collections_existing_ar" in cats
    else 0,
)
wk = c2.selectbox("Week", weeks, format_func=lambda x: f"{x} (ending {s['week_ending'][x]})")
start = pd.Timestamp(s["as_of"]) + pd.Timedelta(weeks=weeks.index(wk))
sel = lines[
    (lines["category"] == cat)
    & (lines["date"] >= start)
    & (lines["date"] < start + pd.Timedelta(days=7))
]
grp = (
    sel.groupby(["source_type", "source_id", "customer_id", "note"], dropna=False)["amount_usd"]
    .sum()
    .reset_index()
    .sort_values("amount_usd", key=abs, ascending=False)
)
st.caption(
    f"{len(grp)} sources totalling {m(sel['amount_usd'].sum(), 2)}. "
    "Every forecast number traces to an invoice, contract, deal, bill or schedule row."
)
st.dataframe(money_table(grp, ["amount_usd"], 3), width="stretch", hide_index=True)
