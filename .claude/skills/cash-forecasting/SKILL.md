---
name: cash-forecasting
description: How this project's 13-week direct-method cash forecast works and how to read its run artifacts. Use whenever running, explaining, reviewing or troubleshooting a forecast run.
---

# Cash forecasting

The engine is deterministic Python. Your job is to run it, read its outputs, and explain
them. You never produce a forecast number yourself.

## Run artifacts (`outputs/runs/<run_id>/`)

| File | What it is | Use it for |
|---|---|---|
| `facts.md` | Pre-formatted figures from every artifact | **The only source for figures in prose** |
| `summary.json` | Opening, ending, minimum cash, flags, week-ending dates | Headline |
| `weekly.csv` | Category x week table, section totals, opening/closing, weekly minimum | The 13-week view |
| `daily_detail.csv` | Weeks 1–2 by day | Near-term liquidity |
| `lines.parquet` | Every forecast cash item with `source_type`, `source_id`, `note` | Drilling into a driver |
| `assumptions.json` | Every learned parameter | Explaining *why* |
| `variance.json` | Prior forecast vs actuals, timing/permanent | `variance-analysis` skill |
| `scenarios.json` | Each scenario's ending/minimum cash, headroom, suggested draw | `treasury-risk` skill |
| `validation.json` | Tie-outs and data-quality findings | Risks |

`outputs/runs/LATEST` names the newest run.

## The model in one paragraph

Receipts come from four streams: open AR timed by each customer's own payment lateness,
unbilled installments of current contracts, renewals weighted by churn and expansion by
archetype, and probability-weighted pipeline. Disbursements come from known schedules
(payroll calendars, debt, tax, capex plan, open AP bills on Tue/Fri runs) plus learned
run rates with seasonality for AP not yet billed. Interest income is earned on the
projected balance. Details: `docs/methodology.md`.

## Drilling into a number

To explain what makes up a weekly figure, filter `lines.parquet` by week and category:

```bash
python -c "import pandas as pd; l=pd.read_parquet('outputs/runs/<run_id>/lines.parquet'); \
w=l[(l.date>='2026-11-22')&(l.date<='2026-11-28')]; \
print(w.groupby(['category','source_type'])['amount_usd'].sum().round(0))"
```

The `note` column says which rule produced each line (e.g. "behavior break: 50% weighted").

## Rules

- A run is valid only if validation passed and the roll-forward balances (the engine
  raises if it doesn't).
- Quote figures exactly as written in `facts.md`. If a figure you need isn't there, say so;
  don't compute it.
- Positive amounts are cash in, negative are cash out.
