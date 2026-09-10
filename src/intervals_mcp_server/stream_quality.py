"""Describe source samples without filling gaps or inferring sensor health."""

from __future__ import annotations

import math
from typing import Any


STREAM_UNITS = {
    "time": "s", "watts": "W", "raw_watts": "W", "heartrate": "bpm",
    "raw_heartrate": "bpm", "cadence": "1/min", "altitude": "m", "distance": "m",
    "velocity_smooth": "m/s", "temp": "C", "temperature": "C",
    "coreTemperature": "C", "skinTemperature": "C", "joules": "J",
    "respiration": "breaths/min", "torque": "N m",
}


def participates_in_alignment(stream: dict[str, Any], field: str) -> bool:
    """Primary data is expected; secondary data participates only when present."""
    return field == "data" or isinstance(stream.get(field), list)


def _finite(value: Any) -> bool:
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def summarize_streams(streams: list[dict[str, Any]]) -> dict[str, Any]:
    """Inspect all returned samples; keep at most 20 illustrative time gaps."""
    rows: list[dict[str, Any]] = []
    lengths: list[int] = []
    missing_primary = False
    for index, stream in enumerate(streams):
        arrays: dict[str, Any] = {}
        for field in ("data", "data2"):
            values = stream.get(field)
            state = "absent" if field not in stream else "null" if values is None else "present"
            if not isinstance(values, list):
                arrays[field] = {"state": state, "count": None}
                missing_primary |= field == "data"
                continue
            if participates_in_alignment(stream, field):
                lengths.append(len(values))
            finite_count = sum(_finite(value) for value in values)
            null_count = sum(value is None for value in values)
            arrays[field] = {
                "state": "present", "count": len(values), "finite_count": finite_count,
                "null_count": null_count,
                "invalid_count": len(values) - finite_count - null_count,
                "zero_count": sum(_finite(value) and value == 0 for value in values),
                "finite_fraction": finite_count / len(values) if values else None,
            }
        rows.append({
            "stream_index": index, "type": stream.get("type"),
            "unit": stream.get("unit", STREAM_UNITS.get(str(stream.get("type")))),
            "arrays": arrays,
        })
    time_streams = [s for s in streams if s.get("type") == "time"]
    axis = time_streams[0].get("data") if len(time_streams) == 1 else None
    time: dict[str, Any] = {"availability": "unavailable", "time_stream_count": len(time_streams)}
    if isinstance(axis, list):
        pairs = [(i, axis[i - 1], axis[i]) for i in range(1, len(axis))
                 if _finite(axis[i - 1]) and _finite(axis[i])]
        deltas = [right - left for _, left, right in pairs]
        gaps = [{"start_index": i - 1, "end_index": i, "start_secs": left,
                 "end_secs": right, "delta_secs": right - left}
                for i, left, right in pairs if right - left > 1]
        time.update({
            "availability": "available", "sample_count": len(axis),
            "invalid_or_null_count": sum(not _finite(value) for value in axis),
            "nonpositive_delta_count": sum(delta <= 0 for delta in deltas),
            "duplicate_timestamp_count": sum(delta == 0 for delta in deltas),
            "reversed_timestamp_count": sum(delta < 0 for delta in deltas),
            "positive_delta_not_1s_count": sum(delta > 0 and delta != 1 for delta in deltas),
            "gap_count_over_1s": len(gaps),
            "max_delta_secs": max(deltas) if deltas else None,
            "unrepresented_seconds_vs_1hz": sum(max(delta - 1, 0) for delta in deltas),
            "gap_examples": gaps[:20], "omitted_gap_examples": max(len(gaps) - 20, 0),
            "elapsed_span_secs": axis[-1] - axis[0]
            if axis and _finite(axis[0]) and _finite(axis[-1]) else None,
        })
    return {
        "streams": rows,
        "alignment": {"missing_primary_arrays": missing_primary,
                      "equal_present_array_lengths": len(set(lengths)) <= 1,
                      "quality": "missing_primary" if missing_primary else
                      "unequal_lengths" if len(set(lengths)) > 1 else
                      "aligned" if lengths else "no_arrays"},
        "time_axis": time,
        "method": {
            "scope": "all samples in returned upstream streams",
            "finite_fraction_denominator": "source array length, not elapsed time",
            "gap_reference_seconds": 1,
            "interpretation": "Gaps relative to 1 Hz are observations, not proof of lost data. "
                              "Numeric validity is not sensor health; non-numeric custom samples "
                              "count as invalid for numeric analysis only. Zeros are observations, "
                              "not sensor failures. No gap filling, "
                              "interpolation, physiological or readiness calculation.",
        },
    }
