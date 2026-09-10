import asyncio

from intervals_mcp_server.tools.metrics import get_metric_definitions


def test_metric_definitions_explain_core_units_origins_and_axes() -> None:
    result = asyncio.run(
        get_metric_definitions(
            names=[
                "watts",
                "raw_watts",
                "watts_per_kg",
                "normalized_power",
                "sample_index",
                "moving_time",
                "vo2max_5m",
                "vo2max",
                "kg_lifted",
            ]
        )
    )

    assert result.status == "ok"
    assert result.source.system == "intervals-mcp-server"
    definitions = {item["name"]: item for item in result.data["definitions"]}
    assert definitions["watts"]["unit"] == "W"
    assert definitions["watts"]["axis"] == "sample_index"
    assert definitions["watts"]["primary_tools"] == ["get_activity_streams", "get_activity_intervals", "get_activity_best_efforts"]
    assert all(link.startswith("https://forum.intervals.icu/") for link in definitions["watts"]["primary_links"])
    assert any("api-access-to-intervals-icu/609?page=7" in link for link in definitions["watts"]["primary_links"])
    assert any("server-side-data-model-for-scripts/25781/16" in link for link in definitions["sample_index"]["primary_links"])
    assert definitions["raw_watts"]["origin"] == "upstream_reported"
    assert definitions["watts_per_kg"]["unit"] == "W/kg"
    assert definitions["normalized_power"]["unit"] == "W"
    assert definitions["watts_per_kg"]["name"] != definitions["normalized_power"]["name"]
    assert definitions["sample_index"]["unit"] == "sample_index"
    assert definitions["moving_time"]["unit"] == "s"
    assert definitions["vo2max_5m"]["origin"] == "upstream_estimated"
    assert definitions["vo2max"]["origin"] == "unknown"
    assert "sets" in " ".join(definitions["kg_lifted"]["limitations"])


def test_metric_definitions_keep_unknown_selectors_explicit_and_support_fields() -> None:
    result = asyncio.run(
        get_metric_definitions(fields=["data2", "hr_load_type"], names=["future_metric"])
    )

    assert result.status == "partial"
    assert result.data["unknown_names"] == ["future_metric"]
    assert {item["name"] for item in result.data["definitions"]} == {
        "data2",
        "hr_load_type",
    }
    assert result.coverage.source_complete_within_query is None
    assert "UNKNOWN_METRIC_NAME" in result.warnings


def test_metric_definitions_resolve_raw_aliases_without_collapsing_context() -> None:
    result = asyncio.run(
        get_metric_definitions(
            names=["icu_weighted_avg_watts", "icu_ftp", "icu_pm_ftp", "ftp"]
        )
    )

    definitions = {item["name"]: item for item in result.data["definitions"]}
    assert set(definitions) == {"normalized_power", "activity_assigned_ftp", "eFTP", "ftp"}
    assert definitions["normalized_power"]["unit"] == "W"
    assert definitions["activity_assigned_ftp"]["origin"] == "upstream_reported"
    assert definitions["eFTP"]["origin"] == "upstream_estimated"
    assert definitions["ftp"]["axis"] == "context_dependent"

    all_definitions = asyncio.run(get_metric_definitions(names=["strain_score", "custom_metric"]))
    all_by_name = {item["name"]: item for item in all_definitions.data["definitions"]}
    assert any("three-dimensional-impulse-response-model" in link for link in all_by_name["strain_score"]["primary_links"])
    assert any("please-help-me-get-xss" in link for link in all_by_name["custom_metric"]["primary_links"])


def test_metric_definition_links_are_metric_specific() -> None:
    result = asyncio.run(
        get_metric_definitions(names=["normalized_power", "tss", "hrv", "strain_score"])
    )

    definitions = {item["name"]: item for item in result.data["definitions"]}
    assert definitions["normalized_power"]["primary_links"] == [
        "https://forum.intervals.icu/t/server-side-data-model-for-scripts/25781/16"
    ]
    assert definitions["tss"]["primary_links"] == [
        "https://forum.intervals.icu/t/server-side-data-model-for-scripts/25781/16"
    ]
    assert definitions["hrv"]["primary_links"] == [
        "https://forum.intervals.icu/t/best-way-to-integrate-apple-watch-apple-health-data-into-intervals-icu/5776/12"
    ]
    assert definitions["strain_score"]["primary_links"] == [
        "https://forum.intervals.icu/t/three-dimensional-impulse-response-model/109644"
    ]


def test_metric_definitions_invalid_selector_is_local_error() -> None:
    result = asyncio.run(get_metric_definitions(names=[True]))  # type: ignore[list-item]

    assert result.status == "error"
    assert result.source.system == "intervals-mcp-server"
    assert result.error is not None and result.error.code == "INVALID_SELECTOR"
    assert result.coverage.reasons == ["INVALID_SELECTOR"]
