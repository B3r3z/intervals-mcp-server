from types import SimpleNamespace

import pytest

from intervals_mcp_server.operations import OperationIntent, WorkoutIntent, event_fingerprint
from intervals_mcp_server.tools import writes


def intent(action="create", uid="flow", session="flow-session", **kwargs):
    workout = WorkoutIntent(
        name="Ride",
        start_date="2026-09-08",
        sport="Ride",
        representation="native_text",
        workout_text="steady",
    )
    return OperationIntent(
        operation_uid=uid,
        action=action,
        session_uid=session,
        workout=workout if action != "delete" else None,
        event_id=kwargs.get("event_id"),
        expected_fingerprint=kwargs.get("expected"),
    )


def observed(i, event_id=1, **changes):
    row = {
        "id": event_id,
        "external_id": writes.external_id_for_session(i.session_uid),
        "category": "WORKOUT",
        "type": "Ride",
        "name": "Ride",
        "start_date_local": "2026-09-08T00:00:00",
        "description": "steady",
        "workout_doc": {"steps": []},
    }
    row.update(changes)
    return row


@pytest.mark.parametrize("changes", [{"external_id": "bad"}, {"name": "other"}, {"id": 2}])
def test_create_readback_mismatch_is_fail_closed(monkeypatch, changes):
    i = intent()
    result = writes._verification(
        i, observed(i, **changes), writes.external_id_for_session(i.session_uid), 1
    )
    assert result.outcome in {"mismatch", "unknown"}


def test_structured_dropped_step_is_mismatch():
    i = intent()
    i.workout.representation = "structured"
    i.workout.workout_text = None
    i.workout.steps = [{"duration": 10}]
    result = writes._verification(
        i, observed(i, workout_doc={"steps": []}), writes.external_id_for_session(i.session_uid), 1
    )
    assert result.code == "VERIFICATION_MISMATCH"


def test_structured_missing_duration_is_unknown():
    i = intent()
    i.workout.representation = "structured"
    i.workout.workout_text = None
    i.workout.steps = [{"duration": 10}]
    result = writes._verification(
        i,
        observed(
            i,
            description="- 10s \n",
            workout_doc={"steps": [{"duration": 10}]},
        ),
        writes.external_id_for_session(i.session_uid),
        1,
    )
    assert result.code == "VERIFICATION_INCOMPLETE"


def test_native_missing_parser_is_unknown():
    i = intent()
    result = writes._verification(
        i, observed(i, workout_doc=None), writes.external_id_for_session(i.session_uid), 1
    )
    assert result.outcome == "unknown"


def test_strength_without_parser_can_confirm():
    i = intent()
    i.workout.sport = "StrengthTraining"
    i.workout.representation = "unstructured_strength"
    i.workout.workout_text = None
    i.workout.description = "lift"
    i.workout.moving_time = 600
    row = observed(i, type="StrengthTraining", description="lift", moving_time=600)
    assert writes._verification(i, row, row["external_id"], 1).outcome == "confirmed"


def test_wrong_id_is_mismatch_not_missing():
    i = intent()
    result = writes._verification(
        i, observed(i, 9), writes.external_id_for_session(i.session_uid), 1
    )
    assert result.code == "VERIFICATION_MISMATCH"


def test_null_mandatory_is_unknown():
    i = intent()
    result = writes._verification(
        i, observed(i, description=None), writes.external_id_for_session(i.session_uid), 1
    )
    assert result.code == "VERIFICATION_INCOMPLETE"


def test_target_fingerprint_conflict_is_detected():
    i = intent("update", event_id=1, expected="sha256:expected")
    assert event_fingerprint(observed(i)) != i.expected_fingerprint


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
    response = await writes.apply_workout_changes("d", [intent(uid="a"), intent(uid="b")])
    assert called
    assert [result.outcome for result in response.results] == ["unknown", "not_attempted"]
    assert response.results[1].code == "PACKAGE_STOPPED"


@pytest.mark.asyncio
async def test_empty_operation_is_rejected_without_http(monkeypatch):
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    response = await writes.apply_workout_changes("decision", [])
    assert response.results[0].code == "EMPTY_OPERATION_PACKAGE"


@pytest.mark.asyncio
async def test_missing_config_is_structured(monkeypatch):
    called = False
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="", api_key=""))

    async def request(*_args, **_kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes("decision", [intent(uid="config")])
    assert response.results[0].code == "CONFIGURATION_ERROR" and not called


@pytest.mark.asyncio
async def test_wrong_target_is_rejected_before_mutation(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    calls = []

    async def request(url, **kwargs):
        calls.append(kwargs.get("method", "GET"))
        return {"id": 9, "category": "ACTIVITY", "external_id": "other"}

    monkeypatch.setattr(writes, "make_intervals_request", request)
    update = intent("update", uid="wrong", event_id=1, expected="sha256:x")
    response = await writes.apply_workout_changes("decision", [update])
    assert response.results[0].code == "OUT_OF_SCOPE" and calls == ["GET"]


@pytest.mark.asyncio
async def test_create_remote_duplicates_are_ambiguous(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    i = intent(uid="ambiguous")
    row = observed(i)

    async def request(*_args, **_kwargs):
        return [row, dict(row, id=2)]

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes("decision", [i])
    assert response.results[0].code == "AMBIGUOUS_SESSION"


@pytest.mark.asyncio
async def test_lock_collision_has_no_http(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(writes, "get_config", lambda: SimpleNamespace(athlete_id="a", api_key="k"))
    held = writes.AccountWriteLock("a", tmp_path)
    held.acquire()
    try:

        async def request(*_args, **_kwargs):
            raise AssertionError("HTTP must not run")

        monkeypatch.setattr(writes, "make_intervals_request", request)
        response = await writes.apply_workout_changes("decision", [intent(uid="locked")])
        assert response.results[0].code == "WRITE_LOCKED"
    finally:
        held.release()
