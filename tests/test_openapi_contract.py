"""Contract tests for the Intervals.icu REST surface used by MCP tools."""

from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any

import httpx
import pytest

from intervals_mcp_server.api import client as api_client
from intervals_mcp_server.config import Config
from intervals_mcp_server.tools import analytics, activities, custom_items, events, power_curves, settings, wellness
from scripts import check_openapi_contract as checker


FIXTURE_PATH = Path(__file__).parent / "contracts" / "intervals-openapi-used-surface.json"
ATHLETE_ID = "i-contract"
ACTIVITY_ID = "activity-contract"
EVENT_ID = 42
CUSTOM_ITEM_ID = 7


def _load_fixture() -> dict[str, Any]:
    value = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _normalize_runtime_path(method: str, url: str) -> str:
    """Map one concrete MCP request path to its original OpenAPI template."""
    path = url if url.startswith("/api/v1/") else f"/api/v1{url}"
    path = re.sub(r"^/api/v1/activity/[^/]+", "/api/v1/activity/{id}", path)
    path = re.sub(
        r"^/api/v1/athlete/[^/]+/sport-settings/[^/]+$",
        "/api/v1/athlete/{athleteId}/sport-settings/{id}",
        path,
    )
    path = re.sub(r"^/api/v1/athlete/[^/]+", "/api/v1/athlete/{id}", path)
    path = path.replace(
        "/api/v1/athlete/{id}/sport-settings/{id}",
        "/api/v1/athlete/{athleteId}/sport-settings/{id}",
    )
    path = re.sub(r"/events/[^/]+$", "/events/{eventId}", path)
    path = re.sub(r"/custom-item/[^/]+$", "/custom-item/{itemId}", path)

    if method == "GET" and path == "/api/v1/activity/{id}/streams":
        return path + "{ext}"
    if method == "GET" and path == "/api/v1/athlete/{id}/events":
        return path + "{format}"
    if method == "GET" and path in {
        "/api/v1/athlete/{id}/power-curves",
        "/api/v1/athlete/{id}/wellness",
        "/api/v1/activity/{id}/power-curves",
    }:
        return path + "{ext}"
    return path


class RequestRecorder:
    """Capture tool-level HTTP boundary calls and return endpoint-shaped data."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        url: str,
        api_key: str | None = None,
        params: dict[str, Any] | None = None,
        method: str = "GET",
        data: dict[str, Any] | None = None,
        **_kwargs: Any,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        normalized_method = method.upper()
        normalized_path = _normalize_runtime_path(normalized_method, url)
        call = {
            "method": normalized_method,
            "path": normalized_path,
            "url": url,
            "api_key": api_key,
            "params": dict(params or {}),
            "data": dict(data) if data is not None else None,
        }
        self.calls.append(call)
        key = (normalized_method, normalized_path)

        if key == ("GET", "/api/v1/activity/{id}"):
            return {
                "id": ACTIVITY_ID,
                "name": "Contract activity",
                "start_date_local": "2026-09-01T08:00:00",
            }
        if key == ("GET", "/api/v1/activity/{id}/intervals"):
            return {"id": ACTIVITY_ID, "icu_intervals": []}
        if key == ("GET", "/api/v1/activity/{id}/interval-stats"):
            return {"start_index": 0, "end_index": 10, "average_watts": 200}
        if key == ("GET", "/api/v1/activity/{id}/best-efforts"):
            return {"efforts": []}
        if key == ("GET", "/api/v1/activity/{id}/messages"):
            return [{"id": 1, "content": "Existing contract message"}]
        if key == ("POST", "/api/v1/activity/{id}/messages"):
            return {"id": 2}
        if key == ("GET", "/api/v1/activity/{id}/streams{ext}"):
            return [{"type": "time", "data": [0, 1]}]
        if key == ("GET", "/api/v1/activity/{id}/power-curves{ext}"):
            return [
                {
                    "stream_type": "watts",
                    "fatigue": "normal",
                    "secs": [5],
                    "values": [250],
                }
            ]
        if key == ("GET", "/api/v1/athlete/{id}/activities"):
            return []
        if key == ("GET", "/api/v1/athlete/{id}/events{format}"):
            return []
        if key in {
            ("POST", "/api/v1/athlete/{id}/events"),
            ("PUT", "/api/v1/athlete/{id}/events/{eventId}"),
        }:
            return {"id": EVENT_ID, **(data or {})}
        if key == ("GET", "/api/v1/athlete/{id}/events/{eventId}"):
            return {
                "id": EVENT_ID,
                "category": "WORKOUT",
                "name": "Contract event",
                "start_date_local": "2026-09-01T00:00:00",
                "type": "Ride",
            }
        if key == ("DELETE", "/api/v1/athlete/{id}/events/{eventId}"):
            return {}
        if key == ("GET", "/api/v1/athlete/{id}/wellness{ext}"):
            return []
        if key == ("GET", "/api/v1/athlete/{id}/power-curves{ext}"):
            return {"list": []}
        if key == ("GET", "/api/v1/athlete/{athleteId}/sport-settings/{id}"):
            return {"types": ["Ride"], "ftp": 250}
        if key == ("GET", "/api/v1/athlete/{id}/custom-item"):
            return []
        if key in {
            ("POST", "/api/v1/athlete/{id}/custom-item"),
            ("PUT", "/api/v1/athlete/{id}/custom-item/{itemId}"),
        }:
            return {"id": CUSTOM_ITEM_ID, **(data or {})}
        if key == ("GET", "/api/v1/athlete/{id}/custom-item/{itemId}"):
            return {"id": CUSTOM_ITEM_ID, "name": "Contract item", "type": "INPUT_FIELD"}
        if key == ("DELETE", "/api/v1/athlete/{id}/custom-item/{itemId}"):
            return {}
        raise AssertionError(f"Unexpected runtime Intervals operation: {key}")


async def _exercise_used_surface() -> None:
    common: dict[str, Any] = {"api_key": "contract-key"}
    await activities.get_activity_details(ACTIVITY_ID, **common)
    await activities.get_activity_intervals(ACTIVITY_ID, **common)
    await analytics.get_activity_interval_stats(ACTIVITY_ID, 0, 10, **common)
    await analytics.get_activity_best_efforts(
        ACTIVITY_ID, "watts", duration=60, **common
    )
    await activities.get_activity_messages(ACTIVITY_ID, **common)
    await activities.add_activity_message(ACTIVITY_ID, "Contract message", **common)
    await activities.get_activity_streams(ACTIVITY_ID, **common)
    await activities.get_activities(
        athlete_id=ATHLETE_ID,
        start_date="2026-09-01",
        end_date_exclusive="2026-09-02",
        **common,
    )

    await events.get_events(
        athlete_id=ATHLETE_ID,
        start_date="2026-09-01",
        end_date_exclusive="2026-09-02",
        **common,
    )
    await events.add_or_update_event(
        "Ride",
        "Create contract event",
        athlete_id=ATHLETE_ID,
        start_date="2026-09-01",
        moving_time=3600,
        **common,
    )
    await events.get_event_by_id(EVENT_ID, athlete_id=ATHLETE_ID, **common)
    await events.add_or_update_event(
        "Ride",
        "Update contract event",
        athlete_id=ATHLETE_ID,
        event_id=EVENT_ID,
        start_date="2026-09-01",
        moving_time=3600,
        **common,
    )
    await events.delete_event(EVENT_ID, athlete_id=ATHLETE_ID, **common)

    await wellness.get_wellness_data(
        athlete_id=ATHLETE_ID,
        start_date="2026-09-01",
        end_date_exclusive="2026-09-02",
        **common,
    )
    await power_curves.get_athlete_power_curves(
        athlete_id=ATHLETE_ID,
        durations=[5],
        this_season=True,
        last_season=False,
        **common,
    )
    await power_curves.get_activity_power_curves(
        ACTIVITY_ID, durations=[5], fatigue=["normal"], **common
    )
    await settings.get_sport_settings("Ride", athlete_id=ATHLETE_ID, **common)
    await custom_items.get_custom_items(athlete_id=ATHLETE_ID, **common)
    await custom_items.create_custom_item(
        "Contract item",
        "INPUT_FIELD",
        athlete_id=ATHLETE_ID,
        description="Contract description",
        content={"type": "numeric"},
        visibility="PRIVATE",
        **common,
    )
    await custom_items.get_custom_item_by_id(
        CUSTOM_ITEM_ID, athlete_id=ATHLETE_ID, **common
    )
    await custom_items.update_custom_item(
        CUSTOM_ITEM_ID,
        athlete_id=ATHLETE_ID,
        name="Updated contract item",
        item_type="INPUT_FIELD",
        description="Updated contract description",
        content={"type": "numeric"},
        visibility="PRIVATE",
        **common,
    )
    await custom_items.delete_custom_item(
        CUSTOM_ITEM_ID, athlete_id=ATHLETE_ID, **common
    )


def _parameter_exceptions(fixture: dict[str, Any]) -> dict[tuple[str, str], set[str]]:
    exemptions: dict[tuple[str, str], set[str]] = {}
    for exception in fixture["exceptions"]:
        scope = exception.get("scope", {})
        parameters = set(scope.get("parameters", []))
        for operation in scope.get("operations", []):
            method, path = operation.split(" ", 1)
            exemptions.setdefault((method, path), set()).update(parameters)
    return exemptions


def test_runtime_calls_match_pinned_used_surface(monkeypatch: Any) -> None:
    fixture = _load_fixture()
    recorder = RequestRecorder()
    for module in (analytics, activities, custom_items, events, power_curves, settings, wellness):
        monkeypatch.setattr(module, "make_intervals_request", recorder)
    monkeypatch.setattr(activities, "_ACTIVITY_SNAPSHOTS", {})

    asyncio.run(_exercise_used_surface())

    expected_operations = {
        (operation["method"], operation["path"]) for operation in fixture["operations"]
    }
    actual_operations = {(call["method"], call["path"]) for call in recorder.calls}
    assert len(recorder.calls) == len(expected_operations) == 22
    assert actual_operations == expected_operations

    operation_contracts = {
        (operation["method"], operation["path"]): operation
        for operation in fixture["operations"]
    }
    exemptions = _parameter_exceptions(fixture)
    payload_schemas_seen: set[str] = set()
    for call in recorder.calls:
        key = (call["method"], call["path"])
        operation = operation_contracts[key]
        for parameter in operation["required_parameters"]:
            if parameter["in"] != "query" or parameter["name"] in exemptions.get(key, set()):
                continue
            assert parameter["name"] in call["params"], (
                f"{key} did not send required query parameter {parameter['name']}"
            )

        payload = call["data"]
        if payload is None:
            continue
        schema_name = operation.get("request_schema")
        assert schema_name is not None, f"{key} sent an undocumented JSON request body"
        payload_schemas_seen.add(schema_name)
        allowed_fields = set(fixture["schemas"][schema_name]["allowed_fields"])
        assert set(payload).issubset(allowed_fields), (
            f"{key} sent fields outside {schema_name}: {set(payload) - allowed_fields}"
        )

    create_event_call = next(
        call
        for call in recorder.calls
        if (call["method"], call["path"])
        == ("POST", "/api/v1/athlete/{id}/events")
    )
    assert create_event_call["params"]["upsertOnUid"] is False
    assert payload_schemas_seen == {"EventEx", "CustomItem", "NewActivityMsg"}


def test_basic_api_key_configuration_matches_pinned_security(monkeypatch: Any) -> None:
    fixture = _load_fixture()
    api_key_scheme = fixture["security"]["schemes"]["APIKey"]
    assert api_key_scheme["type"] == "http"
    assert api_key_scheme["scheme"] == "basic"
    assert "Username is API_KEY" in api_key_scheme["description"]

    server_url = fixture["source"]["servers"][0]["url"]
    monkeypatch.setattr(
        api_client,
        "get_config",
        lambda: Config(
            api_key="configured-key",
            athlete_id=ATHLETE_ID,
            intervals_api_base_url=f"{server_url}/api/v1",
            user_agent="contract-test",
        ),
    )
    full_url, auth, _headers, error = api_client._prepare_request_config(
        "/activity/contract", "contract-key", "GET"
    )
    assert error is None
    assert full_url == f"{server_url}/api/v1/activity/contract"

    flow = auth.auth_flow(httpx.Request("GET", full_url))
    authenticated_request = next(flow)
    scheme, token = authenticated_request.headers["Authorization"].split(" ", 1)
    assert scheme == "Basic"
    assert base64.b64decode(token) == b"API_KEY:contract-key"


def _minimal_spec_from_fixture(fixture: dict[str, Any]) -> dict[str, Any]:
    source = fixture["source"]
    document: dict[str, Any] = {
        "openapi": source["openapi"],
        "info": {"title": source["title"], "version": source["version"]},
        "servers": deepcopy(source["servers"]),
        "security": deepcopy(fixture["security"]["root"]),
        "paths": {},
        "components": {
            "securitySchemes": deepcopy(fixture["security"]["schemes"]),
            "schemas": {},
        },
    }
    for name, schema in fixture["schemas"].items():
        projected_schema: dict[str, Any] = {
            "type": "object",
            "properties": {field: {} for field in schema["allowed_fields"]},
        }
        if schema["required_fields"]:
            projected_schema["required"] = list(schema["required_fields"])
        document["components"]["schemas"][name] = projected_schema
    document["components"]["schemas"].update(deepcopy(fixture["response_schemas"]))

    for operation in fixture["operations"]:
        path_item = document["paths"].setdefault(operation["path"], {})
        operation_object: dict[str, Any] = {
            "operationId": operation["operationId"],
            "parameters": [],
        }
        for parameter in operation["required_parameters"] + operation.get("optional_parameters", []):
            operation_object["parameters"].append(
                {
                    "in": parameter["in"],
                    "name": parameter["name"],
                    "required": parameter["required"],
                    "schema": deepcopy(parameter["schema"]),
                }
            )
        if "responses" in operation:
            operation_object["responses"] = deepcopy(operation["responses"])
        if "request_schema" in operation:
            operation_object["requestBody"] = {
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/" + operation["request_schema"]
                        }
                    }
                }
            }
        path_item[operation["method"].lower()] = operation_object
    return document


def test_checker_requires_explicit_hash_override_and_reports_semantic_drift(
    tmp_path: Path, capsys: Any
) -> None:
    fixture = _load_fixture()
    document = _minimal_spec_from_fixture(fixture)
    spec_path = tmp_path / "candidate-openapi.json"
    spec_path.write_text(json.dumps(document), encoding="utf-8")

    assert checker.main(["--spec", str(spec_path), "--fixture", str(FIXTURE_PATH)]) == 1
    assert "SHA256 mismatch" in capsys.readouterr().err

    assert (
        checker.main(
            [
                "--spec",
                str(spec_path),
                "--fixture",
                str(FIXTURE_PATH),
                "--allow-new-source-hash",
            ]
        )
        == 0
    )
    allowed_output = capsys.readouterr().out
    assert "source SHA256 changed" in allowed_output
    assert "pinned provenance was not updated" in allowed_output

    activities_parameters = document["paths"]["/api/v1/athlete/{id}/activities"][
        "get"
    ]["parameters"]
    oldest = next(parameter for parameter in activities_parameters if parameter["name"] == "oldest")
    oldest["schema"]["type"] = "integer"
    spec_path.write_text(json.dumps(document), encoding="utf-8")
    assert (
        checker.main(
            [
                "--spec",
                str(spec_path),
                "--fixture",
                str(FIXTURE_PATH),
                "--allow-new-source-hash",
            ]
        )
        == 1
    )
    drift_output = capsys.readouterr().err
    assert "selected OpenAPI surface drifted" in drift_output
    assert '"oldest"' in drift_output


@pytest.mark.parametrize("changed", ["message_id_type", "ack_id_type", "read_limit", "ack_response"])
def test_checker_pins_comment_identity_and_bounded_read_evidence(changed: str) -> None:
    fixture = _load_fixture()
    document = _minimal_spec_from_fixture(fixture)
    messages = document["paths"]["/api/v1/activity/{id}/messages"]
    if changed in {"message_id_type", "ack_id_type"}:
        name = "Message" if changed == "message_id_type" else "NewMsg"
        document["components"]["schemas"][name]["properties"]["id"]["type"] = "string"
    elif changed == "read_limit":
        limit = next(parameter for parameter in messages["get"]["parameters"] if parameter["name"] == "limit")
        limit["schema"]["default"] = 10
    else:
        messages["post"]["responses"]["200"]["content"]["*/*"]["schema"]["$ref"] = "#/components/schemas/Message"
    assert checker.project_spec(document, fixture["source"]["sha256"]) != fixture
