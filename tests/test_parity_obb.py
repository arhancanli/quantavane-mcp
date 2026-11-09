"""Parity with the public benchmark's own runner (opt-in): for every certificate test.sh checks, the server's exact
value and verdicts equal what `python3 -I obb.py check` prints in a benchmark checkout.

    QUANTAVANE_MCP_TEST_BENCHMARK=~/quantavane-benchmark pytest tests/test_parity_obb.py

The checkout's certs/ (fetched by its fetch.sh) supplies the other authors' certificates; those absent are skipped.
Benchmark 2.1: the Quantavane Originals' own certificates too, and the second checkers of the claim checks give the
same value as obb.py on every certificate they can read within their limits."""
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
ORIGINALS = sorted(DATA_DIR.joinpath("benchmark", "collections", "originals", "refs").glob("*.txt"))
CASES = [(r["problem"], "refs/" + r["file"], r["expected"]) for r in META["reference_expected"]
         if not r["problem"].startswith("cvrp-")] + \
        [(r["problem"], "certs/" + r["file"], r["expected"]) for r in META["external_expected"]
         if not r["problem"].startswith("cvrp-")] + \
        [(f.stem, "collections/originals/refs/" + f.name, ["does not improve"]) for f in ORIGINALS]

pytestmark = pytest.mark.skipif(not BENCH, reason="set QUANTAVANE_MCP_TEST_BENCHMARK to a benchmark checkout")


def obb(pid: str, rel: str) -> tuple[str | None, list[str]]:
    r = subprocess.run(["python3", "-I", "obb.py", "check", pid, rel], cwd=BENCH, capture_output=True, text=True,
                       timeout=900)
    m = re.search(r"certified value (-?\d+)/(\d+)", r.stdout)
    value = None if not m else (m.group(1) if m.group(2) == "1" else f"{m.group(1)}/{m.group(2)}")
    return value, re.findall(r"IMPROVES|does not improve|NOT CERTIFIED", r.stdout)


@pytest.mark.parametrize("pid,rel,expected", CASES, ids=[f"{c[0]}:{Path(c[1]).name}" for c in CASES])
def test_same_value_and_verdicts_as_obb(store, cache_dir, tmp_path, pid, rel, expected):
    from quantavane_mcp.checking import Checker
    from quantavane_mcp.config import Settings
    path = Path(BENCH).expanduser() / rel
    if not path.is_file():
        pytest.skip(f"{rel} not fetched")
    checker = Checker(store, Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=600,
                                      max_timeout_s=900, instances_dir=Path(BENCH).expanduser() / "instances"))
    ours = checker.check_data(pid, path.read_bytes())
    value, verdicts = obb(pid, rel)
    assert obb_verdicts(ours) == verdicts == expected
    assert ours.value == value


# ------------------------------------------------------------------------------------- families (benchmark 2.0)

SAMPLES = sorted(Path(BENCH).expanduser().joinpath("certs", "samples").glob("*.txt")) if BENCH else []
SAMPLE_CASES = [f for f in SAMPLES if re.match(r"(covering|sphere|code|ca|cw|rcpsp)-", f.name)]


@pytest.mark.parametrize("path", SAMPLE_CASES, ids=[f.name for f in SAMPLE_CASES])
def test_sampled_cells_same_as_obb(store, cache_dir, tmp_path, path):
    """The objects tests/sample_cells.py builds for drawn cells (and their red controls): same value and verdicts."""
    from quantavane_mcp.checking import Checker, CheckError
    from quantavane_mcp.config import Settings
    pid = path.stem.removesuffix("_red")
    c = Checker(store, Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=600, max_timeout_s=900,
                                instances_dir=Path(BENCH).expanduser() / "instances"))
    try:
        ours = c.check_data(pid, path.read_bytes())
    except CheckError as e:
        pytest.skip(str(e)[:100])          # a scheduling cell whose instance files are not here
    value, verdicts = obb(pid, str(path.relative_to(Path(BENCH).expanduser())))
    assert obb_verdicts(ours) == verdicts
    assert ours.value == value
    assert verdicts == (["NOT CERTIFIED"] if path.stem.endswith("_red") else ["does not improve"])


FAMILY_NAMES = ["constant-weight-code", "covering-array", "covering-design", "linear-code", "project-scheduling",
                "spherical-code"]


@pytest.mark.parametrize("family", FAMILY_NAMES)
def test_show_and_sample_same_as_obb(store, family):
    """obb.py sample FAMILY 4 11 draws the same cells, and obb.py show writes each out exactly as the server does."""
    r = subprocess.run(["python3", "-I", "obb.py", "sample", family, "4", "11"], cwd=BENCH, capture_output=True,
                       text=True, timeout=300)
    drawn = r.stdout.split()
    assert drawn == store.benchmark.sample(family, 4, 11)
    for pid in drawn:
        shown = subprocess.run(["python3", "-I", "obb.py", "show", pid], cwd=BENCH, capture_output=True, text=True,
                               timeout=300)
        assert json.loads(shown.stdout) == store.benchmark.find(pid).raw, pid


# ------------------------------------------------------------------------------------- the claim checks' second checkers


@pytest.mark.parametrize("pid,rel,expected", CASES, ids=[f"second:{c[0]}:{Path(c[1]).name}" for c in CASES])
def test_second_checker_agrees_with_obb(checker, pid, rel, expected):
    """The second checker (written apart from the benchmark's) proves the value obb.py prints, and refuses what obb.py
    refuses; certificates beyond its limits (exit 2) are skipped and named."""
    from quantavane_mcp.claims import SECOND, second_kind
    p = checker.bench.find(pid)
    kind = second_kind(p)
    path = Path(BENCH).expanduser() / rel
    if kind is None or not path.is_file():
        pytest.skip("no second checker for this problem" if kind is None else f"{rel} not fetched")
    value, verdicts = obb(pid, rel)
    args = list(p.checker["args"]) + ([value or "0"] if kind == "sph" else [])
    r = subprocess.run(["python3", "-I", str(SECOND), kind, *args, str(path)], capture_output=True, text=True,
                       timeout=900)
    if r.returncode == 2:
        pytest.skip("beyond the second checker's limits: " + r.stdout.strip().splitlines()[-1][:120])
    m = re.search(r"^RESULT (\S+)$", r.stdout, re.M)
    if verdicts == ["NOT CERTIFIED"]:
        assert r.returncode == 1, r.stdout[-300:]
    else:
        assert r.returncode == 0 and m and m.group(1) == value, r.stdout[-300:]
