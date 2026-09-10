from __future__ import annotations

import asyncio
import math
from typing import Any

import pytest

from intervals_mcp_server.tools import analytics


def _patch_request(monkeypatch: pytest.MonkeyPatch, module: str, value: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return value

    monkeypatch.setattr("intervals_mcp_server.tools.analytics.make_intervals_request", fake)
    return calls


def test_interval_stats_preserves_raw_interval_and_reports_sample_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interval = {
        "start_index": 12,
        "end_index": 42,
        "average_watts": 0,
        "average_heartrate": None,
        "future_metric": {"value": 7},
    }
    calls = _patch_request(monkeypatch, "analytics", interval)

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 10, 40))

    assert result.status == "partial"
    assert result.data == interval
    assert result.data["average_watts"] == 0
    assert result.data["average_heartrate"] is None
    assert calls[0]["url"] == "/activity/activity/interval-stats"
    assert calls[0]["params"] == {"start_index": 10, "end_index": 40}
    assert result.model_dump()["bounds"] == {
        "requested": {"start_index": 10, "end_index": 40},
        "returned": {"start_index": 12, "end_index": 42},
        "matched": False,
    }
    assert result.model_dump()["provenance"] == {
        "origin": "upstream intervals.icu",
        "mcp_numeric_calculations": [],
    }
    assert result.model_dump()["units"]["index"] == "sample_index"
    assert result.model_dump()["units"]["average_watts"] == "W"
    assert result.model_dump()["units"]["average_heartrate"] == "bpm"
    assert result.model_dump()["units"]["joules"] == "J"
    assert result.model_dump()["units"]["average_watts_kg"] == "W/kg"
    assert result.model_dump()["follow_up"]["tool"] == "get_activity_streams"
    assert result.model_dump()["follow_up"]["parameters"]["start_index"] == 10
    assert "RETURNED_BOUNDS_MISMATCH" in result.warnings


@pytest.mark.parametrize(
    "start_index,end_index",
    [(True, 2), ("0", 2), (0.0, 2), (0, True), (0, "2"), (0, 2.0), (-1, 2), (2, 2), (3, 2)],
)
def test_interval_stats_rejects_invalid_sample_bounds_before_http(
    monkeypatch: pytest.MonkeyPatch, start_index: Any, end_index: Any
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {})

    result = asyncio.run(analytics.get_activity_interval_stats("activity", start_index, end_index))  # type: ignore[arg-type]

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_RANGE"
    assert calls == []


@pytest.mark.parametrize("payload", [None, [], "bad", {"interval": []}])
def test_interval_stats_rejects_uninterpretable_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "analytics", payload)

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_interval_stats_empty_object_is_explicit_missing_stats(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "analytics", {})

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "partial"
    assert result.data == {}
    assert result.warnings == ["NO_INTERVAL_STATS"]
    assert result.coverage.reasons == ["NO_INTERVAL_STATS"]
    assert result.data != {"average_watts": 0}


def test_interval_stats_without_returned_bounds_is_partial_with_unknown_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "analytics", {"joules": 1000})

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "partial"
    assert result.data == {"joules": 1000}
    assert result.model_dump()["bounds"]["matched"] is None
    assert "RETURNED_BOUNDS_UNAVAILABLE" in result.warnings


def test_interval_stats_null_returned_bounds_are_partial_with_unknown_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {"start_index": None, "end_index": None, "joules": 1000},
    )

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "partial"
    assert result.model_dump()["bounds"]["matched"] is None
    assert "RETURNED_BOUNDS_UNAVAILABLE" in result.warnings


def test_interval_stats_accepts_numeric_training_load_only_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(monkeypatch, "analytics", {"training_load": 5})

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "partial"
    assert result.data == {"training_load": 5}
    assert result.model_dump()["bounds"]["matched"] is None


@pytest.mark.parametrize("field", ["average_watts", "average_heartrate", "joules"])
@pytest.mark.parametrize("bad_value", [True, "bad", {"value": 1}])
def test_interval_stats_rejects_wrong_numeric_field_types(
    monkeypatch: pytest.MonkeyPatch, field: str, bad_value: Any
) -> None:
    _patch_request(monkeypatch, "analytics", {field: bad_value})

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


@pytest.mark.parametrize("function", ["interval", "efforts"])
def test_analytics_rejects_empty_activity_id_before_http(
    monkeypatch: pytest.MonkeyPatch, function: str
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {"efforts": []})
    if function == "interval":
        result = asyncio.run(analytics.get_activity_interval_stats("", 0, 2))
    else:
        result = asyncio.run(
            analytics.get_activity_best_efforts("", "watts", duration=60)
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_ACTIVITY_ID"
    assert calls == []


def test_interval_stats_upstream_error_keeps_recommended_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {
            "error": True,
            "code": "HTTP_429",
            "message": "slow down",
            "phase": "http",
            "http_status": 429,
            "recommended_action": "retry after backoff",
        },
    )

    result = asyncio.run(analytics.get_activity_interval_stats("activity", 0, 2))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "HTTP_429"
    assert result.error.recommended_action == "retry after backoff"


def test_best_efforts_maps_query_and_preserves_null_average_and_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "efforts": [
            {
                "start_index": 20,
                "end_index": 80,
                "average": None,
                "duration": 60,
                "distance": 900.5,
                "future_field": "keep",
            }
        ],
        "source_note": "synthetic",
    }
    calls = _patch_request(monkeypatch, "analytics", payload)

    result = asyncio.run(
        analytics.get_activity_best_efforts(
            "activity",
            "watts",
            duration=60,
            count=3,
            min_value=200,
            exclude_intervals=True,
            start_index=10,
            end_index=100,
        )
    )

    assert result.status == "partial"
    assert result.data == payload
    assert result.data["efforts"][0]["average"] is None
    assert result.data["efforts"][0]["future_field"] == "keep"
    assert result.model_dump()["units"]["average"] == "W"
    assert result.model_dump()["provenance"] == {
        "origin": "upstream intervals.icu",
        "mcp_numeric_calculations": [],
    }
    assert result.model_dump()["missing"] == [{"effort_index": 0, "field": "average", "reason": "UPSTREAM_NULL"}]
    assert result.model_dump()["bounds"]["requested"] == {"start_index": 10, "end_index": 100}
    assert result.model_dump()["bounds"]["returned"] == [{"start_index": 20, "end_index": 80}]
    assert calls[0]["url"] == "/activity/activity/best-efforts"
    assert calls[0]["params"] == {
        "stream": "watts",
        "duration": 60,
        "count": 3,
        "minValue": 200,
        "excludeIntervals": True,
        "startIndex": 10,
        "endIndex": 100,
    }


def test_best_efforts_distance_selector_and_unknown_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {"efforts": []})

    result = asyncio.run(
        analytics.get_activity_best_efforts(
            "activity", "custom_stream", distance=123.5, end_index=None
        )
    )

    assert result.status == "ok"
    assert result.data == {"efforts": []}
    assert result.coverage.source_complete_within_query is None
    assert result.model_dump()["units"]["average"] == "unknown"
    assert calls[0]["params"] == {
        "stream": "custom_stream",
        "distance": 123.5,
        "count": 8,
        "excludeIntervals": False,
        "startIndex": 0,
    }
    assert "endIndex" not in calls[0]["params"]


def test_best_efforts_preserves_explicit_upstream_whole_stream_sentinel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {"efforts": []})

    result = asyncio.run(
        analytics.get_activity_best_efforts(
            "activity", "watts", duration=60, end_index=0
        )
    )

    assert result.status == "ok"
    assert calls[0]["params"]["endIndex"] == 0


def test_best_efforts_null_bounds_are_explicit_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {"efforts": [{"start_index": None, "end_index": None, "average": 200}]},
    )

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", duration=60))

    assert result.status == "partial"
    assert "EFFORT_BOUNDS_UNAVAILABLE" in result.warnings
    assert result.model_dump()["bounds"]["returned"] == [{"start_index": None, "end_index": None}]


@pytest.mark.parametrize(
    "payload",
    [
        {"efforts": [{"start_index": -1, "end_index": 2}]},
        {"efforts": [{"start_index": 3, "end_index": 2}]},
        {"efforts": [{"duration": -1}]},
        {"efforts": [{"distance": -1.0}]},
    ],
)
def test_best_efforts_rejects_non_physical_returned_efforts(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]
) -> None:
    _patch_request(monkeypatch, "analytics", payload)

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", duration=60))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_best_efforts_reports_bounds_outside_requested_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {"efforts": [{"start_index": 0, "end_index": 12, "average": 200}]},
    )

    result = asyncio.run(
        analytics.get_activity_best_efforts(
            "activity", "watts", duration=60, start_index=2, end_index=10
        )
    )

    assert result.status == "partial"
    assert "EFFORT_BOUNDS_OUTSIDE_REQUEST" in result.warnings


@pytest.mark.parametrize("requested_end", [None, 0])
def test_best_efforts_reports_lower_bound_outside_open_ended_request(
    monkeypatch: pytest.MonkeyPatch, requested_end: int | None
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {"efforts": [{"start_index": 3, "end_index": 8, "average": 200}]},
    )

    result = asyncio.run(
        analytics.get_activity_best_efforts(
            "activity",
            "watts",
            duration=60,
            start_index=5,
            end_index=requested_end,
        )
    )

    assert result.status == "partial"
    assert "EFFORT_BOUNDS_OUTSIDE_REQUEST" in result.warnings


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"duration": 60, "distance": 100.0},
        {"duration": 0},
        {"duration": True},
        {"duration": "60"},
        {"distance": 0.0},
        {"distance": -1.0},
        {"distance": math.inf},
        {"distance": True},
        {"distance": "100"},
    ],
)
def test_best_efforts_requires_exactly_one_valid_selector_before_http(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {"efforts": []})

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", **kwargs))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_SELECTOR"
    assert calls == []


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration": 60, "count": 0},
        {"duration": 60, "count": 101},
        {"duration": 60, "count": True},
        {"duration": 60, "count": "8"},
        {"duration": 60, "min_value": math.inf},
        {"duration": 60, "min_value": True},
        {"duration": 60, "min_value": "200"},
        {"duration": 60, "start_index": True},
        {"duration": 60, "start_index": "0"},
        {"duration": 60, "end_index": True},
    ],
)
def test_best_efforts_rejects_invalid_count_values_and_indices_before_http(
    monkeypatch: pytest.MonkeyPatch, kwargs: dict[str, Any]
) -> None:
    calls = _patch_request(monkeypatch, "analytics", {"efforts": []})

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", **kwargs))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code in {"INVALID_COUNT", "INVALID_VALUE", "INVALID_RANGE"}
    assert calls == []


@pytest.mark.parametrize("payload", [None, [], "bad", {}, {"efforts": None}, {"efforts": [1]}])
def test_best_efforts_rejects_malformed_response_shapes(
    monkeypatch: pytest.MonkeyPatch, payload: Any
) -> None:
    _patch_request(monkeypatch, "analytics", payload)

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", duration=60))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_best_efforts_upstream_error_keeps_recommended_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_request(
        monkeypatch,
        "analytics",
        {
            "error": True,
            "code": "HTTP_503",
            "message": "unavailable",
            "phase": "http",
            "http_status": 503,
            "recommended_action": "retry read",
        },
    )

    result = asyncio.run(analytics.get_activity_best_efforts("activity", "watts", duration=60))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "HTTP_503"
    assert result.error.recommended_action == "retry read"
