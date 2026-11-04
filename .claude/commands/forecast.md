---
description: Run the 13-week cash forecast and summarize it for the CFO
argument-hint: "[--as-of YYYY-MM-DD]"
---

Run the weekly cash forecast. (Phase 2–3 version: engine run and summary. Variance,
scenarios, independent review and the memo are added in Phase 4–5.)

1. Run `python scripts/validate.py`. If any ERROR check fails, stop and report it.
   List WARNING findings; they become risks in the summary.
2. Run `python scripts/run_forecast.py $ARGUMENTS`.
3. Read `summary.json`, `weekly.csv` and `assumptions.json` from the run directory printed
   on the last line (also named in `outputs/runs/LATEST`).
4. Summarize for a CFO in under 250 words:
   - Opening, ending and minimum cash with the minimum's date, versus the internal floor
     and the covenant. Name any flagged weeks.
   - The 2–3 largest drivers of the 13-week movement, by category from `weekly.csv`.
   - Key assumptions that most affect the result (from `assumptions.json`): renewal
     churn/expansion, open-AR rules applied to late or disputed invoices, AP seasonality.
   - Risks from validation warnings, such as customers outside their normal payment pattern.
5. Every figure you state must appear in the run artifacts. Do not compute new totals
   in prose; if you need one, say which artifact line it comes from.
