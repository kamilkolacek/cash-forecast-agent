"""Validate an existing dataset: tie-outs and data-quality findings.

Usage: python scripts/validate.py [--data DIR]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from cashforecast.config import PROJECT_ROOT, load_yaml
from cashforecast.data.loaders import load_dataset, load_manifest
from cashforecast.data.validation import validate


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=PROJECT_ROOT / "data" / "raw")
    args = p.parse_args()
    cfg = load_yaml("company.yaml")
    as_of = pd.Timestamp(load_manifest(args.data)["as_of"])
    report = validate(load_dataset(args.data), cfg["balance_sheet"]["opening_cash"], as_of)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
