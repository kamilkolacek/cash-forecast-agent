"""AR invoices from contract billing schedules, and the customer receipts that pay them."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashforecast.synthetic._util import SimContext, bday
from cashforecast.synthetic.fx import FxTable

INSTALLMENTS = {"annual": 1, "quarterly": 4, "monthly": 12}


def generate_invoices(
    ctx: SimContext, customers: pd.DataFrame, contracts: pd.DataFrame, fx: FxTable
) -> pd.DataFrame:
    cust = customers.set_index("customer_id")
    rows = []
    for k in contracts.itertuples():
        c = cust.loc[k.customer_id]
        n = INSTALLMENTS[k.billing_freq]
        step = 12 // n
        for i in range(n):
            bill_date = k.term_start + pd.DateOffset(months=i * step)
            if i == 0 and k.billing_delay_days:
                bill_date += pd.Timedelta(days=k.billing_delay_days)
            issue = bday(bill_date)
            if issue < ctx.start or issue > ctx.end:
                continue
            usd = k.arr_usd / n
            rows.append(
                dict(
                    contract_id=k.contract_id,
                    customer_id=k.customer_id,
                    entity=c.entity,
                    currency=c.currency,
                    issue_date=issue,
                    due_date=issue + pd.Timedelta(days=int(c.terms_days)),
                    amount_usd_at_issue=round(usd, 2),
                    amount_local=round(usd / fx.rate(c.currency, issue), 2),
                    billing_freq=k.billing_freq,
                    installment=i + 1,
                    is_renewal_billing=bool(k.is_renewal and i == 0),
                )
            )
    df = pd.DataFrame(rows).sort_values(["issue_date", "customer_id"]).reset_index(drop=True)
    df.insert(0, "invoice_id", [f"INV{i:06d}" for i in range(1, len(df) + 1)])
    return df


def simulate_receipts(
    ctx: SimContext, customers: pd.DataFrame, invoices: pd.DataFrame, fx: FxTable
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (invoices with dispute/write-off flags, receipts)."""
    rng, rev = ctx.rng, ctx.cfg["revenue"]
    cust = customers.set_index("customer_id")
    receipts, disputed, written_off = [], [], []
    for inv in invoices.itertuples():
        c = cust.loc[inv.customer_id]
        u = rng.random()
        is_dispute = False
        if c.pays_by_card:
            pay = inv.issue_date + pd.Timedelta(days=1)
        elif u < rev["bad_debt_rate"]:
            disputed.append(False)
            written_off.append(inv.due_date + pd.Timedelta(days=120))
            continue
        else:
            late = max(0.0, rng.normal(c.mean_days_late, c.sd_days_late))
            if rng.random() < rev["dispute_rate"]:
                is_dispute = True
                late += rng.integers(30, 91)
            pay = inv.due_date + pd.Timedelta(days=int(late))
        disputed.append(is_dispute)
        written_off.append(pd.NaT)
        pay = bday(pay)
        if not c.pays_by_card and rng.random() < rev["partial_payment_rate"]:
            first = round(inv.amount_local / 2, 2)
            parts = [
                (pay, first),
                (bday(pay + pd.Timedelta(days=30)), round(inv.amount_local - first, 2)),
            ]
        else:
            parts = [(pay, inv.amount_local)]
        for d, amt in parts:
            rate = fx.rate(inv.currency, d)
            receipts.append(
                dict(
                    invoice_id=inv.invoice_id,
                    customer_id=inv.customer_id,
                    entity=inv.entity,
                    currency=inv.currency,
                    receipt_date=d,
                    amount_local=amt,
                    fx_rate=rate,
                    amount_usd=round(amt * rate, 2),
                )
            )
    invoices = invoices.assign(
        is_disputed=disputed, written_off_date=pd.to_datetime(pd.Series(written_off))
    )
    r = pd.DataFrame(receipts).sort_values("receipt_date").reset_index(drop=True)
    r = r[r["receipt_date"] <= ctx.end].reset_index(drop=True)
    r.insert(0, "receipt_id", [f"RCP{i:06d}" for i in range(1, len(r) + 1)])
    return invoices, r


def bookings_by_month(contracts: pd.DataFrame) -> pd.Series:
    """Bookings (new logo ACV + expansion) by month of term start, for commissions."""
    s = contracts.groupby(contracts["term_start"].dt.to_period("M"))["bookings_usd"].sum()
    return s.astype(float)


def arr_by_month(contracts: pd.DataFrame, months: pd.DatetimeIndex) -> pd.Series:
    """Total active ARR at the start of each month: drives expense run rates."""
    ts, te, arr = (contracts[c].to_numpy() for c in ("term_start", "term_end", "arr_usd"))
    vals = [arr[(ts <= m.to_datetime64()) & (te >= m.to_datetime64())].sum() for m in months]
    return pd.Series(np.array(vals, dtype=float), index=months)
