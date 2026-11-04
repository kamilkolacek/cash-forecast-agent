"""PostToolUse hook: block memo figures that don't trace to the run's artifacts.

Fires after Write/Edit. Acts only on files named memo.md inside a run directory.
Exit 2 sends the message on stderr back to Claude so it can fix the memo.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(ROOT / "src"))

from cashforecast.outputs.traceability import untraceable  # noqa: E402


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    path = Path(event.get("tool_input", {}).get("file_path", ""))
    if path.name != "memo.md" or not path.exists():
        return 0
    bad = untraceable(path.read_text(), path.parent)
    if not bad:
        return 0
    print(
        "Memo blocked by number-traceability check. These figures do not appear in the run "
        f"artifacts in {path.parent.name}/ (facts.md, *.json, *.csv): {', '.join(bad)}. "
        "Replace each with the figure as written in facts.md, or remove it. "
        "Do not compute new totals in prose.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
