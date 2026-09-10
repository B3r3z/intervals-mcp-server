"""Bounded activity analytics reads backed by Intervals.icu."""

from __future__ import annotations

import math
import json
from copy import deepcopy
from typing import Any

from pydantic import StrictBool, StrictFloat, StrictInt

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.respiratory import respiratory_guidance


_INTERVAL_MARKER_FIELDS = {
    "start_index",
    "end_index",
    "distance",
    "moving_time",
    "elapsed_time",
    "average_watts",
    "average_heartrate",
    "average_speed",
    "joules",
    "id",
    "type",
    "label",
}

_INTERVAL_INTEGER_FIELDS = {
    "start_index",
    "end_index",
    "moving_time",
    "elapsed_time",
    "average_watts",
    "average_watts_alt",
    "average_watts_alt_acc",
    "min_watts",
    "max_watts",
    "weighted_average_watts",
    "joules",
    "joules_above_ftp",
    "intensity",
    "wbal_start",
    "wbal_end",
    "zone",
    "zone_min_watts",
    "zone_max_watts",
    "average_heartrate",
    "min_heartrate",
    "max_heartrate",
    "min_cadence",
    "max_cadence",
    "prevailing_wind_deg",
    "id",
    "start_time",
    "end_time",
}

_INTERVAL_NUMBER_FIELDS = {
    "distance",
    "average_watts_kg",
    "max_watts_kg",
    "w5s_variability",
    "training_load",
    "decoupling",
    "avg_lr_balance",
    "average_dfa_a1",
    "average_epoc",
    "average_respiration",
    "average_tidal_volume",
    "average_tidal_volume_min",
    "average_speed",
    "min_speed",
    "max_speed",
    "gap",
    "average_cadence",
    "average_torque",
    "min_torque",
    "max_torque",
    "total_elevation_gain",
    "min_altitude",
    "max_altitude",
    "average_gradient",
    "average_smo2",
    "average_thb",
    "average_smo2_2",
    "average_thb_2",
    "average_lactate",
    "min_lactate",
    "max_lactate",
    "average_stance_time",
    "average_vertical_oscillation",
    "average_vertical_ratio",
    "average_step_length",
    "average_stance_time_percent",
    "average_stance_time_balance",
    "average_vertical_speed",
    "average_leg_spring_stiffness",
    "average_impact_loading_rate",
    "average_temp",
    "average_weather_temp",
    "average_feels_like",
    "average_wind_speed",
    "average_wind_gust",
    "average_yaw",
    "headwind_percent",
    "tailwind_percent",
    "strain_score",
    "ss_p_max",
    "ss_w_prime",
    "ss_cp",
    "average_stride",
}


def _is_strict_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    try:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
        )
    except OverflowError:
        return False


def _validate_bounds(
    start_index: Any,
    end_index: Any,
    *,
    resource: str,
) -> ReadResponse[list[Any]] | None:
    if not _is_strict_int(start_index) or not _is_strict_int(end_index):
        return failure(
            resource=resource,
            code="INVALID_RANGE",
            message="start_index and end_index must be strict integers",
            phase="validation",
        )
    if start_index < 0 or end_index <= start_index:
        return failure(
            resource=resource,
            code="INVALID_RANGE",
            message="start_index must be non-negative and end_index must be greater",
            phase="validation",
        )
    return None


def _provenance() -> dict[str, Any]:
    return {
        "origin": "upstream intervals.icu",
        "mcp_numeric_calculations": [],
    }


def _interval_units() -> dict[str, str]:
    units: dict[str, str] = {
        "index": "sample_index",
        "distance": "m",
        "moving_time": "s",
        "elapsed_time": "s",
        "start_time": "s",
        "end_time": "s",
    }
    units.update(
        dict.fromkeys(
            {
                "average_watts",
                "average_watts_alt",
                "average_watts_alt_acc",
                "min_watts",
                "max_watts",
                "weighted_average_watts",
            },
            "W",
        )
    )
    units.update(dict.fromkeys({"average_watts_kg", "max_watts_kg"}, "W/kg"))
    units.update(dict.fromkeys({"joules", "joules_above_ftp"}, "J"))
    units.update(
        dict.fromkeys(
            {"average_heartrate", "min_heartrate", "max_heartrate"}, "bpm"
        )
    )
    units.update(
        dict.fromkeys({"average_cadence", "min_cadence", "max_cadence"}, "1/min")
    )
    units.update(
        dict.fromkeys(
            {"average_speed", "min_speed", "max_speed", "gap", "average_vertical_speed"},
            "m/s",
        )
    )
    return units


def _time_stream_follow_up(
    activity_id: str, start_index: int, end_index: int
) -> dict[str, Any]:
    return {
        "tool": "get_activity_streams",
        "purpose": "map sample indices to elapsed time",
        "parameters": {
            "activity_id": activity_id,
            "mode": "range",
            "start_index": start_index,
            "end_index": end_index,
            "stream_types": "time",
        },
    }


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_interval_stats(
    activity_id: str,
    start_index: StrictInt,
    end_index: StrictInt,
    api_key: str | None = None,
) -> ReadResponse[Any]:
    """Read upstream interval statistics for a half-open sample-index range.

    Choose this when the client needs the Intervals.icu ``Interval`` object for
    ``[start_index, end_index)``.  Indices are samples, never seconds, and all
    upstream fields, including nulls, zeroes, and future fields, stay in
    ``data``.  The MCP adds provenance, units, and requested/returned bounds but
    performs no numeric calculations.  A returned range mismatch is explicit
    partial data; use the suggested ``get_activity_streams`` time range to map
    sample indices to elapsed time.  Source completeness is unknown.

    average_tidal_volume is VT (volume per breath, not VT1/VT2),
    average_tidal_volume_min is VE, and average_respiration is BR. Tymewear
    volumes use relative device units, not calibrated liters; no /100 or
    /1000 conversion is applied. Conditional field documentation is returned
    in provenance.respiratory_interpretation; see get_metric_definitions.
    """
    resource = "activity_interval_stats"
    if not isinstance(activity_id, str) or not activity_id.strip():
        return failure(
            resource=resource,
            code="INVALID_ACTIVITY_ID",
            message="activity_id is required",
            phase="validation",
        )
    validation = _validate_bounds(start_index, end_index, resource=resource)
    if validation is not None:
        return validation
    query = {
        "activity_id": activity_id,
        "start_index": start_index,
        "end_index": end_index,
    }
    result = await make_intervals_request(
        url=f"/activity/{activity_id}/interval-stats",
        api_key=api_key,
        params={"start_index": start_index, "end_index": end_index},
    )
    failed = upstream_failure(result, resource=resource, query=query)
    if failed is not None:
        return failed
    if not isinstance(result, dict):
        return invalid_upstream_response(
            resource=resource,
            message="interval-stats response must be an object",
            query=query,
        )
    recognized_interval_fields = (
        _INTERVAL_MARKER_FIELDS | _INTERVAL_INTEGER_FIELDS | _INTERVAL_NUMBER_FIELDS
    )
    if result and not recognized_interval_fields.intersection(result):
        return invalid_upstream_response(
            resource=resource,
            message="interval-stats object has no recognized Interval fields",
            query=query,
        )

    returned_start = result.get("start_index")
    returned_end = result.get("end_index")
    for field, value in (("start_index", returned_start), ("end_index", returned_end)):
        if field in result and value is not None and not _is_strict_int(value):
            return invalid_upstream_response(
                resource=resource,
                message=f"interval-stats {field} must be an integer when present",
                query=query,
            )
    for field in _INTERVAL_INTEGER_FIELDS.intersection(result):
        value = result[field]
        if value is not None and (
            (field in {"start_index", "end_index"} and not _is_strict_int(value))
            or (field not in {"start_index", "end_index"} and not _is_finite_number(value))
        ):
            return invalid_upstream_response(
                resource=resource,
                message=f"interval-stats {field} must be a finite number or null",
                query=query,
            )
    for field in _INTERVAL_NUMBER_FIELDS.intersection(result):
        value = result[field]
        if value is not None and not _is_finite_number(value):
            return invalid_upstream_response(
                resource=resource,
                message=f"interval-stats {field} must be a finite number or null",
                query=query,
            )

    returned_bounds = {
        "start_index": returned_start,
        "end_index": returned_end,
    }
    bounds_match: bool | None = None
    if _is_strict_int(returned_start) and _is_strict_int(returned_end):
        bounds_match = returned_start == start_index and returned_end == end_index
    warnings: list[str] = []
    reasons = ["upstream_completeness_unverified"]
    if not result:
        warnings.append("NO_INTERVAL_STATS")
        reasons = ["NO_INTERVAL_STATS"]
    elif (
        "start_index" not in result
        or "end_index" not in result
        or returned_start is None
        or returned_end is None
    ):
        warnings.append("RETURNED_BOUNDS_UNAVAILABLE")
        reasons.append("RETURNED_BOUNDS_UNAVAILABLE")
    elif bounds_match is False:
        warnings.append("RETURNED_BOUNDS_MISMATCH")
        reasons.append("RETURNED_BOUNDS_MISMATCH")

    provenance = _provenance()
    respiratory_interpretation = respiratory_guidance(result)
    if respiratory_interpretation:
        provenance["respiratory_interpretation"] = respiratory_interpretation
    response = success(
        dict(result),
        resource=resource,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "response_complete": not warnings,
            "truncated": False,
            "reasons": reasons,
        },
        warnings=warnings,
        units=_interval_units(),
        provenance=provenance,
        bounds={
            "requested": {"start_index": start_index, "end_index": end_index},
            "returned": returned_bounds,
            "matched": bounds_match,
        },
        follow_up=_time_stream_follow_up(activity_id, start_index, end_index),
    )
    if warnings:
        response.status = "partial"
    return response


def _best_effort_units(stream: str) -> dict[str, str]:
    average_units = {
        "watts": "W",
        "heartrate": "bpm",
        "velocity_smooth": "m/s",
    }
    return {
        "average": average_units.get(stream, "unknown"),
        "duration": "s",
        "distance": "m",
        "index": "sample_index",
    }


def _validate_effort_fields(effort: dict[str, Any], index: int) -> str | None:
    integer_fields = ("start_index", "end_index", "duration")
    numeric_fields = ("average", "distance")
    for field in integer_fields:
        value = effort.get(field)
        if field in effort and value is not None and not _is_strict_int(value):
            return f"efforts[{index}].{field} must be an integer or null"
    for field in numeric_fields:
        value = effort.get(field)
        if field in effort and value is not None and not _is_finite_number(value):
            return f"efforts[{index}].{field} must be a finite number or null"
    return None


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_best_efforts(
    activity_id: str,
    stream: str,
    duration: StrictInt | None = None,
    distance: StrictFloat | None = None,
    count: StrictInt = 8,
    min_value: StrictFloat | None = None,
    exclude_intervals: StrictBool = False,
    start_index: StrictInt = 0,
    end_index: StrictInt | None = None,
    api_key: str | None = None,
) -> ReadResponse[Any]:
    """Find upstream best efforts by one duration or distance selector.

    Choose this to ask Intervals.icu for ranked efforts on a named stream.
    ``duration`` is positive seconds or ``distance`` is positive finite metres;
    exactly one is required.  ``start_index`` and the exclusive ``end_index``
    are sample indices.  ``end_index=0`` is the upstream whole-stream
    sentinel, while ``end_index=None`` omits that optional parameter.
    ``count`` is locally limited to 1..100.  The MCP preserves
    each ``Effort`` and its metadata, reports average units (W, bpm, m/s, or
    unknown for custom streams), and performs no FTP, VO2, or numeric
    calculations.  ``min_value`` may expand an effort, so returned durations
    and bounds remain upstream facts; source completeness is unknown.
    """
    resource = "activity_best_efforts"
    if not isinstance(activity_id, str) or not activity_id.strip():
        return failure(
            resource=resource,
            code="INVALID_ACTIVITY_ID",
            message="activity_id is required",
            phase="validation",
        )
    if not isinstance(stream, str) or not stream.strip():
        return failure(
            resource=resource,
            code="INVALID_STREAM",
            message="stream must be a non-empty string",
            phase="validation",
        )
    if not _is_strict_int(count) or not 1 <= count <= 100:
        return failure(
            resource=resource,
            code="INVALID_COUNT",
            message="count must be a strict integer between 1 and 100",
            phase="validation",
        )
    if not _is_strict_int(start_index) or start_index < 0:
        return failure(
            resource=resource,
            code="INVALID_RANGE",
            message="start_index must be a non-negative strict integer",
            phase="validation",
        )
    if end_index is not None and (
        not _is_strict_int(end_index)
        or end_index < 0
        or (end_index != 0 and end_index <= start_index)
    ):
        return failure(
            resource=resource,
            code="INVALID_RANGE",
            message="end_index must be a strict integer greater than start_index",
            phase="validation",
        )
    if not isinstance(exclude_intervals, bool):
        return failure(
            resource=resource,
            code="INVALID_EXCLUDE_INTERVALS",
            message="exclude_intervals must be a boolean",
            phase="validation",
        )
    if min_value is not None and not _is_finite_number(min_value):
        return failure(
            resource=resource,
            code="INVALID_VALUE",
            message="min_value must be a finite number",
            phase="validation",
        )

    has_duration = duration is not None
    has_distance = distance is not None
    if has_duration == has_distance:
        return failure(
            resource=resource,
            code="INVALID_SELECTOR",
            message="provide exactly one positive duration or distance",
            phase="validation",
        )
    if has_duration and (
        not _is_strict_int(duration) or duration <= 0  # type: ignore[operator]
    ):
        return failure(
            resource=resource,
            code="INVALID_SELECTOR",
            message="duration must be a positive strict integer in seconds",
            phase="validation",
        )
    if has_distance and (
        not _is_finite_number(distance) or distance <= 0  # type: ignore[operator]
    ):
        return failure(
            resource=resource,
            code="INVALID_SELECTOR",
            message="distance must be positive finite metres",
            phase="validation",
        )

    query = {
        "activity_id": activity_id,
        "stream": stream,
        "duration": duration,
        "distance": distance,
        "count": count,
        "min_value": min_value,
        "exclude_intervals": exclude_intervals,
        "start_index": start_index,
        "end_index": end_index,
    }
    params: dict[str, Any] = {
        "stream": stream,
        "count": count,
        "excludeIntervals": exclude_intervals,
        "startIndex": start_index,
    }
    if duration is not None:
        params["duration"] = duration
    if distance is not None:
        params["distance"] = distance
    if min_value is not None:
        params["minValue"] = min_value
    if end_index is not None:
        params["endIndex"] = end_index

    result = await make_intervals_request(
        url=f"/activity/{activity_id}/best-efforts",
        api_key=api_key,
        params=params,
    )
    failed = upstream_failure(result, resource=resource, query=query)
    if failed is not None:
        return failed
    if not isinstance(result, dict) or "efforts" not in result:
        return invalid_upstream_response(
            resource=resource,
            message="best-efforts response must be an object with efforts",
            query=query,
        )
    efforts = result["efforts"]
    if not isinstance(efforts, list) or any(not isinstance(effort, dict) for effort in efforts):
        return invalid_upstream_response(
            resource=resource,
            message="best-efforts efforts must be an array of objects",
            query=query,
        )

    for index, effort in enumerate(efforts):
        field_error = _validate_effort_fields(effort, index)
        if field_error:
            return invalid_upstream_response(
                resource=resource,
                message=field_error,
                query=query,
            )
        for field in ("start_index", "end_index"):
            value = effort.get(field)
            if value is not None and _is_strict_int(value) and value < 0:
                return invalid_upstream_response(
                    resource=resource,
                    message=f"efforts[{index}].{field} cannot be negative",
                    query=query,
                )
        if (
            _is_strict_int(effort.get("start_index"))
            and _is_strict_int(effort.get("end_index"))
            and effort["end_index"] <= effort["start_index"]
        ):
            return invalid_upstream_response(
                resource=resource,
                message=f"efforts[{index}] has reversed or empty bounds",
                query=query,
            )
        for field in ("duration", "distance"):
            value = effort.get(field)
            if value is not None and _is_finite_number(value) and value < 0:
                return invalid_upstream_response(
                    resource=resource,
                    message=f"efforts[{index}].{field} cannot be negative",
                    query=query,
                )

    missing: list[dict[str, Any]] = []
    returned_bounds: list[dict[str, Any]] = []
    bounds_missing = False
    bounds_outside = False
    requested_end_for_comparison = None if end_index == 0 else end_index
    for index, effort in enumerate(efforts):
        if "average" not in effort:
            missing.append(
                {"effort_index": index, "field": "average", "reason": "UPSTREAM_MISSING"}
            )
        elif effort["average"] is None:
            missing.append(
                {"effort_index": index, "field": "average", "reason": "UPSTREAM_NULL"}
            )
        if (
            "start_index" not in effort
            or "end_index" not in effort
            or effort.get("start_index") is None
            or effort.get("end_index") is None
        ):
            bounds_missing = True
        else:
            outside_lower_bound = effort["start_index"] < start_index
            outside_upper_bound = (
                requested_end_for_comparison is not None
                and effort["end_index"] > requested_end_for_comparison
            )
            if outside_lower_bound or outside_upper_bound:
                bounds_missing = True
                bounds_outside = True
        returned_bounds.append(
            {
                "start_index": effort.get("start_index"),
                "end_index": effort.get("end_index"),
            }
        )

    warnings: list[str] = []
    reasons = ["upstream_completeness_unverified"]
    if missing:
        warnings.append("MISSING_AVERAGE")
        reasons.append("MISSING_AVERAGE")
    if bounds_missing and efforts:
        warning = (
            "EFFORT_BOUNDS_OUTSIDE_REQUEST"
            if bounds_outside
            else "EFFORT_BOUNDS_UNAVAILABLE"
        )
        warnings.append(warning)
        reasons.append(warning)
    response = success(
        dict(result),
        resource=resource,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "response_complete": not warnings,
            "truncated": False,
            "reasons": reasons,
        },
        warnings=warnings,
        units=_best_effort_units(stream),
        provenance=_provenance(),
        bounds={
            "requested": {"start_index": start_index, "end_index": end_index},
            "returned": returned_bounds,
        },
        missing=missing,
    )
    if warnings:
        response.status = "partial"
    return response


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_power_hr(
    activity_id: str, detail: str = "compact", api_key: str | None = None,
) -> ReadResponse[Any]:
    """Read native power-versus-HR analysis, including upstream HR lag and windows.

    Values, coefficients and selection indices are source-provided. No new
    physiological calculations or causal conclusions are made. Compact detail
    keeps the first 120 series rows and eight curves, then omits whole fields
    if needed to bound data to 32 KiB. Exact omissions and a full continuation
    are returned. Full detail preserves the complete JSON object.
    """
    resource = "activity_power_hr"
    query = {"activity_id": activity_id, "detail": detail}
    if not isinstance(activity_id, str) or not activity_id.strip():
        return failure(resource=resource, code="INVALID_ACTIVITY_ID",
                       message="activity_id is required", phase="validation")
    if detail not in {"compact", "full"}:
        return failure(resource=resource, code="INVALID_DETAIL",
                       message="detail must be compact or full", phase="validation")
    raw = await make_intervals_request(url=f"/activity/{activity_id}/power-vs-hr.json", api_key=api_key)
    failed = upstream_failure(raw, resource=resource, query=query)
    if failed is not None:
        return failed
    if not isinstance(raw, dict):
        return invalid_upstream_response(resource=resource, message="power-HR response must be an object", query=query)
    numeric = {"bucketSize", "warmup", "cooldown", "elapsedTime", "hrLag", "powerHr",
               "powerHrFirst", "powerHrSecond", "decoupling", "powerHrZ2", "medianCadenceZ2",
               "avgCadenceZ2", "hrZ2BucketCount", "start", "mid", "end"}
    if raw and not (numeric | {"series", "curves", "ratioCoefficients"}).intersection(raw):
        return invalid_upstream_response(resource=resource, message="power-HR object has no recognized fields", query=query)
    for key in numeric:
        if key in raw and raw[key] is not None and not _is_finite_number(raw[key]):
            return invalid_upstream_response(resource=resource, message=f"{key} must be finite numeric or null", query=query)
    ratios = raw.get("ratioCoefficients")
    if ratios is not None and (
        not isinstance(ratios, list)
        or any(value is not None and not _is_finite_number(value) for value in ratios)
    ):
        return invalid_upstream_response(resource=resource, message="ratioCoefficients must be numeric or null", query=query)
    for key, numeric_fields in (
        ("series", {"start", "secs", "movingSecs", "watts", "hr", "cadence"}),
        ("curves", {"r2"}),
    ):
        rows = raw.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            return invalid_upstream_response(resource=resource, message=f"{key} must be an object array or null", query=query)
        for row in rows:
            if any(field in row and row[field] is not None and not _is_finite_number(row[field])
                   for field in numeric_fields):
                return invalid_upstream_response(resource=resource, message=f"{key} contains invalid numeric observations", query=query)
            coefficients = row.get("coefficients")
            if coefficients is not None and (
                not isinstance(coefficients, list)
                or any(value is not None and not _is_finite_number(value) for value in coefficients)
            ):
                return invalid_upstream_response(resource=resource, message="curve coefficients must be numeric or null", query=query)
    data = deepcopy(raw)
    omitted_records: dict[str, int] = {}
    omitted_fields: list[str] = []
    if detail == "compact":
        for key, limit in (("series", 120), ("curves", 8)):
            if isinstance(data.get(key), list) and len(data[key]) > limit:
                omitted_records[key] = len(data[key]) - limit
                data[key] = data[key][:limit]
        for key in sorted(data, key=lambda field: len(json.dumps(data[field], ensure_ascii=False)), reverse=True):
            if len(json.dumps(data, ensure_ascii=False).encode("utf-8")) <= 32768:
                break
            omitted_fields.append(key)
            del data[key]
    truncated = bool(omitted_records or omitted_fields)
    response = success(
        data, resource=resource, query=query,
        coverage={"source_complete_within_query": None, "response_complete": not truncated,
                  "truncated": truncated, "reasons": ["upstream_completeness_unverified"]
                  + (["compact_projection"] if truncated else [])},
        provenance={"origin": "upstream intervals.icu", "mcp_numeric_calculations": []},
        units={"bucketSize": "s", "warmup": "s", "cooldown": "s", "elapsedTime": "s",
               "hrLag": "s", "series.start": "s", "series.secs": "s",
               "series.movingSecs": "s", "series.watts": "W", "series.hr": "bpm",
               "series.cadence": "1/min", "start": "series_index", "mid": "series_index",
               "end": "series_index", "decoupling": "%"},
        availability="available" if raw else "empty",
        projection={"detail": detail, "omitted_records": omitted_records,
                    "omitted_fields": omitted_fields, "series_order": "upstream order; no resampling",
                    "full_read": {"tool": "get_activity_power_hr",
                                  "parameters": {"activity_id": activity_id, "detail": "full"}}},
    )
    if truncated:
        response.status = "partial"
    return response


__all__ = ["get_activity_interval_stats", "get_activity_best_efforts", "get_activity_power_hr"]
