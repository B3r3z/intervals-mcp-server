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


def test_default_requested_streams_are_used_for_missing_detection(monkeypatch):
    result = _run(
        monkeypatch,
        [
            {"type": "time", "data": [0, 1]},
            {"type": "watts", "data": [0, 200]},
            {"type": "TymeBreathRate", "data": [0, 30]},
        ],
    )

    assert result.status == "partial"
    assert result.query.stream_types == [
        "time",
        "watts",
        "heartrate",
        "cadence",
        "altitude",
        "distance",
        "velocity_smooth",
    ]
    assert result.data["requested"] == result.query.stream_types
    assert result.data["missing"] == [
        "heartrate",
        "cadence",
        "altitude",
        "distance",
        "velocity_smooth",
    ]
    assert [row["type"] for row in result.data["streams"]] == [
        "time",
        "watts",
        "TymeBreathRate",
    ]
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


def test_stream_semantics_identify_processed_raw_units_and_alignment_basis(monkeypatch):
    result = _run(
        monkeypatch,
        [
            {"type": "time", "data": [0, 1.5, 1.5, None]},
            {"type": "watts", "data": [200, 201, None, 0]},
            {"type": "raw_watts", "data": [198, 199, None, 0]},
            {"type": "heartrate", "data": [140, 141, None, 0]},
            {"type": "raw_heartrate", "data": [139, 140, None, 0]},
            {"type": "cadence", "data": [80, 81, None, 0]},
        ],
        stream_types="time,watts,raw_watts,heartrate,raw_heartrate,cadence",
    )

    units = {row["type"]: row["unit"] for row in result.data["streams"]}
    assert units["watts"] == "W"
    assert units["raw_watts"] == "W"
    assert units["heartrate"] == "bpm"
    assert units["raw_heartrate"] == "bpm"
    assert units["cadence"] == "1/min"
    assert "lengths only" in result.data["alignment"]["quality_basis"]
    assert result.data["time_axis"] == [0, 1.5, 1.5, None]
    assert result.data["snapshot_scope"]["continuation_requires"] == {
        "activity_id": "a",
        "stream_types": ["time", "watts", "raw_watts", "heartrate", "raw_heartrate", "cadence"],
    }
