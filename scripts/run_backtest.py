"""Walk-forward backtest plus scoring of the live forecast against the 13-week holdout.

Usage: python scripts/run_backtest.py [--data DIR] [--out DIR] [--skip-live]

Writes outputs/backtest/<timestamp>/: summary.json, detail.parquet, live_detail.parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from cashforecast.backtest.walk_forward import check_targets, run_backtest, score_live
from cashforecast.config import PROJECT_ROOT, load_forecast_settings, load_yaml
from cashforecast.data.loaders import load_dataset, load_manifest

SHOW = [
    "closing_balance",
    "total_receipts",
    "total_disbursements",
    "customer_receipts",
    "payroll",
    "ap_vendors",
    "other_disbursements",
]


def table(by: dict, rows: list[str]) -> str:
    df = pd.DataFrame(by).T.reindex([r for r in rows if r in by])
    return (df * 100).round(1).astype(str).add("%").to_string()


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "backtest")
    p.add_argument("--skip-live", action="store_true")
    args = p.parse_args()

    weeks = load_forecast_settings().horizon_weeks
    bt_cfg = load_yaml("forecast.yaml")["backtest"]
    data = load_dataset(args.data)
    as_of = pd.Timestamp(load_manifest(args.data)["as_of"])

    detail, summary = run_backtest(data, as_of, weeks, bt_cfg["min_training_weeks"])
    summary["targets"] = check_targets(summary, bt_cfg["targets"])
    out_dir = args.out / datetime.now().strftime("%Y%m%dT%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    detail.to_parquet(out_dir / "detail.parquet", index=False)

    print(
        f"Walk-forward backtest: {summary['cutoffs']} cutoffs, "
        f"{summary['first_cutoff']} to {summary['last_cutoff']}, every 2 weeks"
    )
    print("\nWeekly WAPE (lower is better; naive = trailing 13-week average held flat)")
    print(table(summary["by_group"], SHOW))
    print("\nCumulative-flow WAPE")
    print(table(summary["cumulative"], list(summary["cumulative"])))
    print("\nTargets (closing cash WAPE):")
    for b, t in summary["targets"].items():
        print(
            f"  {b}: {t['engine']:.1%} vs target {t['target']:.0%} -> "
            f"{'PASS' if t['passed'] else 'FAIL'}"
        )
    print(
        f"Mean absolute closing-cash error: ${summary['closing_balance_mean_abs_error_usd']:,.0f}"
    )
    print(f"Note: {summary['note']}")

    if not args.skip_live:
        live_detail, live = score_live(data, load_dataset(args.data, holdout=True), as_of, weeks)
        live_detail.to_parquet(out_dir / "live_detail.parquet", index=False)
        summary["live"] = live
        print(f"\nLive forecast ({as_of.date()}) vs 13-week holdout actuals:")
        print(table(live["by_group"], SHOW))

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    print(f"\nArtifacts: {out_dir}")
    return 0 if all(t["passed"] for t in summary["targets"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
