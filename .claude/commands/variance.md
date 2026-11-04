---
description: Explain forecast vs actual cash with a timing / permanent split
argument-hint: "[--weeks-elapsed N]"
---

Use the `variance-analysis` and `saas-receipts` skills.

1. Run `python scripts/run_variance.py $ARGUMENTS`. With no argument it compares last
   week's forecast to last week's actuals. With `--weeks-elapsed N` it compares the live
   forecast to N weeks of holdout actuals.
2. Read `variance.json` in the directory printed on the last line.
3. Explain, in under 250 words:
   - Forecast vs actual closing cash and the total variance, split timing / permanent.
   - The top 3–5 drivers: who, how much, timing or permanent, why (use `forecast_basis`),
     and any action.
   - What the permanent portion does to cash at the comparison end
     (`prior_forecast_cash_at_comparison_end_usd` vs `revised_cash_at_comparison_end_usd`).
4. Quote figures as printed or as stored in `variance.json`. Do not compute new ones.
