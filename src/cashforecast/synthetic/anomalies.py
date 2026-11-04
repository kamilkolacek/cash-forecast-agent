"""Inject known anomalies into history so validation and the agent can be tested against them."""

from __future__ import annotations

from typing import Any

import pandas as pd

from cashforecast.synthetic._util import SimContext, bday


def whale_late_payment(ctx: SimContext, d: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Top whale's most recent invoice slips well past due and stays open at as_of."""
    cust, inv, rcp = d["customers"], d["invoices"], d["receipts"]
    whales = cust[cust["is_whale"]].sort_values("arr", ascending=False)["customer_id"]
    window = (inv["due_date"] >= ctx.as_of - pd.Timedelta(days=90)) & (inv["due_date"] < ctx.as_of)
    for wid in whales:
        cand = inv[window & (inv["customer_id"] == wid)]
        if len(cand):
            target = cand.sort_values("amount_usd_at_issue").iloc[-1]
            new_date = bday(
                max(target["due_date"] + pd.Timedelta(days=75), ctx.as_of + pd.Timedelta(days=21))
            )
            m = rcp["invoice_id"] == target["invoice_id"]
            rcp.loc[m, "receipt_date"] = new_date
            return dict(
                type="whale_late_payment",
                customer_id=wid,
                invoice_id=target["invoice_id"],
                amount_usd=float(target["amount_usd_at_issue"]),
                due_date=str(target["due_date"].date()),
                collected_date=str(new_date.date()),
            )
    return dict(type="whale_late_payment", skipped="no whale invoice due in window")


def customer_default(ctx: SimContext, d: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """A mid-market customer stops paying: recent invoices never collect."""
    cust, inv, rcp = d["customers"], d["invoices"], d["receipts"]
    recent = inv[
        (inv["issue_date"] >= ctx.as_of - pd.Timedelta(days=150)) & (inv["issue_date"] < ctx.as_of)
    ]
    # Unpaid run must have started at least 40 days before as_of to look like a default.
    old_enough = recent[recent["due_date"] <= ctx.as_of - pd.Timedelta(days=40)]["customer_id"]
    pool = cust[
        (cust["archetype"] == "mid_market")
        & ~cust["pays_by_card"]
        & cust["customer_id"].isin(old_enough)
    ]
    pick = pool.sort_values("arr").iloc[-1]["customer_id"]
    ids = recent.loc[recent["customer_id"] == pick, "invoice_id"]
    d["receipts"] = rcp[~rcp["invoice_id"].isin(ids)].reset_index(drop=True)
    inv.loc[inv["invoice_id"].isin(ids), "written_off_date"] = pd.NaT
    return dict(
        type="customer_default",
        customer_id=pick,
        invoice_ids=list(ids),
        amount_usd=float(inv.loc[inv["invoice_id"].isin(ids), "amount_usd_at_issue"].sum()),
    )


def duplicate_ap_payment(ctx: SimContext, d: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """A vendor bill is paid twice on consecutive payment runs."""
    pay = d["ap_payments"]
    window = (
        (pay["payment_date"] >= ctx.as_of - pd.Timedelta(days=45))
        & (pay["payment_date"] < ctx.as_of - pd.Timedelta(days=7))
        & (pay["amount_usd"] > 50_000)
    )
    orig = pay[window].sample(n=1, random_state=ctx.rng).iloc[0]
    dup = orig.copy()
    dup["payment_id"] = orig["payment_id"] + "-DUP"
    dup["payment_date"] = orig["payment_date"] + pd.Timedelta(
        days=3 if orig["payment_date"].weekday() == 1 else 4
    )
    d["ap_payments"] = pd.concat([pay, dup.to_frame().T], ignore_index=True).astype(pay.dtypes)
    return dict(
        type="duplicate_ap_payment",
        bill_id=orig["bill_id"],
        payment_ids=[orig["payment_id"], dup["payment_id"]],
        amount_usd=float(orig["amount_usd"]),
        dates=[str(orig["payment_date"].date()), str(dup["payment_date"].date())],
    )


INJECTORS = {
    "whale_late_payment": whale_late_payment,
    "customer_default": customer_default,
    "duplicate_ap_payment": duplicate_ap_payment,
}


def inject(ctx: SimContext, d: dict[str, pd.DataFrame], names: list[str]) -> list[dict[str, Any]]:
    return [INJECTORS[n](ctx, d) for n in names]
