import ast
import json
import subprocess
import sys
from pathlib import Path

from cashforecast.outputs.traceability import parse_money, parse_pct, untraceable

ROOT = Path(__file__).resolve().parents[2]


def _run_dir(tmp_path: Path) -> Path:
    (tmp_path / "summary.json").write_text(
        json.dumps(
            {"ending_cash_usd": 65245412.21, "churn": {"enterprise": 0.0703}, "draw": 4000000.0}
        )
    )
    (tmp_path / "facts.md").write_text("| Net change | $6.5M |\n| Headroom | -$3.3M |\n")
    return tmp_path


def test_parse_money_units_and_precision():
    toks = parse_money("Cash $65.2M, fee $12,500, draw $4 million, loss -$3.3M, $1.25B")
    vals = [(t[1], round(t[2], 2)) for t in toks]
    assert vals == [
        (65.2e6, 50000.0),
        (12500.0, 0.5),
        (4e6, 500000.0),
        (3.3e6, 50000.0),
        (1.25e9, 5e6),
    ]


def test_parse_pct():
    assert [t[1] for t in parse_pct("churn 7.0% and 15% but not v2%x")] == [7.0, 15.0]


def test_matches_at_stated_precision(tmp_path):
    run = _run_dir(tmp_path)
    assert untraceable("Ending cash $65.2M; churn 7.0%; draw $4M; net $6.5M.", run) == []
    assert untraceable("Ending cash $65.3M.", run) == ["$65.3M"]
    assert untraceable("Exactly $65,245,412.", run) == []
    assert untraceable("Shortfall of $3.3M.", run) == []  # sign-insensitive


def test_hook_blocks_bad_memo_and_ignores_other_files(tmp_path):
    run = _run_dir(tmp_path)
    hook = ROOT / ".claude" / "hooks" / "check_numbers.py"

    def call(path: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(hook)],
            capture_output=True,
            text=True,
            input=json.dumps({"tool_input": {"file_path": str(path)}}),
        )

    memo = run / "memo.md"
    memo.write_text("Ending cash $65.2M.")
    assert call(memo).returncode == 0
    memo.write_text("Ending cash $70.0M.")
    res = call(memo)
    assert res.returncode == 2 and "$70.0M" in res.stderr
    other = run / "notes.md"
    other.write_text("Ending cash $70.0M.")
    assert call(other).returncode == 0


def test_no_runtime_union_types_for_old_system_python():
    """The hook runs under the system python3 (3.9 on macOS), where `int | float` raises."""
    src = ROOT / "src" / "cashforecast" / "outputs" / "traceability.py"
    calls = [
        node
        for node in ast.walk(ast.parse(src.read_text()))
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "isinstance"
    ]
    assert calls
    assert not [c.lineno for c in calls if isinstance(c.args[1], ast.BinOp)]


def test_committed_sample_memo_is_traceable():
    run = ROOT / "docs" / "examples" / "sample_run"
    assert untraceable((run / "memo.md").read_text(), run) == []
