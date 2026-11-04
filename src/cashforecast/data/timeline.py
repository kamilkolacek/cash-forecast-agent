"""Simulate the passage of time by merging the holdout back into history.

The generator keeps 13 weeks of future actuals aside. Merging them lets us ask
"it is now k weeks later: how did last week's forecast do?" with the same engine.
The snapshot at any cutoff still hides everything on or after that cutoff.
"""

from __future__ import annotations

import pandas as pd

APPEND = [
    "receipts",
    "ap_payments",
    "payroll",
    "commissions",
    "bank_transactions",
    "fx_rates",
    "bank_balances",
    "invoices",
    "ap_bills",
]


def combine_with_holdout(
    hist: dict[str, pd.DataFrame], hold: dict[str, pd.DataFrame]
) -> dict[str, pd.DataFrame]:
    d = dict(hist)
    for name in APPEND:
        if name in hold and len(hold[name]):
            d[name] = pd.concat([hist[name], hold[name]], ignore_index=True)
    if "contracts" in hold:  # full contract history, incl. terms that start later
        d["contracts"] = hold["contracts"].drop(columns=["billing_delay_days"], errors="ignore")
    if "customers_future" in hold and len(hold["customers_future"]):
        fut = hold["customers_future"].drop(columns=["origin"], errors="ignore")
        d["customers"] = pd.concat([hist["customers"], fut], ignore_index=True)
    if "capex_actuals" in hold and len(hold["capex_actuals"]):
        cx = hist["capex_plan"].copy()
        actual = hold["capex_actuals"].set_index("project_id")["actual_date"]
        cx["actual_date"] = cx["actual_date"].fillna(cx["project_id"].map(actual))
        d["capex_plan"] = cx
    # Invoice flags the snapshot needs; holdout rows carry them from the generator.
    for col in ("is_disputed", "is_renewal_billing"):
        d["invoices"][col] = d["invoices"][col].fillna(False).astype(bool)
    return d


def data_end(d: dict[str, pd.DataFrame]) -> pd.Timestamp:
    """Last date with actuals: the latest cutoff a forecast can be run from + 1 day."""
    return pd.Timestamp(d["bank_balances"]["date"].max()) + pd.Timedelta(days=1)
