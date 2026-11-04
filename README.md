# Cash Forecast Agent

A Claude Code agent that produces a **13-week direct-method cash forecast** for a
fictional B2B SaaS company, with variance analysis, scenarios, liquidity risk flags,
a CFO memo, and a Streamlit dashboard. All data is synthetic.

> **Status:** Phase 0 (scaffold). See the roadmap below.

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
make data         # generate synthetic data (Phase 1)
make dashboard    # launch the web UI (Phase 6)
```

Then open the project in Claude Code and run `/forecast`.

## Slash commands

| Command | Purpose |
|---|---|
| `/generate-data` | Build or refresh the synthetic dataset |
| `/forecast` | Full weekly run: validate, forecast, variance, scenarios, risk, memo |
| `/variance` | Forecast vs actuals bridge |
| `/scenario <name>` | Run a named or custom scenario |
| `/backtest` | Walk-forward accuracy report |
| `/cash-memo` | CFO narrative from the latest run |
| `/validate` | Data tie-outs and numeric fidelity check |
| `/dashboard` | Launch the Streamlit dashboard |

## Roadmap

- [x] Phase 0: Scaffold, config, CI
- [ ] Phase 1: Synthetic data generator (`v0.1-data`)
- [ ] Phase 2–3: Forecast engine and backtest (`v0.1`)
- [ ] Phase 4–5: Claude Code layer: skills, commands, subagents, hooks (`v0.2`)
- [ ] Phase 6: Excel workbook, CFO memo, Streamlit dashboard (`v0.3`)
- [ ] Phase 7–8: Evals and hardening (`v1.0`)

## License

MIT © 2026 Kamil Kolacek
