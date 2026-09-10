"""Respiratory documentation must not become a unit conversion or source claim."""

from copy import deepcopy

import pytest

from intervals_mcp_server.contracts import success
from intervals_mcp_server.respiratory import respiratory_guidance
from intervals_mcp_server.tools import activities, analytics, quality
from intervals_mcp_server.tools.metrics import get_metric_definitions


def assert_conditional_documentation(guidance):
    assert guidance["device_source_verified_by_mcp"] is False
    assert guidance["automatic_conversion_applied"] is False
    assert guidance["raw_volume_to_liters_factor"] is None
    assert guidance["applies_when"]
    assert guidance["primary_links"]


def test_guidance_selects_present_fields_without_identifying_unknown_fields():
    fields = {"tidal_volume": None, "TymeVentilation": 0, "future_volume": 186}
    guidance = respiratory_guidance(fields)

    assert_conditional_documentation(guidance)
    assert set(guidance["fields"]) == {"tidal_volume", "TymeVentilation"}
    assert guidance["fields"]["tidal_volume"]["metric"] == "tidal_volume"
    assert guidance["fields"]["TymeVentilation"]["metric"] == "tidal_volume_min"
    assert respiratory_guidance(["future_volume", "VT1", "VT2"]) == {}
    assert respiratory_guidance([]) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("secondary", [None, [186, 0, None]])
@pytest.mark.parametrize("unit_metadata", [{}, {"unit": None}, {"unit": "L/br"}])
async def test_stream_guidance_preserves_raw_values_and_upstream_unit_declarations(
    monkeypatch, secondary, unit_metadata
):
    source = [
        {"type": "time", "data": [0, 1, 2], "data2": None},
        {
            "type": "tidal_volume", "data": [186, 0, None], "data2": secondary,
            "future_record_metadata": {"value": None, "factor": 0}, **unit_metadata,
        },
        {"type": "future_volume", "data": [900, 0, None], "data2": None},
    ]
    original = deepcopy(source)

    async def request(**_kwargs):
        return source

    monkeypatch.setattr(activities, "make_intervals_request", request)
    result = await activities.get_activity_streams(
        "activity", mode="range", start_index=0, end_index=3,
        stream_types="time,tidal_volume,future_volume",
    )

    assert result.status == "ok"
    rows = {row["type"]: row for row in result.data["streams"]}
    assert rows["tidal_volume"]["data"] == [186, 0, None]
    assert rows["tidal_volume"]["data2"] == secondary
    assert rows["tidal_volume"]["unit"] == unit_metadata.get("unit")
    assert rows["tidal_volume"]["future_record_metadata"] == {"value": None, "factor": 0}
    assert rows["future_volume"]["data"] == [900, 0, None]
    guidance = result.provenance["respiratory_interpretation"]
    assert_conditional_documentation(guidance)
    assert set(guidance["fields"]) == {"tidal_volume"}
    assert source == original


@pytest.mark.asyncio
async def test_interval_averages_remain_upstream_values_including_null_and_zero(monkeypatch):
    source = {
        "start_index": 0, "end_index": 3,
        "average_tidal_volume": 186,
        "average_tidal_volume_min": 0,
        "average_respiration": None,
        "future_average_volume": {"value": 186, "unit": "L/br"},
    }
    original = deepcopy(source)

    async def request(**_kwargs):
        return source

    monkeypatch.setattr(analytics, "make_intervals_request", request)
    result = await analytics.get_activity_interval_stats("activity", 0, 3)

    assert result.status == "ok"
    assert result.data == original == source
    guidance = result.provenance["respiratory_interpretation"]
    assert_conditional_documentation(guidance)
    assert set(guidance["fields"]) == {
        "average_tidal_volume", "average_tidal_volume_min", "average_respiration",
    }
    assert result.provenance["mcp_numeric_calculations"] == []


@pytest.mark.asyncio
async def test_quality_counts_device_volume_values_without_a_physiological_range_error(monkeypatch):
    source = [
        {"type": "time", "data": [0, 1, 2], "data2": None},
        {"type": "tidal_volume", "data": [186, 0, None], "data2": None, "unit": "L/br"},
    ]
    original = deepcopy(source)

    async def request(**_kwargs):
        return source

    async def details(*_args, **_kwargs):
        return success({"id": "activity"}, resource="activity")

    monkeypatch.setattr(quality, "make_intervals_request", request)
    monkeypatch.setattr(quality, "get_activity_details", details)
    result = await quality.get_activity_data_quality("activity")

    assert result.status == "ok"
    row = next(row for row in result.data["stream_quality"]["streams"] if row["type"] == "tidal_volume")
    counts = row["arrays"]["data"]
    assert counts["finite_count"] == 2
    assert counts["zero_count"] == counts["null_count"] == 1
    assert counts["invalid_count"] == 0
    assert row["unit"] == "L/br"
    guidance = result.provenance["respiratory_interpretation"]
    assert_conditional_documentation(guidance)
    assert set(guidance["fields"]) == {"tidal_volume"}
    assert source == original


@pytest.mark.asyncio
async def test_metric_aliases_share_definitions_without_claiming_thresholds_or_absolute_volume():
    result = await get_metric_definitions(
        names=["VT", "MeanVT", "VE", "TymeVentilation", "BR", "TymeBreathRate", "VT1", "VT2"],
        fields=["tidal_volume", "tyme_tidal_volume", "average_tidal_volume",
                "tidal_volume_min", "tyme_minute_volume", "average_tidal_volume_min",
                "respiration", "tyme_breath_rate", "average_respiration"],
    )

    assert result.status == "partial"
    definitions = result.data["definitions"]
    assert len(definitions) == 3
    by_name = {item["name"]: item for item in definitions}
    assert set(by_name) == {"tidal_volume", "tidal_volume_min", "respiration"}
    assert result.data["unknown_names"] == ["VT1", "VT2"]
    assert by_name["tidal_volume"]["unit"] == "unknown"
    assert by_name["tidal_volume_min"]["unit"] == "unknown"
    assert by_name["respiration"]["unit"] == "breaths/min"
    for name, definition in by_name.items():
        context = definition["device_context"]
        assert_conditional_documentation(context)
        assert set(context["fields"]) == {name}
