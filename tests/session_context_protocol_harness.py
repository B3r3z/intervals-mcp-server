"""Synthetic MCP-over-stdio proof for composed session context.

Run from the repository root with::

    uv run python -m tests.session_context_protocol_harness --output <path>

All upstream reads use the fixture server's ``httpx.MockTransport``. The
request log is the proof of section selectivity and pairing order.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, TextIO, cast

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _request_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _text_json(result: Any) -> tuple[dict[str, Any] | None, int]:
    blocks = [block for block in result.content if getattr(block, "type", None) == "text"]
    if len(blocks) != 1:
        return None, 0
    raw = blocks[0].text
    return json.loads(raw), len(raw.encode("utf-8"))


def _result_bytes(result: Any) -> int:
    value = result.model_dump(mode="json", by_alias=True, exclude_none=False)
    return len(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _schema_errors(schema: Any, structured: Any) -> list[str]:
    if not isinstance(schema, dict) or structured is None:
        return ["output schema or structured content absent"]
    return [
        error.message
        for error in Draft202012Validator(schema).iter_errors(structured)
    ]


async def capture_session_context_report() -> dict[str, Any]:
    """Exercise default, plan, comments-only, and strict-ID paths over stdio."""
    with tempfile.TemporaryDirectory(prefix="intervals-session-context-") as temp_dir:
        request_log = Path(temp_dir) / "requests.jsonl"
        artifact_dir = Path(temp_dir) / "artifacts"
        operation_dir = Path(temp_dir) / "operations"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-session-context-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
                "INTERVALS_ARTIFACT_DIR": str(artifact_dir),
                "INTERVALS_OPERATION_DIR": str(operation_dir),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        call_reports: list[dict[str, Any]] = []

        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tools = {tool.name: tool for tool in listed.tools}
                if "get_session_context" not in tools:
                    raise AssertionError("get_session_context is not registered")

                async def call_context(arguments: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
                    before = len(_request_rows(request_log))
                    result = await session.call_tool("get_session_context", arguments)
                    structured = result.structuredContent
                    if not isinstance(structured, dict):
                        raise AssertionError("session context structured content is absent")
                    text_value, text_bytes = _text_json(result)
                    errors = _schema_errors(
                        tools["get_session_context"].outputSchema, structured
                    )
                    call_reports.append(
                        {
                            "tool": "get_session_context",
                            "arguments": arguments,
                            "mcp_is_error": result.isError is True,
                            "domain_status": structured.get("status"),
                            "output_schema_valid": not errors,
                            "structured_text_agree": text_value == structured,
                            "utf8_json_text_bytes": text_bytes,
                            "utf8_call_tool_result_bytes": _result_bytes(result),
                        }
                    )
                    return structured, _request_rows(request_log)[before:]

                default, default_requests = await call_context(
                    {"activity_id": "a-context"}
                )
                plan, plan_requests = await call_context(
                    {
                        "activity_id": "a-context",
                        "sections": ["plan"],
                        "athlete_id": "i123",
                    }
                )
                comments, comments_requests = await call_context(
                    {"activity_id": "a-context", "sections": ["comments"]}
                )

                before_invalid = len(_request_rows(request_log))
                invalid = await session.call_tool(
                    "get_event_by_id", {"event_id": True, "athlete_id": "i123"}
                )
                invalid_requests = _request_rows(request_log)[before_invalid:]
                call_reports.append(
                    {
                        "tool": "get_event_by_id",
                        "arguments": {"event_id": True, "athlete_id": "i123"},
                        "mcp_is_error": invalid.isError is True,
                        "structured_content_present": invalid.structuredContent is not None,
                        "utf8_call_tool_result_bytes": _result_bytes(invalid),
                    }
                )

        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-session-context-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")

        default_sections = default["data"]["sections"]
        plan_section = plan["data"]["sections"]["plan"]
        steps = plan_section["data"]["resolved_event"]["workout_doc"]["steps"]
        all_requests = _request_rows(request_log)
        return {
            "protocol": "MCP ClientSession over stdio",
            "python_version": sys.version.split()[0],
            "upstream": "httpx.MockTransport synthetic fixtures; all other requests blocked",
            "proof_boundary": "JSON-RPC framing is excluded from byte counts.",
            "mcp_calls": len(call_reports),
            "upstream_requests": len(all_requests),
            "upstream_request_log": all_requests,
            "utf8_json_text_bytes": sum(
                call.get("utf8_json_text_bytes", 0) for call in call_reports
            ),
            "utf8_call_tool_result_bytes": sum(
                call["utf8_call_tool_result_bytes"] for call in call_reports
            ),
            "all_context_output_schemas_valid": all(
                call.get("output_schema_valid", True) for call in call_reports
            ),
            "all_context_structured_text_agree": all(
                call.get("structured_text_agree", True) for call in call_reports
            ),
            "default_sections_exact": list(default_sections)
            == ["details", "intervals", "comments"],
            "default_two_upstream_reads": [row["path"] for row in default_requests]
            == [
                "/api/v1/activity/a-context",
                "/api/v1/activity/a-context/messages",
            ],
            "default_embedded_intervals_requested": default_requests[0]["query"]
            == [["intervals", "true"]],
            "valid_empty_and_zero_null_preserved": (
                default_sections["intervals"]["data"]["icu_intervals"][0][
                    "average_watts"
                ]
                == 0
                and default_sections["intervals"]["data"]["icu_intervals"][0][
                    "average_heartrate"
                ]
                is None
                and default_sections["details"]["data"]["kg_lifted"] == 0
            ),
            "message_fingerprint_preserved": len(
                default_sections["comments"]["data"][0]["content_fingerprint"]
            )
            == 64,
            "plan_uses_raw_event_date_then_exact_resolve": (
                [row["path"] for row in plan_requests]
                == [
                    "/api/v1/activity/a-context",
                    "/api/v1/athlete/i123/events/42",
                    "/api/v1/athlete/i123/events",
                ]
                and plan_requests[-1]["query"]
                == [
                    ["newest", "2026-09-07"],
                    ["oldest", "2026-09-07"],
                    ["resolve", "true"],
                ]
                and plan_section["data"]["resolved_event"]["id"] == 42
            ),
            "workout_value_objects_preserved": (
                steps[0]["_power"] == {"value": 220, "start": 210, "end": 230}
                and steps[0]["_hr"] == {"value": 150, "start": 145, "end": 155}
                and steps[0]["_pace"] == {"value": 4.0, "start": 3.9, "end": 4.1}
            ),
            "comments_only_one_messages_read": [
                row["path"] for row in comments_requests
            ]
            == ["/api/v1/activity/a-context/messages"],
            "comments_only_status": comments["status"],
            "strict_bool_event_id_rejected_before_http": (
                invalid.isError is True and invalid_requests == []
            ),
            "no_current_settings_request": all(
                "/sport-settings/" not in row["path"] for row in all_requests
            ),
            "context_source_is_local_composition": default["source"]["system"]
            == "intervals-mcp-server",
            "calls": call_reports,
        }


def _write_report(report: dict[str, Any], output: Path | None) -> None:
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(rendered, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args(argv)
    _write_report(asyncio.run(capture_session_context_report()), arguments.output)


if __name__ == "__main__":
    main()
