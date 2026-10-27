"""Despatch report dates follow the India calendar, never C-shift start date."""
from pathlib import Path
import json
import shutil
import subprocess
import pytest

JS = Path(__file__).parents[1] / "app" / "static" / "tiom_despatch.js"


@pytest.mark.parametrize("now_utc,expected", [
    ("2026-10-27T18:33:24Z", "2026-10-27"),  # 28-Oct 00:03 IST; C shift=27-Oct
    ("2026-10-27T08:00:00Z", "2026-10-26"),  # 27-Oct 13:30 IST
    ("2026-11-01T18:45:00Z", "2026-11-01"),  # 02-Nov 00:15 IST
    ("2027-01-01T00:00:00Z", "2026-12-31"),  # month/year boundary
])
def test_despatch_yesterday_india_calendar_not_shift_date(now_utc, expected):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    source = JS.read_text(encoding="utf-8")
    start = source.index("function latestCompletedDespatchDate(){")
    end = source.index("\n}\n", start) + 2
    func = source[start:end]
    script = (
        "const RealDate = global.Date;\n"
        "class FakeDate extends RealDate {\n"
        "  constructor(...args){super(...(args.length?args:[" +
        json.dumps(now_utc) + "]))}\n"
        "  static UTC(...args){return RealDate.UTC(...args)}\n"
        "}\nconst Date=FakeDate;\n"
        + func + "\nconsole.log(latestCompletedDespatchDate());"
    )
    r = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == expected
