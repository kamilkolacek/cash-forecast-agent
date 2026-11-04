"""Payroll calendars by entity (net pay + taxes/benefits), annual bonus, and commissions."""

from __future__ import annotations

import pandas as pd

from cashforecast.synthetic._util import SimContext, bday
from cashforecast.synthetic.fx import FxTable

PERIODS = {"biweekly": 26, "monthly": 12, "semimonthly": 24}
EMPLOYER_LOAD = 0.08  # employer taxes on top of gross


def pay_dates(freq: str, start: pd.Timestamp, end: pd.Timestamp) -> list[pd.Timestamp]:
    if freq == "biweekly":
        first = start + pd.Timedelta(days=(4 - start.weekday()) % 7)  # first Friday
        return list(pd.date_range(first, end, freq="14D"))
    dates = []
    for m in pd.date_range(start.replace(day=1), end, freq="MS"):
        if freq == "monthly":
            dates.append(bday(m.replace(day=25)))
        else:
            dates += [bday(m.replace(day=15)), bday(m + pd.offsets.MonthEnd(0))]
    return [d for d in dates if start <= d <= end]


def generate_payroll(ctx: SimContext, arr: pd.Series, fx: FxTable) -> pd.DataFrame:
    ex = ctx.cfg["expenses"]
    rows = []
    for e in ctx.cfg["entities"]:
        freq = ex["payroll_frequency"][e["code"]]
        dates = pay_dates(freq, ctx.start, ctx.end)
        for d in dates:
            annual_cost = arr.asof(d) * ex["payroll_pct_arr"] * e["arr_share"]
            gross = annual_cost / (1 + EMPLOYER_LOAD) / PERIODS[freq]
            parts = [("regular", gross)]
            # Bonus rides on the last pay date in the bonus month.
            same_month = [x for x in dates if x.month == d.month and x.year == d.year]
            if d.month == ex["bonus_month"] and d == max(same_month):
                parts.append(
                    ("bonus", annual_cost / (1 + EMPLOYER_LOAD) * ex["bonus_pct_annual_payroll"])
                )
            for run_type, g in parts:
                net = g * ex["payroll_net_share"]
                tax = g - net + g * EMPLOYER_LOAD
                for comp, usd, when in [
                    ("net_pay", net, d),
                    ("taxes_benefits", tax, bday(d + pd.Timedelta(days=1))),
                ]:
                    rate = fx.rate(e["currency"], when)
                    rows.append(
                        dict(
                            entity=e["code"],
                            currency=e["currency"],
                            pay_date=when,
                            period_date=d,
                            run_type=run_type,
                            component=comp,
                            amount_local=round(usd / rate, 2),
                            fx_rate=rate,
                            amount_usd=round(round(usd / rate, 2) * rate, 2),
                        )
                    )
    df = pd.DataFrame(rows)
    df = df[df["pay_date"] <= ctx.end].sort_values("pay_date").reset_index(drop=True)
    df.insert(0, "payroll_id", [f"PR{i:05d}" for i in range(1, len(df) + 1)])
    return df


def generate_commissions(ctx: SimContext, bookings: pd.Series) -> pd.DataFrame:
    rate = ctx.cfg["expenses"]["commission_rate_of_bookings"]
    rows = []
    for period, amt in bookings.items():
        pay = bday((period + 1).to_timestamp().replace(day=15))
        if ctx.start <= pay <= ctx.end and amt > 0:
            rows.append(
                dict(
                    entity="US01",
                    currency="USD",
                    bookings_month=str(period),
                    pay_date=pay,
                    bookings_usd=round(amt, 2),
                    amount_usd=round(amt * rate, 2),
                )
            )
    df = pd.DataFrame(rows)
    df.insert(0, "commission_id", [f"CM{i:04d}" for i in range(1, len(df) + 1)])
    return df
