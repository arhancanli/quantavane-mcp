"""The bundled data: integrity against the manifest, counts, and the lossless covering-array runs."""
import hashlib
import json

from quantavane_mcp.data import DATA_DIR, FAMILIES, Manifest


def test_manifest_matches_every_bundled_file():
    m = Manifest.load()
    assert m.verify() == []
    on_disk = {p.relative_to(DATA_DIR).as_posix() for p in DATA_DIR.rglob("*") if p.is_file()}
    assert on_disk - {"MANIFEST.json"} == set(m.files)


def test_sources_are_pinned_commits():
    s = Manifest.load().sources
    assert len(s["benchmark"]["commit"]) == 40 and len(s["replays"]["commit"]) == 40
    assert s["open_data"]["date"] == "2026-11-07"


def test_benchmark_has_117_problems_in_six_families(store):
    probs = store.benchmark.problems
    assert len(probs) == 117
    counts = {}
    for p in probs.values():
        counts[p.family] = counts.get(p.family, 0) + 1
    assert counts == {"constant": 7, "ramsey": 43, "spherical-code": 11, "covering-design": 10,
                      "vehicle-routing": 14, "constant-weight-code": 32}


def test_every_problem_names_an_existing_checker_and_a_dated_value(store):
    b = store.benchmark
    for p in b.problems.values():
        prog = p.checker["program"]
        assert (b.checkers_dir / (prog if prog.endswith(".py") else prog + ".c")).is_file(), p.id
        assert p.kind in FAMILIES
        assert p.objective in ("maximize", "minimize")
        assert p.file_date, p.id
        assert p.read_date() or p.page_commit(), p.id     # every best known value says when it was read


def test_reference_certificates_and_expectations(store):
    refs = store.benchmark.references
    files = {p.name for p in store.benchmark.refs_dir.iterdir()} - {"README.md"}
    assert {r.file for v in refs.values() for r in v} == files     # test.sh expects a verdict for every bundled ref
    assert sum(len(v) for v in refs.values()) == 69
    assert {r.file for r in refs["16a-lower"]} == {"maxr_c16_lower.json", "vid_c16_lower.json"}
    assert all(r.ours for r in refs["cw-34-6-6"])


def test_open_data_counts_match_totals(store):
    od = store.open_data
    assert len(od.records) == 1051
    assert od.totals["verified_results"] == od.totals["records_verified"] + od.totals["first_entries"]
    assert len(od.catools_rows) == od.totals["catools_rows_crediting_us"]


def test_covering_array_runs_are_lossless(store):
    """The runs expand to the published covering_array_entries.csv byte for byte (its SHA-256 is in the manifest)."""
    info = Manifest.load().sources["open_data"]["covering_array_entries_csv"]
    raw = store.open_data.expand_covering_array_csv()
    assert len(raw) == info["bytes"]
    assert hashlib.sha256(raw).hexdigest() == info["sha256"]
    assert info["rows"] == store.open_data.totals["covering_array_entries_listed"] == 206384


def test_replay_index_is_well_formed(store):
    idx = store.replays.index
    assert idx["sections"] and idx["asterisk_index"]["rows"]
    for s in idx["sections"]:
        assert s["heading"] and s["folders"] and s["summary"], s["heading"]
        assert (s["kind"] == "section") == bool(s["anchor"]), s["heading"]
        assert isinstance(s["prs"], list)
    assert json.loads((DATA_DIR / "replays" / "index.json").read_text())["commit"] == idx["commit"]
