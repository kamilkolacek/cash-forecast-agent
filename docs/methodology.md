# Forecast methodology

A 13-week **direct-method** cash forecast: every receipt and disbursement is forecast
explicitly and rolled forward from the opening bank balance. The engine works at daily
grain for all 91 days, then presents weeks 1–13 weekly and weeks 1–2 daily.

Every forecast line carries a `source_type`, `source_id` and `note`, so any number
traces back to an invoice, contract, opportunity, bill, schedule row or learned rate.
Learned parameters are written to `assumptions.json` with each run.

## No look-ahead

`engine/snapshot.py` rebuilds what was known at the cutoff: invoices issued before it,
receipts and payments before it, churn known only for terms that ended before it, capex
actuals before it. The live forecast and the backtest use the same function.

## Receipts

| Stream | Source | Timing | Amount |
|---|---|---|---|
| Existing AR | Open invoices | Due date + customer's expected lateness | Open balance at spot FX |
| Contracted | Unbilled installments of current terms | Billing date + terms + lateness | ARR ÷ installments |
| Renewals | Terms ending in the horizon | Term end + learned billing delay + terms + lateness | ARR × (1 − churn) × (1 + expansion), by archetype |
| New bookings | Open pipeline | Expected close + archetype terms + lateness | ARR ÷ installments × stage probability |

**Customer lateness** is each customer's mean days paid after due date, blended with
their archetype's mean by credibility weighting (`n / (n + 5)` on the customer's own history).

**Timing spread.** Each expected payment is split across five equally likely dates
(normal quintile midpoints at ±1.28 and ±0.52 standard deviations of that customer's
lateness). This improved weekly receipts accuracy from 50% to 36% WAPE in the backtest
without changing totals.

**Open AR rules** for invoices already past their expected date:

| Situation | Treatment |
|---|---|
| Within 2 sd + 7 days of normal | 100% collected about one week out |
| Beyond that (behavior break) | 50% collected at cutoff + 30 days |
| Disputed | 80% collected at cutoff + 45 days |

## Disbursements

| Category | Method |
|---|---|
| Payroll | Each entity's calendar (biweekly continues the actual Friday cadence). Amount = average of the last 3 regular runs. Taxes remitted next business day, including for a pre-cutoff payroll. Prior-year bonus if the bonus month is in the horizon |
| Commissions | 10% of prior month's bookings, paid on the 15th. Future bookings = known + expected renewal expansion + weighted pipeline |
| AP: open bills | First Tue/Fri payment run on or after due date |
| AP: future bills | Last-3-month run rate × same-month-last-year seasonality (clipped 0.5–3.0), issued daily, paid by each category's terms mix |
| Debt | Contractual schedule |
| Taxes | Tax calendar |
| Capex | Planned date + average historical slippage |
| Bank fees | 90-day average per business day |
| Interest income | Rate × prior month's average balance (actual + projected), posted the next business day |

## Risk flags

Any week whose minimum daily balance falls below the internal floor
(`min_cash_threshold`) or the covenant (`min_liquidity`) is flagged in `summary.json`.

## Accuracy

`scripts/run_backtest.py` forecasts from 33 past cutoffs (every two weeks) and scores
each against what actually happened. It also scores the live forecast against the
13-week holdout. The benchmark is a naive forecast: each group's trailing 13-week
average, held flat.

**Formal targets** are on projected closing cash (WAPE): ≤10% for weeks 1–4,
≤20% for weeks 5–13. Treasury judges a 13-week forecast on its cash position; a
receipt landing one week late does not change it by month-end.

**Weekly** WAPE by category is reported for diagnosis. Customer receipts are inherently
lumpy at weekly grain (a handful of whale invoices of $3–8M), so weekly receipts error
is high even when **cumulative** receipts are accurate.

**Known limitation:** there are no historical pipeline snapshots, so past cutoffs use a
pipeline reconstructed from new logos that actually closed. This omits lost deals and
slightly flatters new-bookings accuracy in the backtest (not in the live forecast).
