"""Complete coach workflow through actual MCP discovery/calls and synthetic HTTP."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, TextIO, cast

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from tests.coach_cycle_fixture_server import initial_state


class CoachClient:
    def __init__(self, session: ClientSession, schemas: dict[str, Any]):
        self.session = session
        self.schemas = schemas

    async def call(self, name: str, **arguments: Any) -> dict[str, Any]:
        result = await self.session.call_tool(name, arguments)
        assert result.isError is not True
        structured = result.structuredContent
        assert isinstance(structured, dict)
        assert isinstance(self.schemas[name], dict)
        Draft202012Validator(self.schemas[name]).validate(structured)
        blocks = [block for block in result.content if block.type == "text"]
        assert len(blocks) == 1 and json.loads(blocks[0].text) == structured
        return structured


def _state(directory: Path) -> dict[str, Any]:
    return json.loads((directory / "account.json").read_text(encoding="utf-8"))


@asynccontextmanager
async def _coach(directory: Path, *, mode: str = "coach", lose_ack: bool = False) -> AsyncIterator[CoachClient]:
    state_path = directory / "account.json"
    if not state_path.exists():
        state_path.write_text(json.dumps(initial_state()), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": os.path.abspath("src") + os.pathsep + os.path.abspath("."),
        "PYTHON_DOTENV_DISABLED": "1",
        "API_KEY": "synthetic-coach-cycle-key",
        "ATHLETE_ID": "i123",
        "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
        "INTERVALS_ACCESS_MODE": mode,
        "INTERVALS_OPERATION_DIR": str(directory / "operations"),
        "INTERVALS_ARTIFACT_DIR": str(directory / "artifacts"),
        "COACH_FIXTURE_STATE": str(state_path),
        "COACH_FIXTURE_LOSE_ACK": "1" if lose_ack else "0",
    }
    params = StdioServerParameters(command=sys.executable, args=["-m", "tests.coach_cycle_fixture_server"], env=env)
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as errlog:
        async with stdio_client(params, errlog=cast(TextIO, errlog)) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                yield CoachClient(session, {tool.name: tool.outputSchema for tool in listed.tools})
        errlog.seek(0)
        assert "synthetic-coach-cycle-key" not in errlog.read()


@pytest.mark.asyncio
async def test_coach_cycle_session_plan_comment_history_and_verified_workout(tmp_path: Path) -> None:
    async with _coach(tmp_path) as coach:
        capabilities = (await coach.call("get_capabilities"))["data"]
        assert capabilities["server"]["mode"] == "coach"
        assert capabilities["server"]["live_verified"] is False
        assert {row["name"] for row in capabilities["tool_catalogue"]} == set(coach.schemas)
        assert len(coach.schemas) == 24 and "add_activity_message" not in coach.schemas

        context = await coach.call("get_session_context", activity_id="cycle-activity", sections=["details", "intervals", "plan", "comments"])
        sections = context["data"]["sections"]
        assert all(section["status"] == "ok" for section in sections.values())
        assert sections["details"]["data"]["id"] == "cycle-activity"
        assert sections["intervals"]["data"]["icu_intervals"][0]["average_watts"] == 150
        assert sections["plan"]["data"]["resolved_event"]["id"] == 90
        resolved_request = next(row for row in _state(tmp_path)["requests"] if row["query"].get("resolve") == "true")
        assert resolved_request["query"]["oldest"] == "2026-09-07"
        assert sections["comments"]["data"] == []

        analysis = {"activity_id": "cycle-activity", "analysis_uid": "analysis-v1", "content": "Równo: 150 W. Kolejny trening spokojny. 🚴"}
        published = await coach.call("publish_analysis_comment", **analysis)
        assert published["result"]["outcome"] == "confirmed" and published["result"]["message_id"] == 100
        requests = _state(tmp_path)["requests"]
        assert [row["method"] for row in requests[-2:]] == ["POST", "GET"]
        assert await coach.call("publish_analysis_comment", **analysis) == published
        assert _state(tmp_path)["requests"] == requests
        revision = await coach.call("publish_analysis_comment", **{**analysis, "analysis_uid": "analysis-v2", "content": "Nowa wersja po rozmowie: odczucie 3/10."})
        assert revision["result"]["outcome"] == "confirmed" and revision["result"]["message_id"] == 101
        comments = (await coach.call("get_activity_messages", activity_id="cycle-activity"))
        assert [row["id"] for row in comments["data"]] == [100, 101]
        assert comments["data"][0]["content"] == analysis["content"]
        assert comments["coverage"]["source_complete_within_query"] is None

        written = await coach.call("apply_workout_changes", decision_uid="next-ride", operations=[{
            "operation_uid": "next-ride-create", "session_uid": "next-ride-session", "action": "create",
            "workout": {"name": "Easy ride", "start_date": "2026-09-10", "sport": "Ride", "representation": "native_text", "workout_text": "steady"},
        }])
        assert written["results"][0]["outcome"] == "confirmed"
        assert written["results"][0]["event_id"] == 91
        requests = _state(tmp_path)["requests"]
        assert [(row["method"], row["path"]) for row in requests[-2:]] == [
            ("POST", "/api/v1/athlete/i123/events"), ("GET", "/api/v1/athlete/i123/events/91"),
        ]
        assert sum(row["method"] == "POST" for row in requests) == 3
        assert {row["method"] for row in requests} == {"GET", "POST"}

    # A new MCP process reads both journal families and replays the exact prior result.
    requests = _state(tmp_path)["requests"]
    async with _coach(tmp_path) as restarted:
        assert await restarted.call("publish_analysis_comment", **analysis) == published
        workout = await restarted.call("get_write_status", operation_uid="next-ride-create")
        assert workout["historical_result"]["outcome"] == "confirmed"
    assert _state(tmp_path)["requests"] == requests


@pytest.mark.asyncio
async def test_lost_ack_survives_restart_and_readonly_reconciliation_without_republication(tmp_path: Path) -> None:
    analysis = {"activity_id": "cycle-activity", "analysis_uid": "lost-v1", "content": "Analysis persisted upstream before timeout."}
    async with _coach(tmp_path, lose_ack=True) as coach:
        published = await coach.call("publish_analysis_comment", **analysis)
        assert published["result"]["outcome"] == "unknown"
        assert published["result"]["message_id"] is None
    requests = _state(tmp_path)["requests"]
    assert len(_state(tmp_path)["messages"]) == 1

    async with _coach(tmp_path, mode="readonly") as readonly:
        assert "publish_analysis_comment" not in readonly.schemas
        assert len(readonly.schemas) == 22
        status = await readonly.call("get_analysis_comment_status", analysis_uid="lost-v1", reconcile=True)
        assert status["historical_result"]["outcome"] == "unknown"
        assert status["reconciliation_result"]["code"] == "MESSAGE_ID_UNAVAILABLE"
    assert _state(tmp_path)["requests"] == requests

    async with _coach(tmp_path) as restarted:
        assert await restarted.call("publish_analysis_comment", **analysis) == published
        assert _state(tmp_path)["requests"] == requests
        context = await restarted.call("get_session_context", activity_id="cycle-activity", sections=["details", "comments"])
        assert context["data"]["sections"]["details"]["status"] == "ok"
        assert context["data"]["sections"]["comments"]["data"][0]["content"] == analysis["content"]
    assert len(_state(tmp_path)["messages"]) == 1
    assert sum(row["method"] == "POST" for row in _state(tmp_path)["requests"]) == 1
