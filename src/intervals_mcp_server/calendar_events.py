"""Select overlapping local calendar intervals without inventing missing dates."""

from datetime import date, datetime, time
from typing import Any


# Earliest date representable by the public Python local-date contract. This
# searches the supported history rather than a fixed lookback that can omit
# ongoing long events. Intervals accepts this bound (live checked 2026-09-10).
EARLIEST_EVENT_DATE = date.min.isoformat()


def _local_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    # These are local wall-clock fields, not UTC instants. Do not silently mix
    # offset-bearing, non-contract input with the requested local-date window.
    return parsed if parsed.tzinfo is None else None


def select_overlapping_events(
    rows: list[dict[str, Any]], start_date: str, end_date_exclusive: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Keep intersecting events and flag records whose intersection is unknown.

    Source objects, duplicates, nulls and unknown fields are preserved. A start
    within the window is enough to retain an event with an unknown end. Earlier
    starts need an end after the window's start; unknown ends remain explicit
    unresolved candidates, not silently dropped or treated as open-ended.
    """
    lower = datetime.combine(date.fromisoformat(start_date), time.min)
    upper = datetime.combine(date.fromisoformat(end_date_exclusive), time.min)
    selected: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    matched_count = 0
    for index, row in enumerate(rows):
        # Unknown source fields (such as `date`) are not calendar boundaries.
        start = _local_datetime(row.get("start_date_local"))
        end = _local_datetime(row.get("end_date_local"))
        reason = None
        if start is None:
            reason = "start_date_local_unavailable_or_invalid"
        elif start >= upper:
            continue
        elif end is not None and end < start:
            reason = "end_date_local_precedes_start"
        elif start >= lower:
            matched_count += 1
        elif end is None:
            reason = "earlier_start_with_unknown_end_date_local"
        elif end <= lower:
            continue
        else:
            matched_count += 1
        selected.append(dict(row))
        if reason:
            unresolved.append({"source_index": index, "event_id": row.get("id"), "reason": reason})
    return selected, {
        "mode": "overlap",
        "interval_semantics": "local [start_date_local, end_date_local); zero-length events use their start",
        "candidate_count": len(rows),
        "matched_count": matched_count,
        "excluded_count": len(rows) - len(selected),
        "unresolved_records": unresolved,
        "unknown_dates_policy": "Unresolved candidates are retained; no dates or availability are inferred.",
    }
