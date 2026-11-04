"""Forecast-vs-actual variance with timing / permanent split.

Usage:
  python scripts/run_variance.py                      # last week: as_of-7d forecast vs actuals
  python scripts/run_variance.py --weeks-elapsed 4    # live forecast vs 4 weeks of holdout actuals

Writes variance.json and variance_drivers.csv to outputs/variance/<prior>_<current>/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.data.timeline import combine_with_holdout
from cashforecast.engine.variance import run_variance
from cashforecast.outputs.artifacts import write_variance


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "variance")
    p.add_argument("--weeks-elapsed", type=int, default=0, choices=range(0, 14))
    args = p.parse_args()

    as_of = pd.Timestamp(load_manifest(args.data)["as_of"])
    data = load_dataset(args.data)
    if args.weeks_elapsed:
        data = combine_with_holdout(data, load_dataset(args.data, holdout=True))
        prior, current = as_of, as_of + pd.Timedelta(weeks=args.weeks_elapsed)
    else:
        prior, current = as_of - pd.Timedelta(days=7), as_of
    v = run_variance(data, prior, current, as_of)
    out = args.out / f"{prior:%Y-%m-%d}_{current:%Y-%m-%d}"
    out.mkdir(parents=True, exist_ok=True)
    write_variance(out, v)

    s = v.summary
    print(f"Window {s['window']} (forecast made {s['prior_cutoff']})")
    print(
        f"Closing cash: forecast ${s['forecast_closing_cash_usd']:,.0f} | "
        f"actual ${s['actual_closing_cash_usd']:,.0f}"
    )
    print(
        f"Variance ${s['total_variance_usd']:,.0f} = timing ${s['timing_usd']:,.0f} "
        f"+ permanent ${s['permanent_usd']:,.0f}"
    )
    cols = [
        "driver",
        "type",
        "is_whale",
        "forecast_window",
        "actual_window",
        "variance",
        "timing",
        "permanent",
        "classification",
    ]
    print(v.drivers.head(10)[cols].round(0).to_string(index=False))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
