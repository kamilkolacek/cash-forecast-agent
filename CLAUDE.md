# Cash Forecast Agent: project context for Claude Code

## What this project is
A 13-week direct-method cash forecast for a fictional B2B SaaS company,
Northwind Cloud, Inc. (~$250M ARR; US/UK/CA entities). All data is synthetic.
Weeks 1-2 are forecast daily; weeks 3-13 weekly. Reporting currency is USD.

## Division of labor
- **Python does all math.** Engine code in `src/cashforecast/` and entry points in
  `scripts/` produce every number.
- **Claude orchestrates and explains.** It runs scripts, interprets variances,
  chooses scenario assumptions within `config/scenarios.yaml`, and writes the narrative.

## Non-negotiable rules
1. Never invent, estimate or round a figure in prose. Every number in a memo or
   summary must appear in a run output under `outputs/runs/<run_id>/`.
2. Never edit files in `data/raw/` by hand. Regenerate with `/generate-data`.
3. A forecast run is valid only if the roll-forward balances
   (opening + receipts - disbursements + financing = closing) for every period.
4. Flag any week where projected cash falls below `min_cash_threshold`
   or the covenant `min_liquidity`.
5. Classify every variance as **timing** (reverses within the horizon) or
   **permanent** (does not reverse), with the driver named.

## Slash commands
| Command | Purpose |
|---|---|
| `/generate-data` | Build or refresh the synthetic dataset |
| `/forecast` | Full weekly run: validate, forecast, variance, scenarios, risk, memo |
| `/variance` | Last forecast vs actuals bridge |
| `/scenario` | Run a named or custom scenario |
| `/backtest` | Walk-forward accuracy report |
| `/cash-memo` | CFO narrative from the latest run |
| `/validate` | Data tie-outs and numeric fidelity check |
| `/dashboard` | Launch the Streamlit dashboard |

## Layout
- `config/`: company, forecast, scenario and category definitions
- `src/cashforecast/`: synthetic data, schemas, engine, backtest, outputs
- `scripts/`: CLI entry points Claude invokes
- `app/`: Streamlit dashboard
- `.claude/`: commands, skills, subagents, hooks

## Commands to know
- `make test`: run the unit and integration tests
- `make data`: generate synthetic data
- `make dashboard`: launch the web UI
