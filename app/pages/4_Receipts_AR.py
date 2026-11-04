"""Collections: forecast by stream, AR aging, and concentration."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from components.charts import SERIES, _layout
from components.kpis import kpi_row, m, money_table
from components.loaders import artifact, dataset_for, select_run

st.set_page_config(page_title="Receipts & AR", page_icon="💵", layout="wide")
run = select_run()
s = artifact(run, "summary.json")
weekly = artifact(run, "weekly.csv").set_index("line")
weeks = [c for c in weekly.columns if c.startswith("W")]
st.title("Receipts and receivables")

streams = {
    "Open invoices": "customer_collections_existing_ar",
    "Contract installments": "customer_collections_contracted",
    "Renewals": "customer_collections_renewals",
    "New bookings": "customer_collections_new_bookings",
}
fig = go.Figure()
for i, (label, cat) in enumerate(streams.items()):
    if cat in weekly.index:
        fig.add_bar(
            x=[f"{w} · {s['week_ending'][w][5:]}" for w in weeks],
            y=(weekly.loc[cat, weeks] / 1e6).tolist(),
            name=label,
            marker_color=SERIES[i],
            hovertemplate="%{y:$,.2f}M",
        )
fig.update_layout(barmode="stack")
st.plotly_chart(_layout(fig, "Forecast collections by stream"), width="stretch")

from components.loaders import DATA  # noqa: E402

from cashforecast.data.loaders import load_manifest  # noqa: E402
from cashforecast.engine.snapshot import take_snapshot  # noqa: E402

as_of = pd.Timestamp(s["as_of"])
data = dataset_for(s["as_of"])
snap = take_snapshot(data, as_of, pd.Timestamp(load_manifest(DATA)["as_of"]))
inv = snap["invoices"]
open_ = inv[inv["status"] == "open"].copy()
fx_last = snap["fx_rates"].iloc[-1]
open_["open_usd"] = open_["open_amount_local"] * open_["currency"].map(lambda c: float(fx_last[c]))
open_["days_past_due"] = (as_of - open_["due_date"]).dt.days
bins = [-10_000, 0, 30, 60, 90, 10_000]
names = ["Current", "1-30", "31-60", "61-90", "90+"]
open_["bucket"] = pd.cut(open_["days_past_due"], bins=bins, labels=names)
aging = open_.groupby("bucket", observed=False)["open_usd"].sum().reindex(names)

cust = data["customers"].set_index("customer_id")
open_["whale"] = open_["customer_id"].map(cust["is_whale"]).fillna(False)
past_due = open_.loc[open_["days_past_due"] > 0, "open_usd"].sum()
kpi_row(
    [
        ("Open AR", m(open_["open_usd"].sum()), None),
        ("Past due", m(past_due), None),
        ("Held by whales", m(open_.loc[open_["whale"], "open_usd"].sum()), None),
        ("Disputed", m(open_.loc[open_["is_disputed"], "open_usd"].sum()), None),
    ]
)

c1, c2 = st.columns(2)
with c1:
    afig = go.Figure(
        go.Bar(
            x=names,
            y=(aging / 1e6).tolist(),
            marker_color=["#2E7D32", "#9E9E9E", "#EF6C00", "#C62828", "#6A1B9A"],
            hovertemplate="%{y:$,.2f}M",
        )
    )
    st.plotly_chart(_layout(afig, "AR aging (days past due)"), width="stretch")
with c2:
    top = (
        open_[open_["days_past_due"] > 0]
        .groupby("customer_id")
        .agg(
            open_usd=("open_usd", "sum"),
            invoices=("invoice_id", "count"),
            max_days_past_due=("days_past_due", "max"),
        )
        .sort_values("open_usd", ascending=False)
        .head(10)
    )
    top["archetype"] = top.index.map(cust["archetype"])
    top["whale"] = top.index.map(cust["is_whale"]).map({True: "yes", False: ""})
    st.markdown("**Largest past-due customers**")
    st.dataframe(money_table(top.reset_index(), ["open_usd"], 2), width="stretch", hide_index=True)

val = artifact(run, "validation.json")
if val:
    brk = next((f for f in val["findings"] if f["check"] == "dq:payment_behavior_break"), None)
    if brk and not brk["passed"]:
        st.subheader("Customers outside their normal payment pattern")
        st.caption("Forecast counts these at 50%, collected about 30 days out. Call them.")
        st.dataframe(
            money_table(pd.DataFrame(brk["data"]["invoices"]), ["amount_usd_at_issue"], 2),
            width="stretch",
            hide_index=True,
        )
