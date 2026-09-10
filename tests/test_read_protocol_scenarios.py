import pytest

from tests.protocol_read_harness import capture_invalid_duration_probe, capture_report


@pytest.mark.asyncio
async def test_stdio_read_scenarios_keep_protocol_contract_after_r1a():
    report = await capture_report()
    scenarios = report["scenarios"]
    assert report["input_validation_probe"] == {
        "mcp_is_error": True,
        "structured_content_present": False,
        "text_content_present": True,
        "upstream_requests": 0,
    }
    assert report["analytics_a1_probe"]["mcp_is_error"] is False
    assert report["analytics_a1_probe"]["domain_status"] == "ok"
    assert report["analytics_a1_probe"]["output_schema_valid"] is True
    assert report["analytics_a1_probe"]["structured_text_agree"] is True
    assert report["analytics_a1_probe"]["raw_interval_preserved"] is True
    assert report["analytics_a1_probe"]["upstream_requests"] == 1
    assert report["analytics_a1_probe"]["invalid_mcp_is_error"] is True
    assert report["analytics_a1_probe"]["invalid_structured_content_present"] is False
    assert report["analytics_a1_probe"]["invalid_text_content_present"] is True
    assert report["analytics_a2_probe"]["success_mcp_is_error"] is False
    assert report["analytics_a2_probe"]["success_domain_status"] == "partial"
    assert report["analytics_a2_probe"]["success_output_schema_valid"] is True
    assert report["analytics_a2_probe"]["success_structured_text_agree"] is True
    assert report["analytics_a2_probe"]["null_average_preserved"] is True
    assert report["analytics_a2_probe"]["invalid_mcp_is_error"] is True
    assert report["analytics_a2_probe"]["invalid_structured_content_present"] is False
    assert report["analytics_a2_probe"]["invalid_text_content_present"] is True
    assert report["analytics_a2_probe"]["upstream_requests"] == 1

    assert sum(row["mcp_calls"] for row in scenarios.values()) == 6
    assert sum(row["upstream_requests"] for row in scenarios.values()) == 6
    for scenario in scenarios.values():
        for call in scenario["calls"]:
            assert call["mcp_is_error"] is False
            assert call["output_schema_valid"] is True
            assert call["structured_text_agree"] is True
            assert call["utf8_json_text_bytes"] > 0
            assert call["utf8_call_tool_result_bytes"] > call["utf8_json_text_bytes"]

    activity = scenarios["activity_session"]
    assert [call["domain_status"] for call in activity["calls"]] == [
        "partial",
        "ok",
        "ok",
    ]
    assert activity["observations"]["hidden_source_row_preserved"] is True
    assert activity["observations"]["hidden_source_limitation_reported"] is True

    streams = scenarios["default_streams"]
    assert streams["calls"][0]["domain_status"] == "partial"
    assert streams["observations"]["actual_default_types_reported_as_requested"] is True
    assert streams["observations"]["absent_default_types_reported_missing"] is True
    assert streams["observations"]["duplicate_watts_preserved"] is True
    assert streams["observations"]["data2_preserved"] is True
    assert streams["observations"]["null_and_zero_samples_preserved"] is True

    curves = scenarios["athlete_power_curves"]
    assert curves["observations"]["per_curve_missing_durations_present"] is True
    assert curves["observations"]["compact_raw_curve_omitted"] is True
    assert report["full_power_curve_probe"]["mcp_is_error"] is False
    assert report["full_power_curve_probe"]["upstream_requests"] == 1
    assert report["full_power_curve_probe"]["output_schema_valid"] is True
    assert report["full_power_curve_probe"]["structured_text_agree"] is True
    assert report["full_power_curve_probe"]["full_raw_curve_available"] is True

    a3 = report["a3_probe"]
    assert a3["curve"]["mcp_is_error"] is False
    assert a3["curve"]["domain_status"] == "partial"
    assert a3["curve"]["output_schema_valid"] is True
    assert a3["curve"]["structured_text_agree"] is True
    assert a3["curve_missing_null_preserved"] is True
    assert a3["settings"]["mcp_is_error"] is False
    assert a3["settings"]["domain_status"] == "ok"
    assert a3["settings"]["output_schema_valid"] is True
    assert a3["settings"]["structured_text_agree"] is True
    assert a3["settings_current_scope"] is True
    assert a3["invalid_curve_duration"]["mcp_is_error"] is True
    assert a3["invalid_curve_duration"]["structured_content_present"] is False
    assert a3["invalid_curve_duration"]["text_content_present"] is True
    assert a3["upstream_requests"] == 2

    m1e3 = report["m1e3_probe"]
    for key in ("metric", "custom_list", "custom_full", "custom_not_found_error_schema", "stream_semantics", "wellness_semantics"):
        call = m1e3[key]
        assert call["mcp_is_error"] is False
        assert call["output_schema_valid"] is True
        assert call["structured_content_present"] is True
        assert call["text_content_present"] is True
        assert call["structured_text_agree"] is True
    assert m1e3["metric"]["domain_status"] == "ok"
    assert m1e3["metric_local_source"] is True
    assert m1e3["metric_unknown_partial"] is True
    assert m1e3["custom_list"]["domain_status"] == "partial"
    assert m1e3["custom_list_metadata_warning"] is True
    assert m1e3["custom_full_raw_preserved"] is True
    assert m1e3["custom_not_found_error_schema"]["domain_status"] == "error"
    assert m1e3["stream_units_and_scope"] is True
    assert m1e3["wellness_raw_fields_preserved"] is True
    assert m1e3["invalid_custom_id"]["mcp_is_error"] is True
    assert m1e3["invalid_custom_id"]["structured_content_present"] is False
    assert m1e3["invalid_custom_id"]["text_content_present"] is True
    assert m1e3["upstream_requests"] == 5

    malformed = scenarios["malformed_events"]
    assert malformed["observations"]["malformed_shape_is_error"] is True
    assert malformed["observations"]["malformed_shape_became_empty_success"] is False


@pytest.mark.asyncio
async def test_stdio_rejects_non_integer_power_duration_before_upstream():
    probe = await capture_invalid_duration_probe()
    assert probe["mcp_is_error"] is True
    assert probe["upstream_requests"] == 0
