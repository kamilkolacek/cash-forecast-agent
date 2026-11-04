"""Known schedules: term loan and revolver costs, capex projects (with slippage), and taxes."""

from __future__ import annotations

import pandas as pd

from cashforecast.synthetic._util import SimContext, bday, lognormal_to_total


def generate_debt_schedule(ctx: SimContext) -> pd.DataFrame:
    bs = ctx.cfg["balance_sheet"]
    tl, rv = bs["term_loan"], bs["revolver"]
    balance = float(tl["principal"])
    rows = []
    for q_end in pd.date_range(ctx.start, ctx.end, freq="QE"):
        d = bday(q_end)
        if d > ctx.end:
            break
        interest = balance * tl["rate"] / 4
        principal = min(tl["quarterly_amortization"], balance)
        balance -= principal
        rows += [
            dict(
                date=d,
                facility="term_loan",
                component="interest",
                amount_usd=round(interest, 2),
                balance_after=round(balance, 2),
            ),
            dict(
                date=d,
                facility="term_loan",
                component="principal",
                amount_usd=round(principal, 2),
                balance_after=round(balance, 2),
            ),
            dict(
                date=d,
                facility="revolver",
                component="undrawn_fee",
                amount_usd=round((rv["limit"] - rv["drawn"]) * rv["undrawn_fee"] / 4, 2),
                balance_after=float(rv["drawn"]),
            ),
        ]
    return pd.DataFrame(rows)


def generate_capex(ctx: SimContext) -> pd.DataFrame:
    rng, cx = ctx.rng, ctx.cfg["capex"]
    days = (ctx.end - ctx.start).days
    n = int(cx["projects_per_year"] * days / 365)
    amounts = lognormal_to_total(rng, n, cx["annual_budget"] * days / 365, 0.7)
    planned = sorted(ctx.start + pd.Timedelta(days=int(x)) for x in rng.integers(0, days, n))
    rows = []
    for i, (p, amt) in enumerate(zip(planned, amounts, strict=True), 1):
        actual = bday(p + pd.Timedelta(days=int(rng.exponential(cx["slippage_mean_days"]))))
        rows.append(
            dict(
                project_id=f"CX{i:03d}",
                description=f"Capex project {i}",
                entity="US01",
                planned_date=bday(p),
                amount_usd=round(amt, 2),
                actual_date=actual,
            )
        )
    return pd.DataFrame(rows)


def generate_taxes(ctx: SimContext, invoices: pd.DataFrame) -> pd.DataFrame:
    tx = ctx.cfg["tax"]
    rows = []
    for year in range(ctx.start.year, ctx.end.year + 1):
        for md in tx["us_due_dates"]:
            d = bday(pd.Timestamp(f"{year}-{md}"))
            if ctx.start <= d <= ctx.end:
                rows.append(
                    dict(
                        jurisdiction="US",
                        tax_type="income_estimated",
                        entity="US01",
                        period=f"{year}",
                        due_date=d,
                        amount_usd=float(tx["us_estimated_quarterly_usd"]),
                    )
                )
    uk = invoices[invoices["entity"] == "UK01"]
    by_q = uk.groupby(uk["issue_date"].dt.to_period("Q"))["amount_usd_at_issue"].sum()
    for q, billed in by_q.items():
        d = bday(q.end_time.normalize() + pd.DateOffset(months=1) + pd.Timedelta(days=7))
        if ctx.start <= d <= ctx.end:
            rows.append(
                dict(
                    jurisdiction="UK",
                    tax_type="vat",
                    entity="UK01",
                    period=str(q),
                    due_date=d,
                    amount_usd=round(billed * tx["uk_vat_rate_net"], 2),
                )
            )
    return pd.DataFrame(rows).sort_values("due_date").reset_index(drop=True)
