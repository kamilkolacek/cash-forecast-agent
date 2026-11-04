"""Check that every $ figure and percentage in a memo traces to its run's artifacts.

Usage: python scripts/check_memo.py [path/to/memo.md]   (default: latest run's memo.md)
"""

from __future__ import annotations

import sys
from pathlib import Path

from cashforecast.config import PROJECT_ROOT
from cashforecast.outputs.artifacts import latest_run
from cashforecast.outputs.traceability import untraceable


def main() -> int:
    if len(sys.argv) > 1:
        memo = Path(sys.argv[1])
    else:
        run = latest_run(PROJECT_ROOT / "outputs" / "runs")
        memo = run / "memo.md" if run else Path("memo.md")
    if not memo.exists():
        print(f"No memo at {memo}")
        return 1
    bad = untraceable(memo.read_text(), memo.parent)
    if bad:
        print(f"UNTRACEABLE ({len(bad)}): {', '.join(bad)}")
        return 1
    print(f"All figures in {memo} trace to run artifacts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
