"""Interval evidence stays consistent across standalone, export and composed reads."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from intervals_mcp_server.tools import activities
from intervals_mcp_server.tools.session_context import get_session_context


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "valid", "missing_intervals"),
    [
        ({"icu_intervals": [{"id": 1, "future": 0}], "icu_groups": None,
          "future_container": {"field": None}}, True, False),
        ([{"id": 1, "future": None}], True, False),
        ({"icu_groups": [{"count": 0}]}, True, True),
        ({"icu_groups": None}, True, True),
        ({"icu_intervals": [], "icu_groups": []}, True, False),
        ({"icu_intervals": None}, False, False),
        ({"icu_intervals": [None]}, False, False),
        ({"icu_intervals": [], "icu_groups": "invalid"}, False, False),
        ({"unrecognized": []}, False, False),
    ],
)
async def test_interval_container_contract_across_public_reads(
    monkeypatch, tmp_path, payload, valid, missing_intervals
):
    original = deepcopy(payload)
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))

    async def request(url, **_kwargs):
        if url == "/activity/a1":
            return {"id": "a1", "name": "Ride"}
        if url.endswith("/intervals"):
            return payload
        if url.endswith("/streams"):
            return []
        pytest.fail(f"unexpected read: {url}")

    monkeypatch.setattr(activities, "make_intervals_request", request)
    standalone = await activities.get_activity_intervals("a1")
    export = await activities.export_activity_data("a1")
    context = await get_session_context("a1", sections=["intervals"], detail="full")
    section = context.data["sections"]["intervals"]
    if valid:
        assert standalone.status == export.status == "ok"
        assert standalone.data == section["data"] == payload
        artifact = json.loads(Path(export.data["access"]["path"]).read_text(encoding="utf-8"))
        assert artifact["intervals"] == payload
        assert section["status"] == ("partial" if missing_intervals else "ok")
        assert section["coverage"]["response_complete"] is (not missing_intervals)
        if missing_intervals:
            assert section["missing"] == ["icu_intervals"]
            assert "ICU_INTERVALS_MISSING" in section["warnings"]
    else:
        assert standalone.error is not None and export.error is not None
        assert standalone.error.code == export.error.code == section["error"]["code"] == "INVALID_UPSTREAM_RESPONSE"
        assert section["status"] == "error"
        assert list(tmp_path.iterdir()) == []
    assert payload == original


@pytest.mark.asyncio
@pytest.mark.parametrize("embedded", [True, False])
async def test_interval_projection_owns_omissions_and_preserves_full_follow_up(
    monkeypatch, embedded
):
    payload = {
        "icu_intervals": [{"id": 1, "name": "x" * 4001, "average_watts": 0, "future": None}],
        "icu_groups": None,
    }
    original = deepcopy(payload)

    async def request(url, **_kwargs):
        if url == "/activity/a1":
            return {"id": "a1", "name": "Ride", **(payload if embedded else {})}
        assert url == "/activity/a1/intervals"
        return payload

    monkeypatch.setattr(activities, "make_intervals_request", request)
    compact = await get_session_context("a1", sections=["intervals"])
    section = compact.data["sections"]["intervals"]
    assert section["status"] == "ok"
    assert section["coverage"]["response_complete"] is False
    assert section["coverage"]["truncated"] is True
    assert "compact_projection" in section["coverage"]["reasons"]
    assert "missing" not in section
    assert section["data"]["icu_intervals"][0]["average_watts"] == 0
    assert section["data"]["icu_groups"] is None
    projection = section["projection"]
    assert projection["omitted_fields"] == ["future"]
    assert projection["truncated_text"] == [{
        "path": "intervals.icu_intervals[0].name",
        "original_chars": 4001,
        "returned_chars": 4000,
    }]
    assert projection["full_follow_up"] == {
        "tool": "get_activity_intervals", "parameters": {"activity_id": "a1"}
    }
    full = await activities.get_activity_intervals("a1")
    assert full.data == original == payload
