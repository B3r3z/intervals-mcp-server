"""
API client for Intervals.icu MCP Server.

This module handles all HTTP communication with the Intervals.icu API,
including request management, error handling, and client lifecycle.
"""

from json import JSONDecodeError
import json
import logging
import asyncio
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Any

import httpx  # pylint: disable=import-error
from mcp.server.fastmcp import FastMCP  # pylint: disable=import-error

from intervals_mcp_server.config import get_config

logger = logging.getLogger("intervals_icu_mcp_server")

# One process-owned client. Tests can supply a MockTransport client at lifespan entry.
httpx_client: httpx.AsyncClient | None = None


async def _get_httpx_client() -> httpx.AsyncClient:
    """Lazily create or reuse the client owned by this module."""
    global httpx_client
    if httpx_client is None or httpx_client.is_closed:
        httpx_client = httpx.AsyncClient()
    return httpx_client


@asynccontextmanager
async def setup_api_client(_app: FastMCP, *, client: httpx.AsyncClient | None = None):
    """Own the request client's lifespan, including an optional test adapter."""
    global httpx_client
    if client is not None:
        if httpx_client is not None and not httpx_client.is_closed and httpx_client is not client:
            raise RuntimeError("HTTP client already configured")
        httpx_client = client
    try:
        yield
    finally:
        owned_client, httpx_client = httpx_client, None
        if owned_client is not None and not owned_client.is_closed:
            await owned_client.aclose()


def _get_error_message(error_code: int, error_text: str) -> str:
    """Return a user-friendly error message for a given HTTP status code."""
    error_messages = {
        HTTPStatus.UNAUTHORIZED: f"{HTTPStatus.UNAUTHORIZED.value} {HTTPStatus.UNAUTHORIZED.phrase}: Please check your API key.",
        HTTPStatus.FORBIDDEN: f"{HTTPStatus.FORBIDDEN.value} {HTTPStatus.FORBIDDEN.phrase}: You may not have permission to access this resource.",
        HTTPStatus.NOT_FOUND: f"{HTTPStatus.NOT_FOUND.value} {HTTPStatus.NOT_FOUND.phrase}: The requested endpoint or ID doesn't exist.",
        HTTPStatus.UNPROCESSABLE_ENTITY: f"{HTTPStatus.UNPROCESSABLE_ENTITY.value} {HTTPStatus.UNPROCESSABLE_ENTITY.phrase}: The server couldn't process the request (invalid parameters or unsupported operation).",
        HTTPStatus.TOO_MANY_REQUESTS: f"{HTTPStatus.TOO_MANY_REQUESTS.value} {HTTPStatus.TOO_MANY_REQUESTS.phrase}: Too many requests in a short time period.",
        HTTPStatus.INTERNAL_SERVER_ERROR: f"{HTTPStatus.INTERNAL_SERVER_ERROR.value} {HTTPStatus.INTERNAL_SERVER_ERROR.phrase}: The Intervals.icu server encountered an internal error.",
        HTTPStatus.SERVICE_UNAVAILABLE: f"{HTTPStatus.SERVICE_UNAVAILABLE.value} {HTTPStatus.SERVICE_UNAVAILABLE.phrase}: The Intervals.icu server might be down or undergoing maintenance.",
    }
    try:
        status = HTTPStatus(error_code)
        return error_messages.get(status, error_text)
    except ValueError:
        return error_text


def _prepare_request_config(
    url: str,
    api_key: str | None,
    method: str,
) -> tuple[str, httpx.BasicAuth, dict[str, str], str | None]:
    """Prepare request configuration including headers, auth, and URL.

    Returns:
        Tuple of (full_url, auth, headers, error_message).
        error_message is None if configuration is valid.
    """
    config = get_config()
    headers = {"User-Agent": config.user_agent, "Accept": "application/json"}

    if method in ["POST", "PUT"]:
        headers["Content-Type"] = "application/json"

    # Use provided api_key or fall back to global API_KEY
    key_to_use = api_key if api_key is not None else config.api_key
    if not key_to_use:
        logger.error("No API key provided for request to: %s", url)
        return (
            "",
            httpx.BasicAuth("", ""),
            {},
            "API key is required. Set API_KEY env var or pass api_key",
        )

    auth = httpx.BasicAuth("API_KEY", key_to_use)
    full_url = f"{config.intervals_api_base_url}{url}"
    return full_url, auth, headers, None


def _parse_response(
    response: httpx.Response, full_url: str, method: str = "GET"
) -> dict[str, Any] | list[dict[str, Any]]:
    """Parse HTTP response and return JSON data or error dict.

    Returns:
        Parsed JSON response or error dict.
    """
    # Check status before attempting JSON: gateways often return HTML errors.
    response.raise_for_status()
    try:
        response_data = response.json() if response.content else {}
    except JSONDecodeError:
        logger.error("Invalid JSON in upstream response (status=%s)", response.status_code)
        return {"error": True, "code": "INVALID_JSON", "message": "Invalid JSON in response", "phase": "parse",
                "status_code": response.status_code, "http_status": response.status_code,
                "recommended_action": "retry read" if method in {"GET", "HEAD", "OPTIONS"} else "reconcile write", "write_outcome": "unknown" if method not in {"GET", "HEAD", "OPTIONS"} else None}
    return response_data


async def make_intervals_request(
    url: str,
    api_key: str | None = None,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    data: dict[str, Any] | None = None,
    _retry_count: int = 0,
) -> dict[str, Any] | list[dict[str, Any]]:
    """
    Make a request to the Intervals.icu API with proper error handling.

    Args:
        url (str): The API endpoint path (e.g., '/athlete/{id}/activities').
        api_key (str | None): Optional API key to use for authentication. Defaults to the global API_KEY.
        params (dict[str, Any] | None): Optional query parameters for the request.
        method (str): HTTP method to use (GET, POST, etc.). Defaults to GET.
        data (dict[str, Any] | None): Optional data to send in the request body.

    Returns:
        dict[str, Any] | list[dict[str, Any]]: The parsed JSON response from the API, or an error dict.
    """
    global httpx_client  # noqa: PLW0603
    method = method.upper()
    # Prepare request configuration
    full_url, auth, headers, error_msg = _prepare_request_config(url, api_key, method)
    if error_msg:
        return {"error": True, "code": "CONFIGURATION_ERROR", "message": error_msg,
                "phase": "prepare", "recommended_action": "configure API_KEY"}

    async def _send_request(client: httpx.AsyncClient) -> httpx.Response:
        if method in {"POST", "PUT"} and data is not None:
            body = json.dumps(data)
            logger.debug("Request %s %s (JSON body redacted)", method, url)
            return await client.request(
                method=method,
                url=full_url,
                headers=headers,
                params=params,
                auth=auth,
                timeout=30.0,
                content=body,
            )
        return await client.request(
            method=method,
            url=full_url,
            headers=headers,
            params=params,
            auth=auth,
            timeout=30.0,
        )

    try:
        client = await _get_httpx_client()
        attempts = 3 if method.upper() in {"GET", "HEAD", "OPTIONS"} else 1
        response = None
        for attempt in range(attempts):
            try:
                response = await _send_request(client)
            except RuntimeError as runtime_error:
                # A closed client is safe to recreate only for reads. A write
                # may already have reached the server and is never retried.
                if "client has been closed" not in str(runtime_error).lower() or method.upper() not in {"GET", "HEAD", "OPTIONS"}:
                    raise
                logger.warning("HTTPX client was closed; recreating for read")
                httpx_client = None
                client = await _get_httpx_client()
                response = await _send_request(client)
            if response.status_code != HTTPStatus.TOO_MANY_REQUESTS and response.status_code < 500:
                break
            if attempt + 1 < attempts:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(float(retry_after), 5.0) if retry_after else 0.25 * (attempt + 1)
                except ValueError:
                    delay = 0.25 * (attempt + 1)
                await asyncio.sleep(delay)
        assert response is not None
        return _parse_response(response, full_url, method)
    except httpx.HTTPStatusError as e:
        return _handle_http_status_error(e, method)
    except httpx.TimeoutException:
        if method in {"GET", "HEAD", "OPTIONS"} and _retry_count < 2:
            return await make_intervals_request(url, api_key, params, method, data, _retry_count=_retry_count + 1)
        logger.error("Request timeout")
        return {"error": True, "code": "READ_TIMEOUT" if method in {"GET", "HEAD", "OPTIONS"} else "WRITE_TIMEOUT", "message": "upstream request timed out", "phase": "send", "recommended_action": "retry read" if method in {"GET", "HEAD", "OPTIONS"} else "reconcile write", "write_outcome": "unknown" if method not in {"GET", "HEAD", "OPTIONS"} else None}
    except httpx.RequestError:
        if method in {"GET", "HEAD", "OPTIONS"} and _retry_count < 2:
            return await make_intervals_request(url, api_key, params, method, data, _retry_count=_retry_count + 1)
        logger.error("Request error")
        return {"error": True, "code": "REQUEST_ERROR" if method in {"GET", "HEAD", "OPTIONS"} else "WRITE_TRANSPORT_ERROR", "message": "upstream request failed", "phase": "send", "recommended_action": "inspect connectivity", "write_outcome": "unknown" if method not in {"GET", "HEAD", "OPTIONS"} else None}
    except RuntimeError as exc:
        if method not in {"GET", "HEAD", "OPTIONS"} and "client has been closed" in str(exc).lower():
            return {"error": True, "code": "WRITE_NOT_SENT", "message": "HTTP client closed before write completed", "phase": "send", "recommended_action": "reconcile write", "write_outcome": "rejected"}
        return {"error": True, "code": "INTERNAL_CLIENT_ERROR", "message": "internal HTTP client error", "phase": "send", "recommended_action": "inspect client"}
    except httpx.HTTPError:
        logger.error("HTTP client error")
        return {"error": True, "code": "HTTP_CLIENT_ERROR", "message": "HTTP client error", "phase": "transport", "recommended_action": "inspect connectivity"}


def _handle_http_status_error(e: httpx.HTTPStatusError, method: str = "GET") -> dict[str, Any]:
    """Handle HTTP status errors and return formatted error dict.

    Args:
        e: The HTTPStatusError exception.

    Returns:
        Error dictionary with status code and message.
    """
    error_code = e.response.status_code
    # Never include response bodies: they may contain account data or secrets.
    logger.error("HTTP error: %s", error_code)
    try:
        error_text = HTTPStatus(error_code).phrase
    except ValueError:
        error_text = "Upstream request failed"
    return {
        "error": True,
        "status_code": error_code,
        "message": _get_error_message(error_code, error_text),
        "code": f"HTTP_{error_code}",
        "recommended_action": "check credentials" if error_code in (401, 403) else "retry read" if method in {"GET", "HEAD", "OPTIONS"} and error_code in (429, 502) else "reconcile write" if method not in {"GET", "HEAD", "OPTIONS"} else "inspect request",
        "write_outcome": "unknown" if method not in {"GET", "HEAD", "OPTIONS"} else None,
        "http_status": error_code,
        "phase": "http",
    }
