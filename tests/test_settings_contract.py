from __future__ import annotations

import asyncio
from typing import Any

import pytest

from intervals_mcp_server.tools import settings


def test_sport_settings_compact_units_and_current_scope(monkeypatch) -> None:
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return {
            "id": 7,
            "types": ["Ride"],
            "ftp": 250,
            "indoor_ftp": 240,
            "w_prime": 20_000,
            "after_kj0": 1500,
            "after_kj1": 3000,
            "lthr": 165,
            "hr_zones": [120, 145, 160, 175],
            "power_zones": [150, 200, 250, 300],
            "threshold_pace": 4.2,
            "pace_units": "MINS_KM",
            "pace_zones": [80.0, 90.0, 100.0],
            "load_order": "POWER_HR_PACE",
            "tiz_order": "POWER_HR_PACE",
            "custom_field_values": {"large": {"expression": "untrusted"}},
            "unknown_future": {"keep": True},
        }

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", fake)
    result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))

    assert captured["url"] == "/athlete/athlete/sport-settings/Ride"
    assert result.status == "ok"
    assert result.data["ftp"] == 250
    assert result.data["threshold_pace"] == 4.2
    assert result.model_dump()["units"]["ftp"] == "W"
    assert result.model_dump()["units"]["w_prime"] == "J"
    assert result.model_dump()["units"]["after_kj0"] == "kJ"
    assert result.model_dump()["units"]["threshold_pace"] == "m/s"
    assert result.model_dump()["units"]["pace_zones"] == "% threshold speed"
    assert result.model_dump()["provenance"]["scope"] == "current_at_fetch"
    assert "custom_field_values" in result.data["omitted_fields"]
    assert "unknown_future" in result.data["omitted_fields"]
    assert result.data["full_read"]["parameters"]["detail"] == "full"


def test_sport_settings_accepts_current_settings_id_and_full_raw(
    monkeypatch,
) -> None:
    payload = {"id": 17, "types": ["Ride"], "future": {"keep": True}}
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return payload

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", fake)
    result = asyncio.run(
        settings.get_sport_settings("17", athlete_id="athlete", detail="full")
    )

    assert captured["url"] == "/athlete/athlete/sport-settings/17"
    assert result.status == "ok"
    assert result.data == payload


def test_sport_settings_rejects_malformed_payload_and_blank_selector_before_http(
    monkeypatch,
) -> None:
    calls: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return []

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", fake)
    blank = asyncio.run(settings.get_sport_settings("", athlete_id="athlete"))
    assert blank.status == "error"
    assert blank.error is not None
    assert blank.error.code == "INVALID_SPORT"
    assert calls == []

    async def malformed(**_kwargs: Any) -> Any:
        return []

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", malformed)
    result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"


def test_sport_settings_distinguishes_empty_unknown_and_valid_unknown_fields(
    monkeypatch,
) -> None:
    async def empty(**_kwargs: Any) -> Any:
        return {}

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", empty)
    empty_result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))
    assert empty_result.status == "partial"
    assert empty_result.data["omitted_fields"] == []
    assert "NO_SPORT_SETTINGS" in empty_result.warnings

    async def unknown(**_kwargs: Any) -> Any:
        return {"unexpected": []}

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", unknown)
    unknown_result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))
    assert unknown_result.status == "error"
    assert unknown_result.error is not None
    assert unknown_result.error.code == "INVALID_UPSTREAM_RESPONSE"

    async def known_plus_unknown(**_kwargs: Any) -> Any:
        return {"ftp": 250, "unexpected": []}

    monkeypatch.setattr(
        "intervals_mcp_server.tools.settings.make_intervals_request", known_plus_unknown
    )
    valid_result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))
    assert valid_result.status == "ok"
    assert "unexpected" in valid_result.data["omitted_fields"]


@pytest.mark.parametrize("field", ["ftp", "threshold_pace"])
def test_sport_settings_rejects_wrong_known_numeric_types(monkeypatch, field: str) -> None:
    async def fake(**_kwargs: Any) -> Any:
        return {field: "bad"}

    monkeypatch.setattr("intervals_mcp_server.tools.settings.make_intervals_request", fake)
    result = asyncio.run(settings.get_sport_settings("Ride", athlete_id="athlete"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"
