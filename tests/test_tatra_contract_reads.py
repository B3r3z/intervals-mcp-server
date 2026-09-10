import asyncio
import pytest
import hashlib
import json
from intervals_mcp_server.contracts import ReadResponse
from intervals_mcp_server.tools.activities import (
    get_activities,
    get_activity_details,
    get_activity_messages,
)


def test_empty_period_is_success_with_unknown_source_coverage(monkeypatch):
    async def fake(**_kwargs):
        return []

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    result = asyncio.run(
        get_activities(
            athlete_id="a",
            start_date="2024-01-01",
            end_date_exclusive="2024-01-02",
        )
    )
    assert result.status == "ok"
    assert result.data == []
    # An empty valid response proves the selected result is empty, but the
    # endpoint does not prove that the source had no additional records.
    assert result.coverage.source_complete_within_query is None
    assert result.error is None


def test_contract_empty_and_page_cursor(monkeypatch):
    calls = []

    async def fake(**kwargs):
        calls.append(kwargs)
        return [{"id": str(i), "name": "" if i == 0 else "Ride", "start_date_local": "2024-01-01"} for i in range(3)]

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    first = asyncio.run(get_activities(athlete_id="a", start_date="2024-01-01", end_date_exclusive="2024-01-02", page_size=2))
    assert isinstance(first, ReadResponse) and first.pagination.next_cursor and len(first.data) == 2
    second = asyncio.run(get_activities(athlete_id="a", start_date="2024-01-01", end_date_exclusive="2024-01-02", page_size=2, cursor=first.pagination.next_cursor))
    assert len(second.data) == 1 and len(calls) == 1


def test_activity_order_and_cursor_snapshot_use_canonical_date(monkeypatch):
    calls = []
    upstream_rows = [
        {"id": "zeta", "type": "Ride", "start_date_local": "2024-01-01T08:00:00"},
        {"id": "b", "type": "Ride", "start_date_local": "2024-01-03T09:00:00"},
        {"id": "run", "type": "Run", "start_date_local": "2024-01-03T07:00:00"},
        # Time-of-day is part of the ordering marker, even on the same date.
        {"id": "a", "type": "Ride", "start_date_local": "2024-01-03T08:00:00"},
        {"id": "fallback", "type": "Ride", "start_date_local": "", "startTime": "2024-01-02T09:00:00Z"},
        {"id": "legacy", "type": "Ride", "start_date": "2024-01-01"},
        {"id": "missing", "type": "Ride", "start_date_local": " ", "startTime": ""},
        {"id": "dup", "type": "Ride", "start_date_local": "2024-01-02", "name": "first"},
        {"id": "dup", "type": "Ride", "start_date_local": "2024-01-02", "name": "second"},
        {"id": "dup-tie", "type": "Ride", "start_date_local": "2024-01-02"},
        # The canonical startTime must win over the older start_date fallback.
        {"id": "outside", "type": "Run", "start_date_local": "", "startTime": "2024-01-04", "start_date": "2024-01-02"},
    ]

    async def fake(**kwargs):
        calls.append(kwargs)
        return upstream_rows

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)

    first = asyncio.run(
        get_activities(
            athlete_id="i9991",
            sports=["Ride"],
            page_size=3,
        )
    )
    assert first.status == "ok"
    assert [row["id"] for row in first.data] == ["b", "a", "fallback"]
    assert first.pagination.next_cursor

    # Changing the source collection cannot affect the stored snapshot, and
    # cursor pages must not issue another upstream request.
    upstream_rows.clear()
    second = asyncio.run(
        get_activities(
            athlete_id="i9991",
            sports=["Ride"],
            page_size=3,
            cursor=first.pagination.next_cursor,
        )
    )
    third = asyncio.run(
        get_activities(
            athlete_id="i9991",
            sports=["Ride"],
            page_size=3,
            cursor=second.pagination.next_cursor,
        )
    )

    assert [row["id"] for row in second.data] == ["dup", "dup-tie", "zeta"]
    assert [row["id"] for row in third.data] == ["legacy", "missing"]
    assert third.pagination.next_cursor is None
    assert [row["id"] for row in first.data + second.data + third.data] == [
        "b", "a", "fallback", "dup", "dup-tie", "zeta", "legacy", "missing"
    ]
    assert len(calls) == 1
    assert next(row for row in second.data if row["id"] == "dup")["name"] == "second"


def test_activity_date_filter_uses_canonical_fallback(monkeypatch):
    calls = []
    rows = [
        {
            "id": "local",
            "type": "Ride",
            "start_date_local": "2024-01-01",
            "startTime": "2024-01-03",
            "start_date": "2024-01-04",
        },
        {
            "id": "time",
            "type": "Ride",
            "start_date_local": "",
            "startTime": "2024-01-02T08:00:00Z",
            "start_date": "2024-01-04",
        },
        {"id": "date", "type": "Ride", "start_date_local": "", "startTime": "", "start_date": "2024-01-02"},
        {
            "id": "outside",
            "type": "Ride",
            "start_date_local": "",
            "startTime": "2024-01-04",
            "start_date": "2024-01-02",
        },
        {"id": "wrong-sport", "type": "Run", "start_date_local": "2024-01-03"},
    ]

    async def fake(**kwargs):
        calls.append(kwargs)
        return rows

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)

    result = asyncio.run(
        get_activities(
            athlete_id="i9992",
            start_date="2024-01-01",
            end_date_exclusive="2024-01-04",
            sports=["Ride"],
            page_size=10,
        )
    )

    assert result.status == "ok"
    assert [row["id"] for row in result.data] == ["time", "date", "local"]
    assert len(calls) == 1


def test_contract_page_validation_and_timezone(monkeypatch):
    result = asyncio.run(get_activities(athlete_id="a", page_size=0))
    assert result.status == "error"
    result = asyncio.run(get_activities(athlete_id="a", timezone="No/Such"))
    assert result.status == "error"


def test_cursor_rejects_snapshot_from_a_different_query(monkeypatch):
    async def fake(**_kwargs):
        return [
            {"id": "first", "start_date_local": "2026-09-02"},
            {"id": "second", "start_date_local": "2026-09-01"},
        ]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    first = asyncio.run(
        get_activities(
            athlete_id="i123",
            start_date="2026-09-01",
            end_date_exclusive="2026-09-03",
            page_size=1,
        )
    )
    assert first.pagination.next_cursor is not None
    snapshot = first.pagination.next_cursor.split(".")[1]
    other_query_key = json.dumps(
        ["i124", "2026-09-01", "2026-09-03", "Europe/Warsaw", None],
        sort_keys=True,
    )
    cursor = (
        hashlib.sha256(other_query_key.encode()).hexdigest()[:16]
        + f".{snapshot}.0"
    )

    result = asyncio.run(
        get_activities(
            athlete_id="i124",
            start_date="2026-09-01",
            end_date_exclusive="2026-09-03",
            cursor=cursor,
        )
    )

    assert result.status == "error"
    assert result.error.code == "INVALID_CURSOR"
    assert result.data == []


def test_hidden_activity_is_preserved_with_explicit_source_limitation(monkeypatch):
    hidden = {
        "id": "a-hidden",
        "source": "STRAVA",
        "start_date_local": "2026-09-08T07:30:00",
        "_note": "This activity is hidden by the source privacy policy.",
    }

    async def fake(**_kwargs):
        return hidden

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    result = asyncio.run(get_activity_details("a-hidden"))

    assert result.status == "partial"
    assert result.data == hidden
    assert result.coverage.source_complete_within_query is False
    assert result.coverage.response_complete is True
    assert result.coverage.reasons == ["source_record_hidden"]
    assert result.warnings == ["SOURCE_DATA_LIMITED"]
    assert result.limitations == [
        {
            "code": "SOURCE_DATA_LIMITED",
            "activity_id": "a-hidden",
            "source": "STRAVA",
            "message": hidden["_note"],
        }
    ]


def test_hidden_strava_marker_without_note_is_limited(monkeypatch):
    hidden = {"id": "a-hidden", "name": "Hidden", "source": "STRAVA"}

    async def fake(**_kwargs):
        return hidden

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    result = asyncio.run(get_activity_details("a-hidden"))

    assert result.status == "partial"
    assert result.data == hidden
    assert result.coverage.reasons == ["source_record_hidden"]
    assert result.limitations[0]["activity_id"] == "a-hidden"


def test_generic_activity_note_is_not_treated_as_hidden(monkeypatch):
    activity = {
        "id": "a-visible",
        "name": "Visible ride",
        "type": "Ride",
        "source": "UPLOAD",
        "_note": None,
    }

    async def fake(**_kwargs):
        return activity

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    result = asyncio.run(get_activity_details("a-visible"))

    assert result.status == "ok"
    assert result.data == activity
    assert result.coverage.source_complete_within_query is None
    assert result.warnings == []
    assert result.limitations == []


def test_activity_list_preserves_hidden_row_and_identifies_its_limitation(monkeypatch):
    rows = [
        {
            "id": "a-visible",
            "name": "Visible ride",
            "type": "Ride",
            "source": "UPLOAD",
            "start_date_local": "2026-09-02",
        },
        {
            "id": "a-hidden",
            "name": "Hidden",
            "source": "STRAVA",
            "start_date_local": "2026-09-01",
        },
    ]

    async def fake(**_kwargs):
        return rows

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    result = asyncio.run(
        get_activities(
            athlete_id="i123",
            start_date="2026-09-01",
            end_date_exclusive="2026-09-03",
            page_size=10,
        )
    )

    assert result.status == "partial"
    assert result.data == rows
    assert result.coverage.source_complete_within_query is False
    assert result.coverage.response_complete is True
    assert "source_record_hidden" in result.coverage.reasons
    assert result.warnings == ["SOURCE_DATA_LIMITED"]
    assert result.limitations == [
        {
            "code": "SOURCE_DATA_LIMITED",
            "activity_id": "a-hidden",
            "source": "STRAVA",
            "message": "The upstream source returned a hidden activity record.",
        }
    ]


def test_message_fingerprint(monkeypatch):
    async def fake(**kwargs):
        return [{"id": 1, "name": "athlete", "type": "NOTE", "content": "ok", "created": "t"}]
    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    result = asyncio.run(get_activity_messages("a"))
    assert result.status == "ok" and len(result.data[0]["content_fingerprint"]) == 64


def test_message_edit_changes_fingerprint_and_preserves_identity_metadata(monkeypatch):
    messages = [
        {
            "id": 1,
            "author": "athlete",
            "content": "before",
            "created": "2026-09-08T08:00:00+02:00",
            "updated": "2026-09-08T08:05:00+02:00",
        }
    ]

    async def fake(**_kwargs):
        return messages

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    before = asyncio.run(get_activity_messages("a")).data[0]
    messages[0] = {**messages[0], "content": "after"}
    after = asyncio.run(get_activity_messages("a")).data[0]

    assert before["created"].endswith("+02:00")
    assert before["updated"].endswith("+02:00")
    assert before["author"] == "athlete"
    assert before["content_fingerprint"] != after["content_fingerprint"]


@pytest.mark.parametrize("field,value", [
    ("athlete_id", "i123"), ("activity_id", "a"),
    ("deleted", "2026-09-09T12:00:00Z"), ("deleted_by_id", "i123"),
])
def test_message_identity_or_deletion_changes_fingerprint(monkeypatch, field, value):
    message = {"id": 42, "content": "same analysis"}

    async def fake(**_kwargs):
        return [message]

    monkeypatch.setattr("intervals_mcp_server.tools.activities.make_intervals_request", fake)
    before = asyncio.run(get_activity_messages("a")).data[0]
    message[field] = value
    after = asyncio.run(get_activity_messages("a")).data[0]
    assert after[field] == value and after["content"] == before["content"]
    assert after["content_fingerprint"] != before["content_fingerprint"]
