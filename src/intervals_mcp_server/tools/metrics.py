"""A small local catalogue for interpreting Intervals.icu metric fields.

The catalogue is deliberately descriptive.  It does not fetch account data,
calculate training load, or execute custom-item content.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import StrictStr

from intervals_mcp_server.contracts import (
    Coverage,
    ErrorInfo,
    Pagination,
    Query,
    ReadResponse,
    Source,
)
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.respiratory import (
    RESPIRATORY_METRICS, TYMEWEAR_LIMITATIONS, TYMEWEAR_LINKS,
    TYMEWEAR_REVIEW_NOTE, respiratory_guidance,
)


_LINK_STREAMS = "https://forum.intervals.icu/t/api-access-to-intervals-icu/609?page=7"
_LINK_STREAM_EXAMPLE = "https://forum.intervals.icu/t/solved-possible-bug-on-latitude-longitude-stream/32420"
_LINK_MODEL = "https://forum.intervals.icu/t/server-side-data-model-for-scripts/25781/16"
_LINK_SETTINGS = "https://forum.intervals.icu/t/building-workout-using-zone-number-instead-of-percentage-range/4725?page=2"
_LINK_STRAIN = "https://forum.intervals.icu/t/three-dimensional-impulse-response-model/109644"
_LINK_CUSTOM_LOAD = "https://forum.intervals.icu/t/please-help-me-get-xss-into-activities-page-weekly-totals/115699"
_LINK_HRV = "https://forum.intervals.icu/t/best-way-to-integrate-apple-watch-apple-health-data-into-intervals-icu/5776/12"
_LINK_PACE = "https://forum.intervals.icu/t/api-access-to-intervals-icu/609?page=31"
_REVIEW_NOTE = (
    "Reviewed 2026-09-09 against the supplied OpenAPI snapshot and cited official "
    "forum evidence; this is not live account verification."
)

_DEFAULT_LINKS = (_LINK_MODEL,)


def _definition(
    name: str,
    *,
    label: str,
    unit: str,
    axis: str,
    origin: str,
    calculation: str,
    limitations: list[str],
    primary_tools: list[str],
    primary_links: tuple[str, ...] | None = None,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Create one catalogue entry with a stable, client-facing shape."""
    return {
        "name": name,
        "label": label,
        "unit": unit,
        "axis": axis,
        "origin": origin,
        "calculation": calculation,
        "limitations": limitations,
        "primary_tools": primary_tools,
        # Links describe the metric's evidence directly.  They deliberately
        # do not inherit URLs from ``primary_tools``: a tool can expose many
        # unrelated fields (for example wellness and load values).
        "primary_links": list(dict.fromkeys(primary_links or _DEFAULT_LINKS)),
        "link_note": _REVIEW_NOTE,
        "aliases": list(aliases),
    }


_CATALOGUE: tuple[dict[str, Any], ...] = (
    _definition(
        "sample_index",
        label="Sample index",
        unit="sample_index",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Array position used by half-open stream ranges [start_index, end_index).",
        limitations=[
            "A sample index is not elapsed seconds and does not imply a regular time axis."
        ],
        primary_tools=["get_activity_streams", "export_activity_data"],
        aliases=("index",),
    ),
    _definition(
        "time",
        label="Elapsed time stream",
        unit="s",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Upstream time values indexed by returned samples; gaps and nulls stay visible.",
        limitations=["Do not fabricate seconds from sample positions or resample this axis."],
        primary_tools=["get_activity_streams", "export_activity_data"],
        aliases=("elapsed_seconds",),
    ),
    _definition(
        "data2",
        label="Auxiliary stream component",
        unit="unknown",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Second upstream array retained with its stream and sample alignment.",
        limitations=[
            "Its unit and meaning come from the stream definition; MCP never invents a primary data array."
        ],
        primary_tools=["get_activity_streams", "export_activity_data"],
        aliases=("secondary_stream_data",),
    ),
    _definition(
        "elapsed_time",
        label="Elapsed duration",
        unit="s",
        axis="interval_or_activity",
        origin="upstream_reported",
        calculation="Upstream elapsed duration for the returned activity or interval.",
        limitations=["It can include pauses and is distinct from moving time."],
        primary_tools=["get_activity_intervals", "get_activity_interval_stats"],
    ),
    _definition(
        "moving_time",
        label="Moving duration",
        unit="s",
        axis="interval_or_activity",
        origin="upstream_reported",
        calculation="Upstream moving duration for the returned activity or interval.",
        limitations=["It is not a replacement for elapsed duration or recording time."],
        primary_tools=["get_activity_intervals", "get_activity_interval_stats"],
    ),
    _definition(
        "recording_time",
        label="Recording duration",
        unit="s",
        axis="interval_or_activity",
        origin="upstream_reported",
        calculation="Upstream recording duration when supplied by the source.",
        limitations=["Availability and pause semantics depend on the upstream record."],
        primary_tools=["get_activity_details", "get_activity_intervals"],
        aliases=("recorded_time",),
    ),
    _definition(
        "watts",
        label="Processed power",
        unit="W",
        axis="sample_index",
        origin="upstream_calculated",
        calculation="Upstream processed or corrected power stream; no MCP correction is applied.",
        limitations=["The correction method and source device are upstream metadata."],
        primary_tools=["get_activity_streams", "get_activity_intervals", "get_activity_best_efforts"],
        aliases=("power", "corrected_watts"),
    ),
    _definition(
        "raw_watts",
        label="Raw power",
        unit="W",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Raw power field when the upstream payload supplies it.",
        limitations=["It may be absent; absence is not permission to substitute processed watts."],
        primary_tools=["get_activity_streams", "export_activity_data"],
        aliases=("raw_power",),
    ),
    _definition(
        "heartrate",
        label="Processed heart rate",
        unit="bpm",
        axis="sample_index",
        origin="upstream_calculated",
        calculation="Upstream processed heart-rate stream; no MCP filtering is applied.",
        limitations=["The upstream correction or smoothing method is not assumed."],
        primary_tools=["get_activity_streams", "get_activity_intervals"],
        aliases=("heart_rate", "corrected_heartrate"),
    ),
    _definition(
        "raw_heartrate",
        label="Raw heart rate",
        unit="bpm",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Raw heart-rate field when the upstream payload supplies it.",
        limitations=["It may be absent; no processed/raw substitution is made."],
        primary_tools=["get_activity_streams", "export_activity_data"],
        aliases=("raw_heart_rate",),
    ),
    _definition(
        "cadence",
        label="Cadence",
        unit="1/min",
        axis="sample_index",
        origin="upstream_reported",
        calculation="Upstream cadence samples, retained with their device and sport context.",
        limitations=[
            "Ride commonly uses revolutions per minute; running cadence conventions depend on the device and upstream field. Do not multiply by two."
        ],
        primary_tools=["get_activity_streams", "get_activity_intervals"],
        aliases=("rpm",),
    ),
    _definition(
        "watts_per_kg",
        label="Power-to-weight ratio",
        unit="W/kg",
        axis="sample_index_or_duration",
        origin="upstream_calculated",
        calculation="Upstream power divided by the applicable weight when supplied.",
        limitations=["W/kg is not Normalized Power; weight and provenance may vary by record."],
        primary_tools=["get_activity_streams", "get_activity_intervals", "get_athlete_power_curves"],
        aliases=("wkg", "w_per_kg", "power_per_kg"),
    ),
    _definition(
        "normalized_power",
        label="Normalized Power",
        unit="W",
        axis="activity_or_interval",
        origin="upstream_calculated",
        calculation="Normalized Power as calculated by the upstream service when supplied.",
        limitations=["Do not call this W/kg and do not recompute it in MCP."],
        primary_tools=["get_activity_details", "get_activity_intervals"],
        aliases=("np", "normalised_power", "icu_weighted_avg_watts"),
    ),
    _definition(
        "strain_score",
        label="Strain Score",
        unit="score",
        axis="activity_or_date",
        origin="upstream_calculated",
        calculation="Upstream strain score with its service-specific model.",
        limitations=["SS is distinct from TSS and cannot be substituted for power load."],
        primary_tools=["get_activity_details", "get_wellness_data"],
        aliases=("ss",),
    ),
    _definition(
        "power_load",
        label="Power load",
        unit="score",
        axis="activity_or_interval",
        origin="upstream_calculated",
        calculation="Native Activity.power_load is power-derived TSS when that exact upstream field is returned.",
        limitations=[
            "A generic or custom load field is not automatically power_load, TSS, or Strain Score."
        ],
        primary_tools=["get_activity_details", "get_activity_intervals"],
    ),
    _definition(
        "tss",
        label="Training Stress Score",
        unit="score",
        axis="activity_or_date",
        origin="upstream_calculated",
        calculation="Upstream TSS when explicitly named by the source.",
        limitations=["Do not infer TSS from a generic load field or from SS."],
        primary_tools=["get_activity_details", "get_wellness_data"],
        aliases=("training_stress_score",),
    ),
    _definition(
        "icu_training_load",
        label="Intervals training load",
        unit="score",
        axis="activity_or_date",
        origin="upstream_reported",
        calculation="Generic upstream training-load field; its load type and source/model determine interpretation.",
        limitations=[
            "It may be supplied or overridden upstream and is not assumed to be SS, TSS, TRIMP, or a comparable score."
        ],
        primary_tools=["get_activity_details", "get_wellness_data"],
        aliases=("training_load",),
    ),
    _definition(
        "icu_training_load_data",
        label="Intervals training-load metadata",
        unit="unknown",
        axis="activity_or_date",
        origin="unknown",
        calculation="Opaque upstream source or model metadata; MCP does not execute or decode it.",
        limitations=["A source code or numeric payload alone does not prove a metric or unit."],
        primary_tools=["get_activity_details", "get_wellness_data"],
        aliases=("training_load_data",),
    ),
    _definition(
        "hr_load_type",
        label="Heart-rate load type",
        unit="enum",
        axis="activity_or_date",
        origin="upstream_reported",
        calculation="Upstream selector such as AVG_HR, HR_ZONES, or HRSS.",
        limitations=["The selector describes the load method; it is not itself a load value."],
        primary_tools=["get_activity_details", "get_sport_settings"],
        aliases=("heart_rate_load_type",),
    ),
    _definition(
        "activity_assigned_ftp",
        label="Activity-assigned FTP",
        unit="W",
        axis="activity",
        origin="upstream_reported",
        calculation="FTP attached to the historical activity record when supplied.",
        limitations=["It may differ from current sport settings and is not a live setting read."],
        primary_tools=["get_activity_details", "get_activity_intervals"],
        aliases=("activity_ftp", "icu_ftp"),
    ),
    _definition(
        "current_ftp",
        label="Current sport-settings FTP",
        unit="W",
        axis="current_settings",
        origin="upstream_reported",
        calculation="FTP returned by current sport settings at fetch time.",
        limitations=["It is not historical activity-assigned FTP and can change after the activity."],
        primary_tools=["get_sport_settings"],
        aliases=("settings_ftp",),
    ),
    _definition(
        "ftp",
        label="Context-dependent FTP",
        unit="W",
        axis="context_dependent",
        origin="unknown",
        calculation="An unqualified ftp field requires its activity, event, or sport-settings context.",
        limitations=[
            "Do not map bare ftp to current settings or historical activity FTP without the surrounding record."
        ],
        primary_tools=["get_activity_details", "get_sport_settings"],
    ),
    _definition(
        "hrv",
        label="Native wellness HRV rMSSD",
        unit="ms",
        axis="local_date",
        origin="upstream_reported",
        calculation="Native Wellness.hrv value documented as rMSSD.",
        limitations=["No readiness, diagnosis, or device-method inference is made."],
        primary_tools=["get_wellness_data"],
        aliases=("hrv_rmssd", "rmssd"),
    ),
    _definition(
        "hrvSDNN",
        label="Native wellness HRV SDNN",
        unit="ms",
        axis="local_date",
        origin="upstream_reported",
        calculation="Native Wellness.hrvSDNN field when supplied.",
        limitations=["It is distinct from native hrv/rMSSD and has no clinical interpretation here."],
        primary_tools=["get_wellness_data"],
        aliases=("hrv_sdnn", "sdnn"),
    ),
    _definition(
        "vo2max_5m",
        label="Five-minute modeled VO2max",
        unit="ml/kg/min",
        axis="activity_or_date",
        origin="upstream_estimated",
        calculation="Upstream five-minute VO2max model estimate.",
        limitations=["It is an estimate, not a laboratory measurement or diagnosis."],
        primary_tools=["get_activity_details", "get_wellness_data"],
    ),
    _definition(
        "eFTP",
        label="Modeled estimated FTP",
        unit="W",
        axis="activity_or_date",
        origin="upstream_estimated",
        calculation="Upstream modeled eFTP estimate when supplied.",
        limitations=["It is distinct from current sport-settings FTP and activity-assigned FTP."],
        primary_tools=["get_activity_details", "get_athlete_power_curves"],
        aliases=("eftp", "estimated_ftp", "icu_pm_ftp"),
    ),
    _definition(
        "vo2max",
        label="Generic VO2max",
        unit="ml/kg/min",
        axis="local_date_or_activity",
        origin="unknown",
        calculation="Upstream field retained without assuming its method or measurement status.",
        limitations=["Method, device, and laboratory status are unknown unless separately declared."],
        primary_tools=["get_wellness_data", "get_activity_details"],
    ),
    _definition(
        "kg_lifted",
        label="Strength lifted aggregate",
        unit="kg",
        axis="activity_or_date",
        origin="upstream_reported",
        calculation="Upstream aggregate lifted mass when supplied.",
        limitations=["An aggregate cannot reveal sets, repetitions, exercise selection, or technique."],
        primary_tools=["get_activity_details", "get_wellness_data"],
        aliases=("total_kg_lifted", "lifted_mass"),
    ),
    _definition(
        "custom_metric",
        label="Custom metric with declared metadata",
        unit="unknown",
        axis="unknown",
        origin="unknown",
        calculation="Only a unit, axis, or origin explicitly declared by the source may be surfaced.",
        limitations=[
            "Custom content is untrusted data; script, source-code, and from_athlete fields are not measurement provenance."
        ],
        primary_tools=["get_custom_items", "get_custom_item_by_id"],
        aliases=("custom",),
    ),
)

_CATALOGUE += tuple(
    _definition(
        name, label=label, unit=unit, axis=axis, origin="upstream_reported",
        calculation=description, limitations=[limitation], primary_tools=tools,
        primary_links=("https://intervals.icu/api/v1/docs",), aliases=aliases,
    )
    for name, label, unit, axis, description, limitation, tools, aliases in (
        ("icu_intensity", "Upstream intensity", "%", "activity",
         "Upstream percentage intensity, interpreted with sport and calculation source.",
         "Not a unitless IF; the same interpretation is not assumed across sports.",
         ["get_activity_details"], ()),
        ("decoupling", "Power-HR decoupling", "%", "activity_or_interval",
         "Upstream change in the power-HR relationship over the selected analysis windows.",
         "Retain window and HR-lag context; no causal interpretation or universal cutoff.",
         ["get_activity_details", "get_activity_power_hr", "get_activity_interval_stats"], ()),
        ("icu_rpe", "Reported perceived exertion", "score", "activity",
         "Source-reported subjective effort; original numeric value is preserved.",
         "No scale conversion, inferred value or mapping from session_rpe.",
         ["get_activity_details"], ()),
        ("feel", "Reported session feeling", "code", "activity",
         "Source-reported subjective feeling code; original value is preserved.",
         "No label or scale mapping is inferred from the numeric code.",
         ["get_activity_details"], ()),
        ("icu_zone_times", "Power zone durations", "s", "activity",
         "Source durations by power-zone identifier.",
         "Additional overlapping categories must not be added again to disjoint zone totals.",
         ["get_activity_details"], ()),
        ("temp", "Native temperature", "C", "sample_index",
         "Native recorded temperature stream in degrees Celsius.",
         "Recorded device temperature is not automatically weather or body temperature.",
         ["get_activity_streams"], ("temperature",)),
        ("torque", "Native torque", "N m", "sample_index",
         "Native upstream torque observations.",
         "Device or upstream derivation must be established separately.",
         ["get_activity_streams"], ()),
        ("activity_hrv", "Activity HRV stream with unknown semantics", "unknown", "sample_index",
         "Activity stream named hrv; preserve values without assigning a wellness metric.",
         "Not interchangeable with daily Wellness.hrv rMSSD; no device-method inference.",
         ["get_activity_streams", "get_activity_data_quality"], ("streams.hrv",)),
    )
)

for _respiratory_metric in RESPIRATORY_METRICS:
    _entry = _definition(
        _respiratory_metric["name"], label=_respiratory_metric["label"],
        unit=_respiratory_metric["unit"], axis="sample_index_or_interval_or_activity",
        origin="upstream_reported", calculation=_respiratory_metric["description"],
        limitations=list(TYMEWEAR_LIMITATIONS),
        primary_tools=["get_activity_streams", "get_activity_intervals",
                       "get_activity_interval_stats", "get_activity_data_quality",
                       "get_custom_items"],
        primary_links=TYMEWEAR_LINKS, aliases=_respiratory_metric["aliases"],
    )
    _entry["link_note"] = TYMEWEAR_REVIEW_NOTE
    _entry["device_context"] = respiratory_guidance([_respiratory_metric["name"]])
    _CATALOGUE += (_entry,)

_BY_SELECTOR: dict[str, dict[str, Any]] = {}
_EXPLICIT_LINKS = {
    "sample_index": (_LINK_MODEL, _LINK_STREAMS),
    "time": (_LINK_STREAMS,),
    "data2": (_LINK_STREAMS,),
    "watts": (_LINK_STREAMS,),
    "raw_watts": (_LINK_STREAMS,),
    "heartrate": (_LINK_STREAMS,),
    "raw_heartrate": (_LINK_STREAMS,),
    "cadence": (_LINK_STREAMS,),
    "normalized_power": (_LINK_MODEL,),
    "strain_score": (_LINK_STRAIN,),
    "power_load": (_LINK_MODEL,),
    "tss": (_LINK_MODEL,),
    "icu_training_load": (_LINK_CUSTOM_LOAD, _LINK_MODEL),
    "icu_training_load_data": (_LINK_CUSTOM_LOAD, _LINK_MODEL),
    "current_ftp": (_LINK_SETTINGS,),
    "hrv": (_LINK_HRV,),
    "hrvSDNN": (_LINK_HRV,),
    "vo2max": (_LINK_HRV, _LINK_MODEL),
    "custom_metric": (_LINK_CUSTOM_LOAD, _LINK_MODEL),
}
for _item in _CATALOGUE:
    if _item["name"] in _EXPLICIT_LINKS:
        _item["primary_links"] = list(_EXPLICIT_LINKS[_item["name"]])
    _BY_SELECTOR[_item["name"].casefold()] = _item
    for _alias in _item["aliases"]:
        _BY_SELECTOR[_alias.casefold()] = _item


def _selector_values(value: Any, field: str) -> tuple[list[str], str | None]:
    """Validate one optional selector without allowing bool/string coercion."""
    if value is None:
        return [], None
    if not isinstance(value, list) or not value:
        return [], f"{field} must be a non-empty list of strings when provided"
    if any(not isinstance(item, str) or not item.strip() for item in value):
        return [], f"{field} must contain non-empty strings"
    return [item.strip() for item in value], None


def _metric_response(
    *,
    status: Literal["ok", "partial", "error"],
    data: dict[str, Any],
    query: dict[str, Any],
    warnings: list[str],
    reasons: list[str],
) -> ReadResponse[Any]:
    """Build a local-source response without implying an upstream fetch."""
    return ReadResponse(
        status=status,
        source=Source(system="intervals-mcp-server", resource="metric_definitions"),
        query=Query(**query),
        data=data,
        coverage=Coverage(
            source_complete_within_query=None,
            response_complete=status == "ok",
            truncated=False,
            reasons=reasons,
        ),
        pagination=Pagination(),
        warnings=warnings,
        error=None,
    )


def _metric_failure(code: str, message: str) -> ReadResponse[list[Any]]:
    """Return a validation error whose source is the local catalogue."""
    return ReadResponse(
        status="error",
        source=Source(system="intervals-mcp-server", resource="metric_definitions"),
        query=Query(),
        data=[],
        coverage=Coverage(
            source_complete_within_query=None,
            response_complete=False,
            truncated=False,
            reasons=[code],
        ),
        pagination=Pagination(),
        warnings=[],
        error=ErrorInfo(code=code, message=message, phase="validation"),
    )


@coach_tool(access="read", upstream="none", local="none")
async def get_metric_definitions(
    names: list[StrictStr] | None = None,
    fields: list[StrictStr] | None = None,
) -> ReadResponse[Any]:
    """Explain selected metric names and fields from the local catalogue.

    Use this before interpreting activity streams, intervals, wellness, or
    custom-item content.  Selectors are optional; omitting both returns the
    small curated catalogue.  Units, sample-index versus time axes, upstream
    reported/calculated/estimated status, and limitations are descriptive only.
    No account data is fetched, no training calculation is performed, and
    unknown selectors remain explicit in ``unknown_names``.

    Includes VT/tidal_volume, VE/tidal_volume_min and BR/respiration with
    Tymewear FIT mappings and device-unit context. Tymewear volume is relative,
    not calibrated liters; do not divide raw VT by 100 or 1000. VT is volume
    per breath, distinct from thresholds VT1/VT2. Custom names/units require
    source verification; this catalogue does not identify a recording's device.
    """
    selected_names, error = _selector_values(names, "names")
    if error:
        return _metric_failure("INVALID_SELECTOR", error)
    selected_fields, error = _selector_values(fields, "fields")
    if error:
        return _metric_failure("INVALID_SELECTOR", error)
    selectors = selected_names + selected_fields
    requested = list(dict.fromkeys(selectors))
    if requested:
        definitions: list[dict[str, Any]] = []
        unknown_names: list[str] = []
        seen: set[str] = set()
        for selector in requested:
            item = _BY_SELECTOR.get(selector.casefold())
            if item is None:
                unknown_names.append(selector)
                continue
            canonical = item["name"]
            if canonical not in seen:
                definitions.append(deepcopy(item))
                seen.add(canonical)
    else:
        definitions = [deepcopy(item) for item in _CATALOGUE]
        unknown_names = []

    warnings = ["UNKNOWN_METRIC_NAME"] if unknown_names else []
    reasons = ["curated_catalogue_non_exhaustive"]
    status: Literal["ok", "partial"] = "ok"
    if unknown_names:
        status = "partial"
        reasons.append("unknown_metric_names")
    return _metric_response(
        status=status,
        data={
            "definitions": definitions,
            "unknown_names": unknown_names,
            "catalogue_size": len(_CATALOGUE),
        },
        query={"names": selected_names or None, "fields": selected_fields or None},
        warnings=warnings,
        reasons=reasons,
    )


__all__ = ["get_metric_definitions"]
