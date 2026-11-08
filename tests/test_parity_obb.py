"""Parity with the public benchmark's own runner (opt-in): for every certificate test.sh checks, the server's exact
value and verdicts equal what `python3 -I obb.py check` prints in a benchmark checkout.

    QUANTAVANE_MCP_TEST_BENCHMARK=~/quantavane-benchmark pytest tests/test_parity_obb.py

The checkout's certs/ (fetched by its fetch.sh) supplies the other authors' certificates; those absent are skipped."""
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from quantavane_mcp.checking import obb_verdicts
from quantavane_mcp.data import DATA_DIR

BENCH = os.environ.get("QUANTAVANE_MCP_TEST_BENCHMARK")
META = json.loads((DATA_DIR / "benchmark" / "meta.json").read_text())
CASES = [(r["problem"], "refs/" + r["file"], r["expected"]) for r in META["reference_expected"]
         if not r["problem"].startswith("cvrp-")] + \
        [(r["problem"], "certs/" + r["file"], r["expected"]) for r in META["external_expected"]
         if not r["problem"].startswith("cvrp-")]

pytestmark = pytest.mark.skipif(not BENCH, reason="set QUANTAVANE_MCP_TEST_BENCHMARK to a benchmark checkout")


def obb(pid: str, rel: str) -> tuple[str | None, list[str]]:
    r = subprocess.run(["python3", "-I", "obb.py", "check", pid, rel], cwd=BENCH, capture_output=True, text=True,
                       timeout=900)
    m = re.search(r"certified value (\d+)/(\d+)", r.stdout)
    value = None if not m else (m.group(1) if m.group(2) == "1" else f"{m.group(1)}/{m.group(2)}")
    return value, re.findall(r"IMPROVES|does not improve|NOT CERTIFIED", r.stdout)


@pytest.mark.parametrize("pid,rel,expected", CASES, ids=[f"{c[0]}:{Path(c[1]).name}" for c in CASES])
def test_same_value_and_verdicts_as_obb(checker, pid, rel, expected):
    path = Path(BENCH).expanduser() / rel
    if not path.is_file():
        pytest.skip(f"{rel} not fetched")
    ours = checker.check_data(pid, path.read_bytes())
    value, verdicts = obb(pid, rel)
    assert obb_verdicts(ours) == verdicts == expected
    assert ours.value == value
