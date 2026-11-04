# Cash Forecast Agent

A Claude Code agent that runs a **13-week direct-method cash forecast** for a B2B SaaS
company end to end: it validates the data, forecasts receipts and disbursements, explains
last week's variance, runs scenarios, gets an independent review, and writes a CFO memo in
which every figure is mechanically checked against the forecast output. All data is synthetic.

**See it first:** a sample [CFO memo](docs/examples/sample_run/memo.md), the
[facts sheet](docs/examples/sample_run/facts.md) it was written from, and the
[Excel workbook](docs/examples/sample_run/cash_forecast_2026-11-29.xlsx).

## Why it's built this way

Cash forecasts fail in two ways that matter to a CFO: the numbers are wrong, or the story
about them is. This project addresses both.

- **Python does every calculation.** A deterministic engine forecasts each cash flow from
  its source (an invoice, a contract, a payroll calendar, a debt schedule) and rolls cash
  forward day by day. Every line keeps a pointer to its source.
- **Claude orchestrates and explains.** It runs the cycle, interprets variances, turns
  plain-English what-ifs into scenario inputs, and writes the memo.
- **Claude can't invent a number.** A Claude Code hook checks every `$` and `%` in the
  memo against the run's output and blocks the write if anything doesn't match. During
  development it caught a wrong churn figure (5.8% written, 7.0% actual) in a draft memo.

## Accuracy

Walk-forward backtest: 33 past forecasts, one every two weeks, each scored against what
actually happened. Error is WAPE of projected closing cash.

| Horizon | Engine | Naive baseline | Target |
|---|---|---|---|
| Weeks 1–4 | 4.5% | 8.8% | ≤10% |
| Weeks 5–13 | 6.0% | 20.2% | ≤20% |

Cumulative customer receipts land within 6.6% by weeks 5–13. Weekly receipts are noisier
(about 36%) because a handful of large annual invoices dominate individual weeks; see
[methodology](docs/methodology.md).

## Quickstart

```bash
git clone https://github.com/kamilkolacek/cash-forecast-agent.git
cd cash-forecast-agent
make setup     # virtual env, dependencies, pre-commit
make demo      # data → this week's run → a run 4 weeks later → backtest → dashboard
```

The dashboard opens at http://localhost:8501. Then open the project in
[Claude Code](https://docs.claude.com/en/docs/claude-code/overview) and run `/forecast`.

| Command | What it does |
|---|---|
| `make data` | Generate the synthetic dataset (~30s) |
| `make weekly` | Deterministic weekly cycle: forecast, variance, scenarios, facts sheet, workbook |
| `make backtest` | Walk-forward accuracy report (~20s) |
| `make dashboard` | Launch the dashboard |
| `make test` | 55 tests |
| `make eval` | Agent evals (needs `ANTHROPIC_API_KEY`) |

## The company: Northwind Cloud, Inc. (fictional)

| | |
|---|---|
| ARR | $254M at the forecast date, entities in the US, UK and Canada |
| Customers | 962 active; enterprise, mid-market and SMB, each with its own payment behavior |
| Concentration | 5 "whale" customers, ~15% of ARR, billed annually, slow payers |
| Billing mix (by ARR) | 64% annual, 27% quarterly, 10% monthly |
| History | 24 months, plus 13 held-back weeks of "future" actuals for scoring |
| Planted problems | A whale paying 75 days late, a customer default, a duplicate vendor payment |

## Slash commands (Claude Code)

| Command | Purpose |
|---|---|
| `/forecast` | Full weekly cycle: validate → engine → variance → scenarios → independent review → memo |
| `/variance` | Forecast vs actuals, split into **timing** (late but still coming) and **permanent** (not coming) |
| `/scenario <what-if>` | A named scenario, or a plain-English question, e.g. "what if we pay $30M for an acquisition in December?" |
| `/cash-memo` | Write or rewrite the CFO memo for the latest run |
| `/validate` | Data tie-outs and data-quality findings, as treasury action items |
| `/backtest` | Accuracy report |
| `/generate-data` | Build or refresh the synthetic dataset |
| `/dashboard` | Launch the dashboard |

## What's inside

| Piece | Where | What it does |
|---|---|---|
| Rules | `CLAUDE.md` | Python does the math; never state an untraceable figure; never forecast on failed data |
| Skills | `.claude/skills/` | `cash-forecasting`, `saas-receipts`, `variance-analysis`, `treasury-risk`, `cfo-narrative` |
| Subagents | `.claude/agents/` | `data-validator` (read-only checks), `forecast-reviewer` (independent review → `review.md`) |
| Hook | `.claude/hooks/check_numbers.py` | Blocks any `memo.md` with a figure not found in the run |
| Engine | `src/cashforecast/` | Synthetic data, validation, forecast, variance, scenarios, backtest, outputs |
| Dashboard | `app/` | 8 pages, including drill-down to source lines and live what-if sliders |
| Evals | `tests/evals/` | Headless Claude Code runs, graded deterministically |

## Outputs (per run, in `outputs/runs/<run_id>/`)

| Output | For |
|---|---|
| `memo.md` | The CFO memo |
| `cash_forecast_<date>.xlsx` | Finance users: Summary, 13-Week Forecast, Daily, Variance, Scenarios, Assumptions. Engine figures in blue; totals and the cash roll-forward are live formulas |
| `facts.md` | Pre-formatted figures the memo cites |
| `review.md` | The independent reviewer's findings and verdict |
| `audit.json` | Code commit, config and data fingerprints, timings, artifact hashes |
| JSON / CSV / Parquet | Summary, weekly view, every source line, assumptions, variance, scenarios, validation |

## Agent evals

Five cases run Claude Code headless in a throwaway copy of the repo and grade the result
with deterministic checks:

| Case | Passes when |
|---|---|
| Full forecast cycle | Memo exists, follows the template, every figure traces, names the right variance drivers with the right classification, reviewer gives a verdict |
| Plain-English what-if | The question becomes the right shock ($30M one-off), is saved, and is reported against the floor and revolver |
| Validation | The planted duplicate payment and payment-pattern breaks are raised as action items |
| Bad data | With receipts that no longer tie to the bank, no memo is written and the data is left alone |
| No invented numbers | Asked about a date beyond the horizon, the agent says so instead of extrapolating |

The graders themselves are unit-tested in normal CI. The live evals run nightly or on demand
(GitHub Actions → "Agent evals"), so pull requests never spend API credits.

## Docs

- [Architecture](docs/architecture.md): components, data flow, design decisions
- [Methodology](docs/methodology.md): forecasting methods, variance split, scenarios, accuracy
- [Data dictionary](docs/data_dictionary.md): every table and validation check
- [Runbook](docs/runbook.md): how treasury would run this every week

## License

MIT © 2026 Kamil Kolacek
