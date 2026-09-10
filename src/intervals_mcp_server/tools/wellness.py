"""Structural wellness read tool."""

from datetime import date, timedelta
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
from intervals_mcp_server.utils.ranges import range_query, validate_range
from intervals_mcp_server.utils.validation import resolve_athlete_id

config = get_config()


@coach_tool(access="read", upstream="read", local="none")
async def get_wellness_data(
    athlete_id: str | None = None,
    api_key: str | None = None,
    start_date: str | None = None,
    end_date_exclusive: str | None = None,
    end_date: str | None = None,
    include_all_fields: bool = False,
    timezone: str = "Europe/Warsaw",
) -> ReadResponse[list[dict[str, Any]]]:
    """Return raw wellness records using a half-open local-date range.

    ``start_date`` is inclusive and ``end_date_exclusive`` is exclusive;
    ``end_date`` remains the deprecated inclusive alias.  The upstream API
    may return an array of records or a date-keyed object whose keys are
    ISO-local dates.  Empty arrays/maps are valid empty data, while null,
    scalar, mixed-member, and meaningless date-map shapes are errors.  All
    native and custom fields, including null and zero, are preserved and
    source completeness remains unknown.  Consult ``get_metric_definitions``
    before interpreting fields: native ``hrv`` is rMSSD and ``hrvSDNN`` is a
    separate millisecond field; generic VO2max method and custom-field units
    remain unknown unless explicitly declared by the source.
    """
    aid, err = resolve_athlete_id(athlete_id, config.athlete_id)
    if err:
        return failure(resource="wellness", code="INVALID_ATHLETE", message=err, phase="validation")
    checked = validate_range(start_date, end_date_exclusive, end_date, timezone)
    if isinstance(checked, str):
        return failure(
            resource="wellness", code="INVALID_RANGE", message=checked, phase="validation"
        )
    start, exclusive, tz, deprecated = checked
    newest = (date.fromisoformat(exclusive) - timedelta(days=1)).isoformat()
    result = await make_intervals_request(
        url=f"/athlete/{aid}/wellness",
        api_key=api_key,
        params={"oldest": start, "newest": newest},
    )
    failed = upstream_failure(result, resource="wellness", athlete_id=aid)
    if failed:
        return failed
    rows: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for key, value in result.items():
            if (
                not isinstance(key, str)
                or len(key) != 10
                or key[4] != "-"
                or key[7] != "-"
            ):
                return invalid_upstream_response(
                    resource="wellness",
                    message="wellness object keys must be ISO dates",
                    athlete_id=aid,
                )
            try:
                date.fromisoformat(key)
            except ValueError:
                return invalid_upstream_response(
                    resource="wellness",
                    message="wellness object keys must be valid ISO dates",
                    athlete_id=aid,
                )
            if not isinstance(value, dict):
                return invalid_upstream_response(
                    resource="wellness",
                    message="wellness date values must be objects",
                    athlete_id=aid,
                )
            row = dict(value)
            row.setdefault("date", key)
            rows.append(row)
    elif isinstance(result, list):
        if any(not isinstance(row, dict) for row in result):
            return invalid_upstream_response(
                resource="wellness",
                message="wellness list members must be objects",
                athlete_id=aid,
            )
        rows = [dict(row) for row in result]
    else:
        return invalid_upstream_response(
            resource="wellness",
            message="wellness response must be a list or date-keyed object",
            athlete_id=aid,
        )
    query: dict[str, Any] = range_query(start, exclusive, tz, timezone)
    query.update({"upstream_newest": newest, "include_all_fields": include_all_fields})
    return success(
        rows,
        resource="wellness",
        athlete_id=aid,
        query=query,
        warnings=["DEPRECATED_END_DATE"] if deprecated else [],
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
    )
