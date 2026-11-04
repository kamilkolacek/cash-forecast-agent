"""Integrity tie-outs and data-quality findings.

Severity:
  ERROR    the dataset is internally inconsistent; a forecast must not run on it
  WARNING  real-world problem a treasury analyst should act on (e.g. duplicate payment)
  INFO     context worth surfacing (e.g. concentration of overdue AR)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

from cashforecast.data.schemas import SCHEMAS

TOL = 0.01


@dataclass
class Finding:
    check: str
    severity: str
    passed: bool
    detail: str
    data: dict[str, Any] = field(default_factory=dict)


def _tie(name: str, a: float, b: float, what: str) -> Finding:
    diff = round(a - b, 2)
    ok = abs(diff) <= TOL
    return Finding(
        name, "ERROR", ok, f"{what}: subledger {a:,.2f} vs bank {b:,.2f} (diff {diff:,.2f})"
    )


def check_schemas(d: dict[str, pd.DataFrame]) -> list[Finding]:
    out = []
    for table, spec in SCHEMAS.items():
        if table not in d:
            out.append(Finding(f"schema:{table}", "ERROR", False, "table missing"))
            continue
        missing = [c for c in spec["columns"] if c not in d[table].columns]  # type: ignore[union-attr]
        key = spec["key"]
        dupes = int(d[table][key].duplicated().sum()) if key else 0
        ok = not missing and dupes == 0
        out.append(
            Finding(
                f"schema:{table}",
                "ERROR",
                ok,
                "ok" if ok else f"missing={missing} duplicate_keys={dupes}",
            )
        )
    return out


def check_tieouts(d: dict[str, pd.DataFrame], opening_cash: float) -> list[Finding]:
    bank, bal = d["bank_transactions"], d["bank_balances"]
    by_type = bank.groupby("source_type")["amount_usd"].sum()
    out = [
        _tie(
            "tie:receipts_to_bank",
            d["receipts"]["amount_usd"].sum(),
            by_type.get("ar_receipt", 0.0),
            "Customer receipts",
        ),
        _tie(
            "tie:ap_to_bank",
            -d["ap_payments"]["amount_usd"].sum(),
            by_type.get("ap_payment", 0.0),
            "AP payments",
        ),
        _tie(
            "tie:payroll_to_bank",
            -d["payroll"]["amount_usd"].sum(),
            by_type.get("payroll", 0.0),
            "Payroll",
        ),
        _tie(
            "tie:commissions_to_bank",
            -d["commissions"]["amount_usd"].sum(),
            by_type.get("commission", 0.0),
            "Commissions",
        ),
    ]
    # Bank roll-forward: opening + cumulative flows = closing, every day.
    flows = bank.groupby("date")["amount_usd"].sum().reindex(bal["date"], fill_value=0.0)
    expected = opening_cash + flows.cumsum().to_numpy()
    worst = float(abs(expected - bal["closing_balance_usd"].to_numpy()).max())
    out.append(
        Finding(
            "tie:bank_rollforward",
            "ERROR",
            worst <= 1.0,
            f"max daily roll-forward break {worst:,.2f}",
        )
    )
    # Every subledger cash item appears in the bank exactly once.
    for src, table, key in [
        ("ar_receipt", "receipts", "receipt_id"),
        ("ap_payment", "ap_payments", "payment_id"),
    ]:
        ids = set(bank.loc[bank["source_type"] == src, "source_id"])
        missing = int((~d[table][key].isin(ids)).sum())
        out.append(
            Finding(
                f"tie:{table}_in_bank",
                "ERROR",
                missing == 0,
                f"{missing} {table} rows not found in bank",
            )
        )
    return out


def check_ar(d: dict[str, pd.DataFrame]) -> list[Finding]:
    inv, rcp = d["invoices"], d["receipts"]
    out = []
    calc = (inv["amount_local"] - inv["paid_local_to_date"]).round(2)
    breaks = int((abs(calc - inv["open_amount_local"]) > TOL).sum())
    out.append(
        Finding(
            "ar:open_balance_math",
            "ERROR",
            breaks == 0,
            f"{breaks} invoices where open != amount - paid",
        )
    )
    over = int((inv["open_amount_local"] < -TOL).sum())
    out.append(Finding("ar:no_overpayment", "ERROR", over == 0, f"{over} overpaid invoices"))
    m = rcp.merge(inv[["invoice_id", "issue_date"]], on="invoice_id", how="left")
    early = int((m["receipt_date"] < m["issue_date"]).sum())
    out.append(
        Finding(
            "ar:receipt_after_issue",
            "ERROR",
            early == 0,
            f"{early} receipts dated before their invoice",
        )
    )
    return out


def check_data_quality(d: dict[str, pd.DataFrame], as_of: pd.Timestamp) -> list[Finding]:
    """Findings a treasury analyst should act on. These are expected to fire on anomalies."""
    out = []
    pay = d["ap_payments"]
    multi = pay.groupby("bill_id").filter(lambda g: len(g) > 1)
    if len(multi):
        bills = multi.groupby("bill_id").agg(
            payments=("payment_id", list), amount_usd=("amount_usd", "first")
        )
        out.append(
            Finding(
                "dq:duplicate_ap_payment",
                "WARNING",
                False,
                f"{len(bills)} bill(s) paid more than once",
                {"bills": bills.reset_index().to_dict("records")},
            )
        )
    else:
        out.append(Finding("dq:duplicate_ap_payment", "WARNING", True, "no duplicate payments"))

    inv = d["invoices"]
    open_ = inv[inv["status"] == "open"].copy()
    open_["days_past_due"] = (as_of - open_["due_date"]).dt.days
    stale = open_[(open_["days_past_due"] > 60) & ~open_["is_disputed"]]
    out.append(
        Finding(
            "dq:stale_undisputed_ar",
            "WARNING",
            stale.empty,
            f"{len(stale)} undisputed invoices >60 days past due "
            f"(${stale['amount_usd_at_issue'].sum():,.0f})",
            {
                "invoices": stale[
                    ["invoice_id", "customer_id", "days_past_due", "amount_usd_at_issue"]
                ].to_dict("records")
            },
        )
    )
    # Behavior break: past due well beyond this customer's own normal lateness.
    c = d["customers"][["customer_id", "mean_days_late", "sd_days_late"]]
    ob = open_.merge(c, on="customer_id", how="left")
    ob["threshold"] = ob["mean_days_late"] + 2 * ob["sd_days_late"] + 7
    breaks = ob[(ob["days_past_due"] > ob["threshold"]) & ~ob["is_disputed"]]
    out.append(
        Finding(
            "dq:payment_behavior_break",
            "WARNING",
            breaks.empty,
            f"{breaks['customer_id'].nunique()} customer(s) paying well outside "
            f"their normal pattern (${breaks['amount_usd_at_issue'].sum():,.0f} open)",
            {
                "invoices": breaks[
                    [
                        "invoice_id",
                        "customer_id",
                        "days_past_due",
                        "threshold",
                        "amount_usd_at_issue",
                    ]
                ]
                .round(1)
                .to_dict("records")
            },
        )
    )

    overdue = open_[open_["days_past_due"] > 0]
    if len(overdue):
        by_c = (
            overdue.groupby("customer_id")["amount_usd_at_issue"].sum().sort_values(ascending=False)
        )
        share = float(by_c.iloc[:5].sum() / by_c.sum())
        out.append(
            Finding(
                "dq:overdue_concentration",
                "INFO",
                True,
                f"top 5 customers hold {share:.0%} of overdue AR",
                {"top": by_c.head(5).round(0).to_dict()},
            )
        )
    return out


def validate(
    d: dict[str, pd.DataFrame], opening_cash: float, as_of: pd.Timestamp
) -> dict[str, Any]:
    findings = check_schemas(d)
    if all(f.passed for f in findings):
        findings += check_tieouts(d, opening_cash) + check_ar(d)
        findings += check_data_quality(d, as_of)
    errors = [f for f in findings if f.severity == "ERROR" and not f.passed]
    return {
        "passed": not errors,
        "errors": len(errors),
        "warnings": sum(f.severity == "WARNING" and not f.passed for f in findings),
        "findings": [asdict(f) for f in findings],
    }
