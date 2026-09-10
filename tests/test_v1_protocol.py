from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.v1_scenario_harness import capture_v1_report
from tests.v1_fixture_server import (
    _activity_curves,
    _best_efforts,
    _four_by_eight_intervals,
    _interval_stats,
    _sport_settings,
    _stream_values,
)
from tests.protocol_read_harness import capture_report


def _flat_calls(case: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in case["calls"]:
        calls.extend(item.get("calls", [item]))
    return calls


@pytest.mark.asyncio
async def test_v1_cases_use_real_stdio_and_preserve_protocol_facts(
    tmp_path: Path,
) -> None:
    report = await capture_v1_report(
        repo_root=Path(__file__).resolve().parents[1],
        private_root=tmp_path / "private-state",
    )

    assert [case["case"] for case in report["cases"]] == [
        f"S{index:02d}" for index in range(1, 13)
    ]
    for case in report["cases"]:
        for call in _flat_calls(case):
            assert call["text_content_present"] is True
            if call["schema_check"] == "required":
                assert call["output_schema_valid"] is True
                assert call["structured_text_agree"] is True
            else:
                assert call["schema_check"] == "not_applicable"

    observations = {case["case"]: case["observations"] for case in report["cases"]}
    assert observations["S01"]["legacy_details_do_not_duplicate_intervals"] is True
    assert observations["S01"]["context_interval_records"] == 8
    assert observations["S01"]["context_comment_fingerprint_present"] is True
    assert observations["S01"]["work_durations"] == [480, 480, 480, 480]
    assert observations["S01"]["work_watts"] == [315, 318, 321, 324]
    assert observations["S01"]["work_heartrate"] == [154, 155, 156, 157]
    assert observations["S01"]["recovery_durations"] == [420, 420, 420, 420]
    assert observations["S02"]["returned_sample_count"] == 30
    assert observations["S02"]["returned_bounds"]["matched"] is True
    assert observations["S02"]["returned_time_values"] == list(range(10, 40))
    assert observations["S03"]["returned_effort_duration"] == 300
    assert observations["S03"]["returned_effort_average"] == 345
    assert observations["S03"]["historical_curve_watts"] == [330]
    assert observations["S03"]["historical_curve_activity_ids"] == [
        "a-history-300"
    ]
    assert observations["S03"]["historical_curve_period"] == {
        "start": "2026-08-01",
        "end": "2026-09-08",
    }
    assert observations["S03"]["curve_missing_durations"] == [600]
    assert observations["S04"]["selection"]["verified"] is not True
    assert observations["S04"]["returned_after_kj"] == [None, 246, 480]
    assert observations["S04"]["returned_300_watts"] == [410, 390, 370]
    assert observations["S04"]["returned_bounds_at_300"] == [
        {"start_index": 0, "end_index": 300},
        {"start_index": 600, "end_index": 900},
        {"start_index": 1200, "end_index": 1500},
    ]
    assert observations["S05"]["current_settings_ftp"] == 280
    assert observations["S05"]["paired_event_ids"] == {"raw": 9001, "resolved": 9001}
    assert observations["S05"]["decoy_excluded"] is True
    assert observations["S05"]["ftp_scopes"] == {
        "activity": 245,
        "event": 260,
        "workout_document": 260,
    }
    assert observations["S05"]["resolved_power_target"]["value"] == 221
    assert observations["S06"]["heartrate_unit"] == "bpm"
    assert observations["S06"]["icu_hr_zone_times"] == [300, 700, 600, 200]
    assert observations["S06"]["opaque_load_code"] == 17
    assert observations["S06"]["historical_power_missing"] is True
    assert observations["S07"]["stream_error_code"] == "HTTP_403"
    assert observations["S07"]["hidden_warning_retained"] is True
    assert observations["S08"]["error_codes"] == [None, "SNAPSHOT_CHANGED", None]
    assert observations["S09"]["oversized_range"]["error_code"] == "RANGE_TOO_LARGE"
    assert observations["S09"]["oversized_range"]["http_attempts"] == 0
    assert observations["S09"]["parameter_validation"] == {
        "mcp_is_error": True,
        "structured_content_present": False,
        "schema_check": "not_applicable",
        "http_attempts": 0,
    }
    assert observations["S09"]["full_stream_sample_counts"][0]["data_count"] == 10005
    assert observations["S09"]["duplicate_watts_preserved"] is True
    assert observations["S09"]["data2_preserved"] is True
    assert observations["S09"]["manifest_hash_matches"] is True
    assert observations["S09"]["chunk_hashes_match"] is True
    assert observations["S10"]["script_preserved_as_data"] is True
    assert observations["S10"]["statuses"] == ["partial", "partial"]
    assert observations["S10"]["missing_metadata_reported"] is True
    assert observations["S11"]["set_level_records_supplied"] is False
    assert observations["S11"]["full_source_has_no_set_fields"] is True
    assert "set-level" in observations["S11"]["description"]
    assert observations["S12"]["section_statuses"] == [
        {"details": "error", "comments": "ok"},
        {"details": "error", "comments": "ok"},
        {"details": "error", "comments": "ok"},
    ]
    assert observations["S12"]["context_http_attempts"] == [2, 4, 4]
    assert observations["S12"]["section_error_codes"] == [
        "INVALID_UPSTREAM_RESPONSE",
        "READ_TIMEOUT",
        "HTTP_429",
    ]
    assert observations["S12"]["recommended_actions"] == [
        None,
        "retry read",
        "retry read",
    ]


@pytest.mark.asyncio
async def test_original_six_call_replay_has_additive_source_flags() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    current = await capture_report(baseline_only=True)
    source_replay = await capture_report(
        server_source=repo_root / "src",
        baseline_only=True,
    )

    def totals(report: dict[str, Any]) -> tuple[int, int, int, int]:
        scenarios = report["scenarios"].values()
        return (
            sum(item["mcp_calls"] for item in scenarios),
            sum(item["upstream_requests"] for item in report["scenarios"].values()),
            sum(
                item["utf8_json_text_bytes"]
                for item in report["scenarios"].values()
            ),
            sum(
                item["utf8_call_tool_result_bytes"]
                for item in report["scenarios"].values()
            ),
        )

    assert totals(current) == (6, 6, 11203, 20740)
    assert totals(source_replay) == (6, 6, 11203, 20740)
    assert current["baseline_only"] is True
    assert source_replay["baseline_only"] is True


def test_v1_fixture_declared_statistics_match_full_arrays() -> None:
    def streams(activity_id: str) -> dict[str, list[Any]]:
        return {
            str(row["type"]): row["data"]
            for row in _stream_values(activity_id)
            if isinstance(row.get("data"), list)
        }

    four_by_eight = streams("a-4x8")
    for interval in _four_by_eight_intervals():
        start = int(interval["start_index"])
        end = int(interval["end_index"])
        watts = four_by_eight["watts"][start:end]
        heartrate = four_by_eight["heartrate"][start:end]
        assert sum(watts) / len(watts) == interval["average_watts"]
        assert sum(heartrate) / len(heartrate) == interval["average_heartrate"]

    fragment = streams("a-fragment")
    fragment_stats = _interval_stats("a-fragment")
    assert sum(fragment["watts"][10:40]) / 30 == fragment_stats["average_watts"]
    assert sum(fragment["heartrate"][10:40]) / 30 == fragment_stats["average_heartrate"]

    best_effort = _best_efforts("a-best5")["efforts"][0]
    best_watts = streams("a-best5")["watts"][100:400]
    assert sum(best_watts) / len(best_watts) == best_effort["average"]
    assert best_effort["end_index"] - best_effort["start_index"] == best_effort["duration"]

    fatigue_watts = streams("a-fatigue")["watts"]
    expected_thresholds = {None: 0, 246: 600, 480: 1200}
    for curve in _activity_curves("a-fatigue"):
        threshold = curve["after_kj"]
        first_start = int(curve["start_index"][0])
        assert first_start == expected_thresholds[threshold]
        if threshold is not None:
            assert sum(fatigue_watts[:first_start]) / 1000 == threshold
        for secs, value, start, end in zip(
            curve["secs"],
            curve["values"],
            curve["start_index"],
            curve["end_index"],
            strict=True,
        ):
            segment = fatigue_watts[int(start) : int(end)]
            assert int(end) - int(start) == secs
            assert sum(segment) / len(segment) == value

    settings = _sport_settings()
    assert settings["after_kj0"] == 246
    assert settings["after_kj1"] == 480
