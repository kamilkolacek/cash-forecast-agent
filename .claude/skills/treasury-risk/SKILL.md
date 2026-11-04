---
name: treasury-risk
description: Liquidity risk framing for the cash forecast - internal floor, covenant, revolver, scenarios and recommended actions. Use when assessing flags, running /scenario, or writing the risk section of the memo.
---

# Treasury risk

## Thresholds (`config/forecast.yaml`, `config/company.yaml`)

| Threshold | Meaning | If breached |
|---|---|---|
| Internal floor (`min_cash_threshold`) | Management's operating cushion | Plan action: delay discretionary spend, accelerate collections, or draw the revolver |
| Covenant (`min_liquidity`) | Lender requirement | Must not happen: escalate to the CFO immediately, draw revolver before the breach date |

Flags are per week, on the **minimum daily** balance, not the week-end balance.

## Headroom and liquidity (`scenarios.json`, per scenario)

- `floor_headroom_usd`, `covenant_headroom_usd`: minimum cash minus the threshold.
- `revolver_available_usd`: undrawn revolver.
- `total_liquidity_at_low_point_usd`: minimum cash plus undrawn revolver.
- `suggested_revolver_draw_usd`: draw needed to stay at the floor, rounded up to $1M.

## Scenarios

| Scenario | Tests |
|---|---|
| base | Current assumptions |
| downside | 10% of renewal cash 45 days late + top whale 60 days late |
| severe_downside | All whales 60 days late, 15% renewal churn, collections 10 days slower |
| churn_shock | 15% of renewal cash lost |
| upside | Top 5 deals close 30 days early at 100%, collections 5 days faster |
| hiring_freeze | Payroll −3% from week 3 |

Custom scenarios: `python scripts/run_scenario.py --custom NAME '<shocks JSON>'`. Shock
types are documented at the top of `config/scenarios.yaml`. Translate a CFO's question
("what if we close the acquisition in December?") into shocks, run it, and report.

## Writing the risk view

1. Lead with the worst plausible case that still matters: the lowest minimum cash among
   downside scenarios and its headroom to the floor and the covenant.
2. Name the trigger: which shock drives it.
3. Recommend actions only where headroom is thin or negative, sized from
   `suggested_revolver_draw_usd`.
4. If nothing is close, say so plainly. "No action needed" is a valid conclusion.
