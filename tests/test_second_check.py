"""The second checkers (independent/second_check.py): known objects with their exact values, broken ones refused, and
the same value as the benchmark's checker on the bundled reference certificates."""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from helpers import pentagon, ref

from quantavane_mcp.claims import SECOND, red_controls

PETERSEN = "0 1\n1 2\n2 3\n3 4\n4 0\n0 5\n1 6\n2 7\n3 8\n4 9\n5 7\n7 9\n9 6\n6 8\n8 5\n"
STRASSEN = {"field": "Q", "terms": [
    [[[1, 0], [0, 1]], [[1, 0], [0, 1]], [[1, 0], [0, 1]]],
    [[[0, 0], [1, 1]], [[1, 0], [0, 0]], [[0, 0], [1, -1]]],
    [[[1, 0], [0, 0]], [[0, 1], [0, -1]], [[0, 1], [0, 1]]],
    [[[0, 0], [0, 1]], [[-1, 0], [1, 0]], [[1, 0], [1, 0]]],
    [[[1, 1], [0, 0]], [[0, 0], [0, 1]], [[-1, 1], [0, 0]]],
    [[[-1, 0], [1, 0]], [[1, 1], [0, 0]], [[0, 0], [0, 1]]],
    [[[0, 1], [0, -1]], [[0, 0], [1, 1]], [[1, 0], [0, 0]]]]}

KNOWN = [  # kind, args, object, exact value
    ("ramsey", ["3", "3"], pentagon(), "5"),
    ("multiramsey", ["3", "3"], pentagon().replace("1", "x").replace("0", "1").replace("x", "0"), "5"),
    ("schur", ["schur", "2"], "0110", "4"),
    ("schur", ["weak", "2"], "00101110", "8"),
    ("vdw", ["2", "3"], "00110011", "8"),
    ("covering", ["5", "3", "2", "2"], "1 2 3\n1 4 5\n2 4 5\n3 4 5\n", "4"),
    ("cw", ["6", "4", "3"], "1 2 3\n1 4 5\n2 4 6\n3 5 6\n", "4"),
    ("kissing", ["2"], "1 -1 0\n-1 1 0\n1 0 -1\n-1 0 1\n0 1 -1\n0 -1 1\n", "6"),   # A2 written in 3 coordinates
    ("golomb", ["4"], "0 1 4 6", "6"),
    ("sortnet", ["4"], "0 1\n2 3\n0 2\n1 3\n1 2\n", "5"),
    ("capset", ["2"], "00 01 10 11", "4"),
    ("no3line", ["3"], "0,1 0,2 1,0 1,2 2,0 2,1", "6"),
    ("hadamard", ["4"], "++++\n+-+-\n++--\n+--+\n", "1"),
    ("cwm", ["4", "4"], "-1 1 1 1", "1"),
    ("costas", ["3"], "1 3 2", "1"),
    ("mols", ["3"], "0 1 2\n1 2 0\n2 0 1\n\n0 1 2\n2 0 1\n1 2 0\n", "2"),
    ("projplane", ["2"], "0 1 3\n1 2 4\n2 3 5\n3 4 6\n4 5 0\n5 6 1\n6 0 2\n", "1"),
    ("srg", ["10", "3", "0", "1"], PETERSEN, "1"),
    ("cage", ["3", "5"], PETERSEN, "10"),
    ("degdiam", ["3", "2"], PETERSEN, "10"),
    ("snake", ["snake", "3"], "0120", "4"),
    ("snake", ["coil", "3"], "012012", "6"),
    ("superperm", ["3"], "123121321", "9"),
    ("strongpow", ["5", "2"], "00 12 24 31 43", "5"),
    ("lincode", ["2", "7", "4"], "1000110\n0100101\n0010011\n0001111\n", "3"),
    ("lincode", ["3", "4", "2"], "1 0 1 1\n0 1 1 2\n", "3"),
    ("lincode", ["4", "6", "3"], "1 0 0 1 2 2\n0 1 0 2 1 2\n0 0 1 2 2 1\n", "4"),     # the hexacode over GF(4)
    ("ca", ["2", "3", "2"], "000\n011\n101\n110\n", "4"),
    ("matmul", ["2", "2", "2", "any"], json.dumps(STRASSEN), "7"),
]


def second(kind, args, text, tmp_path):
    f = tmp_path / "object.txt"
    f.write_text(text)
    r = subprocess.run([sys.executable, "-I", str(SECOND), kind, *args, str(f)], capture_output=True, text=True,
                       timeout=600)
    last = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else ""
    return r.returncode, last, r.stdout


@pytest.mark.parametrize("kind,args,text,value", KNOWN, ids=[f"{k[0]}-{'-'.join(k[1])}" for k in KNOWN])
def test_known_objects(kind, args, text, value, tmp_path):
    code, last, out = second(kind, args, text, tmp_path)
    assert code == 0 and last == f"RESULT {value}", out


@pytest.mark.parametrize("kind,args,text", [
    ("ramsey", ["3", "3"], "01111\n10000\n10000\n10000\n10000\n"),              # a blue triangle among 1..4
    ("kissing", ["2"], "1 -1 0\n-1 1 0\n1 0 -1\n-1 0 1\n0 1 -1\n0 -1 1\n1 1 -2\n"),   # norms differ
    ("kissing", ["2"], "1 -1 0\n-1 1 0\n1 0 -1\n-1 0 1\n0 1 -1\n0 -1 1\n1 -1 0\n"),   # a vector twice
    ("schur", ["schur", "2"], "0000"),
    ("schur", ["weak", "2"], "000"),
    ("vdw", ["2", "3"], "000"),
    ("covering", ["5", "3", "2", "2"], "1 2 3\n1 4 5\n2 4 5\n"),
    ("cw", ["6", "4", "3"], "1 2 3\n1 2 4\n"),
    ("golomb", ["4"], "0 1 2 4"),
    ("sortnet", ["4"], "0 1\n2 3\n0 2\n1 3\n"),
    ("capset", ["2"], "00 11 22"),
    ("no3line", ["3"], "0,0 1,1 2,2"),
    ("hadamard", ["4"], "++++\n++++\n++--\n+--+\n"),
    ("cwm", ["4", "4"], "1 1 1 1"),
    ("costas", ["3"], "1 2 3"),
    ("mols", ["3"], "0 1 2\n1 2 0\n2 0 1\n\n0 1 2\n1 2 0\n2 0 1\n"),
    ("projplane", ["2"], "0 1 3\n0 1 3\n2 3 5\n3 4 6\n4 5 0\n5 6 1\n6 0 2\n"),
    ("srg", ["10", "3", "0", "1"], PETERSEN.replace("8 5\n", "")),
    ("cage", ["3", "6"], PETERSEN),                                              # girth 5, not 6
    ("degdiam", ["3", "1"], PETERSEN),
    ("snake", ["snake", "3"], "00"),
    ("snake", ["coil", "3"], "0120"),
    ("superperm", ["3"], "1231213"),
    ("strongpow", ["5", "2"], "00 11"),
    ("tree_unimodal", [], "0 1\n1 2\n2 3\n"),
    ("lincode", ["2", "7", "4"], "1000110\n1000110\n0010011\n0001111\n"),
    ("ca", ["2", "3", "2"], "000\n011\n101\n"),
    ("matmul", ["2", "2", "2", "any"], json.dumps(dict(STRASSEN, terms=STRASSEN["terms"][:6]))),
    ("matmul", ["2", "2", "2", "char0"], json.dumps(dict(STRASSEN, field="GF(2)"))),
])
def test_broken_objects_are_refused(kind, args, text, tmp_path):
    code, last, out = second(kind, args, text, tmp_path)
    assert code == 1 and out.startswith("INVALID") or "INVALID" in out, out


def test_limits_give_no_verdict(tmp_path):
    code, last, out = second("sph", ["2", "2", "1/2"], "1, 0\n0, 1\n", tmp_path)
    assert code == 1                          # cosine 0 is not within 1e-20 of the claimed 1/2
    code, last, out = second("sph", ["2", "2", "0"], "1, 0\n0, 1\n", tmp_path)
    assert code == 0 and last == "RESULT 0"
    code, last, out = second("lincode", ["2", "40", "39"], "\n".join("1" * 40 for _ in range(39)), tmp_path)
    assert code in (1, 2)
    code, last, out = second("nonsense", [], "x", tmp_path)
    assert code == 2


@pytest.mark.parametrize("pid,name,args", [
    ("covering-17-7-4-6", "ours_covering_17-7-4-6.txt", ["17", "7", "4", "6"]),
    ("cw-34-6-5", "ours_cw_34_6_5.txt", ["34", "6", "5"]),
    ("cw-27-4-6", "ours_cw_27_4_6.txt", ["27", "4", "6"]),
    ("multiramsey-4-4-4", "classic_multiramsey_444_n127.txt", ["4", "4", "4"]),
    ("kissing-d16", "classic_kissing_d16_BW16_n4320.txt", ["16"]),
    ("golomb-29", "classic_golomb_erdos_turan_m29.txt", ["29"]),
    ("sortnet-n24-size", "classic_sortnet_batcher_n24.txt", ["24"]),
    ("superperm-n8", "classic_superperm_n8.txt", ["8"]),
    ("shannon-c7-power5", "classic_shannon_c7_k5_n243.txt", ["7", "5"]),
    ("ramsey-3-18", "ours_ramsey_3_18_n100.txt", ["3", "18"]),
])
def test_same_value_as_the_benchmark_checker(checker, pid, name, args, tmp_path):
    data = ref(name)
    first = checker.check_data(pid, data)
    kind = Path(checker.bench.find(pid).checker["program"]).name.replace("_check.py", "").replace("_check", "")
    code, last, out = second(kind, args, data.decode(), tmp_path)
    assert first.verdict == "certified" and code == 0 and last == f"RESULT {first.value}", out


def test_spherical_code_confirms_the_first_value(checker, tmp_path):
    data = ref("ours_sphere_d8_n119.txt")
    first = checker.check_data("sphere-d8-n119", data)
    code, last, out = second("sph", ["8", "119", first.value], data.decode(), tmp_path)
    assert code == 0 and last == f"RESULT {first.value}"
    off = str(first.value_decimal).rstrip(".")[:-3] + "999"                        # 1e-18 above: refused
    code, last, out = second("sph", ["8", "119", off], data.decode(), tmp_path)
    assert code == 1


def test_red_controls_are_built_for_every_kind(store):
    b = store.benchmark
    cases = {"ramsey-3-17": pentagon().encode(), "covering-17-7-4-6": ref("ours_covering_17-7-4-6.txt"),
             "sphere-d8-n119": ref("ours_sphere_d8_n119.txt"), "golomb-29": ref("classic_golomb_erdos_turan_m29.txt"),
             "sortnet-n13-size": ref("classic_sortnet_batcher_n13.txt"), "cage-6-9": ref("ours_cage_6_9_n5600.s6")}
    for pid, data in cases.items():
        reds = red_controls(b.find(pid), data)
        assert reds and all(isinstance(why, str) and bad != data for why, bad in reds), pid
    assert red_controls(b.find("qr-sumfree"), b"1 2\n") == []                     # no second checker: no control
