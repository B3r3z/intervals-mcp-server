import json
import os
import sys
import tempfile
from typing import TextIO, cast

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_tools_call_structured_contract():
    errlog = tempfile.TemporaryFile(mode="w+")
    env = dict(os.environ)
    env.update(
        {
            "API_KEY": "protocol-api-marker",
            "ATHLETE_ID": "i123",
            "INTERVALS_ACCESS_MODE": "admin",
        }
    )
    env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(command=sys.executable,
                                   args=["-m", "intervals_mcp_server.server"], env=env)
    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            capability = next(tool for tool in listed.tools if tool.name == "get_capabilities")
            assert capability.outputSchema
            result = await session.call_tool("get_capabilities", {})
            assert result.isError is not True
            assert result.structuredContent["schema_version"] == "1.0"
            text_blocks = [block for block in result.content if getattr(block, "type", None) == "text"]
            assert len(text_blocks) == 1
            assert json.loads(text_blocks[0].text) == result.structuredContent
            invalid = await session.call_tool("get_event_by_id", {})
            assert invalid.isError is True
    errlog.seek(0)
    assert "protocol-api-marker" not in errlog.read()


async def _surface_for_mode(mode: str) -> tuple[set[str], dict]:
    errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+"))
    env = dict(os.environ)
    env.update(
        {
            "API_KEY": "surface-api-marker",
            "ATHLETE_ID": "i123",
            "INTERVALS_ACCESS_MODE": mode,
        }
    )
    env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + env.get("PYTHONPATH", "")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "intervals_mcp_server.server"],
        env=env,
    )
    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            capabilities = await session.call_tool("get_capabilities", {})
    errlog.seek(0)
    assert "surface-api-marker" not in errlog.read()
    assert capabilities.structuredContent is not None
    return {tool.name for tool in listed.tools}, capabilities.structuredContent["data"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["coach", "readonly"])
async def test_stdio_access_mode_hides_legacy_mutations(mode):
    names, capabilities = await _surface_for_mode(mode)
    legacy = {
        "add_activity_message",
        "add_or_update_event",
        "add_or_update_note",
        "delete_event",
        "delete_events_by_date_range",
        "create_custom_item",
        "update_custom_item",
        "delete_custom_item",
    }
    assert names.isdisjoint(legacy)
    assert "get_write_status" in names
    assert capabilities["server"]["mode"] == mode
    assert set(capabilities["write_surface"]["safe"]) <= names
    if mode == "coach":
        assert "apply_workout_changes" in names
    else:
        assert "apply_workout_changes" not in names
