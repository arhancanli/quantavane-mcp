"""Helpers shared by the tests: bundled reference certificates, small certificates and a mini benchmark."""
import hashlib
import json
import shutil
from pathlib import Path

from quantavane_mcp.data import DATA_DIR

BUNDLED = DATA_DIR / "benchmark"


def ref(name: str) -> bytes:
    return (BUNDLED / "refs" / name).read_bytes()


def pentagon() -> str:
    """The 5-cycle in red, its complement in blue: no red triangle, no blue triangle (R(3,3) > 5)."""
    return "".join("".join("1" if (j - i) % 5 in (1, 4) else "0" for j in range(5)) + "\n" for i in range(5))


# A tiny CVRPLIB-format instance (EUC_2D, depot node 1, capacity 10) and a mini benchmark around it, so the routing
# pipeline, the instance hash check and the routing red controls run without CVRPLIB's files.
TINY_VRP = """NAME : tiny
TYPE : CVRP
DIMENSION : 5
EDGE_WEIGHT_TYPE : EUC_2D
CAPACITY : 10
NODE_COORD_SECTION
1 0 0
2 3 4
3 6 8
4 -3 4
5 0 -5
DEMAND_SECTION
1 0
2 4
3 5
4 6
5 3
DEPOT_SECTION
1
-1
EOF
"""


def make_mini_benchmark(root: Path, *, extra_checkers: dict | None = None, extra_problems: list | None = None) -> Path:
    """problems/ with one routing problem (cvrp-tiny) plus extras, checkers/ copied from the bundle, and a fetch.sh
    pinning the tiny instance's SHA-256."""
    (root / "problems").mkdir(parents=True)
    shutil.copytree(BUNDLED / "checkers", root / "checkers")
    for name, text in (extra_checkers or {}).items():
        (root / "checkers" / name).write_text(text)
    (root / "instances").mkdir()
    (root / "instances" / "tiny.vrp").write_text(TINY_VRP)
    digest = hashlib.sha256(TINY_VRP.encode()).hexdigest()
    (root / "fetch.sh").write_text(f"slow tiny.vrp https://example.invalid/tiny {digest}\n")
    problems = [{
        "id": "cvrp-tiny", "title": "Vehicle routing: a tiny test instance", "page": "test", "statement": "test",
        "objective": "minimize", "submission": "Text file in CVRPLIB's solution format",
        "checker": {"program": "cvrp_check.py", "args": ["instances/tiny.vrp"], "value": "cvrp"},
        "best_known": {"value": "39", "exact": "39", "source": "test fixture, read 8 Nov 2026"},
        "verified_pending": [],
    }] + (extra_problems or [])
    for p in problems:
        (root / "problems" / f"{p['id']}.json").write_text(json.dumps(p))
    return root
