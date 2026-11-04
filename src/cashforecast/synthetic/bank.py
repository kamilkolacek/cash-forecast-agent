"""Derive the consolidated bank ledger (USD) from every subledger, plus fees and interest."""

from __future__ import annotations

import pandas as pd

from cashforecast.synthetic._util import SimContext, bday

LEDGER_COLS = [
    "date",
    "entity",
    "category",
    "amount_usd",
    "source_type",
    "source_id",
    "counterparty",
]


def _frame(
    df: pd.DataFrame,
    date: str,
    category,
    sign: int,
    source_type: str,
    source_id: str,
    counterparty: str,
) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "date": df[date].values,
            "entity": df["entity"].values,
            "category": df[category].values if category in df.columns else category,
            "amount_usd": sign * df["amount_usd"].astype(float).values,
            "source_type": source_type,
            "source_id": df[source_id].values,
            "counterparty": df[counterparty].values if counterparty in df.columns else counterparty,
        }
    )
    return out


def build_ledger(ctx: SimContext, d: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rng = ctx.rng
    pr = d["payroll"].copy()
    pr["category"] = pr["component"].map(
        {"net_pay": "payroll_net", "taxes_benefits": "payroll_taxes_benefits"}
    )
    debt = d["debt_schedule"].copy()
    debt["entity"] = "US01"
    debt["category"] = debt["component"].map(
        {"interest": "debt_interest", "principal": "debt_principal", "undrawn_fee": "debt_interest"}
    )
    debt["source_id"] = debt["facility"] + ":" + debt["date"].dt.strftime("%Y-%m-%d")
    capex = d["capex"].copy()
    tax = d["taxes"].copy()
    tax["category"] = tax["tax_type"].map(
        {"income_estimated": "income_taxes", "vat": "vat_sales_tax"}
    )
    tax["source_id"] = tax["jurisdiction"] + ":" + tax["period"]

    parts = [
        _frame(
            d["receipts"],
            "receipt_date",
            "customer_collections",
            1,
            "ar_receipt",
            "receipt_id",
            "customer_id",
        ),
        _frame(
            d["ap_payments"],
            "payment_date",
            "category",
            -1,
            "ap_payment",
            "payment_id",
            "vendor_id",
        ),
        _frame(pr, "pay_date", "category", -1, "payroll", "payroll_id", "Payroll provider"),
        _frame(
            d["commissions"],
            "pay_date",
            "commissions",
            -1,
            "commission",
            "commission_id",
            "Payroll provider",
        ),
        _frame(debt, "date", "category", -1, "debt", "source_id", "Lender"),
        _frame(capex, "actual_date", "capex", -1, "capex", "project_id", "Capex vendor"),
        _frame(tax, "due_date", "category", -1, "tax", "source_id", "Tax authority"),
    ]
    # Bank fees: small charges on most business days.
    days = pd.bdate_range(ctx.start, ctx.end)
    fee_days = days[rng.random(len(days)) < 0.6]
    fees = pd.DataFrame(
        {
            "date": fee_days,
            "entity": "US01",
            "amount_usd": rng.uniform(50, 600, len(fee_days)).round(2),
            "source_id": [f"FEE{i:05d}" for i in range(len(fee_days))],
        }
    )
    parts.append(_frame(fees, "date", "bank_fees", -1, "bank", "source_id", "Bank"))

    ledger = pd.concat(parts, ignore_index=True)
    ledger = ledger[(ledger["date"] >= ctx.start) & (ledger["date"] <= ctx.end)]
    ledger = _add_interest(ctx, ledger)
    ledger = ledger.sort_values(["date", "category", "source_id"]).reset_index(drop=True)
    ledger["amount_usd"] = ledger["amount_usd"].round(2)
    ledger.insert(0, "txn_id", [f"T{i:07d}" for i in range(1, len(ledger) + 1)])
    return ledger


def _add_interest(ctx: SimContext, ledger: pd.DataFrame) -> pd.DataFrame:
    """Monthly interest on the prior month's average balance, posted the next business day."""
    rate = ctx.cfg["balance_sheet"]["interest_income_rate"]
    opening = ctx.cfg["balance_sheet"]["opening_cash"]
    days = pd.date_range(ctx.start, ctx.end, freq="D")
    daily = ledger.groupby("date")["amount_usd"].sum().reindex(days, fill_value=0.0)
    balance = opening + daily.cumsum()
    rows, accrued = [], 0.0
    for m in pd.date_range(ctx.start, ctx.end, freq="MS"):
        month_bal = balance[(balance.index >= m) & (balance.index < m + pd.offsets.MonthBegin(1))]
        post = bday(m + pd.offsets.MonthBegin(1))
        if post > ctx.end:
            break
        amt = round((month_bal.mean() + accrued) * rate / 12, 2)
        accrued += amt
        rows.append(
            dict(
                date=post,
                entity="US01",
                category="interest_income",
                amount_usd=amt,
                source_type="bank",
                source_id=f"INT:{m:%Y-%m}",
                counterparty="Bank",
            )
        )
    return pd.concat([ledger, pd.DataFrame(rows)], ignore_index=True)


def daily_balances(
    ledger: pd.DataFrame, opening: float, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    flows = ledger.groupby("date")["amount_usd"].sum().reindex(days, fill_value=0.0)
    out = pd.DataFrame({"date": days, "net_flow_usd": flows.values.round(2)})
    out["closing_balance_usd"] = (opening + out["net_flow_usd"].cumsum()).round(2)
    out["opening_balance_usd"] = (out["closing_balance_usd"] - out["net_flow_usd"]).round(2)
    return out[["date", "opening_balance_usd", "net_flow_usd", "closing_balance_usd"]]
