import pytest
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from intervals_mcp_server.catalogue import coach_tool, register_tools, tool_catalogue
from intervals_mcp_server.tools.capabilities import capabilities_for


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["admin", "coach", "readonly", "invalid"])
async def test_installed_inventory_matches_complete_capabilities(mode, monkeypatch):
    app = FastMCP("catalogue-test")
    catalogue = register_tools(app, mode)
    names = {tool.name for tool in await app.list_tools()}
    data = capabilities_for(catalogue).data
    assert names == {tool["name"] for tool in data["tool_catalogue"]}
    assert names == set(catalogue.names())
    assert data["server"]["mode"] == (mode if mode != "invalid" else "readonly")
    if mode != "admin":
        with pytest.raises(ToolError, match="Unknown tool"):
            await app.call_tool("delete_event", {"event_id": 1})
    if mode in {"readonly", "invalid"}:
        with pytest.raises(ToolError, match="Unknown tool"):
            await app.call_tool("apply_workout_changes", {})
    monkeypatch.setenv("INTERVALS_ACCESS_MODE", "readonly" if mode == "admin" else "admin")
    result = await app.call_tool("get_capabilities", {})
    assert isinstance(result, tuple)
    assert result[1]["data"]["server"]["mode"] == catalogue.mode
    assert {tool["name"] for tool in result[1]["data"]["tool_catalogue"]} == names


@pytest.mark.asyncio
async def test_imported_handlers_do_not_install_tools_and_servers_are_independent():
    first, second = FastMCP("first"), FastMCP("second")
    assert await first.list_tools() == []
    register_tools(first, "readonly")
    register_tools(second, "admin")
    assert "delete_event" not in {tool.name for tool in await first.list_tools()}
    assert "delete_event" in {tool.name for tool in await second.list_tools()}
    with pytest.raises(ValueError, match="different tool catalogue"):
        register_tools(first, "admin")


def test_readonly_catalogue_describes_local_effects():
    items = {tool["name"]: tool for tool in tool_catalogue("readonly").describe()}
    assert all(tool["effects"]["upstream"] != "write" for tool in items.values())
    assert items["export_activity_data"]["effects"]["local"] == "write"
    assert items["get_write_status"]["effects"]["local"] == "write"
    assert items["get_artifact_chunk"]["effects"] == {"upstream": "none", "local": "read"}


def test_compatibility_exports_cover_all_tools():
    from intervals_mcp_server import server, tools

    for tool in tool_catalogue("admin").definitions:
        assert getattr(server, tool.name) is tool.handler
        assert getattr(tools, tool.name) is tool.handler


def test_invalid_classification_and_duplicate_identity_fail_before_installation():
    before = tool_catalogue("admin").names()
    with pytest.raises(ValueError, match="mutations require write access"):
        coach_tool(access="read", upstream="write")

    async def get_activities():
        pass

    with pytest.raises(ValueError, match="duplicate tool identity"):
        coach_tool(access="read", upstream="read")(get_activities)
    assert tool_catalogue("admin").names() == before


@pytest.mark.asyncio
async def test_stdio_exact_inventory_all_modes():
    from tests.test_protocol_contract import _surface_for_mode

    for mode in ("admin", "coach", "readonly", "invalid"):
        names, data = await _surface_for_mode(mode)
        assert names == {item["name"] for item in data["tool_catalogue"]}
        assert set(data["write_surface"]["legacy_tools"]) <= names
        assert len(names) == len(data["tool_catalogue"])
