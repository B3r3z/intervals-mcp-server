import httpx
import pytest
from unittest.mock import AsyncMock
import intervals_mcp_server.api.client as client_module
from intervals_mcp_server.config import Config
from intervals_mcp_server.api.client import _parse_response, _handle_http_status_error


def _response(status, content=b"{}"):
    return httpx.Response(status, content=content, request=httpx.Request("GET", "https://example.invalid"))


def test_invalid_json_read_and_write():
    assert _parse_response(_response(200, b"<html>"), "x", "GET")["code"] == "INVALID_JSON"
    write = _parse_response(_response(200, b"<html>"), "x", "POST")
    assert write["write_outcome"] == "unknown" and write["recommended_action"] == "reconcile write"


@pytest.mark.parametrize("status", [401, 403, 429, 502])
def test_http_status_codes(status):
    error = _handle_http_status_error(httpx.HTTPStatusError("x", request=_response(status).request, response=_response(status)), "GET")
    assert error["code"] == f"HTTP_{status}" and error["http_status"] == status


def test_write_http_reconcile():
    response = _response(502)
    error = _handle_http_status_error(httpx.HTTPStatusError("x", request=response.request, response=response), "POST")
    assert error["write_outcome"] == "unknown" and error["recommended_action"] == "reconcile write"


def test_parser_preserves_empty_json():
    assert _parse_response(_response(200, b""), "x").get("error") is not True


def test_parser_html_error_is_not_json():
    with pytest.raises(httpx.HTTPStatusError):
        _parse_response(_response(502, b"<html>"), "x")


def test_no_body_in_error_text(caplog):
    _parse_response(_response(200, b"marker-secret"), "x", "POST")
    assert "marker-secret" not in caplog.text


def test_write_status_code_safe():
    response = _response(500)
    error = _handle_http_status_error(httpx.HTTPStatusError("x", request=response.request, response=response), "DELETE")
    assert error["code"] == "HTTP_500"


def test_invalid_json_status_and_phase():
    result = _parse_response(_response(200, b"not-json"), "x")
    assert result["phase"] == "parse" and result["http_status"] == 200


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.is_closed = False

    async def request(self, **_kwargs):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _patch_runtime(monkeypatch, fake):
    monkeypatch.setattr(client_module, "_get_httpx_client", AsyncMock(return_value=fake))
    monkeypatch.setattr(client_module, "get_config", lambda: Config("key", "a", "https://example", "test"))


def test_make_request_get_retries_502(monkeypatch):
    fake = FakeClient([_response(502, b"<html>")] * 3)
    _patch_runtime(monkeypatch, fake)
    monkeypatch.setattr(client_module.asyncio, "sleep", AsyncMock())
    result = __import__("asyncio").run(client_module.make_intervals_request("/x"))
    assert fake.calls == 3 and result["code"] == "HTTP_502"


def test_make_request_429_retry_after(monkeypatch):
    first = _response(429)
    first.headers["Retry-After"] = "0"
    fake = FakeClient([first, _response(200, b'{"ok":1}')])
    _patch_runtime(monkeypatch, fake)
    monkeypatch.setattr(client_module.asyncio, "sleep", AsyncMock())
    result = __import__("asyncio").run(client_module.make_intervals_request("/x"))
    assert fake.calls == 2 and result["ok"] == 1


def test_make_request_post_timeout_once(monkeypatch):
    fake = FakeClient([httpx.TimeoutException("timeout")])
    _patch_runtime(monkeypatch, fake)
    result = __import__("asyncio").run(client_module.make_intervals_request("/x", method="POST", data={"secret": "body-marker-secret"}))
    assert fake.calls == 1 and result["code"] == "WRITE_TIMEOUT"


def test_make_request_get_timeout_retries(monkeypatch):
    fake = FakeClient([httpx.TimeoutException("timeout")] * 3)
    _patch_runtime(monkeypatch, fake)
    result = __import__("asyncio").run(client_module.make_intervals_request("/x"))
    assert fake.calls == 3 and result["code"] == "READ_TIMEOUT"


def test_make_request_delete_500_is_not_retried(monkeypatch):
    fake = FakeClient([_response(500)])
    _patch_runtime(monkeypatch, fake)
    result = __import__("asyncio").run(
        client_module.make_intervals_request("/x", method="DELETE")
    )
    assert fake.calls == 1
    assert result["code"] == "HTTP_500"
    assert result["write_outcome"] == "unknown"
