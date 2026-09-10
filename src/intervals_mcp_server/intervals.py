"""Interpret activity interval evidence and its bounded presentation together."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from intervals_mcp_server._projection import project_record_list

_COMPACT_INTERVAL_RECORDS = 100
_INTERVAL_FIELDS: tuple[str, ...] = (
    "id",
    "type",
    "name",
    "label",
    "group_id",
    "start_index",
    "end_index",
    "start_time",
    "end_time",
    "moving_time",
    "elapsed_time",
    "distance",
    "average_watts",
    "weighted_average_watts",
    "average_watts_kg",
    "average_heartrate",
    "min_heartrate",
    "max_heartrate",
    "average_cadence",
    "intensity",
    "training_load",
    "joules",
    "joules_above_ftp",
    "zone",
    "zone_min_watts",
    "zone_max_watts",
    "wbal_start",
    "wbal_end",
    "decoupling",
    "strain_score",
    "average_speed",
    "gap",
    "total_elevation_gain",
    "average_gradient",
)
_GROUP_FIELDS: tuple[str, ...] = _INTERVAL_FIELDS + ("count", "intervals")


def _shape_error(value: Any) -> str | None:
    """Validate interval containers, including the live nullable groups variant."""
    if isinstance(value, list):
        if any(not isinstance(row, dict) for row in value):
            return "flat interval list members must be objects"
        return None
    if not isinstance(value, dict):
        return "interval response must be an object or flat list"
    recognized = {"icu_intervals", "icu_groups"}.intersection(value)
    if not recognized:
        return "interval response must contain icu_intervals or icu_groups"
    for field in ("icu_intervals", "icu_groups"):
        if field not in recognized:
            continue
        rows = value[field]
        # The live API can return null here even though its OpenAPI schema says
        # array. Preserve that distinction instead of coercing it to an empty list.
        if field == "icu_groups" and rows is None:
            continue
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) for row in rows
        ):
            return f"interval field {field} must be an array of objects"
    return None


def _interval_projection(
    value: Any, activity_id: str
) -> tuple[Any, dict[str, Any]]:
    if isinstance(value, list):
        projected, metadata = project_record_list(
            value,
            _INTERVAL_FIELDS,
            limit=_COMPACT_INTERVAL_RECORDS,
            path="intervals",
        )
        metadata.update(
            {
                "mode": "compact",
                "record_limit": _COMPACT_INTERVAL_RECORDS,
                "full_follow_up": {
                    "tool": "get_activity_intervals",
                    "parameters": {"activity_id": activity_id},
                },
            }
        )
        return projected, metadata

    assert isinstance(value, dict)
    compact: dict[str, Any] = {}
    aggregate_omitted: set[str] = set(value).difference(
        {"icu_intervals", "icu_groups"}
    )
    omitted_records: dict[str, int | None] = {}
    returned_records: dict[str, int | None] = {}
    truncated_text: list[dict[str, Any]] = []
    for field, fields in (
        ("icu_intervals", _INTERVAL_FIELDS),
        ("icu_groups", _GROUP_FIELDS),
    ):
        if field not in value:
            continue
        rows = value[field]
        if field == "icu_groups" and rows is None:
            compact[field] = None
            omitted_records[field] = None
            returned_records[field] = None
            continue
        assert isinstance(rows, list)
        projected, metadata = project_record_list(
            rows,
            fields,
            limit=_COMPACT_INTERVAL_RECORDS,
            path=f"intervals.{field}",
        )
        compact[field] = projected
        aggregate_omitted.update(metadata["omitted_fields"])
        omitted_records[field] = metadata["omitted_records"]
        returned_records[field] = metadata["returned_records"]
        truncated_text.extend(metadata["truncated_text"])
    return compact, {
        "mode": "compact",
        "record_limit_per_container": _COMPACT_INTERVAL_RECORDS,
        "returned_records": returned_records,
        "omitted_records": omitted_records,
        "omitted_fields": sorted(aggregate_omitted),
        "truncated_text": truncated_text,
        "upstream_order_preserved": True,
        "order_semantics": "unknown",
        "full_follow_up": {
            "tool": "get_activity_intervals",
            "parameters": {"activity_id": activity_id},
        },
    }


@dataclass(frozen=True)
class IntervalEvidence:
    """Preserved data plus presentation facts, without a caller decoding metadata."""

    data: Any
    projection: dict[str, Any] | None
    missing: list[str]
    warnings: list[str]
    coverage: dict[str, Any]


def interval_evidence(
    value: Any, *, activity_id: str, detail: Literal["compact", "full"] = "full"
) -> IntervalEvidence:
    """Validate source shapes and own omission, missingness and coverage rules.

    Full data retains the original containers, unknown fields and null values.
    Coverage here describes the availability of intervals in a composed section;
    a standalone raw-container read can still completely return a groups-only
    payload. The caller owns source acquisition and section-level aggregation.
    """
    shape_error = _shape_error(value)
    if shape_error:
        raise ValueError(shape_error)
    if detail not in {"compact", "full"}:
        raise ValueError("interval detail must be compact or full")

    missing = ["icu_intervals"] if isinstance(value, dict) and "icu_intervals" not in value else []
    coverage: dict[str, Any] = {"reasons": []}
    projection = None
    if detail == "compact":
        data, projection = _interval_projection(value, activity_id)
        omitted = projection["omitted_records"]
        truncated = bool(
            (any(omitted.values()) if isinstance(omitted, dict) else omitted)
            or projection["omitted_fields"]
            or projection["truncated_text"]
        )
        coverage.update(response_complete=not truncated and not missing, truncated=truncated)
        if truncated:
            coverage["reasons"].append("compact_projection")
    else:
        data = deepcopy(value)
    if missing:
        coverage["response_complete"] = False
        coverage["reasons"].append("icu_intervals_missing")
    return IntervalEvidence(
        data=data,
        projection=projection,
        missing=missing,
        warnings=["ICU_INTERVALS_MISSING"] if missing else [],
        coverage=coverage,
    )
