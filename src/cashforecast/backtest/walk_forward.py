"""Walk-forward backtest: forecast from past cutoffs, score against what actually happened."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from cashforecast.backtest.metrics import GROUPS, naive_baseline, wape, weekly_by_group
from cashforecast.engine.forecast import run_forecast

SCORED = list(GROUPS) + ["total_receipts", "total_disbursements", "net_flow"]


def cutoffs(
    data: dict[str, pd.DataFrame],
    data_as_of: pd.Timestamp,
    weeks: int,
    min_training_weeks: int,
    step_days: int = 14,
) -> list[pd.Timestamp]:
    first = data["bank_balances"]["date"].min() + pd.Timedelta(weeks=min_training_weeks)
    last = data_as_of - pd.Timedelta(weeks=weeks)
    return list(pd.date_range(first, last, freq=f"{step_days}D"))


def score_one(
    data: dict[str, pd.DataFrame],
    cutoff: pd.Timestamp,
    data_as_of: pd.Timestamp,
    weeks: int,
    actual_bank: pd.DataFrame,
    actual_balances: pd.DataFrame,
) -> pd.DataFrame:
    """Long table: one row per (group, horizon week) with actual, engine and naive values."""
    res = run_forecast(data, cutoff, data_as_of)
    f = weekly_by_group(res.lines, cutoff, weeks)
    a = weekly_by_group(actual_bank, cutoff, weeks)
    n = naive_baseline(pd.concat([data["bank_transactions"], actual_bank]), cutoff, weeks)
    rows = []
    for g in SCORED:
        for w in range(1, weeks + 1):
            rows.append(
                dict(
                    cutoff=cutoff,
                    group=g,
                    week=w,
                    actual=a.loc[g, w],
                    forecast=f.loc[g, w],
                    naive=n.loc[g, w],
                )
            )
    # Ending balance by week.
    bal = actual_balances.set_index("date")["closing_balance_usd"]
    fdaily = res.daily.set_index("date")["closing_balance_usd"]
    for w in range(1, weeks + 1):
        d = cutoff + pd.Timedelta(days=7 * w - 1)
        if d in bal.index:
            naive_close = res.summary["opening_cash_usd"] + n.loc["net_flow", 1:w].sum()
            rows.append(
                dict(
                    cutoff=cutoff,
                    group="closing_balance",
                    week=w,
                    actual=bal[d],
                    forecast=fdaily[d],
                    naive=naive_close,
                )
            )
    return pd.DataFrame(rows)


def summarize(detail: pd.DataFrame) -> dict[str, Any]:
    """WAPE by group and horizon bucket; closing-balance error as % of actual balance."""
    out: dict[str, Any] = {"by_group": {}, "by_week": {}}
    buckets = {"weeks_1_4": range(1, 5), "weeks_5_13": range(5, 14)}
    for g, gdf in detail.groupby("group"):
        row = {}
        for b, wk in buckets.items():
            x = gdf[gdf["week"].isin(wk)]
            row[f"engine_{b}"] = round(wape(x["actual"].to_numpy(), x["forecast"].to_numpy()), 4)
            row[f"naive_{b}"] = round(wape(x["actual"].to_numpy(), x["naive"].to_numpy()), 4)
        out["by_group"][g] = row
    for g in ("total_receipts", "total_disbursements", "closing_balance"):
        gdf = detail[detail["group"] == g]
        out["by_week"][g] = {
            int(w): {
                "engine": round(wape(x["actual"].to_numpy(), x["forecast"].to_numpy()), 4),
                "naive": round(wape(x["actual"].to_numpy(), x["naive"].to_numpy()), 4),
            }
            for w, x in gdf.groupby("week")
        }
    # Cumulative flows: timing slips inside the horizon cancel out, as they do in cash.
    out["cumulative"] = {}
    for g in ("customer_receipts", "total_receipts", "total_disbursements", "net_flow"):
        gdf = detail[detail["group"] == g].sort_values(["cutoff", "week"]).copy()
        gdf[["actual", "forecast", "naive"]] = gdf.groupby("cutoff")[
            ["actual", "forecast", "naive"]
        ].cumsum()
        row = {}
        for b, wk in buckets.items():
            x = gdf[gdf["week"].isin(wk)]
            row[f"engine_{b}"] = round(wape(x["actual"].to_numpy(), x["forecast"].to_numpy()), 4)
            row[f"naive_{b}"] = round(wape(x["actual"].to_numpy(), x["naive"].to_numpy()), 4)
        out["cumulative"][g] = row
    cb = detail[detail["group"] == "closing_balance"]
    out["closing_balance_mean_abs_error_usd"] = round(
        float(np.abs(cb["actual"] - cb["forecast"]).mean()), 0
    )
    return out


def check_targets(summary: dict[str, Any], targets: dict[str, float]) -> dict[str, Any]:
    """Formal accuracy targets are on projected closing cash (see config/forecast.yaml)."""
    cb = summary["by_group"]["closing_balance"]
    return {
        b: {
            "engine": cb[f"engine_{b}"],
            "target": targets[b],
            "passed": cb[f"engine_{b}"] <= targets[b],
        }
        for b in ("weeks_1_4", "weeks_5_13")
    }


def run_backtest(
    data: dict[str, pd.DataFrame], data_as_of: pd.Timestamp, weeks: int, min_training_weeks: int
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cuts = cutoffs(data, data_as_of, weeks, min_training_weeks)
    frames = [
        score_one(data, c, data_as_of, weeks, data["bank_transactions"], data["bank_balances"])
        for c in cuts
    ]
    detail = pd.concat(frames, ignore_index=True)
    summary = summarize(detail)
    summary.update(
        {
            "cutoffs": len(cuts),
            "first_cutoff": str(cuts[0].date()),
            "last_cutoff": str(cuts[-1].date()),
            "note": "Pipeline at past cutoffs is reconstructed from realized new logos "
            "(no lost deals), which slightly flatters new-bookings accuracy.",
        }
    )
    return detail, summary


def score_live(
    data: dict[str, pd.DataFrame], holdout: dict[str, pd.DataFrame], as_of: pd.Timestamp, weeks: int
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Score the live forecast against the held-back 13 weeks of future actuals."""
    bank = holdout["bank_transactions"]
    balances = holdout["bank_balances"]
    detail = score_one(data, as_of, as_of, weeks, bank, balances)
    return detail, summarize(detail)
