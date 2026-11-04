"""Disbursements forecast: known schedules first, learned run rates for the rest."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cashforecast.engine.receipts import LINE_COLS, expected_bookings
from cashforecast.engine.snapshot import Snapshot, roll
from cashforecast.synthetic._util import bday
from cashforecast.synthetic.payables import next_payment_run
from cashforecast.synthetic.payroll import pay_dates

DEBT_CATEGORY = {
    "interest": "debt_interest",
    "principal": "debt_principal",
    "undrawn_fee": "debt_interest",
}
TAX_CATEGORY = {"income_estimated": "income_taxes", "vat": "vat_sales_tax"}


def _line(date, category, amount, source_type, source_id, note="") -> dict[str, Any]:
    return dict(
        date=date,
        category=category,
        amount_usd=-abs(float(amount)),
        source_type=source_type,
        source_id=source_id,
        customer_id=None,
        note=note,
    )


def payroll_lines(snap: Snapshot, cfg: dict, end: pd.Timestamp) -> tuple[list, dict]:
    c, ex = snap.cutoff, cfg["expenses"]
    pr = snap["payroll"]
    lines, learned = [], {}
    for e in cfg["entities"]:
        code = e["code"]
        reg = pr[(pr["entity"] == code) & (pr["run_type"] == "regular")]
        per_run = {}
        for comp in ("net_pay", "taxes_benefits"):
            last = reg[reg["component"] == comp].groupby("period_date")["amount_usd"].sum()
            per_run[comp] = float(last.tail(3).mean())
        learned[code] = {k: round(v, 0) for k, v in per_run.items()}
        freq = ex["payroll_frequency"][code]
        if freq == "biweekly" and len(reg):
            # Continue the actual cadence from the last pay date, not from the cutoff.
            last = reg.loc[reg["component"] == "net_pay", "period_date"].max()
            dates = [
                d for d in pd.date_range(last + pd.Timedelta(days=14), end, freq="14D") if d >= c
            ]
        else:
            dates = pay_dates(freq, c, end)
        # Taxes from a pay date just before the cutoff are remitted after it.
        recent = reg[
            (reg["component"] == "net_pay") & (reg["pay_date"] >= c - pd.Timedelta(days=7))
        ]
        for d in recent["period_date"].unique():
            remit = bday(pd.Timestamp(d) + pd.Timedelta(days=1))
            if remit >= c:
                lines.append(
                    _line(
                        remit,
                        "payroll_taxes_benefits",
                        per_run["taxes_benefits"],
                        "payroll",
                        f"{code}:{pd.Timestamp(d):%Y-%m-%d}",
                        "remittance for pre-cutoff payroll",
                    )
                )
        for d in dates:
            lines.append(
                _line(
                    d,
                    "payroll_net",
                    per_run["net_pay"],
                    "payroll",
                    f"{code}:{d:%Y-%m-%d}",
                    "avg of last 3 regular runs",
                )
            )
            lines.append(
                _line(
                    bday(d + pd.Timedelta(days=1)),
                    "payroll_taxes_benefits",
                    per_run["taxes_benefits"],
                    "payroll",
                    f"{code}:{d:%Y-%m-%d}",
                )
            )
        # Annual bonus: last year's bonus, if the bonus month falls in the horizon.
        bonus_dates = [d for d in dates if d.month == ex["bonus_month"]]
        if bonus_dates:
            prev = pr[(pr["entity"] == code) & (pr["run_type"] == "bonus")]
            for comp, cat in (
                ("net_pay", "payroll_net"),
                ("taxes_benefits", "payroll_taxes_benefits"),
            ):
                amt = prev.loc[prev["component"] == comp, "amount_usd"].tail(1).sum()
                if amt:
                    lines.append(
                        _line(
                            max(bonus_dates),
                            cat,
                            amt,
                            "payroll",
                            f"{code}:bonus",
                            "prior-year bonus",
                        )
                    )
    return lines, learned


def commission_lines(snap: Snapshot, cfg: dict, end: pd.Timestamp, rates: dict) -> list:
    c, rate = snap.cutoff, cfg["expenses"]["commission_rate_of_bookings"]
    lines = []
    month = (c - pd.DateOffset(months=1)).to_period("M")
    while True:
        pay = bday((month + 1).to_timestamp().replace(day=15))
        if pay > end:
            break
        if pay >= c:
            bookings = expected_bookings(snap, month, rates)
            lines.append(
                _line(
                    pay,
                    "commissions",
                    bookings * rate,
                    "commission",
                    str(month),
                    f"{rate:.0%} of {month} bookings",
                )
            )
        month += 1
    return lines


def ap_lines(snap: Snapshot, cfg: dict, end: pd.Timestamp) -> tuple[list, dict]:
    c = snap.cutoff
    runs = cfg["expenses"]["ap_payment_runs"]
    fx_last = snap["fx_rates"].iloc[-1]
    lines = []
    # Open bills: pay on the first payment run on/after due date (or next run if overdue).
    for b in snap["ap_bills"][lambda x: x["status"] == "open"].itertuples():
        pay = next_payment_run(max(b.due_date, c), runs)
        if pay <= end:
            remaining = b.amount_local - b.paid_local_to_date
            lines.append(
                _line(
                    pay,
                    b.category,
                    remaining * float(fx_last[b.currency]),
                    "ap_bill",
                    b.bill_id,
                    "open bill",
                )
            )

    # Bills not yet received: monthly run rate x same-month seasonality, paid at avg terms.
    bills = snap["ap_bills"].copy()
    bills["month"] = bills["issue_date"].dt.to_period("M")
    last_full = (c - pd.Timedelta(days=1)).to_period("M")
    if c.day != 1:
        last_full -= 1
    monthly = bills.groupby(["category", "month"])["amount_usd_at_issue"].sum().unstack(0).fillna(0)
    vend = snap["vendors"].merge(
        bills.groupby("vendor_id")["amount_usd_at_issue"].sum().rename("spend"), on="vendor_id"
    )
    terms = vend.groupby("category").apply(
        lambda g: np.average(g["terms_days"], weights=g["spend"]), include_groups=False
    )
    # Spend share by payment terms, so 30-day and 60-day vendors land in different weeks.
    mix = (
        vend.groupby(["category", "terms_days"])["spend"].sum()
        / vend.groupby("category")["spend"].sum()
    )
    learned: dict[str, Any] = {}
    for cat in monthly.columns:
        s = monthly[cat]
        base_months = [last_full - i for i in range(3)]
        run_rate = float(s.reindex(base_months).fillna(0).mean())
        learned[cat] = {
            "monthly_run_rate": round(run_rate, 0),
            "avg_terms_days": round(float(terms.get(cat, 30)), 1),
            "terms_mix": {int(k): round(float(v), 3) for k, v in mix.loc[cat].items()}
            if cat in mix.index.get_level_values(0)
            else {},
            "seasonality": {},
        }
        for m in pd.period_range(c.to_period("M"), end.to_period("M"), freq="M"):
            ly = s.get(m - 12)
            ly_base = s.reindex([b - 12 for b in base_months]).dropna()
            factor = 1.0
            if ly is not None and len(ly_base) == 3 and ly_base.mean() > 0:
                factor = float(np.clip(ly / ly_base.mean(), 0.5, 3.0))
            learned[cat]["seasonality"][str(m)] = round(factor, 3)
            amount = run_rate * factor
            start, stop = max(m.start_time, c), min(m.end_time.normalize(), end)
            if cat == "rent_facilities":
                issue_days = [m.start_time] if m.start_time >= c else []
            else:
                issue_days = list(pd.bdate_range(start, stop))
            if not issue_days:
                continue
            share = len(issue_days) / max(len(pd.bdate_range(m.start_time, m.end_time)), 1)
            if cat == "rent_facilities":
                share = 1.0
            per_day = amount * share / len(issue_days)
            cat_mix = mix.loc[cat] if cat in mix.index.get_level_values(0) else pd.Series({30: 1.0})
            for d in issue_days:
                for term, w in cat_mix.items():
                    pay = next_payment_run(d + pd.Timedelta(days=int(term)), runs)
                    if pay <= end:
                        lines.append(
                            _line(
                                pay,
                                cat,
                                per_day * w,
                                "ap_run_rate",
                                f"{cat}:{m}",
                                f"run rate x {factor:.2f} seasonality, {term}d terms",
                            )
                        )
    return lines, learned


def schedule_lines(snap: Snapshot, end: pd.Timestamp) -> tuple[list, dict]:
    c = snap.cutoff
    lines = []
    debt = snap["debt_schedule"]
    for r in debt[(debt["date"] >= c) & (debt["date"] <= end)].itertuples():
        lines.append(
            _line(
                r.date,
                DEBT_CATEGORY[r.component],
                r.amount_usd,
                "debt",
                f"{r.facility}:{r.component}:{r.date:%Y-%m-%d}",
                "contractual",
            )
        )
    tax = snap["tax_calendar"]
    for r in tax[(~tax["paid"]) & (tax["due_date"] <= end)].itertuples():
        lines.append(
            _line(
                roll(r.due_date, c),
                TAX_CATEGORY[r.tax_type],
                r.amount_usd,
                "tax",
                f"{r.jurisdiction}:{r.period}",
                "tax calendar",
            )
        )
    cx = snap["capex_plan"]
    done = cx[cx["actual_date"].notna()]
    slip = float((done["actual_date"] - done["planned_date"]).dt.days.mean()) if len(done) else 21.0
    for r in cx[cx["actual_date"].isna()].itertuples():
        expected = r.planned_date + pd.Timedelta(days=round(slip))
        date = roll(expected, c + pd.Timedelta(days=7)) if expected < c else bday(expected)
        if date <= end:
            lines.append(
                _line(
                    date,
                    "capex",
                    r.amount_usd,
                    "capex",
                    r.project_id,
                    f"planned + {slip:.0f}d avg slippage",
                )
            )
    fees = snap["bank_transactions"]
    recent = fees[(fees["category"] == "bank_fees") & (fees["date"] >= c - pd.Timedelta(days=90))]
    per_bday = float(
        -recent["amount_usd"].sum()
        / max(len(pd.bdate_range(c - pd.Timedelta(days=90), c - pd.Timedelta(days=1))), 1)
    )
    for d in pd.bdate_range(c, end):
        lines.append(
            _line(d, "bank_fees", per_bday, "bank", f"fees:{d:%Y-%m-%d}", "90-day average")
        )
    return lines, {
        "capex_avg_slippage_days": round(slip, 1),
        "bank_fees_per_business_day": round(per_bday, 2),
    }


def forecast_disbursements(
    snap: Snapshot, cfg: dict, end: pd.Timestamp, rates: dict
) -> tuple[pd.DataFrame, dict[str, Any]]:
    pay, pay_learned = payroll_lines(snap, cfg, end)
    ap, ap_learned = ap_lines(snap, cfg, end)
    sched, sched_learned = schedule_lines(snap, end)
    lines = pay + commission_lines(snap, cfg, end, rates) + ap + sched
    out = pd.DataFrame(lines, columns=LINE_COLS)
    out = out[(out["date"] >= snap.cutoff) & (out["date"] <= end)].reset_index(drop=True)
    return out, {"payroll_per_run_usd": pay_learned, "ap": ap_learned, **sched_learned}
