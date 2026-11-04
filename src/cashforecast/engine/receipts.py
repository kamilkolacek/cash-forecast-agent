"""Receipts forecast: four streams, each learned from history known at the cutoff.

1. customer_collections_existing_ar    open invoices, timed by each customer's own lateness
2. customer_collections_contracted     unbilled installments of current contract terms
3. customer_collections_renewals       terms renewing in the horizon, churn/expansion-weighted
4. customer_collections_new_bookings   pipeline, probability-weighted
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from cashforecast.engine.snapshot import Snapshot, roll, spot_fx
from cashforecast.synthetic._util import bday

INSTALLMENTS = {"annual": 1, "quarterly": 4, "monthly": 12}
CREDIBILITY_K = 5  # receipts needed before a customer's own history outweighs its archetype
LINE_COLS = ["date", "category", "amount_usd", "source_type", "source_id", "customer_id", "note"]


def payment_behavior(snap: Snapshot) -> pd.DataFrame:
    """Expected days paid relative to due date, per customer, shrunk toward the archetype."""
    r = snap["receipts"].merge(snap["invoices"][["invoice_id", "due_date"]], on="invoice_id")
    r["days_late"] = (r["receipt_date"] - r["due_date"]).dt.days
    cust = snap["customers"][["customer_id", "archetype", "terms_days"]]
    r = r.merge(cust, on="customer_id")
    arch = (
        r.groupby("archetype")["days_late"]
        .agg(["mean", "std"])
        .rename(columns={"mean": "a_mean", "std": "a_sd"})
    )
    own = r.groupby("customer_id")["days_late"].agg(["mean", "std", "count"])
    out = cust.merge(own, on="customer_id", how="left").merge(arch, on="archetype", how="left")
    n = out["count"].fillna(0)
    w = n / (n + CREDIBILITY_K)
    out["exp_days_late"] = (w * out["mean"].fillna(0) + (1 - w) * out["a_mean"]).round(1)
    out["sd_days_late"] = out["std"].fillna(out["a_sd"]).fillna(out["a_sd"].mean()).round(1)
    return out[["customer_id", "archetype", "terms_days", "exp_days_late", "sd_days_late"]]


def renewal_rates(snap: Snapshot) -> dict[str, Any]:
    """Churn, expansion and renewal billing delay by archetype, from completed terms."""
    k = snap["contracts"].merge(snap["customers"][["customer_id", "archetype"]], on="customer_id")
    done = k[k["churned_at_end"].notna()]
    churn = done.groupby("archetype")["churned_at_end"].mean().astype(float)
    nxt = k[["customer_id", "term_no", "arr_usd"]].rename(columns={"arr_usd": "next_arr"})
    nxt["term_no"] -= 1
    renewed = done[~done["churned_at_end"].astype(bool)].merge(nxt, on=["customer_id", "term_no"])
    expansion = (
        renewed.groupby("archetype")["next_arr"].sum()
        / renewed.groupby("archetype")["arr_usd"].sum()
        - 1
    )
    inv = snap["invoices"]
    first_bills = inv[inv["is_renewal_billing"]].merge(
        k[["contract_id", "term_start"]], on="contract_id"
    )
    delay = float((first_bills["issue_date"] - first_bills["term_start"]).dt.days.mean())
    return {
        "churn": churn.round(4).to_dict(),
        "expansion": expansion.round(4).to_dict(),
        "renewal_billing_delay_days": round(delay, 1),
    }


# Quintile midpoints of a standard normal: spread each expected payment across five
# equally likely dates instead of betting it all on one day.
SPREAD_Z = (-1.2816, -0.5244, 0.0, 0.5244, 1.2816)


def _spread(
    mean_date: pd.Timestamp, sd: float, floor: pd.Timestamp
) -> list[tuple[pd.Timestamp, float]]:
    sd = max(float(sd), 0.0)
    return [
        (roll(mean_date + pd.Timedelta(days=round(z * sd)), floor), 1 / len(SPREAD_Z))
        for z in SPREAD_Z
    ]


def _collect(
    issue: pd.Timestamp, terms: float, late: float, sd: float, floor: pd.Timestamp
) -> list[tuple[pd.Timestamp, float]]:
    return _spread(issue + pd.Timedelta(days=float(terms + late)), sd, floor)


def _emit(lines: list, timing: list[tuple[pd.Timestamp, float]], amount: float, **kw) -> None:
    for date, w in timing:
        lines.append(dict(date=date, amount_usd=amount * w, **kw))


def forecast_receipts(snap: Snapshot, end: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, Any]]:
    c = snap.cutoff
    fx = spot_fx(snap)
    beh = payment_behavior(snap).set_index("customer_id")
    rates = renewal_rates(snap)
    cust = snap["customers"].set_index("customer_id")
    lines: list[dict[str, Any]] = []

    # 1. Open AR
    inv = snap["invoices"]
    open_ = inv[inv["status"] == "open"]
    for i in open_.itertuples():
        b = beh.loc[i.customer_id]
        expected = i.due_date + pd.Timedelta(days=float(b.exp_days_late))
        days_beyond = (c - expected).days
        if days_beyond <= 0:
            timing, p, note = _spread(expected, b.sd_days_late, c), 1.0, "on pattern"
        elif i.is_disputed:
            timing, p, note = [(bday(c + pd.Timedelta(days=45)), 1.0)], 0.8, "disputed"
        elif days_beyond > 2 * b.sd_days_late + 7:
            timing, p, note = (
                [(bday(c + pd.Timedelta(days=30)), 1.0)],
                0.5,
                "behavior break: 50% weighted",
            )
        else:
            timing, p, note = _spread(c + pd.Timedelta(days=7), 3, c), 1.0, "modestly late"
        _emit(
            lines,
            timing,
            i.open_amount_local * fx[i.currency] * p,
            category="customer_collections_existing_ar",
            source_type="invoice",
            source_id=i.invoice_id,
            customer_id=i.customer_id,
            note=note,
        )

    # 2 & 3. Contracted installments and renewals
    k = snap["contracts"]
    invoiced = set(inv["contract_id"])
    current = k[k["term_end"] >= c]
    for t in current.itertuples():
        b, cu = beh.loc[t.customer_id], cust.loc[t.customer_id]
        n = INSTALLMENTS[t.billing_freq]
        for j in range(n):
            sched = t.term_start + pd.DateOffset(months=j * (12 // n))
            slipped_renewal = (
                j == 0
                and t.is_renewal
                and t.contract_id not in invoiced
                and t.term_start >= c - pd.Timedelta(days=90)
            )
            if slipped_renewal:
                # Renewal term started but its first invoice is not out yet (billing slip).
                issue = roll(
                    t.term_start + pd.Timedelta(days=rates["renewal_billing_delay_days"]), c
                )
            elif sched < c:
                continue
            else:
                issue = bday(sched)
            if issue > end:
                break
            _emit(
                lines,
                _collect(issue, cu.terms_days, b.exp_days_late, b.sd_days_late, c),
                t.arr_usd / n,
                category="customer_collections_contracted",
                source_type="contract",
                source_id=t.contract_id,
                customer_id=t.customer_id,
                note=f"installment {j + 1}/{n}",
            )

    renewing = current[current["term_end"] < end]
    for t in renewing.itertuples():
        b, cu = beh.loc[t.customer_id], cust.loc[t.customer_id]
        a = b.archetype
        churn = rates["churn"].get(a, 0.1)
        exp = rates["expansion"].get(a, 0.0)
        exp_arr = t.arr_usd * (1 - churn) * (1 + exp)
        n = INSTALLMENTS[t.billing_freq]
        start = t.term_end + pd.Timedelta(days=1)
        for j in range(n):
            issue = start + pd.DateOffset(months=j * (12 // n))
            if j == 0:
                issue += pd.Timedelta(days=rates["renewal_billing_delay_days"])
            issue = bday(issue)
            if issue > end:
                break
            _emit(
                lines,
                _collect(issue, cu.terms_days, b.exp_days_late, b.sd_days_late, c),
                exp_arr / n,
                category="customer_collections_renewals",
                source_type="renewal",
                source_id=t.contract_id,
                customer_id=t.customer_id,
                note=f"renewal {j + 1}/{n}, p_renew={1 - churn:.2f}",
            )

    # 4. Pipeline (new logos)
    arch_terms = snap["customers"].groupby("archetype")["terms_days"].median()
    arch_late = beh.groupby("archetype")["exp_days_late"].mean()
    arch_sd = beh.groupby("archetype")["sd_days_late"].mean()
    for o in snap["pipeline"].itertuples():
        n = INSTALLMENTS[o.billing_freq]
        close = max(o.expected_close, c)
        for j in range(n):
            issue = bday(close + pd.DateOffset(months=j * (12 // n)))
            if issue > end:
                break
            timing = _collect(
                issue,
                arch_terms.get(o.archetype, 30),
                arch_late.get(o.archetype, 5),
                arch_sd.get(o.archetype, 7),
                c,
            )
            _emit(
                lines,
                timing,
                o.arr_usd / n * o.probability,
                category="customer_collections_new_bookings",
                source_type="opportunity",
                source_id=o.opportunity_id,
                customer_id=None,
                note=f"stage {o.stage}, p={o.probability}",
            )

    out = pd.DataFrame(lines, columns=LINE_COLS)
    out = out[(out["date"] >= c) & (out["date"] <= end)]
    assumptions = {
        "renewal_rates": rates,
        "archetype_days_late": arch_late.round(1).to_dict(),
        "fx_spot": fx,
        "open_ar_rules": {
            "disputed": "collect 80% at cutoff+45d",
            "behavior_break": "collect 50% at cutoff+30d (beyond 2 sd + 7d)",
            "modestly_late": "collect 100% at cutoff+7d",
        },
    }
    return out.reset_index(drop=True), assumptions


def expected_bookings(snap: Snapshot, month: pd.Period, rates: dict[str, Any]) -> float:
    """Bookings for a month: known actuals plus expected renewal expansion and pipeline."""
    c = snap.cutoff
    k = snap["contracts"]
    m_start, m_end = month.start_time, month.end_time.normalize()
    known = float(
        k.loc[(k["term_start"] >= m_start) & (k["term_start"] <= m_end), "bookings_usd"].sum()
    )
    if c > m_end:
        return known
    kk = k.merge(snap["customers"][["customer_id", "archetype"]], on="customer_id")
    ren = kk[
        (kk["term_end"] + pd.Timedelta(days=1) >= max(m_start, c))
        & (kk["term_end"] + pd.Timedelta(days=1) <= m_end)
    ]
    exp_rate = ren["archetype"].map(rates["expansion"]).fillna(0).clip(lower=0)
    churn = ren["archetype"].map(rates["churn"]).fillna(0.1)
    expansion = float((ren["arr_usd"] * (1 - churn) * exp_rate).sum())
    p = snap["pipeline"]
    win = p[(p["expected_close"] >= max(m_start, c)) & (p["expected_close"] <= m_end)]
    return known + expansion + float((win["arr_usd"] * win["probability"]).sum())
