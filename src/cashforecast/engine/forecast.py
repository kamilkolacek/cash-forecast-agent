"""Run a full 13-week forecast for a cutoff date."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from cashforecast.config import load_forecast_settings, load_yaml
from cashforecast.engine.disbursements import forecast_disbursements
from cashforecast.engine.receipts import forecast_receipts
from cashforecast.engine.rollforward import add_interest, daily_rollforward, daily_view, weekly_view
from cashforecast.engine.snapshot import horizon_dates, take_snapshot

TOL = 0.01


@dataclass
class ForecastResult:
    as_of: pd.Timestamp
    lines: pd.DataFrame  # every forecast cash item with its source
    daily: pd.DataFrame  # full-horizon daily roll-forward
    weekly: pd.DataFrame  # category x week table
    daily_detail: pd.DataFrame  # weeks 1-2 daily view
    summary: dict[str, Any]
    assumptions: dict[str, Any] = field(default_factory=dict)


def run_forecast(
    data: dict[str, pd.DataFrame], as_of: pd.Timestamp, data_as_of: pd.Timestamp | None = None
) -> ForecastResult:
    settings = load_forecast_settings()
    company = load_yaml("company.yaml")
    data_as_of = pd.Timestamp(data_as_of or as_of)
    snap = take_snapshot(data, pd.Timestamp(as_of), data_as_of)
    start, end = horizon_dates(snap, settings.horizon_weeks)

    rec, rec_a = forecast_receipts(snap, end)
    dis, dis_a = forecast_disbursements(snap, company, end, rec_a["renewal_rates"])
    lines = pd.concat([rec, dis], ignore_index=True)
    history = data["bank_balances"][data["bank_balances"]["date"] < start]
    lines = add_interest(
        lines,
        snap.opening_cash,
        start,
        end,
        history,
        company["balance_sheet"]["interest_income_rate"],
    )
    lines["amount_usd"] = lines["amount_usd"].round(2)
    lines = lines.sort_values(["date", "category"]).reset_index(drop=True)

    daily = daily_rollforward(lines, snap.opening_cash, start, end)
    weekly = weekly_view(lines, daily, start, settings.horizon_weeks)
    detail = daily_view(lines, daily, start, settings.daily_detail_weeks * 7)

    # Roll-forward identity must hold for every period.
    rf_break = abs(
        snap.opening_cash + lines["amount_usd"].sum() - daily["closing_balance_usd"].iloc[-1]
    )
    if rf_break > TOL:
        raise AssertionError(f"Roll-forward does not balance (break {rf_break:,.2f})")

    floor = settings.min_cash_threshold
    covenant = company["balance_sheet"]["covenants"]["min_liquidity"]
    wk = weekly.set_index("line")
    flags = []
    for w in [c for c in weekly.columns if c.startswith("W")]:
        low = float(wk.loc["Minimum daily cash", w])
        if low < covenant:
            flags.append({"week": w, "level": "covenant_breach", "min_cash_usd": round(low, 2)})
        elif low < floor:
            flags.append(
                {"week": w, "level": "below_internal_floor", "min_cash_usd": round(low, 2)}
            )

    low_row = daily.loc[daily["closing_balance_usd"].idxmin()]
    summary = {
        "as_of": str(start.date()),
        "horizon_end": str(end.date()),
        "horizon_weeks": settings.horizon_weeks,
        "opening_cash_usd": round(snap.opening_cash, 2),
        "ending_cash_usd": round(float(daily["closing_balance_usd"].iloc[-1]), 2),
        "total_receipts_usd": round(
            float(lines.loc[lines["amount_usd"] > 0, "amount_usd"].sum()), 2
        ),
        "total_disbursements_usd": round(
            float(lines.loc[lines["amount_usd"] < 0, "amount_usd"].sum()), 2
        ),
        "min_cash_usd": round(float(low_row["closing_balance_usd"]), 2),
        "min_cash_date": str(low_row["date"].date()),
        "min_cash_threshold_usd": floor,
        "covenant_min_liquidity_usd": covenant,
        "flags": flags,
        "week_ending": weekly.attrs["week_ending"],
        "pipeline_reconstructed": snap.pipeline_reconstructed,
    }
    assumptions = {"receipts": rec_a, "disbursements": dis_a}
    return ForecastResult(start, lines, daily, weekly, detail, summary, assumptions)
