"""Reusable synthetic MCP-over-stdio read scenario harness.

Run from the repository root with::

    uv run python -m tests.protocol_read_harness --output <path>

The report counts public MCP tool calls, synthetic upstream requests, the
UTF-8 size of the JSON compatibility text, and the full serialized
``CallToolResult``.  MCP initialization and
``tools/list`` are setup traffic and are excluded from ``mcp_calls``.
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


DEFAULT_STREAM_TYPES = [
    "time",
    "watts",
    "heartrate",
    "cadence",
    "altitude",
    "distance",
    "velocity_smooth",
]

SCENARIOS: dict[str, list[tuple[str, dict[str, Any]]]] = {
    "activity_session": [
        ("get_activity_details", {"activity_id": "a-session"}),
        ("get_activity_intervals", {"activity_id": "a-session"}),
        ("get_activity_messages", {"activity_id": "a-session"}),
    ],
    "default_streams": [
        ("get_activity_streams", {"activity_id": "a-session"}),
    ],
    "athlete_power_curves": [
        (
            "get_athlete_power_curves",
            {"athlete_id": "i123", "durations": [5, 60]},
        ),
    ],
    "malformed_events": [
        (
            "get_events",
            {
                "athlete_id": "i123",
                "start_date": "2026-09-08",
                "end_date_exclusive": "2026-09-09",
            },
        ),
    ],
}


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


def _call_tool_result_bytes(result: Any) -> int:
    payload = result.model_dump(mode="json", by_alias=True, exclude_none=False)
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _observations(scenario: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    structured = [call["structured"] for call in calls]
    if scenario == "activity_session":
        details = structured[0]
        return {
            "hidden_source_row_preserved": details.get("data", {}).get("source") == "STRAVA",
            "hidden_source_limitation_reported": (
                "SOURCE_DATA_LIMITED" in details.get("warnings", [])
                and "source_record_hidden" in details.get("coverage", {}).get("reasons", [])
                and details.get("status") == "partial"
            ),
            "interval_container_preserved": set(structured[1].get("data", {}))
            >= {"icu_intervals", "icu_groups"},
        }
    if scenario == "default_streams":
        data = structured[0].get("data", {})
        returned = data.get("streams", [])
        return {
            "actual_default_types_reported_as_requested": data.get("requested")
            == DEFAULT_STREAM_TYPES,
            "absent_default_types_reported_missing": data.get("missing")
            == DEFAULT_STREAM_TYPES[2:],
            "returned_types": [row.get("type") for row in returned],
            "duplicate_watts_preserved": sum(
                row.get("type") == "watts" for row in returned
            )
            == 2,
            "data2_preserved": returned[1].get("data2") == [0, 249, None, 0],
            "null_and_zero_samples_preserved": returned[1].get("data")
            == [0, 250, None, 0],
        }
    if scenario == "athlete_power_curves":
        data = structured[0].get("data", {})
        curves = data.get("curves", [])
        return {
            "per_curve_missing_durations_present": all(
                "missing_durations" in curve for curve in curves
            ),
            "aggregate_missing_durations": data.get("missing_durations"),
            "zero_and_null_watts_preserved": [
                point.get("watts")
                for point in curves[0].get("data_points", [])
            ]
            == [0, None],
            "meaningful_curve_metadata_preserved": curves[0].get("moving_time") == 12345
            and "weight" in curves[0],
            "compact_raw_curve_omitted": "raw" not in curves[0],
        }
    if scenario == "malformed_events":
        response = structured[0]
        return {
            "malformed_shape_is_error": response.get("status") == "error",
            "malformed_shape_became_empty_success": response.get("status") == "ok"
            and response.get("data") == [],
        }
    return {}


async def capture_report(
    *,
    server_source: Path | None = None,
    baseline_only: bool = False,
) -> dict[str, Any]:
    """Run all scenarios through a real ``ClientSession`` stdio connection."""
    source_path = (server_source or Path("src")).resolve()
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.pathsep.join(
            [str(source_path), os.path.abspath(".")]
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        scenario_reports: dict[str, Any] = {}
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool_by_name = {tool.name: tool for tool in listed.tools}
                for scenario, tool_calls in SCENARIOS.items():
                    upstream_before = len(_request_rows(request_log))
                    call_reports: list[dict[str, Any]] = []
                    for tool_name, arguments in tool_calls:
                        result = await session.call_tool(tool_name, arguments)
                        structured = result.structuredContent
                        text_value, text_bytes = _text_json(result)
                        result_bytes = _call_tool_result_bytes(result)
                        schema = tool_by_name[tool_name].outputSchema
                        schema_errors = []
                        if not isinstance(schema, dict):
                            schema_errors.append("outputSchema is absent")
                        elif structured is None:
                            schema_errors.append("structuredContent is absent")
                        else:
                            schema_errors = [
                                error.message
                                for error in Draft202012Validator(schema).iter_errors(
                                    structured
                                )
                            ]
                        call_reports.append(
                            {
                                "tool": tool_name,
                                "mcp_is_error": result.isError is True,
                                "domain_status": (
                                    structured.get("status")
                                    if isinstance(structured, dict)
                                    else None
                                ),
                                "utf8_json_text_bytes": text_bytes,
                                "utf8_call_tool_result_bytes": result_bytes,
                                "output_schema_valid": not schema_errors,
                                "schema_errors": schema_errors,
                                "structured_text_agree": text_value == structured,
                                "structured": structured,
                            }
                        )
                    requests = _request_rows(request_log)[upstream_before:]
                    public_calls = [
                        {
                            key: value
                            for key, value in call.items()
                            if key != "structured"
                        }
                        for call in call_reports
                    ]
                    scenario_reports[scenario] = {
                        "mcp_calls": len(tool_calls),
                        "upstream_requests": len(requests),
                        "upstream_request_log": requests,
                        "utf8_json_text_bytes": sum(
                            call["utf8_json_text_bytes"] for call in call_reports
                        ),
                        "utf8_call_tool_result_bytes": sum(
                            call["utf8_call_tool_result_bytes"] for call in call_reports
                        ),
                        "calls": public_calls,
                        "observations": _observations(scenario, call_reports),
                    }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        report: dict[str, Any] = {
            "protocol": "MCP ClientSession over stdio",
            "upstream": "httpx.MockTransport synthetic fixtures; all other requests blocked",
            "server_source": (
                "stage0-source" if server_source is not None else "current-checkout"
            ),
            "baseline_only": baseline_only,
            "measurement_notes": {
                "mcp_calls": "Public tools/call requests only; initialize and tools/list excluded.",
                "utf8_json_text_bytes": "Bytes in the single JSON text content block.",
                "utf8_call_tool_result_bytes": (
                    "Canonical JSON bytes for CallToolResult content, structuredContent, "
                    "isError, and metadata; JSON-RPC framing excluded."
                ),
                "mcp_is_error": "Transport/tool execution error; domain status:error is separate.",
            },
            "scenarios": scenario_reports,
        }
        if not baseline_only:
            report.update(
                {
                    "input_validation_probe": await capture_invalid_duration_probe(),
                    "analytics_a1_probe": await capture_analytics_a1_probe(),
                    "analytics_a2_probe": await capture_analytics_a2_probe(),
                    "full_power_curve_probe": await capture_full_power_probe(),
                    "a3_probe": await capture_a3_probe(),
                    "m1e3_probe": await capture_m1e3_probe(),
                }
            )
        return report


async def capture_invalid_duration_probe() -> dict[str, Any]:
    """Verify MCP input validation rejects a string duration before HTTP."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-invalid-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(
                    "get_athlete_power_curves",
                    {
                        "athlete_id": "i123",
                        "durations": ["5"],
                        "this_season": True,
                        "last_season": False,
                    },
                )
                probe = {
                    "mcp_is_error": result.isError is True,
                    "structured_content_present": result.structuredContent is not None,
                    "text_content_present": any(
                        getattr(block, "type", None) == "text" for block in result.content
                    ),
                    "upstream_requests": len(_request_rows(request_log)),
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


async def capture_full_power_probe() -> dict[str, Any]:
    """Verify the opt-in full power-curve representation outside baseline totals."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-full-curve-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool = next(tool for tool in listed.tools if tool.name == "get_athlete_power_curves")
                result = await session.call_tool(
                    "get_athlete_power_curves",
                    {"athlete_id": "i123", "durations": [5, 60], "detail": "full"},
                )
                structured = result.structuredContent
                text_value, text_bytes = _text_json(result)
                schema_errors = []
                if not isinstance(tool.outputSchema, dict) or structured is None:
                    schema_errors.append("output schema or structured content absent")
                else:
                    schema_errors = [
                        error.message
                        for error in Draft202012Validator(tool.outputSchema).iter_errors(
                            structured
                        )
                    ]
                curves = structured.get("data", {}).get("curves", []) if isinstance(structured, dict) else []
                probe = {
                    "mcp_is_error": result.isError is True,
                    "upstream_requests": len(_request_rows(request_log)),
                    "output_schema_valid": not schema_errors,
                    "structured_text_agree": text_value == structured,
                    "utf8_json_text_bytes": text_bytes,
                    "full_raw_curve_available": bool(curves) and "raw" in curves[0],
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


async def capture_a3_probe() -> dict[str, Any]:
    """Verify new activity-curve and sport-settings reads over real stdio."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-a3-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )

        def summarize(result: Any, tool: Any) -> dict[str, Any]:
            structured = result.structuredContent
            try:
                text_value, text_bytes = _text_json(result)
            except json.JSONDecodeError:
                text_blocks = [
                    block
                    for block in result.content
                    if getattr(block, "type", None) == "text"
                ]
                text_value = None
                text_bytes = (
                    len(text_blocks[0].text.encode("utf-8")) if text_blocks else 0
                )
            schema_errors: list[str] = []
            if not isinstance(tool.outputSchema, dict) or structured is None:
                schema_errors.append("output schema or structured content absent")
            else:
                schema_errors = [
                    error.message
                    for error in Draft202012Validator(tool.outputSchema).iter_errors(
                        structured
                    )
                ]
            return {
                "mcp_is_error": result.isError is True,
                "domain_status": (
                    structured.get("status") if isinstance(structured, dict) else None
                ),
                "output_schema_valid": not schema_errors,
                "structured_text_agree": text_value == structured,
                "utf8_json_text_bytes": text_bytes,
                "utf8_call_tool_result_bytes": _call_tool_result_bytes(result),
                "structured_content_present": structured is not None,
                "text_content_present": any(
                    getattr(block, "type", None) == "text" for block in result.content
                ),
                "structured": structured,
            }

        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool_by_name = {tool.name: tool for tool in listed.tools}
                curve_result = await session.call_tool(
                    "get_activity_power_curves",
                    {
                        "activity_id": "a-session",
                        "durations": [5, 60],
                        "fatigue": ["normal"],
                    },
                )
                settings_result = await session.call_tool(
                    "get_sport_settings",
                    {"sport": "Ride", "athlete_id": "i123"},
                )
                invalid_result = await session.call_tool(
                    "get_activity_power_curves",
                    {"activity_id": "a-session", "durations": [True]},
                )
                curve = summarize(
                    curve_result, tool_by_name["get_activity_power_curves"]
                )
                settings = summarize(
                    settings_result, tool_by_name["get_sport_settings"]
                )
                invalid = summarize(
                    invalid_result, tool_by_name["get_activity_power_curves"]
                )
                probe = {
                    "curve": curve,
                    "settings": settings,
                    "invalid_curve_duration": {
                        key: value
                        for key, value in invalid.items()
                        if key != "structured"
                    },
                    "curve_missing_null_preserved": (
                        isinstance(curve["structured"], dict)
                        and curve["structured"].get("data", {})
                        .get("curves", [{}])[0]
                        .get("data_points", [{}, {}])[1]
                        .get("watts")
                        is None
                    ),
                    "settings_current_scope": (
                        isinstance(settings["structured"], dict)
                        and settings["structured"].get("provenance", {}).get("scope")
                        == "current_at_fetch"
                    ),
                    "upstream_requests": len(_request_rows(request_log)),
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


async def capture_m1e3_probe() -> dict[str, Any]:
    """Verify metric, custom-definition, stream, and wellness semantics over stdio."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-m1e3-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )

        def summarize(result: Any, tool: Any) -> dict[str, Any]:
            structured = result.structuredContent
            try:
                text_value, text_bytes = _text_json(result)
            except json.JSONDecodeError:
                text_blocks = [
                    block
                    for block in result.content
                    if getattr(block, "type", None) == "text"
                ]
                text_value = None
                text_bytes = (
                    len(text_blocks[0].text.encode("utf-8")) if text_blocks else 0
                )
            schema_errors: list[str] = []
            if not isinstance(tool.outputSchema, dict) or structured is None:
                schema_errors.append("output schema or structured content absent")
            else:
                schema_errors = [
                    error.message
                    for error in Draft202012Validator(tool.outputSchema).iter_errors(
                        structured
                    )
                ]
            return {
                "mcp_is_error": result.isError is True,
                "domain_status": (
                    structured.get("status") if isinstance(structured, dict) else None
                ),
                "output_schema_valid": not schema_errors,
                "structured_content_present": structured is not None,
                "text_content_present": any(
                    getattr(block, "type", None) == "text" for block in result.content
                ),
                "structured_text_agree": text_value == structured,
                "utf8_json_text_bytes": text_bytes,
                "utf8_call_tool_result_bytes": _call_tool_result_bytes(result),
                "structured": structured,
            }

        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool_by_name = {tool.name: tool for tool in listed.tools}
                metric_result = await session.call_tool(
                    "get_metric_definitions",
                    {"names": ["watts", "hrv", "vo2max_5m"]},
                )
                unknown_metric_result = await session.call_tool(
                    "get_metric_definitions", {"names": ["future_metric"]}
                )
                custom_list_result = await session.call_tool(
                    "get_custom_items", {"athlete_id": "i123"}
                )
                custom_full_result = await session.call_tool(
                    "get_custom_item_by_id",
                    {"item_id": 7, "athlete_id": "i123", "detail": "full"},
                )
                custom_not_found_result = await session.call_tool(
                    "get_custom_item_by_id",
                    {"item_id": 999, "athlete_id": "i123"},
                )
                streams_result = await session.call_tool(
                    "get_activity_streams",
                    {
                        "activity_id": "a-m1",
                        "stream_types": "time,watts,raw_watts,heartrate,raw_heartrate,cadence",
                    },
                )
                wellness_result = await session.call_tool(
                    "get_wellness_data", {"athlete_id": "i123"}
                )
                invalid_custom_id_result = await session.call_tool(
                    "get_custom_item_by_id",
                    {"item_id": True, "athlete_id": "i123"},
                )
                results = {
                    "metric": summarize(
                        metric_result, tool_by_name["get_metric_definitions"]
                    ),
                    "unknown_metric": summarize(
                        unknown_metric_result, tool_by_name["get_metric_definitions"]
                    ),
                    "custom_list": summarize(
                        custom_list_result, tool_by_name["get_custom_items"]
                    ),
                    "custom_full": summarize(
                        custom_full_result, tool_by_name["get_custom_item_by_id"]
                    ),
                    "custom_not_found": summarize(
                        custom_not_found_result, tool_by_name["get_custom_item_by_id"]
                    ),
                    "streams": summarize(
                        streams_result, tool_by_name["get_activity_streams"]
                    ),
                    "wellness": summarize(
                        wellness_result, tool_by_name["get_wellness_data"]
                    ),
                    "invalid_custom_id": summarize(
                        invalid_custom_id_result,
                        tool_by_name["get_custom_item_by_id"],
                    ),
                }
                metric_structured = results["metric"]["structured"]
                custom_list_structured = results["custom_list"]["structured"]
                custom_full_structured = results["custom_full"]["structured"]
                streams_structured = results["streams"]["structured"]
                wellness_structured = results["wellness"]["structured"]
                probe = {
                    "metric": {
                        key: value for key, value in results["metric"].items() if key != "structured"
                    },
                    "metric_local_source": (
                        isinstance(metric_structured, dict)
                        and metric_structured.get("source", {}).get("system")
                        == "intervals-mcp-server"
                    ),
                    "metric_unknown_partial": (
                        results["unknown_metric"]["domain_status"] == "partial"
                        and isinstance(results["unknown_metric"]["structured"], dict)
                        and results["unknown_metric"]["structured"].get("data", {}).get(
                            "unknown_names"
                        )
                        == ["future_metric"]
                    ),
                    "custom_list": {
                        key: value
                        for key, value in results["custom_list"].items()
                        if key != "structured"
                    },
                    "custom_list_metadata_warning": (
                        results["custom_list"]["domain_status"] == "partial"
                        and isinstance(custom_list_structured, dict)
                        and custom_list_structured.get("data", {})
                        .get("items", [{}])[0]
                        .get("declared_metadata_status")
                        == "declared_unverified"
                    ),
                    "custom_full": {
                        key: value
                        for key, value in results["custom_full"].items()
                        if key != "structured"
                    },
                    "custom_full_raw_preserved": (
                        results["custom_full"]["domain_status"] == "ok"
                        and isinstance(custom_full_structured, dict)
                        and custom_full_structured.get("data", {})
                        .get("item", {})
                        .get("content", {})
                        .get("script")
                        == "do not execute"
                    ),
                    "custom_not_found_error_schema": {
                        key: value
                        for key, value in results["custom_not_found"].items()
                        if key != "structured"
                    },
                    "stream_semantics": {
                        key: value
                        for key, value in results["streams"].items()
                        if key != "structured"
                    },
                    "stream_units_and_scope": (
                        isinstance(streams_structured, dict)
                        and {
                            row.get("type"): row.get("unit")
                            for row in streams_structured.get("data", {}).get("streams", [])
                        }.get("cadence")
                        == "1/min"
                        and "lengths only"
                        in streams_structured.get("data", {})
                        .get("alignment", {})
                        .get("quality_basis", "")
                        and streams_structured.get("data", {})
                        .get("snapshot_scope", {})
                        .get("same_selection_only")
                        is True
                    ),
                    "wellness_semantics": {
                        key: value
                        for key, value in results["wellness"].items()
                        if key != "structured"
                    },
                    "wellness_raw_fields_preserved": (
                        isinstance(wellness_structured, dict)
                        and wellness_structured.get("data", [{}])[0].get("hrv") == 42
                        and wellness_structured.get("data", [{}])[0].get("hrvSDNN") == 55
                    ),
                    "invalid_custom_id": {
                        key: value
                        for key, value in results["invalid_custom_id"].items()
                        if key != "structured"
                    },
                    "upstream_requests": len(_request_rows(request_log)),
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


async def capture_analytics_a1_probe() -> dict[str, Any]:
    """Verify interval-stats shape and protocol identity through real stdio."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-analytics-a1-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool = next(
                    tool
                    for tool in listed.tools
                    if tool.name == "get_activity_interval_stats"
                )
                result = await session.call_tool(
                    "get_activity_interval_stats",
                    {"activity_id": "a-session", "start_index": 0, "end_index": 3},
                )
                structured = result.structuredContent
                text_value, text_bytes = _text_json(result)
                schema_errors = []
                if not isinstance(tool.outputSchema, dict) or structured is None:
                    schema_errors.append("output schema or structured content absent")
                else:
                    schema_errors = [
                        error.message
                        for error in Draft202012Validator(tool.outputSchema).iter_errors(
                            structured
                        )
                    ]
                invalid_result = await session.call_tool(
                    "get_activity_interval_stats",
                    {"activity_id": "a-session", "start_index": "0", "end_index": 3},
                )
                probe = {
                    "mcp_is_error": result.isError is True,
                    "domain_status": (
                        structured.get("status")
                        if isinstance(structured, dict)
                        else None
                    ),
                    "output_schema_valid": not schema_errors,
                    "structured_text_agree": text_value == structured,
                    "utf8_json_text_bytes": text_bytes,
                    "utf8_call_tool_result_bytes": _call_tool_result_bytes(result),
                    "upstream_requests": len(_request_rows(request_log)),
                    "invalid_mcp_is_error": invalid_result.isError is True,
                    "invalid_structured_content_present": (
                        invalid_result.structuredContent is not None
                    ),
                    "invalid_text_content_present": any(
                        getattr(block, "type", None) == "text"
                        for block in invalid_result.content
                    ),
                    "raw_interval_preserved": (
                        isinstance(structured, dict)
                        and structured.get("data", {}).get("average_watts") == 0
                        and structured.get("data", {}).get("average_heartrate") is None
                    ),
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


async def capture_analytics_a2_probe() -> dict[str, Any]:
    """Verify best-efforts success and strict duration rejection through stdio."""
    with tempfile.TemporaryDirectory(prefix="intervals-read-protocol-analytics-a2-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-protocol-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool = next(
                    tool
                    for tool in listed.tools
                    if tool.name == "get_activity_best_efforts"
                )
                success_result = await session.call_tool(
                    "get_activity_best_efforts",
                    {"activity_id": "a-session", "stream": "watts", "duration": 3},
                )
                success_structured = success_result.structuredContent
                success_text, success_text_bytes = _text_json(success_result)
                success_schema_errors = []
                if not isinstance(tool.outputSchema, dict) or success_structured is None:
                    success_schema_errors.append("output schema or structured content absent")
                else:
                    success_schema_errors = [
                        error.message
                        for error in Draft202012Validator(tool.outputSchema).iter_errors(
                            success_structured
                        )
                    ]
                invalid_result = await session.call_tool(
                    "get_activity_best_efforts",
                    {
                        "activity_id": "a-session",
                        "stream": "watts",
                        "duration": "3",
                    },
                )
                probe = {
                    "success_mcp_is_error": success_result.isError is True,
                    "success_domain_status": (
                        success_structured.get("status")
                        if isinstance(success_structured, dict)
                        else None
                    ),
                    "success_output_schema_valid": not success_schema_errors,
                    "success_structured_text_agree": success_text == success_structured,
                    "success_utf8_json_text_bytes": success_text_bytes,
                    "success_utf8_call_tool_result_bytes": _call_tool_result_bytes(
                        success_result
                    ),
                    "invalid_mcp_is_error": invalid_result.isError is True,
                    "invalid_structured_content_present": (
                        invalid_result.structuredContent is not None
                    ),
                    "invalid_text_content_present": any(
                        getattr(block, "type", None) == "text"
                        for block in invalid_result.content
                    ),
                    "upstream_requests": len(_request_rows(request_log)),
                    "null_average_preserved": (
                        isinstance(success_structured, dict)
                        and success_structured.get("data", {})
                        .get("efforts", [{}])[0]
                        .get("average")
                        is None
                    ),
                }
        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-protocol-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        return probe


def _write_report(report: dict[str, Any], output: Path | None) -> None:
    serialized = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(serialized, encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Run only the original six-call scenarios; keep baseline inputs unchanged.",
    )
    parser.add_argument(
        "--server-source",
        type=Path,
        help="Optional source directory placed first on PYTHONPATH, e.g. stage0 archive src.",
    )
    args = parser.parse_args(argv)
    _write_report(
        asyncio.run(
            capture_report(
                server_source=args.server_source,
                baseline_only=args.baseline_only,
            )
        ),
        args.output,
    )


if __name__ == "__main__":
    main()
