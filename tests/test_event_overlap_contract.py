"""Ongoing calendar constraints must survive reads beginning after their start."""

from copy import deepcopy

import pytest

from intervals_mcp_server.calendar_events import select_overlapping_events
from intervals_mcp_server.contracts import success
from intervals_mcp_server.tools import events, session_context


def event(event_id, start, end, category="HOLIDAY"):
    return {"id": event_id, "category": category, "start_date_local": start,
            "end_date_local": end, "name": "Leave", "description": "Off season",
            "training_availability": "UNAVAILABLE", "future_field": {"zero": 0, "missing": None}}


@pytest.mark.asyncio
@pytest.mark.parametrize("start,end", [("2026-09-10", "2026-09-14"), ("2026-09-14", "2026-09-21")])
async def test_default_finds_ongoing_holiday_after_its_start(monkeypatch, start, end):
    source = [event(1, "2026-09-07T00:00:00", "2026-09-21T00:00:00"),
              event(2, "1999-01-01T00:00:00", "2027-01-01T00:00:00", "NOTE"),
              event(3, "2020-01-01T00:00:00", "2020-01-02T00:00:00", "WORKOUT")]
    original = deepcopy(source)
    calls = []

    async def request(**kwargs):
        calls.append(kwargs)
        # Reproduce the API's filtering by start, rather than interval overlap.
        query = kwargs["params"]
        return [row for row in source
                if query["oldest"] <= row["start_date_local"][:10] <= query["newest"]]

    monkeypatch.setattr(events, "make_intervals_request", request)
    result = await events.get_events(athlete_id="a", start_date=start, end_date_exclusive=end)

    assert result.status == "ok"
    assert result.data == [source[1], source[0]]
    assert source == original
    assert calls[0]["params"]["oldest"] == "0001-01-01"
    assert "limit" not in calls[0]["params"] and "category" not in calls[0]["params"]
    assert result.query.start_date == start and result.query.upstream_oldest == "0001-01-01"
    assert result.query.include_overlapping is True
    assert result.overlap["matched_count"] == 2
    assert result.overlap["excluded_count"] == 1
    assert result.coverage.source_complete_within_query is None


@pytest.mark.parametrize("category", ["HOLIDAY", "NOTE", "RACE_A", "WORKOUT", "FUTURE_CATEGORY"])
def test_overlap_preserves_every_category_duplicates_and_complete_source_fields(category):
    source = [event(1, "2026-01-01", "2026-12-31", category)] * 2
    rows, metadata = select_overlapping_events(source, "2026-09-14", "2026-09-21")
    assert rows == source and len(rows) == 2
    assert metadata["matched_count"] == 2
    assert metadata["unresolved_records"] == []


@pytest.mark.parametrize("start,end,matched", [
    ("2026-09-01T00:00:00", "2026-09-14T00:00:00", False),
    ("2026-09-01T00:00:00", "2026-09-14T00:00:01", True),
    ("2026-09-20T23:59:59", "2026-09-21T00:00:00", True),
    ("2026-09-21T00:00:00", "2026-09-22T00:00:00", False),
    ("2026-09-14T00:00:00", "2026-09-14T00:00:00", True),
    ("2026-09-13T12:00:00", "2026-09-13T12:00:00", False),
    ("2026-09-14", None, True),
    ("2026-10-01", None, False),
])
def test_half_open_boundaries_use_full_local_time(start, end, matched):
    row = event(1, start, end)
    selected, metadata = select_overlapping_events([row], "2026-09-14", "2026-09-21")
    assert selected == ([row] if matched else [])
    assert metadata["unresolved_records"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [
    event(1, "2026-09-07", None),
    {"id": 1, "start_date_local": "2026-09-07"},
    event(1, None, "2026-09-21"),
    event(1, "invalid", "2026-09-21"),
    event(1, "2026-09-07", "invalid"),
    event(1, "2026-09-15", "2026-09-01"),
    event(1, "2026-09-07T00:00:00+02:00", "2026-09-21T00:00:00+02:00"),
    {"id": 1, "date": "2026-10-01", "end_date_local": "2026-09-21"},
    {"id": 1, "date": "2020-01-01", "end_date_local": "2020-01-02"},
    {"id": 1, "start_date_local": None, "date": "2026-10-01", "end_date_local": "2026-09-21"},
])
async def test_unknown_overlap_retains_candidate_and_reports_partial(monkeypatch, row):
    original = deepcopy(row)

    async def request(**_kwargs):
        return [row]

    monkeypatch.setattr(events, "make_intervals_request", request)
    result = await events.get_events(athlete_id="a", start_date="2026-09-14", end_date_exclusive="2026-09-21")
    assert result.status == "partial"
    assert result.data == [original] and row == original
    assert "EVENT_OVERLAP_UNRESOLVED" in result.warnings
    assert result.overlap["unresolved_records"][0]["event_id"] == 1
    assert result.overlap["matched_count"] == 0
    assert result.coverage.response_complete is False


@pytest.mark.asyncio
async def test_explicit_start_date_mode_keeps_original_query(monkeypatch):
    calls = []

    async def request(**kwargs):
        calls.append(kwargs)
        return [{"id": 1, "description": None}]

    monkeypatch.setattr(events, "make_intervals_request", request)
    result = await events.get_events(athlete_id="a", start_date="2026-09-14",
                                     end_date_exclusive="2026-09-21", include_overlapping=False)
    assert result.status == "ok" and result.data == [{"id": 1, "description": None}]
    assert calls[0]["params"] == {"oldest": "2026-09-14", "newest": "2026-09-20"}
    assert "overlap" not in result.model_dump()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, 1, "true", None])
async def test_invalid_overlap_flag_rejected_before_api(monkeypatch, value):
    async def request(**_kwargs):
        pytest.fail("invalid flag must not access the API")
    monkeypatch.setattr(events, "make_intervals_request", request)
    result = await events.get_events(include_overlapping=value)
    assert result.error.code == "INVALID_INCLUDE_OVERLAPPING"


@pytest.mark.asyncio
async def test_session_context_inherits_overlap_and_explains_unresolved_candidates(monkeypatch):
    known = event(1, "2026-09-07", "2026-09-21")
    uncertain = event(2, "2026-09-01", None)

    async def details(*_args, **_kwargs):
        return success({"id": "activity", "start_date_local": "2026-09-15T09:00:00"}, resource="activity")

    async def request(**kwargs):
        assert kwargs["params"]["oldest"] == "0001-01-01"
        return [known, uncertain]

    monkeypatch.setattr(session_context, "get_activity_details", details)
    monkeypatch.setattr(events, "make_intervals_request", request)
    result = await session_context.get_session_context(
        "activity", athlete_id="a", sections=["contextual_events"], detail="full")
    section = result.data["sections"]["contextual_events"]
    assert result.status == section["status"] == "partial"
    assert section["data"] == [uncertain, known]
    assert section["overlap"]["unresolved_records"][0]["event_id"] == 2
    assert section["full_read"]["parameters"]["include_overlapping"] is True
