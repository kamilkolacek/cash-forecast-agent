"""Scenarios: deterministic shocks applied to the base forecast's line items."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from cashforecast.config import load_forecast_settings, load_yaml
from cashforecast.engine.forecast import ForecastResult
from cashforecast.engine.receipts import LINE_COLS
from cashforecast.engine.rollforward import daily_rollforward, weekly_view
from cashforecast.synthetic._util import bday

RECEIPTS = [
    "customer_collections_existing_ar",
    "customer_collections_contracted",
    "customer_collections_renewals",
    "customer_collections_new_bookings",
]
REQUIRED = {
    "renewal_slip": ["pct_arr", "delay_days"],
    "churn": ["pct_renewals_lost"],
    "customer_delay": ["target", "delay_days"],
    "collections_delay": ["delay_days"],
    "pipeline_accelerate": ["deal_rank", "advance_days"],
    "payroll_adjust": ["pct_change", "effective_week"],
    "one_off": ["date", "amount_usd", "category"],
}


def validate_shocks(shocks: list[dict[str, Any]]) -> None:
    for s in shocks:
        t = s.get("type")
        if t not in REQUIRED:
            raise ValueError(f"Unknown shock type {t!r}. Known: {sorted(REQUIRED)}")
        missing = [f for f in REQUIRED[t] if f not in s]
        if missing:
            raise ValueError(f"Shock {t} missing fields {missing}")


def _shift(lines: pd.DataFrame, mask: pd.Series, days: int, floor: pd.Timestamp) -> pd.DataFrame:
    moved = lines.loc[mask].copy()
    moved["date"] = [bday(max(d + pd.Timedelta(days=days), floor)) for d in moved["date"]]
    return pd.concat([lines.loc[~mask], moved], ignore_index=True)


def _split_shift(lines, mask, share, days, floor) -> pd.DataFrame:
    """Move `share` of the matching lines' cash `days` later; leave the rest in place."""
    part = lines.loc[mask].copy()
    part["amount_usd"] *= share
    part["date"] = [bday(d + pd.Timedelta(days=days)) for d in part["date"]]
    stay = lines.copy()
    stay.loc[mask, "amount_usd"] *= 1 - share
    return pd.concat([stay, part], ignore_index=True)


def _accelerate(
    lines: pd.DataFrame, shock: dict[str, Any], ctx: dict[str, Any], rank: int
) -> pd.DataFrame:
    start = ctx["start"]
    p = ctx["pipeline"].sort_values("arr_usd", ascending=False)
    if rank - 1 >= len(p):
        return lines
    opp = p.iloc[rank - 1]
    # Rebuild the deal's cash from its new close date at 100% (its base cash may sit
    # entirely beyond the horizon, so shifting existing lines is not enough).
    out = lines[lines["source_id"] != opp["opportunity_id"]]
    n = {"annual": 1, "quarterly": 4, "monthly": 12}[opp["billing_freq"]]
    close = max(opp["expected_close"] - pd.Timedelta(days=int(shock["advance_days"])), start)
    lag = ctx["arch_terms"].get(opp["archetype"], 30) + ctx["arch_late"].get(opp["archetype"], 5)
    rows = []
    for j in range(n):
        issue = close + pd.DateOffset(months=j * (12 // n))
        rows.append(
            dict(
                date=bday(issue + pd.Timedelta(days=float(lag))),
                category="customer_collections_new_bookings",
                amount_usd=opp["arr_usd"] / n,
                source_type="opportunity",
                source_id=opp["opportunity_id"],
                customer_id=opp.get("customer_id"),
                note=f"accelerated {shock['advance_days']}d, p=1.0",
            )
        )
    return pd.concat([out, pd.DataFrame(rows, columns=LINE_COLS)], ignore_index=True)


def apply_shock(lines: pd.DataFrame, shock: dict[str, Any], ctx: dict[str, Any]) -> pd.DataFrame:
    t, start = shock["type"], ctx["start"]
    cat = lines["category"]
    if t == "renewal_slip":
        return _split_shift(
            lines,
            cat == "customer_collections_renewals",
            shock["pct_arr"],
            int(shock["delay_days"]),
            start,
        )
    if t == "churn":
        out = lines.copy()
        out.loc[cat == "customer_collections_renewals", "amount_usd"] *= (
            1 - shock["pct_renewals_lost"]
        )
        return out
    if t == "customer_delay":
        target = shock["target"]
        ids = {"top_whale": ctx["whales"][:1], "top_whales": ctx["whales"]}.get(target, [target])
        return _shift(
            lines,
            lines["customer_id"].isin(ids) & cat.isin(RECEIPTS),
            int(shock["delay_days"]),
            start,
        )
    if t == "collections_delay":
        return _shift(lines, cat.isin(RECEIPTS), int(shock["delay_days"]), start)
    if t == "pipeline_accelerate":
        ranks = shock["deal_rank"] if isinstance(shock["deal_rank"], list) else [shock["deal_rank"]]
        for rank in ranks:
            lines = _accelerate(lines, shock, ctx, int(rank))
        return lines
    if t == "payroll_adjust":
        eff = start + pd.Timedelta(weeks=int(shock["effective_week"]) - 1)
        out = lines.copy()
        m = cat.isin(["payroll_net", "payroll_taxes_benefits"]) & (lines["date"] >= eff)
        out.loc[m, "amount_usd"] *= 1 + shock["pct_change"]
        return out
    if t == "one_off":
        row = dict(
            date=bday(pd.Timestamp(shock["date"])),
            category=shock["category"],
            amount_usd=float(shock["amount_usd"]),
            source_type="scenario",
            source_id="one_off",
            customer_id=None,
            note=shock.get("note", "one-off"),
        )
        return pd.concat([lines, pd.DataFrame([row], columns=LINE_COLS)], ignore_index=True)
    raise ValueError(t)


def liquidity(min_cash: float, company: dict, floor: float) -> dict[str, Any]:
    bs = company["balance_sheet"]
    rv = bs["revolver"]
    available = rv["limit"] - rv["drawn"]
    covenant = bs["covenants"]["min_liquidity"]
    shortfall = max(0.0, floor - min_cash)
    draw = min(available, math.ceil(shortfall / 1e6) * 1e6) if shortfall else 0.0
    return {
        "covenant_headroom_usd": round(min_cash - covenant, 2),
        "floor_headroom_usd": round(min_cash - floor, 2),
        "revolver_available_usd": float(available),
        "total_liquidity_at_low_point_usd": round(min_cash + available, 2),
        "suggested_revolver_draw_usd": float(draw),
    }


def run_scenarios(
    base: ForecastResult,
    data: dict[str, pd.DataFrame],
    names: list[str] | None = None,
    custom: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    settings = load_forecast_settings()
    company = load_yaml("company.yaml")
    defs = {k: v["shocks"] for k, v in load_yaml("scenarios.yaml")["scenarios"].items()}
    descs = {k: v["description"] for k, v in load_yaml("scenarios.yaml")["scenarios"].items()}
    chosen = {n: defs[n] for n in (names or list(defs))}
    for n, shocks in (custom or {}).items():
        chosen[n], descs[n] = shocks, "custom"
    start, end = base.as_of, pd.Timestamp(base.summary["horizon_end"])
    cust = data["customers"]
    whales = list(cust[cust["is_whale"]].sort_values("arr", ascending=False)["customer_id"])
    ctx = {
        "start": start,
        "whales": whales,
        "pipeline": data["pipeline"],
        "arch_terms": cust.groupby("archetype")["terms_days"].median().to_dict(),
        "arch_late": base.assumptions["receipts"]["archetype_days_late"],
    }
    floor = settings.min_cash_threshold
    covenant = company["balance_sheet"]["covenants"]["min_liquidity"]
    base_end = base.summary["ending_cash_usd"]

    results: dict[str, Any] = {}
    weekly_closing = {}
    for name, shocks in chosen.items():
        validate_shocks(shocks)
        lines = base.lines.copy()
        for s in shocks:
            lines = apply_shock(lines, s, ctx)
        lines = lines[(lines["date"] >= start) & (lines["date"] <= end)]
        daily = daily_rollforward(lines, base.summary["opening_cash_usd"], start, end)
        weekly = weekly_view(lines, daily, start, settings.horizon_weeks).set_index("line")
        weeks = [c for c in weekly.columns if c.startswith("W")]
        low = daily.loc[daily["closing_balance_usd"].idxmin()]
        flags = []
        for w in weeks:
            m = float(weekly.loc["Minimum daily cash", w])
            if m < covenant:
                flags.append({"week": w, "level": "covenant_breach", "min_cash_usd": round(m, 2)})
            elif m < floor:
                flags.append(
                    {"week": w, "level": "below_internal_floor", "min_cash_usd": round(m, 2)}
                )
        ending = float(daily["closing_balance_usd"].iloc[-1])
        results[name] = {
            "description": descs[name],
            "shocks": shocks,
            "ending_cash_usd": round(ending, 2),
            "change_vs_base_usd": round(ending - base_end, 2),
            "min_cash_usd": round(float(low["closing_balance_usd"]), 2),
            "min_cash_date": str(low["date"].date()),
            "flags": flags,
            **liquidity(float(low["closing_balance_usd"]), company, floor),
        }
        weekly_closing[name] = weekly.loc["Closing cash", weeks].round(2).to_dict()
    return {
        "as_of": str(start.date()),
        "scenarios": results,
        "weekly_closing": weekly_closing,
        "note": "Interest income is held at the base forecast in all scenarios.",
    }
