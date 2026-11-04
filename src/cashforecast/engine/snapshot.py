"""Rebuild 'what was known' at any cutoff date from the full history.

The live forecast uses cutoff = as_of. The backtest uses earlier cutoffs. Both go through
this one function, so the engine never sees information dated on or after its cutoff.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cashforecast.synthetic._util import bday

STAGE_PROBABILITY = {1: 0.10, 2: 0.20, 3: 0.40, 4: 0.60, 5: 0.80}


@dataclass
class Snapshot:
    cutoff: pd.Timestamp
    tables: dict[str, pd.DataFrame]
    opening_cash: float
    pipeline_reconstructed: bool

    def __getitem__(self, name: str) -> pd.DataFrame:
        return self.tables[name]


def take_snapshot(
    d: dict[str, pd.DataFrame], cutoff: pd.Timestamp, data_as_of: pd.Timestamp
) -> Snapshot:
    c = pd.Timestamp(cutoff)
    t: dict[str, pd.DataFrame] = {}

    for name, col in [
        ("receipts", "receipt_date"),
        ("ap_payments", "payment_date"),
        ("payroll", "pay_date"),
        ("commissions", "pay_date"),
        ("bank_transactions", "date"),
        ("fx_rates", "date"),
    ]:
        t[name] = d[name][d[name][col] < c]

    t["customers"] = d["customers"][d["customers"]["first_start"] < c]

    k = d["contracts"][d["contracts"]["term_start"] < c].copy()
    k["churned_at_end"] = k["churned_at_end"].where(k["term_end"] < c)
    t["contracts"] = k

    inv = d["invoices"][d["invoices"]["issue_date"] < c].copy()
    paid = t["receipts"].groupby("invoice_id")["amount_local"].sum()
    inv["paid_local_to_date"] = inv["invoice_id"].map(paid).fillna(0.0)
    inv["open_amount_local"] = (inv["amount_local"] - inv["paid_local_to_date"]).round(2)
    wo = inv["written_off_date"] < c
    inv["status"] = np.where(
        wo, "written_off", np.where(inv["open_amount_local"] <= 0.005, "paid", "open")
    )
    t["invoices"] = inv

    bills = d["ap_bills"][d["ap_bills"]["issue_date"] < c].copy()
    paid_b = t["ap_payments"].groupby("bill_id")["amount_local"].sum()
    bills["paid_local_to_date"] = bills["bill_id"].map(paid_b).fillna(0.0)
    bills["status"] = np.where(
        bills["paid_local_to_date"] >= bills["amount_local"] - 0.005, "paid", "open"
    )
    t["ap_bills"] = bills

    cx = d["capex_plan"].copy()
    cx["actual_date"] = cx["actual_date"].where(cx["actual_date"] < c)
    t["capex_plan"] = cx

    tax = d["tax_calendar"].copy()
    tax["paid"] = tax["due_date"] < c
    t["tax_calendar"] = tax

    for name in ("vendors", "debt_schedule", "arr_monthly"):
        t[name] = d[name]
    t["arr_monthly"] = d["arr_monthly"][d["arr_monthly"]["month"] < c]

    reconstructed = c != data_as_of
    t["pipeline"] = _reconstruct_pipeline(d, c) if reconstructed else d["pipeline"]

    bal = d["bank_balances"]
    prior = bal[bal["date"] < c]
    opening = (
        float(prior["closing_balance_usd"].iloc[-1])
        if len(prior)
        else float(bal["opening_balance_usd"].iloc[0])
    )
    return Snapshot(c, t, opening, reconstructed)


def _reconstruct_pipeline(
    d: dict[str, pd.DataFrame], c: pd.Timestamp, window_days: int = 120
) -> pd.DataFrame:
    """Historical pipeline snapshots don't exist, so rebuild one for a past cutoff.

    New-logo first terms starting in the next 120 days become open opportunities, with
    stage set by time to close. This mirrors how the generator builds the live pipeline
    and is disclosed in backtest results as a known limitation (it omits lost deals and
    close-date noise, so it slightly flatters new-bookings accuracy).
    """
    k = d["contracts"]
    hist_start = d["bank_balances"]["date"].min()
    first = k[
        (k["term_no"] == 1)
        & (k["term_start"] >= max(c, hist_start))
        & (k["term_start"] <= c + pd.Timedelta(days=window_days))
    ]
    first = first.merge(d["customers"][["customer_id", "archetype", "entity"]], on="customer_id")
    days = (first["term_start"] - c).dt.days
    stage = np.select([days <= 30, days <= 60, days <= 90], [5, 4, 3], default=2)
    return pd.DataFrame(
        {
            "opportunity_id": [f"R{i:05d}" for i in range(len(first))],
            "customer_id": first["customer_id"].values,
            "archetype": first["archetype"].values,
            "entity": first["entity"].values,
            "arr_usd": first["arr_usd"].values,
            "billing_freq": first["billing_freq"].values,
            "stage": stage,
            "probability": [STAGE_PROBABILITY[s] for s in stage],
            "expected_close": first["term_start"].values,
        }
    )


def spot_fx(snap: Snapshot) -> dict[str, float]:
    last = snap["fx_rates"].iloc[-1]
    return {ccy: float(last[ccy]) for ccy in ("USD", "GBP", "CAD")}


def horizon_dates(snap: Snapshot, weeks: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """First and last day of the forecast horizon (inclusive)."""
    return snap.cutoff, snap.cutoff + pd.Timedelta(weeks=weeks) - pd.Timedelta(days=1)


def roll(d: pd.Timestamp, floor: pd.Timestamp) -> pd.Timestamp:
    """Business-day roll, never earlier than floor."""
    return bday(max(d, floor))
