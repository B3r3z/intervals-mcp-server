from __future__ import annotations

import asyncio
from typing import Any

import pytest

from intervals_mcp_server.tools.activities import (
    export_activity_data,
    get_activities,
    get_activity_details,
    get_activity_intervals,
    get_activity_messages,
    get_activity_streams,
)
from intervals_mcp_server.tools.events import get_event_by_id, get_events
from intervals_mcp_server.tools.power_curves import get_athlete_power_curves
from intervals_mcp_server.tools.wellness import get_wellness_data


def _patch_request(monkeypatch: pytest.MonkeyPatch, module: str, value: Any) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return value

    monkeypatch.setattr(f"intervals_mcp_server.tools.{module}.make_intervals_request", fake)


def _run_stream(monkeypatch: pytest.MonkeyPatch, value: Any, **kwargs: Any) -> Any:
    _patch_request(monkeypatch, "activities", value)
    return asyncio.run(get_activity_streams("activity", **kwargs))


@pytest.mark.parametrize("payload", [None, "not-json-shape", {}, {"list": None}, [{"id": "ok"}, "bad"]])
def test_power_curves_reject_uninterpretable_payloads(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "power_curves", payload)
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete", durations=[5], this_season=True, last_season=False
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize("durations", [[0], [-1], [1.5], [True], ["5"], []])
def test_power_curve_durations_are_positive_integers(
    monkeypatch: pytest.MonkeyPatch, durations: list[Any]
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return {"list": []}

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete", durations=durations, this_season=True, last_season=False
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_DURATIONS"
    assert calls == []


def test_power_curves_are_missing_per_curve_and_can_return_raw_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "list": [
            {
                "id": "a",
                "label": "Curve A",
                "start_date_local": "2026-01-01",
                "end_date_local": "2026-06-01",
                "filter_label": "indoor",
                "weight": 80,
                "moving_time": 123,
                "secs": [5, 60],
                "values": [0, None],
                "activity_id": ["zero", None],
                "watts_per_kg": [0, None],
                "wkg_activity_id": ["zero-wkg", None],
                "future_field": {"preserve": True},
            },
            {
                "id": "b",
                "label": "Curve B",
                "secs": [5],
                "values": [300],
                "activity_id": ["b5"],
            },
        ]
    }
    _patch_request(monkeypatch, "power_curves", payload)
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete",
            durations=[5, 60],
            this_season=True,
            last_season=False,
            detail="full",
        )
    )
    assert result.status == "partial"
    curves = result.data["curves"]
    assert curves[0]["missing_durations"] == [60]
    assert curves[1]["missing_durations"] == [60]
    assert result.data["missing_durations"] == [60]
    assert [point["watts"] for point in curves[0]["data_points"]] == [0, None]
    assert curves[0]["filter_label"] == "indoor"
    assert curves[0]["future_field"] == {"preserve": True}
    assert curves[0]["raw"] == payload["list"][0]
    assert result.coverage.source_complete_within_query is None
    assert "MISSING_DURATION" in result.warnings


def test_power_curves_keep_aligned_prefix_when_series_is_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "power_curves",
        {"list": [{"secs": [5, 60], "values": [100]}]},
    )
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete", durations=[5], this_season=True, last_season=False
        )
    )
    assert result.status == "partial"
    assert result.error is None
    curve = result.data["curves"][0]
    assert curve["data_points"] == [
        {
            "secs": 5,
            "watts": 100,
            "activity_id": None,
            "watts_per_kg": None,
            "wkg_activity_id": None,
        }
    ]
    assert curve["missing_durations"] == [60]
    assert "SERIES_LENGTH_MISMATCH" in result.warnings


@pytest.mark.parametrize("bad_value", [True, "200", {"watts": 200}])
def test_power_curves_reject_non_numeric_watts(
    monkeypatch: pytest.MonkeyPatch, bad_value: Any
) -> None:
    _patch_request(
        monkeypatch,
        "power_curves",
        {"list": [{"secs": [5], "values": [bad_value]}]},
    )
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete", durations=[5], this_season=True, last_season=False
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_power_query_retains_period_selectors_and_compact_alignment_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return {
            "list": [
                {
                    "id": "range",
                    "secs": [5, 60],
                    "values": [100, 200],
                    "start_index": [10, 11],
                    "end_index": [20, 21],
                }
            ]
        }

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    compact = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete",
            durations=[5],
            this_season=False,
            last_season=False,
            start_date="2026-01-01",
            end_date="2026-02-01",
        )
    )
    query = compact.query.model_dump()
    assert query["this_season"] is False
    assert query["last_season"] is False
    assert query["start_date"] == "2026-01-01"
    assert query["end_date"] == "2026-02-01"
    assert query["curves"] == ["r.2026-01-01.2026-02-01"]
    assert compact.data["curves"][0]["data_points"][0]["start_index"] == 10
    assert compact.data["curves"][0]["data_points"][0]["end_index"] == 20
    assert captured["params"]["curves"] == ["r.2026-01-01.2026-02-01"]


def test_power_full_retains_alignment_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "list": [
            {
                "id": "range",
                "secs": [5],
                "values": [100],
                "start_index": [10],
                "end_index": [20],
            }
        ]
    }
    _patch_request(monkeypatch, "power_curves", payload)
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete",
            durations=[5],
            this_season=True,
            last_season=False,
            detail="full",
        )
    )
    assert result.data["curves"][0]["raw"] == payload["list"][0]


def test_athlete_power_compact_omits_large_arrays_with_full_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "list": [
            {
                "id": "s0",
                "secs": [5],
                "values": [100],
                "start_index": [3],
                "end_index": [4],
                "submax_values": [[90]],
                "future_object": {"keep": True},
            }
        ]
    }
    _patch_request(monkeypatch, "power_curves", payload)

    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete", durations=[5], this_season=True, last_season=False
        )
    )

    curve = result.data["curves"][0]
    assert curve["data_points"][0]["start_index"] == 3
    assert curve["data_points"][0]["end_index"] == 4
    assert "submax_values" in curve["omitted_fields"]
    assert "future_object" in curve["omitted_fields"]
    assert curve["full_read"]["parameters"]["detail"] == "full"


def test_athlete_power_full_keeps_large_raw_arrays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "list": [
            {
                "id": "s0",
                "secs": [5],
                "values": [100],
                "submax_values": [[90]],
                "future_object": {"keep": True},
            }
        ]
    }
    _patch_request(monkeypatch, "power_curves", payload)

    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="athlete",
            durations=[5],
            this_season=True,
            last_season=False,
            detail="full",
        )
    )

    assert result.data["curves"][0]["raw"] == payload["list"][0]


@pytest.mark.parametrize("payload", [None, "not-an-event-list", {}, {"events": []}, [{"id": 1}, "bad"]])
def test_events_reject_uninterpretable_list_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "events", payload)
    result = asyncio.run(
        get_events(
            athlete_id="athlete",
            start_date="2026-01-01",
            end_date_exclusive="2026-01-02",
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_event_by_id_preserves_not_found_and_rejects_wrong_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "events", {})
    missing = asyncio.run(get_event_by_id(1, athlete_id="athlete"))
    assert missing.error is not None
    assert missing.error.code == "NOT_FOUND"

    _patch_request(monkeypatch, "events", [])
    result = asyncio.run(get_event_by_id(1, athlete_id="athlete"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_read_errors_preserve_recommended_action(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_request(
        monkeypatch,
        "events",
        {
            "error": True,
            "code": "HTTP_429",
            "message": "slow down",
            "recommended_action": "retry after backoff",
        },
    )
    result = asyncio.run(
        get_events(
            athlete_id="athlete",
            start_date="2026-01-01",
            end_date_exclusive="2026-01-02",
        )
    )
    assert result.error is not None
    assert result.error.recommended_action == "retry after backoff"


@pytest.mark.parametrize("payload", [None, "bad", {"unexpected": []}, [{"id": 1}, "bad"]])
def test_activity_list_rejects_uninterpretable_payloads(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "activities", payload)
    result = asyncio.run(get_activities(athlete_id="athlete"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_hidden_activity_without_sport_survives_sport_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hidden = {
        "id": "hidden",
        "source": "STRAVA",
        "name": "Hidden",
        "_note": "restricted by source",
        "start_date_local": "2026-09-08T07:30:00",
    }
    _patch_request(monkeypatch, "activities", [hidden])
    result = asyncio.run(
        get_activities(
            athlete_id="athlete",
            sports=["Ride"],
            start_date="2026-09-08",
            end_date_exclusive="2026-09-09",
        )
    )
    assert result.status == "partial"
    assert result.data == [hidden]
    assert result.coverage.reasons == [
        "upstream_completeness_unverified",
        "source_record_hidden",
        "sport_filter_unverified",
    ]
    assert result.warnings == ["SOURCE_DATA_LIMITED", "SPORT_FILTER_UNVERIFIED"]
    assert result.model_dump()["limitations"][-1]["code"] == "SPORT_FILTER_UNVERIFIED"


def test_activity_details_does_not_select_first_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "activities", [{"id": "first"}, {"id": "second"}])
    result = asyncio.run(get_activity_details("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_activity_details_rejects_meaningless_nonempty_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "activities", {"unexpected": []})

    result = asyncio.run(get_activity_details("activity"))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"icu_intervals": "bad"},
        {"icu_intervals": None, "icu_groups": None},
        {"icu_intervals": [], "icu_groups": "bad"},
        {"icu_intervals": [], "icu_groups": [None]},
        [{"id": 1}, "bad"],
    ],
)
def test_activity_intervals_reject_bad_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "activities", payload)
    result = asyncio.run(get_activity_intervals("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_activity_intervals_preserves_nullable_groups_from_live_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "id": "activity",
        "analyzed": "2026-09-09T20:00:00Z",
        "icu_intervals": [{"id": 1, "start_index": 0, "end_index": 60}],
        "icu_groups": None,
    }
    _patch_request(monkeypatch, "activities", payload)

    result = asyncio.run(get_activity_intervals("activity"))

    assert result.status == "ok"
    assert result.error is None
    assert result.data == payload
    assert result.data["icu_groups"] is None


@pytest.mark.parametrize("payload", [None, {}, [{"id": 1}, "bad"]])
def test_activity_messages_reject_bad_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "activities", payload)
    result = asyncio.run(get_activity_messages("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize("payload", [None, "bad", {"2026-01-01": "bad"}, {"not-a-date": {}} , [{"date": "2026-01-01"}, "bad"]])
def test_wellness_rejects_uninterpretable_payloads(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "wellness", payload)
    result = asyncio.run(get_wellness_data(athlete_id="athlete"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize("payload", [None, "bad", {}, [{"type": "watts"}, "bad"]])
def test_streams_reject_uninterpretable_top_level_or_members(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    result = _run_stream(monkeypatch, payload, stream_types="watts")
    if payload == {}:
        # An empty object is a malformed stream response, unlike a valid empty list.
        assert result.status == "error"
    else:
        assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize(
    "stream",
    [{"type": "watts", "data": "bad"}, {"type": "watts", "data2": "bad"}],
)
def test_streams_reject_wrong_type_arrays(
    monkeypatch: pytest.MonkeyPatch, stream: dict[str, Any]
) -> None:
    result = _run_stream(monkeypatch, [stream], stream_types="watts")
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_streams_keep_missing_and_null_primary_data_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_stream(
        monkeypatch,
        [
            {"type": "watts", "data2": [100, 101]},
            {"type": "cadence", "data": None, "data2": None},
        ],
        mode="range",
        start_index=0,
        end_index=2,
        stream_types="watts,cadence",
    )
    watts, cadence = result.data["streams"]
    assert "data" not in watts
    assert watts["data2"] == [100, 101]
    assert cadence["data"] is None and cadence["data2"] is None
    assert watts["data_state"] == "missing"
    assert cadence["data_state"] == "null"
    assert result.status == "partial"
    assert "TIME_AXIS_UNAVAILABLE" in result.warnings


def test_complete_range_without_optional_data2_is_not_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_stream(
        monkeypatch,
        [
            {"type": "time", "data": [0, 1]},
            {"type": "watts", "data": [200, 201]},
        ],
        mode="range",
        start_index=0,
        end_index=2,
        stream_types="time,watts",
    )
    assert result.status == "ok"
    assert result.coverage.response_complete is True
    assert result.coverage.truncated is False
    assert all("data2_missing_indices" not in row for row in result.data["streams"])


@pytest.mark.parametrize("bad_index", [True, "0", 0.0])
def test_stream_range_indices_require_strict_integers(
    monkeypatch: pytest.MonkeyPatch, bad_index: Any
) -> None:
    calls: list[bool] = []

    async def fake(**_kwargs: Any) -> Any:
        calls.append(True)
        return [{"type": "time", "data": [0]}]

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    result = asyncio.run(
        get_activity_streams(
            "activity", mode="range", start_index=bad_index, end_index=1  # type: ignore[arg-type]
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_RANGE"
    assert calls == []


def test_short_stream_preview_is_not_marked_truncated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _run_stream(
        monkeypatch,
        [{"type": "watts", "data": [0, None, 0]}],
        stream_types="watts",
    )
    assert result.coverage.truncated is False
    assert "preview" not in result.coverage.reasons


def test_export_rejects_bad_stream_or_interval_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return None if calls == 1 else {}

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    result = asyncio.run(export_activity_data("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"

    calls = 0

    async def streams_then_bad_intervals(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return [] if calls == 1 else None

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request",
        streams_then_bad_intervals,
    )
    result = asyncio.run(export_activity_data("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"
