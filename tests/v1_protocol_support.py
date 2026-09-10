"""Shared private protocol helpers for the deterministic V1 evaluation.

The helpers deliberately expose only MCP results to the client bridge.  Fixture
request logs and audit rows stay under the caller-provided private state dir.
"""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO, cast

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def request_rows(path: Path) -> list[dict[str, Any]]:
    """Read private fixture request rows, returning an empty log if absent."""
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def canonical_json_bytes(value: Any) -> int:
    """Return deterministic UTF-8 bytes for a JSON-compatible value."""
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def call_tool_result_bytes(result: Any) -> int:
    """Measure the complete serialized MCP CallToolResult payload."""
    if hasattr(result, "model_dump"):
        payload = result.model_dump(mode="json", by_alias=True, exclude_none=False)
    else:
        payload = result
    return canonical_json_bytes(payload)


def text_json(result: Any) -> tuple[Any | None, int, bool]:
    """Parse the single JSON text block and return value, bytes, and presence."""
    blocks = [
        block
        for block in getattr(result, "content", [])
        if getattr(block, "type", None) == "text"
    ]
    if len(blocks) != 1:
        return None, 0, False
    raw = blocks[0].text
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        value = None
    return value, len(raw.encode("utf-8")), True


def schema_errors(schema: Any, structured: Any) -> list[str]:
    """Validate structured content against the advertised output schema."""
    if not isinstance(schema, Mapping):
        return ["outputSchema is absent"]
    if structured is None:
        return ["structuredContent is absent"]
    return [
        error.message for error in Draft202012Validator(schema).iter_errors(structured)
    ]


def _private_audit_path(state_dir: Path) -> Path:
    path = state_dir / "audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_private_audit(
    state_dir: Path,
    *,
    case: str | None,
    tool: str,
    arguments: dict[str, Any],
    text_bytes: int,
    result_bytes: int,
    request_delta: int,
    started_at: str,
    finished_at: str,
) -> None:
    """Append an audit row without headers, credentials, or response bodies."""
    row = {
        "case": case,
        "tool": tool,
        "arguments": arguments,
        "utf8_json_text_bytes": text_bytes,
        "utf8_call_tool_result_bytes": result_bytes,
        "http_attempt_delta": request_delta,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    with _private_audit_path(state_dir).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def build_server_env(
    *,
    repo_root: Path,
    state_dir: Path,
    request_log: Path,
    source_root: Path | None = None,
) -> dict[str, str]:
    """Build the isolated synthetic environment used by bridge and harness."""
    source = source_root or repo_root / "src"
    env = dict(os.environ)
    env.update(
        {
            "API_KEY": "synthetic-v1-key",
            "ATHLETE_ID": "i123",
            "INTERVALS_ACCESS_MODE": "readonly",
            "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
            "PYTHON_DOTENV_DISABLED": "1",
            "V1_SERVER_STATE_DIR": str(state_dir),
            "V1_SERVER_REQUEST_LOG": str(request_log),
            "INTERVALS_ARTIFACT_DIR": str(state_dir / "artifacts"),
            "INTERVALS_OPERATION_DIR": str(state_dir / "operations"),
            "INTERVALS_ARTIFACT_TTL_SECONDS": "3600",
            "INTERVALS_ARTIFACT_MAX_BYTES": "0",
            "INTERVALS_ARTIFACT_MAX_FILES": "0",
        }
    )
    env["PYTHONPATH"] = os.pathsep.join(
        [str(source), str(repo_root), *[item for item in env.get("PYTHONPATH", "").split(os.pathsep) if item]]
    )
    return env


def server_parameters(
    *,
    repo_root: Path,
    state_dir: Path,
    request_log: Path,
    source_root: Path | None = None,
) -> tuple[StdioServerParameters, TextIO]:
    """Return stdio parameters and a private stderr sink for one server."""
    state_dir.mkdir(parents=True, exist_ok=True)
    request_log.parent.mkdir(parents=True, exist_ok=True)
    errlog = cast(TextIO, __import__("tempfile").TemporaryFile(mode="w+", encoding="utf-8"))
    env = build_server_env(
        repo_root=repo_root,
        state_dir=state_dir,
        request_log=request_log,
        source_root=source_root,
    )
    return (
        StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.v1_fixture_server"],
            env=env,
        ),
        errlog,
    )


@asynccontextmanager
async def open_session(
    *,
    repo_root: Path,
    state_dir: Path,
    request_log: Path,
    source_root: Path | None = None,
):
    """Yield an initialized actual ClientSession and its tool catalogue."""
    params, errlog = server_parameters(
        repo_root=repo_root,
        state_dir=state_dir,
        request_log=request_log,
        source_root=source_root,
    )
    async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            yield session, {tool.name: tool for tool in listed.tools}, errlog
    errlog.seek(0)
    stderr = errlog.read()
    errlog.close()
    if "synthetic-v1-key" in stderr:
        raise AssertionError("synthetic API key leaked to MCP stderr")


async def call_and_record(
    session: ClientSession,
    tools: Mapping[str, Any],
    request_log: Path,
    tool_name: str,
    arguments: dict[str, Any],
    *,
    expected_parameter_error: bool = False,
) -> tuple[Any, dict[str, Any]]:
    """Call one public tool and record protocol facts for deterministic checks."""
    import datetime as _datetime

    before = len(request_rows(request_log))
    started = _datetime.datetime.now(_datetime.timezone.utc).isoformat()
    result = await session.call_tool(tool_name, arguments)
    finished = _datetime.datetime.now(_datetime.timezone.utc).isoformat()
    after = request_rows(request_log)
    structured = result.structuredContent
    text_value, text_bytes, text_present = text_json(result)
    complete_bytes = call_tool_result_bytes(result)
    errors = schema_errors(tools[tool_name].outputSchema, structured)
    if expected_parameter_error:
        schema_valid: bool | None = None
        structured_text_agree: bool | None = None
        if result.isError is not True or structured is not None:
            raise AssertionError(
                f"expected parameter validation error for {tool_name}: "
                f"isError={result.isError!r} structured={structured is not None}"
            )
    else:
        schema_valid = not errors
        structured_text_agree = text_value == structured
    record = {
        "tool": tool_name,
        "arguments": arguments,
        "mcp_is_error": result.isError is True,
        "domain_status": structured.get("status") if isinstance(structured, dict) else None,
        "structured_content_present": structured is not None,
        "text_content_present": text_present,
        "output_schema_valid": schema_valid,
        "schema_check": "not_applicable" if expected_parameter_error else "required",
        "schema_errors": [] if expected_parameter_error else errors,
        "structured_text_agree": structured_text_agree,
        "utf8_json_text_bytes": text_bytes,
        "utf8_call_tool_result_bytes": complete_bytes,
        "http_attempts": len(after) - before,
        "started_at": started,
        "finished_at": finished,
        "structured": structured,
    }
    return result, record
