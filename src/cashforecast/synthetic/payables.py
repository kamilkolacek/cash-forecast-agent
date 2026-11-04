"""Vendors, AP bills scaled to the ARR run rate, and payments on Tue/Fri payment runs."""

from __future__ import annotations

import pandas as pd

from cashforecast.synthetic._util import SimContext, lognormal_to_total
from cashforecast.synthetic.fx import FxTable

# category: (vendor count, bills per month, payment terms options)
CATEGORIES = {
    "cloud_hosting": (3, 3, [30]),
    "software_vendors": (150, 40, [30, 45]),
    "marketing_programs": (80, 20, [30]),
    "other_ap": (160, 50, [30, 45, 60]),
    "rent_facilities": (3, 3, [0]),
}
RENT_SPLIT = {"US01": 0.75, "UK01": 0.15, "CA01": 0.10}


def generate_vendors(ctx: SimContext) -> pd.DataFrame:
    rng = ctx.rng
    ents = ctx.cfg["entities"]
    rows = []
    for cat, (n, _, terms) in CATEGORIES.items():
        for i in range(n):
            if cat == "rent_facilities":
                ent = list(RENT_SPLIT)[i]
            elif cat == "cloud_hosting":
                ent = "US01"
            else:
                ent = str(rng.choice([e["code"] for e in ents], p=[e["arr_share"] for e in ents]))
            rows.append(
                dict(
                    category=cat,
                    entity=ent,
                    terms_days=int(rng.choice(terms)),
                    critical=cat in ("cloud_hosting", "rent_facilities"),
                )
            )
    df = pd.DataFrame(rows)
    ccy = {e["code"]: e["currency"] for e in ents}
    df["currency"] = df["entity"].map(ccy)
    df.insert(0, "vendor_id", [f"V{i:04d}" for i in range(1, len(df) + 1)])
    df["name"] = [f"Vendor {v[1:]}" for v in df["vendor_id"]]
    return df


def next_payment_run(d: pd.Timestamp, run_days: list[int]) -> pd.Timestamp:
    while d.weekday() not in run_days:
        d += pd.Timedelta(days=1)
    return d


def generate_bills(
    ctx: SimContext, vendors: pd.DataFrame, arr: pd.Series, fx: FxTable
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (bills, payments). arr is active ARR indexed by month start."""
    rng, ex = ctx.rng, ctx.cfg["expenses"]
    runs = ex["ap_payment_runs"]
    pct = {
        "cloud_hosting": ex["cloud_hosting_pct_arr"],
        "software_vendors": ex["software_pct_arr"],
        "marketing_programs": ex["marketing_pct_arr"],
        "other_ap": ex["other_ap_pct_arr"],
    }
    events = set(ex["marketing_event_months"])
    mkt_scale = 12 / (12 + len(events))  # event months carry double weight
    bills = []
    for m, run_rate in arr.items():
        for cat, (_, n_bills, _) in CATEGORIES.items():
            vend = vendors[vendors["category"] == cat]
            if cat == "rent_facilities":
                for v in vend.itertuples():
                    usd = ex["rent_annual_usd"] / 12 * RENT_SPLIT[v.entity]
                    bills.append((v, m, usd))
                continue
            monthly = run_rate * pct[cat] / 12
            if cat == "marketing_programs":
                monthly *= mkt_scale * (2 if m.month in events else 1)
            if cat == "cloud_hosting" and m.month == ex["cloud_commit_prepay"]["month"]:
                monthly += run_rate * pct[cat] * ex["cloud_commit_prepay"]["pct_annual"]
            amounts = lognormal_to_total(rng, n_bills, monthly, 0.9)
            picks = vend.sample(n=n_bills, replace=True, random_state=rng)
            for v, usd in zip(picks.itertuples(), amounts, strict=True):
                bills.append((v, m, usd))

    bill_rows, pay_rows = [], []
    for v, m, usd in bills:
        issue = (
            m
            if v.category == "rent_facilities"
            else m + pd.Timedelta(days=int(rng.integers(0, m.days_in_month)))
        )
        if issue > ctx.end:
            continue
        due = issue + pd.Timedelta(days=v.terms_days)
        local = round(usd / fx.rate(v.currency, issue), 2)
        bill_rows.append(
            dict(
                vendor_id=v.vendor_id,
                entity=v.entity,
                currency=v.currency,
                category=v.category,
                issue_date=issue,
                due_date=due,
                amount_local=local,
                amount_usd_at_issue=round(usd, 2),
            )
        )
        target = due
        if not v.critical and due.days_in_month - due.day < 3:  # month-end stretch
            target = due + pd.Timedelta(days=4)
        pay = next_payment_run(target, runs)
        rate = fx.rate(v.currency, pay)
        pay_rows.append(
            dict(
                vendor_id=v.vendor_id,
                entity=v.entity,
                currency=v.currency,
                category=v.category,
                payment_date=pay,
                amount_local=local,
                fx_rate=rate,
                amount_usd=round(local * rate, 2),
            )
        )

    b = pd.DataFrame(bill_rows)
    b.insert(0, "bill_id", [f"B{i:06d}" for i in range(1, len(b) + 1)])
    p = pd.DataFrame(pay_rows)
    p.insert(0, "bill_id", b["bill_id"])
    p = p[p["payment_date"] <= ctx.end].sort_values("payment_date").reset_index(drop=True)
    p.insert(0, "payment_id", [f"P{i:06d}" for i in range(1, len(p) + 1)])
    return b.sort_values("issue_date").reset_index(drop=True), p
