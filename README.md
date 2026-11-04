# Cash Forecast Agent

A Claude Code agent that produces a **13-week direct-method cash forecast** for a
fictional B2B SaaS company, with variance analysis, scenarios, liquidity risk flags,
a CFO memo, and a Streamlit dashboard. All data is synthetic.

> **Status:** Phase 6 (Excel workbook and dashboard). See the roadmap below.
>
> **See it first:** a sample [CFO memo](docs/examples/sample_run/memo.md), the [facts sheet](docs/examples/sample_run/facts.md) it was written from, and the [Excel workbook](docs/examples/sample_run/cash_forecast_2026-11-29.xlsx).

## How it works

- **Python does the math.** A deterministic engine forecasts receipts (AR aging,
  customer payment behavior, renewals, pipeline) and disbursements (payroll,
  commissions, cloud hosting, AP, debt, tax, capex), then rolls cash forward.
- **Claude orchestrates and explains.** Slash commands run the engine, classify
  variances as timing or permanent, run scenarios, and write the narrative.
- **Every number is traceable.** A hook checks that each figure in the memo exists
  in the run output.

## The company: Northwind Cloud, Inc. (fictional)

| | |
|---|---|
| ARR | ~$250M, entities in US, UK, Canada |
| Billing mix | 60% annual, 25% quarterly, 15% monthly |
| Customers | ~1,200; enterprise, mid-market, SMB archetypes; 5 whales ≈ 20% of AR |
| Forecast | 13 weeks; daily detail for weeks 1–2 |

## Quickstart

```bash
git clone https://github.com/kamilkolacek/cash-forecast-agent.git
cd cash-forecast-agent
make setup        # create venv, install, enable pre-commit
make test         # run tests
make data         # generate synthetic data (~30s)
make forecast     # run the 13-week forecast
make weekly       # forecast + variance + scenarios + facts sheet
make backtest     # walk-forward accuracy report (~20s)
make dashboard    # launch the web dashboard at http://localhost:8501
```

Then open the project in Claude Code and run `/forecast`.

## Accuracy (seed 42)

Walk-forward backtest over 33 cutoffs; WAPE of projected closing cash vs actual:

| Horizon | Engine | Naive baseline | Target |
|---|---|---|---|
| Weeks 1–4 | 4.5% | 8.8% | ≤10% |
| Weeks 5–13 | 6.0% | 20.2% | ≤20% |

See [docs/methodology.md](docs/methodology.md) for methods and metric definitions.

## Outputs

Every run writes to `outputs/runs/<run_id>/`:

| Output | For |
|---|---|
| `cash_forecast_<date>.xlsx` | Finance users. Six tabs (Summary, 13-Week Forecast, Daily, Variance, Scenarios, Assumptions). Engine figures in blue; totals and the cash roll-forward are live formulas |
| `memo.md` | The CFO memo Claude writes from `facts.md` |
| `facts.md` | Pre-formatted figures the memo must cite |
| JSON / CSV / Parquet | Summary, weekly view, every source line, assumptions, variance, scenarios, validation |

**Dashboard** (`make dashboard`): Home, Forecast (with drill-down to source lines), Variance
bridge, Scenarios (with live what-if sliders), Receipts & AR, Liquidity & Risk, Backtest,
and Run History.

## The Claude Code layer

| Piece | What it does |
|---|---|
| `CLAUDE.md` | Project rules: Python does the math; never state an untraceable figure |
| Skills (`.claude/skills/`) | `cash-forecasting`, `saas-receipts`, `variance-analysis`, `treasury-risk`, `cfo-narrative` |
| Subagents (`.claude/agents/`) | `data-validator` (read-only pre-run checks), `forecast-reviewer` (independent review → `review.md`) |
| Hook (`.claude/hooks/check_numbers.py`) | Blocks any `memo.md` containing a figure not found in the run's artifacts |

## Slash commands

| Command | Purpose |
|---|---|
| `/generate-data` | Build or refresh the synthetic dataset |
| `/forecast` | Full weekly cycle: validate → engine → variance → scenarios → independent review → memo |
| `/variance` | Forecast vs actuals, split into timing and permanent |
| `/scenario <what-if>` | Named scenario, or a plain-English what-if translated into shocks |
| `/backtest` | Walk-forward accuracy report |
| `/cash-memo` | CFO narrative from the latest run |
| `/validate` | Data tie-outs and numeric fidelity check |
| `/dashboard` | Launch the Streamlit dashboard |

## Roadmap

- [x] Phase 0: Scaffold, config, CI
- [x] Phase 1: Synthetic data generator (`v0.1-data`)
- [x] Phase 2–3: Forecast engine and backtest (`v0.1`)
- [x] Phase 4–5: Claude Code layer: skills, commands, subagents, hooks (`v0.2`)
- [x] Phase 6: Excel workbook, CFO memo, Streamlit dashboard (`v0.3`)
- [ ] Phase 7–8: Evals and hardening (`v1.0`)

## License

MIT © 2026 Kamil Kolacek
