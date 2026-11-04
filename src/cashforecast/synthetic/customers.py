"""Customers, contract terms (renewals, churn, expansion), and the sales pipeline."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cashforecast.synthetic._util import SimContext, lognormal_to_total

STAGE_PROBABILITY = {1: 0.10, 2: 0.20, 3: 0.40, 4: 0.60, 5: 0.80}


def _pick_entity(ctx: SimContext, n: int) -> list[str]:
    ents = ctx.cfg["entities"]
    return list(ctx.rng.choice([e["code"] for e in ents], size=n, p=[e["arr_share"] for e in ents]))


def _billing(ctx: SimContext, archetype: str, n: int) -> list[str]:
    mix = ctx.cfg["customers"]["archetypes"][archetype]["billing_mix"]
    keys = list(mix)
    return list(ctx.rng.choice(keys, size=n, p=[mix[k] for k in keys]))


def generate_customers(ctx: SimContext) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (customers, new_logo_starts). Existing base plus new logos over the window."""
    cfg, rng = ctx.cfg, ctx.rng
    ccfg, rev = cfg["customers"], cfg["revenue"]
    ccy = {e["code"]: e["currency"] for e in cfg["entities"]}
    rows = []

    # Whales: largest enterprise accounts, US-based, annual billing, slow portal payers.
    w = ccfg["whales"]
    whale_arr = lognormal_to_total(rng, w["count"], rev["starting_arr"] * w["arr_share"], 0.3)
    for arr in sorted(whale_arr, reverse=True):
        rows.append(
            dict(
                archetype="enterprise",
                is_whale=True,
                entity="US01",
                arr=arr,
                billing_freq="annual",
                terms_days=60,
                origin="existing",
            )
        )

    # Existing base by archetype.
    non_whale_arr = rev["starting_arr"] * (1 - w["arr_share"])
    n_base = ccfg["existing_count"] - w["count"]
    arche_mean = {}
    for name, a in ccfg["archetypes"].items():
        n = int(round(n_base * a["count_share"]))
        arrs = lognormal_to_total(rng, n, non_whale_arr * a["arr_share"])
        arche_mean[name] = arrs.mean()
        for arr, ent, bill in zip(arrs, _pick_entity(ctx, n), _billing(ctx, name, n), strict=True):
            rows.append(
                dict(
                    archetype=name,
                    is_whale=False,
                    entity=ent,
                    arr=arr,
                    billing_freq=bill,
                    terms_days=int(rng.choice(a["terms_days"])),
                    origin="existing",
                )
            )

    # New logos: Poisson per month, weighted toward Q4.
    q4 = rev["q4_bookings_weight"]
    qw = {1: (1 - q4) / 3, 2: (1 - q4) / 3, 3: (1 - q4) / 3, 4: q4}
    starts = []
    for m in pd.date_range(ctx.start, ctx.end, freq="MS"):
        lam = rev["new_logos_per_year"] / 12 * qw[m.quarter] * 4
        for _ in range(rng.poisson(lam)):
            starts.append(m + pd.Timedelta(days=int(rng.integers(0, m.days_in_month))))
    names = list(ccfg["archetypes"])
    shares = [ccfg["archetypes"][k]["count_share"] for k in names]
    for d in starts:
        name = str(rng.choice(names, p=shares))
        a = ccfg["archetypes"][name]
        arr = arche_mean[name] * rev["new_logo_size_factor"] * rng.lognormal(-0.18, 0.6)
        rows.append(
            dict(
                archetype=name,
                is_whale=False,
                entity=_pick_entity(ctx, 1)[0],
                arr=arr,
                billing_freq=_billing(ctx, name, 1)[0],
                terms_days=int(rng.choice(a["terms_days"])),
                origin="new_logo",
                first_start=d,
            )
        )

    df = pd.DataFrame(rows)
    df.insert(0, "customer_id", [f"C{i:05d}" for i in range(1, len(df) + 1)])
    df["currency"] = df["entity"].map(ccy)
    df["name"] = [f"Customer {cid[1:]}" for cid in df["customer_id"]]
    for name, a in ccfg["archetypes"].items():
        m = df["archetype"] == name
        df.loc[m, "mean_days_late"] = a["mean_days_late"]
        df.loc[m, "sd_days_late"] = a["sd_days_late"]
    df.loc[df["is_whale"], ["mean_days_late", "sd_days_late"]] = [28, 15]
    card = ccfg["archetypes"]["smb"].get("card_share", 0)
    df["pays_by_card"] = (df["archetype"] == "smb") & (rng.random(len(df)) < card)
    # Existing customers renew on a random anniversary within the first year of history.
    existing = df["origin"] == "existing"
    offsets = rng.integers(1, 366, size=existing.sum())
    df.loc[existing, "first_start"] = [ctx.start - pd.Timedelta(days=int(o)) for o in offsets]
    df["first_start"] = pd.to_datetime(df["first_start"]).dt.normalize()
    return df, df.loc[~existing, ["customer_id", "first_start"]]


def generate_contracts(ctx: SimContext, customers: pd.DataFrame) -> pd.DataFrame:
    """Annual contract terms per customer: renewals with churn, expansion and billing slips."""
    cfg, rng = ctx.cfg, ctx.rng
    rev, ccfg = cfg["revenue"], cfg["customers"]
    rows = []
    for c in customers.itertuples():
        churn = ccfg["whales"]["churn"] if c.is_whale else ccfg["archetypes"][c.archetype]["churn"]
        exp_mean = rev["net_retention"] / (1 - churn) - 1
        term_start, arr, term_no = c.first_start, c.arr, 1
        prev_arr = 0.0 if c.origin == "new_logo" else None
        while term_start <= ctx.end:
            bookings = arr if prev_arr == 0.0 else max(0.0, arr - (prev_arr or arr))
            slip = term_no > 1 and rng.random() < rev["renewal_slip_rate"]
            churned = bool(rng.random() < churn)
            rows.append(
                dict(
                    customer_id=c.customer_id,
                    term_no=term_no,
                    term_start=term_start,
                    term_end=term_start + pd.DateOffset(years=1) - pd.Timedelta(days=1),
                    arr_usd=round(arr, 2),
                    billing_freq=c.billing_freq,
                    is_renewal=term_no > 1,
                    bookings_usd=round(bookings, 2),
                    billing_delay_days=int(rng.integers(15, 46)) if slip else 0,
                    churned_at_end=churned,
                )
            )
            if churned:
                break
            prev_arr = arr
            arr = arr * (1 + max(-0.10, rng.normal(exp_mean, 0.10)))
            term_start = term_start + pd.DateOffset(years=1)
            term_no += 1
    df = pd.DataFrame(rows)
    df.insert(0, "contract_id", [f"K{i:06d}" for i in range(1, len(df) + 1)])
    return df


def generate_pipeline(
    ctx: SimContext, customers: pd.DataFrame, contracts: pd.DataFrame, window_days: int = 120
) -> pd.DataFrame:
    """Open opportunities as of the forecast date: true future wins plus deals that will be lost."""
    rng = ctx.rng
    horizon = ctx.as_of + pd.Timedelta(days=window_days)
    first = contracts[contracts["term_no"] == 1].merge(
        customers[["customer_id", "origin", "archetype", "entity"]], on="customer_id"
    )
    wins = first[
        (first["origin"] == "new_logo")
        & (first["term_start"] >= ctx.as_of)
        & (first["term_start"] <= horizon)
    ]
    rows = []
    for w in wins.itertuples():
        days = (w.term_start - ctx.as_of).days
        stage = 5 if days <= 30 else 4 if days <= 60 else 3 if days <= 90 else 2
        stage = int(np.clip(stage + rng.choice([-1, 0, 0, 1]), 1, 5))
        rows.append(
            dict(
                customer_id=w.customer_id,
                archetype=w.archetype,
                entity=w.entity,
                arr_usd=w.arr_usd,
                billing_freq=w.billing_freq,
                stage=stage,
                expected_close=w.term_start + pd.Timedelta(days=int(rng.normal(0, 10))),
                outcome="won",
                actual_close=w.term_start,
            )
        )
    n_lost = int(len(rows) * 0.8) + 5
    arrs = wins["arr_usd"].to_numpy() if len(wins) else np.array([100_000.0])
    for _ in range(n_lost):
        rows.append(
            dict(
                customer_id=None,
                archetype=str(rng.choice(["enterprise", "mid_market", "smb"])),
                entity="US01",
                arr_usd=float(rng.choice(arrs)) * rng.uniform(0.6, 1.4),
                billing_freq="annual",
                stage=int(rng.choice([1, 2, 3, 4], p=[0.35, 0.30, 0.20, 0.15])),
                expected_close=ctx.as_of + pd.Timedelta(days=int(rng.integers(5, window_days))),
                outcome="lost",
                actual_close=pd.NaT,
            )
        )
    df = pd.DataFrame(rows)
    df["probability"] = df["stage"].map(STAGE_PROBABILITY)
    df["expected_close"] = pd.to_datetime(df["expected_close"]).dt.normalize()
    df.insert(0, "opportunity_id", [f"O{i:05d}" for i in range(1, len(df) + 1)])
    return df
