"""Generate the synthetic dataset, then validate it.

Usage: python scripts/generate.py [--seed N] [--no-anomalies] [--csv] [--out DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT, load_yaml
from cashforecast.data.loaders import load_dataset
from cashforecast.data.validation import validate
from cashforecast.synthetic.generator import generate


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--no-anomalies", action="store_true")
    p.add_argument("--csv", action="store_true", help="also write CSV copies for review")
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "data" / "raw")
    args = p.parse_args()

    m = generate(args.out, seed=args.seed, inject=not args.no_anomalies, csv=args.csv)
    cfg = load_yaml("company.yaml")
    report = validate(
        load_dataset(args.out), cfg["balance_sheet"]["opening_cash"], pd.Timestamp(m["as_of"])
    )
    (args.out / "validation.json").write_text(json.dumps(report, indent=2, default=str))

    print(
        f"Generated {m['company']} | seed {m['seed']} | history {m['history_start']} "
        f"to {m['as_of']} (exclusive) | holdout to {m['holdout_end']}"
    )
    print(
        f"ARR at as_of ${m['arr_at_as_of_usd']:,.0f} | customers {m['active_customers_at_as_of']} "
        f"| billing mix {m['billing_mix_by_arr']}"
    )
    print(
        f"Cash at as_of ${m['cash_at_as_of_usd']:,.0f} | history low "
        f"${m['min_cash_in_history_usd']:,.0f} on {m['min_cash_date']} "
        f"| open AR ${m['open_ar_usd_at_issue']:,.0f}"
    )
    print(f"Anomalies injected: {[a['type'] for a in m['anomalies']]}")
    print(
        f"Validation: {'PASSED' if report['passed'] else 'FAILED'} | "
        f"errors {report['errors']} | warnings {report['warnings']}"
    )
    for f in report["findings"]:
        if not f["passed"] or f["severity"] == "INFO":
            print(f"  [{f['severity']}] {f['check']}: {f['detail']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
