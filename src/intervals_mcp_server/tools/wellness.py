"""Structural wellness read tool."""

from datetime import date, timedelta
from typing import Any

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import ReadResponse, failure, success
from intervals_mcp_server.mcp_instance import mcp
from intervals_mcp_server.utils.ranges import range_query, validate_range
from intervals_mcp_server.utils.validation import resolve_athlete_id

config = get_config()


@mcp.tool()
async def get_wellness_data(
    athlete_id: str | None = None,
    api_key: str | None = None,
    start_date: str | None = None,
    end_date_exclusive: str | None = None,
    end_date: str | None = None,
    include_all_fields: bool = False,
    timezone: str = "Europe/Warsaw",
) -> ReadResponse[list[dict[str, Any]]]:
    """Return raw wellness records using a half-open local-date range."""
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
    if isinstance(result, dict) and result.get("error"):
        return failure(
            resource="wellness",
            code=str(result.get("code", "UPSTREAM_ERROR")),
            message=str(result.get("message", "upstream request failed")),
            phase=str(result.get("phase", "http")),
            http_status=result.get("http_status") or result.get("status_code"),
        )
    rows: list[dict[str, Any]] = []
    if isinstance(result, dict):
        for key, value in result.items():
            if isinstance(value, dict):
                row = dict(value)
                row.setdefault("date", key)
                rows.append(row)
    elif isinstance(result, list):
        rows = [dict(row) for row in result if isinstance(row, dict)]
    query: dict[str, Any] = range_query(start, exclusive, tz, timezone)
    query.update({"upstream_newest": newest, "include_all_fields": include_all_fields})
    return success(
        rows,
        resource="wellness",
        athlete_id=aid,
        query=query,
        warnings=["DEPRECATED_END_DATE"] if deprecated else [],
    )
