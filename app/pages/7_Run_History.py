"""All forecast runs, their headline numbers, memos and downloads."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from components.kpis import md, money_table
from components.loaders import RUNS, list_runs

st.set_page_config(page_title="Run History", page_icon="💵", layout="wide")
st.title("Run history")

rows = []
for rid in list_runs():
    s = json.loads((RUNS / rid / "summary.json").read_text())
    v = RUNS / rid / "variance.json"
    rows.append(
        {
            "run": rid,
            "as_of": s["as_of"],
            "opening": s["opening_cash_usd"],
            "ending": s["ending_cash_usd"],
            "lowest": s["min_cash_usd"],
            "lowest_date": s["min_cash_date"],
            "flags": len(s["flags"]),
            "variance": json.loads(v.read_text())["summary"]["total_variance_usd"]
            if v.exists()
            else None,
            "memo": "yes" if (RUNS / rid / "memo.md").exists() else "",
            "review": "yes" if (RUNS / rid / "review.md").exists() else "",
        }
    )
if not rows:
    st.info("No runs yet.")
    st.stop()
df = pd.DataFrame(rows)
st.dataframe(
    money_table(df, ["opening", "ending", "lowest", "variance"]), width="stretch", hide_index=True
)

rid = st.selectbox("Open a run", df["run"].tolist())
run = RUNS / rid
tabs = st.tabs(["Memo", "Review", "Facts sheet", "Assumptions", "Downloads"])
with tabs[0]:
    st.markdown(
        md((run / "memo.md").read_text())
        if (run / "memo.md").exists()
        else "_No memo. Run `/cash-memo` in Claude Code._"
    )
with tabs[1]:
    st.markdown(
        md((run / "review.md").read_text())
        if (run / "review.md").exists()
        else "_No independent review. `/forecast` runs the forecast-reviewer subagent._"
    )
with tabs[2]:
    st.markdown(
        md((run / "facts.md").read_text()) if (run / "facts.md").exists() else "_No facts sheet._"
    )
with tabs[3]:
    st.json(json.loads((run / "assumptions.json").read_text()), expanded=False)
with tabs[4]:
    for p in sorted(run.iterdir()):
        if p.suffix in (".xlsx", ".md", ".csv", ".json"):
            st.download_button(p.name, p.read_bytes(), file_name=p.name, key=f"dl-{p.name}")
