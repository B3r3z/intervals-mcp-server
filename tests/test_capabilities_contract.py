import asyncio

from intervals_mcp_server.tools.capabilities import get_capabilities


def test_capabilities_identify_local_source_and_metric_catalogue() -> None:
    result = asyncio.run(get_capabilities())

    assert result.source.system == "intervals-mcp-server"
    assert "get_metric_definitions" in result.data["read_surface"]["implemented"]
    assert "get_session_context" in result.data["read_surface"]["implemented"]
    assert {
        "get_custom_items",
        "get_custom_item_by_id",
    } <= set(result.data["read_surface"]["implemented"])
