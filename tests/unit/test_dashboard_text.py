import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "app"))

from components.kpis import md  # noqa: E402


def test_md_escapes_every_dollar_sign():
    assert md("low $58.7M is $23.7M above") == r"low \$58.7M is \$23.7M above"
    assert md("| $65.2M | -$3.3M |") == r"| \$65.2M | -\$3.3M |"
    assert md("no money here") == "no money here"


def test_md_does_not_double_escape():
    assert md(md("$1.0M and $2.0M")) == r"\$1.0M and \$2.0M"
