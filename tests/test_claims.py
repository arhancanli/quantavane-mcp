"""run_claim_checks: the claim pipeline offline (two separately written checkers, red controls, the keeper's value on
file) on bundled certificates, forged ones, a problem without a second checker, the MCP tool and the command line."""
import json
import subprocess
import sys

import pytest
from helpers import ref
from mcp.shared.memory import create_connected_server_and_client_session

from quantavane_mcp import claims
from quantavane_mcp.claims import run_claim
from quantavane_mcp.config import Settings
from quantavane_mcp.server import build_server


def test_verified_but_not_a_record(checker):
    c = run_claim(checker, "covering-17-7-4-6", ref("ours_covering_17-7-4-6.txt"))
    assert c.verified and not c.record and c.verdict.startswith("NOT-A-RECORD (17 vs listed 17;")
    assert c.second_checker == "second_check.py covering" and c.red_controls == 1
    assert [x.kind for x in c.checks] == ["check", "check", "red", "red"] and all(x.as_expected for x in c.checks)
    assert c.beats_keeper_value_on_file is False and c.keeper.value == "17" and "offline" in c.keeper.re_read
    assert set(c.packet) == {"VERDICT", "checks.txt", "keeper.txt", "literature.json", "README.md"}
    assert "VERIFIED" in c.packet["checks.txt"] and c.packet["VERDICT"].startswith("NOT-A-RECORD")
    assert all(q.backend == "stub" for q in c.literature) and len(c.certificate_sha256) == 64


def test_record_against_the_value_on_file(checker):
    """Our (6,9)-graph on 5,600 vertices beats the 7,781 the problem file holds: RECORD, with the re-read reminder."""
    c = run_claim(checker, "cage-6-9", ref("ours_cage_6_9_n5600.s6"))
    assert c.verified and c.record and c.verdict.startswith("RECORD (5600 vs listed 7781;")
    assert "re-read the keeper today" in c.verdict and c.beats_keeper_value_on_file is True


def test_spherical_code_claim(checker):
    c = run_claim(checker, "sphere-d8-n119", ref("ours_sphere_d8_n119.txt"))
    assert c.verified and c.second_checker == "second_check.py sph" and c.verdict.startswith("NOT-A-RECORD (0.4588")


def test_forged_object_is_not_verified(checker):
    lines = ref("ours_covering_17-7-4-6.txt").decode().splitlines()
    c = run_claim(checker, "covering-17-7-4-6", ("\n".join(lines[1:]) + "\n").encode())    # one block removed
    assert not c.verified and not c.record and c.verdict.startswith("NOT VERIFIED")
    assert c.checks[0].verdict == "not_certified" and c.checks[1].verdict == "not_certified"


def test_no_second_checker_is_not_verified(checker, store):
    data = store.benchmark.references["qr-sumfree"][0].path.read_bytes()
    c = run_claim(checker, "qr-sumfree", data)
    assert c.verdict == "NOT VERIFIED (only one checker for this problem)" and c.second_checker is None
    assert c.checks[0].verdict == "certified" and c.value == "174" and "no second checker" in c.notes[0]


def test_a_red_control_that_passes_makes_it_not_verified(checker, monkeypatch):
    monkeypatch.setitem(claims.RED, "covering", lambda p, text: [("the object unchanged", text.encode())])
    c = run_claim(checker, "covering-17-7-4-6", ref("ours_covering_17-7-4-6.txt"))
    assert not c.verified and "red control passed" in c.verdict
    assert [x.as_expected for x in c.checks if x.kind == "red"] == [False, False]


@pytest.mark.anyio
async def test_the_tool(tmp_path, cache_dir, store):
    server = build_server(Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=300), store)
    cert = tmp_path / "code.txt"
    cert.write_bytes(ref("ours_cw_34_6_5.txt"))
    async with create_connected_server_and_client_session(server) as client:
        r = await client.call_tool("run_claim_checks", {"problem_id": "cw-34-6-5", "certificate_path": str(cert)})
        bad = await client.call_tool("run_claim_checks", {"problem_id": "cw-34-6-5"})
        prompt = await client.get_prompt("prepare_claim", {"problem_id": "cw-34-6-5"})
    s = r.structuredContent
    assert not r.isError and s["verified"] and s["verdict"].startswith("NOT-A-RECORD (528 vs listed 528;")
    assert bad.isError and "exactly one of" in bad.content[0].text
    assert "run_claim_checks" in prompt.messages[0].content.text


def test_command_line(tmp_path):
    cert = tmp_path / "design.txt"
    cert.write_bytes(ref("ours_covering_17-7-4-6.txt"))
    r = subprocess.run([sys.executable, "-m", "quantavane_mcp", "claim", "covering-17-7-4-6", str(cert)],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 1 and json.loads(r.stdout)["verified"] is True        # 1: verified, not a record
