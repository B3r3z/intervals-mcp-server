import asyncio
from intervals_mcp_server.tools.events import get_events, get_event_by_id


def test_event_half_open_and_duplicates(monkeypatch):
    seen = []
    async def fake(**kwargs):
        seen.append(kwargs)
        return [{"id": "a", "date": "2026-09-08", "zero": 0, "value": None}, {"id": "a", "date": "2026-09-08"}]
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    result = asyncio.run(get_events(athlete_id="a", end_date="2026-09-08"))
    assert result.status == "ok" and result.query.upstream_newest == "2026-09-08"
    assert seen[0]["params"]["newest"] == "2026-09-08" and len(result.data) == 2


def test_event_empty_error_and_invalid_without_http(monkeypatch):
    calls = []
    async def fake(**kwargs):
        calls.append(kwargs)
        return {}
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    assert asyncio.run(get_event_by_id("", athlete_id="a")).status == "error" and not calls
    assert asyncio.run(get_event_by_id("x", athlete_id="a")).error.code == "NOT_FOUND"


def test_event_bad_timezone_and_conflicting_dates(monkeypatch):
    async def fake(**_): return []
    monkeypatch.setattr("intervals_mcp_server.tools.events.make_intervals_request", fake)
    assert asyncio.run(get_events(athlete_id="a", timezone="No/Such")).status == "error"
    assert asyncio.run(get_events(athlete_id="a", end_date="2026-01-01", end_date_exclusive="2026-01-02")).status == "error"
