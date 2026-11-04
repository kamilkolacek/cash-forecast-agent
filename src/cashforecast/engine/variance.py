"""Forecast-vs-actual variance with a timing / permanent split.

For a prior forecast made at P, actuals through C (the current cutoff), and X = the
comparison end, LOOKAHEAD_WEEKS beyond the current 13-week horizon:

  V         = actual(P..C) - prior_forecast(P..C)                 window variance
  permanent = actual(P..C) + current_forecast(C..X)
              - prior_forecast(P..X)                              cash no longer expected
  timing    = V - permanent                                       cash late but still coming

Permanent is about amounts, not dates: churn, write-offs, changed amounts or run rates.
Both forecasts are extended to X, well past the reported horizon, so a payment that
slips a few weeks (e.g. a renewal whose invoice keeps not going out) is still timing.
A fixed cutoff at the horizon end would misclassify such slips as permanent.

Receipts are keyed by customer, everything else by category, so drivers can be named.
Positive variance is favorable to cash. By construction timing + permanent = V for every
driver; drivers sum to the closing-cash difference at C; and the permanent total equals
revised minus prior-forecast cash at X.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from cashforecast.config import load_forecast_settings
from cashforecast.engine.forecast import ForecastResult, run_forecast

RECEIPT_CATS = {
    "customer_collections",
    "customer_collections_existing_ar",
    "customer_collections_contracted",
    "customer_collections_renewals",
    "customer_collections_new_bookings",
}


@dataclass
class VarianceResult:
    prior_cutoff: pd.Timestamp
    current_cutoff: pd.Timestamp
    comparison_end: pd.Timestamp
    drivers: pd.DataFrame  # one row per customer / category
    by_category: pd.DataFrame  # forecast vs actual in the window, by category
    summary: dict[str, Any]


def _key(df: pd.DataFrame) -> pd.Series:
    is_rec = df["category"].isin(RECEIPT_CATS)
    cust = df["customer_id"].fillna("unassigned_pipeline")
    return pd.Series(
        [
            "customer:" + c if r else "category:" + k
            for r, c, k in zip(is_rec, cust, df["category"], strict=True)
        ],
        index=df.index,
    )


def _actual_lines(bank: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    a = bank[(bank["date"] >= start) & (bank["date"] < end)].copy()
    a["customer_id"] = a["counterparty"].where(a["category"] == "customer_collections")
    return a[["date", "category", "amount_usd", "customer_id"]]


def compute_variance(
    data: dict[str, pd.DataFrame], prior: ForecastResult, current: ForecastResult
) -> VarianceResult:
    """`prior` must extend at least to `current`'s horizon end (see run_variance)."""
    p, c = prior.as_of, current.as_of
    x = pd.Timestamp(current.summary["horizon_end"])
    if not p < c:
        raise ValueError("current cutoff must fall after the prior cutoff")
    if pd.Timestamp(prior.summary["horizon_end"]) < x:
        raise ValueError("prior forecast must extend to the current forecast's horizon end")
    weeks = load_forecast_settings().horizon_weeks
    prior_end = p + pd.Timedelta(weeks=weeks) - pd.Timedelta(days=1)  # as originally reported

    f = prior.lines[prior.lines["date"] <= x]
    f = f.assign(key=_key(f))
    a = _actual_lines(data["bank_transactions"], p, c)
    a = a.assign(key=_key(a))
    r = current.lines.assign(key=_key(current.lines))

    in_win = f[f["date"] < c]
    tbl = pd.DataFrame(
        {
            "forecast_window": in_win.groupby("key")["amount_usd"].sum(),
            "actual_window": a.groupby("key")["amount_usd"].sum(),
            "prior_forecast_to_comparison_end": f.groupby("key")["amount_usd"].sum(),
            "reforecast_rest": r.groupby("key")["amount_usd"].sum(),
        }
    ).fillna(0.0)
    tbl["variance"] = tbl["actual_window"] - tbl["forecast_window"]
    tbl["permanent"] = (
        tbl["actual_window"] + tbl["reforecast_rest"] - tbl["prior_forecast_to_comparison_end"]
    )
    tbl["timing"] = tbl["variance"] - tbl["permanent"]
    tbl["classification"] = [
        "timing" if abs(t) >= abs(pm) else "permanent"
        for t, pm in zip(tbl["timing"], tbl["permanent"], strict=True)
    ]
    tbl = tbl.round(2)

    cust = data["customers"].set_index("customer_id")
    notes = f.groupby("key")["note"].agg(lambda s: "; ".join(sorted(set(s.dropna())))[:160])
    tbl["driver"] = [k.split(":", 1)[1] for k in tbl.index]
    tbl["type"] = ["customer" if k.startswith("customer:") else "category" for k in tbl.index]
    tbl["archetype"] = [
        cust["archetype"].get(d) if t == "customer" else None
        for d, t in zip(tbl["driver"], tbl["type"], strict=True)
    ]
    tbl["is_whale"] = [
        bool(cust["is_whale"].get(d, False)) if t == "customer" else False
        for d, t in zip(tbl["driver"], tbl["type"], strict=True)
    ]
    tbl["forecast_basis"] = tbl.index.map(notes).fillna("")
    tbl = tbl.reset_index(drop=True)
    order = (tbl["variance"].abs() + tbl["permanent"].abs()).sort_values(ascending=False).index
    tbl = tbl.reindex(order).reset_index(drop=True)

    # Category view for the window (bank books all collections under one category).
    fc = in_win.assign(
        cat=in_win["category"].where(~in_win["category"].isin(RECEIPT_CATS), "customer_collections")
    )
    by_cat = pd.DataFrame(
        {
            "forecast": fc.groupby("cat")["amount_usd"].sum(),
            "actual": a.groupby("category")["amount_usd"].sum(),
        }
    ).fillna(0.0)
    by_cat["variance"] = by_cat["actual"] - by_cat["forecast"]
    by_cat = (
        by_cat.round(2)
        .reset_index(names="category")
        .sort_values("variance", key=abs, ascending=False)
        .reset_index(drop=True)
    )

    def close_at(res: ForecastResult, d: pd.Timestamp) -> float:
        return float(res.daily.loc[res.daily["date"] <= d, "closing_balance_usd"].iloc[-1])

    fc_close = close_at(prior, c - pd.Timedelta(days=1))
    act_close = current.summary["opening_cash_usd"]
    summary = {
        "prior_cutoff": str(p.date()),
        "current_cutoff": str(c.date()),
        "window": f"{p.date()} to {(c - pd.Timedelta(days=1)).date()}",
        "comparison_end": str(x.date()),
        "permanent_definition": (
            f"cash no longer expected at all (both forecasts compared through {x.date()})"
        ),
        "forecast_closing_cash_usd": round(fc_close, 2),
        "actual_closing_cash_usd": round(act_close, 2),
        "total_variance_usd": round(act_close - fc_close, 2),
        "timing_usd": round(float(tbl["timing"].sum()), 2),
        "permanent_usd": round(float(tbl["permanent"].sum()), 2),
        "receipts_variance_usd": round(
            float(tbl.loc[tbl["type"] == "customer", "variance"].sum()), 2
        ),
        "disbursements_variance_usd": round(
            float(
                tbl.loc[
                    (tbl["type"] == "category") & (tbl["driver"] != "interest_income"), "variance"
                ].sum()
            ),
            2,
        ),
        "prior_forecast_cash_at_comparison_end_usd": round(close_at(prior, x), 2),
        "revised_cash_at_comparison_end_usd": round(close_at(current, x), 2),
        "prior_reported_horizon_end": str(prior_end.date()),
        "prior_reported_ending_cash_usd": round(close_at(prior, prior_end), 2),
    }
    return VarianceResult(p, c, x, tbl, by_cat, summary)


LOOKAHEAD_WEEKS = 13  # beyond the reported horizon, for the timing/permanent split only


def run_variance(
    data: dict[str, pd.DataFrame],
    prior_cutoff: pd.Timestamp,
    current_cutoff: pd.Timestamp,
    data_as_of: pd.Timestamp,
) -> VarianceResult:
    """Run both forecasts out to the same comparison end and compute the bridge."""
    weeks = load_forecast_settings().horizon_weeks
    elapsed = -(-(current_cutoff - prior_cutoff).days // 7)  # ceiling
    prior = run_forecast(
        data, prior_cutoff, data_as_of, horizon_weeks=weeks + LOOKAHEAD_WEEKS + elapsed
    )
    current = run_forecast(data, current_cutoff, data_as_of, horizon_weeks=weeks + LOOKAHEAD_WEEKS)
    return compute_variance(data, prior, current)
