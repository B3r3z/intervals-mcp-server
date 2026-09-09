import asyncio
import json
from intervals_mcp_server.tools.power_curves import get_athlete_power_curves


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
