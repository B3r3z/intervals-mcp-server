"""
Activity-related MCP tools for Intervals.icu.

This module contains tools for retrieving and managing athlete activities.
"""

from datetime import datetime, timedelta
import json
from typing import Any

from pydantic import StrictBool, StrictInt

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.validation import resolve_athlete_id
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.artifacts import ArtifactStoreError, write_activity_artifact
from intervals_mcp_server.intervals import interval_evidence
from intervals_mcp_server.stream_quality import STREAM_UNITS, participates_in_alignment
from intervals_mcp_server.respiratory import respiratory_guidance
import secrets
import time
from intervals_mcp_server.utils.ranges import range_query, validate_range

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.catalogue import coach_tool

config = get_config()
_ACTIVITY_SNAPSHOTS: dict[str, tuple[float, str, list[dict[str, Any]], bool | None]] = {}
_SNAPSHOT_TTL = 900.0
_MAX_STREAM_RANGE_SAMPLES = 10_000
_DEFAULT_STREAM_TYPES: tuple[str, ...] = (
    "time",
    "watts",
    "heartrate",
    "cadence",
    "altitude",
    "distance",
    "velocity_smooth",
)


def _validate_stream_payload(value: Any) -> str | None:
    """Return a shape error for a stream list, preserving missing/null arrays."""
    if not isinstance(value, list):
        return "stream response must be a list of objects"
    for stream in value:
        if not isinstance(stream, dict):
            return "stream list members must be objects"
        stream_type = stream.get("type")
        if not isinstance(stream_type, str) or not stream_type.strip():
            return "each stream must have a non-empty string type"
        for field in ("data", "data2"):
            if field in stream and stream[field] is not None and not isinstance(stream[field], list):
                return f"stream field {field} must be an array or null"
    return None


@coach_tool(access="read", upstream="read", local="write")
async def export_activity_data(activity_id: str, api_key: str | None = None) -> ReadResponse[Any]:
    """Export complete raw activity data to the configured local artifact.

    Use this after a compact read when the client needs all stream samples and
    interval records.  The stream arrays retain their upstream index and null
    values; this read validates their shape before handing them to the local
    artifact store. No ``types`` filter is sent, so the artifact includes every
    stream returned by that request. Streams and intervals come from separate
    HTTP reads: the returned hash verifies the local composite bytes, not an
    atomic upstream snapshot. Use ``get_artifact_chunk`` with the opaque ID when
    the MCP client cannot access the server filesystem. Source completeness
    remains unknown until the upstream data contract says otherwise.
    Tymewear VT/VE remain in raw device units, with no conversion to liters;
    use get_metric_definitions for respiratory field and FIT mapping context.
    """
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
    stream_error = _validate_stream_payload(streams)
    if stream_error:
        return invalid_upstream_response(
            resource="activity_export", message=stream_error
        )
    try:
        interval_data = interval_evidence(intervals, activity_id=activity_id)
    except ValueError as exc:
        return invalid_upstream_response(
            resource="activity_export", message=str(exc)
        )
    raw_streams = streams
    # Preserve the upstream stream list verbatim, including duplicate types.
    payload = {"activity_id": activity_id, "streams": raw_streams, "intervals": interval_data.data}
    try:
        manifest = write_activity_artifact(payload, source=f"activity/{activity_id}")
    except (ArtifactStoreError, OSError, TypeError, ValueError):
        return failure(
            resource="activity_export",
            code="ARTIFACT_WRITE_FAILED",
            message="Activity artifact could not be written.",
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


def _parse_activities_from_result(
    result: Any,
) -> tuple[list[dict[str, Any]], str | None, bool | None]:
    """Validate an activity-list response without dropping malformed rows.

    The documented endpoint returns a list.  A small compatibility exception
    accepts an object with an explicit ``activities`` or ``list`` array and a
    single activity object with a recognizable activity field.  Unknown
    objects and mixed arrays remain errors.  The optional completeness marker
    is used only when the upstream explicitly provides a boolean value.
    """
    if isinstance(result, list):
        if any(not isinstance(item, dict) for item in result):
            return [], "activity list members must be objects", None
        return [dict(item) for item in result], None, None
    if not isinstance(result, dict):
        return [], "activity response must be a list or recognized object", None
    for key in ("activities", "list"):
        if key in result:
            values = result[key]
            if not isinstance(values, list) or any(
                not isinstance(item, dict) for item in values
            ):
                return [], f"activity {key} must be an array of objects", None
            marker = result.get("source_complete_within_query")
            return [dict(item) for item in values], None, marker if isinstance(marker, bool) else None
    if any(
        key in result
        for key in ("id", "name", "startTime", "start_date_local", "start_date", "distance")
    ):
        return [dict(result)], None, None
    return [], "activity response object has no recognized activity shape", None


def _activity_date_key(activity: dict[str, Any]) -> str:
    """Return the canonical start marker for an activity.

    Intervals payloads use ``start_date_local`` today, while older payloads
    may expose ``startTime`` or ``start_date``.  Keeping the fallback order in
    one place ensures that date filtering and ordering make the same choice.
    Blank values are ignored and an activity without a usable date gets an
    empty key so it sorts after dated activities.  Consumers that need a
    calendar date (rather than the full timestamp) take the first ten
    characters from this same value.
    """
    for field in ("start_date_local", "startTime", "start_date"):
        value = activity.get(field)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _deduplicate_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one row per activity ID while preserving rows without an ID."""
    unique: dict[str, dict[str, Any]] = {}
    for index, activity in enumerate(activities):
        raw_id = activity.get("id")
        id_key = str(raw_id).strip() if raw_id is not None and str(raw_id).strip() else f"__missing_{index}"
        unique[id_key] = activity
    return list(unique.values())


def _sort_activities(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort newest dates first, then deterministically by string activity ID."""
    # Python's sort is stable: sorting IDs first makes them the tie-breaker
    # when the second pass groups rows by their canonical date.
    by_id = sorted(
        activities,
        key=lambda activity: str(activity.get("id", "")).strip(),
    )
    return sorted(by_id, key=_activity_date_key, reverse=True)


def _activity_source_limitation(activity: dict[str, Any]) -> dict[str, Any] | None:
    """Describe an explicit upstream Hidden record without guessing from sparsity."""
    source = activity.get("source")
    name = activity.get("name")
    note = activity.get("_note")
    note_text = note.strip() if isinstance(note, str) else ""
    hidden_name = isinstance(name, str) and name.strip().casefold() == "hidden"
    hidden_note = bool(note_text) and (
        source == "STRAVA"
        or any(
            marker in note_text.casefold()
            for marker in ("hidden", "privacy", "private", "restricted", "unavailable")
        )
    )
    if not hidden_name and not hidden_note:
        return None
    return {
        "code": "SOURCE_DATA_LIMITED",
        "activity_id": activity.get("id"),
        "source": source,
        "message": note_text or "The upstream source returned a hidden activity record.",
    }


def _activity_detail_shape_error(value: Any) -> str | None:
    """Reject non-activity objects while retaining explicit hidden stubs."""
    if not isinstance(value, dict) or not value:
        return "activity detail response must be a non-empty object"
    if _activity_source_limitation(value) is not None:
        return None
    if "id" not in value:
        return "activity detail response must contain an activity id"
    semantic_fields = {
        "name",
        "type",
        "startTime",
        "start_date",
        "start_date_local",
        "distance",
        "source",
        "duration",
        "moving_time",
    }
    if semantic_fields.isdisjoint(value):
        return "activity detail response has no recognized activity fields"
    return None


def _sport_filter_limitation(
    activity: dict[str, Any], sports: list[str] | None
) -> dict[str, Any] | None:
    """Mark a hidden row whose sport filter cannot be verified from its stub."""
    if not sports or _activity_source_limitation(activity) is None:
        return None
    has_type = isinstance(activity.get("type"), str) and bool(activity["type"].strip())
    has_sport = isinstance(activity.get("sport"), str) and bool(activity["sport"].strip())
    if has_type or has_sport:
        return None
    return {
        "code": "SPORT_FILTER_UNVERIFIED",
        "activity_id": activity.get("id"),
        "requested_sports": list(sports),
        "message": "The hidden source record has no sport field; the requested sport filter cannot be verified.",
    }


@coach_tool(access="legacy_write", upstream="write", local="none")
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
    return upstream_failure(value, resource=resource)


@coach_tool(access="read", upstream="read", local="memory")
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
    """List activities in a half-open local-date range with bounded paging.

    ``start_date`` is inclusive and ``end_date_exclusive`` is exclusive.  A
    valid empty list is different from a malformed upstream response.  The
    first page is snapshotted for cursor continuation, and a cursor is valid
    only for the same athlete, range, timezone, and sport filter.  The source
    endpoint does not expose a trustworthy completeness marker, so source
    completeness stays ``null`` even when the returned list is short.  A
    Hidden source stub without a sport field is retained for identity, but a
    requested sport match is reported as unverified.
    """
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
        if cached[1] != query_key:
            return failure(
                resource="activities",
                code="INVALID_CURSOR",
                message="cursor snapshot does not match query",
                phase="validation",
            )
        rows = cached[2]
        source_complete = cached[3]
        offset = int(parts[2])
        snapshot = parts[1]
    else:
        result = await make_intervals_request(
            url=f"/athlete/{aid}/activities",
            api_key=api_key,
            params={"oldest": start, "newest": end, "limit": 10000},
        )
        failed = _read_error(result, "activities")
        if failed:
            return failed
        parsed_rows, parse_error, explicit_source_complete = _parse_activities_from_result(result)
        if parse_error:
            return invalid_upstream_response(resource="activities", message=parse_error, athlete_id=aid)
        source_complete = explicit_source_complete
        rows = _deduplicate_activities(parsed_rows)
        if start_date or end_date_exclusive:
            rows = [
                row
                for row in rows
                if start <= _activity_date_key(row)[:10] < end_exclusive
            ]
        if sports:
            rows = [
                row
                for row in rows
                if row.get("type") in sports
                or row.get("sport") in sports
                or _activity_source_limitation(row) is not None
            ]
        rows = _sort_activities(rows)
        offset = 0
        snapshot = secrets.token_hex(12)
    if not cursor:
        _ACTIVITY_SNAPSHOTS[snapshot] = (
            time.monotonic(),
            query_key,
            rows,
            source_complete,
        )
    page = rows[offset : offset + size]
    source_limitations: list[dict[str, Any]] = []
    for row in rows:
        limitation = _activity_source_limitation(row)
        if limitation is not None:
            source_limitations.append(limitation)
        sport_limitation = _sport_filter_limitation(row, sports)
        if sport_limitation is not None:
            source_limitations.append(sport_limitation)
    page_ids = {row.get("id") for row in page}
    page_limitations = [
        limitation
        for limitation in source_limitations
        if limitation["activity_id"] in page_ids
    ]
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
    reasons: list[str] = []
    if source_complete is False:
        reasons.append("upstream_limit_reached")
    elif source_complete is None:
        reasons.append("upstream_completeness_unverified")
    if any(item["code"] == "SOURCE_DATA_LIMITED" for item in source_limitations):
        reasons.append("source_record_hidden")
    if any(item["code"] == "SPORT_FILTER_UNVERIFIED" for item in source_limitations):
        reasons.append("sport_filter_unverified")
    response = success(
        page,
        resource="activities",
        athlete_id=aid,
        query=query,
        pagination={"snapshot_id": snapshot, "next_cursor": next_cursor},
        coverage={
            "source_complete_within_query": (
                False if source_limitations else source_complete
            ),
            "response_complete": next_cursor is None,
            "truncated": next_cursor is not None,
            "reasons": reasons,
        },
        warnings=list(dict.fromkeys(item["code"] for item in source_limitations)),
        limitations=page_limitations,
    )
    if source_limitations:
        response.status = "partial"
    return response


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_details(
    activity_id: str,
    api_key: str | None = None,
    include_intervals: StrictBool = False,
) -> ReadResponse[Any]:
    """Return one activity with upstream fields preserved.

    A source-hidden record is returned as ``partial`` with an explicit
    limitation.  In that case the row is useful for identity and timing, but
    it is not evidence that metrics, intervals, or streams are available; use
    the dedicated interval and stream tools to check those resources. Set
    ``include_intervals`` to request the upstream embedded interval container;
    missing embedded intervals still require ``get_activity_intervals``.
    For Tymewear, VT is relative tidal volume per breath (not VT1/VT2), VE
    is relative minute ventilation, and BR is breaths/min. Custom L/br or
    L/min labels are not calibration evidence; use get_metric_definitions.
    """
    if not isinstance(include_intervals, bool):
        return failure(
            resource="activity",
            code="INVALID_INCLUDE_INTERVALS",
            message="include_intervals must be a boolean",
            phase="validation",
            query={"activity_id": activity_id},
        )
    request_kwargs: dict[str, Any] = {
        "url": f"/activity/{activity_id}",
        "api_key": api_key,
    }
    if include_intervals:
        request_kwargs["params"] = {"intervals": True}
    result = await make_intervals_request(**request_kwargs)
    failed = _read_error(result, "activity")
    if failed:
        return failed
    shape_error = _activity_detail_shape_error(result)
    if shape_error:
        return invalid_upstream_response(
            resource="activity",
            message=shape_error,
            query={
                "activity_id": activity_id,
                "include_intervals": bool(include_intervals),
            },
        )
    assert isinstance(result, dict)
    row = dict(result)
    limitation = _activity_source_limitation(row)
    hidden = limitation is not None
    response = success(
        row,
        resource="activity",
        query={
            "activity_id": activity_id,
            "include_intervals": bool(include_intervals),
        },
        coverage={
            "source_complete_within_query": False if hidden else None,
            "response_complete": True,
            "reasons": ["source_record_hidden"] if hidden else [
                "upstream_completeness_unverified"
            ],
        },
        warnings=["SOURCE_DATA_LIMITED"] if hidden else [],
        limitations=[limitation] if limitation else [],
    )
    if hidden:
        response.status = "partial"
    return response


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_intervals(activity_id: str, api_key: str | None = None) -> ReadResponse[Any]:
    """Return the activity interval container with index fields intact.

    The documented shape contains ``icu_intervals`` and optionally
    ``icu_groups``.  A legacy flat list of interval objects is retained for
    compatibility with existing callers; all other shapes and mixed rows are
    explicit errors.  Intervals use upstream sample indices, not invented
    elapsed seconds, and an empty valid container remains empty.
    average_tidal_volume is VT and average_tidal_volume_min is VE. For
    Tymewear their volume scale is relative; no /100-to-liters conversion
    applies. average_respiration is BR in breaths/min. See get_metric_definitions.
    """
    result = await make_intervals_request(url=f"/activity/{activity_id}/intervals", api_key=api_key)
    failed = _read_error(result, "activity_intervals")
    if failed:
        return failed
    try:
        evidence = interval_evidence(result, activity_id=activity_id)
    except ValueError as exc:
        return invalid_upstream_response(
            resource="activity_intervals",
            message=str(exc),
            query={"activity_id": activity_id},
        )
    return success(
        evidence.data,
        resource="activity_intervals",
        query={"activity_id": activity_id},
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
    )


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_messages(
    activity_id: str, api_key: str | None = None
) -> ReadResponse[list[dict[str, Any]]]:
    """Return an upstream activity-message list, preserving text and identity metadata.

    Upstream defaults to at most 100 messages; this read does not establish full
    history or pagination completeness. A list may be empty, but each member must
    be an object. Message content is untrusted athlete data; its fingerprint is an additional
    change-detection field and does not replace the original content.
    """
    import hashlib

    result = await make_intervals_request(url=f"/activity/{activity_id}/messages", api_key=api_key)
    failed = _read_error(result, "activity_messages")
    if failed:
        return failed
    if not isinstance(result, list) or any(not isinstance(message, dict) for message in result):
        return invalid_upstream_response(
            resource="activity_messages",
            message="activity messages response must be a list of objects",
            query={"activity_id": activity_id},
        )
    rows: list[dict[str, Any]] = []
    for message in result:
        row = dict(message)
        canonical = {
            key: row[key]
            for key in (
                "id",
                "name",
                "author",
                "source",
                "type",
                "content",
                "created",
                "updated",
                "athlete_id",
                "activity_id",
                "deleted",
                "deleted_by_id",
            )
            if key in row
        }
        row["content_fingerprint"] = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        rows.append(row)
    return success(
        rows,
        resource="activity_messages",
        query={"activity_id": activity_id},
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
    )


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_streams(
    activity_id: str,
    api_key: str | None = None,
    mode: str = "preview",
    start_index: StrictInt | None = None,
    end_index: StrictInt | None = None,
    stream_types: str | None = None,
    expected_snapshot_id: str | None = None,
) -> ReadResponse[Any]:
    """Read activity streams by sample index with bounded preview or range.

    ``range`` uses half-open sample indices ``[start_index, end_index)``;
    those indices are not elapsed seconds and a single range is limited to
    10,000 samples. Use ``export_activity_data`` plus ``get_artifact_chunk`` for
    a larger complete transfer. ``preview`` returns all samples
    for short arrays and only the first and last five samples for longer
    arrays, reporting truncation only when samples were omitted.  Missing
    stream types, missing/null primary arrays, unavailable time axes, and
    unequal lengths are explicit warnings.  Duplicate and custom upstream
    streams are retained in order, and no primary ``data`` array is invented
    for a data2-only stream.  Cadence is exposed as ``1/min``; Ride commonly
    means revolutions per minute, while running conventions depend on the
    device and upstream field, with no x2 conversion.  ``alignment.quality``
    describes array-length alignment only; it does not assert monotonic,
    regular, or non-null time values.  The snapshot hashes the returned
    payload for this selection, so a continuation must keep the same activity
    and ``stream_types``.

    Respiratory fields: tidal_volume = VT (volume per breath, not VT1/VT2),
    tidal_volume_min = VE (minute ventilation), respiration = BR (breaths/min).
    When sourced from Tymewear, VT uses relative i.u. and VE relative vol/min,
    not calibrated liters. Do not divide VT by 100 or 1000. The response adds
    conditional documentation in provenance.respiratory_interpretation;
    original samples and source unit labels are preserved. Use
    get_metric_definitions and get_custom_items to check mappings and units.
    """
    import hashlib

    if any(
        value is not None
        and (isinstance(value, bool) or not isinstance(value, int))
        for value in (start_index, end_index)
    ):
        return failure(
            resource="activity_streams",
            code="INVALID_RANGE",
            message="sample indices must be integers",
            phase="validation",
        )
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
        (start_index is not None and start_index < 0)
        or (end_index is not None and end_index <= (start_index or 0))
    ):
        return failure(
            resource="activity_streams",
            code="INVALID_RANGE",
            message="invalid range",
            phase="validation",
        )
    if (
        mode == "range"
        and start_index is not None
        and end_index is not None
        and end_index - start_index > _MAX_STREAM_RANGE_SAMPLES
    ):
        return failure(
            resource="activity_streams",
            code="RANGE_TOO_LARGE",
            message="A stream range may contain at most 10,000 samples.",
            phase="validation",
            recommended_action=(
                "Use export_activity_data, then retrieve the artifact with "
                "get_artifact_chunk."
            ),
        )
    if stream_types is not None and not isinstance(stream_types, str):
        return failure(
            resource="activity_streams",
            code="INVALID_STREAM_TYPES",
            message="stream_types must be a comma-separated string",
            phase="validation",
        )
    requested = (
        [item.strip() for item in stream_types.split(",") if item.strip()]
        if stream_types is not None
        else list(_DEFAULT_STREAM_TYPES)
    )
    requested_param = ",".join(requested)
    result = await make_intervals_request(
        url=f"/activity/{activity_id}/streams",
        api_key=api_key,
        params={"types": requested_param},
    )
    failed = _read_error(result, "activity_streams")
    if failed:
        return failed
    shape_error = _validate_stream_payload(result)
    if shape_error:
        return invalid_upstream_response(
            resource="activity_streams",
            message=shape_error,
            query={"activity_id": activity_id},
        )
    if not isinstance(result, list):
        return invalid_upstream_response(
            resource="activity_streams",
            message="stream response must be a list of objects",
            query={"activity_id": activity_id},
        )
    streams = [dict(stream) for stream in result]
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
    available = [str(stream["type"]) for stream in streams]
    missing = [item for item in requested if item not in available]
    selected = [
        stream
        for stream in streams
        if stream_types is None or stream.get("type") in requested
    ]
    source_lengths_all = [
        len(stream[field])
        for stream in selected
        for field in ("data", "data2")
        if isinstance(stream.get(field), list)
    ]
    time_source = next(
        (
            stream.get("data")
            for stream in streams
            if stream.get("type") == "time" and isinstance(stream.get("data"), list)
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

    def select_values(
        values: list[Any],
    ) -> tuple[list[Any], list[dict[str, int]], bool]:
        if mode == "preview":
            if len(values) <= 10:
                return list(values), [{"start_index": 0, "end_index": len(values)}], False
            return (
                values[:5] + values[-5:],
                [
                    {"start_index": 0, "end_index": 5},
                    {"start_index": len(values) - 5, "end_index": len(values)},
                ],
                True,
            )
        assert start_index is not None and end_index is not None
        available_end = min(end_index, len(values))
        if start_index >= available_end:
            return [], [], False
        return (
            values[start_index:available_end],
            [{"start_index": start_index, "end_index": available_end}],
            False,
        )

    payload_streams: list[dict[str, Any]] = []
    alignment_lengths: list[dict[str, Any]] = []
    has_missing_indices = False
    preview_truncated = False
    missing_primary_data = False
    for stream_index, stream in enumerate(selected):
        row = dict(stream)
        for field, prefix in (("data", ""), ("data2", "data2_")):
            state = "missing" if field not in stream else "null" if stream[field] is None else "present"
            row[f"{prefix}state" if prefix else "data_state"] = state
            raw_values = stream.get(field)
            if isinstance(raw_values, list):
                values, spans, truncated = select_values(raw_values)
                row[field] = values
                row[f"{prefix}source_count" if prefix else "source_count"] = len(raw_values)
                row[f"{prefix}returned_count" if prefix else "returned_count"] = len(values)
                row[f"{prefix}effective_spans" if prefix else "effective_spans"] = spans
                preview_truncated = preview_truncated or truncated
                if mode == "range" and end_index is not None and end_index > len(raw_values):
                    missing_start = max(start_index or 0, len(raw_values))
                    row[
                        "data2_missing_indices" if field == "data2" else "missing_indices"
                    ] = [{"start_index": missing_start, "end_index": end_index}]
                    has_missing_indices = True
            else:
                row[f"{prefix}source_count" if prefix else "source_count"] = None
                row[f"{prefix}returned_count" if prefix else "returned_count"] = None
                row[f"{prefix}effective_spans" if prefix else "effective_spans"] = []
                if field == "data":
                    missing_primary_data = True
                if mode == "range" and end_index is not None and field == "data":
                    row[
                        "data2_missing_indices" if field == "data2" else "missing_indices"
                    ] = [{"start_index": start_index or 0, "end_index": end_index}]
                    has_missing_indices = True
            if not participates_in_alignment(stream, field):
                continue
            alignment_lengths.append(
                {
                    "stream_index": stream_index,
                    "type": stream.get("type"),
                    "array": field,
                    "count": len(raw_values) if isinstance(raw_values, list) else None,
                    "state": state,
                }
            )
        if "unit" not in row:
            row["unit"] = STREAM_UNITS.get(str(row.get("type")))
        payload_streams.append(row)

    time_axis = None
    if isinstance(time_source, list):
        time_axis, time_spans, time_truncated = select_values(time_source)
        preview_truncated = preview_truncated or time_truncated
    else:
        time_spans = []
    counts = [item["count"] for item in alignment_lengths if item["count"] is not None]
    has_missing_arrays = any(item["count"] is None for item in alignment_lengths)
    unequal = len(set(counts)) > 1
    warnings = (
        (["MISSING_STREAM"] if missing else [])
        + (["UNEQUAL_STREAM_LENGTHS"] if unequal else [])
        + (["MISSING_PRIMARY_DATA"] if missing_primary_data else [])
        + (["TIME_AXIS_UNAVAILABLE"] if time_source is None else [])
    )
    reasons = ["upstream_completeness_unverified"]
    if preview_truncated:
        reasons.append("preview")
    if unequal or has_missing_arrays:
        reasons.append("UNEQUAL_STREAM_LENGTHS")
    if has_missing_indices:
        reasons.append("MISSING_SAMPLE_INDICES")
    if time_source is None:
        reasons.append("TIME_AXIS_UNAVAILABLE")
    response_metadata: dict[str, Any] = {}
    respiratory_interpretation = respiratory_guidance(stream["type"] for stream in selected)
    if respiratory_interpretation:
        response_metadata["provenance"] = {"respiratory_interpretation": respiratory_interpretation}
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
                "equal_source_lengths": not unequal and not has_missing_arrays,
                "quality_basis": (
                    "array lengths only; does not assert monotonic, regular, or non-null time values"
                ),
                "quality": (
                    "missing_arrays"
                    if has_missing_arrays
                    else "unequal_lengths"
                    if unequal
                    else "aligned"
                ),
            },
            "snapshot_scope": {
                "basis": "sha256 of the returned stream payload for the requested selection",
                "continuation_requires": {
                    "activity_id": activity_id,
                    "stream_types": requested,
                },
                "same_selection_only": True,
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
            "response_complete": not (
                preview_truncated
                or has_missing_indices
                or missing
                or unequal
                or has_missing_arrays
                or time_source is None
            ),
            "truncated": preview_truncated or has_missing_indices,
            "reasons": reasons,
        },
        warnings=warnings,
        **response_metadata,
    )
    if (
        preview_truncated
        or has_missing_indices
        or missing
        or unequal
        or has_missing_arrays
        or time_source is None
    ):
        response.status = "partial"
    return response
