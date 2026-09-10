import httpx
import pytest
from mcp.server.fastmcp import FastMCP

from intervals_mcp_server.api import client as module
from intervals_mcp_server.config import Config


@pytest.mark.asyncio
async def test_lifespan_uses_supplied_transport_and_closes_it(monkeypatch):
    seen = []

    def request(req):
        seen.append(req.url.path)
        return httpx.Response(200, json={"id": "fixture"})

    adapter = httpx.AsyncClient(transport=httpx.MockTransport(request))
    monkeypatch.setattr(module, "httpx_client", None)
    monkeypatch.setattr(module, "get_config", lambda: Config("key", "i123", "https://fixture", "test"))
    async with module.setup_api_client(FastMCP("test"), client=adapter):
        assert (await module.make_intervals_request("/one"))["id"] == "fixture"
        assert (await module.make_intervals_request("/two"))["id"] == "fixture"
        assert not adapter.is_closed
    assert seen == ["/one", "/two"]
    assert adapter.is_closed


@pytest.mark.asyncio
async def test_closed_client_is_replaced_and_replacement_closed(monkeypatch):
    old = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    await old.aclose()
    replacement = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"replacement": True}))
    )
    monkeypatch.setattr(module, "httpx_client", old)
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda: replacement)
    monkeypatch.setattr(module, "get_config", lambda: Config("key", "i123", "https://fixture", "test"))
    async with module.setup_api_client(FastMCP("test")):
        assert (await module.make_intervals_request("/one"))["replacement"] is True
    assert replacement.is_closed
