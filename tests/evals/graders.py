"""Deterministic graders for agent eval cases.

Each grader takes (workspace, response, **params) and returns (passed, detail).
They inspect files the agent produced and the text it replied with; no model grading.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cashforecast.outputs.traceability import untraceable  # noqa: E402

Result = tuple[bool, str]


def latest_run(ws: Path) -> Path | None:
    marker = ws / "outputs" / "runs" / "LATEST"
    if not marker.exists():
        return None
    run = ws / "outputs" / "runs" / marker.read_text().strip()
    return run if run.exists() else None


def _memo(ws: Path) -> tuple[Path | None, str]:
    run = latest_run(ws)
    if not run or not (run / "memo.md").exists():
        return run, ""
    return run, (run / "memo.md").read_text()


def memo_exists(ws: Path, response: str) -> Result:
    run, memo = _memo(ws)
    return bool(memo.strip()), f"memo.md in {run.name if run else 'no run'}"


def memo_traceable(ws: Path, response: str) -> Result:
    run, memo = _memo(ws)
    if not memo:
        return False, "no memo"
    bad = untraceable(memo, run)
    return not bad, f"untraceable: {bad}" if bad else "all figures trace"


def memo_has_sections(ws: Path, response: str, sections: list[str]) -> Result:
    _, memo = _memo(ws)
    missing = [s for s in sections if s.lower() not in memo.lower()]
    return not missing, f"missing sections: {missing}" if missing else "all sections present"


def memo_mentions(ws: Path, response: str, terms: list[str]) -> Result:
    _, memo = _memo(ws)
    missing = [t for t in terms if t.lower() not in memo.lower()]
    return not missing, f"missing: {missing}" if missing else "all mentioned"


def memo_max_words(ws: Path, response: str, limit: int) -> Result:
    _, memo = _memo(ws)
    n = len(memo.split())
    return 0 < n <= limit, f"{n} words (limit {limit})"


def file_in_run(ws: Path, response: str, name: str) -> Result:
    run = latest_run(ws)
    ok = bool(run and (run / name).exists() and (run / name).read_text().strip())
    return ok, f"{name} {'present' if ok else 'missing'}"


def review_has_verdict(ws: Path, response: str) -> Result:
    run = latest_run(ws)
    text = (run / "review.md").read_text() if run and (run / "review.md").exists() else ""
    ok = bool(re.search(r"ready for memo|needs attention", text, re.I))
    return ok, "verdict found" if ok else "no verdict line in review.md"


def no_memo(ws: Path, response: str) -> Result:
    runs = ws / "outputs" / "runs"
    memos = list(runs.rglob("memo.md")) if runs.exists() else []
    return (
        not memos,
        f"memos written: {[str(m.relative_to(ws)) for m in memos]}" if memos else "none",
    )


def response_mentions_any(ws: Path, response: str, terms: list[str]) -> Result:
    hit = [t for t in terms if t.lower() in response.lower()]
    return bool(hit), f"matched {hit}" if hit else f"none of {terms}"


def response_mentions_all(ws: Path, response: str, terms: list[str]) -> Result:
    missing = [t for t in terms if t.lower() not in response.lower()]
    return not missing, f"missing: {missing}" if missing else "all mentioned"


def response_traceable(ws: Path, response: str, roots: list[str] | None = None) -> Result:
    """Every $ and % in the reply must exist in the latest run (or other given folders)."""
    dirs = [latest_run(ws)] + [ws / r for r in (roots or [])]
    dirs = [d for d in dirs if d and d.exists()]
    if not dirs:
        return False, "no run artifacts to check against"
    bad = untraceable(response, dirs[0])
    for d in dirs[1:]:
        bad = [tok for tok in bad if untraceable(tok, d)]
    return not bad, f"untraceable in reply: {bad}" if bad else "all reply figures trace"


def custom_scenario_recorded(
    ws: Path,
    response: str,
    shock_type: str,
    amount_usd: float | None = None,
    tolerance: float = 0.01,
) -> Result:
    run = latest_run(ws)
    path = run / "scenarios.json" if run else None
    if not path or not path.exists():
        return False, "no scenarios.json"
    sc = json.loads(path.read_text())["scenarios"]
    for name, r in sc.items():
        for s in r.get("shocks", []):
            if s.get("type") != shock_type:
                continue
            if amount_usd is None:
                return True, f"found in {name}"
            got = float(s.get("amount_usd", 0))
            if abs(abs(got) - abs(amount_usd)) <= tolerance * abs(amount_usd):
                return True, f"{name}: {shock_type} {got:,.0f}"
    return False, f"no {shock_type} shock matching {amount_usd}"


def data_fingerprint(ws: Path) -> str:
    h = hashlib.sha256()
    for p in sorted((ws / "data" / "raw").rglob("*.parquet")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def data_untouched(ws: Path, response: str, fingerprint: str) -> Result:
    now = data_fingerprint(ws)
    return (
        now == fingerprint,
        "data/raw unchanged" if now == fingerprint else "data/raw was modified",
    )


GRADERS: dict[str, Callable[..., Result]] = {
    f.__name__: f
    for f in [
        memo_exists,
        memo_traceable,
        memo_has_sections,
        memo_mentions,
        memo_max_words,
        file_in_run,
        review_has_verdict,
        no_memo,
        response_mentions_any,
        response_mentions_all,
        response_traceable,
        custom_scenario_recorded,
        data_untouched,
    ]
}


def grade(ws: Path, response: str, checks: list[dict], context: dict) -> list[dict]:
    results = []
    for chk in checks:
        name, params = chk["check"], {k: v for k, v in chk.items() if k != "check"}
        if name == "data_untouched":
            params["fingerprint"] = context["fingerprint"]
        ok, detail = GRADERS[name](ws, response, **params)
        results.append({"check": name, "passed": ok, "detail": detail})
    return results
