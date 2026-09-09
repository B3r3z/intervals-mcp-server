"""
Activity-related MCP tools for Intervals.icu.

This module contains tools for retrieving and managing athlete activities.
"""

from datetime import datetime, timedelta
import json
from typing import Any

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.tools.gear import (
    resolve_gear_for_activity,
    resolve_gear_for_activities,
)
from intervals_mcp_server.utils.validation import resolve_athlete_id
from intervals_mcp_server.contracts import ReadResponse, success, failure
from intervals_mcp_server.artifacts import write_activity_artifact
import secrets
import time
from intervals_mcp_server.utils.ranges import range_query, validate_range

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

config = get_config()
_ACTIVITY_SNAPSHOTS: dict[str, tuple[float, str, list[dict[str, Any]], bool | None]] = {}
_SNAPSHOT_TTL = 900.0


@mcp.tool()
async def export_activity_data(activity_id: str, api_key: str | None = None) -> ReadResponse[Any]:
    """Export complete raw activity streams/intervals to the configured local artifact directory."""
    if not activity_id.strip():
        return failure(
            resource="activity_export",
            code="INVALID_ACTIVITY_ID",
            message="activity_id is required",
            phase="validation",
        )
    streams = await make_intervals_request(url=f"/activity/{activity_id}/streams", api_key=api_key)
    failed = _read_error(streams, "activity_export")
    if failed:
        return failed
    intervals = await make_intervals_request(
        url=f"/activity/{activity_id}/intervals", api_key=api_key
    )
    failed = _read_error(intervals, "activity_export")
    if failed:
        return failed
    raw_streams = streams if isinstance(streams, list) else []
    # Preserve the upstream stream list verbatim, including duplicate types.
    payload = {"activity_id": activity_id, "streams": raw_streams, "intervals": intervals}
    import hashlib

    snapshot_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    try:
        manifest = write_activity_artifact(
            payload, snapshot_id=snapshot_id, source=f"activity/{activity_id}"
        )
    except (OSError, ValueError) as exc:
        return failure(
            resource="activity_export",
            code="ARTIFACT_WRITE_FAILED",
            message=str(exc),
            phase="artifact",
            recommended_action="check artifact configuration and retry the read",
        )
    return success(
        manifest,
        resource="activity_export",
        query={"activity_id": activity_id},
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
    )


def _parse_activities_from_result(result: Any) -> list[dict[str, Any]]:
    """Extract a list of activity dictionaries from the API result."""
    activities: list[dict[str, Any]] = []

    if isinstance(result, list):
        activities = [item for item in result if isinstance(item, dict)]
    elif isinstance(result, dict):
        # Result is a single activity or a container
        for _key, value in result.items():
            if isinstance(value, list):
                activities = [item for item in value if isinstance(item, dict)]
                break
        # If no list was found but the dict has typical activity fields, treat it as a single activity
        if not activities and any(key in result for key in ["name", "startTime", "distance"]):
            activities = [result]

    return activities


@mcp.tool()
async def add_activity_message(
    activity_id: str,
    content: str,
    api_key: str | None = None,
) -> str:
    """Add a message (note/comment) to an activity on Intervals.icu

    Args:
        activity_id: The Intervals.icu activity ID
        content: The message text to add
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
    """
    result = await make_intervals_request(
        url=f"/activity/{activity_id}/messages",
        api_key=api_key,
        method="POST",
        data={"content": content},
    )

    if isinstance(result, dict) and "error" in result:
        error_message = result.get("message", "Unknown error")
        return f"Error adding message to activity: {error_message}"

    if not result or not isinstance(result, dict):
        return "Error: Unexpected response when adding message."

    msg_id = result.get("id")
    if msg_id is not None:
        return f"Successfully added message (ID: {msg_id}) to activity {activity_id}."
    return f"Message appears to have been added to activity {activity_id}, but no ID was returned. Please verify manually."


def _read_error(value: Any, resource: str) -> ReadResponse[Any] | None:
    if isinstance(value, dict) and value.get("error"):
        return failure(
            resource=resource,
            code=str(value.get("code", "UPSTREAM_ERROR")),
            message=str(value.get("message", "upstream request failed")),
            phase=str(value.get("phase", "http")),
            http_status=value.get("http_status") or value.get("status_code"),
        )
    return None


@mcp.tool()
async def get_activities(
    athlete_id: str | None = None,
    api_key: str | None = None,
    start_date: str | None = None,
    end_date_exclusive: str | None = None,
    timezone: str = "Europe/Warsaw",
    page_size: int = 10,
    cursor: str | None = None,
    sports: list[str] | None = None,
    limit: int | None = None,
) -> ReadResponse[list[dict[str, Any]]]:
    if (limit if limit is not None else page_size) <= 0:
        return failure(
            resource="activities",
            code="INVALID_PAGE_SIZE",
            message="page_size must be positive",
            phase="validation",
        )
    aid, error = resolve_athlete_id(athlete_id, config.athlete_id)
    if error:
        return failure(
            resource="activities", code="INVALID_ATHLETE", message=error, phase="validation"
        )
    checked = validate_range(start_date, end_date_exclusive, None, timezone)
    if isinstance(checked, str):
        return failure(
            resource="activities", code="INVALID_RANGE", message=checked, phase="validation"
        )
    start, end_exclusive, tz, _deprecated = checked
    end = (datetime.fromisoformat(end_exclusive).date() - timedelta(days=1)).isoformat()
    size = limit if limit is not None else page_size
    query_key = json.dumps([aid, start, end_exclusive, timezone, sports], sort_keys=True)
    if cursor:
        parts = cursor.split(".")
        if (
            len(parts) != 3
            or parts[0] != __import__("hashlib").sha256(query_key.encode()).hexdigest()[:16]
            or not parts[2].isdigit()
        ):
            return failure(
                resource="activities",
                code="INVALID_CURSOR",
                message="cursor does not match query",
                phase="validation",
            )
        cached = _ACTIVITY_SNAPSHOTS.get(parts[1])
        if not cached or time.monotonic() - cached[0] > _SNAPSHOT_TTL:
            return failure(
                resource="activities",
                code="CURSOR_EXPIRED",
                message="cursor expired",
                phase="validation",
            )
        rows = cached[2]
        source_complete = cached[3]
        offset = int(parts[2])
    else:
        result = await make_intervals_request(
            url=f"/athlete/{aid}/activities",
            api_key=api_key,
            params={"oldest": start, "newest": end, "limit": 10000},
        )
        failed = _read_error(result, "activities")
        if failed:
            return failed
        source_complete = len(result) < 10000 if isinstance(result, list) else None
        rows = sorted(
            _parse_activities_from_result(result),
            key=lambda row: (str(row.get("startTime", "")), str(row.get("id", ""))),
        )
        offset = 0
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique[str(row.get("id", f"__missing_{len(unique)}"))] = row
    rows = list(unique.values())
    if start_date or end_date_exclusive:
        rows = [
            row
            for row in rows
            if start
            <= str(row.get("start_date_local", row.get("startTime", "")))[:10]
            < end_exclusive
        ]
    await resolve_gear_for_activities(rows, athlete_id=aid, api_key=api_key)
    if sports:
        rows = [row for row in rows if row.get("type") in sports or row.get("sport") in sports]
    snapshot = cursor.split(".")[1] if cursor else secrets.token_hex(12)
    if not cursor:
        _ACTIVITY_SNAPSHOTS[snapshot] = (
            time.monotonic(),
            query_key,
            rows,
            source_complete,
        )
    page = rows[offset : offset + size]
    next_cursor = (
        None
        if offset + size >= len(rows)
        else __import__("hashlib").sha256(query_key.encode()).hexdigest()[:16]
        + "."
        + snapshot
        + "."
        + str(offset + size)
    )
    query: dict[str, Any] = range_query(start, end_exclusive, tz, timezone)
    query.update({"upstream_newest": end, "sports": sports, "cursor": cursor})
    return success(
        page,
        resource="activities",
        athlete_id=aid,
        query=query,
        pagination={"snapshot_id": snapshot, "next_cursor": next_cursor},
        coverage={
            "source_complete_within_query": source_complete,
            "response_complete": True,
            "truncated": next_cursor is not None,
            "reasons": (
                []
                if source_complete
                else [
                    "upstream_limit_reached"
                    if source_complete is False
                    else "upstream_completeness_unverified"
                ]
            ),
        },
    )


@mcp.tool()
async def get_activity_details(activity_id: str, api_key: str | None = None) -> ReadResponse[Any]:
    result = await make_intervals_request(url=f"/activity/{activity_id}", api_key=api_key)
    failed = _read_error(result, "activity")
    if failed:
        return failed
    row = result[0] if isinstance(result, list) and result else result
    if isinstance(row, dict):
        await resolve_gear_for_activity(row, api_key=api_key)
    return success(row, resource="activity", query={"activity_id": activity_id})


@mcp.tool()
async def get_activity_intervals(activity_id: str, api_key: str | None = None) -> ReadResponse[Any]:
    result = await make_intervals_request(url=f"/activity/{activity_id}/intervals", api_key=api_key)
    failed = _read_error(result, "activity_intervals")
    if failed:
        return failed
    return success(
        result if result is not None else [],
        resource="activity_intervals",
        query={"activity_id": activity_id},
    )


@mcp.tool()
async def get_activity_messages(
    activity_id: str, api_key: str | None = None
) -> ReadResponse[list[dict[str, Any]]]:
    import hashlib

    result = await make_intervals_request(url=f"/activity/{activity_id}/messages", api_key=api_key)
    failed = _read_error(result, "activity_messages")
    if failed:
        return failed
    rows = []
    for message in result if isinstance(result, list) else []:
        if isinstance(message, dict):
            row = dict(message)
            canonical = {
                k: row[k]
                for k in ("id", "name", "author", "source", "type", "content", "created", "updated")
                if k in row
            }
            row["content_fingerprint"] = hashlib.sha256(
                json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            rows.append(row)
    return success(rows, resource="activity_messages", query={"activity_id": activity_id})


@mcp.tool()
async def get_activity_streams(
    activity_id: str,
    api_key: str | None = None,
    mode: str = "preview",
    start_index: int | None = None,
    end_index: int | None = None,
    stream_types: str | None = None,
    expected_snapshot_id: str | None = None,
) -> ReadResponse[Any]:
    import hashlib

    if mode not in {"preview", "range"}:
        return failure(
            resource="activity_streams",
            code="INVALID_MODE",
            message="mode must be preview or range",
            phase="validation",
        )
    if mode == "range" and (start_index is None or end_index is None):
        return failure(
            resource="activity_streams",
            code="INVALID_RANGE",
            message="range requires start_index and end_index",
            phase="validation",
        )
    if mode == "range" and (
        start_index is not None
        and start_index < 0
        or end_index is not None
        and end_index <= (start_index or 0)
    ):
        return failure(
            resource="activity_streams",
            code="INVALID_RANGE",
            message="invalid range",
            phase="validation",
        )
    requested_param = stream_types or (
        "time,watts,heartrate,cadence,altitude,distance,velocity_smooth"
    )
    result = await make_intervals_request(
        url=f"/activity/{activity_id}/streams",
        api_key=api_key,
        params={"types": requested_param},
    )
    failed = _read_error(result, "activity_streams")
    if failed:
        return failed
    streams = result if isinstance(result, list) else []
    canonical = json.dumps(
        streams, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    snapshot = hashlib.sha256(canonical).hexdigest()
    if expected_snapshot_id and expected_snapshot_id != snapshot:
        return failure(
            resource="activity_streams",
            code="SNAPSHOT_CHANGED",
            message="stream snapshot changed",
            phase="validation",
        )
    available = [str(s.get("type")) for s in streams if isinstance(s, dict)]
    requested = [x for x in (stream_types or ",".join(available)).split(",") if x]
    missing = [x for x in requested if x not in available]
    selected = [
        stream
        for stream in streams
        if isinstance(stream, dict) and (not stream_types or stream.get("type") in requested)
    ]
    source_lengths_all = [
        len(stream[array_name])
        for stream in selected
        for array_name in ("data", "data2")
        if isinstance(stream.get(array_name), list)
    ]
    time_source = next(
        (
            stream.get("data")
            for stream in streams
            if isinstance(stream, dict)
            and stream.get("type") == "time"
            and isinstance(stream.get("data"), list)
        ),
        None,
    )
    common_length = (
        len(time_source) if isinstance(time_source, list) else max(source_lengths_all, default=0)
    )
    if mode == "range" and end_index is not None and end_index > common_length:
        return failure(
            resource="activity_streams",
            code="OUT_OF_RANGE",
            message="range exceeds activity axis",
            phase="validation",
        )

    def select_values(values: list[Any]) -> tuple[list[Any], list[dict[str, int]]]:
        if mode == "preview":
            if len(values) <= 10:
                return list(values), [{"start_index": 0, "end_index": len(values)}]
            return (
                values[:5] + values[-5:],
                [
                    {"start_index": 0, "end_index": 5},
                    {"start_index": len(values) - 5, "end_index": len(values)},
                ],
            )
        assert start_index is not None and end_index is not None
        available_end = min(end_index, len(values))
        if start_index >= available_end:
            return [], []
        return values[start_index:available_end], [
            {"start_index": start_index, "end_index": available_end}
        ]

    payload_streams: list[dict[str, Any]] = []
    alignment_lengths: list[dict[str, Any]] = []
    has_missing_indices = False
    for stream_index, stream in enumerate(selected):
        row = dict(stream)
        raw_values = row.get("data")
        values: list[Any] = raw_values if isinstance(raw_values, list) else []
        row["data"], data_spans = select_values(values)
        row["source_count"] = len(values)
        row["returned_count"] = len(row["data"])
        row["effective_spans"] = data_spans
        alignment_lengths.append(
            {
                "stream_index": stream_index,
                "type": stream.get("type"),
                "array": "data",
                "count": len(values),
            }
        )
        if mode == "range" and end_index is not None and end_index > len(values):
            missing_start = max(start_index or 0, len(values))
            row["missing_indices"] = [{"start_index": missing_start, "end_index": end_index}]
            has_missing_indices = True
        if isinstance(stream.get("data2"), list):
            data2 = stream["data2"]
            row["data2"], data2_spans = select_values(data2)
            row["data2_source_count"] = len(data2)
            row["data2_returned_count"] = len(row["data2"])
            row["data2_effective_spans"] = data2_spans
            alignment_lengths.append(
                {
                    "stream_index": stream_index,
                    "type": stream.get("type"),
                    "array": "data2",
                    "count": len(data2),
                }
            )
            if mode == "range" and end_index is not None and end_index > len(data2):
                has_missing_indices = True
                row["data2_missing_indices"] = [
                    {
                        "start_index": max(start_index or 0, len(data2)),
                        "end_index": end_index,
                    }
                ]
        row["unit"] = row.get("unit") or {
            "time": "s",
            "watts": "W",
            "heartrate": "bpm",
            "cadence": "rpm",
            "altitude": "m",
            "distance": "m",
            "velocity_smooth": "m/s",
            "temperature": "C",
            "coreTemperature": "C",
            "skinTemperature": "C",
            "joules": "J",
        }.get(str(row.get("type")))
        payload_streams.append(row)

    time_axis = None
    if isinstance(time_source, list):
        time_axis, time_spans = select_values(time_source)
    else:
        time_spans = []
    unequal = len({item["count"] for item in alignment_lengths}) > 1
    warnings = (
        (["MISSING_STREAM"] if missing else [])
        + (["UNEQUAL_STREAM_LENGTHS"] if unequal else [])
        + (["TIME_AXIS_UNAVAILABLE"] if time_source is None else [])
    )
    reasons = (
        (["preview"] if mode == "preview" else [])
        + (["UNEQUAL_STREAM_LENGTHS"] if unequal else [])
        + (["MISSING_SAMPLE_INDICES"] if has_missing_indices else [])
        + (["TIME_AXIS_UNAVAILABLE"] if time_source is None else [])
    )
    response = success(
        {
            "activity_id": activity_id,
            "mode": mode,
            "streams": payload_streams,
            "requested": requested,
            "available": available,
            "missing": missing,
            "snapshot_id": snapshot,
            "time_axis": time_axis,
            "time_axis_effective_spans": time_spans,
            "alignment": {
                "source_lengths": alignment_lengths,
                "equal_source_lengths": not unequal,
                "quality": "unequal_lengths" if unequal else "aligned",
            },
        },
        resource="activity_streams",
        query={
            "activity_id": activity_id,
            "mode": mode,
            "start_index": start_index,
            "end_index": end_index,
            "stream_types": requested,
        },
        pagination={"snapshot_id": snapshot},
        coverage={
            "source_complete_within_query": None,
            "response_complete": mode == "range" and not has_missing_indices,
            "truncated": mode == "preview" or has_missing_indices,
            "reasons": reasons,
        },
        warnings=warnings,
    )
    if mode == "preview" or has_missing_indices or missing:
        response.status = "partial"
    return response
