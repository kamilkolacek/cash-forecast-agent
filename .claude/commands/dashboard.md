---
description: Launch the Streamlit cash dashboard for the latest forecast run
---

1. If `outputs/runs/LATEST` doesn't exist, run `python scripts/run_weekly.py` first.
2. Start the dashboard in the background: `streamlit run app/Home.py --server.headless true`.
3. Tell the user it is at http://localhost:8501 and what each page is for:
   - **Home**: headline KPIs, cash vs floor and covenant, data findings, the CFO memo,
     Excel download
   - **Forecast**: 13-week chart and table, weeks 1–2 daily, drill-down to source lines
   - **Variance**: waterfall bridge and timing vs permanent by driver
   - **Scenarios**: saved scenarios plus live what-if sliders
   - **Receipts & AR**: collections by stream, AR aging, past-due and pattern-break customers
   - **Liquidity & Risk**: weekly low points, headroom by scenario, revolver
   - **Backtest**: accuracy vs the naive baseline (run `make backtest` first)
   - **Run History**: every run, its memo, review, facts sheet and downloads
4. Note that the what-if sliders don't save anything; to record a scenario, use `/scenario`.
