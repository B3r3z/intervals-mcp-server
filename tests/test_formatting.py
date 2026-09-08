"""
Unit tests for formatting utilities in intervals_mcp_server.utils.formatting.

These tests verify that the formatting functions produce expected output strings for activities, workouts, wellness entries, events, and intervals.
"""

import json
from intervals_mcp_server.utils.formatting import (
    format_activity_summary,
    format_workout,
    format_wellness_entry,
    format_event_summary,
    format_event_details,
    format_intervals,
    format_power_curves,
)
from tests.sample_data import INTERVALS_DATA
from intervals_mcp_server.utils.types import Value, ValueUnits


def test_format_activity_summary():
    """
    Test that format_activity_summary returns a string containing the activity name and ID.
    """
    data = {
        "name": "Morning Ride",
        "id": 1,
        "type": "Ride",
        "startTime": "2024-01-01T08:00:00Z",
        "distance": 1000,
        "duration": 3600,
    }
    result = format_activity_summary(data)
    assert "Activity: Morning Ride" in result
    assert "ID: 1" in result


def test_pace_units_round_trip_and_ranges():
    expected = {
        ValueUnits.MINS_KM: "5:00/km Pace",
        ValueUnits.MINS_MILE: "5:00/mi Pace",
        ValueUnits.SECS_100M: "1:40/100m Pace",
        ValueUnits.SECS_100Y: "1:40/100y Pace",
        ValueUnits.SECS_500M: "1:40/500m Pace",
    }
    for unit, text in expected.items():
        value = 5 if unit in (ValueUnits.MINS_KM, ValueUnits.MINS_MILE) else 100
        assert str(Value(value=value, units=unit)) == text
    assert Value.from_dict({"value": 100, "units": "SECS_100Y"}).to_dict() == {
        "value": 100, "units": "SECS_100Y"
    }
    assert str(Value(start=5, end=5.5, units=ValueUnits.MINS_KM)) == "5:00/km-5:30/km Pace"


def test_format_workout():
    """
    Test that format_workout returns a string containing the workout name and interval count.
    """
    workout = {
        "name": "Workout1",
        "description": "desc",
        "sport": "Ride",
        "duration": 3600,
        "tss": 50,
        "intervals": [1, 2, 3],
    }
    result = format_workout(workout)
    assert "Workout: Workout1" in result
    assert "Intervals: 3" in result


def test_format_wellness_entry():
    """
    Test that format_wellness_entry returns a string containing the date and fitness (CTL).
    """
    with open("tests/ressources/wellness_entry.json", "r", encoding="utf-8") as f:
        entry = json.load(f)
    result = format_wellness_entry(entry)

    with open("tests/ressources/wellness_entry_formatted.txt", "r", encoding="utf-8") as f:
        expected_result = f.read()
    assert result == expected_result


def test_format_wellness_entry_include_all_fields():
    """
    Test that format_wellness_entry with include_all_fields=True includes additional unknown fields.
    """
    entry = {
        "id": "2024-06-01",
        "ctl": 80,
        "weight": 75,
        "customField1": "hello",
        "customField2": 42,
        "updated": "2024-06-01T10:00:00Z",
    }
    result = format_wellness_entry(entry, include_all_fields=True)
    assert "Date: 2024-06-01" in result
    assert "Fitness (CTL): 80" in result
    assert "Weight: 75 kg" in result
    assert "Other Fields:" in result
    assert "customField1: hello" in result
    assert "customField2: 42" in result
    # "updated" is a known built-in field, should not appear in Other Fields
    assert "updated:" not in result


def test_format_wellness_entry_no_extra_fields_by_default():
    """
    Test that format_wellness_entry without include_all_fields does not include additional fields.
    """
    entry = {
        "id": "2024-06-01",
        "ctl": 80,
        "customField1": "hello",
    }
    result = format_wellness_entry(entry)
    assert "Other Fields:" not in result
    assert "customField1" not in result


def test_format_wellness_entry_macros_populated():
    """
    Test that format_wellness_entry renders native nutrition macros
    (carbohydrates, protein, fatTotal) in grams when present.
    """
    entry = {
        "id": "2026-04-08",
        "carbohydrates": 310,
        "protein": 145,
        "fatTotal": 72,
    }
    result = format_wellness_entry(entry)
    assert "Nutrition & Hydration:" in result
    assert "- Carbohydrates: 310 g" in result
    assert "- Protein: 145 g" in result
    assert "- Fat: 72 g" in result


def test_format_wellness_entry_macros_null_hidden():
    """
    Test that format_wellness_entry hides macro lines when the fields are null,
    preserving backward compatibility with older wellness records.
    """
    entry = {
        "id": "2026-04-08",
        "ctl": 80,
        "carbohydrates": None,
        "protein": None,
        "fatTotal": None,
    }
    result = format_wellness_entry(entry)
    assert "Carbohydrates" not in result
    assert "Protein" not in result
    # "Fat" could legitimately appear inside e.g. "Body Fat" elsewhere, so
    # anchor the negative assertion on the line-prefix form we would emit.
    assert "- Fat:" not in result


def test_format_event_summary():
    """
    Test that format_event_summary returns a string containing the event date and type.
    """
    event = {
        "start_date_local": "2024-01-01",
        "id": "e1",
        "name": "Event1",
        "description": "desc",
        "race": True,
    }
    summary = format_event_summary(event)
    assert "Date: 2024-01-01" in summary
    assert "Type: Race" in summary


def test_format_event_details():
    """
    Test that format_event_details returns a string containing event and workout details.
    """
    event = {
        "id": "e1",
        "date": "2024-01-01",
        "name": "Event1",
        "description": "desc",
        "workout": {
            "id": "w1",
            "sport": "Ride",
            "duration": 3600,
            "tss": 50,
            "intervals": [1, 2],
        },
        "race": True,
        "priority": "A",
        "result": "1st",
        "calendar": {"name": "Main"},
    }
    details = format_event_details(event)
    assert "Event Details:" in details
    assert "Workout Information:" in details


def test_format_intervals():
    """
    Test that format_intervals returns a string containing interval analysis and the interval label.
    """
    result = format_intervals(INTERVALS_DATA)
    assert "Intervals Analysis:" in result
    assert "Rep 1" in result


def test_format_intervals_preserves_missing_and_zero():
    result = format_intervals({"icu_intervals": [{"average_watts": None, "max_watts": 0}],
                               "icu_groups": [{"average_watts": None, "max_watts": 0}]})
    individual, groups = result.split("Interval Groups:")
    assert "Average Power: N/A watts" in individual and "Max Power: 0 watts" in individual
    assert "Power: Avg N/A watts" in groups and "Max 0 watts" in groups


def test_current_api_activity_and_event_shape():
    assert "2026-01-02" in format_activity_summary({"name": "Ride", "start_date_local": "2026-01-02T08:00:00"})
    summary = format_event_summary({"id": "e", "category": "WORKOUT", "start_date_local": "2026-01-02T00:00:00", "name": "Ride"})
    assert "Type: Workout" in summary and "2026-01-02" in summary
    details = format_event_details({"id": "e", "category": "WORKOUT", "start_date_local": "2026-01-02T00:00:00",
                                    "name": "Ride", "type": "Ride", "workout_doc": {"duration": 120, "steps": [{}, {}]},
                                    "icu_training_load": 55})
    assert "2026-01-02" in details and "Sport: Ride" in details and "Duration: 120 seconds" in details
    assert "Intervals: 2" in details and "Training Load: 55" in details
    zero_duration = format_event_details({"category": "WORKOUT", "type": "Ride", "workout_doc": {"duration": 0}, "moving_time": 99})
    assert "Duration: 0 seconds" in zero_duration
    race = format_event_details({"category": "RACE_A", "start_date_local": "2026-01-02T00:00:00"})
    assert "Race Information:" in race


def test_format_power_curves():
    """
    Test that format_power_curves returns a concise string with curve labels,
    power values, W/kg values, and activity IDs.
    """
    curves = [
        {
            "id": "s0",
            "label": "This season",
            "start": "2025-09-29T00:00:00",
            "end": "2026-03-14T00:00:00",
            "data_points": [
                {"secs": 5, "watts": 780, "activity_id": "i100", "watts_per_kg": 10.4, "wkg_activity_id": "i100"},
                {"secs": 60, "watts": 380, "activity_id": "i102", "watts_per_kg": 5.07, "wkg_activity_id": "i102"},
                {"secs": 3600, "watts": 210, "activity_id": "i107", "watts_per_kg": 2.8, "wkg_activity_id": "i107"},
            ],
        },
    ]
    result = format_power_curves(curves, "Ride", include_normalised=True)
    assert "Power Curves (Ride):" in result
    assert "This season" in result
    assert "5s: 780W" in result
    assert "10.40W/kg" in result
    assert "1m: 380W" in result
    assert "1h: 210W" in result
    assert "i100" in result
    assert "i107" in result


def test_format_power_curves_without_normalised():
    """
    Test that format_power_curves without normalised data does not include W/kg.
    """
    curves = [
        {
            "id": "s0",
            "label": "This season",
            "start": "",
            "end": "",
            "data_points": [
                {"secs": 5, "watts": 780, "activity_id": "i100"},
            ],
        },
    ]
    result = format_power_curves(curves, "Ride", include_normalised=False)
    assert "780W" in result
    assert "W/kg" not in result
