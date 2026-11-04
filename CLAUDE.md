# Cash Forecast Agent: project context for Claude Code

## What this project is
A 13-week direct-method cash forecast for a fictional B2B SaaS company,
Northwind Cloud, Inc. (~$250M ARR; US/UK/CA entities). All data is synthetic.
Weeks 1-2 are shown daily; weeks 3-13 weekly. Reporting currency is USD.

## Division of labor
- **Python does all math.** Engine code in `src/cashforecast/` and entry points in
  `scripts/` produce every number.
- **Claude orchestrates and explains.** It runs scripts, reviews output, translates
  what-if questions into scenario shocks, and writes the narrative.

## Non-negotiable rules
1. Never invent, estimate or round a figure in prose. Every figure in a memo or summary
   must appear in the run artifacts; cite it as written in `facts.md`. A PostToolUse hook
   (`.claude/hooks/check_numbers.py`) blocks a `memo.md` containing untraceable figures.
2. Never edit files in `data/raw/` by hand. Regenerate with `/generate-data`.
3. Never forecast on data that failed validation (any ERROR check).
4. Flag any week where the minimum daily balance falls below `min_cash_threshold`
   or the covenant `min_liquidity`.
5. Classify every variance as **timing** or **permanent** using the computed split
   in `variance.json`, and name the driver.

## Slash commands
| Command | Purpose |
|---|---|
| `/generate-data` | Build or refresh the synthetic dataset |
| `/validate` | Data tie-outs and data-quality findings |
| `/forecast` | Full weekly cycle: validate → engine → variance → scenarios → review → memo |
| `/variance` | Forecast vs actuals, timing / permanent |
| `/scenario` | Named scenario or plain-English what-if |
| `/cash-memo` | (Re)write the CFO memo for the latest run |
| `/backtest` | Walk-forward accuracy report |
| `/dashboard` | Launch the Streamlit dashboard |

## Skills and subagents
- Skills (`.claude/skills/`): `cash-forecasting`, `saas-receipts`, `variance-analysis`,
  `treasury-risk`, `cfo-narrative`.
- Subagents (`.claude/agents/`): `data-validator` (read-only checks before a run),
  `forecast-reviewer` (independent review, writes `review.md`).

## Layout
- `config/`: company, forecast, scenario and category definitions
- `src/cashforecast/`: synthetic data, data checks, engine, backtest, outputs
- `scripts/`: CLI entry points Claude invokes
- `outputs/runs/<run_id>/`: run artifacts incl. `cash_forecast_<date>.xlsx`; `outputs/runs/LATEST` names the newest
- `app/`: Streamlit dashboard (8 pages)
- `docs/`: methodology and data dictionary

## Commands to know
- `make test`: unit and integration tests
- `make data`: generate synthetic data
- `make weekly`: deterministic part of the weekly cycle
- `make backtest`: accuracy report
