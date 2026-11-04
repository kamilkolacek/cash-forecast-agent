"""Formatting and KPI helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def m(x: float, decimals: int = 1) -> str:
    return f"{'-' if x < 0 else ''}${abs(x) / 1e6:,.{decimals}f}M"


def kpi_row(items: list[tuple[str, str, str | None]]) -> None:
    """items: (label, value, delta or None)."""
    cols = st.columns(len(items))
    for col, (label, value, delta) in zip(cols, items, strict=True):
        col.metric(label, value, delta)


def money_table(df: pd.DataFrame, money_cols: list[str], decimals: int = 1) -> pd.DataFrame:
    """Display copy with $M formatting (keeps the source frame numeric)."""
    out = df.copy()
    for c in money_cols:
        out[c] = out[c].map(lambda v: m(v, decimals) if pd.notna(v) else "")
    return out


def status_badge(min_cash: float, floor: float, covenant: float) -> None:
    if min_cash < covenant:
        st.error(f"Covenant breach: minimum cash {m(min_cash)} vs covenant {m(covenant)}")
    elif min_cash < floor:
        st.warning(f"Below internal floor: minimum cash {m(min_cash)} vs floor {m(floor)}")
    else:
        st.success(
            f"Within limits: low point {m(min_cash)} is {m(min_cash - floor)} above "
            f"the floor and {m(min_cash - covenant)} above the covenant"
        )
