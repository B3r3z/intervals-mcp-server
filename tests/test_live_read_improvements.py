"""Coach outcomes reproduced from the live audit with non-personal fixtures."""

import asyncio
from copy import deepcopy
import json
from typing import Any

import pytest

from intervals_mcp_server.contracts import failure, success
from intervals_mcp_server.tools import activities, analytics, custom_items, power_curves, quality
from intervals_mcp_server.tools import session_context as context
from intervals_mcp_server.tools.metrics import get_metric_definitions


def test_scalar_null_secondary_arrays_do_not_invent_missing_samples(monkeypatch):
    async def request(**_):
        return [{"type": kind, "data": [0, 1, 2], "data2": None}
                for kind in ("time", "watts", "heartrate")]
    monkeypatch.setattr(activities, "make_intervals_request", request)
    result = asyncio.run(activities.get_activity_streams(
        "activity", mode="range", start_index=0, end_index=3,
        stream_types="time,watts,heartrate"))
    assert result.status == "ok"
    assert result.coverage.response_complete and not result.coverage.truncated
    assert result.data["alignment"]["quality"] == "aligned"
    assert result.data["alignment"]["equal_source_lengths"] is True
    assert "MISSING_SAMPLE_INDICES" not in result.coverage.reasons
    assert result.data["streams"][1]["data2"] is None


def test_quality_counts_all_samples_and_keeps_recording_stops_separate(monkeypatch):
    source = [
        {"type": "time", "data": [0, 1, 4, 4, None, 3], "data2": None},
        {"type": "watts", "data": [0, None, 250, 0, "invalid", True], "data2": None},
    ]
    original = deepcopy(source)
    async def request(**kwargs):
        assert kwargs["url"] == "/activity/activity/streams" and "params" not in kwargs
        return source
    async def details(*_, **__):
        return success({"id": "activity", "recording_stops": [4], "icu_rpe": 0,
                        "description": None}, resource="activity")
    monkeypatch.setattr(quality, "make_intervals_request", request)
    monkeypatch.setattr(quality, "get_activity_details", details)
    result = asyncio.run(quality.get_activity_data_quality("activity"))
    assert result.status == "ok"  # The report is complete; observations may be imperfect.
    observed = result.data["stream_quality"]
    assert observed["alignment"]["quality"] == "aligned"
    watts = observed["streams"][1]["arrays"]["data"]
    assert (watts["finite_count"], watts["null_count"], watts["invalid_count"], watts["zero_count"]) == (3, 1, 2, 2)
    assert observed["time_axis"]["gap_count_over_1s"] == 1
    assert observed["time_axis"]["unrepresented_seconds_vs_1hz"] == 2
    assert observed["time_axis"]["nonpositive_delta_count"] == 1
    assert observed["time_axis"]["invalid_or_null_count"] == 1
    assert result.data["activity_metadata"]["recording_stops"] == [4]
    assert result.data["activity_metadata"]["feedback_activity_fields"]["icu_rpe"] == "present"
    assert source == original


@pytest.mark.parametrize("failed_component", ["streams", "activity", "both"])
def test_quality_preserves_independent_sources_on_failure(monkeypatch, failed_component):
    async def request(**_):
        return {"error": True, "code": "HTTP_403", "message": "Forbidden"} if failed_component in {"streams", "both"} else [{"type": "time", "data": [0]}]
    async def details(*_, **__):
        return failure(resource="activity", code="HTTP_403", message="Forbidden", phase="http") if failed_component in {"activity", "both"} else success({"id": "activity"}, resource="activity")
    monkeypatch.setattr(quality, "make_intervals_request", request)
    monkeypatch.setattr(quality, "get_activity_details", details)
    result = asyncio.run(quality.get_activity_data_quality("activity"))
    assert result.status == ("error" if failed_component == "both" else "partial")
    assert (result.data["stream_quality"] is None) == (failed_component in {"streams", "both"})
    assert (result.data["activity_metadata"] is None) == (failed_component in {"activity", "both"})


def test_fatigue_failure_preserves_normal_curve_and_redacted_guidance(monkeypatch):
    calls = []
    async def request(**kwargs):
        selector = kwargs["params"]["fatigue"]
        calls.append(selector)
        if selector == "kj0":
            return {"error": True, "code": "HTTP_422", "message": "Unprocessable", "http_status": 422}
        return [{"id": "activity", "stream_type": "watts", "after_kj": 0,
                 "secs": [5], "watts": [0], "start_index": [1], "end_index": [6]}]
    monkeypatch.setattr(power_curves, "make_intervals_request", request)
    result = asyncio.run(power_curves.get_activity_power_curves("activity", durations=[5], fatigue=["normal", "kj0"]))
    assert result.status == "partial" and result.data["curves"][0]["data_points"][0]["watts"] == 0
    assert calls == ["normal", "kj0"]
    variants = result.data["selector_results"]
    assert variants[0]["availability"] == "available"
    assert variants[0]["selection"]["verification_state"] == "not_echoed"
    assert variants[1]["error"]["http_status"] == 422
    assert "get_sport_settings" in variants[1]["error"]["recommended_action"]
    assert "not_configured" not in str(variants)


def test_missing_fatigue_echo_does_not_mark_complete_power_points_partial(monkeypatch):
    async def request(**_):
        return [{"stream_type": "watts", "secs": [5], "watts": [250],
                 "start_index": [0], "end_index": [5]}]
    monkeypatch.setattr(power_curves, "make_intervals_request", request)
    result = asyncio.run(power_curves.get_activity_power_curves("activity", durations=[5]))
    assert result.status == "ok" and result.coverage.response_complete
    assert result.data["selection"]["verified"] is False
    assert result.data["selection"]["verification_state"] == "not_echoed"


def test_contradictory_fatigue_echo_remains_partial(monkeypatch):
    async def request(**_):
        return [{"fatigue": "kj1", "stream_type": "watts", "secs": [5], "watts": [250],
                 "start_index": [0], "end_index": [5]}]
    monkeypatch.setattr(power_curves, "make_intervals_request", request)
    result = asyncio.run(power_curves.get_activity_power_curves("activity", durations=[5]))
    assert result.status == "partial"
    assert "FATIGUE_SELECTION_MISMATCH" in result.warnings


def test_unpaired_and_windowed_context_have_separate_meanings(monkeypatch):
    calls: dict[str, dict[str, Any]] = {}
    async def details(*_, **__):
        return success({"id": "activity", "paired_event_id": None,
                        "start_date_local": "2026-03-29T01:30:00"}, resource="activity")
    async def wellness(**kwargs):
        calls["wellness"] = kwargs
        return success([], resource="wellness", query=kwargs)
    async def history(**kwargs):
        calls["activities"] = kwargs
        return success([{"id": "activity", "icu_training_load": 0}], resource="activities",
                       pagination={"snapshot_id": "snapshot", "next_cursor": "next"},
                       coverage={"response_complete": False})
    async def events(**kwargs):
        calls["events"] = kwargs
        return success([{"id": 55, "category": "RACE_A"}], resource="events")
    monkeypatch.setattr(context, "get_activity_details", details)
    monkeypatch.setattr(context, "get_wellness_data", wellness)
    monkeypatch.setattr(context, "get_activities", history)
    monkeypatch.setattr(context, "get_events", events)
    result = asyncio.run(context.get_session_context(
        "activity", sections=["plan", "wellness", "activities", "contextual_events"],
        context_days_before=2, context_days_after=1, timezone="Europe/Warsaw"))
    assert all(call["start_date"] == "2026-03-27" and call["end_date_exclusive"] == "2026-03-31" for call in calls.values())
    sections = result.data["sections"]
    assert sections["plan"]["status"] == "ok" and sections["plan"]["availability"] == "unpaired"
    assert sections["plan"]["error"] is None
    assert sections["activities"]["next_read"]["parameters"]["cursor"] == "next"
    assert sections["activities"]["next_read"]["parameters"]["timezone"] == "Europe/Warsaw"
    assert sections["contextual_events"]["data"][0]["id"] == 55
    assert sections["wellness"]["projection"]["full_follow_up"]["parameters"]["end_date_exclusive"] == "2026-03-31"
    assert result.query.context_days_before == 2


@pytest.mark.parametrize("days", [-1, 32, True, 1.5, "2"])
def test_context_window_is_validated_before_http(days):
    result = asyncio.run(context.get_session_context("activity", context_days_before=days))
    assert result.error.code == "INVALID_CONTEXT_WINDOW"


def test_power_hr_full_and_compact_preserve_source_numbers(monkeypatch):
    raw = {"hrLag": 30, "decoupling": 0, "warmup": None, "future": {"preserve": True},
           "series": [{"start": i * 60, "secs": 60, "watts": 0, "hr": None} for i in range(125)],
           "curves": [{"id": "all", "coefficients": [0, 1], "r2": None}]}
    original = deepcopy(raw)
    async def request(**kwargs):
        assert kwargs["url"] == "/activity/activity/power-vs-hr.json"
        return raw
    monkeypatch.setattr(analytics, "make_intervals_request", request)
    compact = asyncio.run(analytics.get_activity_power_hr("activity"))
    full = asyncio.run(analytics.get_activity_power_hr("activity", detail="full"))
    assert compact.status == "partial" and len(compact.data["series"]) == 120
    assert compact.projection["omitted_records"] == {"series": 5}
    assert compact.data["warmup"] is None and compact.data["decoupling"] == 0
    assert full.status == "ok" and full.data == original and raw == original
    assert full.provenance["mcp_numeric_calculations"] == []


@pytest.mark.parametrize("raw", [[], {"hrLag": True}, {"series": [None]}, {"series": [{"watts": "200"}]}, {"curves": [{"coefficients": [True]}]}, {"ratioCoefficients": ["bad"]}, {"message": "unexpected"}, {"hrLag": 10**400}])
def test_power_hr_invalid_source_is_a_structured_error(monkeypatch, raw):
    async def request(**_):
        return raw
    monkeypatch.setattr(analytics, "make_intervals_request", request)
    result = asyncio.run(analytics.get_activity_power_hr("activity"))
    assert result.status == "error" and result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_power_hr_empty_response_is_a_valid_empty_fact(monkeypatch):
    async def request(**_):
        return {}
    monkeypatch.setattr(analytics, "make_intervals_request", request)
    result = asyncio.run(analytics.get_activity_power_hr("activity"))
    assert result.status == "ok" and result.data == {} and result.availability == "empty"


def test_power_hr_compact_bounds_unicode_payload_and_preserves_full_continuation(monkeypatch):
    raw = {"hrLag": 30, "future": "\u754c" * 12000, "series": [], "curves": []}
    async def request(**_):
        return raw
    monkeypatch.setattr(analytics, "make_intervals_request", request)
    compact = asyncio.run(analytics.get_activity_power_hr("activity"))
    assert len(json.dumps(compact.data, ensure_ascii=False).encode("utf-8")) <= 32768
    assert compact.projection["omitted_fields"] == ["future"]
    follow_up = compact.projection["full_read"]
    assert asyncio.run(analytics.get_activity_power_hr(**follow_up["parameters"])).data == raw


def test_quality_bounds_gap_examples_and_reports_missing_primary(monkeypatch):
    async def request(**_):
        return [{"type": "time", "data": list(range(0, 100, 2)), "data2": None},
                {"type": "watts", "data": None, "data2": None}]
    async def details(*_, **__):
        return success({"id": "activity"}, resource="activity")
    monkeypatch.setattr(quality, "make_intervals_request", request)
    monkeypatch.setattr(quality, "get_activity_details", details)
    data = asyncio.run(quality.get_activity_data_quality("activity")).data["stream_quality"]
    assert data["alignment"]["quality"] == "missing_primary"
    assert data["time_axis"]["gap_count_over_1s"] == 49
    assert len(data["time_axis"]["gap_examples"]) == 20
    assert data["time_axis"]["omitted_gap_examples"] == 29


def test_quality_distinguishes_fractional_duplicate_and_reversed_time(monkeypatch):
    async def request(**_):
        return [{"type": "time", "data": [0, 0.5, 0.5, 0.25, 1.25]}]
    async def details(*_, **__):
        return success({"id": "activity"}, resource="activity")
    monkeypatch.setattr(quality, "make_intervals_request", request)
    monkeypatch.setattr(quality, "get_activity_details", details)
    axis = asyncio.run(quality.get_activity_data_quality("activity")).data["stream_quality"]["time_axis"]
    assert axis["positive_delta_not_1s_count"] == 1
    assert axis["duplicate_timestamp_count"] == 1 and axis["reversed_timestamp_count"] == 1
    assert axis["gap_count_over_1s"] == 0


def test_custom_compact_retains_request_codes_without_scripts(monkeypatch):
    async def request(**_):
        return [{"id": 1, "name": "Sensor", "type": "ACTIVITY_STREAM", "content": {
            "code": "SensorCode", "fit_record_field": "sensor_field", "units": "unknown",
            "script": "do not execute this content"}}]
    monkeypatch.setattr(custom_items, "make_intervals_request", request)
    result = asyncio.run(custom_items.get_custom_items(athlete_id="i123"))
    item = result.data["items"][0]
    assert item["content_metadata"]["code"] == "SensorCode"
    assert item["content_metadata"]["fit_record_field"] == "sensor_field"
    assert "script" not in item["content_metadata"] and "content" not in item


def test_native_definitions_keep_activity_hrv_separate_from_wellness():
    result = asyncio.run(get_metric_definitions(names=["temp", "torque", "respiration", "hrv", "streams.hrv", "icu_intensity", "feel", "icu_rpe", "decoupling", "icu_zone_times"]))
    assert result.status == "ok"
    definitions = {row["name"]: row for row in result.data["definitions"]}
    assert definitions["hrv"]["unit"] == "ms"
    assert definitions["activity_hrv"]["unit"] == "unknown"
    assert definitions["icu_intensity"]["unit"] == "%"
