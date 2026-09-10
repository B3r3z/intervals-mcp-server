"""Compose bounded activity context from existing read-only tools."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import json
from typing import Any, Literal
from pydantic import StrictInt

from intervals_mcp_server.contracts import (
    Coverage,
    ErrorInfo,
    Query,
    ReadResponse,
    Source,
    failure,
)
from intervals_mcp_server._projection import (
    COMPACT_TEXT_CHARS as _COMPACT_TEXT_CHARS,
    copy_projected as _copy_projected,
    project_record_list as _project_record_list,
)
from intervals_mcp_server.intervals import IntervalEvidence, interval_evidence
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.tools.activities import (
    get_activity_details,
    get_activity_intervals,
    get_activity_messages,
    get_activities,
)
from intervals_mcp_server.tools.events import get_event_by_id, get_events
from intervals_mcp_server.tools.wellness import get_wellness_data

SectionName = Literal["details", "intervals", "plan", "comments", "wellness", "activities", "contextual_events"]
DetailLevel = Literal["compact", "full"]

_SECTION_ORDER: tuple[SectionName, ...] = (
    "details",
    "intervals",
    "plan",
    "comments",
    "wellness",
    "activities",
    "contextual_events",
)
_DEFAULT_SECTIONS: tuple[SectionName, ...] = ("details", "intervals", "comments")
_COMPACT_COMMENT_RECORDS = 20
_COMPACT_WELLNESS_RECORDS = 10
_COMPACT_WORKOUT_STEPS_BYTES = 32_768

_DETAIL_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "type",
    "sub_type",
    "startTime",
    "start_date",
    "start_date_local",
    "timezone",
    "source",
    "description",
    "moving_time",
    "duration",
    "elapsed_time",
    "icu_recording_time",
    "distance",
    "icu_distance",
    "total_elevation_gain",
    "icu_average_watts",
    "icu_weighted_avg_watts",
    "average_heartrate",
    "max_heartrate",
    "average_cadence",
    "icu_training_load",
    "icu_training_load_data",
    "power_load",
    "hr_load",
    "hr_load_type",
    "pace_load",
    "pace_load_type",
    "strain_score",
    "perceived_exertion",
    "icu_rpe",
    "feel",
    "session_rpe",
    "compliance",
    "icu_intensity",
    "decoupling",
    "carbs_used",
    "carbs_ingested",
    "icu_ftp",
    "lthr",
    "threshold_pace",
    "icu_power_zones",
    "icu_zone_times",
    "icu_hr_zones",
    "icu_hr_zone_times",
    "athlete_max_hr",
    "pace_zones",
    "paired_event_id",
    "device_watts",
    "has_heartrate",
    "trainer",
    "analysis_issues",
    "tags",
    "kg_lifted",
    "_note",
)
_COMMENT_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "author",
    "source",
    "type",
    "content",
    "created",
    "updated",
    "content_fingerprint",
    "athlete_id",
    "activity_id",
    "deleted",
    "deleted_by_id",
)
_EVENT_FIELDS: tuple[str, ...] = (
    "id",
    "start_date_local",
    "end_date_local",
    "name",
    "description",
    "category",
    "type",
    "target",
    "moving_time",
    "distance",
    "icu_training_load",
    "icu_intensity",
    "strain_score",
    "icu_ftp",
    "lthr",
    "threshold_pace",
    "w_prime",
    "p_max",
    "updated",
    "plan_applied",
)
_WORKOUT_DOC_FIELDS: tuple[str, ...] = (
    "description",
    "duration",
    "distance",
    "ftp",
    "lthr",
    "threshold_pace",
    "pace_units",
    "category",
    "target",
)
_WELLNESS_FIELDS: tuple[str, ...] = (
    "id",
    "date",
    "ctl",
    "atl",
    "rampRate",
    "ctlLoad",
    "atlLoad",
    "sportInfo",
    "updated",
    "weight",
    "restingHR",
    "hrv",
    "hrvSDNN",
    "menstrualPhase",
    "menstrualPhasePredicted",
    "kcalConsumed",
    "sleepSecs",
    "sleepScore",
    "sleepQuality",
    "avgSleepingHR",
    "soreness",
    "fatigue",
    "stress",
    "mood",
    "motivation",
    "injury",
    "spO2",
    "systolic",
    "diastolic",
    "hydration",
    "hydrationVolume",
    "readiness",
    "baevskySI",
    "bloodGlucose",
    "lactate",
    "bodyFat",
    "abdomen",
    "vo2max",
    "comments",
    "steps",
    "respiration",
    "carbohydrates",
    "protein",
    "fatTotal",
    "locked",
    "tempWeight",
    "tempRestingHR",
)


def _model_dict(value: Any) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=False)


def _provenance(response: ReadResponse[Any], role: str) -> dict[str, Any]:
    return {
        "role": role,
        "source": _model_dict(response.source),
        "query": _model_dict(response.query),
    }


def _response_error(response: ReadResponse[Any]) -> dict[str, Any] | None:
    return _model_dict(response.error) if response.error is not None else None


def _response_section(
    response: ReadResponse[Any],
    *,
    data: Any,
    role: str,
    dependencies: dict[str, str] | None = None,
) -> dict[str, Any]:
    availability = {
        "ok": "available",
        "partial": "partial",
        "error": "unavailable",
    }[response.status]
    return {
        "status": response.status,
        "availability": availability,
        "data": data,
        "provenance": [_provenance(response, role)],
        "dependencies": dependencies or {},
        "coverage": _model_dict(response.coverage),
        "warnings": list(response.warnings),
        "error": _response_error(response),
    }


def _composition_error(
    *,
    code: str,
    message: str,
    data: Any,
    provenance: list[dict[str, Any]],
    dependencies: dict[str, str],
    status: Literal["partial", "error"],
    recommended_action: str | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "availability": "partial" if status == "partial" else "unavailable",
        "data": data,
        "provenance": provenance,
        "dependencies": dependencies,
        "coverage": {
            "source_complete_within_query": None,
            "response_complete": False,
            "truncated": False,
            "reasons": [code],
        },
        "warnings": [code],
        "error": {
            "code": code,
            "message": message,
            "phase": "composition",
            "http_status": None,
            "recommended_action": recommended_action,
        },
    }


def _local_failure(**kwargs: Any) -> ReadResponse[Any]:
    """Return a context-domain failure without implying a fresh upstream read."""
    response = failure(**kwargs)
    response.source.system = "intervals-mcp-server"
    return response


def _dependent_error(
    response: ReadResponse[Any], section_name: str
) -> dict[str, Any]:
    section = _response_section(
        response,
        data=[],
        role="activity_dependency",
        dependencies={"activity": "error"},
    )
    section["warnings"] = [f"{section_name.upper()}_ACTIVITY_DEPENDENCY_FAILED"]
    return section


def _threshold_values(
    value: dict[str, Any], fields: dict[str, str]
) -> dict[str, dict[str, Any]]:
    return {
        field: {"value": deepcopy(value[field]), "unit": unit}
        for field, unit in fields.items()
        if field in value
    }


def _activity_thresholds(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "activity_assigned": _threshold_values(
            activity,
            {
                "icu_ftp": "W",
                "lthr": "bpm",
                "athlete_max_hr": "bpm",
                "threshold_pace": "m/s",
                "icu_hr_zones": "bpm",
                "icu_hr_zone_times": "s",
            },
        ),
        "scope": "historical_activity_assignment",
        "current_sport_settings": {
            "status": "not_requested",
            "reason": "current settings are not substituted for activity-assigned values",
        },
    }


def _activity_field_semantics(activity: dict[str, Any]) -> dict[str, Any]:
    units = {
        field: unit
        for field, unit in {
            "kg_lifted": "kg",
            "moving_time": "s",
            "duration": "s",
            "elapsed_time": "s",
            "icu_recording_time": "s",
            "icu_hr_zones": "bpm",
            "icu_hr_zone_times": "s",
            "icu_zone_times": "s",
            "lthr": "bpm",
            "athlete_max_hr": "bpm",
        }.items()
        if field in activity
    }
    opaque = [
        field
        for field in ("hr_load_type", "pace_load_type", "icu_training_load_data")
        if field in activity
    ]
    return {
        "scope": "historical_activity",
        "units": units,
        "opaque_upstream_provenance_fields": opaque,
        "interpretation": (
            "Opaque load provenance values are preserved without model inference."
        ),
    }


def _details_section(
    response: ReadResponse[Any],
    activity: dict[str, Any],
    detail: DetailLevel,
    activity_id: str,
) -> dict[str, Any]:
    if detail == "full":
        section = _response_section(
            response,
            data=deepcopy(activity),
            role="activity_details",
            dependencies={"activity": response.status},
        )
    else:
        truncated_text: list[dict[str, Any]] = []
        data, omitted = _copy_projected(
            activity,
            _DETAIL_FIELDS,
            path="details",
            truncated_text=truncated_text,
        )
        full_parameters: dict[str, Any] = {"activity_id": activity_id}
        if "icu_intervals" in activity or "icu_groups" in activity:
            full_parameters["include_intervals"] = True
        section = _response_section(
            response,
            data=data,
            role="activity_details",
            dependencies={"activity": response.status},
        )
        section["projection"] = {
            "mode": "compact",
            "text_limit_chars": _COMPACT_TEXT_CHARS,
            "omitted_fields": sorted(omitted),
            "truncated_text": truncated_text,
            "full_follow_up": {
                "tool": "get_activity_details",
                "parameters": full_parameters,
            },
        }
        truncated = bool(omitted or truncated_text)
        section["coverage"]["response_complete"] = not truncated
        section["coverage"]["truncated"] = truncated
        if truncated:
            section["coverage"]["reasons"] = list(
                dict.fromkeys(section["coverage"]["reasons"] + ["compact_projection"])
            )
    section["thresholds"] = _activity_thresholds(activity)
    section["field_semantics"] = _activity_field_semantics(activity)
    return section


def _finalize_interval_section(
    response: ReadResponse[Any],
    evidence: IntervalEvidence,
    *,
    role: str,
    dependencies: dict[str, str],
) -> dict[str, Any]:
    section = _response_section(
        response,
        data=evidence.data,
        role=role,
        dependencies=dependencies,
    )
    if evidence.projection is not None:
        section["projection"] = evidence.projection
    reasons = section["coverage"]["reasons"] + evidence.coverage["reasons"]
    section["coverage"].update(evidence.coverage)
    section["coverage"]["reasons"] = list(dict.fromkeys(reasons))
    if evidence.missing:
        section["status"] = "partial"
        section["availability"] = "partial"
        section["missing"] = evidence.missing
        section["warnings"] = list(dict.fromkeys(section["warnings"] + evidence.warnings))
    return section


async def _intervals_section(
    activity_response: ReadResponse[Any],
    activity: dict[str, Any],
    *,
    detail: DetailLevel,
    activity_id: str,
    api_key: str | None,
) -> dict[str, Any]:
    if "icu_intervals" in activity:
        embedded = {
            field: deepcopy(activity[field])
            for field in ("icu_intervals", "icu_groups")
            if field in activity
        }
        try:
            evidence = interval_evidence(embedded, activity_id=activity_id, detail=detail)
        except ValueError as exc:
            return _composition_error(
                code="INVALID_UPSTREAM_RESPONSE",
                message=str(exc),
                data=[],
                provenance=[_provenance(activity_response, "activity_with_intervals")],
                dependencies={"activity_with_intervals": activity_response.status},
                status="error",
                recommended_action="retry get_activity_intervals after checking the source",
            )
        return _finalize_interval_section(
            activity_response,
            evidence,
            role="activity_with_intervals",
            dependencies={"activity_with_intervals": activity_response.status},
        )

    embedded_groups: list[dict[str, Any]] | None = None
    if "icu_groups" in activity:
        groups = activity["icu_groups"]
        try:
            interval_evidence({"icu_groups": groups}, activity_id=activity_id)
        except ValueError as exc:
            return _composition_error(
                code="INVALID_UPSTREAM_RESPONSE",
                message=str(exc),
                data=[],
                provenance=[_provenance(activity_response, "activity_with_intervals")],
                dependencies={"activity_with_intervals": activity_response.status},
                status="error",
            )
        if groups is not None:
            embedded_groups = deepcopy(groups)

    dedicated = await get_activity_intervals(activity_id, api_key=api_key)
    dependencies: dict[str, str] = {
        "activity_with_intervals": activity_response.status,
        "dedicated_intervals": dedicated.status,
    }
    if dedicated.status != "error":
        try:
            evidence = interval_evidence(dedicated.data, activity_id=activity_id, detail=detail)
        except ValueError as exc:
            return _composition_error(
                code="INVALID_UPSTREAM_RESPONSE",
                message=str(exc),
                data={"icu_groups": embedded_groups} if embedded_groups is not None else [],
                provenance=[
                    _provenance(activity_response, "activity_with_intervals"),
                    _provenance(dedicated, "dedicated_intervals"),
                ],
                dependencies=dependencies,
                status="partial" if embedded_groups is not None else "error",
            )
        return _finalize_interval_section(
            dedicated,
            evidence,
            role="dedicated_intervals",
            dependencies=dependencies,
        )

    if embedded_groups is not None:
        value = {"icu_groups": embedded_groups}
        section = _finalize_interval_section(
            activity_response,
            interval_evidence(value, activity_id=activity_id, detail=detail),
            role="activity_with_intervals",
            dependencies=dependencies,
        )
        section["provenance"].append(_provenance(dedicated, "dedicated_intervals"))
        section["error"] = _response_error(dedicated)
        section["warnings"] = list(
            dict.fromkeys(section["warnings"] + ["DEDICATED_INTERVAL_READ_FAILED"])
        )
        return section
    return _response_section(
        dedicated,
        data=[],
        role="dedicated_intervals",
        dependencies=dependencies,
    )


def _comments_section(
    response: ReadResponse[Any], activity_id: str, detail: DetailLevel
) -> dict[str, Any]:
    if response.status == "error" or detail == "full":
        return _response_section(
            response,
            data=deepcopy(response.data),
            role="activity_messages",
        )
    assert isinstance(response.data, list)
    compact, metadata = _project_record_list(
        response.data,
        _COMMENT_FIELDS,
        limit=_COMPACT_COMMENT_RECORDS,
        path="comments",
    )
    metadata.update(
        {
            "mode": "compact",
            "record_limit": _COMPACT_COMMENT_RECORDS,
            "text_limit_chars": _COMPACT_TEXT_CHARS,
            "full_follow_up": {
                "tool": "get_activity_messages",
                "parameters": {"activity_id": activity_id},
            },
        }
    )
    section = _response_section(
        response,
        data=compact,
        role="activity_messages",
    )
    section["projection"] = metadata
    truncated = bool(
        metadata["omitted_records"]
        or metadata["omitted_fields"]
        or metadata["truncated_text"]
    )
    section["coverage"]["response_complete"] = not truncated
    section["coverage"]["truncated"] = truncated
    if truncated:
        section["coverage"]["reasons"] = list(
            dict.fromkeys(section["coverage"]["reasons"] + ["compact_projection"])
        )
    return section


def _activity_date(activity: dict[str, Any]) -> str | None:
    value = activity.get("start_date_local")
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _paired_event_id(activity: dict[str, Any]) -> tuple[int | None, str | None]:
    if "paired_event_id" not in activity:
        return None, "PAIRED_EVENT_MISSING"
    value = activity["paired_event_id"]
    if value is None:
        return None, "PAIRED_EVENT_NULL"
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        return None, "INVALID_PAIRED_EVENT_ID"
    return value, None


def _event_thresholds(event: dict[str, Any], activity: dict[str, Any]) -> dict[str, Any]:
    workout_doc = event.get("workout_doc")
    workout_thresholds: dict[str, Any] = {}
    if isinstance(workout_doc, dict):
        workout_thresholds = _threshold_values(
            workout_doc,
            {"ftp": "W", "lthr": "bpm", "threshold_pace": "m/s"},
        )
        if "pace_units" in workout_doc:
            workout_thresholds["pace_units"] = {
                "value": deepcopy(workout_doc["pace_units"]),
                "unit": "display_unit_enum",
            }
    return {
        "activity_assigned": _activity_thresholds(activity)["activity_assigned"],
        "event_provided": _threshold_values(
            event,
            {
                "icu_ftp": "W",
                "lthr": "bpm",
                "threshold_pace": "m/s",
                "w_prime": "J",
                "p_max": "W",
            },
        ),
        "workout_document": workout_thresholds,
        "current_sport_settings": {
            "status": "not_requested",
            "reason": "current settings are not substituted for stored plan values",
        },
    }


def _compact_event(
    event: dict[str, Any],
    *,
    path: str,
) -> tuple[dict[str, Any], set[str], list[dict[str, Any]], dict[str, Any] | None, str | None]:
    truncated_text: list[dict[str, Any]] = []
    compact, omitted = _copy_projected(
        event,
        _EVENT_FIELDS,
        path=path,
        truncated_text=truncated_text,
    )
    steps_projection: dict[str, Any] | None = None
    malformed: str | None = None
    if "workout_doc" in event:
        workout_doc = event["workout_doc"]
        omitted.discard("workout_doc")
        if workout_doc is None:
            compact["workout_doc"] = None
            steps_projection = {
                "status": "unavailable",
                "reason": "upstream_workout_doc_null",
            }
        elif not isinstance(workout_doc, dict):
            malformed = "workout_doc must be an object when present"
            steps_projection = {"status": "malformed", "reason": "invalid_workout_doc"}
        else:
            compact_doc, doc_omitted = _copy_projected(
                workout_doc,
                _WORKOUT_DOC_FIELDS,
                path=f"{path}.workout_doc",
                truncated_text=truncated_text,
            )
            omitted.update(f"workout_doc.{field}" for field in doc_omitted if field != "steps")
            if "steps" in workout_doc:
                steps = workout_doc["steps"]
                if steps is None:
                    compact_doc["steps"] = None
                    steps_projection = {
                        "status": "unavailable",
                        "reason": "upstream_steps_null",
                    }
                elif not isinstance(steps, list):
                    malformed = "workout_doc.steps must be an array when present"
                    steps_projection = {
                        "status": "malformed",
                        "reason": "invalid_step_tree",
                    }
                else:
                    try:
                        step_bytes = len(
                            json.dumps(
                                steps,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        )
                    except (TypeError, ValueError, UnicodeEncodeError):
                        step_bytes = _COMPACT_WORKOUT_STEPS_BYTES + 1
                        malformed = "workout_doc.steps could not be measured as JSON"
                    if malformed is None and step_bytes <= _COMPACT_WORKOUT_STEPS_BYTES:
                        compact_doc["steps"] = deepcopy(steps)
                        steps_projection = {
                            "status": "included_whole",
                            "bytes": step_bytes,
                            "limit_bytes": _COMPACT_WORKOUT_STEPS_BYTES,
                        }
                    elif malformed is None:
                        steps_projection = {
                            "status": "omitted",
                            "reason": "compact_size_limit",
                            "limit_bytes": _COMPACT_WORKOUT_STEPS_BYTES,
                        }
            compact["workout_doc"] = compact_doc
    return compact, omitted, truncated_text, steps_projection, malformed


def _workout_document_shape_error(event: dict[str, Any]) -> str | None:
    if "workout_doc" not in event:
        return None
    workout_doc = event["workout_doc"]
    if workout_doc is None:
        return None
    if not isinstance(workout_doc, dict):
        return "workout_doc must be an object when present"
    if "steps" not in workout_doc:
        return None

    def validate_steps(steps: Any, path: str) -> str | None:
        if steps is None:
            return None
        if not isinstance(steps, list):
            return f"{path} must be an array"
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                return f"{path}[{index}] must be an object"
            for target in ("_power", "_hr", "_pace"):
                if (
                    target in step
                    and step[target] is not None
                    and not isinstance(step[target], dict)
                ):
                    return f"{path}[{index}].{target} must be a Value object"
            if "steps" in step:
                error = validate_steps(step["steps"], f"{path}[{index}].steps")
                if error:
                    return error
        return None

    return validate_steps(workout_doc["steps"], "workout_doc.steps")


def _plan_full_follow_up(
    activity_id: str, athlete_id: str | None
) -> dict[str, Any]:
    return {
        "tool": "get_session_context",
        "parameters": {
            "activity_id": activity_id,
            "sections": ["plan"],
            "detail": "full",
            "athlete_id": athlete_id,
        },
    }


def _finalize_plan_outcome(
    *,
    activity: dict[str, Any],
    activity_id: str,
    athlete_id: str | None,
    detail: DetailLevel,
    paired_id: int,
    raw_event: dict[str, Any],
    resolved_event: dict[str, Any] | None,
    response: ReadResponse[Any],
    provenance: list[dict[str, Any]],
    dependencies: dict[str, str],
    composition_error: dict[str, Any] | None = None,
    upstream_error: dict[str, Any] | None = None,
    resolved_current_plan: bool = False,
) -> dict[str, Any]:
    threshold_event = resolved_event if resolved_event is not None else raw_event
    data = {
        "paired_event_id": paired_id,
        "raw_event": deepcopy(raw_event),
        "resolved_event": deepcopy(resolved_event),
        "thresholds": _event_thresholds(threshold_event, activity),
    }
    if composition_error is None:
        section = _response_section(
            response,
            data=data,
            role="paired_event_resolved_day" if resolved_event is not None else "paired_event_raw",
            dependencies=dependencies,
        )
        section["provenance"] = provenance
    else:
        section = _composition_error(
            code=composition_error["code"],
            message=composition_error["message"],
            data=data,
            provenance=provenance,
            dependencies=dependencies,
            status="partial",
            recommended_action=composition_error.get("recommended_action"),
        )
    if upstream_error is not None:
        section["upstream_error"] = deepcopy(upstream_error)
    if resolved_current_plan:
        section["warnings"] = list(
            dict.fromkeys(section["warnings"] + ["PLAN_IS_CURRENT_STORED_VERSION"])
        )

    raw_shape_error = _workout_document_shape_error(raw_event)
    resolved_shape_error = (
        _workout_document_shape_error(resolved_event)
        if resolved_event is not None
        else None
    )
    workout_shape_error = resolved_shape_error or raw_shape_error
    if workout_shape_error:
        workout_error = {
            "code": "WORKOUT_DOCUMENT_MALFORMED",
            "message": workout_shape_error,
            "phase": "composition",
            "http_status": None,
            "recommended_action": (
                "use get_session_context detail=full to inspect the stored event"
            ),
        }
        if section["error"] is None:
            section["error"] = workout_error
        else:
            section["workout_document_error"] = workout_error
        section["status"] = "partial"
        section["availability"] = "partial"
        section["warnings"] = list(
            dict.fromkeys(section["warnings"] + ["WORKOUT_DOCUMENT_MALFORMED"])
        )
        section["coverage"]["response_complete"] = False
        section["coverage"]["reasons"] = list(
            dict.fromkeys(
                section["coverage"]["reasons"] + ["workout_document_malformed"]
            )
        )

    if detail == "full":
        return section

    raw_compact, raw_omitted, raw_text, raw_steps, raw_compact_error = _compact_event(
        raw_event, path="plan.raw_event"
    )
    if resolved_event is None:
        resolved_compact = None
        resolved_omitted: set[str] = set()
        resolved_text: list[dict[str, Any]] = []
        resolved_steps = None
        resolved_compact_error = None
    else:
        (
            resolved_compact,
            resolved_omitted,
            resolved_text,
            resolved_steps,
            resolved_compact_error,
        ) = _compact_event(resolved_event, path="plan.resolved_event")
    section["data"] = {
        "paired_event_id": paired_id,
        "raw_event": raw_compact,
        "resolved_event": resolved_compact,
        "thresholds": _event_thresholds(threshold_event, activity),
    }
    section["projection"] = {
        "mode": "compact",
        "text_limit_chars": _COMPACT_TEXT_CHARS,
        "workout_steps_limit_bytes": _COMPACT_WORKOUT_STEPS_BYTES,
        "omitted_fields": sorted(raw_omitted | resolved_omitted),
        "truncated_text": raw_text + resolved_text,
        "full_follow_up": _plan_full_follow_up(activity_id, athlete_id),
    }
    steps_projection = resolved_steps or raw_steps
    if steps_projection is not None:
        section["projection"]["workout_steps"] = steps_projection
    omitted_steps = bool(
        steps_projection
        and steps_projection.get("status") in {"omitted", "malformed"}
    )
    truncated = bool(
        raw_omitted
        or resolved_omitted
        or raw_text
        or resolved_text
        or omitted_steps
    )
    section["coverage"]["response_complete"] = (
        section["status"] == "ok" and not truncated
    )
    section["coverage"]["truncated"] = truncated
    if truncated:
        section["coverage"]["reasons"] = list(
            dict.fromkeys(section["coverage"]["reasons"] + ["compact_projection"])
        )
    compact_error = resolved_compact_error or raw_compact_error
    if compact_error and workout_shape_error is None:
        section["status"] = "partial"
        section["availability"] = "partial"
        section["coverage"]["response_complete"] = False
        section["warnings"] = list(
            dict.fromkeys(section["warnings"] + ["WORKOUT_DOCUMENT_MALFORMED"])
        )
        section["error"] = {
            "code": "WORKOUT_DOCUMENT_MALFORMED",
            "message": compact_error,
            "phase": "composition",
            "http_status": None,
            "recommended_action": (
                "use get_session_context detail=full to inspect the stored event"
            ),
        }
    return section


async def _plan_section(
    activity_response: ReadResponse[Any],
    activity: dict[str, Any],
    *,
    detail: DetailLevel,
    activity_id: str,
    athlete_id: str | None,
    timezone: str,
    api_key: str | None,
) -> dict[str, Any]:
    paired_id, pair_error = _paired_event_id(activity)
    activity_provenance = [_provenance(activity_response, "activity_pairing")]
    if pair_error == "PAIRED_EVENT_NULL":
        return {
            "status": "ok", "availability": "unpaired",
            "data": {"paired_event_id": None, "raw_event": None, "resolved_event": None},
            "provenance": activity_provenance,
            "dependencies": {"activity": activity_response.status, "paired_event": "unpaired"},
            "coverage": Coverage(source_complete_within_query=None,
                                 reasons=["explicitly_unpaired"]).model_dump(),
            "warnings": [], "error": None,
        }
    if pair_error:
        messages = {
            "PAIRED_EVENT_MISSING": "activity has no paired_event_id field",
            "PAIRED_EVENT_NULL": "activity paired_event_id is explicitly null",
            "INVALID_PAIRED_EVENT_ID": "paired_event_id must be a positive integer",
        }
        link_data = (
            {}
            if "paired_event_id" not in activity
            else {"paired_event_id": deepcopy(activity["paired_event_id"])}
        )
        return _composition_error(
            code=pair_error,
            message=messages[pair_error],
            data=link_data,
            provenance=activity_provenance,
            dependencies={"activity": activity_response.status, "paired_event": "unavailable"},
            status="error",
            recommended_action="use get_event_by_id only after obtaining a valid numeric link",
        )
    assert paired_id is not None

    raw_response = await get_event_by_id(
        paired_id, athlete_id=athlete_id, api_key=api_key
    )
    provenance = activity_provenance + [_provenance(raw_response, "paired_event_raw")]
    dependencies: dict[str, str] = {
        "activity": activity_response.status,
        "paired_event_raw": raw_response.status,
    }
    if raw_response.status == "error" or not isinstance(raw_response.data, dict):
        section = _response_section(
            raw_response,
            data={"paired_event_id": paired_id, "raw_event": None, "resolved_event": None},
            role="paired_event_raw",
            dependencies=dependencies,
        )
        section["provenance"] = provenance
        return section

    raw_event = deepcopy(raw_response.data)
    raw_id = raw_event.get("id")
    if "id" not in raw_event:
        identity_error = {
            "code": "PAIRED_EVENT_ID_MISSING",
            "message": "paired event response has no id",
            "recommended_action": "inspect the raw event with get_event_by_id",
        }
    elif isinstance(raw_id, bool) or not isinstance(raw_id, int) or raw_id < 1:
        identity_error = {
            "code": "PAIRED_EVENT_ID_INVALID",
            "message": "paired event response id must be a positive integer",
            "recommended_action": "inspect the raw event with get_event_by_id",
        }
    elif raw_id != paired_id:
        identity_error = {
            "code": "PAIRED_EVENT_ID_MISMATCH",
            "message": "paired event response id does not match paired_event_id",
            "recommended_action": "inspect the raw event with get_event_by_id",
        }
    else:
        identity_error = None
    if identity_error is not None:
        dependencies["paired_event_identity"] = "error"
        return _finalize_plan_outcome(
            activity=activity,
            activity_id=activity_id,
            athlete_id=athlete_id,
            detail=detail,
            paired_id=paired_id,
            raw_event=raw_event,
            resolved_event=None,
            response=raw_response,
            provenance=provenance,
            dependencies=dependencies,
            composition_error=identity_error,
        )
    dependencies["paired_event_identity"] = "ok"
    event_day = _activity_date(raw_event)
    if event_day is None:
        dependencies["paired_event_date"] = "error"
        return _finalize_plan_outcome(
            activity=activity,
            activity_id=activity_id,
            athlete_id=athlete_id,
            detail=detail,
            paired_id=paired_id,
            raw_event=raw_event,
            resolved_event=None,
            response=raw_response,
            provenance=provenance,
            dependencies=dependencies,
            composition_error={
                "code": "PAIRED_EVENT_DATE_INVALID",
                "message": "paired event has no valid start_date_local date",
                "recommended_action": "inspect the raw event with get_event_by_id",
            },
        )

    next_day = (date.fromisoformat(event_day) + timedelta(days=1)).isoformat()
    resolved_response = await get_events(
        athlete_id=athlete_id,
        api_key=api_key,
        start_date=event_day,
        end_date_exclusive=next_day,
        timezone=timezone,
        resolve=True,
        include_overlapping=False,
    )
    provenance.append(_provenance(resolved_response, "paired_event_resolved_day"))
    dependencies["paired_event_date"] = "ok"
    dependencies["resolved_event_day"] = resolved_response.status
    if resolved_response.status == "error" or not isinstance(resolved_response.data, list):
        return _finalize_plan_outcome(
            activity=activity,
            activity_id=activity_id,
            athlete_id=athlete_id,
            detail=detail,
            paired_id=paired_id,
            raw_event=raw_event,
            resolved_event=None,
            response=raw_response,
            provenance=provenance,
            dependencies=dependencies,
            composition_error={
                "code": "PAIRED_EVENT_RESOLVE_FAILED",
                "message": "paired event resolve read failed; raw event is retained",
                "recommended_action": "retry the same-day get_events read with resolve=true",
            },
            upstream_error=_response_error(resolved_response),
        )

    matches = [
        row
        for row in resolved_response.data
        if isinstance(row.get("id"), int)
        and not isinstance(row.get("id"), bool)
        and row["id"] == paired_id
    ]
    if len(matches) != 1:
        code = "AMBIGUOUS_PAIRED_EVENT" if len(matches) > 1 else "PAIRED_EVENT_NOT_RESOLVED"
        message = (
            "resolved event list contains multiple rows with the paired event id"
            if len(matches) > 1
            else "resolved event list contains no row with the paired event id"
        )
        return _finalize_plan_outcome(
            activity=activity,
            activity_id=activity_id,
            athlete_id=athlete_id,
            detail=detail,
            paired_id=paired_id,
            raw_event=raw_event,
            resolved_event=None,
            response=resolved_response,
            provenance=provenance,
            dependencies=dependencies,
            composition_error={
                "code": code,
                "message": message,
                "recommended_action": "inspect the raw event and same-day resolved event list",
            },
        )

    resolved_event = deepcopy(matches[0])
    return _finalize_plan_outcome(
        activity=activity,
        activity_id=activity_id,
        athlete_id=athlete_id,
        detail=detail,
        paired_id=paired_id,
        raw_event=raw_event,
        resolved_event=resolved_event,
        response=resolved_response,
        provenance=provenance,
        dependencies=dependencies,
        resolved_current_plan=True,
    )


def _wellness_section(
    response: ReadResponse[Any],
    *,
    detail: DetailLevel,
    activity_id: str,
    activity_day: str,
    athlete_id: str | None,
) -> dict[str, Any]:
    dependencies: dict[str, str] = {
        "activity_date": "ok",
        "wellness": response.status,
    }
    if response.status == "error" or detail == "full":
        return _response_section(
            response,
            data=deepcopy(response.data),
            role="activity_day_wellness",
            dependencies=dependencies,
        )
    assert isinstance(response.data, list)
    compact, metadata = _project_record_list(
        response.data,
        _WELLNESS_FIELDS,
        limit=_COMPACT_WELLNESS_RECORDS,
        path="wellness",
    )
    metadata.update(
        {
            "mode": "compact",
            "record_limit": _COMPACT_WELLNESS_RECORDS,
            "text_limit_chars": _COMPACT_TEXT_CHARS,
            "full_follow_up": {
                "tool": "get_wellness_data",
                "parameters": {
                    "athlete_id": athlete_id,
                    "start_date": response.query.model_dump().get("start_date", activity_day),
                    "timezone": response.query.model_dump().get("timezone", "Europe/Warsaw"),
                    "end_date_exclusive": response.query.model_dump().get("end_date_exclusive", (
                        date.fromisoformat(activity_day) + timedelta(days=1)
                    ).isoformat()),
                },
            },
        }
    )
    section = _response_section(
        response,
        data=compact,
        role="activity_day_wellness",
        dependencies=dependencies,
    )
    section["projection"] = metadata
    truncated = bool(
        metadata["omitted_records"]
        or metadata["omitted_fields"]
        or metadata["truncated_text"]
    )
    section["coverage"]["response_complete"] = not truncated
    section["coverage"]["truncated"] = truncated
    if truncated:
        section["coverage"]["reasons"] = list(
            dict.fromkeys(section["coverage"]["reasons"] + ["compact_projection"])
        )
    return section


def _context_list_section(
    response: ReadResponse[Any], *, kind: str, detail: DetailLevel,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    fields = (
        ("id", "name", "type", "start_date_local", "moving_time", "elapsed_time", "distance",
         "total_elevation_gain", "icu_training_load", "power_load", "hr_load", "strain_score",
         "icu_rpe", "feel", "paired_event_id", "source", "tags")
        if kind == "activities" else
        ("id", "name", "category", "type", "start_date_local", "end_date_local",
         "description", "training_availability", "paired_activity_id", "icu_training_load")
    )
    data = deepcopy(response.data)
    projection = None
    if response.status != "error" and detail == "compact":
        data, projection = _project_record_list(data, fields, limit=20, path=kind)
    section = _response_section(response, data=data, role=kind)
    section["pagination"] = response.pagination.model_dump()
    tool = "get_activities" if kind == "activities" else "get_events"
    section["full_read"] = {"tool": tool, "parameters": parameters}
    if response.pagination.next_cursor:
        section["next_read"] = {"tool": tool,
                                "parameters": {**parameters, "cursor": response.pagination.next_cursor}}
    if projection is not None:
        section["projection"] = projection
        omitted = bool(projection["omitted_records"] or projection["omitted_fields"]
                       or projection["truncated_text"])
        if omitted:
            section["coverage"]["response_complete"] = False
            section["coverage"]["truncated"] = True
            section["coverage"]["reasons"].append("compact_projection")
    if kind == "contextual_events":
        section["pairing_semantics"] = "Calendar context only; shared dates do not establish a workout link."
        if response.model_extra and "overlap" in response.model_extra:
            section["overlap"] = deepcopy(response.model_extra["overlap"])
    return section


def _aggregate_response(
    *,
    activity_id: str,
    requested: list[SectionName],
    detail: DetailLevel,
    athlete_id: str | None,
    timezone: str,
    sections: dict[str, dict[str, Any]],
) -> ReadResponse[Any]:
    statuses = [section["status"] for section in sections.values()]
    usable = [status for status in statuses if status in {"ok", "partial"}]
    if not usable:
        status: Literal["ok", "partial", "error"] = "error"
    elif all(section_status == "ok" for section_status in statuses):
        status = "ok"
    else:
        status = "partial"
    truncated = any(
        bool(section.get("coverage", {}).get("truncated"))
        for section in sections.values()
    )
    complete = status == "ok" and not truncated and all(
        bool(section.get("coverage", {}).get("response_complete"))
        for section in sections.values()
    )
    reasons = ["upstream_completeness_unverified"]
    if truncated:
        reasons.append("compact_projection")
    if status != "ok":
        reasons.append("section_failures_or_partial_results")
    warnings = [
        f"SECTION_{name.upper()}_{section['status'].upper()}"
        for name, section in sections.items()
        if section["status"] != "ok"
    ]
    return ReadResponse(
        status=status,
        source=Source(
            system="intervals-mcp-server",
            resource="session_context",
            athlete_id=athlete_id,
        ),
        query=Query.model_validate(
            {
                "activity_id": activity_id,
                "sections": requested,
                "detail": detail,
                "timezone": timezone,
            }
        ),
        data={
            "activity_id": activity_id,
            "detail": detail,
            "requested_sections": requested,
            "sections": sections,
        },
        coverage=Coverage(
            source_complete_within_query=None,
            response_complete=complete,
            truncated=truncated,
            reasons=reasons,
        ),
        warnings=warnings,
        error=(
            ErrorInfo(
                code="SESSION_CONTEXT_UNAVAILABLE",
                message="all requested session context sections are unavailable",
                phase="composition",
                recommended_action="use the section error details and retry the relevant raw read tool",
            )
            if status == "error"
            else None
        ),
    )


@coach_tool(access="read", upstream="read", local="memory")
async def get_session_context(
    activity_id: str,
    sections: list[SectionName] | None = None,
    detail: DetailLevel = "compact",
    athlete_id: str | None = None,
    timezone: str = "Europe/Warsaw",
    api_key: str | None = None,
    context_days_before: StrictInt = 0,
    context_days_after: StrictInt = 0,
) -> ReadResponse[Any]:
    """Return bounded, section-aware context for one completed activity.

    The default sections are details, intervals, and comments. Only requested
    sections are fetched; comments can be read without an athlete ID or an
    activity-detail request. ``compact`` uses fixed limits (20 comments, 100
    intervals and groups, 10 wellness rows, 4,000 characters per projected text
    field, and 32,768 UTF-8 bytes for the complete workout step tree) and reports
    every omission with an exact full-read continuation. It never prunes a
    workout step tree or a resolved ``_power``, ``_hr``, or ``_pace`` value.

    Plan resolution follows only a positive numeric ``paired_event_id``: the
    raw event is fetched first, its own local date selects one resolved day, and
    exactly one matching numeric ID is accepted. A failed resolve retains the
    raw event. The resolved plan is the current stored version, not necessarily
    the historical version executed by the activity. Activity-assigned
    thresholds, stored event/workout thresholds, and current sport settings are
    separate sources; this tool does not fetch or substitute current settings.
    Each requested section reports its own status, availability, provenance,
    dependencies, coverage, warnings, and error. A valid empty section remains
    a successful fact, and successful sections survive failures elsewhere.
    An explicitly null paired_event_id is a successful unpaired fact. Optional
    activities and contextual_events sections use the same local-date window as
    wellness; context_days_before/after each accept 0..31 days (default zero).
    Activities are paged at 20 records with an exact raw continuation. Events
    provide context only and never imply pairing. Defaults fetch no extra history.
    """
    if not isinstance(activity_id, str) or not activity_id.strip():
        return _local_failure(
            resource="session_context",
            code="INVALID_ACTIVITY_ID",
            message="activity_id must be a non-empty string",
            phase="validation",
        )
    if detail not in {"compact", "full"}:
        return _local_failure(
            resource="session_context",
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
            query={"activity_id": activity_id},
        )
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 31
           for value in (context_days_before, context_days_after)):
        return _local_failure(resource="session_context", code="INVALID_CONTEXT_WINDOW",
                              message="context days must be integers in 0..31", phase="validation")
    requested_raw: list[Any] = list(_DEFAULT_SECTIONS if sections is None else sections)
    if not requested_raw:
        return _local_failure(
            resource="session_context",
            code="INVALID_SECTIONS",
            message="sections must contain at least one supported section",
            phase="validation",
            query={"activity_id": activity_id},
        )
    allowed = set(_SECTION_ORDER)
    if (
        any(not isinstance(section, str) or section not in allowed for section in requested_raw)
        or len({section for section in requested_raw if isinstance(section, str)})
        != len(requested_raw)
    ):
        return _local_failure(
            resource="session_context",
            code="INVALID_SECTIONS",
            message="sections must be unique supported section names",
            phase="validation",
            query={"activity_id": activity_id},
        )
    requested = [section for section in _SECTION_ORDER if section in requested_raw]

    activity_sections = {"details", "intervals", "plan", "wellness", "activities", "contextual_events"}
    needs_activity = any(section in activity_sections for section in requested)
    activity_response: ReadResponse[Any] | None = None
    activity: dict[str, Any] | None = None
    if needs_activity:
        activity_response = await get_activity_details(
            activity_id,
            api_key=api_key,
            include_intervals="intervals" in requested,
        )
        if activity_response.status != "error" and isinstance(activity_response.data, dict):
            activity = activity_response.data

    composed: dict[str, dict[str, Any]] = {}
    if "details" in requested:
        assert activity_response is not None
        composed["details"] = (
            _dependent_error(activity_response, "details")
            if activity is None
            else _details_section(activity_response, activity, detail, activity_id)
        )

    if "intervals" in requested:
        assert activity_response is not None
        composed["intervals"] = (
            _dependent_error(activity_response, "intervals")
            if activity is None
            else await _intervals_section(
                activity_response,
                activity,
                detail=detail,
                activity_id=activity_id,
                api_key=api_key,
            )
        )

    if "plan" in requested:
        assert activity_response is not None
        composed["plan"] = (
            _dependent_error(activity_response, "plan")
            if activity is None
            else await _plan_section(
                activity_response,
                activity,
                detail=detail,
                activity_id=activity_id,
                athlete_id=athlete_id,
                timezone=timezone,
                api_key=api_key,
            )
        )

    if "comments" in requested:
        comments_response = await get_activity_messages(activity_id, api_key=api_key)
        composed["comments"] = _comments_section(
            comments_response, activity_id, detail
        )

    for context_section in ("wellness", "activities", "contextual_events"):
        if context_section not in requested:
            continue
        assert activity_response is not None
        if activity is None:
            composed[context_section] = _dependent_error(activity_response, context_section)
        else:
            activity_day = _activity_date(activity)
            window_start, window_end = None, None
            if activity_day is not None:
                try:
                    window_start = (date.fromisoformat(activity_day) - timedelta(days=context_days_before)).isoformat()
                    window_end = (date.fromisoformat(activity_day) + timedelta(days=context_days_after + 1)).isoformat()
                except (ValueError, OverflowError):
                    activity_day = None
            if activity_day is None:
                composed[context_section] = _composition_error(
                    code="ACTIVITY_DATE_INVALID",
                    message="activity has no valid local date for the requested context window",
                    data=[],
                    provenance=[_provenance(activity_response, "activity_date")],
                    dependencies={"activity": activity_response.status, "activity_date": "error"},
                    status="error",
                    recommended_action="inspect activity details and request context by an explicit date",
                )
            else:
                parameters: dict[str, Any] = {"athlete_id": athlete_id, "start_date": window_start,
                              "end_date_exclusive": window_end, "timezone": timezone}
                if context_section == "wellness":
                    wellness_response = await get_wellness_data(api_key=api_key, **parameters)
                    composed["wellness"] = _wellness_section(
                        wellness_response, detail=detail, activity_id=activity_id,
                        activity_day=activity_day, athlete_id=athlete_id,
                    )
                else:
                    if context_section == "activities":
                        context_response = await get_activities(api_key=api_key, page_size=20, **parameters)
                        parameters["page_size"] = 20
                    else:
                        parameters["include_overlapping"] = True
                        context_response = await get_events(api_key=api_key, **parameters)
                    composed[context_section] = _context_list_section(
                        context_response, kind=context_section, detail=detail, parameters=parameters,
                    )

    response = _aggregate_response(
        activity_id=activity_id,
        requested=requested,
        detail=detail,
        athlete_id=athlete_id,
        timezone=timezone,
        sections=composed,
    )
    response.query = Query.model_validate({**response.query.model_dump(),
                                         "context_days_before": context_days_before,
                                         "context_days_after": context_days_after})
    return response


__all__ = ["get_session_context"]
