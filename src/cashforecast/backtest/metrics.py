"""Forecast-vs-actual comparison at a common grain, and accuracy metrics."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Comparison groups: forecast categories and bank categories roll up to the same buckets.
GROUPS = {
    "customer_receipts": [
        "customer_collections",
        "customer_collections_existing_ar",
        "customer_collections_contracted",
        "customer_collections_renewals",
        "customer_collections_new_bookings",
    ],
    "payroll": ["payroll_net", "payroll_taxes_benefits"],
    "ap_vendors": [
        "cloud_hosting",
        "software_vendors",
        "marketing_programs",
        "rent_facilities",
        "other_ap",
    ],
    "other_disbursements": [
        "commissions",
        "debt_principal",
        "debt_interest",
        "income_taxes",
        "vat_sales_tax",
        "capex",
        "bank_fees",
    ],
    "interest_income": ["interest_income"],
}
CATEGORY_TO_GROUP = {cat: g for g, cats in GROUPS.items() for cat in cats}


def weekly_by_group(lines: pd.DataFrame, start: pd.Timestamp, weeks: int) -> pd.DataFrame:
    """Group x week matrix (index group, columns 1..weeks) plus derived totals."""
    end = start + pd.Timedelta(weeks=weeks)
    x = lines[(lines["date"] >= start) & (lines["date"] < end)].copy()
    x["group"] = x["category"].map(CATEGORY_TO_GROUP).fillna("unmapped")
    x["week"] = (x["date"] - start).dt.days // 7 + 1
    m = x.pivot_table(
        index="group", columns="week", values="amount_usd", aggfunc="sum", fill_value=0.0
    )
    m = m.reindex(index=list(GROUPS), columns=range(1, weeks + 1), fill_value=0.0).fillna(0.0)
    m.loc["total_receipts"] = m.loc[["customer_receipts", "interest_income"]].sum()
    m.loc["total_disbursements"] = m.loc[["payroll", "ap_vendors", "other_disbursements"]].sum()
    m.loc["net_flow"] = m.loc["total_receipts"] + m.loc["total_disbursements"]
    return m


def naive_baseline(
    bank: pd.DataFrame, cutoff: pd.Timestamp, weeks: int, lookback_weeks: int = 13
) -> pd.DataFrame:
    """Benchmark: each group's average weekly flow over the prior 13 weeks, held flat."""
    start = cutoff - pd.Timedelta(weeks=lookback_weeks)
    hist = weekly_by_group(bank, start, lookback_weeks)
    avg = hist.mean(axis=1)
    return pd.DataFrame({w: avg for w in range(1, weeks + 1)})


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    denom = np.abs(actual).sum()
    return float(np.abs(actual - forecast).sum() / denom) if denom else float("nan")
