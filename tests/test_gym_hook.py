"""The opt-in hook for the training gym: no tools without QUANTAVANE_MCP_GYM; with it, gym_environments and
gym_propose, whose verdicts agree with check_candidate."""
import pytest
from helpers import ref
from mcp.shared.memory import create_connected_server_and_client_session

from quantavane_mcp import gym
from quantavane_mcp.config import Settings
from quantavane_mcp.server import build_server


@pytest.fixture
def server(tmp_path, cache_dir, store):
    return build_server(Settings(roots=(tmp_path.resolve(),), cache_dir=cache_dir, gym="fake_gym:backend"), store)


@pytest.mark.anyio
async def test_gym_tools_appear_and_agree_with_check_candidate(server):
    code = ref("ours_cw_34_6_5.txt").decode()
    async with create_connected_server_and_client_session(server) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        envs = (await client.call_tool("gym_environments", {})).structuredContent
        good = (await client.call_tool("gym_propose", {"env_id": "cw-34-6-5", "obj": code})).structuredContent
        bad = (await client.call_tool("gym_propose", {"env_id": "cw-34-6-5",
                                                      "obj": code.splitlines()[0] + "\n" + code})).structuredContent
        same = (await client.call_tool("check_candidate", {"problem_id": "cw-34-6-5",
                                                           "certificate": code})).structuredContent
        inexact = await client.call_tool("gym_propose", {"env_id": "float-env", "obj": "x"})
    assert {"gym_environments", "gym_propose"} <= names
    assert [e["id"] for e in envs["environments"]] == ["cw-34-6-5", "float-env"]
    assert good["verdict"] == "pass" and good["score"] == same["value"] == "528"
    assert bad["verdict"] == "fail" and bad["score"] is None
    assert inexact.isError and "inexact" in inexact.content[0].text


def test_bad_specs_are_refused():
    assert gym.load_backend(None) is None
    with pytest.raises(gym.GymError):
        gym.load_backend("no_colon")
    with pytest.raises(gym.GymError):
        gym.load_backend("no_such_module_xyz:backend")
    with pytest.raises(gym.GymError):
        gym.load_backend("json:dumps")            # callable, but returns nothing with environments()/propose()
