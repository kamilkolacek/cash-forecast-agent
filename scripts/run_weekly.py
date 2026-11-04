"""The full weekly cycle, deterministic part: validate, forecast, variance, scenarios, facts.

Usage:
  python scripts/run_weekly.py                    # forecast at the data's as_of
  python scripts/run_weekly.py --simulate-week 2  # pretend 2 weeks have passed (uses holdout)

Variance compares last week's forecast (cutoff - 7 days) with the week's actuals.
Writes everything into outputs/runs/<run_id>/ and prints the run directory last.
Claude then reviews the run and writes memo.md from facts.md (see /forecast).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT, load_yaml
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.data.timeline import combine_with_holdout
from cashforecast.data.validation import validate
from cashforecast.engine.forecast import run_forecast
from cashforecast.engine.scenarios import run_scenarios
from cashforecast.engine.variance import run_variance
from cashforecast.outputs.artifacts import (
    write_facts,
    write_forecast,
    write_scenarios,
    write_validation,
    write_variance,
)
from cashforecast.outputs.audit import Audit
from cashforecast.outputs.workbook import write_workbook


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "runs")
    p.add_argument(
        "--simulate-week",
        type=int,
        default=0,
        choices=range(0, 13),
        help="weeks after the data's as_of to run from, using holdout actuals",
    )
    args = p.parse_args()

    try:
        data_as_of = pd.Timestamp(load_manifest(args.data)["as_of"])
        data = load_dataset(args.data)
    except FileNotFoundError:
        print(
            f"No dataset at {args.data}. Run `make data` (or /generate-data) first.",
            file=sys.stderr,
        )
        return 2
    audit = Audit(args.data, simulate_week=args.simulate_week)
    report = validate(data, load_yaml("company.yaml")["balance_sheet"]["opening_cash"], data_as_of)
    if not report["passed"]:
        print(f"Validation FAILED with {report['errors']} error(s). No forecast produced.")
        for f in report["findings"]:
            if f["severity"] == "ERROR" and not f["passed"]:
                print(f"  {f['check']}: {f['detail']}")
        return 1
    if args.simulate_week:
        data = combine_with_holdout(data, load_dataset(args.data, holdout=True))
    cutoff = data_as_of + pd.Timedelta(weeks=args.simulate_week)
    audit.params["cutoff"] = str(cutoff.date())
    audit.step("load_and_validate")

    current = run_forecast(data, cutoff, data_as_of)
    run_dir = write_forecast(current, args.out)
    write_validation(run_dir, report)
    audit.step("forecast")
    v = run_variance(data, cutoff - pd.Timedelta(days=7), cutoff, data_as_of)
    write_variance(run_dir, v)
    audit.step("variance")
    write_scenarios(run_dir, run_scenarios(current, data))
    audit.step("scenarios")
    write_facts(run_dir)
    workbook = write_workbook(run_dir)
    audit.step("facts_and_workbook")
    audit.write(run_dir)

    s, vs = current.summary, v.summary
    print(f"Validation passed ({report['warnings']} warnings)")
    print(
        f"Forecast {s['as_of']} to {s['horizon_end']}: opening ${s['opening_cash_usd']:,.0f}, "
        f"ending ${s['ending_cash_usd']:,.0f}, "
        f"low ${s['min_cash_usd']:,.0f} on {s['min_cash_date']}"
    )
    print(
        f"Variance {vs['window']}: ${vs['total_variance_usd']:,.0f} "
        f"(timing ${vs['timing_usd']:,.0f}, permanent ${vs['permanent_usd']:,.0f})"
    )
    print(f"Flags: {s['flags'] or 'none'}")
    print(f"Workbook: {workbook.name}")
    print(run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
