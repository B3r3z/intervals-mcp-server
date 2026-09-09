from types import SimpleNamespace

import pytest

from intervals_mcp_server.operations import (
    OperationIntent,
    OperationJournal,
    OperationResult,
    WorkoutIntent,
    event_fingerprint,
    external_id_for_session,
)
from intervals_mcp_server.tools import writes


def _workout(name: str = "Ride") -> WorkoutIntent:
    return WorkoutIntent(
        name=name,
        start_date="2026-09-08",
        sport="Ride",
        representation="native_text",
        workout_text="steady",
    )


def _create(uid: str, session: str, name: str = "Ride") -> OperationIntent:
    return OperationIntent(
        operation_uid=uid,
        action="create",
        session_uid=session,
        workout=_workout(name),
    )


def _event(
    event_id: int,
    session: str,
    name: str = "Ride",
    description: str = "steady",
) -> dict[str, object]:
    return {
        "id": event_id,
        "external_id": external_id_for_session(session),
        "category": "WORKOUT",
        "type": "Ride",
        "name": name,
        "start_date_local": "2026-09-08T00:00:00",
        "description": description,
        "workout_doc": {"steps": []},
    }


def _configure(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(
        writes,
        "get_config",
        lambda: SimpleNamespace(athlete_id="athlete", api_key="key"),
    )


@pytest.mark.asyncio
async def test_package_validation_reports_every_operation_without_http(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, tmp_path)

    async def must_not_call(*_args, **_kwargs):
        raise AssertionError("invalid package must not call HTTP")

    monkeypatch.setattr(writes, "make_intervals_request", must_not_call)
    operations = [_create("same", "one"), _create("same", "two")]
    duplicate = await writes.apply_workout_changes("decision", operations)
    invalid_decision = await writes.apply_workout_changes("", operations)

    assert len(duplicate.results) == 2
    assert {result.code for result in duplicate.results} == {
        "DUPLICATE_OPERATION_UID"
    }
    assert len(invalid_decision.results) == 2
    assert {result.code for result in invalid_decision.results} == {
        "INVALID_DECISION_UID"
    }


@pytest.mark.asyncio
async def test_partial_package_uses_one_lock_and_stops(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    acquired = 0
    released = 0

    class CountingLock:
        def __init__(self, _account):
            pass

        def acquire(self):
            nonlocal acquired
            acquired += 1

        def release(self):
            nonlocal released
            released += 1

    monkeypatch.setattr(writes, "AccountWriteLock", CountingLock)
    first = _create("op-a", "session-a", "A")
    current_b = _event(2, "session-b", "B old")
    second = OperationIntent(
        operation_uid="op-b",
        action="update",
        session_uid="session-b",
        event_id=2,
        expected_fingerprint="sha256:stale",
        workout=_workout("B new"),
    )
    third = _create("op-c", "session-c", "C")
    calls: list[tuple[str, str]] = []

    async def request(url, **kwargs):
        method = kwargs.get("method", "GET")
        calls.append((url, method))
        if method == "POST":
            return {"id": 1}
        if url.endswith("/1"):
            return _event(1, "session-a", "A")
        if url.endswith("/2"):
            return current_b
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes(
        "decision", [first, second, third]
    )

    assert acquired == released == 1
    assert [item.outcome for item in response.results] == [
        "confirmed",
        "conflict",
        "not_attempted",
    ]
    assert response.results[2].code == "PACKAGE_STOPPED"
    assert [method for _, method in calls] == ["GET", "POST", "GET", "GET"]


@pytest.mark.asyncio
async def test_create_preflight_requires_a_list(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    methods: list[str] = []

    async def request(_url, **kwargs):
        methods.append(kwargs.get("method", "GET"))
        return {"unexpected": True}

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes(
        "decision", [_create("op-preflight-shape", "session-preflight-shape")]
    )

    assert response.results[0].outcome == "unknown"
    assert response.results[0].code == "PREFLIGHT_INCOMPLETE"
    assert methods == ["GET"]


@pytest.mark.asyncio
async def test_successful_update_has_fresh_preflight_and_readback(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    current = _event(7, "session-update", "Old")
    intent = OperationIntent(
        operation_uid="op-update",
        action="update",
        session_uid="session-update",
        event_id=7,
        expected_fingerprint=event_fingerprint(current),
        workout=_workout("New"),
    )
    calls: list[str] = []

    async def request(_url, **kwargs):
        method = kwargs.get("method", "GET")
        calls.append(method)
        if method == "PUT":
            return {"id": 7}
        return current if len(calls) == 1 else _event(7, "session-update", "New")

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes("decision", [intent])

    assert response.results[0].outcome == "confirmed"
    assert response.results[0].prepared_at
    assert response.results[0].sent_at
    assert response.results[0].completed_at
    assert calls == ["GET", "PUT", "GET"]
    record = OperationJournal("athlete", tmp_path).load("op-update")
    assert record is not None
    assert record["result"]["prepared_at"]
    assert record["result"]["sent_at"]
    assert record["result"]["completed_at"]


@pytest.mark.asyncio
async def test_successful_delete_requires_404_and_account_list(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    current = _event(8, "session-delete")
    intent = OperationIntent(
        operation_uid="op-delete",
        action="delete",
        session_uid="session-delete",
        event_id=8,
        expected_fingerprint=event_fingerprint(current),
    )
    calls: list[str] = []

    async def request(_url, **kwargs):
        method = kwargs.get("method", "GET")
        calls.append(method)
        if len(calls) == 1:
            return current
        if method == "DELETE":
            return {}
        if len(calls) == 3:
            return {
                "error": True,
                "code": "HTTP_404",
                "http_status": 404,
                "message": "not found",
            }
        return []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes("decision", [intent])

    assert response.results[0].outcome == "confirmed"
    assert calls == ["GET", "DELETE", "GET", "GET"]


@pytest.mark.asyncio
async def test_delete_404_without_account_list_access_stays_unknown(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    current = _event(9, "session-delete-denied")
    intent = OperationIntent(
        operation_uid="op-delete-denied",
        action="delete",
        session_uid="session-delete-denied",
        event_id=9,
        expected_fingerprint=event_fingerprint(current),
    )
    calls = 0

    async def request(_url, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return current
        if kwargs.get("method", "GET") == "DELETE":
            return {}
        if calls == 3:
            return {
                "error": True,
                "code": "HTTP_404",
                "http_status": 404,
                "message": "not found",
            }
        return {
            "error": True,
            "code": "HTTP_403",
            "http_status": 403,
            "message": "forbidden",
        }

    monkeypatch.setattr(writes, "make_intervals_request", request)
    response = await writes.apply_workout_changes("decision", [intent])

    assert response.results[0].outcome == "unknown"
    assert response.results[0].code == "VERIFICATION_INCOMPLETE"


@pytest.mark.asyncio
async def test_uncertain_create_reconciles_without_second_mutation(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    intent = _create("op-timeout", "session-timeout")
    methods: list[str] = []

    async def timeout_request(_url, **kwargs):
        method = kwargs.get("method", "GET")
        methods.append(method)
        if method == "POST":
            return {
                "error": True,
                "code": "WRITE_TIMEOUT",
                "message": "timeout",
                "write_outcome": "unknown",
            }
        return []

    monkeypatch.setattr(writes, "make_intervals_request", timeout_request)
    first = await writes.apply_workout_changes("decision", [intent])
    assert first.results[0].outcome == "unknown"
    assert methods == ["GET", "POST"]

    async def must_not_call(*_args, **_kwargs):
        raise AssertionError("local status must not call HTTP")

    monkeypatch.setattr(writes, "make_intervals_request", must_not_call)
    local = await writes.get_write_status("op-timeout")
    assert local.historical_result.outcome == "unknown"

    reconcile_methods: list[str] = []

    async def reconcile_request(_url, **kwargs):
        reconcile_methods.append(kwargs.get("method", "GET"))
        return [_event(11, "session-timeout")]

    monkeypatch.setattr(writes, "make_intervals_request", reconcile_request)
    reconciled = await writes.get_write_status("op-timeout", reconcile=True)
    assert reconcile_methods == ["GET"]
    assert reconciled.historical_result.outcome == "unknown"
    assert reconciled.reconciliation_result is not None
    assert reconciled.reconciliation_result.outcome == "confirmed"

    monkeypatch.setattr(writes, "make_intervals_request", must_not_call)
    persisted = await writes.get_write_status("op-timeout")
    assert persisted.historical_result.outcome == "confirmed"


@pytest.mark.asyncio
async def test_uncertain_delete_reconciles_with_reads_only(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    current = _event(31, "session-delete-reconcile")
    intent = OperationIntent(
        operation_uid="op-delete-reconcile",
        action="delete",
        session_uid="session-delete-reconcile",
        event_id=31,
        expected_fingerprint=event_fingerprint(current),
    )
    methods: list[str] = []

    async def initial_request(_url, **kwargs):
        method = kwargs.get("method", "GET")
        methods.append(method)
        if method == "GET":
            return current
        return {
            "error": True,
            "code": "WRITE_TIMEOUT",
            "message": "timeout",
            "write_outcome": "unknown",
        }

    monkeypatch.setattr(writes, "make_intervals_request", initial_request)
    initial = await writes.apply_workout_changes("decision", [intent])
    assert initial.results[0].outcome == "unknown"
    assert initial.results[0].target_start_date == "2026-09-08"
    assert methods == ["GET", "DELETE"]

    methods.clear()

    async def reconcile_request(url, **kwargs):
        methods.append(kwargs.get("method", "GET"))
        if url.endswith("/31"):
            return {
                "error": True,
                "code": "HTTP_404",
                "http_status": 404,
                "message": "not found",
            }
        return []

    monkeypatch.setattr(writes, "make_intervals_request", reconcile_request)
    status = await writes.get_write_status("op-delete-reconcile", reconcile=True)

    assert status.reconciliation_result is not None
    assert status.reconciliation_result.outcome == "confirmed"
    assert methods == ["GET", "GET"]


@pytest.mark.asyncio
async def test_uncertain_create_absent_from_narrow_range_remains_unknown(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, tmp_path)
    intent = _create("op-moved", "session-moved")

    async def timeout_request(_url, **kwargs):
        if kwargs.get("method", "GET") == "POST":
            return {
                "error": True,
                "code": "WRITE_TIMEOUT",
                "message": "timeout",
                "write_outcome": "unknown",
            }
        return []

    monkeypatch.setattr(writes, "make_intervals_request", timeout_request)
    await writes.apply_workout_changes("decision", [intent])
    reconcile_methods: list[str] = []

    async def absent_request(_url, **kwargs):
        reconcile_methods.append(kwargs.get("method", "GET"))
        return []

    monkeypatch.setattr(writes, "make_intervals_request", absent_request)
    status = await writes.get_write_status("op-moved", reconcile=True)

    assert reconcile_methods == ["GET"]
    assert status.reconciliation_result is not None
    assert status.reconciliation_result.outcome == "unknown"
    assert status.reconciliation_result.code == "RECONCILIATION_INCOMPLETE"


@pytest.mark.asyncio
async def test_confirmed_replay_and_current_mismatch_never_mutate(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    intent = _create("op-confirmed", "session-confirmed")
    calls: list[str] = []

    async def create_request(url, **kwargs):
        method = kwargs.get("method", "GET")
        calls.append(method)
        if method == "POST":
            return {"id": 12}
        if url.endswith("/12"):
            return _event(12, "session-confirmed")
        return []

    monkeypatch.setattr(writes, "make_intervals_request", create_request)
    created = await writes.apply_workout_changes("decision", [intent])
    assert created.results[0].outcome == "confirmed"
    calls.clear()

    replay = await writes.apply_workout_changes("decision", [intent])
    assert replay.results[0].outcome == "confirmed"
    assert calls == []

    async def edited_request(_url, **kwargs):
        calls.append(kwargs.get("method", "GET"))
        return _event(12, "session-confirmed", name="Manual edit")

    monkeypatch.setattr(writes, "make_intervals_request", edited_request)
    status = await writes.get_write_status("op-confirmed", reconcile=True)
    assert calls == ["GET"]
    assert status.historical_result.outcome == "confirmed"
    assert status.reconciliation_result is not None
    assert status.reconciliation_result.outcome == "mismatch"


@pytest.mark.asyncio
async def test_in_flight_restart_and_corrupt_journal_fail_closed(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    intent = _create("op-crash", "session-crash")
    journal = OperationJournal("athlete", tmp_path)
    journal.save(
        intent,
        OperationResult(
            operation_uid=intent.operation_uid,
            session_uid=intent.session_uid,
            action="create",
            outcome="in_flight",
            external_id=external_id_for_session(intent.session_uid),
        ),
        "decision",
    )

    async def must_not_call(*_args, **_kwargs):
        raise AssertionError("unresolved journal state must not call HTTP")

    monkeypatch.setattr(writes, "make_intervals_request", must_not_call)
    restarted = await writes.apply_workout_changes("decision", [intent])
    assert restarted.results[0].code == "RECONCILIATION_REQUIRED"
    assert restarted.results[0].outcome == "unknown"

    corrupt = _create("op-corrupt", "session-corrupt")
    journal._path(corrupt.operation_uid).write_text("not-json", encoding="utf-8")
    blocked = await writes.apply_workout_changes("decision", [corrupt])
    assert blocked.results[0].code == "JOURNAL_CORRUPT"
    assert blocked.results[0].outcome == "unknown"


@pytest.mark.asyncio
async def test_invalid_package_inputs_and_lock_collision_are_structured(
    monkeypatch, tmp_path
):
    _configure(monkeypatch, tmp_path)
    invalid = await writes.apply_workout_changes("", [_create("a", "a")])
    assert invalid.results[0].code == "INVALID_DECISION_UID"
    empty = await writes.apply_workout_changes("decision", [])
    assert empty.results[0].code == "EMPTY_OPERATION_PACKAGE"

    held = writes.AccountWriteLock("athlete", tmp_path)
    held.acquire()
    try:
        collision = await writes.apply_workout_changes(
            "decision", [_create("b", "b"), _create("c", "c")]
        )
    finally:
        held.release()
    assert [item.outcome for item in collision.results] == [
        "rejected",
        "not_attempted",
    ]
    assert collision.results[0].code == "WRITE_LOCKED"
