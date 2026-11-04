"""Run scenarios against the latest forecast run (or a new one).

Usage:
  python scripts/run_scenario.py                       # all scenarios in config/scenarios.yaml
  python scripts/run_scenario.py --name downside
  python scripts/run_scenario.py --custom acquisition \
      '[{"type": "one_off", "date": "2026-12-15", "amount_usd": -12000000, "category": "capex"}]'

Results merge into scenarios.json in the run directory and facts.md is refreshed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.engine.forecast import run_forecast
from cashforecast.engine.scenarios import run_scenarios, validate_shocks
from cashforecast.outputs.artifacts import latest_run, write_facts, write_forecast, write_scenarios


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "runs")
    p.add_argument("--name", action="append", help="scenario name from scenarios.yaml")
    p.add_argument("--custom", nargs=2, metavar=("NAME", "SHOCKS_JSON"))
    args = p.parse_args()

    custom = None
    if args.custom:
        shocks = json.loads(args.custom[1])
        validate_shocks(shocks)
        custom = {args.custom[0]: shocks}

    data = load_dataset(args.data)
    run_dir = latest_run(args.out)
    if run_dir and run_dir.exists():
        as_of = pd.Timestamp(json.loads((run_dir / "summary.json").read_text())["as_of"])
    else:
        as_of = pd.Timestamp(load_manifest(args.data)["as_of"])
    base = run_forecast(data, as_of, pd.Timestamp(load_manifest(args.data)["as_of"]))
    if not (run_dir and run_dir.exists()):
        run_dir = write_forecast(base, args.out)

    names = args.name if args.name else ([] if custom else None)
    names = (["base"] + names) if names is not None and "base" not in names else names
    result = run_scenarios(base, data, names=names, custom=custom)
    write_scenarios(run_dir, result)
    write_facts(run_dir)

    df = pd.DataFrame(result["scenarios"]).T
    cols = [
        "ending_cash_usd",
        "change_vs_base_usd",
        "min_cash_usd",
        "min_cash_date",
        "floor_headroom_usd",
        "suggested_revolver_draw_usd",
    ]
    print(df[cols].to_string())
    for n, r in result["scenarios"].items():
        if r["flags"]:
            print(f"{n}: flags {r['flags']}")
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
