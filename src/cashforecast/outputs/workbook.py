"""Excel workbook for a forecast run.

Engine outputs are written as blue inputs; totals, net flow and the cash roll-forward are
live formulas in black; links between sheets are green. A reader can change a forecast
line and the workbook re-balances itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

FONT = "Arial"
BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
MONEY = '$#,##0;($#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
SECTION_FILL = PatternFill("solid", fgColor="D9E1F2")
INPUT_FILL = PatternFill("solid", fgColor="FFFF00")
THIN = Side(style="thin", color="808080")
SECTION_LABELS = {
    "receipts": "Receipts",
    "disbursements_operating": "Operating disbursements",
    "disbursements_non_operating": "Non-operating disbursements",
    "financing": "Financing",
}


def _font(color: str = BLACK, bold: bool = False, size: int = 10, white: bool = False) -> Font:
    return Font(name=FONT, size=size, bold=bold, color="FFFFFF" if white else color)


def _header(ws: Worksheet, row: int, labels: list[str], col: int = 1) -> None:
    for i, label in enumerate(labels):
        c = ws.cell(row=row, column=col + i, value=label)
        c.font = _font(bold=True, white=True)
        c.fill = HEADER_FILL
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _set(ws, row, col, value, color=BLACK, fmt=None, bold=False):
    c = ws.cell(row=row, column=col, value=value)
    c.font = _font(color, bold)
    if fmt:
        c.number_format = fmt
    return c


def _title(ws: Worksheet, text: str, sub: str) -> None:
    ws["A1"] = text
    ws["A1"].font = _font(bold=True, size=14)
    ws["A2"] = sub
    ws["A2"].font = _font(size=9, color="595959")


def _widths(ws: Worksheet, widths: dict[str, float]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


# ------------------------------------------------------------------ 13-week sheet


def _forecast_sheet(wb: Workbook, weekly: pd.DataFrame, s: dict) -> dict[str, str]:
    """Returns cell addresses other sheets link to."""
    ws = wb.create_sheet("13-Week Forecast")
    weeks = [c for c in weekly.columns if c.startswith("W")]
    n = len(weeks)
    _title(
        ws,
        "13-Week Cash Forecast ($)",
        f"{s['as_of']} to {s['horizon_end']}. Blue = engine forecast (editable); "
        "black = formula; totals and roll-forward recalculate.",
    )
    _header(ws, 4, ["Line"] + [f"{w}\n{s['week_ending'][w]}" for w in weeks] + ["13-week total"])
    ws.row_dimensions[4].height = 30
    first_col, last_col = 2, 1 + n
    tot_col = last_col + 1
    L = get_column_letter

    row = 5
    section_total_rows: dict[str, int] = {}
    body = weekly[weekly["section"] != "summary"]
    for sec in SECTION_LABELS:
        rows = body[(body["section"] == sec) & ~body["line"].str.startswith("Total")]
        c = ws.cell(row=row, column=1, value=SECTION_LABELS[sec])
        c.font = _font(bold=True)
        for col in range(1, tot_col + 1):
            ws.cell(row=row, column=col).fill = SECTION_FILL
        row += 1
        start = row
        for _, r in rows.iterrows():
            _set(ws, row, 1, r["line"].replace("_", " "))
            for j, w in enumerate(weeks):
                _set(ws, row, first_col + j, round(float(r[w]), 2), BLUE, MONEY)
            _set(ws, row, tot_col, f"=SUM({L(first_col)}{row}:{L(last_col)}{row})", fmt=MONEY)
            row += 1
        end = row - 1
        _set(ws, row, 1, f"Total {SECTION_LABELS[sec].lower()}", bold=True)
        for col in range(first_col, tot_col + 1):
            c = _set(ws, row, col, f"=SUM({L(col)}{start}:{L(col)}{end})", fmt=MONEY, bold=True)
            c.border = Border(top=THIN)
        section_total_rows[sec] = row
        row += 2

    net, opening, closing, minimum = row, row + 1, row + 2, row + 3
    _set(ws, net, 1, "Net cash flow", bold=True)
    _set(ws, opening, 1, "Opening cash", bold=True)
    _set(ws, closing, 1, "Closing cash", bold=True)
    _set(ws, minimum, 1, "Minimum daily cash (engine)")
    wk = weekly.set_index("line")
    for j, w in enumerate(weeks):
        col = first_col + j
        cl = L(col)
        totals = "+".join(f"{cl}{r}" for r in section_total_rows.values())
        _set(ws, net, col, f"={totals}", fmt=MONEY, bold=True)
        if j == 0:
            c = _set(ws, opening, col, round(s["opening_cash_usd"], 2), BLUE, MONEY, bold=True)
            c.comment = Comment(
                "Actual bank balance at the forecast date (engine input).", "engine"
            )
        else:
            _set(ws, opening, col, f"={L(col - 1)}{closing}", fmt=MONEY, bold=True)
        _set(ws, closing, col, f"={cl}{opening}+{cl}{net}", fmt=MONEY, bold=True)
        _set(ws, minimum, col, round(float(wk.loc["Minimum daily cash", w]), 2), BLUE, MONEY)
    _set(ws, net, tot_col, f"=SUM({L(first_col)}{net}:{L(last_col)}{net})", fmt=MONEY, bold=True)
    for r in (opening, closing, minimum):
        ws.cell(row=r, column=tot_col).value = None
    for col in range(1, tot_col + 1):
        ws.cell(row=closing, column=col).border = Border(top=THIN, bottom=Side(style="double"))

    note = minimum + 2
    _set(
        ws,
        note,
        1,
        "Minimum daily cash is the engine's lowest end-of-day balance within each "
        "week; it does not recalculate if lines are edited.",
    )
    ws.cell(row=note, column=1).font = _font(size=8, color="595959")
    _widths(ws, {"A": 36, **{L(c): 13 for c in range(first_col, tot_col + 1)}})
    ws.freeze_panes = "B5"
    return {
        "opening": f"'13-Week Forecast'!{L(first_col)}{opening}",
        "ending": f"'13-Week Forecast'!{L(last_col)}{closing}",
        "min_range": f"'13-Week Forecast'!{L(first_col)}{minimum}:{L(last_col)}{minimum}",
        "receipts": f"'13-Week Forecast'!{L(tot_col)}{section_total_rows['receipts']}",
        "op": f"'13-Week Forecast'!{L(tot_col)}{section_total_rows['disbursements_operating']}",
        "nonop": f"'13-Week Forecast'!{L(tot_col)}"
        f"{section_total_rows['disbursements_non_operating']}",
        "fin": f"'13-Week Forecast'!{L(tot_col)}{section_total_rows['financing']}",
    }


# ------------------------------------------------------------------ other sheets


def _summary_sheet(wb: Workbook, s: dict, links: dict[str, str]) -> None:
    ws = wb.active
    ws.title = "Summary"
    _title(
        ws,
        "Northwind Cloud, Inc.: Cash Forecast Summary",
        f"Run {s['run_id']}. Synthetic data. Green = linked from the forecast sheet; "
        "blue on yellow = thresholds you can change.",
    )
    _header(ws, 4, ["Item", "Value ($)"])
    rows = [
        ("Forecast start", s["as_of"], None, None),
        ("Forecast end", s["horizon_end"], None, None),
        ("Opening cash", f"={links['opening']}", GREEN, MONEY),
        ("Total receipts", f"={links['receipts']}", GREEN, MONEY),
        ("Total operating disbursements", f"={links['op']}", GREEN, MONEY),
        ("Total non-operating disbursements", f"={links['nonop']}", GREEN, MONEY),
        ("Ending cash", f"={links['ending']}", GREEN, MONEY),
        ("Net change", "=B11-B7", BLACK, MONEY),
        ("Minimum daily cash", f"=MIN({links['min_range']})", GREEN, MONEY),
        ("Minimum cash date (engine)", s["min_cash_date"], BLUE, None),
        ("Internal floor", s["min_cash_threshold_usd"], BLUE, MONEY),
        ("Covenant minimum liquidity", s["covenant_min_liquidity_usd"], BLUE, MONEY),
        ("Headroom to floor", "=B13-B15", BLACK, MONEY),
        ("Headroom to covenant", "=B13-B16", BLACK, MONEY),
        (
            "Status",
            '=IF(B13<B16,"COVENANT BREACH",IF(B13<B15,"Below internal floor","OK"))',
            BLACK,
            None,
        ),
    ]
    for i, (label, value, color, fmt) in enumerate(rows, start=5):
        _set(ws, i, 1, label)
        c = _set(ws, i, 2, value, color or BLACK, fmt)
        if label in ("Internal floor", "Covenant minimum liquidity"):
            c.fill = INPUT_FILL
    ws["B19"].font = _font(bold=True)
    _set(ws, 21, 1, "Check: opening + flows = ending")
    _set(ws, 21, 2, f'=IF(ABS(B7+B8+B9+B10+{links["fin"]}-B11)<1,"OK","ERROR")')
    _widths(ws, {"A": 36, "B": 22})


def _daily_sheet(wb: Workbook, daily: pd.DataFrame) -> None:
    ws = wb.create_sheet("Daily (Wks 1-2)")
    _title(
        ws,
        "Daily cash, weeks 1-2 ($)",
        "Receipts and disbursements from the engine (blue); net flow and balances are formulas.",
    )
    _header(ws, 4, ["Date", "Day", "Opening", "Receipts", "Disbursements", "Net flow", "Closing"])
    for i, r in enumerate(daily.itertuples(), start=5):
        d = pd.Timestamp(r.date)
        _set(ws, i, 1, d.to_pydatetime(), fmt="yyyy-mm-dd")
        _set(ws, i, 2, d.strftime("%a"))
        if i == 5:
            _set(ws, i, 3, round(r.opening_balance_usd, 2), BLUE, MONEY)
        else:
            _set(ws, i, 3, f"=G{i - 1}", fmt=MONEY)
        _set(ws, i, 4, round(r.receipts_usd, 2), BLUE, MONEY)
        _set(ws, i, 5, round(r.disbursements_usd, 2), BLUE, MONEY)
        _set(ws, i, 6, f"=D{i}+E{i}", fmt=MONEY)
        _set(ws, i, 7, f"=C{i}+F{i}", fmt=MONEY, bold=True)
    _widths(ws, {"A": 12, "B": 6, "C": 15, "D": 15, "E": 15, "F": 15, "G": 15})
    ws.freeze_panes = "A5"


def _variance_sheet(wb: Workbook, v: dict) -> None:
    ws = wb.create_sheet("Variance")
    vs = v["summary"]
    _title(
        ws,
        f"Forecast vs actual: {vs['window']} ($)",
        f"Permanent = {vs['permanent_definition']}. Positive = favorable to cash.",
    )
    _header(ws, 4, ["Item", "Value"])
    items = [
        ("Forecast closing cash", vs["forecast_closing_cash_usd"]),
        ("Actual closing cash", vs["actual_closing_cash_usd"]),
        ("Total variance", "=B6-B5"),
        ("Timing", vs["timing_usd"]),
        ("Permanent", vs["permanent_usd"]),
        ("Check: timing + permanent = variance", '=IF(ABS(B8+B9-B7)<1,"OK","ERROR")'),
    ]
    for i, (label, val) in enumerate(items, start=5):
        _set(ws, i, 1, label)
        _set(
            ws,
            i,
            2,
            val,
            BLUE if isinstance(val, int | float) else BLACK,
            None if label.startswith("Check") else MONEY,
        )
    top = 13
    _header(
        ws,
        top,
        [
            "Driver",
            "Type",
            "Whale",
            "Forecast",
            "Actual",
            "Variance",
            "Timing",
            "Permanent",
            "Class",
            "Forecast basis",
        ],
    )
    for i, d in enumerate(v["top_drivers"], start=top + 1):
        _set(ws, i, 1, d["driver"])
        _set(ws, i, 2, d["type"])
        _set(ws, i, 3, "yes" if d["is_whale"] else "")
        _set(ws, i, 4, d["forecast_window"], BLUE, MONEY)
        _set(ws, i, 5, d["actual_window"], BLUE, MONEY)
        _set(ws, i, 6, f"=E{i}-D{i}", fmt=MONEY)
        _set(ws, i, 7, f"=F{i}-H{i}", fmt=MONEY)
        _set(ws, i, 8, d["permanent"], BLUE, MONEY)
        _set(ws, i, 9, d["classification"])
        _set(ws, i, 10, d["forecast_basis"])
    _widths(ws, {"A": 34, "B": 10, "C": 7, **{c: 14 for c in "DEFGH"}, "I": 11, "J": 60})


def _scenario_sheet(wb: Workbook, sc: dict, floor_ref: str, cov_ref: str) -> None:
    ws = wb.create_sheet("Scenarios")
    _title(
        ws,
        "Scenarios ($)",
        "Engine results (blue). Change vs base and headroom are formulas "
        "linked to the thresholds on Summary.",
    )
    _header(
        ws,
        4,
        [
            "Scenario",
            "Description",
            "Ending cash",
            "Change vs base",
            "Minimum cash",
            "Min date",
            "Floor headroom",
            "Covenant headroom",
            "Suggested revolver draw",
            "Flagged weeks",
        ],
    )
    names = list(sc["scenarios"])
    base_row = 5 + names.index("base") if "base" in names else 5
    for i, name in enumerate(names, start=5):
        r = sc["scenarios"][name]
        _set(ws, i, 1, name, bold=name == "base")
        _set(ws, i, 2, r["description"])
        _set(ws, i, 3, r["ending_cash_usd"], BLUE, MONEY)
        _set(ws, i, 4, f"=C{i}-$C${base_row}", fmt=MONEY)
        _set(ws, i, 5, r["min_cash_usd"], BLUE, MONEY)
        _set(ws, i, 6, r["min_cash_date"])
        _set(ws, i, 7, f"=E{i}-{floor_ref}", GREEN, MONEY)
        _set(ws, i, 8, f"=E{i}-{cov_ref}", GREEN, MONEY)
        _set(ws, i, 9, r["suggested_revolver_draw_usd"], BLUE, MONEY)
        _set(ws, i, 10, len(r["flags"]), BLUE)
    _widths(ws, {"A": 18, "B": 58, **{c: 15 for c in "CDEGHI"}, "F": 12, "J": 9})


def _assumptions_sheet(wb: Workbook, a: dict) -> None:
    ws = wb.create_sheet("Assumptions")
    _title(
        ws,
        "Key assumptions learned by the engine",
        "Source: assumptions.json for this run. Values are what the engine used; "
        "editing them here does not re-run the forecast.",
    )
    _header(ws, 4, ["Assumption", "Value", "Unit"])
    r = a["receipts"]["renewal_rates"]
    rows: list[tuple[str, float | str, str, str | None]] = []
    rows += [(f"Renewal churn, {k}", v, "rate", PCT) for k, v in sorted(r["churn"].items())]
    rows += [
        (f"Expansion on renewal, {k}", v, "rate", PCT) for k, v in sorted(r["expansion"].items())
    ]
    rows.append(("Renewal billing delay", r["renewal_billing_delay_days"], "days", "0.0"))
    rows += [
        (f"Avg days paid after due, {k}", v, "days", "0.0")
        for k, v in sorted(a["receipts"]["archetype_days_late"].items())
    ]
    for ent, p in a["disbursements"]["payroll_per_run_usd"].items():
        rows.append(
            (
                f"Payroll per run (net + taxes), {ent}",
                p["net_pay"] + p["taxes_benefits"],
                "$",
                MONEY,
            )
        )
    for cat, info in a["disbursements"]["ap"].items():
        rows.append((f"AP monthly run rate, {cat}", info["monthly_run_rate"], "$", MONEY))
    rows.append(
        ("Capex average slippage", a["disbursements"]["capex_avg_slippage_days"], "days", "0.0")
    )
    for i, (label, val, unit, fmt) in enumerate(rows, start=5):
        _set(ws, i, 1, label)
        _set(ws, i, 2, val, BLUE, fmt)
        _set(ws, i, 3, unit)
    _widths(ws, {"A": 44, "B": 16, "C": 8})


def write_workbook(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    s = json.loads((run_dir / "summary.json").read_text())
    weekly = pd.read_csv(run_dir / "weekly.csv")
    wb = Workbook()
    links = _forecast_sheet(wb, weekly, s)
    _summary_sheet(wb, s, links)
    wb.move_sheet("Summary", offset=-(len(wb.sheetnames) - 1))
    _daily_sheet(wb, pd.read_csv(run_dir / "daily_detail.csv", parse_dates=["date"]))
    if (run_dir / "variance.json").exists():
        _variance_sheet(wb, json.loads((run_dir / "variance.json").read_text()))
    if (run_dir / "scenarios.json").exists():
        _scenario_sheet(
            wb,
            json.loads((run_dir / "scenarios.json").read_text()),
            "Summary!$B$15",
            "Summary!$B$16",
        )
    _assumptions_sheet(wb, json.loads((run_dir / "assumptions.json").read_text()))
    path = run_dir / f"cash_forecast_{s['as_of']}.xlsx"
    wb.save(path)
    return path
