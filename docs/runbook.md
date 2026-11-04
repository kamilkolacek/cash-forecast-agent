# Weekly runbook

How treasury would operate this forecast each week. Times assume a Monday cycle.

## Monday morning: run the cycle

In Claude Code, from the project root:

```
/forecast
```

This validates the data, runs the engine, explains last week's variance, runs all
scenarios, has the `forecast-reviewer` subagent review the run, and writes the CFO memo.
Expect 3–6 minutes.

Without Claude: `make weekly` produces everything except the review and memo.

## Check before sending

| Check | Where | Action if it fails |
|---|---|---|
| Validation passed | `/forecast` stops if not | Fix the source data (never edit `data/raw/` by hand), rerun |
| Reviewer verdict | `review.md` last line | Read every HIGH finding; confirm the memo addresses it |
| Memo traces | `python scripts/check_memo.py` | The hook should have caught it; correct from `facts.md` |
| Flags | `summary.json` → `flags`, dashboard Home | Any floor flag goes to the CFO the same day; a covenant flag is escalated immediately |
| Audit | `audit.json` → `uncommitted_code_or_config_changes` | If `true`, the run used unreviewed code or config; rerun from a clean `main` before distributing |

## Distribute

- **CFO:** `memo.md`, and `cash_forecast_<date>.xlsx` for anyone who wants the detail.
- **Dashboard:** `make dashboard` for a live walkthrough; the Run History page has
  downloads.

## During the week

| Question | Do |
|---|---|
| "What if…?" | `/scenario <the question in plain English>` |
| "Why did cash come in below forecast?" | `/variance` |
| "Can we still trust the model?" | `/backtest`, or the dashboard Backtest page |
| A large customer payment is late | Check the Receipts & AR page; the customer will appear under "outside their normal pattern" once the gap is unusual for them |

## Monthly

- Review `config/forecast.yaml` thresholds and `config/scenarios.yaml` with the CFO.
- Run `/backtest`. If closing-cash error exceeds target, investigate the worst
  component before the next cycle.
- Run the agent evals (`make eval`, or the "Agent evals" GitHub workflow) after any
  change to skills, commands, `CLAUDE.md` or the model.

## When something breaks

| Symptom | Likely cause | Fix |
|---|---|---|
| `No dataset at data/raw` | Data not generated | `make data` |
| Validation ERROR on a tie-out | Source extract incomplete | Re-pull the source; do not patch the files |
| Hook blocks the memo repeatedly | Figure not on `facts.md` (often a derived total) | Use a figure from `facts.md`, or add it to the facts sheet generator |
| Dashboard says no runs | No run under `outputs/runs/` | `make weekly` |
