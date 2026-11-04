---
name: saas-receipts
description: How SaaS customer collections behave and how the engine forecasts them (billing mix, renewals, whales, payment behavior, pipeline). Use when explaining receipts, collection risk, or a customer-level variance.
---

# SaaS receipts

## Why SaaS cash is lumpy

- **Billing mix** drives timing more than revenue does. Annual upfront billing (about 64%
  of ARR here) means a renewal produces a whole year of cash in one invoice.
- **Q4 bookings concentration** creates large December renewals and a January
  collections peak.
- **Whales** (5 customers, ~15% of ARR, annual billing, slow portal payers) make
  individual weeks swing by several million dollars. Weekly receipts error is high for
  this reason even when 13-week totals are accurate.

## How each stream is forecast

| Stream | Category | Key assumption to cite |
|---|---|---|
| Open invoices | `customer_collections_existing_ar` | Customer's expected days late (credibility-weighted) |
| Current-term installments | `customer_collections_contracted` | Billing schedule + lateness |
| Renewals | `customer_collections_renewals` | Churn and expansion by archetype; renewal billing delay |
| Pipeline | `customer_collections_new_bookings` | Stage probability |

## Late and disputed invoices

| `note` on the line | Meaning | Treatment |
|---|---|---|
| on pattern | Not yet past the customer's normal payment date | 100%, spread around expected date |
| modestly late | Past normal date, within 2 sd + 7 days | 100% about a week out |
| behavior break: 50% weighted | Far outside the customer's own pattern | 50% at cutoff + 30 days |
| disputed | Invoice in dispute | 80% at cutoff + 45 days |

A behavior break is the strongest early signal of a default or a dispute that hasn't been
logged. Name the customer and amount from `facts.md` or `variance.json`, and recommend a
collections call.

## Talking about it

- Say "timing" when cash is late but still expected inside the horizon, "permanent" when
  it is not expected (see `variance-analysis`).
- Distinguish ARR from cash: renewing ARR becomes cash only after billing delay, payment
  terms and lateness.
