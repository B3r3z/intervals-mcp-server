import asyncio
from intervals_mcp_server.tools.wellness import get_wellness_data


def test_wellness_empty_error_and_raw_fields(monkeypatch):
    async def empty(**_): return []
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", empty)
    assert asyncio.run(get_wellness_data(athlete_id="a")).data == []
    async def raw(**_): return {"2024-01-01": {"id": "x", "custom": None, "zero": 0}}
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", raw)
    row = asyncio.run(get_wellness_data(athlete_id="a")).data[0]
    assert row["id"] == "x" and row["custom"] is None and row["zero"] == 0 and row["date"] == "2024-01-01"


def test_wellness_half_open_and_error(monkeypatch):
    seen = []
    async def fake(**kwargs):
        seen.append(kwargs)
        return {"error": True, "code": "HTTP_502", "message": "bad", "status_code": 502}
    monkeypatch.setattr("intervals_mcp_server.tools.wellness.make_intervals_request", fake)
    result = asyncio.run(get_wellness_data(athlete_id="a", start_date="2024-01-01", end_date_exclusive="2024-01-03"))
    assert result.status == "error" and seen[0]["params"]["newest"] == "2024-01-02"
