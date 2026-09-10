import asyncio
import json
from typing import Any

import pytest

from intervals_mcp_server.tools import power_curves
from intervals_mcp_server.tools.power_curves import DEFAULT_DURATIONS, get_athlete_power_curves


@pytest.mark.asyncio
async def test_activity_watts_only_projection_preserves_original_evidence(monkeypatch):
    from copy import deepcopy
    from intervals_mcp_server.tools.power_curves import get_activity_power_curves

    source = {
        "id": "normal", "fatigue": "normal", "stream_type": "watts",
        "secs": [60, 300], "watts": [0, 250],
        "start_index": [0, 100], "end_index": [60, 400],
        "future_metadata": {"quality": [1, None]},
    }
    original = deepcopy(source)

    async def request(**_kwargs):
        return [source]

    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", request)
    full = await get_activity_power_curves("curve-fixture", durations=[60, 300], detail="full")
    compact = await get_activity_power_curves("curve-fixture", durations=[300], detail="compact")
    full_curve, compact_curve = full.data["curves"][0], compact.data["curves"][0]
    assert full_curve["raw"] == original
    assert source == original
    assert [point["watts"] for point in full_curve["data_points"]] == [0, 250]
    assert compact_curve["data_points"][0]["watts"] == 250
    assert "watts" in compact_curve["omitted_fields"]
    assert "values" not in compact_curve["omitted_fields"]


def test_power_curve_precision_and_ids(monkeypatch):
    async def fake(**_):
        return {"list": [{"id": "s0", "secs": [5], "values": [321], "watts_per_kg": [3.14159], "activity_id": ["a"], "wkg_activity_id": ["wa"]}]}
    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", fake)
    result = asyncio.run(get_athlete_power_curves(athlete_id="a", durations=[5]))
    point = result.data["curves"][0]["data_points"][0]
    assert point["watts_per_kg"] == 3.14159 and point["activity_id"] == "a" and point["wkg_activity_id"] == "wa"


def test_power_curve_empty_and_missing(monkeypatch):
    async def fake(**_): return {"list": []}
    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", fake)
    result = asyncio.run(get_athlete_power_curves(athlete_id="a", durations=[5]))
    assert result.status == "ok" and result.data["curves"] == []


def test_power_curve_missing_duration_warning(monkeypatch):
    async def fake(**_): return {"list": [{"id": "s", "secs": [5], "values": [100]}]}
    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", fake)
    result = asyncio.run(get_athlete_power_curves(athlete_id="a", durations=[5, 60]))
    assert result.data["missing_durations"] == [60] and "MISSING_DURATION" in result.warnings


def test_power_curve_applies_indoor_filter_and_preserves_missing_ids(monkeypatch):
    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return {"list": [{"secs": [5], "values": [100], "watts_per_kg": [2.5]}]}

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        get_athlete_power_curves(
            athlete_id="a", durations=[5], indoor_outdoor="indoor"
        )
    )

    filters = json.loads(captured["params"]["filters"])
    assert filters == [{"field_id": "indoor", "value": "indoor", "id": 1}]
    curve = result.data["curves"][0]
    point = curve["data_points"][0]
    assert curve["id"] is None
    assert point["activity_id"] is None
    assert point["wkg_activity_id"] is None


def test_power_curve_invalid_requests_do_not_call_http(monkeypatch):
    calls = []
    async def fake(**_):
        calls.append(1)
        return {"list": []}
    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", fake)
    assert asyncio.run(get_athlete_power_curves(athlete_id="a", indoor_outdoor="other")).status == "error"
    assert asyncio.run(get_athlete_power_curves(athlete_id="a", this_season=False, last_season=False)).status == "error"
    assert not calls


def test_power_curve_upstream_error(monkeypatch):
    async def fake(**_): return {"error": True, "code": "HTTP_502", "phase": "response", "http_status": 502, "message": "bad"}
    monkeypatch.setattr("intervals_mcp_server.tools.power_curves.make_intervals_request", fake)
    result = asyncio.run(get_athlete_power_curves(athlete_id="a"))
    assert result.status == "error" and result.error.code == "HTTP_502" and result.error.http_status == 502


def test_activity_power_curves_compact_preserves_alignment_and_selection(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return [
            {
                "id": "curve-1",
                "stream_type": "watts",
                "fatigue": "normal",
                "after_kj": 0,
                "secs": [5, 60],
                "values": [0, None],
                "start_index": [10, 20],
                "end_index": [11, 21],
                "wkg_activity_id": ["a-zero", None],
                "submax_values": [[1], [2]],
                "future_scalar": "preserve",
            }
        ]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves(
            "activity",
            durations=[5, 60],
            fatigue=["normal", "kj0"],
        )
    )

    assert captured["url"] == "/activity/activity/power-curves"
    assert captured["params"] == {"types": "watts", "fatigue": "kj0"}
    curve = result.data["curves"][0]
    assert curve["data_points"] == [
        {
            "secs": 5,
            "watts": 0,
            "activity_id": None,
            "start_index": 10,
            "end_index": 11,
            "wkg_activity_id": "a-zero",
        },
        {
            "secs": 60,
            "watts": None,
            "activity_id": None,
            "start_index": 20,
            "end_index": 21,
            "wkg_activity_id": None,
        },
    ]
    assert curve["missing_durations"] == [60]
    assert curve["future_scalar"] == "preserve"
    assert "submax_values" in curve["omitted_fields"]
    assert result.data["selection"]["requested_fatigue"] == ["normal", "kj0"]


def test_activity_power_curves_default_durations_are_reported(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return [{"stream_type": "watts", "secs": [5], "values": [200]}]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(power_curves.get_activity_power_curves("activity"))

    assert captured["params"] == {"types": "watts", "fatigue": "normal"}
    assert result.query.model_dump()["durations"] == list(DEFAULT_DURATIONS)
    assert result.data["curves"][0]["missing_durations"] == list(DEFAULT_DURATIONS[1:])


def test_activity_power_curves_empty_list_is_valid_empty(monkeypatch) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return []

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves("activity", durations=[5])
    )

    assert result.status == "ok"
    assert result.data["curves"] == []
    assert result.data["selection"]["verified"] is None
    assert result.warnings == []


def test_activity_power_curves_alignment_mismatch_and_reversal_are_partial(
    monkeypatch,
) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return [
            {
                "stream_type": "watts",
                "secs": [5, 60],
                "values": [200, 210],
                "start_index": [2],
                "end_index": [1],
            }
        ]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves("activity", durations=[5, 60])
    )

    assert result.status == "partial"
    assert "SERIES_LENGTH_MISMATCH" in result.warnings
    assert "INCONSISTENT_BOUNDS" in result.warnings
    assert result.data["curves"][0]["data_points"][1]["start_index"] is None


@pytest.mark.parametrize(
    "payload",
    [
        [{"stream_type": "heartrate", "secs": [5], "values": [160]}],
        [{"stream_type": "watts", "secs": [5], "values": [200], "after_kj": "bad"}],
    ],
)
def test_activity_power_curves_rejects_wrong_stream_or_threshold_shape(
    monkeypatch, payload: Any
) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves("activity", durations=[5])
    )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_activity_power_curves_full_preserves_raw_curve(
    monkeypatch,
) -> None:
    payload = [
        {
            "stream_type": "watts",
            "secs": [5],
            "values": [200],
            "submax_values": [[190]],
            "unknown_future": {"value": 1},
        }
    ]

    async def fake(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves(
            "activity", durations=[5], detail="full"
        )
    )

    assert result.data["curves"][0]["raw"] == payload[0]
    assert result.data["curves"][0]["raw"]["unknown_future"] == {"value": 1}


@pytest.mark.parametrize(
    "kwargs",
    [
        {"durations": []},
        {"durations": [True]},
        {"durations": ["5"]},
        {"durations": [0]},
        {"fatigue": []},
        {"fatigue": ["invalid"]},
    ],
)
def test_activity_power_curves_rejects_invalid_selectors_before_http(
    monkeypatch, kwargs: dict[str, Any]
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake(**request: Any) -> Any:
        calls.append(request)
        return []

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(power_curves.get_activity_power_curves("activity", **kwargs))

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code in {"INVALID_DURATIONS", "INVALID_FATIGUE"}
    assert calls == []


def test_activity_power_curves_marks_missing_fatigue_threshold(
    monkeypatch,
) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return [{"stream_type": "watts", "fatigue": "kj0", "secs": [5], "values": [200]}]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.power_curves.make_intervals_request", fake
    )
    result = asyncio.run(
        power_curves.get_activity_power_curves(
            "activity", durations=[5], fatigue=["kj0"]
        )
    )

    assert result.status == "partial"
    assert "FATIGUE_THRESHOLD_UNAVAILABLE" in result.warnings
    assert "fatigue_threshold_unavailable" in result.coverage.reasons
