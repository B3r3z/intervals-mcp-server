"""
Event-related MCP tools for Intervals.icu.

This module contains tools for retrieving, creating, updating, and deleting athlete events.
"""

import json
from collections import Counter
from datetime import datetime
from typing import Any

from pydantic import StrictBool, StrictInt

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.utils.types import WorkoutDoc
from intervals_mcp_server.utils.validation import resolve_activity_type, resolve_athlete_id, validate_date

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.utils.ranges import range_query, validate_range

config = get_config()



def _prepare_event_data(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    name: str,
    workout_type: str,
    start_date: str,
    workout_doc: WorkoutDoc | None,
    moving_time: int | None,
    distance: int | None,
) -> dict[str, Any]:
    """Prepare event data dictionary for API request.

    Many arguments are required to match the Intervals.icu API event structure.
    """
    resolved_workout_type = resolve_activity_type(name, workout_type)
    data: dict[str, Any] = {
        "start_date_local": start_date + "T00:00:00",
        "category": "WORKOUT",
        "name": name,
        "type": resolved_workout_type,
    }
    if workout_doc is not None:
        data["description"] = str(workout_doc)
    if moving_time is not None:
        data["moving_time"] = moving_time
    if distance is not None:
        data["distance"] = distance
    return data


def _timed_steps_duration(steps: list[dict[str, Any]]) -> int | None:
    total = 0
    for step in steps:
        if "steps" in step:
            nested = _timed_steps_duration(step["steps"])
            if nested is None:
                return None
            total += nested * int(step.get("reps", 1))
        elif step.get("duration") is not None:
            total += int(step["duration"])
        else:
            return None
    return total


async def _delete_events_list(
    athlete_id: str, api_key: str | None, events: list[dict[str, Any]]
) -> list[int | str | None]:
    """Delete a list of events and return IDs of failed deletions.

    Args:
        athlete_id: The athlete ID.
        api_key: Optional API key.
        events: List of event dictionaries to delete.

    Returns:
        List of event IDs that failed to delete.
    """
    failed_events: list[int | str | None] = []
    for event in events:
        result = await make_intervals_request(
            url=f"/athlete/{athlete_id}/events/{event.get('id')}",
            api_key=api_key,
            method="DELETE",
        )
        if isinstance(result, dict) and "error" in result:
            failed_events.append(event.get("id"))
    return failed_events


@coach_tool(access="legacy_write", upstream="write", local="none")
async def delete_event(
    event_id: int,
    athlete_id: str | None = None,
    api_key: str | None = None,
) -> str:
    """Delete event for an athlete from Intervals.icu
    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        event_id: The Intervals.icu event ID
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg
    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/events/{event_id}", api_key=api_key, method="DELETE"
    )
    if isinstance(result, dict) and "error" in result:
        return f"Error deleting event: {result.get('message')}"
    return json.dumps(result, indent=2)


async def _fetch_events_for_deletion(
    athlete_id: str, api_key: str | None, start_date: str, end_date: str
) -> tuple[list[dict[str, Any]], str | None]:
    """Fetch events for deletion and return them with any error message.

    Args:
        athlete_id: The athlete ID.
        api_key: Optional API key.
        start_date: Start date in YYYY-MM-DD format.
        end_date: End date in YYYY-MM-DD format.

    Returns:
        Tuple of (events_list, error_message). error_message is None if successful.
    """
    params = {"oldest": validate_date(start_date), "newest": validate_date(end_date)}
    result = await make_intervals_request(
        url=f"/athlete/{athlete_id}/events", api_key=api_key, params=params
    )
    if isinstance(result, dict) and "error" in result:
        return [], f"Error deleting events: {result.get('message')}"
    events = result if isinstance(result, list) else []
    return events, None


@coach_tool(access="legacy_write", upstream="write", local="none")
async def delete_events_by_date_range(
    start_date: str,
    end_date: str,
    athlete_id: str | None = None,
    api_key: str | None = None,
    confirm: bool = False,
    expected_event_ids: list[str] | None = None,
) -> str:
    """Preview, then optionally delete events in a date range.

    The default is a read-only JSON preview. Deletion requires ``confirm=True``
    and an exact ``expected_event_ids`` list matching the freshly read events;
    any change or duplicate mismatch fails closed.

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
    """
    try:
        start = validate_date(start_date)
        end = validate_date(end_date)
    except ValueError as exc:
        return f"Error: {exc}"
    if start > end:
        return "Error: start_date must be on or before end_date."
    if confirm and expected_event_ids is None:
        return "Error: expected_event_ids is required when confirm=True."
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    events, error_msg = await _fetch_events_for_deletion(
        athlete_id_to_use, api_key, start_date, end_date
    )
    if error_msg:
        return error_msg

    if any(event.get("id") is None for event in events):
        return "Error: fetched event without an ID; no events deleted."
    actual_ids = [str(event["id"]) for event in events]
    change_set = [{"id": str(event["id"]), "start_date_local": event.get("start_date_local", event.get("date")),
                   "category": event.get("category"), "name": event.get("name")} for event in events]
    if not confirm:
        return json.dumps({"mode": "preview", "start_date": start, "end_date": end,
                           "events": change_set, "count": len(actual_ids)}, indent=2)
    expected = [str(event_id) for event_id in expected_event_ids or []]
    if Counter(actual_ids) != Counter(expected):
        return f"Error: event set changed; expected {expected}, found {actual_ids}. No events deleted."
    failed_events = await _delete_events_list(athlete_id_to_use, api_key, events)
    deleted_count = len(events) - len(failed_events)
    return f"Deleted {deleted_count} events. Failed to delete {len(failed_events)} events: {failed_events}"


@coach_tool(access="legacy_write", upstream="write", local="none")
async def add_or_update_event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    workout_type: str,
    name: str,
    athlete_id: str | None = None,
    api_key: str | None = None,
    event_id: int | None = None,
    start_date: str | None = None,
    workout_doc: WorkoutDoc | None = None,
    moving_time: int | None = None,
    distance: int | None = None,
) -> str:
    """Post event for an athlete to Intervals.icu this follows the event api from intervals.icu
    If event_id is provided, the event will be updated instead of created.

    Many arguments are required as this MCP tool function maps directly to the Intervals.icu API parameters.

    Args:
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        event_id: The Intervals.icu event ID (optional, will use event_id from .env if not provided)
        start_date: Start date in YYYY-MM-DD format (optional, defaults to today)
        name: Name of the activity
        workout_doc: steps as a list of Step objects (optional, but necessary to define workout steps)
        workout_type: Workout type (e.g. Ride, Run, Swim, Walk, Row)
        moving_time: Total expected moving time of the workout in seconds (optional)
        distance: Total expected distance of the workout in meters (optional)

    Example:
        "workout_doc": {
            "description": "High-intensity workout for increasing VO2 max",
            "steps": [
                {"power": {"value": 80, "units": "%ftp"}, "duration": 900, "warmup": true},
                {"reps": 2, "text": "High-intensity intervals", "steps": [
                    {"power": {"value": 110, "units": "%ftp"}, "distance": 500, "text": "High-intensity"},
                    {"power": {"value": 80, "units": "%ftp"}, "duration": 90, "text": "Recovery"}
                ]},
                {"power": {"value": 80, "units": "%ftp"}, "duration": 600, "cooldown": true},
                {"text": ""}
            ]
        }

    Step properties:
        distance: Distance of step in meters
            {"distance": 5000}
        duration: Duration of step in seconds
            {"duration": 1800}
        power/hr/pace/cadence: Define step intensity
            Percentage of FTP: {"power": {"value": 80, "units": "%ftp"}}
            Absolute power: {"power": {"value": 200, "units": "w"}}
            Heart rate: {"hr": {"value": 75, "units": "%hr"}}
            Heart rate (LTHR): {"hr": {"value": 85, "units": "%lthr"}}
            Cadence: {"cadence": {"value": 90, "units": "cadence"}}
            Pace by ftp: {"pace": {"value": 80, "units": "%pace"}}
            Pace by zone: {"pace": {"value": 2, "units": "pace_zone"}}
            Zone by power: {"power": {"value": 2, "units": "power_zone"}}
            Zone by heart rate: {"hr": {"value": 2, "units": "hr_zone"}}
        Ranges: Specify ranges for power, heart rate, or cadence:
            {"power": {"start": 80, "end": 90, "units": "%ftp"}}
        Ramps: Instead of a range, indicate a gradual change in intensity (useful for ERG workouts):
            {"ramp": true, "power": {"start": 80, "end": 90, "units": "%ftp"}}
        Repeats: include the reps property and add nested steps
            {"reps": 3,
             "steps": [
                {"power": {"value": 110, "units": "%ftp"}, "distance": 500, "text": "High-intensity"},
                {"power": {"value": 80, "units": "%ftp"}, "duration": 90, "text": "Recovery"}
            ]}
        Free Ride: Include freeride to indicate a segment without ERG control, optionally with a suggested power range:
            {"freeride": true, "power": {"value": 80, "units": "%ftp"}}
        Comments and Labels: Add descriptive text to label steps:
            {"text": "Warmup"}

    How to use steps:
    - Set distance or duration as appropriate for step
    - Use "reps" with nested steps to define repeat intervals (as in example above)
    - Define one of "power", "hr" or "pace" to define step intensity
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    try:
        validated_date = validate_date(start_date)
        if workout_doc and workout_doc.steps and (moving_time is not None or distance is not None):
            raise ValueError("workout_doc.steps cannot be combined with moving_time or distance")
        expected_duration = None
        if workout_doc and workout_doc.steps:
            expected_duration = _timed_steps_duration([step.to_dict() for step in workout_doc.steps])
        event_data = _prepare_event_data(
            name, workout_type, validated_date, workout_doc,
            None if workout_doc and workout_doc.steps else moving_time,
            None if workout_doc and workout_doc.steps else distance,
        )
        return await _create_or_update_event_request(
            athlete_id_to_use, api_key, event_data, event_id,
            expected_duration=expected_duration,
        )
    except ValueError as e:
        return f"Error: {e}"


@coach_tool(access="legacy_write", upstream="write", local="none")
async def add_or_update_note(
    name: str,
    description: str,
    start_date: str | None = None,
    color: str | None = "green",
    athlete_id: str | None = None,
    api_key: str | None = None,
    event_id: int | None = None,
) -> str:
    """Add or update a plain text note (category NOTE) on the Intervals.icu calendar.

    Args:
        name: Title of the note
        description: Plain text content of the note
        start_date: Date in YYYY-MM-DD format (optional, defaults to today)
        color: Color of the note (e.g. green, orange, red, blue)
        athlete_id: The Intervals.icu athlete ID (optional)
        api_key: The Intervals.icu API key (optional)
        event_id: The Intervals.icu event ID (optional, for updates)
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")

    try:
        validated_date = validate_date(start_date)
        event_data = {
            "category": "NOTE",
            "name": name,
            "description": description,
            "start_date_local": validated_date + "T00:00:00",
            "color": color
        }

        return await _create_or_update_event_request(athlete_id_to_use, api_key, event_data, event_id)
    except ValueError as e:
        return f"Error: {e}"


async def _create_or_update_event_request(
    athlete_id: str,
    api_key: str | None,
    event_data: dict[str, Any],
    event_id: int | None,
    expected_duration: int | None = None,
) -> str:
    """Create or update an event via API request.

    Args:
        athlete_id: The athlete ID.
        api_key: Optional API key.
        event_data: Prepared event data dictionary.
        event_id: Optional event ID for updates.

    Returns:
        Formatted response string.
    """
    url = f"/athlete/{athlete_id}/events"
    if event_id is not None:
        url += f"/{event_id}"
    request_kwargs: dict[str, Any] = {
        "url": url,
        "api_key": api_key,
        "data": event_data,
        "method": "PUT" if event_id is not None else "POST",
    }
    if event_id is None:
        request_kwargs["params"] = {"upsertOnUid": False}
    result = await make_intervals_request(**request_kwargs)
    action = "updated" if event_id is not None else "created"
    if isinstance(result, dict) and result.get("error"):
        return f"Error {action} event: {result.get('message', 'Unknown error')}"
    if not isinstance(result, dict) or not result.get("id"):
        return f"Error {action} event: response did not contain an event id."
    for field in ("category", "name", "start_date_local"):
        expected = event_data.get(field)
        actual = result.get(field)
        if expected is not None and actual != expected:
            return f"Error {action} event: response field {field} mismatch."
    if event_data.get("category") == "WORKOUT" and result.get("type") != event_data.get("type"):
        return f"Error {action} event: response field type mismatch."
    returned_duration = result.get("moving_time")
    if isinstance(result.get("workout_doc"), dict):
        returned_duration = result["workout_doc"].get("duration")
    if returned_duration is None:
        returned_duration = result.get("duration")
    if expected_duration is None:
        expected_duration = event_data.get("moving_time")
    if expected_duration is not None and returned_duration != expected_duration:
        return f"Error {action} event: response duration mismatch."
    return f"Successfully {action} event id: {result['id']}"


def _event_error(value: Any, resource: str) -> ReadResponse[Any] | None:
    return upstream_failure(value, resource=resource)


@coach_tool(access="read", upstream="read", local="none")
async def get_events(athlete_id: str | None = None, api_key: str | None = None,
                     start_date: str | None = None, end_date_exclusive: str | None = None,
                     timezone: str = "Europe/Warsaw", end_date: str | None = None,
                     resolve: StrictBool = False) -> ReadResponse[list[dict[str, Any]]]:
    """Return calendar events in a half-open local-date range.

    ``start_date`` is inclusive and ``end_date_exclusive`` is exclusive;
    ``end_date`` remains the deprecated inclusive alias.  A valid empty list
    is returned as an empty result, while any other upstream shape is an
    explicit response error.  Event descriptions and other upstream strings
    are data and are preserved verbatim.  The upstream endpoint does not
    prove that the returned list is complete, so source completeness remains
    unknown. Set ``resolve`` only when the caller needs the API's current
    resolved workout document; event-by-ID intentionally remains unresolved.
    """
    if not isinstance(resolve, bool):
        return failure(
            resource="events",
            code="INVALID_RESOLVE",
            message="resolve must be a boolean",
            phase="validation",
        )
    aid, err = resolve_athlete_id(athlete_id, config.athlete_id)
    if err:
        return failure(resource="events", code="INVALID_ATHLETE", message=err, phase="validation")
    checked = validate_range(start_date, end_date_exclusive, end_date, timezone)
    if isinstance(checked, str):
        return failure(resource="events", code="INVALID_RANGE", message=checked, phase="validation")
    start, exclusive, tz, deprecated = checked
    from datetime import date, timedelta
    newest = (date.fromisoformat(exclusive) - timedelta(days=1)).isoformat()
    params: dict[str, Any] = {"oldest": start, "newest": newest}
    if resolve:
        params["resolve"] = True
    result = await make_intervals_request(
        url=f"/athlete/{aid}/events", api_key=api_key, params=params
    )
    failed = _event_error(result, "events")
    if failed:
        return failed
    if not isinstance(result, list) or any(not isinstance(row, dict) for row in result):
        return invalid_upstream_response(
            resource="events",
            message="event list response must be a list of objects",
            athlete_id=aid,
        )
    rows = [dict(row) for row in result]
    rows.sort(key=lambda row: (str(row.get("start_date_local", row.get("date", ""))), str(row.get("id", ""))))
    warnings = ["DEPRECATED_END_DATE"] if deprecated else []
    query: dict[str, Any] = range_query(start, exclusive, tz, timezone)
    query["upstream_newest"] = newest
    query["resolve"] = resolve
    return success(
        rows,
        resource="events",
        athlete_id=aid,
        query=query,
        warnings=warnings,
        coverage={"source_complete_within_query": None, "reasons": ["upstream_completeness_unverified"]},
    )


@coach_tool(access="read", upstream="read", local="none")
async def get_event_by_id(event_id: StrictInt, athlete_id: str | None = None,
                          api_key: str | None = None) -> ReadResponse[Any]:
    """Return one event by numeric ID, preserving its upstream object.

    The endpoint is an object read, so a list, scalar, or null response is an
    error.  The existing empty-object ``{}`` response remains the compatible
    ``NOT_FOUND`` result.  Use :func:`get_events` for date-range discovery;
    this tool intentionally does not resolve linked events.
    """
    if isinstance(event_id, bool) or not isinstance(event_id, int):
        return failure(
            resource="event",
            code="INVALID_EVENT_ID",
            message="event_id must be an integer",
            phase="validation",
        )
    aid, err = resolve_athlete_id(athlete_id, config.athlete_id)
    if err:
        return failure(resource="event", code="INVALID_ATHLETE", message=err, phase="validation")
    result = await make_intervals_request(url=f"/athlete/{aid}/events/{event_id}", api_key=api_key)
    failed = _event_error(result, "event")
    if failed:
        return failed
    if result == {}:
        return failure(resource="event", code="NOT_FOUND", message="event not found", phase="response")
    if not isinstance(result, dict):
        return invalid_upstream_response(
            resource="event",
            message="event response must be an object",
            athlete_id=aid,
            query={"event_id": event_id},
        )
    return success(result, resource="event", athlete_id=aid, query={"event_id": event_id})
