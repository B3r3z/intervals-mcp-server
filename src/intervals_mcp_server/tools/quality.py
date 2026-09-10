"""Bounded evidence about activity data quality, without coaching decisions."""

from typing import Any

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.contracts import (
    ReadResponse, failure, invalid_upstream_response, success, upstream_failure,
)
from intervals_mcp_server.stream_quality import summarize_streams
from intervals_mcp_server.respiratory import respiratory_guidance
from intervals_mcp_server.tools.activities import _validate_stream_payload, get_activity_details


@coach_tool(access="read", upstream="read", local="none")
async def get_activity_data_quality(
    activity_id: str, api_key: str | None = None,
) -> ReadResponse[Any]:
    """Summarize all returned stream samples and activity metadata using GETs only.

    Finite fractions use source sample count, not elapsed time. Time gaps are
    relative to a 1-second reference and do not prove dropped sensor data.
    Optional secondary arrays, missing primary arrays, zero and null are distinct.
    Metadata and stream failures are independent. No sensor-source, physiological
    or readiness inference is made, and only 20 gap examples are returned.
    Conditional Tymewear documentation is in provenance.respiratory_interpretation:
    VT/VE use relative device volume units, BR uses breaths/min. Finite raw VT
    values such as 186 are not invalid merely because they are not in liters.
    No volume conversion or VE=VT*BR consistency check is performed.
    """
    resource = "activity_data_quality"
    query = {"activity_id": activity_id}
    if not isinstance(activity_id, str) or not activity_id.strip():
        return failure(resource=resource, code="INVALID_ACTIVITY_ID",
                       message="activity_id is required", phase="validation")
    raw = await make_intervals_request(url=f"/activity/{activity_id}/streams", api_key=api_key)
    stream_response: ReadResponse[Any] | None = upstream_failure(raw, resource="activity_streams", query=query)
    if stream_response is None:
        shape_error = _validate_stream_payload(raw)
        if shape_error:
            stream_response = invalid_upstream_response(resource="activity_streams", message=shape_error)
    stream_data = None
    respiratory_interpretation: dict[str, Any] = {}
    if stream_response is None:
        assert isinstance(raw, list)
        stream_data = summarize_streams(raw)
        respiratory_interpretation = respiratory_guidance(stream["type"] for stream in raw)
        stream_response = success({}, resource="activity_streams", query=query)
    details = await get_activity_details(activity_id, api_key=api_key)
    metadata = None
    if details.status != "error" and isinstance(details.data, dict):
        activity = details.data
        metadata = {key: activity[key] for key in (
            "recording_stops", "icu_recording_time", "moving_time", "elapsed_time",
            "device_name", "power_meter", "stream_types", "icu_ignore_power",
            "icu_ignore_hr", "icu_intervals_edited", "icu_lap_count", "paired_event_id",
        ) if key in activity}
        metadata["feedback_activity_fields"] = {
            key: "absent" if key not in activity else "null" if activity[key] is None
            else "empty" if activity[key] == "" else "present"
            for key in ("description", "icu_rpe", "feel", "carbs_ingested")
        }
    components: dict[str, dict[str, Any]] = {
        name: {"status": response.status, "source": response.source.model_dump(mode="json"),
               "coverage": response.coverage.model_dump(), "warnings": response.warnings,
               "error": response.error.model_dump(mode="json") if response.error else None}
        for name, response in (("streams", stream_response), ("activity", details))
    }
    failed = [name for name, component in components.items() if component["status"] == "error"]
    incomplete = [name for name, component in components.items() if component["status"] != "ok"]
    response = success(
        {"activity_id": activity_id, "stream_quality": stream_data,
         "activity_metadata": metadata, "components": components},
        resource=resource, query=query,
        coverage={"source_complete_within_query": None, "response_complete": not incomplete,
                  "reasons": ["upstream_completeness_unverified"] + incomplete},
        warnings=[f"{name.upper()}_{components[name]['status'].upper()}" for name in incomplete],
        provenance={"mcp_numeric_calculations": ["sample counts and finite fractions",
                                                "adjacent time deltas relative to 1 Hz"],
                    "upstream_atomic_snapshot": False,
                    "respiratory_interpretation": respiratory_interpretation},
    )
    response.source.system = "intervals-mcp-server"
    if incomplete:
        response.status = "error" if len(failed) == 2 else "partial"
        if len(failed) == 2:
            response.error = stream_response.error
    return response
