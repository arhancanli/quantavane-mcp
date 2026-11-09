"""The benchmark's families (v2.0): cells written out as problems, listing, sampling, and check_candidate on a cell of
every family with a red control (a corrupted object must fail)."""
import hashlib
import itertools
import json
import random
import shutil
from pathlib import Path

import pytest
from helpers import BUNDLED

from quantavane_mcp.checking import Checker, CheckError, find_problem, obb_verdicts
from quantavane_mcp.config import Settings
from quantavane_mcp.data import Benchmark, Store

FAMILIES = {"constant-weight-code": 1134, "covering-array": 2651, "covering-design": 55985, "linear-code": 15255,
            "project-scheduling": 59170, "spherical-code": 14782}


def test_families_and_counts(store):
    b = store.benchmark
    assert {n: f["count"] for n, f in b.families.items()} == FAMILIES
    assert b.total_problems() == 149372 == len(b.problems) + sum(FAMILIES.values())
    assert b.family_counts()["covering-design"] == 55985 + 10          # with the 10 single problems of v1
    for name, info in b.meta["families"].items():                     # the gzip copies are the published files
        import gzip
        raw = gzip.decompress((b.root / info["cells"]).read_bytes())
        assert hashlib.sha256(raw).hexdigest() == info["sha256"] and len(raw.splitlines()) == info["count"], name


def test_cells_are_written_out_as_problems(store):
    b = store.benchmark
    lotto = b.find("covering-7-3-2-3").raw
    assert lotto["title"] == "Covering design C(7,3,2,3)" and lotto["checker"]["args"] == ["7", "3", "2", "3"]
    assert lotto["best_known"]["exact"] == "4" and lotto["bound"]["kind"] == "lower bound"
    assert lotto["family"] == "covering-design" and lotto["added"] == "2.0"
    sphere = b.find("sphere-d3-n16").raw
    assert "exact" not in sphere["best_known"]                         # the table prints rounded values
    code = b.find("code-q2-n32-k14").raw
    assert code["best_known"]["provenance"]["url"] == "https://www.codetables.de/BKLC/BKLC.php?q=2&n=32&k=14"
    netres = b.find("rcpsp-nr_ad-80224").raw
    assert netres["checker"]["args"] == ["rcp+res", "instances/rcpsp/NetRes/MT30/Set 2.1 AD (low SP)/EV224.rcp",
                                         "instances/rcpsp/NetRes/ResSet/ResSet1.txt", "101"]
    assert b.find("covering-7-3-2-99") is None and b.find("nonsense-1") is None


def test_unknown_cell_says_which_family(store):
    with pytest.raises(CheckError, match="covering-design family"):
        find_problem(store.benchmark, "covering-7-3-2-99")


def test_sample_draws_as_obb_does(store):
    # obb.py sample linear-code 5 0, run with the benchmark's own Python on 9 Nov 2026
    assert store.benchmark.sample("linear-code", 5, 0) == ["code-q8-n65-k6", "code-q3-n118-k7", "code-q5-n105-k10",
                                                            "code-q9-n38-k6", "code-q3-n150-k134"]


def test_family_problems_put_single_problems_first(store):
    ids = store.benchmark.family_problems("covering-design")
    assert len(ids) == 55995 and ids[0] in store.benchmark.problems and ids[10] == "covering-7-3-2-3"


# ------------------------------------------------------------------------------------- one cell of each family


def check(checker, pid, lines):
    return checker.check(pid, certificate="\n".join(lines) + "\n")


def greedy_covering(v, k, t):
    covered, blocks = set(), []
    for T in itertools.combinations(range(1, v + 1), t):
        if T in covered:
            continue
        b = sorted(T + tuple(p for p in range(1, v + 1) if p not in T)[:k - t])
        blocks.append(b)
        covered.update(itertools.combinations(b, t))
    return blocks


def test_covering_design_cells(checker):
    lines = [" ".join(map(str, b)) for b in greedy_covering(19, 4, 3)]          # C(19,4,3), t = m
    r = check(checker, "covering-19-4-3", lines)
    assert r.verdict == "certified" and r.value == str(len(lines)) and r.improves_page_best is False
    assert r.limits.timeout_s == 300                                             # covering designs get 300 s
    assert check(checker, "covering-19-4-3", lines[:-1]).verdict == "not_certified"   # last block removed
    lotto = [" ".join(map(str, b)) for b in greedy_covering(7, 3, 2)]           # covers every pair: a C(7,3,2,3)
    assert obb_verdicts(check(checker, "covering-7-3-2-3", lotto)) == ["does not improve"]
    bad = lotto[1:] + ["1 2 8"]                                                   # a point outside 1..7
    assert check(checker, "covering-7-3-2-3", bad).verdict == "not_certified"


def test_spherical_code_cell(checker):
    rng = random.Random(5)
    lines = [",".join(f"{rng.gauss(0, 1):.15f}" for _ in range(3)) for _ in range(16)]
    r = check(checker, "sphere-d3-n16", lines)
    assert r.verdict == "certified" and r.improves_page_best is False and r.exactness.startswith("decimal")
    assert check(checker, "sphere-d3-n16", lines[:-1]).verdict == "not_certified"   # a point too few


def test_linear_code_cell(checker):
    p = find_problem(checker.bench, "code-q2-n32-k14")                           # best known d = 8, upper bound 9
    assert p.raw["checker"]["program"] == "lincode_check.py" and p.best_known["value"] == "8"
    rng = random.Random(1)
    q, n, k = 2, 32, 14
    gen = [[1 if j == i else 0 for j in range(k)] + [rng.randrange(q) for _ in range(n - k)] for i in range(k)]
    lines = [" ".join(map(str, row)) for row in gen]                            # a random code in systematic form
    r = check(checker, "code-q2-n32-k14", lines)
    assert r.verdict == "certified" and 1 <= int(r.value) < 8 and r.improves_page_best is False, r.reason
    assert check(checker, "code-q2-n32-k14", lines[:-1] + [lines[0]]).verdict == "not_certified"   # a row repeated


def test_covering_array_cell(checker):
    rng = random.Random(3)
    t, k, v = 2, 5, 3
    rows = [[rng.randrange(v) for _ in range(k)] for _ in range(v ** t)]
    for cols in itertools.combinations(range(k), t):
        seen = {tuple(r[c] for c in cols) for r in rows}
        for tup in itertools.product(range(v), repeat=t):
            if tup not in seen:
                r = [rng.randrange(v) for _ in range(k)]
                for c, s in zip(cols, tup, strict=True):
                    r[c] = s
                rows.append(r)
                seen.add(tup)
    lines = [" ".join(map(str, r)) for r in rows]
    r = check(checker, "ca-2-5-3", lines)
    assert r.verdict == "certified" and r.value == str(len(rows)) and r.improves_page_best is False
    assert check(checker, "ca-2-5-3", lines[:-1]).verdict == "not_certified"         # its last row was needed


def test_constant_weight_code_cell(checker):
    words, seen = [], set()
    for x in itertools.combinations(range(1, 9), 4):                             # A(8,6,4): share at most 1 position
        subs = list(itertools.combinations(x, 2))
        if any(s in seen for s in subs):
            continue
        words.append(x)
        seen.update(subs)
    lines = [" ".join(map(str, w)) for w in words]
    r = check(checker, "cw-8-6-4", lines)
    assert r.verdict == "certified" and r.value == str(len(words)) and r.improves_page_best is False
    assert check(checker, "cw-8-6-4", lines + [lines[0]]).verdict == "not_certified"   # a word repeated


def test_scheduling_cell_without_instances_says_how_to_get_them(checker):
    with pytest.raises(CheckError, match="instances/rcpsp/CV/cv108.rcp"):
        checker.check("rcpsp-cv-108", certificate="0 0 0\n")


@pytest.fixture
def mini_scheduling(tmp_path, cache_dir):
    """A local benchmark with one scheduling cell on a generated instance (the sets' files are not bundled)."""
    root = tmp_path / "bench"
    (root / "problems").mkdir(parents=True)
    shutil.copytree(BUNDLED / "checkers", root / "checkers")
    fam_dir = root / "families" / "project-scheduling"
    fam_dir.mkdir(parents=True)
    shutil.copy(BUNDLED / "families" / "project-scheduling" / "family.json", fam_dir / "family.json")
    cell = {"id": "rcpsp-test-1", "params": {"set": "TEST", "id": 1, "file": "t1.rcp"}, "best": "5", "bound": "4"}
    cells = (json.dumps(cell) + "\n").encode()
    (fam_dir / "cells.jsonl").write_bytes(cells)
    (root / "index.json").write_text(json.dumps({"benchmark_version": "test", "problems": 1, "by_family": {
        "project-scheduling": 1}, "shards": [{"kind": "family", "family": "project-scheduling",
                                              "path": "families/project-scheduling/cells.jsonl", "count": 1,
                                              "sha256": hashlib.sha256(cells).hexdigest()}]}))
    inst = root / "instances" / "rcpsp" / "TEST"
    inst.mkdir(parents=True)
    # two activities of duration 2 and demand 2 on one resource of capacity 3, between dummy start and end
    (inst / "t1.rcp").write_text("4 1\n3\n0 0 2 2 3\n2 2 1 4\n2 2 1 4\n0 0 0\n")
    s = Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, instances_dir=root / "instances", timeout_s=60)
    return Checker(Store(benchmark=Benchmark(root)), s)


def test_scheduling_cell_with_a_local_instance(mini_scheduling):
    p = find_problem(mini_scheduling.bench, "rcpsp-test-1")
    assert p.raw["checker"]["args"] == ["rcp", "instances/rcpsp/TEST/t1.rcp"]
    r = mini_scheduling.check("rcpsp-test-1", certificate="0 0 2 4\n")             # one after the other: makespan 4
    assert r.verdict == "certified" and r.value == "4" and r.improves_page_best is True
    bad = mini_scheduling.check("rcpsp-test-1", certificate="0 0 0 2\n")          # both at once: demand 4 > 3
    assert bad.verdict == "not_certified"
    early = mini_scheduling.check("rcpsp-test-1", certificate="0 0 2 3\n")        # the end before activity 3 ends
    assert early.verdict == "not_certified"


def test_instance_paths_cannot_leave_the_instances_folder(mini_scheduling):
    with pytest.raises(CheckError, match="Refusing"):
        mini_scheduling.instance("instances/../../etc/passwd")


def test_family_cells_resolve_lazily(tmp_path):
    b = Benchmark()
    assert b._cells == {}
    b.find("cw-8-6-4")
    assert list(b._cells) == ["constant-weight-code"]
    assert Path(b.root / b.meta["families"]["covering-design"]["cells"]).suffix == ".gz"
