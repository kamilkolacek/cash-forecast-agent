"""Number traceability: every money figure and percentage in a memo must exist in the run.

Standard library only, so the Claude Code hook can import it without the project venv.

A memo figure matches if some value in the run artifacts (JSON, CSV, facts.md) rounds to
it at the precision the memo used: "$58.7M" matches 58,726,680; "4.5%" matches 0.045 or 4.5.
Signs are ignored ("an outflow of $3.3M" may cite -3,262,174).
"""

from __future__ import annotations

import bisect
import contextlib
import csv
import json
import math
import re
from pathlib import Path

MONEY = re.compile(
    r"(?P<neg>-)?\$\s?(?P<num>\d[\d,]*(?:\.\d+)?)\s?"
    r"(?P<unit>[MKB]\b|mm\b|million|thousand|billion|bn\b)?",
    re.IGNORECASE,
)
PCT = re.compile(r"(?<![\w.])(?P<num>-?\d+(?:\.\d+)?)\s?%")
SCALE = {
    "m": 1e6,
    "mm": 1e6,
    "million": 1e6,
    "k": 1e3,
    "thousand": 1e3,
    "b": 1e9,
    "bn": 1e9,
    "billion": 1e9,
}


def _decimals(num: str) -> int:
    return len(num.split(".")[1]) if "." in num else 0


def parse_money(text: str) -> list[tuple[str, float, float]]:
    """(token, value, tolerance) for each $ figure."""
    out = []
    for mt in MONEY.finditer(text):
        num, unit = mt.group("num"), (mt.group("unit") or "").lower()
        scale = SCALE.get(unit, 1.0)
        value = float(num.replace(",", "")) * scale
        tol = 0.5 * 10 ** (-_decimals(num)) * scale + 1e-6
        out.append((mt.group(0).strip(), value, tol))
    return out


def parse_pct(text: str) -> list[tuple[str, float, float]]:
    return [
        (mt.group(0), float(mt.group("num")), 0.5 * 10 ** (-_decimals(mt.group("num"))) + 1e-9)
        for mt in PCT.finditer(text)
    ]


def _walk(obj, acc: list[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, int | float):
        acc.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _walk(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, acc)


def artifact_values(run_dir: Path) -> tuple[list[float], list[float]]:
    """Sorted absolute values: (money-like pool, percent pool)."""
    money: list[float] = []
    for p in run_dir.glob("*.json"):
        _walk(json.loads(p.read_text()), money)
    for p in run_dir.glob("*.csv"):
        with open(p, newline="") as f:
            for row in csv.reader(f):
                for cell in row:
                    with contextlib.suppress(ValueError):
                        money.append(float(cell))
    facts = run_dir / "facts.md"
    percents = [v * 100 for v in money] + list(money)
    if facts.exists():
        text = facts.read_text()
        money += [v for _, v, _ in parse_money(text)]
        percents += [v for _, v, _ in parse_pct(text)]

    # NaN/inf (blank CSV cells, JSON NaN) would break the sorted order bisect relies on.
    def pool(vals: list[float]) -> list[float]:
        return sorted({abs(v) for v in vals if math.isfinite(v)})

    return pool(money), pool(percents)


def _found(pool: list[float], value: float, tol: float) -> bool:
    i = bisect.bisect_left(pool, abs(value) - tol)
    return i < len(pool) and pool[i] <= abs(value) + tol


def untraceable(memo_text: str, run_dir: Path) -> list[str]:
    money_pool, pct_pool = artifact_values(Path(run_dir))
    bad = [tok for tok, v, tol in parse_money(memo_text) if not _found(money_pool, v, tol)]
    bad += [tok for tok, v, tol in parse_pct(memo_text) if not _found(pct_pool, v, tol)]
    return bad
