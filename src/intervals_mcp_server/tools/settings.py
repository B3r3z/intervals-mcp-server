"""Read current Intervals.icu sport settings without changing them."""

from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.utils.validation import resolve_athlete_id


_COMPACT_FIELDS = {
    "id",
    "athlete_id",
    "types",
    "created",
    "updated",
    "ftp",
    "indoor_ftp",
    "w_prime",
    "p_max",
    "power_zones",
    "power_zone_names",
    "sweet_spot_min",
    "sweet_spot_max",
    "power_spike_threshold",
    "ftp_est_min_secs",
    "after_kj0",
    "after_kj1",
    "power_field",
    "p30s_exponent",
    "lthr",
    "max_hr",
    "hr_zones",
    "hr_zone_names",
    "hr_load_type",
    "hrrc_min_percent",
    "threshold_pace",
    "pace_units",
    "pace_zones",
    "pace_zone_names",
    "pace_load_type",
    "mmp_model",
    "load_order",
    "tiz_order",
    "workout_order",
    "interval_display",
    "show_pauses",
    "ignore_velocity",
    "use_gap_zone_times",
    "gap_model",
    "elevation_correction",
    "iseFTPSupported",
    "use_distance_for_intervals",
}

_NUMERIC_FIELDS = {
    "ftp",
    "indoor_ftp",
    "w_prime",
    "p_max",
    "sweet_spot_min",
    "sweet_spot_max",
    "power_spike_threshold",
    "ftp_est_min_secs",
    "after_kj0",
    "after_kj1",
    "p30s_exponent",
    "lthr",
    "max_hr",
    "hrrc_min_percent",
    "threshold_pace",
    "show_pauses",
}

_NUMERIC_ARRAY_FIELDS = {
    "power_zones",
    "hr_zones",
    "pace_zones",
    "best_effort_distances",
}

_STRING_ARRAY_FIELDS = {"types", "power_zone_names", "hr_zone_names", "pace_zone_names"}

_SETTINGS_MARKER_FIELDS = {
    "id",
    "athlete_id",
    "types",
    "ftp",
    "indoor_ftp",
    "w_prime",
    "p_max",
    "power_zones",
    "lthr",
    "max_hr",
    "hr_zones",
    "threshold_pace",
    "pace_zones",
    "load_order",
    "tiz_order",
}


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_settings_shape(settings: dict[str, Any]) -> str | None:
    """Validate known scalar and array fields while preserving unknown fields."""
    for field in _NUMERIC_FIELDS:
        value = settings.get(field)
        if value is not None and not _is_finite_number(value):
            return f"sport-settings {field} must be a finite number or null"
    for field in _NUMERIC_ARRAY_FIELDS:
        value = settings.get(field)
        if value is None:
            continue
        if not isinstance(value, list) or any(
            item is not None and not _is_finite_number(item) for item in value
        ):
            return f"sport-settings {field} must be an array of finite numbers or null"
    for field in _STRING_ARRAY_FIELDS:
        value = settings.get(field)
        if value is not None and (
            not isinstance(value, list)
            or any(item is not None and not isinstance(item, str) for item in value)
        ):
            return f"sport-settings {field} must be an array of strings or null"
    return None


def _compact_settings(
    settings: dict[str, Any],
    *,
    athlete_id: str,
    selector: str,
) -> dict[str, Any]:
    compact = {
        key: deepcopy(value) for key, value in settings.items() if key in _COMPACT_FIELDS
    }
    omitted = sorted(key for key in settings if key not in _COMPACT_FIELDS)
    compact["omitted_fields"] = omitted
    compact["full_read"] = {
        "tool": "get_sport_settings",
        "parameters": {
            "sport": selector,
            "athlete_id": athlete_id,
            "detail": "full",
        },
    }
    return compact


def _settings_units() -> dict[str, str]:
    return {
        "ftp": "W",
        "indoor_ftp": "W",
        "p_max": "W",
        "w_prime": "J",
        "after_kj0": "kJ",
        "after_kj1": "kJ",
        "lthr": "bpm",
        "max_hr": "bpm",
        "hr_zones": "bpm",
        "power_zones": "%FTP",
        "threshold_pace": "m/s",
        "pace_zones": "% threshold speed",
        "pace_units": "display preference only",
    }


@coach_tool(access="read", upstream="read", local="none")
async def get_sport_settings(
    sport: str = "Ride",
    athlete_id: str | None = None,
    detail: str = "compact",
    api_key: str | None = None,
) -> ReadResponse[Any]:
    """Read current-at-fetch settings for one sport or settings ID.

    Choose this for the athlete's current FTP, zones, load order, and fatigue
    thresholds.  ``sport`` is one selector: a sport name such as ``Ride`` or
    the current settings ID.  Compact output keeps useful thresholds, zones,
    models, and ordering fields; ``full_read`` or ``detail='full'`` preserves
    every upstream field and unknown unit.  ``ftp``/``p_max`` are W,
    ``w_prime`` is J, ``after_kj0``/``after_kj1`` are kJ, heart-rate values
    are bpm, power zones are %FTP, and ``threshold_pace`` is always m/s;
    ``pace_units`` is only a display preference.  These are current settings,
    not activity-assigned historical thresholds, and the MCP performs no
    physiological calculations.  Source completeness is unknown.
    """
    resource = "sport_settings"
    if not isinstance(sport, str) or not sport.strip():
        return failure(
            resource=resource,
            code="INVALID_SPORT",
            message="sport or settings ID is required",
            phase="validation",
        )
    selector = sport.strip()
    if detail not in {"compact", "full"}:
        return failure(
            resource=resource,
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
        )
    aid, err = resolve_athlete_id(athlete_id, get_config().athlete_id)
    if err:
        return failure(resource=resource, code="INVALID_ATHLETE", message=err, phase="validation")

    query = {"sport": selector, "athlete_id": aid, "detail": detail}
    result = await make_intervals_request(
        url=f"/athlete/{aid}/sport-settings/{selector}",
        api_key=api_key,
    )
    failed = upstream_failure(result, resource=resource, athlete_id=aid, query=query)
    if failed is not None:
        return failed
    if not isinstance(result, dict):
        return invalid_upstream_response(
            resource=resource,
            athlete_id=aid,
            query=query,
            message="sport-settings response must be an object",
        )
    shape_error = _validate_settings_shape(result)
    if shape_error:
        return invalid_upstream_response(
            resource=resource, athlete_id=aid, query=query, message=shape_error
        )
    if result and not _SETTINGS_MARKER_FIELDS.intersection(result):
        return invalid_upstream_response(
            resource=resource,
            athlete_id=aid,
            query=query,
            message="sport-settings object has no recognized setting fields",
        )

    warnings: list[str] = []
    reasons = ["upstream_completeness_unverified"]
    if not result:
        warnings.append("NO_SPORT_SETTINGS")
        reasons = ["NO_SPORT_SETTINGS"]
    data: dict[str, Any]
    if detail == "compact":
        data = _compact_settings(result, athlete_id=aid, selector=selector)
    else:
        data = deepcopy(result)
    response = success(
        data,
        resource=resource,
        athlete_id=aid,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "response_complete": not warnings,
            "truncated": False,
            "reasons": reasons,
        },
        warnings=warnings,
        units=_settings_units(),
        provenance={
            "origin": "upstream intervals.icu",
            "scope": "current_at_fetch",
            "activity_assigned_values": "separate historical activity fields",
            "mcp_numeric_calculations": [],
        },
        limitations=[
            "Current sport settings are not activity-assigned historical values."
        ],
    )
    if warnings:
        response.status = "partial"
    return response


__all__ = ["get_sport_settings"]
