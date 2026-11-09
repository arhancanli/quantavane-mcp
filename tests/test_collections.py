"""Benchmark 2.1's collections: Prestige 100 (pages over single problems) and the Quantavane Originals (problems with
their own checkers), bundled byte for byte, listed, shown and checked in the sandbox as obb.py checks them."""
import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from quantavane_mcp.checking import CheckError, obb_verdicts, standalone_command
from quantavane_mcp.config import Settings
from quantavane_mcp.server import build_server


def test_both_collections_are_bundled(store):
    b = store.benchmark
    assert set(b.collections) == {"originals", "prestige100"}
    pres, orig = b.collections["prestige100"], b.collections["originals"]
    assert len(pres.entries) == 100 and [e["slot"] for e in pres.entries] == list(range(1, 101))
    assert len(orig.problems) == 39 == len(orig.entries) == b.meta["collections"]["originals"]["problems"]
    assert all(p.collection == "originals" and p.family == "originals" for p in orig.problems.values())
    assert len(orig.dropped) >= 1 and all(pres.page(e["id"]) for e in pres.entries)


def test_prestige_problems_are_single_problems_with_the_same_record(store):
    """As the benchmark's build_prestige100.py --check: every slot is a single problem whose best known value is the
    record the collection lists."""
    b = store.benchmark
    for e in b.collections["prestige100"].entries:
        p = b.problems[e["id"]]
        assert p.best_known["value"] == e["best_known_value"], e["id"]
        assert p.checker == e["checker"], e["id"]


def test_originals_are_found_like_obb(store):
    b = store.benchmark
    p = b.find("qr-sumfree")
    assert p is not None and p.checker["program"] == "collections/originals/checkers/orig_numth.py"
    assert b.program_path(p.checker["program"]).is_file()
    assert standalone_command(p) == "python3 -I collections/originals/checkers/orig_numth.py qr-sumfree 1009 FILE"
    with pytest.raises(Exception):
        b.inside("../etc/passwd")
    with pytest.raises(Exception):
        b.inside("checkers/../../x")


@pytest.mark.slow
def test_every_original_certificate_is_certified_with_its_value(checker, store):
    """test_originals.py, part 1, through the sandbox: each problem's own certificate gives exactly the stated best
    known value, and obb.py would say it does not improve (it is the best known value)."""
    b = store.benchmark
    for pid, p in b.collections["originals"].problems.items():
        (ref,) = b.references[pid]
        r = checker.check_data(pid, ref.path.read_bytes())
        assert r.verdict == "certified" and r.value == p.best_known["exact"], (pid, r.reason)
        assert obb_verdicts(r) == ["does not improve"] and r.standing == "equals the best known", pid
        assert r.collection == "originals" and "obb.py check " + pid in r.reproduce


def test_originals_red_controls_are_refused(checker, store):
    """test_originals.py, part 2 (three of its controls): a broken certificate is refused."""
    b = store.benchmark

    def own(pid):
        return b.references[pid][0].path.read_text()
    toks = own("potts3-600").split()
    assert checker.check_data("potts3-600", (" ".join(["3"] + toks[1:]) + "\n").encode()).verdict == "not_certified"
    w = "".join(line for line in own("sync-quadratic").splitlines() if line.strip() and not line.startswith("#"))
    assert checker.check_data("sync-quadratic", (w[:-1] + "\n").encode()).verdict == "not_certified"
    t = own("cell600-idcode").split()
    assert checker.check_data("cell600-idcode", (" ".join(t[:-6]) + "\n").encode()).verdict == "not_certified"


def test_tampered_collection_checker_is_refused(checker, store, monkeypatch):
    p = store.benchmark.find("qr-sumfree")
    real = store.manifest.files["benchmark/" + p.checker["program"]]
    monkeypatch.setitem(store.manifest.files, "benchmark/" + p.checker["program"], dict(real, sha256="0" * 64))
    with pytest.raises(CheckError, match="differ from the benchmark release"):
        checker.check_data("qr-sumfree", b"1 2 4\n")


@pytest.fixture
def server(tmp_path, cache_dir, store):
    return build_server(Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=300), store)


async def call(server, name, args):
    async with create_connected_server_and_client_session(server) as client:
        return await client.call_tool(name, args)


@pytest.mark.anyio
async def test_list_and_get_collection_problems(server):
    r = await call(server, "list_collection", {"collection": "prestige100", "group": "kissing", "limit": 5})
    s = r.structuredContent
    assert not r.isError and s["total"] == 25 and s["count"] == 5 and s["entries"][0]["id"] == "kissing-d5"
    assert {c["name"] for c in s["collections"]} == {"prestige100", "originals"}
    r = await call(server, "list_collection", {"collection": "originals", "group": "physics"})
    assert r.structuredContent["total"] == 5 and all(e["field"] == "Physics" for e in r.structuredContent["entries"])
    r = await call(server, "get_collection_problem", {"collection": "prestige100", "problem": "17"})
    s = r.structuredContent
    assert s["id"] == "ramsey-5-15" and s["entry"]["record"] == "R(5,15) ≥ 283"
    assert s["leaderboard"]["record"]["value"] == "282" and "check_candidate" in s["check_with"]
    r = await call(server, "get_collection_problem", {"collection": "originals", "problem": "qr-sumfree"})
    s = r.structuredContent
    assert s["entry"]["novelty"]["verdict"].startswith("new") and s["leaderboard"] is None
    r = await call(server, "get_collection_problem", {"collection": "originals", "problem": "no-such-problem"})
    assert r.isError and "list_collection" in r.content[0].text


@pytest.mark.anyio
async def test_get_problem_and_check_an_original(server, store):
    r = await call(server, "get_problem", {"problem_id": "qr-sumfree"})
    s = r.structuredContent
    assert not r.isError and s["collection"] == "originals" and s["family"] == "originals"
    assert s["collection_info"]["field"] == "Number theory" and s["collection_info"]["first_values"]["rows"]
    assert s["page"].endswith("collections/originals/problems/qr-sumfree.md")
    assert s["reference_certificates"][0]["uri"] == "quantavane://collections/originals/refs/qr-sumfree.txt"
    assert s["second_checker"] is None
    ref = store.benchmark.references["qr-sumfree"][0].path.read_text()
    r = await call(server, "check_candidate", {"problem_id": "qr-sumfree", "certificate": ref})
    assert r.structuredContent["verdict"] == "certified" and r.structuredContent["value"] == "174"
    r = await call(server, "compare_to_record", {"problem_id": "qr-sumfree", "value": "175"})
    assert r.structuredContent["improves_page_best"] is True


@pytest.mark.anyio
async def test_collection_resources(server):
    async with create_connected_server_and_client_session(server) as client:
        templates = {t.uriTemplate for t in (await client.list_resource_templates()).resourceTemplates}
        index = (await client.read_resource("quantavane://collections")).contents[0].text
        readme = (await client.read_resource("quantavane://collections/originals")).contents[0].text
        page = (await client.read_resource("quantavane://collections/prestige100/ramsey-5-5")).contents[0].text
        slot = (await client.read_resource("quantavane://collections/prestige100/1")).contents[0].text
        cert = (await client.read_resource("quantavane://collections/originals/refs/qr-sumfree.txt")).contents[0].text
        docs = (await client.read_resource("quantavane://checkers/orig_numth.py")).contents[0].text
        checkers = (await client.read_resource("quantavane://checkers")).contents[0].text
        changes = (await client.read_resource("quantavane://benchmark/changelog")).contents[0].text
        about = json.loads((await client.read_resource("quantavane://about")).contents[0].text)
    assert {"quantavane://collections/{name}", "quantavane://collections/{name}/{problem_id}",
            "quantavane://collections/{name}/refs/{filename}"} <= templates
    assert "prestige100" in index and "Originals" in readme and "R(5,5)" in page and page == slot
    assert cert.strip() and "qr-sumfree" in docs and "orig_numth.py** (originals)" in checkers
    assert "## 2.1" in changes and about["benchmark_version"] == "2.1"
