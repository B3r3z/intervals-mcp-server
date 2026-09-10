"""
Power curve MCP tools for Intervals.icu.

This module contains tools for retrieving athlete power curve data.
"""

from copy import deepcopy
from datetime import datetime
import json
import math
from typing import Any, Literal

from pydantic import StrictInt

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.utils.validation import resolve_athlete_id

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.catalogue import coach_tool

config = get_config()

# 5s, 15s, 30s, 1min, 2min, 5min, 10min, 20min, 60min
DEFAULT_DURATIONS: tuple[int, ...] = (5, 15, 30, 60, 120, 300, 600, 1200, 3600)


def _build_curves_param(
    this_season: bool,
    last_season: bool,
    start_date: str | None,
    end_date: str | None,
) -> list[str]:
    """Build the curves query parameter list based on user selections.

    Args:
        this_season: Whether to include this season's curve.
        last_season: Whether to include last season's curve.
        start_date: Optional start date for a custom date range curve.
        end_date: Optional end date for a custom date range curve.

    Returns:
        List of curve identifiers for the API request.
    """
    curves: list[str] = []
    if this_season:
        curves.append("s0")
    if last_season:
        curves.append("s1")
    if start_date and end_date:
        curves.append(f"r.{start_date}.{end_date}")
    return curves


def _validate_dates(start_date: str | None, end_date: str | None) -> str | None:
    """Validate that start_date and end_date are either both provided or both absent.

    Returns:
        An error message if validation fails, otherwise None.
    """
    if (start_date is None) != (end_date is None):
        return "Error: Both start_date and end_date must be provided together for a custom date range."
    if start_date and end_date:
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            if s >= e:
                return "Error: start_date must be before end_date."
        except ValueError:
            return "Error: Dates must be in YYYY-MM-DD format."
    return None


_CURVE_SERIES_FIELDS = {
    "start_index",
    "end_index",
    "secs",
    "values",
    "activity_id",
    "watts_per_kg",
    "wkg_activity_id",
}

_ACTIVITY_CURVE_LARGE_FIELDS = {
    "submax_values",
    "submax_activity_id",
    "submax_watts_per_kg",
    "submax_wkg_activity_id",
    "powerModels",
    "ranks",
    "mapPlot",
    "watts",
}


def _series_or_empty(curve: dict[str, Any], field: str) -> list[Any] | None:
    """Validate an optional curve series while retaining an explicit null."""
    value = curve.get(field)
    if value is None:
        return None
    if not isinstance(value, list):
        raise ValueError(f"curve field {field} must be an array or null")
    return value


def _validate_numeric_series(series: list[Any] | None, field: str) -> None:
    """Reject non-numeric or non-finite values in a numeric curve series."""
    if series is None:
        return
    for value in series:
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"curve field {field} must contain numbers or null")
        if not math.isfinite(float(value)):
            raise ValueError(f"curve field {field} must contain finite numbers or null")


def _project_curve(
    curve: dict[str, Any],
    durations: list[int],
    detail: str,
    *,
    origin: Literal["athlete", "activity"],
    full_read: dict[str, Any],
    include_normalised: bool = False,
) -> tuple[dict[str, Any], list[str]]:
    """Project original evidence; source shape and compact rules stay internal.

    include_normalised selects upstream W/kg, not Normalized Power.
    The original curve is never reshaped, including when activity power is
    supplied as watts. Full raw evidence is therefore unchanged.
    """
    if origin == "activity":
        shape_error = _validate_activity_curve_shape(curve)
        if shape_error:
            raise ValueError(shape_error)
    alignment = origin == "activity" or "start_index" in curve or "end_index" in curve
    compact_metadata = origin == "activity" or bool(_ACTIVITY_CURVE_LARGE_FIELDS.intersection(curve))
    power_field = "watts" if origin == "activity" and "values" not in curve else "values"
    secs = _series_or_empty(curve, "secs") or []
    values = _series_or_empty(curve, power_field) or []
    activity_ids = _series_or_empty(curve, "activity_id")
    watts_per_kg = _series_or_empty(curve, "watts_per_kg")
    wkg_activity_ids = _series_or_empty(curve, "wkg_activity_id")
    _validate_numeric_series(values, "values")
    _validate_numeric_series(watts_per_kg, "watts_per_kg")

    axis: list[int] = []
    for value in secs:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("curve secs must contain positive integers")
        axis.append(value)
    if len(set(axis)) != len(axis):
        raise ValueError("curve secs must not contain duplicate durations")

    warnings: list[str] = []
    if len(secs) != len(values):
        warnings.append("SERIES_LENGTH_MISMATCH")
        if len(values) < len(secs):
            missing_durations_from_shape = secs[len(values) :]
        else:
            missing_durations_from_shape = []
    else:
        missing_durations_from_shape = []
    start_indices = _series_or_empty(curve, "start_index")
    end_indices = _series_or_empty(curve, "end_index")
    for series in (
        activity_ids,
        watts_per_kg,
        wkg_activity_ids,
        start_indices,
        end_indices,
    ):
        if series is not None and len(series) != len(secs):
            warnings.append("SERIES_LENGTH_MISMATCH")

    sec_to_idx = {duration: index for index, duration in enumerate(axis)}
    data_points: list[dict[str, Any]] = []
    missing_durations: list[int] = list(missing_durations_from_shape)
    missing_reasons: list[dict[str, Any]] = [
        {"duration": duration, "reason": "SERIES_LENGTH_MISMATCH"}
        for duration in missing_durations_from_shape
    ]
    for duration in durations:
        index = sec_to_idx.get(duration)
        if index is None:
            missing_durations.append(duration)
            missing_reasons.append(
                {"duration": duration, "reason": "DURATION_NOT_RETURNED"}
            )
            continue
        if index >= len(values):
            missing_durations.append(duration)
            missing_reasons.append(
                {"duration": duration, "reason": "SERIES_LENGTH_MISMATCH"}
            )
            continue
        value = values[index]
        point: dict[str, Any] = {
            "secs": duration,
            "watts": value,
            "activity_id": (
                activity_ids[index]
                if activity_ids is not None and index < len(activity_ids)
                else None
            ),
        }
        if alignment:
            point["start_index"] = (
                start_indices[index]
                if start_indices is not None and index < len(start_indices)
                else None
            )
            point["end_index"] = (
                end_indices[index]
                if end_indices is not None and index < len(end_indices)
                else None
            )
            if point["start_index"] is None or point["end_index"] is None:
                warnings.append("BOUNDS_UNAVAILABLE")
            elif point["end_index"] <= point["start_index"]:
                warnings.append("INCONSISTENT_BOUNDS")
        if value is None:
            missing_durations.append(duration)
            missing_reasons.append(
                {"duration": duration, "reason": "UPSTREAM_NULL"}
            )
        if include_normalised or (origin == "activity" and watts_per_kg is not None):
            point["watts_per_kg"] = (
                watts_per_kg[index]
                if watts_per_kg is not None and index < len(watts_per_kg)
                else None
            )
        if include_normalised or origin == "activity":
            point["wkg_activity_id"] = (
                wkg_activity_ids[index]
                if wkg_activity_ids is not None and index < len(wkg_activity_ids)
                else None
            )
        data_points.append(point)

    metadata = {
        key: deepcopy(value)
        for key, value in curve.items()
        if key not in _CURVE_SERIES_FIELDS
        and (not compact_metadata or key not in _ACTIVITY_CURVE_LARGE_FIELDS)
    }
    omitted_fields: set[str] = set()
    if compact_metadata and detail == "compact":
        omitted_fields.update(
            key
            for key in curve
            if key in _CURVE_SERIES_FIELDS or key in _ACTIVITY_CURVE_LARGE_FIELDS
        )
        for key, value in list(metadata.items()):
            if isinstance(value, (list, dict)):
                omitted_fields.add(key)
                del metadata[key]
    metadata.setdefault("id", curve.get("id"))
    metadata.setdefault("label", curve.get("label", curve.get("id")))
    metadata.setdefault("start", curve.get("start_date_local"))
    metadata.setdefault("end", curve.get("end_date_local"))
    metadata["data_points"] = data_points
    metadata["missing_durations"] = list(dict.fromkeys(missing_durations))
    if origin == "activity":
        metadata["missing_reasons"] = list(
            {json.dumps(reason, sort_keys=True): reason for reason in missing_reasons}.values()
        )
    if compact_metadata and detail == "compact":
        metadata["omitted_fields"] = sorted(omitted_fields)
        metadata["full_read"] = deepcopy(full_read)
    if detail == "full":
        metadata["raw"] = deepcopy(curve)
    return metadata, list(dict.fromkeys(warnings))


def _curve_source(result: Any) -> tuple[list[dict[str, Any]], dict[str, Any]] | str:
    """Validate the documented list response and return curves plus metadata."""
    if isinstance(result, list):
        source = result
        metadata: dict[str, Any] = {}
    elif isinstance(result, dict) and isinstance(result.get("list"), list):
        source = result["list"]
        metadata = {
            key: deepcopy(value) for key, value in result.items() if key != "list"
        }
    else:
        return "power-curves response must be a list or an object with a list array"
    if any(not isinstance(curve, dict) for curve in source):
        return "power-curves list members must be objects"
    return [dict(curve) for curve in source], metadata


@coach_tool(access="read", upstream="read", local="none")
async def get_athlete_power_curves(
    activity_type: str = "Ride",
    durations: list[StrictInt] | None = None,
    indoor_outdoor: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    this_season: bool = True,
    last_season: bool = True,
    include_normalised: bool = True,
    athlete_id: str | None = None,
    api_key: str | None = None,
    detail: str = "compact",
) -> ReadResponse[Any]:
    """Read selected athlete power-curve durations in seconds.

    Choose this tool for season or custom-range best-power comparisons.  Each
    requested duration is a positive integer number of seconds.  Compact
    results return requested points and curve metadata; ``detail='full'`` also
    returns the untouched upstream curve as ``raw`` for deeper analysis.
    ``include_normalised`` is the legacy option for the upstream W/kg series,
    not Normalized Power.  Empty upstream lists are valid empty data, while
    malformed shapes fail explicitly.  Per-curve missing durations and null
    values are preserved, and source completeness remains unknown.
    """
    requested_durations = list(DEFAULT_DURATIONS) if durations is None else durations
    if (
        not isinstance(requested_durations, list)
        or not requested_durations
        or any(
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
            for duration in requested_durations
        )
    ):
        return failure(
            resource="power_curves",
            code="INVALID_DURATIONS",
            message="durations must be a non-empty list of positive integers",
            phase="validation",
        )
    if detail not in {"compact", "full"}:
        return failure(
            resource="power_curves",
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
        )
    aid, err = resolve_athlete_id(athlete_id, config.athlete_id)
    if err:
        return failure(resource="power_curves", code="INVALID_ATHLETE", message=err, phase="validation")
    date_error = _validate_dates(start_date, end_date)
    if date_error:
        return failure(resource="power_curves", code="INVALID_DATE", message=date_error, phase="validation")
    if indoor_outdoor and indoor_outdoor not in ("indoor", "outdoor"):
        return failure(resource="power_curves", code="INVALID_FILTER", message="invalid indoor_outdoor", phase="validation")
    curves = _build_curves_param(this_season, last_season, start_date, end_date)
    if not curves:
        return failure(resource="power_curves", code="INVALID_CURVES", message="at least one curve required", phase="validation")
    params: dict[str, Any] = {
        "curves": curves,
        "type": activity_type,
        "includeRanks": False,
    }
    if indoor_outdoor:
        params["filters"] = json.dumps(
            [{"field_id": "indoor", "value": indoor_outdoor, "id": 1}]
        )
    result = await make_intervals_request(
        url=f"/athlete/{aid}/power-curves", api_key=api_key, params=params
    )
    failed = upstream_failure(result, resource="power_curves", athlete_id=aid)
    if failed:
        return failed
    source_result = _curve_source(result)
    if isinstance(source_result, str):
        return invalid_upstream_response(
            resource="power_curves", message=source_result, athlete_id=aid
        )
    source, response_metadata = source_result
    data: list[dict[str, Any]] = []
    warnings: list[str] = []
    athlete_full_read = {
        "tool": "get_athlete_power_curves",
        "parameters": {
            "activity_type": activity_type,
            "durations": requested_durations,
            "indoor_outdoor": indoor_outdoor,
            "start_date": start_date,
            "end_date": end_date,
            "this_season": this_season,
            "last_season": last_season,
            "include_normalised": include_normalised,
            "athlete_id": aid,
            "detail": "full",
        },
    }
    for curve in source:
        try:
            extracted, curve_warnings = _project_curve(
                curve, requested_durations, detail, origin="athlete",
                full_read=athlete_full_read, include_normalised=include_normalised,
            )
        except ValueError as exc:
            return invalid_upstream_response(
                resource="power_curves", message=str(exc), athlete_id=aid
            )
        data.append(extracted)
        warnings.extend(curve_warnings)
    missing = sorted(
        {duration for curve in data for duration in curve["missing_durations"]}
    )
    warnings = list(dict.fromkeys(warnings))
    if missing:
        warnings.append("MISSING_DURATION")
    output: dict[str, Any] = {"curves": data, "missing_durations": missing}
    if response_metadata:
        output["response_metadata"] = response_metadata
    reasons = ["upstream_completeness_unverified"]
    if missing:
        reasons.append("missing_durations")
    if "SERIES_LENGTH_MISMATCH" in warnings:
        reasons.append("series_length_mismatch")
    response = success(
        output,
        resource="power_curves",
        athlete_id=aid,
        query={
            "activity_type": activity_type,
            "durations": requested_durations,
            "indoor_outdoor": indoor_outdoor,
            "include_normalised": include_normalised,
            "detail": detail,
            "this_season": this_season,
            "last_season": last_season,
            "start_date": start_date,
            "end_date": end_date,
            "curves": curves,
        },
        coverage={
            "source_complete_within_query": None,
            "reasons": reasons,
        },
        warnings=warnings,
    )
    if (missing or "SERIES_LENGTH_MISMATCH" in warnings) and data:
        response.status = "partial"
    return response


def _validate_activity_curve_shape(curve: dict[str, Any]) -> str | None:
    """Validate activity PowerCurve arrays without reshaping their raw values."""
    array_fields = _CURVE_SERIES_FIELDS | {
        "watts",
        "submax_values",
        "submax_activity_id",
        "submax_watts_per_kg",
        "submax_wkg_activity_id",
        "powerModels",
    }
    for field in array_fields:
        if field in curve and curve[field] is not None and not isinstance(curve[field], list):
            return f"power-curve field {field} must be an array or null"
    for field in ("ranks", "mapPlot"):
        if field in curve and curve[field] is not None and not isinstance(curve[field], dict):
            return f"power-curve field {field} must be an object or null"

    for field in ("values", "watts", "watts_per_kg"):
        value = curve.get(field)
        if value is not None:
            if not isinstance(value, list):
                return f"power-curve field {field} must be an array or null"
            try:
                _validate_numeric_series(value, field)
            except ValueError as exc:
                return str(exc)

    for field in ("start_index", "end_index"):
        value = curve.get(field)
        if value is None:
            continue
        for item in value:
            if item is not None and (
                isinstance(item, bool) or not isinstance(item, int) or item < 0
            ):
                return f"power-curve field {field} must contain non-negative integers or null"
    for field in ("activity_id", "wkg_activity_id"):
        value = curve.get(field)
        if value is None:
            continue
        for item in value:
            if item is not None and not isinstance(item, str):
                return f"power-curve field {field} must contain strings or null"

    stream_type = curve.get("stream_type")
    if stream_type is not None and (
        not isinstance(stream_type, str) or stream_type.lower() != "watts"
    ):
        return "power-curve stream_type must be watts for the requested stream"
    after_kj = curve.get("after_kj")
    if after_kj is not None and (
        isinstance(after_kj, bool) or not isinstance(after_kj, int)
    ):
        return "power-curve after_kj must be an integer or null"
    return None


def _activity_curve_source(result: Any) -> list[dict[str, Any]] | str:
    """Validate the array response documented for activity power curves."""
    if not isinstance(result, list):
        return "activity power-curves response must be an array"
    if any(not isinstance(curve, dict) for curve in result):
        return "activity power-curves members must be objects"
    return [dict(curve) for curve in result]


def _activity_curve_selection(
    curves: list[dict[str, Any]], requested: list[str]
) -> dict[str, Any]:
    """Report fatigue selection coverage without deriving it from curve IDs."""
    returned = [curve.get("fatigue") for curve in curves if "fatigue" in curve]
    labels_are_explicit = len(returned) == len(curves) and all(
        isinstance(label, str) for label in returned
    )
    verified = (
        None
        if not curves
        else labels_are_explicit and set(returned) == set(requested)
    )
    return {
        "requested_fatigue": list(requested),
        "returned_fatigue": returned,
        "verified": verified,
        "basis": "explicit curve fatigue fields only; curve IDs and after_kj are not selectors",
        "verification_state": "empty" if not curves else "not_echoed" if not returned
        else "confirmed" if verified else "unverified",
    }


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_power_curves(
    activity_id: str,
    durations: list[StrictInt] | None = None,
    fatigue: list[Literal["normal", "kj0", "kj1"]] | None = None,
    detail: str = "compact",
    api_key: str | None = None,
) -> ReadResponse[Any]:
    """Read watts power curves for one activity and optional durations.

    Choose this for best-power points from one activity.  ``durations`` are
    positive seconds selected exactly from the upstream ``secs`` axis; omitted
    durations use the standard duration set, while full detail preserves the
    complete upstream axis.  ``fatigue`` defaults to ``normal``
    and each distinct selector is requested independently; the response keeps
    ``after_kj`` and does not infer selector identity from curve IDs.  Compact
    points retain aligned sample indices and W/kg activity IDs, while large
    raw arrays are listed in ``omitted_fields``.  Use the supplied ``full_read``
    continuation or ``detail='full'`` when those arrays or unknown fields are
    needed.  Values are upstream watts; no MCP calculations are performed.
    Successful variants survive failures of other variants. Selection echo and
    point completeness are separate; request context does not prove upstream
    selector identity. HTTP 422 guidance includes checking sport settings.
    """
    resource = "activity_power_curves"
    if not isinstance(activity_id, str) or not activity_id.strip():
        return failure(
            resource=resource,
            code="INVALID_ACTIVITY_ID",
            message="activity_id is required",
            phase="validation",
        )
    if durations is not None and (
        not isinstance(durations, list)
        or not durations
        or any(
            isinstance(duration, bool)
            or not isinstance(duration, int)
            or duration <= 0
            for duration in durations
        )
    ):
        return failure(
            resource=resource,
            code="INVALID_DURATIONS",
            message="durations must be a non-empty list of positive integers when provided",
            phase="validation",
        )
    requested_durations = list(DEFAULT_DURATIONS) if durations is None else list(durations)
    requested_fatigue = ["normal"] if fatigue is None else list(fatigue)
    if not requested_fatigue or any(
        selector not in {"normal", "kj0", "kj1"} for selector in requested_fatigue
    ):
        return failure(
            resource=resource,
            code="INVALID_FATIGUE",
            message="fatigue must be a non-empty list of normal, kj0, or kj1",
            phase="validation",
        )
    if detail not in {"compact", "full"}:
        return failure(
            resource=resource,
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
        )

    query = {
        "activity_id": activity_id,
        "durations": requested_durations,
        "fatigue": requested_fatigue,
        "detail": detail,
    }
    full_read = {
        "tool": "get_activity_power_curves",
        "parameters": {
            "activity_id": activity_id,
            "durations": requested_durations,
            "fatigue": requested_fatigue,
            "detail": "full",
        },
    }
    data: list[dict[str, Any]] = []
    warnings: list[str] = []
    source_result: list[dict[str, Any]] = []
    selector_results: list[dict[str, Any]] = []
    failures: list[ReadResponse[Any]] = []
    for selector in dict.fromkeys(requested_fatigue):
        selector_query = {**query, "fatigue": [selector]}
        result = await make_intervals_request(
            url=f"/activity/{activity_id}/power-curves", api_key=api_key,
            params={"types": "watts", "fatigue": selector},
        )
        failed = upstream_failure(result, resource=resource, query=selector_query)
        curves = _activity_curve_source(result) if failed is None else []
        if isinstance(curves, str):
            failed = invalid_upstream_response(resource=resource, message=curves, query=selector_query)
        projected: list[dict[str, Any]] = []
        variant_warnings: list[str] = []
        if failed is None:
            assert isinstance(curves, list)
            for curve in curves:
                try:
                    extracted, curve_warnings = _project_curve(
                        curve, requested_durations, detail, origin="activity", full_read=full_read,
                    )
                except ValueError as exc:
                    failed = invalid_upstream_response(resource=resource, message=str(exc), query=selector_query)
                    break
                projected.append(extracted)
                variant_warnings.extend(curve_warnings)
        if failed is not None:
            if failed.error and failed.error.http_status == 422:
                failed.error.recommended_action = (
                    "Inspect get_sport_settings after_kj0/after_kj1 and request parameters; "
                    "HTTP 422 alone does not prove missing configuration."
                )
            failures.append(failed)
            selector_results.append({
                "requested_fatigue": selector, "status": "error", "curve_indices": [],
                "error": failed.error.model_dump(mode="json") if failed.error else None,
            })
            continue
        assert isinstance(curves, list)
        variant_selection = _activity_curve_selection(curves, [selector])
        if any("fatigue" in curve and curve["fatigue"] != selector for curve in curves):
            variant_warnings.append("FATIGUE_SELECTION_MISMATCH")
        if selector != "normal" and curves and not all(
            isinstance(curve.get("after_kj"), int) for curve in curves
        ):
            variant_warnings.append("FATIGUE_THRESHOLD_UNAVAILABLE")
        selector_results.append({
            "requested_fatigue": selector, "status": "partial" if variant_warnings else "ok",
            "availability": "available" if curves else "empty",
            "curve_indices": list(range(len(data), len(data) + len(projected))),
            "selection": variant_selection, "warnings": list(dict.fromkeys(variant_warnings)),
            "error": None,
        })
        data.extend(projected)
        source_result.extend(curves)
        warnings.extend(variant_warnings)
    if failures:
        warnings.append("FATIGUE_VARIANT_UNAVAILABLE")
        if len(failures) == len(selector_results):
            failed_response = failures[0]
            failed_response.query = type(failed_response.query).model_validate(query)
            failed_response.data = {"curves": [], "selector_results": selector_results}
            return failed_response
    selection = _activity_curve_selection(source_result, requested_fatigue)
    selection["request_results"] = selector_results
    if failures or "FATIGUE_SELECTION_MISMATCH" in warnings:
        selection["verified"] = False
    missing = sorted(
        {duration for curve in data for duration in curve["missing_durations"]}
    )
    if missing:
        warnings.append("MISSING_DURATION")
    warnings = list(dict.fromkeys(warnings))
    reasons = ["upstream_completeness_unverified"]
    if missing:
        reasons.append("missing_durations")
    if "SERIES_LENGTH_MISMATCH" in warnings:
        reasons.append("series_length_mismatch")
    if failures:
        reasons.append("fatigue_variant_unavailable")
    if "FATIGUE_SELECTION_MISMATCH" in warnings:
        reasons.append("fatigue_selection_mismatch")
    if "FATIGUE_THRESHOLD_UNAVAILABLE" in warnings:
        reasons.append("fatigue_threshold_unavailable")
    if "BOUNDS_UNAVAILABLE" in warnings:
        reasons.append("bounds_unavailable")
    if "INCONSISTENT_BOUNDS" in warnings:
        reasons.append("inconsistent_bounds")
    output: dict[str, Any] = {
        "curves": data,
        "missing_durations": missing,
        "selection": selection,
        "selector_results": selector_results,
    }
    if detail == "compact":
        output["full_read"] = full_read
    response = success(
        output,
        resource=resource,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "response_complete": not warnings,
            "truncated": False,
            "reasons": reasons,
        },
        warnings=warnings,
        units={
            "duration": "s",
            "watts": "W",
            "watts_per_kg": "W/kg",
            "after_kj": "kJ",
            "weight": "kg",
            "moving_time": "s",
            "start_index": "sample_index",
            "end_index": "sample_index",
        },
        provenance={
            "origin": "upstream intervals.icu",
            "requested_stream": "watts",
            "mcp_numeric_calculations": [],
        },
        selection=selection,
    )
    if warnings:
        response.status = "partial"
    return response


__all__ = ["get_athlete_power_curves", "get_activity_power_curves"]
