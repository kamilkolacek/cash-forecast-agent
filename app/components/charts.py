"""Plotly charts with one consistent look."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

INK = "#1F3864"
POS = "#2E7D32"
NEG = "#C62828"
MUTED = "#9E9E9E"
FLOOR = "#EF6C00"
COVENANT = "#B71C1C"
SERIES = ["#1F3864", "#C62828", "#6A1B9A", "#EF6C00", "#2E7D32", "#00838F", "#5D4037", "#9E9E9E"]


def _layout(fig: go.Figure, title: str = "", height: int = 380, yaxis: str = "$M") -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(size=15)),
        height=height,
        margin=dict(l=10, r=10, t=50, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        yaxis=dict(
            title=yaxis,
            gridcolor="rgba(128,128,128,0.2)",
            zeroline=True,
            zerolinecolor="rgba(128,128,128,0.4)",
        ),
    )
    return fig


def threshold_lines(fig: go.Figure, floor: float, covenant: float) -> go.Figure:
    fig.add_hline(
        y=floor / 1e6,
        line_dash="dash",
        line_color=FLOOR,
        annotation_text=f"Floor ${floor / 1e6:.0f}M",
        annotation_position="top left",
    )
    fig.add_hline(
        y=covenant / 1e6,
        line_dash="dot",
        line_color=COVENANT,
        annotation_text=f"Covenant ${covenant / 1e6:.0f}M",
        annotation_position="bottom left",
    )
    return fig


def cash_bars_and_balance(
    labels: list[str], receipts, disbursements, closing, title: str = ""
) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=labels,
        y=[v / 1e6 for v in receipts],
        name="Receipts",
        marker_color=POS,
        hovertemplate="%{y:$,.1f}M",
    )
    fig.add_bar(
        x=labels,
        y=[v / 1e6 for v in disbursements],
        name="Disbursements",
        marker_color=NEG,
        hovertemplate="%{y:$,.1f}M",
    )
    fig.add_scatter(
        x=labels,
        y=[v / 1e6 for v in closing],
        name="Closing cash",
        mode="lines+markers",
        line=dict(color=INK, width=3),
        yaxis="y2",
        hovertemplate="%{y:$,.1f}M",
    )
    fig.update_layout(
        barmode="relative",
        yaxis2=dict(
            title="Closing cash $M",
            overlaying="y",
            side="right",
            showgrid=False,
            rangemode="tozero",
        ),
    )
    return _layout(fig, title, yaxis="Flows $M")


def balance_lines(
    series: dict[str, pd.Series], floor: float, covenant: float, title: str = ""
) -> go.Figure:
    fig = go.Figure()
    for i, (name, s) in enumerate(series.items()):
        fig.add_scatter(
            x=list(s.index),
            y=(s / 1e6).tolist(),
            name=name,
            mode="lines",
            line=dict(
                color=SERIES[i % len(SERIES)],
                width=3 if i == 0 else 2,
                dash="solid" if i == 0 else "dash",
            ),
            hovertemplate="%{y:$,.1f}M",
        )
    return _layout(threshold_lines(fig, floor, covenant), title)


def waterfall(labels: list[str], values: list[float], title: str = "") -> go.Figure:
    measures = ["absolute"] + ["relative"] * (len(values) - 2) + ["total"]
    fig = go.Figure(
        go.Waterfall(
            x=labels,
            y=[v / 1e6 for v in values],
            measure=measures,
            increasing=dict(marker_color=POS),
            decreasing=dict(marker_color=NEG),
            totals=dict(marker_color=INK),
            connector=dict(line=dict(color=MUTED)),
            texttemplate="%{y:$,.2f}M",
            textposition="outside",
            hovertemplate="%{y:$,.2f}M",
        )
    )
    return _layout(fig, title, height=420)


def grouped_bars(
    x: list[str],
    series: dict[str, list[float]],
    title: str = "",
    yaxis: str = "$M",
    scale: float = 1e6,
    fmt: str = "%{y:$,.1f}M",
) -> go.Figure:
    fig = go.Figure()
    for i, (name, vals) in enumerate(series.items()):
        fig.add_bar(
            x=x,
            y=[v / scale for v in vals],
            name=name,
            marker_color=SERIES[i % len(SERIES)],
            hovertemplate=fmt,
        )
    fig.update_layout(barmode="group")
    return _layout(fig, title, yaxis=yaxis)
