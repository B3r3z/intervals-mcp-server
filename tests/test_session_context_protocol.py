import pytest

from tests.session_context_protocol_harness import capture_session_context_report


@pytest.mark.asyncio
async def test_session_context_over_real_stdio_client() -> None:
    report = await capture_session_context_report()

    assert report["mcp_calls"] == 4
    assert report["upstream_requests"] == 6
    assert report["all_context_output_schemas_valid"] is True
    assert report["all_context_structured_text_agree"] is True
    assert report["default_sections_exact"] is True
    assert report["default_two_upstream_reads"] is True
    assert report["default_embedded_intervals_requested"] is True
    assert report["valid_empty_and_zero_null_preserved"] is True
    assert report["message_fingerprint_preserved"] is True
    assert report["plan_uses_raw_event_date_then_exact_resolve"] is True
    assert report["workout_value_objects_preserved"] is True
    assert report["comments_only_one_messages_read"] is True
    assert report["comments_only_status"] == "ok"
    assert report["strict_bool_event_id_rejected_before_http"] is True
    assert report["no_current_settings_request"] is True
    assert report["context_source_is_local_composition"] is True
