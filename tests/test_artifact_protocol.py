import pytest

from tests.artifact_protocol_harness import capture_artifact_report


@pytest.mark.asyncio
async def test_stdio_client_reconstructs_verified_multibyte_artifact() -> None:
    report = await capture_artifact_report()
    assert report["mcp_calls"] == report["artifact_chunks"] + 2
    assert report["artifact_chunks"] >= 2
    assert report["upstream_requests"] == 2
    assert [row["path"] for row in report["upstream_request_log"]] == [
        "/api/v1/activity/a-artifact/streams",
        "/api/v1/activity/a-artifact/intervals",
    ]
    assert report["upstream_request_log"][0]["query"] == []
    assert report["export_manifest_hash_matches"] is True
    assert report["all_chunk_artifact_hashes_match"] is True
    assert report["all_chunk_hashes_match"] is True
    assert report["multibyte_json_reconstructed"] is True
    assert report["duplicates_data2_null_zero_and_custom_preserved"] is True
    assert report["chunk_metadata_has_path"] is False
    assert report["invalid_artifact_id_is_domain_error"] is True
    assert report["artifact_bytes"] > 0
    assert report["utf8_json_text_bytes"] > 0
    assert report["utf8_call_tool_result_bytes"] > report["utf8_json_text_bytes"]

    for index, call in enumerate(report["calls"]):
        assert call["mcp_is_error"] is False
        assert call["output_schema_valid"] is True
        assert call["structured_text_agree"] is True
        assert call["utf8_json_text_bytes"] > 0
        assert call["utf8_call_tool_result_bytes"] > call["utf8_json_text_bytes"]
        if index:
            assert call["source_system"] == "intervals-mcp-server"
            if call["domain_status"] != "error":
                assert call["response_complete"] is True
