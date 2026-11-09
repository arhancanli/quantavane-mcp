"""check_candidate's core: the benchmark's expected verdicts on every bundled reference certificate, red controls
(a corrupted certificate must fail), input validation, limits, and output hygiene."""
import hashlib
import json
import os
import shutil
from fractions import Fraction
from pathlib import Path

import pytest
from helpers import make_mini_benchmark, pentagon, ref

from quantavane_mcp import sandbox
from quantavane_mcp.checking import Checker, CheckError, obb_verdicts, ramsey_precheck, value_from_output
from quantavane_mcp.config import Settings
from quantavane_mcp.data import DATA_DIR, Benchmark, Store

META = json.loads((DATA_DIR / "benchmark" / "meta.json").read_text())
REFS = [(r["problem"], r["file"], r["expected"]) for r in META["reference_expected"]]
SLOW = {"maxr_c16_lower.json"}


def check_text(checker, pid, text, **kw):
    return checker.check(pid, certificate=text if isinstance(text, str) else text.decode(), **kw)


# ------------------------------------------------------------------------------------- parity with the benchmark


@pytest.mark.parametrize("pid,fname,expected", [r for r in REFS if not r[0].startswith("cvrp-")],
                         ids=[f"{r[0]}:{r[1]}" for r in REFS if not r[0].startswith("cvrp-")])
def test_reference_certificates_get_the_benchmarks_verdicts(checker, pid, fname, expected):
    """test.sh's expected verdicts (page best, then verified in review) on every bundled reference certificate."""
    r = checker.check_data(pid, ref(fname))
    assert obb_verdicts(r) == expected
    assert r.verdict == "certified" and r.value
    assert r.certificate_sha256 == hashlib.sha256(ref(fname)).hexdigest()


INSTANCES = os.environ.get("QUANTAVANE_MCP_TEST_INSTANCES")


@pytest.mark.skipif(not INSTANCES, reason="set QUANTAVANE_MCP_TEST_INSTANCES to a folder of CVRPLIB instances")
@pytest.mark.parametrize("pid,fname,expected", [r for r in REFS if r[0].startswith("cvrp-")],
                         ids=[r[0] for r in REFS if r[0].startswith("cvrp-")])
def test_routing_references_with_local_instances(store, cache_dir, pid, fname, expected):
    s = Settings(cache_dir=cache_dir, instances_dir=Path(INSTANCES), timeout_s=300)
    c = Checker(store, s)
    try:
        r = c.check_data(pid, ref(fname))
    except CheckError as e:
        pytest.skip(str(e)[:120])
    assert obb_verdicts(r) == expected


# ------------------------------------------------------------------------------------- red controls


def test_cw_repeated_word_fails(checker):
    data = ref("ours_cw_34_6_5.txt").decode()
    r = check_text(checker, "cw-34-6-5", data.splitlines()[0] + "\n" + data)
    assert r.verdict == "not_certified" and "share" in r.reason


def test_cw_wrong_weight_fails(checker):
    lines = ref("ours_cw_34_6_5.txt").decode().splitlines()
    lines[0] += " 34"
    r = check_text(checker, "cw-34-6-5", "\n".join(lines) + "\n")
    assert r.verdict == "not_certified" and "invalid word" in r.reason


def test_cw_two_close_words_fail(checker):
    lines = ref("ours_cw_34_6_5.txt").decode().splitlines()
    first = [int(x) for x in lines[0].split()]
    others = [p for p in range(1, 35) if p not in first]
    lines.append(" ".join(str(x) for x in first[:3] + others[:2]))   # shares 3 of 5 positions: distance 4 < 6
    r = check_text(checker, "cw-34-6-5", "\n".join(lines) + "\n")
    assert r.verdict == "not_certified"


def test_covering_missing_block_fails(checker):
    lines = ref("ours_covering_36-6-2.txt").decode().splitlines()
    r = check_text(checker, "covering-36-6-2", "\n".join(lines[1:]) + "\n")
    assert r.verdict == "not_certified" and "uncovered" in r.reason


def test_covering_m_design_missing_block_fails(checker):
    lines = ref("ours_covering_17-7-4-6.txt").decode().splitlines()
    r = check_text(checker, "covering-17-7-4-6", "\n".join(lines[:-1]) + "\n")
    assert r.verdict == "not_certified"


def test_covering_point_out_of_range_fails(checker):
    lines = ref("ours_covering_36-6-2.txt").decode().splitlines()
    pts = lines[0].split()
    pts[0] = "37"
    lines[0] = " ".join(pts)
    r = check_text(checker, "covering-36-6-2", "\n".join(lines) + "\n")
    assert r.verdict == "not_certified" and "invalid block" in r.reason


def test_spherical_code_missing_point_fails(checker):
    lines = [x for x in ref("ours_sphere_d8_n119.txt").decode().splitlines() if x.count(",") == 7]
    r = check_text(checker, "sphere-d8-n119", "\n".join(lines[1:]) + "\n")
    assert r.verdict == "not_certified" and "118 points" in r.reason


def test_spherical_code_with_a_repeated_point_scores_one(checker):
    lines = [x for x in ref("ours_sphere_d8_n119.txt").decode().splitlines() if x.count(",") == 7]
    lines[1] = lines[0]
    r = check_text(checker, "sphere-d8-n119", "\n".join(lines) + "\n")
    assert r.verdict == "certified" and r.value == "1" and r.improves_page_best is False


def test_autocorrelation_1a_flat_and_negative(checker):
    r = check_text(checker, "1a-upper", '{"values": [1, 1, 1, 1]}')
    assert r.verdict == "certified" and r.value == "2" and r.standing == "below the best known"
    assert obb_verdicts(r) == ["does not improve", "does not improve", "does not improve"]   # v2.1: two in review
    r = check_text(checker, "1a-upper", '{"values": [1, -1, 1, 1]}')
    assert r.verdict == "not_certified" and "non-negative" in r.reason


def test_autocorrelation_1c_small_and_corrupted(checker):
    r = check_text(checker, "1c-lower", '{"K": 2, "weights_int": [1, 1, 1]}')
    assert r.verdict == "certified" and r.value == "2/9" and r.improves_page_best is False
    for bad in ('{"K": 2, "weights_int": [1, -1, 1]}', '{"K": 2, "weights_int": [1, 0.5, 1]}', '{"K": 2}', "not json"):
        assert check_text(checker, "1c-lower", bad).verdict == "not_certified", bad


def test_autocorrelation_1d_zero_integral_fails(checker):
    assert check_text(checker, "1d-upper", '{"values": [1, 2, 1]}').verdict == "certified"
    r = check_text(checker, "1d-upper", '{"values": [1, -1]}')
    assert r.verdict == "not_certified" and "integral is zero" in r.reason


@pytest.mark.parametrize("pid", ["68a-lower", "42a-upper", "59a-upper", "16a-lower"])
def test_constant_checkers_refuse_garbage(checker, pid):
    for bad in ("{}", "[1, 2, 3]", "nonsense"):
        r = check_text(checker, pid, bad)
        assert r.verdict == "not_certified", (pid, bad)
        assert r.value is None and r.improves_page_best is None


def test_c16_verified_value_improves_the_page(checker):
    r = checker.check_data("16a-lower", ref("vid_c16_lower.json"))
    assert obb_verdicts(r) == ["IMPROVES", "does not improve"]
    assert r.value.endswith("/10000000000000000000000000000000000000000000000000")


def test_ramsey_pentagon_and_paley17(checker):
    r = check_text(checker, "ramsey-3-17", pentagon())
    assert r.verdict == "certified" and r.value == "5" and r.improves_page_best is False
    squares = {(x * x) % 17 for x in range(1, 17)}
    paley = "".join("".join("1" if i != j and (i - j) % 17 in squares else "0" for j in range(17)) + "\n"
                    for i in range(17))
    r = check_text(checker, "ramsey-4-15", paley)            # Paley(17): no K_4 in either colour
    assert r.verdict == "certified" and r.value == "17"


def test_ramsey_red_triangle_fails(checker):
    rows = [list(x) for x in pentagon().split()]
    rows[0][2] = rows[2][0] = "1"                          # 0-1-2 becomes a red triangle
    r = check_text(checker, "ramsey-3-17", "\n".join("".join(x) for x in rows) + "\n")
    assert r.verdict == "not_certified" and "red K_3" in r.reason


@pytest.mark.parametrize("mutate,why", [
    (lambda rows: rows[0].__setitem__(1, "0"), "not symmetric"),
    (lambda rows: (rows[3].__setitem__(3, "1")), "diagonal"),
    (lambda rows: rows.pop(), "rows of"),
])
def test_ramsey_malformed_matrix_fails(checker, mutate, why):
    rows = [list(x) for x in pentagon().split()]
    mutate(rows)
    r = check_text(checker, "ramsey-3-17", "\n".join("".join(x) for x in rows) + "\n")
    assert r.verdict == "not_certified" and why in r.reason


def test_ramsey_rows_past_the_c_limit_are_rejected_before_running(checker):
    r = check_text(checker, "ramsey-3-17", ("0" * 2049 + "\n") * 3)
    assert r.verdict == "not_certified" and r.checker.exit_code is None and "2048" in r.reason
    assert ramsey_precheck(b"x" + b"0" * 4200) is not None    # the C checker's second fgets chunk: 2055 zeros
    assert ramsey_precheck(b"x" * 10 + b"0" * 3000) is None   # its second chunk holds 955 zeros only
    assert ramsey_precheck(pentagon().encode()) is None


def test_vendored_ramsey_checker_rejects_a_wide_row_itself(checker, tmp_path):
    """Red control on the C checker alone (benchmark commit 3635207): a 2,050-character row gets its exit-2 error.
    It runs directly, as the server's own guard stops such a file before the checker."""
    wide = tmp_path / "wide.txt"
    wide.write_text("0" * 2050 + "\n")
    r = sandbox.run([str(checker.ramsey_binary()), "3", "17", str(wide)], cwd=tmp_path,
                    limits=sandbox.Limits(timeout_s=60, memory_mb=256))
    assert r.exit_code == 2 and "rows wider than 2048 are not supported" in r.stderr
    assert value_from_output("ramsey", r.exit_code, r.stdout, r.stderr) is None
    p = checker.bench.problems["ramsey-3-17"]
    assert Checker.failure_reason(p, r.exit_code, r.stdout, r.stderr) == \
        "the file is not a valid matrix: rows wider than 2048 are not supported"


# ------------------------------------------------------------------------------------- routing (mini benchmark)


@pytest.fixture
def mini(tmp_path, cache_dir):
    root = make_mini_benchmark(tmp_path / "bench", extra_checkers={
        "sleep_check.py": "import time\ntime.sleep(60)\n",
        "hog_check.py": "b = bytearray(1500 * 2**20)\nimport time\ntime.sleep(30)\n",
    }, extra_problems=[
        {"id": "slow-test", "title": "t", "page": "t", "statement": "t", "objective": "maximize", "submission": "Text",
         "checker": {"program": "sleep_check.py", "args": [], "value": "words"},
         "best_known": {"value": "1", "exact": "1", "source": "t"}, "verified_pending": []},
        {"id": "hog-test", "title": "t", "page": "t", "statement": "t", "objective": "maximize", "submission": "Text",
         "checker": {"program": "hog_check.py", "args": [], "value": "words"},
         "best_known": {"value": "1", "exact": "1", "source": "t"}, "verified_pending": []},
    ])
    s = Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=60, memory_mb=256)
    return Checker(Store(benchmark=Benchmark(root)), s)


TINY_SOLUTION = "Route #1: 1 2\nRoute #2: 3 4\nCost 39\n"   # 5 + 5 + 10 = 20 (load 9); 5 + 9 + 5 = 19 (load 9)


def test_routing_valid_solution_is_certified(mini):
    r = mini.check("cvrp-tiny", certificate=TINY_SOLUTION)
    assert r.verdict == "certified" and r.value == "39" and r.improves_page_best is False
    assert mini.compare("cvrp-tiny", Fraction(38)).improves_page_best
    assert not mini.compare("cvrp-tiny", Fraction(39)).improves_page_best


@pytest.mark.parametrize("bad,why", [
    ("Route #1: 1 2\nRoute #2: 3\n", "not visited exactly once"),          # customer 4 missing
    ("Route #1: 1 2 3 4\n", "capacity"),                                    # load 18 > 10
    ("Route #1: 1 2\nRoute #2: 3 4\nRoute #3: 4\n", "not visited exactly once"),
    ("Route #1: 1 2 9\nRoute #2: 3 4\n", "out of range"),
])
def test_routing_red_controls(mini, bad, why):
    r = mini.check("cvrp-tiny", certificate=bad)
    assert r.verdict == "not_certified" and why in r.reason


def test_routing_instance_with_wrong_hash_is_refused(mini):
    (mini.bench.root / "instances" / "tiny.vrp").write_text("NAME : changed\n")
    with pytest.raises(CheckError, match="SHA-256"):
        mini.check("cvrp-tiny", certificate=TINY_SOLUTION)


def test_routing_without_instances_says_how_to_get_them(checker):
    with pytest.raises(CheckError, match="QUANTAVANE_MCP_INSTANCES"):
        checker.check_data("cvrp-antwerp1", ref("ours_cvrp_Antwerp1.sol"))


def test_timeout_gives_no_verdict(mini):
    r = mini.check("slow-test", certificate="x\n", timeout_s=2)
    assert r.verdict == "no_verdict" and "timeout" in r.reason and r.value is None


def test_memory_cap_gives_no_verdict(mini):
    from quantavane_mcp import sandbox
    if sandbox.memory_cap_mode() is None:
        pytest.skip("no memory cap on this platform")
    r = mini.check("hog-test", certificate="x\n", timeout_s=30)
    assert r.verdict == "no_verdict" and "memory" in r.reason


# ------------------------------------------------------------------------------------- inputs


def test_exactly_one_certificate_source(checker, tmp_path):
    with pytest.raises(CheckError, match="exactly one"):
        checker.check("cw-34-6-5")
    p = tmp_path / "c.txt"
    p.write_bytes(ref("ours_cw_34_6_5.txt"))
    with pytest.raises(CheckError, match="exactly one"):
        checker.check("cw-34-6-5", certificate="1 2 3 4 5", certificate_path=str(p))


def test_certificate_path_inside_roots(checker, tmp_path):
    p = tmp_path / "c.txt"
    p.write_bytes(ref("ours_cw_34_6_5.txt"))
    r = checker.check("cw-34-6-5", certificate_path=str(p))
    assert r.verdict == "certified" and r.value == "528"


def test_certificate_path_outside_roots_is_refused(checker):
    target = DATA_DIR / "benchmark" / "refs" / "ours_cw_34_6_5.txt"
    with pytest.raises(CheckError, match="allowed folder"):
        checker.check("cw-34-6-5", certificate_path=str(target))


def test_symlink_out_of_the_roots_is_refused(checker, tmp_path):
    link = tmp_path / "link.txt"
    link.symlink_to(DATA_DIR / "benchmark" / "refs" / "ours_cw_34_6_5.txt")
    with pytest.raises(CheckError, match="allowed folder"):
        checker.check("cw-34-6-5", certificate_path=str(link))


def test_hidden_and_missing_and_folder_paths_are_refused(checker, tmp_path):
    hidden = tmp_path / ".secret" / "c.txt"
    hidden.parent.mkdir()
    hidden.write_text("1 2 3 4 5\n")
    with pytest.raises(CheckError, match="Hidden"):
        checker.check("cw-34-6-5", certificate_path=str(hidden))
    with pytest.raises(CheckError, match="No such file"):
        checker.check("cw-34-6-5", certificate_path=str(tmp_path / "nope.txt"))
    with pytest.raises(CheckError, match="Not a regular file"):
        checker.check("cw-34-6-5", certificate_path=str(tmp_path))


def test_size_limits(store, tmp_path, cache_dir):
    small = Checker(store, Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, max_bytes=100))
    with pytest.raises(CheckError, match="larger than"):
        small.check("cw-34-6-5", certificate="1 2 3 4 5\n" * 20)
    p = tmp_path / "big.txt"
    p.write_text("1 2 3 4 5\n" * 20)
    with pytest.raises(CheckError, match="larger than"):
        small.check("cw-34-6-5", certificate_path=str(p))
    with pytest.raises(CheckError, match="empty"):
        small.check("cw-34-6-5", certificate="   \n")


def test_unknown_problem_suggests_ids(checker):
    with pytest.raises(CheckError, match="cw-34-6-5"):
        checker.check("cw-34-6-55", certificate="1 2 3 4 5")


def test_timeout_bounds(checker):
    with pytest.raises(CheckError, match="timeout_s"):
        checker.check("cw-34-6-5", certificate="1 2 3 4 5", timeout_s=10**6)


# ------------------------------------------------------------------------------------- integrity and hygiene


def test_modified_bundled_checker_is_refused(tmp_path, cache_dir):
    data = tmp_path / "data"
    shutil.copytree(DATA_DIR, data)
    with open(data / "benchmark" / "checkers" / "cw_check.py", "a") as f:
        f.write("\n# changed\n")
    c = Checker(Store(benchmark=Benchmark(data_dir=data)), Settings(cache_dir=cache_dir))
    with pytest.raises(CheckError, match="differ from the benchmark release"):
        c.check_data("cw-34-6-5", ref("ours_cw_34_6_5.txt"))


def test_output_has_no_local_paths(checker):
    r = check_text(checker, "1c-lower", '{"K": 2, "weights_int": [1, 1, 1]}')
    tail = r.checker.output_tail
    assert "<candidate>" in tail
    assert str(Path.home()) not in tail and "quantavane-check-" not in tail
    assert "obb.py check 1c-lower" in r.reproduce and META["commit"][:7] in r.reproduce
