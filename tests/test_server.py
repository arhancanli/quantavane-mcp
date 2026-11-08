"""The MCP surface through a real client session (in memory): tools, schemas, errors, resources, prompts, completion."""
import json

import pytest
from helpers import pentagon
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import PromptReference, ResourceTemplateReference

from quantavane_mcp.config import Settings
from quantavane_mcp.server import build_server

TOOLS = {"list_problems", "get_problem", "check_candidate", "compare_to_record", "search_results", "get_replay", "cite"}


@pytest.fixture
def server(tmp_path, cache_dir, store):
    return build_server(Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, timeout_s=300), store)


async def call(server, name, args):
    async with create_connected_server_and_client_session(server) as client:
        return await client.call_tool(name, args)


@pytest.mark.anyio
async def test_tools_are_listed_with_schemas_and_read_only_annotations(server):
    async with create_connected_server_and_client_session(server) as client:
        init = client.get_server_capabilities()
        assert init is not None and init.tools is not None
        tools = (await client.list_tools()).tools
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.description and t.inputSchema["type"] == "object" and t.outputSchema, t.name
        assert t.annotations.readOnlyHint is True and t.annotations.openWorldHint is False, t.name
        assert t.title, t.name
    check = next(t for t in tools if t.name == "check_candidate")
    assert set(check.inputSchema["properties"]) == {"problem_id", "certificate", "certificate_path", "timeout_s"}
    assert check.inputSchema["required"] == ["problem_id"]


@pytest.mark.anyio
async def test_list_and_get_problem(server):
    r = await call(server, "list_problems", {"family": "ramsey", "limit": 5})
    s = r.structuredContent
    assert not r.isError and s["total"] == 43 and s["count"] == 5 and s["has_more"]
    assert s["families"]["spherical-code"] == 11
    r = await call(server, "get_problem", {"problem_id": "sphere-d3-n952"})
    s = r.structuredContent
    assert s["checker"]["program"] == "sph_check.py" and s["objective"] == "minimize"
    assert s["reference_certificates"][0]["uri"] == "quantavane://refs/ours_sphere_d3_n952.txt"
    assert "read 6 Nov 2026" in s["best_known"]["read"]
    r = await call(server, "get_problem", {"problem_id": "cvrp-antwerp1"})
    assert r.structuredContent["instance"]["file"] == "Antwerp1.vrp"


@pytest.mark.anyio
async def test_check_candidate_through_the_protocol(server):
    r = await call(server, "check_candidate", {"problem_id": "ramsey-3-17", "certificate": pentagon()})
    s = r.structuredContent
    assert not r.isError and s["verdict"] == "certified" and s["value"] == "5" and s["improves_page_best"] is False
    assert json.loads(r.content[0].text)["verdict"] == "certified"


@pytest.mark.anyio
async def test_check_candidate_errors_are_tool_errors(server):
    r = await call(server, "check_candidate", {"problem_id": "ramsey-3-17"})
    assert r.isError and "exactly one" in r.content[0].text
    r = await call(server, "check_candidate", {"problem_id": "../../etc/passwd", "certificate": "x"})
    assert r.isError                                         # the id pattern refuses it before any lookup
    r = await call(server, "check_candidate", {"problem_id": "ramsey-3-17", "certificate_path": "/etc/hosts"})
    assert r.isError and "allowed folder" in r.content[0].text


@pytest.mark.anyio
async def test_compare_search_replay_cite(server):
    r = await call(server, "compare_to_record", {"problem_id": "cw-34-6-6", "value": "2057"})
    assert r.structuredContent["improves_page_best"] is True
    r = await call(server, "compare_to_record", {"problem_id": "cw-34-6-6", "value": "lots"})
    assert r.isError
    r = await call(server, "search_results", {"cell": "R(5,15)"})
    assert r.structuredContent["results"][0]["slug"] == "r-5-15"
    r = await call(server, "search_results", {"date_from": "11/06/2026"})
    assert r.isError
    r = await call(server, "get_replay", {"pr": 297})
    assert r.structuredContent["found"] and r.structuredContent["matches"][0]["heading"].startswith("C59")
    r = await call(server, "cite", {"target": "result", "id": "r-5-15", "format": "bibtex"})
    assert r.structuredContent["bibtex"].startswith("@misc{") and r.structuredContent["text"] is None


@pytest.mark.anyio
async def test_resources(server):
    async with create_connected_server_and_client_session(server) as client:
        listed = {str(r.uri) for r in (await client.list_resources()).resources}
        templates = {t.uriTemplate for t in (await client.list_resource_templates()).resourceTemplates}
        about = json.loads((await client.read_resource("quantavane://about")).contents[0].text)
        prob = json.loads((await client.read_resource("quantavane://problems/1c-lower")).contents[0].text)
        docs = (await client.read_resource("quantavane://checkers/cw_check.py")).contents[0].text
        src = (await client.read_resource("quantavane://checkers/ramsey_check/source")).contents[0].text
        refc = (await client.read_resource("quantavane://refs/ours_covering_17-7-4-6.txt")).contents[0].text
        index = (await client.read_resource("quantavane://checkers")).contents[0].text
    assert {"quantavane://about", "quantavane://problems", "quantavane://checkers", "quantavane://benchmark/readme",
            "quantavane://open-data/readme"} <= listed
    assert "quantavane://problems/{problem_id}" in templates and "quantavane://refs/{filename}" in templates
    assert about["network"].startswith("none") and about["counts"]["problems"] == 117
    assert prob["id"] == "1c-lower"
    assert "Used by: cw-" in docs and "SHA-256" in docs and "constant weight code" in docs
    assert "Bron-Kerbosch" in src and len(refc.splitlines()) == 17
    assert "ramsey_check.c" in index and "Used by 43 problem(s)" in index


@pytest.mark.anyio
async def test_bad_resource_is_an_error(server):
    async with create_connected_server_and_client_session(server) as client:
        with pytest.raises(McpError, match="No reference certificate"):
            await client.read_resource("quantavane://refs/..%2F..%2FMANIFEST.json")
        with pytest.raises(McpError, match="No checker"):
            await client.read_resource("quantavane://checkers/nope.py")


@pytest.mark.anyio
async def test_prompts(server):
    async with create_connected_server_and_client_session(server) as client:
        names = {p.name for p in (await client.list_prompts()).prompts}
        attack = await client.get_prompt("attack_problem", {"problem_id": "sphere-d3-n952"})
        verify = await client.get_prompt("verify_certificate", {"problem_id": "cw-34-6-5",
                                                                 "certificate_path": "/tmp/c.txt"})
        explain = await client.get_prompt("explain_replay", {"pr": "#292"})
    assert names == {"attack_problem", "verify_certificate", "explain_replay"}
    text = attack.messages[0].content.text
    assert "check_candidate" in text and "quantavane://refs/ours_sphere_d3_n952.txt" in text and "never" in text.lower()
    assert 'certificate_path="/tmp/c.txt"' in verify.messages[0].content.text
    assert "get_replay(pr=292)" in explain.messages[0].content.text


@pytest.mark.anyio
async def test_completion_of_problem_ids(server):
    async with create_connected_server_and_client_session(server) as client:
        c = await client.complete(PromptReference(type="ref/prompt", name="attack_problem"),
                                  {"name": "problem_id", "value": "sphere-d1"})
        t = await client.complete(ResourceTemplateReference(type="ref/resource",
                                                            uri="quantavane://checkers/{program}"),
                                  {"name": "program", "value": "c1"})
    assert c.completion.values == ["sphere-d10-n176", "sphere-d12-n103", "sphere-d16-n63"]
    assert set(t.completion.values) == {"c16_check.py", "c16_lower.py", "c16_trunc_check.py"}


@pytest.mark.anyio
async def test_no_gym_tools_by_default(server):
    async with create_connected_server_and_client_session(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert not any(n.startswith("gym_") for n in names)
