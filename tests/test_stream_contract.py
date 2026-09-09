import asyncio
from intervals_mcp_server.tools.activities import get_activity_streams


def _run(monkeypatch, streams, **kwargs):
    async def fake(**_):
        return streams
    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    return asyncio.run(get_activity_streams("a", **kwargs))


def test_preview_data2_counts_units(monkeypatch):
    streams = [{"type": "watts", "data": list(range(20)), "data2": list(range(20)), "valueType": "power"}]
    result = _run(monkeypatch, streams)
    item = result.data["streams"][0]
    assert result.status == "partial" and item["data"] == list(range(5)) + list(range(15, 20))
    assert item["data2"] == item["data"] and item["source_count"] == 20 and item["returned_count"] == 10 and item["unit"] == "W"


def test_range_null_unequal_and_missing(monkeypatch):
    result = _run(monkeypatch, [{"type": "time", "data": [0, 1, None, 3]}, {"type": "watts", "data": [0, 2]}], mode="range", start_index=0, end_index=2, stream_types="time,watts,cadence")
    assert result.status == "partial" and result.data["streams"][0]["data"] == [0, 1]
    assert result.data["alignment"]["equal_source_lengths"] is False
    assert "MISSING_STREAM" in result.warnings


def test_invalid_mode_range_and_snapshot(monkeypatch):
    assert _run(monkeypatch, [], mode="bad").status == "error"
    assert _run(monkeypatch, [], mode="range", start_index=0, end_index=0).status == "error"
    assert _run(monkeypatch, [{"type": "time", "data": [0]}], expected_snapshot_id="wrong").error.code == "SNAPSHOT_CHANGED"


def test_preview_reports_non_contiguous_spans(monkeypatch):
    result = _run(monkeypatch, [{"type": "time", "data": list(range(20))}])
    item = result.data["streams"][0]
    assert item["effective_spans"] == [
        {"start_index": 0, "end_index": 5},
        {"start_index": 15, "end_index": 20},
    ]
    assert result.data["time_axis_effective_spans"] == item["effective_spans"]


def test_range_keeps_shorter_stream_and_marks_missing_indices(monkeypatch):
    streams = [
        {"type": "time", "data": [0, 1, 2, 3]},
        {"type": "watts", "data": [100, 101]},
    ]
    result = _run(monkeypatch, streams, mode="range", start_index=0, end_index=4)
    watts = result.data["streams"][1]
    assert result.status == "partial" and watts["data"] == [100, 101]
    assert watts["missing_indices"] == [{"start_index": 2, "end_index": 4}]


def test_data2_has_independent_counts_spans_and_alignment(monkeypatch):
    streams = [
        {
            "type": "watts",
            "data": list(range(20)),
            "data2": list(range(12)),
            "valueType": "power",
        }
    ]
    result = _run(monkeypatch, streams)
    item = result.data["streams"][0]
    assert item["data2_source_count"] == 12
    assert item["data2_returned_count"] == 10
    assert item["data2_effective_spans"][-1] == {
        "start_index": 7,
        "end_index": 12,
    }
    assert result.data["alignment"]["equal_source_lengths"] is False


def test_data2_can_define_axis_when_primary_data_is_absent(monkeypatch):
    result = _run(
        monkeypatch,
        [{"type": "watts", "data2": [100, 101]}],
        mode="range",
        start_index=0,
        end_index=2,
    )
    assert result.error is None
    assert result.data["streams"][0]["data2"] == [100, 101]
    assert result.data["streams"][0]["missing_indices"] == [
        {"start_index": 0, "end_index": 2}
    ]


def test_irregular_time_axis_preserves_duplicates_and_null(monkeypatch):
    axis = [0, 1.1, 1.1, None]
    result = _run(monkeypatch, [{"type": "time", "data": axis}])
    assert result.data["time_axis"] == axis


def test_range_beyond_activity_axis_is_error(monkeypatch):
    result = _run(
        monkeypatch,
        [{"type": "time", "data": [0, 1]}],
        mode="range",
        start_index=0,
        end_index=3,
    )
    assert result.error.code == "OUT_OF_RANGE"


def test_stream_units_and_data2_snapshot_change(monkeypatch):
    temperature = _run(
        monkeypatch,
        [
            {"type": "time", "data": [0]},
            {"type": "coreTemperature", "data": [37.1]},
            {"type": "joules", "data": [0]},
        ],
    )
    assert [row["unit"] for row in temperature.data["streams"]] == ["s", "C", "J"]

    first = _run(
        monkeypatch,
        [{"type": "watts", "data": [1], "data2": [2]}],
    )
    changed = _run(
        monkeypatch,
        [{"type": "watts", "data": [1], "data2": [3]}],
        expected_snapshot_id=first.pagination.snapshot_id,
    )
    assert changed.error.code == "SNAPSHOT_CHANGED"
