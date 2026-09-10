"""Persistent synthetic upstream for a coach cycle and MCP process restarts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


def initial_state() -> dict[str, Any]:
    return {
        "messages": [],
        "events": [{
            "id": 90, "name": "Linked plan", "category": "WORKOUT", "type": "Ride",
            "start_date_local": "2026-09-07T18:00:00", "description": "- 10m 60%",
            "workout_doc": {"steps": [{"duration": 600, "power": {"value": 60, "units": "%ftp"}}]},
        }],
        "requests": [],
    }


class SyntheticCoachAccount:
    def __init__(self, path: Path):
        self.path = path

    def request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host != "synthetic.invalid":
            raise AssertionError("only synthetic upstream requests are allowed")
        state = json.loads(self.path.read_text(encoding="utf-8"))
        body = json.loads(request.content) if request.content else None
        state["requests"].append({
            "method": request.method, "path": request.url.path,
            "query": dict(request.url.params), "body": body,
        })
        route = request.url.path.removeprefix("/api/v1")
        result: Any
        if route == "/activity/cycle-activity" and request.method == "GET":
            result = {
                "id": "cycle-activity", "name": "Completed ride", "type": "Ride",
                "start_date_local": "2026-09-08T07:00:00", "moving_time": 600,
                "paired_event_id": 90, "icu_ftp": 250,
                "icu_intervals": [{"id": 1, "start_index": 0, "end_index": 599, "average_watts": 150}],
                "icu_groups": [],
            }
        elif route == "/activity/cycle-activity/messages" and request.method == "GET":
            result = state["messages"][-100:]
        elif route == "/activity/cycle-activity/messages" and request.method == "POST":
            assert isinstance(body, dict) and set(body) == {"content"}
            result = {"id": 100 + len(state["messages"])}
            state["messages"].append({
                **result, **body, "activity_id": "cycle-activity", "athlete_id": "i123",
                "created": "2026-09-09T12:00:00Z", "deleted": None, "deleted_by_id": None,
            })
        elif route == "/athlete/i123/events" and request.method == "GET":
            oldest, newest = request.url.params["oldest"], request.url.params["newest"]
            result = [row for row in state["events"] if oldest <= row["start_date_local"][:10] <= newest]
        elif route == "/athlete/i123/events" and request.method == "POST":
            assert request.url.params["upsertOnUid"] == "false"
            assert isinstance(body, dict) and body["category"] == "WORKOUT"
            result = {"id": 91, **body, "workout_doc": {"steps": []}}
            state["events"].append(result)
        elif route in {"/athlete/i123/events/90", "/athlete/i123/events/91"} and request.method == "GET":
            event_id = int(route.rsplit("/", 1)[-1])
            result = next(row for row in state["events"] if row["id"] == event_id)
        else:
            raise AssertionError(f"unsupported synthetic request: {request.method} {route}")
        self.path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        if request.method == "POST" and route.endswith("/messages") and os.getenv("COACH_FIXTURE_LOSE_ACK") == "1":
            raise httpx.ReadTimeout("synthetic lost acknowledgement", request=request)
        return httpx.Response(200, json=result)


def main() -> None:
    from intervals_mcp_server import server
    from intervals_mcp_server.api import client

    account = SyntheticCoachAccount(Path(os.environ["COACH_FIXTURE_STATE"]))
    client.httpx_client = httpx.AsyncClient(transport=httpx.MockTransport(account.request))
    server.mcp.run()


if __name__ == "__main__":
    main()
