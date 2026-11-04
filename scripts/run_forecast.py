"""Run the 13-week cash forecast and write run artifacts.

Usage: python scripts/run_forecast.py [--as-of YYYY-MM-DD] [--data DIR] [--out DIR]

Writes outputs/runs/<run_id>/:
  summary.json       headline numbers, flags, week-ending dates
  assumptions.json   every learned parameter the forecast used
  weekly.csv         category x week table (the 13-week view)
  daily_detail.csv   weeks 1-2 at daily grain
  daily.parquet      full-horizon daily roll-forward
  lines.parquet      every forecast cash item with its source
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.engine.forecast import run_forecast
from cashforecast.outputs.artifacts import write_facts, write_forecast
from cashforecast.outputs.audit import Audit
from cashforecast.outputs.workbook import write_workbook


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--as-of", type=pd.Timestamp, default=None)
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "runs")
    args = p.parse_args()

    try:
        data_as_of = pd.Timestamp(load_manifest(args.data)["as_of"])
    except FileNotFoundError:
        print(
            f"No dataset at {args.data}. Run `make data` (or /generate-data) first.",
            file=sys.stderr,
        )
        return 2
    audit = Audit(args.data, as_of=str((args.as_of or data_as_of).date()))
    as_of = args.as_of or data_as_of
    if as_of > data_as_of:
        print(f"--as-of cannot be after the data's as_of ({data_as_of.date()})", file=sys.stderr)
        return 2
    res = run_forecast(load_dataset(args.data), as_of, data_as_of)
    run_dir = write_forecast(res, args.out)
    write_facts(run_dir)
    workbook = write_workbook(run_dir)
    audit.step("forecast_and_outputs")
    audit.write(run_dir)

    s = res.summary
    print(f"Run {run_dir.name} | horizon {s['as_of']} to {s['horizon_end']}")
    print(f"Opening cash  ${s['opening_cash_usd']:>15,.0f}")
    print(f"Receipts      ${s['total_receipts_usd']:>15,.0f}")
    print(f"Disbursements ${s['total_disbursements_usd']:>15,.0f}")
    print(f"Ending cash   ${s['ending_cash_usd']:>15,.0f}")
    floor, covenant = s["min_cash_threshold_usd"], s["covenant_min_liquidity_usd"]
    print(
        f"Minimum cash  ${s['min_cash_usd']:>15,.0f} on {s['min_cash_date']} "
        f"(floor ${floor:,.0f}, covenant ${covenant:,.0f})"
    )
    print(f"Flags: {s['flags'] or 'none'}")
    w = res.weekly.set_index("line")
    weeks = [c for c in res.weekly.columns if c.startswith("W")]
    print(
        "\n"
        + pd.DataFrame(
            {
                "week_ending": [s["week_ending"][c] for c in weeks],
                "receipts_m": (w.loc["Total receipts", weeks] / 1e6).round(1).values,
                "disbursements_m": (
                    (
                        w.loc["Total operating disbursements", weeks]
                        + w.loc["Total non-operating disbursements", weeks]
                    )
                    / 1e6
                )
                .round(1)
                .values,
                "closing_m": (w.loc["Closing cash", weeks] / 1e6).round(1).values,
            },
            index=weeks,
        ).to_string()
    )
    print(f"Workbook: {workbook.name}")
    print(f"\nArtifacts: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
