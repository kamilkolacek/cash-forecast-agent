"""Write run artifacts and the facts sheet the memo is written from."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cashforecast.engine.forecast import ForecastResult
from cashforecast.engine.variance import VarianceResult


def _dump(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str))


def write_forecast(res: ForecastResult, out_root: Path) -> Path:
    run_id = f"{res.as_of:%Y-%m-%d}_{datetime.now():%Y%m%dT%H%M%S}"
    run_dir = Path(out_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    _dump(run_dir / "summary.json", {"run_id": run_id, **res.summary})
    _dump(run_dir / "assumptions.json", res.assumptions)
    res.weekly.round(2).to_csv(run_dir / "weekly.csv", index=False)
    detail = res.daily_detail.copy()
    num = detail.select_dtypes("number").columns
    detail[num] = detail[num].round(2)
    detail.to_csv(run_dir / "daily_detail.csv", index=False)
    res.daily.to_parquet(run_dir / "daily.parquet", index=False)
    res.lines.to_parquet(run_dir / "lines.parquet", index=False)
    (Path(out_root) / "LATEST").write_text(run_id)
    return run_dir


def latest_run(out_root: Path) -> Path | None:
    marker = Path(out_root) / "LATEST"
    return Path(out_root) / marker.read_text().strip() if marker.exists() else None


def write_variance(run_dir: Path, v: VarianceResult, top: int = 15) -> None:
    _dump(
        run_dir / "variance.json",
        {
            "summary": v.summary,
            "top_drivers": v.drivers.head(top).to_dict("records"),
            "by_category": v.by_category.to_dict("records"),
        },
    )
    v.drivers.to_csv(run_dir / "variance_drivers.csv", index=False)


def write_scenarios(run_dir: Path, s: dict[str, Any]) -> None:
    path = run_dir / "scenarios.json"
    if path.exists():  # merge so a single /scenario run doesn't drop the others
        old = json.loads(path.read_text())
        old["scenarios"].update(s["scenarios"])
        old["weekly_closing"].update(s["weekly_closing"])
        s = old
    _dump(path, s)
    pd.DataFrame(s["weekly_closing"]).to_csv(run_dir / "scenarios_weekly.csv", index_label="week")


def write_validation(run_dir: Path, report: dict[str, Any]) -> None:
    _dump(run_dir / "validation.json", report)


# ---------------------------------------------------------------- facts sheet


def m(x: float) -> str:
    """$ millions, one decimal, sign preserved: -$3.3M."""
    return f"{'-' if x < 0 else ''}${abs(x) / 1e6:,.1f}M"


def k(x: float) -> str:
    return f"{'-' if x < 0 else ''}${abs(x) / 1e3:,.0f}K"


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def write_facts(run_dir: Path) -> Path:
    """Pre-formatted figures for the memo. Everything here derives from the run's JSON/CSV,
    so the traceability check accepts any figure on this sheet."""
    s = json.loads((run_dir / "summary.json").read_text())
    a = json.loads((run_dir / "assumptions.json").read_text())
    w = pd.read_csv(run_dir / "weekly.csv").set_index("line")
    weeks = [c for c in w.columns if c.startswith("W")]
    out = [
        f"# Facts sheet: run {s['run_id']}",
        "",
        "Cite figures from this sheet as written. All values in USD.",
        "",
        "## Headline",
        "",
    ]
    floor, cov = s["min_cash_threshold_usd"], s["covenant_min_liquidity_usd"]
    rows = [
        ("Forecast horizon", f"{s['as_of']} to {s['horizon_end']} (13 weeks)"),
        ("Opening cash", m(s["opening_cash_usd"])),
        ("Total receipts", m(s["total_receipts_usd"])),
        ("Total disbursements", m(s["total_disbursements_usd"])),
        ("Ending cash", m(s["ending_cash_usd"])),
        ("Net change over horizon", m(s["ending_cash_usd"] - s["opening_cash_usd"])),
        ("Minimum cash", f"{m(s['min_cash_usd'])} on {s['min_cash_date']}"),
        ("Internal floor", m(floor)),
        ("Covenant minimum liquidity", m(cov)),
        ("Headroom to floor at low point", m(s["min_cash_usd"] - floor)),
        ("Headroom to covenant at low point", m(s["min_cash_usd"] - cov)),
        ("Flagged weeks", ", ".join(f"{f['week']} ({f['level']})" for f in s["flags"]) or "none"),
    ]
    out += ["| Item | Value |", "|---|---|"] + [f"| {r[0]} | {r[1]} |" for r in rows]

    out += [
        "",
        "## Weekly view",
        "",
        "| Week | Week ending | Receipts | Disbursements | Net flow | Closing cash |",
        "|---|---|---|---|---|---|",
    ]
    for wk in weeks:
        dis = (
            w.loc["Total operating disbursements", wk]
            + w.loc["Total non-operating disbursements", wk]
        )
        out.append(
            f"| {wk} | {s['week_ending'][wk]} | {m(w.loc['Total receipts', wk])} | {m(dis)} "
            f"| {m(w.loc['Net cash flow', wk])} | {m(w.loc['Closing cash', wk])} |"
        )

    cats = w[~w.index.str.startswith(("Total", "Net", "Opening", "Closing", "Minimum"))]
    totals = cats[weeks].sum(axis=1)
    totals = totals[totals.abs() > 0].sort_values(key=abs, ascending=False)
    out += [
        "",
        "## 13-week totals by category (largest first)",
        "",
        "| Category | 13-week total |",
        "|---|---|",
    ]
    out += [f"| {c} | {m(v)} |" for c, v in totals.items()]

    vpath = run_dir / "variance.json"
    if vpath.exists():
        v = json.loads(vpath.read_text())
        vs = v["summary"]
        out += [
            "",
            f"## Variance: prior forecast vs actuals, {vs['window']}",
            "",
            "| Item | Value |",
            "|---|---|",
            f"| Forecast closing cash | {m(vs['forecast_closing_cash_usd'])} |",
            f"| Actual closing cash | {m(vs['actual_closing_cash_usd'])} |",
            f"| Total variance (+ favorable) | {m(vs['total_variance_usd'])} |",
            f"| Timing | {m(vs['timing_usd'])} |",
            f"| Permanent | {m(vs['permanent_usd'])} |",
            f"| Receipts variance | {m(vs['receipts_variance_usd'])} |",
            f"| Disbursements variance | {m(vs['disbursements_variance_usd'])} |",
            f"| Prior forecast cash at {vs['comparison_end']} "
            f"| {m(vs['prior_forecast_cash_at_comparison_end_usd'])} |",
            f"| Revised forecast cash at {vs['comparison_end']} "
            f"| {m(vs['revised_cash_at_comparison_end_usd'])} |",
            f"| Permanent means | {vs['permanent_definition']} |",
            "",
            "Top drivers:",
            "",
            "| Driver | Type | Whale | Forecast | Actual | Variance | Timing | Permanent | Class |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for d in v["top_drivers"][:8]:
            out.append(
                f"| {d['driver']} | {d['type']} | {'yes' if d['is_whale'] else ''} "
                f"| {k(d['forecast_window'])} | {k(d['actual_window'])} | {k(d['variance'])} "
                f"| {k(d['timing'])} | {k(d['permanent'])} | {d['classification']} |"
            )

    spath = run_dir / "scenarios.json"
    if spath.exists():
        sc = json.loads(spath.read_text())["scenarios"]
        out += [
            "",
            "## Scenarios",
            "",
            "| Scenario | Description | Ending cash | vs base | Minimum cash | Min date "
            "| Floor headroom | Suggested revolver draw | Flags |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for n, r in sc.items():
            out.append(
                f"| {n} | {r['description']} | {m(r['ending_cash_usd'])} "
                f"| {m(r['change_vs_base_usd'])} | {m(r['min_cash_usd'])} | {r['min_cash_date']} "
                f"| {m(r['floor_headroom_usd'])} | {m(r['suggested_revolver_draw_usd'])} "
                f"| {len(r['flags'])} |"
            )
        rv = next(iter(sc.values()))["revolver_available_usd"]
        out.append(f"\nUndrawn revolver available: {m(rv)}")

    vpath2 = run_dir / "validation.json"
    if vpath2.exists():
        val = json.loads(vpath2.read_text())
        out += ["", "## Data findings", ""]
        for f in val["findings"]:
            if f["severity"] != "ERROR" and (not f["passed"] or f["severity"] == "INFO"):
                out.append(f"- [{f['severity']}] {f['check']}: {f['detail']}")

    r = a["receipts"]["renewal_rates"]
    out += ["", "## Key assumptions", "", "| Assumption | Value |", "|---|---|"]
    for arch in sorted(r["churn"]):
        out.append(f"| Renewal churn, {arch} | {pct(r['churn'][arch])} |")
    for arch in sorted(r["expansion"]):
        out.append(f"| Expansion on renewal, {arch} | {pct(r['expansion'][arch])} |")
    out.append(f"| Renewal billing delay | {r['renewal_billing_delay_days']} days |")
    for arch, d in sorted(a["receipts"]["archetype_days_late"].items()):
        out.append(f"| Avg days paid after due, {arch} | {d} days |")
    for ent, p in a["disbursements"]["payroll_per_run_usd"].items():
        out.append(f"| Payroll per run, {ent} | {m(p['net_pay'] + p['taxes_benefits'])} |")
    for cat, info in a["disbursements"]["ap"].items():
        out.append(f"| AP monthly run rate, {cat} | {m(info['monthly_run_rate'])} |")
        for month, f in info["seasonality"].items():
            if abs(f - 1) >= 0.2:
                out.append(f"| AP seasonality, {cat} {month} | {f:.2f}x |")
    out.append(f"| Capex average slippage | {a['disbursements']['capex_avg_slippage_days']} days |")
    path = run_dir / "facts.md"
    path.write_text("\n".join(out) + "\n")
    return path
