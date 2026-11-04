"""Daily cash roll-forward, interest income, and the weekly / daily views."""

from __future__ import annotations

import pandas as pd

from cashforecast.config import load_yaml
from cashforecast.synthetic._util import bday


def category_order() -> tuple[list[str], dict[str, str]]:
    """Display order and section for every category, from config/categories.yaml."""
    c = load_yaml("categories.yaml")
    order, section = [], {}
    for cat in c["receipts"]:
        order.append(cat)
        section[cat] = "receipts"
    for grp in ("operating", "non_operating"):
        for cat in c["disbursements"][grp]:
            order.append(cat)
            section[cat] = f"disbursements_{grp}"
    for cat in c["financing"]:
        order.append(cat)
        section[cat] = "financing"
    return order, section


def daily_rollforward(
    lines: pd.DataFrame, opening: float, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    flows = lines.groupby("date")["amount_usd"].sum().reindex(days, fill_value=0.0)
    out = pd.DataFrame({"date": days, "net_flow_usd": flows.to_numpy()})
    out["closing_balance_usd"] = opening + out["net_flow_usd"].cumsum()
    out["opening_balance_usd"] = out["closing_balance_usd"] - out["net_flow_usd"]
    return out[["date", "opening_balance_usd", "net_flow_usd", "closing_balance_usd"]]


def add_interest(
    lines: pd.DataFrame,
    opening: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    history: pd.DataFrame,
    rate: float,
) -> pd.DataFrame:
    """Interest on each month's average balance, posted the next business day.

    Months that straddle the cutoff blend actual history balances with projected ones.
    """
    hist = history.set_index("date")["closing_balance_usd"]
    for m in pd.period_range(start.to_period("M") - 1, end.to_period("M"), freq="M"):
        post = bday((m + 1).start_time)
        if post < start or post > end:
            continue
        proj = daily_rollforward(lines, opening, start, end).set_index("date")[
            "closing_balance_usd"
        ]
        days = pd.date_range(m.start_time, m.end_time.normalize(), freq="D")
        bal = pd.concat([hist, proj]).reindex(days).dropna()
        if bal.empty:
            continue
        amount = float(bal.mean()) * rate / 12
        lines = pd.concat(
            [
                lines,
                pd.DataFrame(
                    [
                        dict(
                            date=post,
                            category="interest_income",
                            amount_usd=amount,
                            source_type="bank",
                            source_id=f"INT:{m}",
                            customer_id=None,
                            note=f"{rate:.1%} on {m} avg balance",
                        )
                    ]
                ),
            ],
            ignore_index=True,
        )
    return lines


def weekly_view(
    lines: pd.DataFrame, daily: pd.DataFrame, start: pd.Timestamp, weeks: int
) -> pd.DataFrame:
    """Category x week table with section subtotals, opening/closing and minimum balance."""
    order, section = category_order()
    lines = lines.assign(week=(lines["date"] - start).dt.days // 7 + 1)
    daily = daily.assign(week=(daily["date"] - start).dt.days // 7 + 1)
    pivot = lines.pivot_table(
        index="category", columns="week", values="amount_usd", aggfunc="sum", fill_value=0.0
    )
    pivot = pivot.reindex(columns=range(1, weeks + 1), fill_value=0.0)
    pivot = pivot.reindex([c for c in order if c in pivot.index or c in section]).fillna(0.0)
    rows = []
    for sec, label in [
        ("receipts", "Total receipts"),
        ("disbursements_operating", "Total operating disbursements"),
        ("disbursements_non_operating", "Total non-operating disbursements"),
        ("financing", "Total financing"),
    ]:
        cats = [c for c in order if section[c] == sec]
        for cat in cats:
            rows.append((sec, cat, pivot.loc[cat]))
        rows.append((sec, label, pivot.loc[cats].sum()))
    by_week = daily.groupby("week")
    rows.append(("summary", "Net cash flow", pivot.sum()))
    rows.append(("summary", "Opening cash", by_week["opening_balance_usd"].first()))
    rows.append(("summary", "Closing cash", by_week["closing_balance_usd"].last()))
    rows.append(("summary", "Minimum daily cash", by_week["closing_balance_usd"].min()))
    out = pd.DataFrame([r[2].rename(None) for r in rows])
    out.insert(0, "line", [r[1] for r in rows])
    out.insert(0, "section", [r[0] for r in rows])
    out.columns = ["section", "line"] + [f"W{w}" for w in range(1, weeks + 1)]
    week_ends = [start + pd.Timedelta(days=7 * w - 1) for w in range(1, weeks + 1)]
    out.attrs["week_ending"] = {f"W{w}": str(d.date()) for w, d in enumerate(week_ends, 1)}
    return out.reset_index(drop=True)


def daily_view(
    lines: pd.DataFrame, daily: pd.DataFrame, start: pd.Timestamp, days: int
) -> pd.DataFrame:
    """Weeks 1-2 at daily grain: receipts, disbursements, net flow, closing balance."""
    _, section = category_order()
    window = daily[daily["date"] < start + pd.Timedelta(days=days)].copy()
    sec = lines.assign(section=lines["category"].map(section))
    rec = sec[sec["section"] == "receipts"].groupby("date")["amount_usd"].sum()
    dis = sec[sec["section"].str.startswith("disbursements")].groupby("date")["amount_usd"].sum()
    window["receipts_usd"] = window["date"].map(rec).fillna(0.0)
    window["disbursements_usd"] = window["date"].map(dis).fillna(0.0)
    return window[
        [
            "date",
            "opening_balance_usd",
            "receipts_usd",
            "disbursements_usd",
            "net_flow_usd",
            "closing_balance_usd",
        ]
    ].reset_index(drop=True)
