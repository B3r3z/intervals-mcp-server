"""Validation and upstream adaptation for local half-open date ranges."""

from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_range(
    start: str | None, end_exclusive: str | None, legacy_end: str | None, zone: str
) -> tuple[str, str, tzinfo, bool] | str:
    if end_exclusive and legacy_end:
        return "end_date and end_date_exclusive cannot both be provided"
    try:
        tz: tzinfo = ZoneInfo(zone)
    except ZoneInfoNotFoundError:
        return f"unknown timezone: {zone}"
    try:
        local_today = datetime.now(tz).date()
        start_date = date.fromisoformat(start) if start else local_today - timedelta(days=30)
        if end_exclusive:
            end_date = date.fromisoformat(end_exclusive)
            deprecated = False
        elif legacy_end:
            end_date = date.fromisoformat(legacy_end) + timedelta(days=1)
            deprecated = True
        else:
            end_date = local_today + timedelta(days=1)
            deprecated = False
    except (TypeError, ValueError) as exc:
        return f"invalid date: {exc}"
    if start_date >= end_date:
        return "start must precede end_exclusive"
    return start_date.isoformat(), end_date.isoformat(), tz, deprecated


def range_query(start: str, end_exclusive: str, zone: tzinfo, zone_name: str) -> dict[str, str]:
    """Return explicit local and UTC boundaries for a half-open date range."""
    local_start = datetime.combine(date.fromisoformat(start), time.min, tzinfo=zone)
    local_end = datetime.combine(date.fromisoformat(end_exclusive), time.min, tzinfo=zone)
    return {
        "start_date": start,
        "end_date_exclusive": end_exclusive,
        "timezone": zone_name,
        "start_utc": local_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "end_utc_exclusive": local_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "end_utc": local_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
