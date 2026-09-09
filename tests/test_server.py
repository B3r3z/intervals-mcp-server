"""
Unit tests for the main MCP server tool functions in intervals_mcp_server.server.

These tests use monkeypatching to mock API responses and verify the formatting and output of each tool function:
- get_activities
- get_activity_details
- get_activity_intervals
- get_activity_streams
- get_activity_messages
- add_activity_message
- get_events
- get_event_by_id
- add_or_update_event
- get_wellness_data

The tests ensure that the server's public API returns expected strings and handles data correctly.
"""

import asyncio
import os
import pathlib
import sys
import json

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("API_KEY", "test")
os.environ.setdefault("ATHLETE_ID", "i1")

from intervals_mcp_server.server import (  # pylint: disable=wrong-import-position
    add_activity_message,
    get_activities,
    get_activity_details,
    get_activity_intervals,
    get_activity_messages,
    get_activity_streams,
    add_or_update_event,
    get_athlete_power_curves,
    get_event_by_id,
    delete_events_by_date_range,
    get_events,
    get_wellness_data,
    get_custom_items,
    get_custom_item_by_id,
    create_custom_item,
    update_custom_item,
    delete_custom_item,
)
from intervals_mcp_server.utils.types import Step, WorkoutDoc  # pylint: disable=wrong-import-position
from intervals_mcp_server.tools.events import add_or_update_note  # pylint: disable=wrong-import-position
from tests.sample_data import INTERVALS_DATA, POWER_CURVES_DATA  # pylint: disable=wrong-import-position


def test_get_activities(monkeypatch):
    """
    Test get_activities returns a formatted string containing activity details when given a sample activity.
    """
    sample = {
        "name": "Morning Ride",
        "id": 123,
        "type": "Ride",
        "startTime": "2024-01-01T08:00:00Z",
        "distance": 1000,
        "duration": 3600,
    }

    async def fake_request(*_args, **_kwargs):
        return [sample]

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activities(athlete_id="1", limit=1))
    assert result.status == "ok" and result.data[0]["name"] == "Morning Ride"


def test_get_activity_details(monkeypatch):
    """
    Test get_activity_details returns a formatted string with the activity name and details.
    """
    sample = {
        "name": "Morning Ride",
        "id": 123,
        "type": "Ride",
        "startTime": "2024-01-01T08:00:00Z",
        "distance": 1000,
        "duration": 3600,
    }

    async def fake_request(*_args, **_kwargs):
        return sample

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_details(123))
    assert result.status == "ok" and result.data["name"] == "Morning Ride"


def test_get_events(monkeypatch):
    """
    Test get_events returns a formatted string containing event details when given a sample event.
    """
    event = {
        "date": "2024-01-01",
        "id": "e1",
        "name": "Test Event",
        "description": "desc",
        "race": True,
    }

    async def fake_request(*_args, **_kwargs):
        return [event]

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake_request)
    result = asyncio.run(get_events(athlete_id="1", start_date="2024-01-01", end_date="2024-01-02"))
    assert result.status == "ok" and result.data[0]["name"] == "Test Event"


def test_get_event_by_id(monkeypatch):
    """
    Test get_event_by_id returns a formatted string with event details for a given event ID.
    """
    event = {
        "id": "e1",
        "date": "2024-01-01",
        "name": "Test Event",
        "description": "desc",
        "race": True,
    }

    seen = []
    async def fake_request(*_args, **_kwargs):
        seen.append(_args[0] if _args else _kwargs.get("url"))
        return event

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake_request)
    result = asyncio.run(get_event_by_id(1, athlete_id="1"))
    assert result.status == "ok" and result.data["name"] == "Test Event"
    assert seen == ["/athlete/1/events/1"]


def test_delete_events_preview_and_exact_confirmation(monkeypatch):
    calls = []
    events = [{"id": "a", "start_date_local": "2024-01-01T00:00:00", "category": "NOTE", "name": "A"},
              {"id": "b", "date": "2024-01-02", "category": "WORKOUT", "name": "B"}]
    async def fake(*args, **kwargs):
        calls.append((kwargs.get("method", "GET"), kwargs.get("url", args[0] if args else "")))
        return events if kwargs.get("method", "GET") != "DELETE" else {}
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    preview = json.loads(asyncio.run(delete_events_by_date_range("2024-01-01", "2024-01-02", athlete_id="1")))
    assert preview["events"][0]["id"] == "a" and len(calls) == 1
    calls.clear()
    stale = asyncio.run(delete_events_by_date_range("2024-01-01", "2024-01-02", athlete_id="1", confirm=True, expected_event_ids=["a", "a"]))
    assert "No events deleted" in stale and all(method != "DELETE" for method, _ in calls)
    calls.clear()
    ok = asyncio.run(delete_events_by_date_range("2024-01-01", "2024-01-02", athlete_id="1", confirm=True, expected_event_ids=["b", "a"]))
    assert "Deleted 2" in ok and [url for method, url in calls if method == "DELETE"] == ["/athlete/1/events/a", "/athlete/1/events/b"]


def test_delete_preview_requires_confirmation_ids_and_rejects_missing_id(monkeypatch):
    calls = []
    async def fake(*args, **kwargs):
        calls.append(kwargs.get("method", "GET"))
        return [{"id": None, "name": "bad"}]
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    missing = asyncio.run(delete_events_by_date_range("2024-01-01", "2024-01-01", athlete_id="1"))
    assert "without an ID" in missing and calls == ["GET"]
    calls.clear()
    none_ids = asyncio.run(delete_events_by_date_range("2024-01-01", "2024-01-01", athlete_id="1", confirm=True))
    assert "expected_event_ids" in none_ids and calls == []


def test_structured_workout_payload_and_postconditions(monkeypatch):
    captured = []
    async def fake(*args, **kwargs):
        captured.append(kwargs)
        return {"id": "w1", "category": "WORKOUT", "name": "Timed", "start_date_local": "2024-01-01T00:00:00",
                "type": "Ride", "workout_doc": {"duration": 120}}
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    doc = WorkoutDoc(steps=[Step(duration=60), Step(steps=[Step(duration=30)], reps=2)])
    result = asyncio.run(add_or_update_event("Ride", "Timed", athlete_id="1", start_date="2024-01-01", workout_doc=doc))
    assert "Successfully created" in result
    payload = captured[0]["data"]
    assert captured[0]["method"] == "POST"
    assert captured[0]["params"] == {"upsertOnUid": False}
    assert payload["description"] == str(doc)
    assert "moving_time" not in payload and "distance" not in payload
    captured.clear()
    rejected = asyncio.run(add_or_update_event("Ride", "Timed", athlete_id="1", workout_doc=doc, moving_time=1))
    assert "cannot be combined" in rejected and not captured
    captured.clear()
    rejected_distance = asyncio.run(add_or_update_event("Ride", "Timed", athlete_id="1", workout_doc=doc, distance=1))
    assert "cannot be combined" in rejected_distance and not captured


def test_event_write_postconditions_and_note(monkeypatch):
    doc = WorkoutDoc(steps=[Step(duration=120)])
    responses = [
        {"category": "WORKOUT", "name": "Timed", "start_date_local": "2024-01-01T00:00:00", "type": "Ride", "workout_doc": {"duration": 120}},
        {"id": "w", "category": "WORKOUT", "name": "Wrong", "start_date_local": "2024-01-01T00:00:00", "type": "Ride", "workout_doc": {"duration": 120}},
        {"id": "w", "category": "WORKOUT", "name": "Timed", "start_date_local": "2024-01-01T00:00:00", "type": "Ride", "workout_doc": {"duration": 60}},
        {"error": True, "message": "upstream failed"},
    ]
    async def fake(*_args, **_kwargs):
        return responses.pop(0)
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    for expected in ("event id", "mismatch", "duration mismatch", "upstream failed"):
        result = asyncio.run(add_or_update_event("Ride", "Timed", athlete_id="1", start_date="2024-01-01", workout_doc=doc))
        assert "Error" in result and expected in result
    async def note(*_args, **_kwargs):
        return {"id": "n", "category": "NOTE", "name": "Note", "start_date_local": "2024-01-01T00:00:00"}
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", note)
    assert "Successfully created event id: n" in asyncio.run(add_or_update_note("Note", "Text", start_date="2024-01-01", athlete_id="1"))


def test_get_wellness_data(monkeypatch):
    """
    Test get_wellness_data returns a formatted string containing wellness data for a given athlete.
    """
    wellness = {
        "2024-01-01": {
            "id": "2024-01-01",
            "ctl": 75,
            "sleepSecs": 28800,
        }
    }

    async def fake_request(*_args, **_kwargs):
        return wellness

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", fake_request)
    result = asyncio.run(get_wellness_data(athlete_id="1"))
    assert result.status == "ok" and result.data[0]["date"] == "2024-01-01"


def test_get_wellness_data_renders_macros(monkeypatch):
    """
    Integration test: native nutrition macros (carbohydrates, protein,
    fatTotal) flow from the API response through get_wellness_data into the
    formatted output.
    """
    wellness = [
        {
            "id": "2026-04-08",
            "carbohydrates": 310,
            "protein": 145,
            "fatTotal": 72,
        }
    ]

    async def fake_request(*_args, **_kwargs):
        return wellness

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", fake_request)
    result = asyncio.run(get_wellness_data(athlete_id="1"))
    assert result.status == "ok" and result.data[0]["carbohydrates"] == 310


def test_get_wellness_data_include_all_fields(monkeypatch):
    """
    Test get_wellness_data with include_all_fields=True returns a formatted string including additional fields.
    """
    wellness = [
        {
            "id": "2024-01-01",
            "ctl": 75,
            "sleepSecs": 28800,
            "customField": "custom_value",
        }
    ]

    async def fake_request(*_args, **_kwargs):
        return wellness

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", fake_request)
    result = asyncio.run(get_wellness_data(athlete_id="1", include_all_fields=True))
    assert result.status == "ok" and result.data[0]["customField"] == "custom_value"


def test_get_activity_intervals(monkeypatch):
    """
    Test get_activity_intervals returns a formatted string with interval analysis for a given activity.
    """

    async def fake_request(*_args, **_kwargs):
        return INTERVALS_DATA

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_intervals("123"))
    assert result.status == "ok" and "icu_intervals" in result.data


def test_get_activity_streams(monkeypatch):
    """
    Test get_activity_streams returns a formatted string with stream data for a given activity.
    """
    sample_streams = [
        {
            "type": "time",
            "name": "time",
            "data": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "data2": [],
            "valueType": "time_units",
            "valueTypeIsArray": False,
            "anomalies": None,
            "custom": False,
        },
        {
            "type": "watts",
            "name": "watts",
            "data": [150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200],
            "data2": [],
            "valueType": "power_units",
            "valueTypeIsArray": False,
            "anomalies": None,
            "custom": False,
        },
        {
            "type": "heartrate",
            "name": "heartrate",
            "data": [120, 125, 130, 135, 140, 145, 150, 155, 160, 165, 170],
            "data2": [],
            "valueType": "hr_units",
            "valueTypeIsArray": False,
            "anomalies": None,
            "custom": False,
        },
    ]

    async def fake_request(*_args, **_kwargs):
        return sample_streams

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_streams("i107537962"))
    assert result.status == "partial"
    assert {s["type"] for s in result.data["streams"]} == {"time", "watts", "heartrate"}


def test_get_activity_streams_range_and_invalid_range(monkeypatch):
    calls = []
    streams = [{"type": "watts", "name": "watts", "valueType": "power_units",
                "data": [0, 1, None, 3, 4, 5, 6, 7]}]
    async def fake(*args, **kwargs):
        calls.append((args, kwargs))
        return streams
    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    result = asyncio.run(get_activity_streams("a", mode="range", start_index=2, end_index=6))
    assert result.data["streams"][0]["data"] == [None, 3, 4, 5]
    calls.clear()
    bad = asyncio.run(get_activity_streams("a", mode="range", start_index=2))
    assert bad.status == "error" and not calls
    calls.clear()
    assert asyncio.run(get_activity_streams("a", mode="range", start_index=-1, end_index=2)).status == "error" and not calls
    assert asyncio.run(get_activity_streams("a", mode="range", start_index=2, end_index=2)).status == "error" and not calls
    assert asyncio.run(get_activity_streams("a", mode="range", start_index=0, end_index=99)).status == "error" and len(calls) == 1


def test_get_activity_streams_latlng_slices_data2(monkeypatch):
    async def fake(*_args, **_kwargs):
        return [{"type": "latlng", "name": "latlng", "valueType": "latlng", "data": [1, None, 0, 4],
                 "data2": [5, 6, None, 0], "valueTypeIsArray": True, "custom": False}]
    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    result = asyncio.run(get_activity_streams("a", mode="range", start_index=1, end_index=4))
    stream = result.data["streams"][0]
    assert stream["data"] == [None, 0, 4] and stream["data2"] == [6, None, 0]
    assert stream["valueTypeIsArray"] is True


def test_add_or_update_event(monkeypatch):
    """
    Test create/update requests and their event payloads match the API contract.
    """
    expected_response = {
        "id": 123,
        "start_date_local": "2024-01-15T00:00:00",
        "category": "WORKOUT",
        "name": "Test Workout",
        "type": "Ride",
    }
    calls = []

    async def fake_post_request(*_args, **_kwargs):
        calls.append(_kwargs)
        return expected_response

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_post_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", fake_post_request
    )
    result = asyncio.run(
        add_or_update_event(
            athlete_id="i1", start_date="2024-01-15", name="Test Workout", workout_type="Ride"
        )
    )
    assert "Successfully created event id:" in result
    assert "123" in result
    assert calls[0]["method"] == "POST"
    assert calls[0]["params"] == {"upsertOnUid": False}
    assert "description" not in calls[0]["data"]

    updated = asyncio.run(
        add_or_update_event(
            athlete_id="i1",
            start_date="2024-01-15",
            name="Test Workout",
            workout_type="Ride",
            event_id=123,
        )
    )
    assert "Successfully updated event id: 123" in updated
    assert calls[1]["method"] == "PUT"
    assert "params" not in calls[1]


def test_get_activity_messages(monkeypatch):
    """Test get_activity_messages returns formatted messages for an activity."""
    sample_messages = [
        {
            "id": 1,
            "name": "Niko",
            "created": "2024-06-15T10:30:00Z",
            "type": "NOTE",
            "content": "Legs felt heavy today",
        },
        {
            "id": 2,
            "name": "Coach",
            "created": "2024-06-15T11:00:00Z",
            "type": "TEXT",
            "content": "Good effort despite that!",
        },
    ]

    async def fake_request(*_args, **_kwargs):
        return sample_messages

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_messages(activity_id="i123"))
    assert result.status == "ok" and result.data[0]["content"] == "Legs felt heavy today"
    assert result.data[1]["content_fingerprint"]


def test_get_activity_messages_error(monkeypatch):
    """Test get_activity_messages handles API errors gracefully."""

    async def fake_request(*_args, **_kwargs):
        return {"error": True, "message": "Activity not found"}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_messages(activity_id="i999"))
    assert result.status == "error" and result.error.message == "Activity not found"


def test_get_activity_messages_empty(monkeypatch):
    """Test get_activity_messages returns appropriate message when no messages exist."""

    async def fake_request(*_args, **_kwargs):
        return []

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(get_activity_messages(activity_id="i123"))
    assert result.status == "ok" and result.data == []


def test_add_activity_message(monkeypatch):
    """Test add_activity_message posts a message and returns confirmation."""

    async def fake_request(*_args, **kwargs):
        assert kwargs.get("method") == "POST"
        assert kwargs.get("data") == {"content": "Great run!"}
        return {"id": 42, "new_chat": None}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(add_activity_message(activity_id="i123", content="Great run!"))
    assert "Successfully added message" in result
    assert "42" in result


def test_add_activity_message_missing_id(monkeypatch):
    """Test add_activity_message warns when response has no ID."""

    async def fake_request(*_args, **_kwargs):
        return {"new_chat": None}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(add_activity_message(activity_id="i123", content="Hello"))
    assert "appears to have been added" in result
    assert "verify manually" in result


def test_add_activity_message_unexpected_response(monkeypatch):
    """Test add_activity_message handles unexpected non-dict response."""

    async def fake_request(*_args, **_kwargs):
        return None

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(add_activity_message(activity_id="i123", content="Hello"))
    assert "Unexpected response" in result


def test_add_activity_message_error(monkeypatch):
    """Test add_activity_message handles API errors."""

    async def fake_request(*_args, **_kwargs):
        return {"error": True, "message": "Not found"}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(add_activity_message(activity_id="i999", content="Hello"))
    assert "Error adding message" in result


def test_get_athlete_power_curves(monkeypatch):
    """
    Test get_athlete_power_curves returns formatted power curve data with both seasons.
    """

    async def fake_request(*_args, **_kwargs):
        return POWER_CURVES_DATA

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake_request
    )
    result = asyncio.run(
        get_athlete_power_curves(
            activity_type="Ride",
            athlete_id="i1",
        )
    )
    assert result.status == "ok" and result.data["curves"]


def test_get_athlete_power_curves_custom_durations(monkeypatch):
    """
    Test get_athlete_power_curves with custom durations returns only those durations.
    """

    async def fake_request(*_args, **_kwargs):
        return POWER_CURVES_DATA

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake_request
    )
    result = asyncio.run(
        get_athlete_power_curves(
            activity_type="Ride",
            durations=[5, 60],
            athlete_id="i1",
        )
    )
    durations = [x["secs"] for x in result.data["curves"][0]["data_points"]]
    assert durations == [5, 60]


def test_get_athlete_power_curves_without_normalised(monkeypatch):
    """
    Test get_athlete_power_curves without normalised data excludes W/kg values.
    """

    async def fake_request(*_args, **_kwargs):
        return POWER_CURVES_DATA

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake_request
    )
    result = asyncio.run(
        get_athlete_power_curves(
            activity_type="Ride",
            include_normalised=False,
            athlete_id="i1",
        )
    )
    assert result.status == "ok" and "watts_per_kg" not in result.data["curves"][0]["data_points"][0]


def test_get_athlete_power_curves_date_validation(monkeypatch):
    """
    Test get_athlete_power_curves validates date parameters.
    """

    async def fake_request(*_args, **_kwargs):
        return POWER_CURVES_DATA

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake_request
    )
    # Only start_date without end_date should fail
    result = asyncio.run(
        get_athlete_power_curves(
            activity_type="Ride",
            start_date="2026-01-01",
            athlete_id="i1",
        )
    )
    assert result.status == "error"


def test_get_athlete_power_curves_no_curves_selected(monkeypatch):
    """
    Test get_athlete_power_curves returns error when no curves selected.
    """

    async def fake_request(*_args, **_kwargs):
        return POWER_CURVES_DATA

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake_request
    )
    result = asyncio.run(
        get_athlete_power_curves(
            activity_type="Ride",
            this_season=False,
            last_season=False,
            athlete_id="i1",
        )
    )
    assert result.status == "error"


def test_get_custom_items(monkeypatch):
    """
    Test get_custom_items returns a formatted string containing custom item details.
    """
    custom_items = [
        {"id": 1, "name": "HR Zones", "type": "ZONES", "description": "Heart rate zones"},
        {"id": 2, "name": "Power Chart", "type": "FITNESS_CHART", "description": None},
    ]

    async def fake_request(*_args, **_kwargs):
        return custom_items

    # Patch in both api.client and tools modules to ensure it works
    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(get_custom_items(athlete_id="1"))
    assert "Custom Items:" in result
    assert "HR Zones" in result
    assert "ZONES" in result
    assert "Power Chart" in result


def test_get_custom_item_by_id(monkeypatch):
    """
    Test get_custom_item_by_id returns formatted details of a single custom item.
    """
    custom_item = {
        "id": 1,
        "name": "HR Zones",
        "type": "ZONES",
        "description": "Heart rate zones",
        "visibility": "PRIVATE",
        "index": 0,
    }

    async def fake_request(*_args, **_kwargs):
        return custom_item

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(get_custom_item_by_id(item_id=1, athlete_id="1"))
    assert "Custom Item Details:" in result
    assert "HR Zones" in result
    assert "ZONES" in result
    assert "Heart rate zones" in result
    assert "PRIVATE" in result


def test_create_custom_item(monkeypatch):
    """
    Test create_custom_item returns a success message with formatted item details.
    """
    created_item = {
        "id": 10,
        "name": "New Chart",
        "type": "FITNESS_CHART",
        "description": "A new fitness chart",
        "visibility": "PRIVATE",
    }

    async def fake_request(*_args, **_kwargs):
        return created_item

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(
        create_custom_item(name="New Chart", item_type="FITNESS_CHART", athlete_id="1")
    )
    assert "Successfully created custom item:" in result
    assert "New Chart" in result
    assert "FITNESS_CHART" in result


def test_create_custom_item_with_string_content(monkeypatch):
    """
    Test create_custom_item correctly parses content when passed as a JSON string.
    """
    captured: dict = {}

    async def fake_request(*_args, **kwargs):
        captured["data"] = kwargs.get("data")
        return {
            "id": 11,
            "name": "Activity Field",
            "type": "ACTIVITY_FIELD",
            "content": {"expression": "icu_training_load"},
        }

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(
        create_custom_item(
            name="Activity Field",
            item_type="ACTIVITY_FIELD",
            athlete_id="1",
            content='{"expression": "icu_training_load"}',  # type: ignore[arg-type]
        )
    )
    assert "Successfully created custom item:" in result
    # Verify the content was parsed from string to dict before being sent
    assert isinstance(captured["data"]["content"], dict)
    assert captured["data"]["content"]["expression"] == "icu_training_load"


def test_update_custom_item(monkeypatch):
    """
    Test update_custom_item returns a success message with formatted item details.
    """
    updated_item = {
        "id": 1,
        "name": "Updated Chart",
        "type": "FITNESS_CHART",
        "description": "Updated description",
        "visibility": "PUBLIC",
    }

    async def fake_request(*_args, **_kwargs):
        return updated_item

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(
        update_custom_item(item_id=1, name="Updated Chart", athlete_id="1")
    )
    assert "Successfully updated custom item:" in result
    assert "Updated Chart" in result
    assert "PUBLIC" in result


def test_delete_custom_item(monkeypatch):
    """
    Test delete_custom_item returns the API response.
    """

    async def fake_request(*_args, **_kwargs):
        return {}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(delete_custom_item(item_id=1, athlete_id="1"))
    assert "Successfully deleted" in result


def test_create_custom_item_with_invalid_json_content(monkeypatch):
    """
    Test create_custom_item returns an error message when content is an invalid JSON string.
    """

    async def fake_request(*_args, **_kwargs):
        return {}

    monkeypatch.setattr("intervals_mcp_server.api.client.make_intervals_request", fake_request)
    monkeypatch.setattr(
        "intervals_mcp_server.tools.custom_items.make_intervals_request", fake_request
    )
    result = asyncio.run(
        create_custom_item(
            name="Bad Item",
            item_type="FITNESS_CHART",
            athlete_id="1",
            content="not valid json",  # type: ignore[arg-type]
        )
    )
    assert "Error: content must be valid JSON when passed as a string." in result
