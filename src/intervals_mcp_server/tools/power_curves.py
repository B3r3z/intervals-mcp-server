"""
Power curve MCP tools for Intervals.icu.

This module contains tools for retrieving athlete power curve data.
"""

from datetime import datetime
import json
from typing import Any

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import ReadResponse, success, failure
from intervals_mcp_server.utils.validation import resolve_athlete_id

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.mcp_instance import mcp  # noqa: F401

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


def _extract_curve_data(
    curve: dict[str, Any],
    durations: list[int],
    include_normalised: bool,
) -> dict[str, Any]:
    """Extract power data for requested durations from a single curve.

    Args:
        curve: A single curve object from the API response.
        durations: List of durations in seconds to extract.
        include_normalised: Whether to include W/kg data.

    Returns:
        Dictionary with curve metadata and extracted data points.
    """
    secs = curve.get("secs", [])
    values = curve.get("values", [])
    activity_ids = curve.get("activity_id", [])
    watts_per_kg = curve.get("watts_per_kg", [])
    wkg_activity_ids = curve.get("wkg_activity_id", [])

    # Build a lookup from seconds to index for efficient access
    sec_to_idx: dict[int, int] = {s: i for i, s in enumerate(secs)}

    data_points: list[dict[str, Any]] = []
    for dur in durations:
        idx = sec_to_idx.get(dur)
        if idx is None or idx >= len(values):
            continue
        point: dict[str, Any] = {
            "secs": dur,
            "watts": values[idx],
            "activity_id": (
                activity_ids[idx]
                if idx < len(activity_ids) and activity_ids[idx] is not None
                else None
            ),
        }
        if include_normalised and idx < len(watts_per_kg):
            point["watts_per_kg"] = watts_per_kg[idx]
            point["wkg_activity_id"] = (
                wkg_activity_ids[idx]
                if idx < len(wkg_activity_ids)
                and wkg_activity_ids[idx] is not None
                else None
            )
        data_points.append(point)

    return {
        "id": curve.get("id"),
        "label": curve.get("label", curve.get("id")),
        "start": curve.get("start_date_local"),
        "end": curve.get("end_date_local"),
        "data_points": data_points,
    }


@mcp.tool()
async def get_athlete_power_curves(activity_type: str = "Ride", durations: list[int] | None = None, indoor_outdoor: str | None = None, start_date: str | None = None, end_date: str | None = None, this_season: bool = True, last_season: bool = True, include_normalised: bool = True, athlete_id: str | None = None, api_key: str | None = None) -> ReadResponse[Any]:
    durations = durations or list(DEFAULT_DURATIONS)
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
    if isinstance(result, dict) and result.get("error"):
        return failure(resource="power_curves", code=str(result.get("code", "UPSTREAM_ERROR")), message=str(result.get("message")), phase=str(result.get("phase", "http")), http_status=result.get("http_status") or result.get("status_code"))
    source = result.get("list", []) if isinstance(result, dict) else result if isinstance(result, list) else []
    data = [_extract_curve_data(curve, durations, include_normalised) for curve in source if isinstance(curve, dict)]
    missing = [duration for duration in durations if not any(point.get("secs") == duration for curve in data for point in curve["data_points"])]
    return success({"curves": data, "missing_durations": missing}, resource="power_curves", athlete_id=aid, query={"activity_type": activity_type, "durations": durations, "indoor_outdoor": indoor_outdoor, "include_normalised": include_normalised}, coverage={"source_complete_within_query": None, "reasons": ["missing_durations"] if missing else []}, warnings=["MISSING_DURATION"] if missing else [])
