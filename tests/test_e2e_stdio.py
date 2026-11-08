"""End to end: the installed server as a subprocess over stdio, driven by the MCP client, through every tool."""
import os
import sys

import pytest
from helpers import ref
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

TOOLS = {"list_problems", "get_problem", "check_candidate", "compare_to_record", "search_results", "get_replay", "cite"}


@pytest.mark.anyio
async def test_stdio_server_end_to_end(tmp_path, cache_dir):
    cert = tmp_path / "covering.txt"
    cert.write_bytes(ref("ours_covering_17-7-4-6.txt"))
    params = StdioServerParameters(command=sys.executable, args=["-m", "quantavane_mcp"], cwd=str(tmp_path),
                                   env={"QUANTAVANE_MCP_ROOTS": str(tmp_path.resolve()),
                                        "QUANTAVANE_MCP_CACHE": str(cache_dir),
                                        "PATH": os.environ.get("PATH", "/usr/bin:/bin")})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.serverInfo.name == "quantavane"
            assert "check_candidate" in (init.instructions or "")
            assert {t.name for t in (await session.list_tools()).tools} == TOOLS

            lp = await session.call_tool("list_problems", {"query": "covering", "limit": 3})
            assert lp.structuredContent["total"] == 10

            gp = await session.call_tool("get_problem", {"problem_id": "covering-17-7-4-6"})
            assert gp.structuredContent["best_known"]["value"] == "17"

            ok = await session.call_tool("check_candidate", {"problem_id": "covering-17-7-4-6",
                                                             "certificate_path": str(cert)})
            s = ok.structuredContent
            assert not ok.isError and s["verdict"] == "certified" and s["value"] == "17"
            assert s["improves_page_best"] is False and len(s["certificate_sha256"]) == 64

            lines = cert.read_text().splitlines()
            bad = await session.call_tool("check_candidate", {"problem_id": "covering-17-7-4-6",
                                                              "certificate": "\n".join(lines[1:]) + "\n"})
            assert bad.structuredContent["verdict"] == "not_certified"          # red control: a block removed

            cr = await session.call_tool("compare_to_record", {"problem_id": "covering-17-7-4-6", "value": "16"})
            assert cr.structuredContent["improves_page_best"] is True

            sr = await session.call_tool("search_results", {"cell": "C(17,7,4,6)"})
            assert sr.structuredContent["total"] >= 1

            rp = await session.call_tool("get_replay", {"pr": 292})
            assert rp.structuredContent["found"] is True

            ct = await session.call_tool("cite", {"target": "benchmark"})
            assert ct.structuredContent["bibtex"].startswith("@misc{")

            about = await session.read_resource("quantavane://about")
            assert '"network": "none' in about.contents[0].text

            pr = await session.get_prompt("attack_problem", {"problem_id": "covering-17-7-4-6"})
            assert "check_candidate" in pr.messages[0].content.text
