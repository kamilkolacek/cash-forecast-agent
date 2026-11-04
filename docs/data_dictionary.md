# Data dictionary

The engine reads a **generic, source-agnostic format**: Parquet tables in `data/raw/`.
The synthetic generator produces it today. A future ERP adapter (NetSuite, Workday, etc.)
only needs to emit the same tables and columns. Required columns are enforced in
`src/cashforecast/data/schemas.py`.

All amounts carry both local currency and USD where the source is multi-currency.
USD is the reporting currency. Dates are calendar dates (no time component).

## Time model

| Term | Meaning |
|---|---|
| `as_of` | Forecast date (default 2026-11-01). History contains only facts known before it. |
| History | 2024-11-01 to the day before `as_of`. Lives in `data/raw/`. |
| Holdout | `as_of` + 13 weeks of simulated "future actuals". Lives in `data/raw/holdout/` and is never read by the forecaster; it is used to score forecasts and test `/variance`. |

## Tables in `data/raw/`

| Table | Grain | What it holds |
|---|---|---|
| `customers` | customer | Archetype (enterprise / mid_market / smb), whale flag, entity, currency, terms, normal payment lateness, card payer flag |
| `contracts` | contract term | Annual terms with ARR, billing frequency, renewal flag, bookings (new + expansion). `churned_at_end` is blank for terms that end after `as_of` |
| `pipeline` | opportunity | Open deals at `as_of`: stage 1–5, probability, ARR, expected close. Outcomes are holdout-only |
| `invoices` | invoice | AR subledger with status as of `as_of` (paid / open / written_off), amount paid to date, open balance, dispute flag |
| `receipts` | cash receipt | Customer payments; partial payments create multiple rows per invoice |
| `vendors` | vendor | Category, entity, terms, critical flag (hosting, rent) |
| `ap_bills` | bill | AP subledger with status as of `as_of` |
| `ap_payments` | payment | Vendor payments on Tue/Fri runs |
| `payroll` | entity × pay date × component | Net pay and taxes/benefits (remitted next business day); `run_type` regular or bonus |
| `commissions` | month | 10% of prior month's bookings, paid on the 15th |
| `debt_schedule` | date × facility × component | Contractual term-loan interest and amortization, revolver undrawn fee (full schedule incl. future) |
| `capex_plan` | project | Planned date and amount; `actual_date` only for projects already paid |
| `tax_calendar` | filing | US estimated income tax and UK VAT due dates and amounts; `paid` flag |
| `fx_rates` | day | USD per GBP and per CAD |
| `bank_transactions` | transaction | Consolidated USD bank ledger; every row traces to a subledger row via `source_type` + `source_id` |
| `bank_balances` | day | Opening, net flow, closing consolidated cash |
| `arr_monthly` | month | Active ARR at the start of each month |

Also written: `manifest.json` (seed, summary metrics, injected anomalies) and
`validation.json` (tie-out and data-quality results).

## Bank categories

`customer_collections`, `interest_income`, `payroll_net`, `payroll_taxes_benefits`,
`commissions`, `cloud_hosting`, `software_vendors`, `marketing_programs`, `rent_facilities`,
`other_ap`, `bank_fees`, `debt_principal`, `debt_interest`, `income_taxes`, `vat_sales_tax`,
`capex`.

## Validation

| Severity | Check | Meaning |
|---|---|---|
| ERROR | `schema:*` | Required columns present, keys unique |
| ERROR | `tie:*` | Receipts, AP, payroll and commissions tie to the bank; daily bank roll-forward balances; every subledger cash item is in the bank |
| ERROR | `ar:*` | Open balance = amount − paid; no overpayments; no receipt before its invoice |
| WARNING | `dq:duplicate_ap_payment` | A bill paid more than once |
| WARNING | `dq:stale_undisputed_ar` | Undisputed invoices more than 60 days past due |
| WARNING | `dq:payment_behavior_break` | Open invoice past due well beyond the customer's own normal lateness |
| INFO | `dq:overdue_concentration` | Share of overdue AR held by the top 5 customers |

A forecast must not run if any ERROR check fails.

## Injected anomalies

Configured in `config/company.yaml` under `anomalies`, logged in `manifest.json`:

| Anomaly | What happens | Caught by |
|---|---|---|
| `whale_late_payment` | Top whale's recent invoice slips ~75 days past due, collected after `as_of` | `dq:payment_behavior_break`, `dq:stale_undisputed_ar` |
| `customer_default` | A mid-market customer stops paying recent invoices; never collected | `dq:payment_behavior_break` |
| `duplicate_ap_payment` | A vendor bill paid twice on consecutive runs | `dq:duplicate_ap_payment` |

Generate a clean dataset with `python scripts/generate.py --no-anomalies`.
