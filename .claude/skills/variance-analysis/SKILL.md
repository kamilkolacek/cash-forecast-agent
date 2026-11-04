---
name: variance-analysis
description: How to read and explain the forecast-vs-actual variance bridge, including the timing vs permanent split. Use for /variance, the variance section of the weekly memo, or any question about why actual cash differed from forecast.
---

# Variance analysis

## The method

For a forecast made at P, with actuals through C, and X = the end of the current
13-week horizon (the comparison end):

- **Variance** = actual(P..C) − forecast(P..C). Positive is favorable to cash.
- **Permanent** = [actual(P..C) + current forecast(C..X)] − prior forecast(P..X).
  Cash that is no longer expected by X: lost, written off, or a changed amount.
- **Timing** = variance − permanent. Cash that is late but still expected by X.

The prior forecast is extended to X so both sides cover the same window. Using the
rolling horizon end means a payment that slips a few days past the old horizon edge is
still timing, which is what a CFO means by timing.

The split comes from re-running the engine at C, not from judgment. Drivers are
customers (for receipts) or categories (for everything else). By construction,
timing + permanent = variance for each driver, and drivers sum to the closing-cash
difference.

## Reading `variance.json`

- `summary`: forecast vs actual closing cash, total variance, timing, permanent, and the
  prior vs revised forecast cash at the comparison end (their difference is the
  permanent total).
- `top_drivers`: sorted by absolute variance. `forecast_basis` shows the rule that
  produced the forecast (from line notes), which usually explains the miss.
- `by_category`: window variance by bank category.

## Explaining a driver

For each of the top 3–5 drivers, state:
1. Who or what (customer ID and archetype, flag if whale; or category).
2. Forecast vs actual, and the variance, as written in `facts.md`.
3. Timing or permanent, and what that means ("expected in December" vs "will not recover").
4. The cause, from `forecast_basis` and validation findings. A permanent favorable
   variance on a customer marked "behavior break: 50% weighted" means they paid in full
   after we haircut them. A permanent unfavorable variance on payroll means run-rate
   growth, not timing.
5. The action, if any: chase a collection, update an assumption, nothing.

## Pitfalls

- Don't call a variance permanent because it is large; use the computed split.
- Don't net favorable and unfavorable drivers into a single story unless they share a cause.
- A one-week window is noisy. Say so if the variance is under ~1% of cash.
