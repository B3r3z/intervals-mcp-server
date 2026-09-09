from types import SimpleNamespace

import pytest

from intervals_mcp_server.operations import (
    OperationIntent,
    event_fingerprint,
)
from intervals_mcp_server.tools import writes


def workout():
    return {
        "name": "Planned ride",
        "start_date": "2026-09-08",
        "sport": "Ride",
        "representation": "native_text",
        "workout_text": "steady",
    }


def create_intent(uid="op-1", session="session-1"):
    return OperationIntent(
        operation_uid=uid,
        action="create",
        session_uid=session,
        workout=workout(),
    )


@pytest.mark.asyncio
async def test_create_uses_preflight_mutation_and_independent_readback(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(
        writes, "get_config", lambda: SimpleNamespace(athlete_id="athlete", api_key="key")
    )
    calls = []
    event = {
        "id": 10,
        "external_id": "tatra-v3:" + "",
        "category": "WORKOUT",
        "type": "Ride",
        "name": "Planned ride",
        "start_date_local": "2026-09-08T00:00:00",
        "description": "steady",
        "workout_doc": {"steps": []},
    }

    async def request(url, **kwargs):
        calls.append((url, kwargs.get("method", "GET")))
        if kwargs.get("method", "GET") == "POST":
            return {"id": 10}
        if url.endswith("/10"):
            return event
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    event["external_id"] = writes.external_id_for_session("session-1")
    response = await writes.apply_workout_changes("decision", [create_intent()])
    assert response.results[0].outcome == "confirmed"
    assert [method for _, method in calls] == ["GET", "POST", "GET"]


@pytest.mark.asyncio
async def test_create_replays_journal_without_mutation(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    calls = 0

    async def request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    first = await writes.apply_workout_changes("d", [create_intent()])
    second = await writes.apply_workout_changes("d", [create_intent()])
    assert first.results[0].code == "VERIFICATION_INCOMPLETE"
    assert second.results[0].code == "VERIFICATION_INCOMPLETE"
    assert calls == 2


@pytest.mark.asyncio
async def test_reused_operation_uid_with_changed_intent_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))

    async def request(*_args, **_kwargs):
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    await writes.apply_workout_changes("d", [create_intent()])
    changed = create_intent()
    changed.workout.name = "changed"
    response = await writes.apply_workout_changes("d", [changed])
    assert response.results[0].code == "OPERATION_ID_REUSED"


@pytest.mark.asyncio
async def test_multiple_operations_stop_after_first_unknown(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    called = False

    async def request(*_args, **_kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    response = await writes.apply_workout_changes("d", [create_intent("a"), create_intent("b")])
    assert called
    assert [result.outcome for result in response.results] == ["unknown", "not_attempted"]
    assert response.results[1].code == "PACKAGE_STOPPED"


def test_event_fingerprint_is_usable_for_update_approval():
    event = {"id": 1, "category": "WORKOUT", "type": "Ride", "name": "x"}
    assert event_fingerprint(event).startswith("sha256:")


def test_verification_rejects_missing_external_id_and_wrong_id():
    intent = create_intent()
    observed = {
        "id": 2,
        "category": "WORKOUT",
        "type": "Ride",
        "name": "Planned ride",
        "start_date_local": "2026-09-08T00:00:00",
        "description": "steady",
    }
    result = writes._verification(intent, observed, "expected", 1)
    assert result.outcome == "unknown"
    assert "external_id" in result.unavailable_fields


def test_verification_native_requires_parser_result():
    intent = create_intent()
    observed = {
        "id": 1,
        "external_id": writes.external_id_for_session("session-1"),
        "category": "WORKOUT",
        "type": "Ride",
        "name": "Planned ride",
        "start_date_local": "2026-09-08T00:00:00",
        "description": "steady",
    }
    result = writes._verification(intent, observed, observed["external_id"], 1)
    assert result.code == "VERIFICATION_INCOMPLETE"


def test_verification_strength_checks_optional_moving_time():
    from intervals_mcp_server.operations import WorkoutIntent

    intent = OperationIntent(
        operation_uid="strength",
        action="create",
        session_uid="gym",
        workout=WorkoutIntent(
            name="Gym",
            start_date="2026-09-08",
            sport="StrengthTraining",
            representation="unstructured_strength",
            description="lift",
            moving_time=600,
        ),
    )
    ext = writes.external_id_for_session("gym")
    observed = {
        "id": 4,
        "external_id": ext,
        "category": "WORKOUT",
        "type": "StrengthTraining",
        "name": "Gym",
        "start_date_local": "2026-09-08T00:00:00",
        "description": "lift",
        "moving_time": 600,
    }
    assert writes._verification(intent, observed, ext, 4).outcome == "confirmed"
