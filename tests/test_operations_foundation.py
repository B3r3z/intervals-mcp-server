import os
import subprocess
import sys

import pytest

from intervals_mcp_server.operations import (
    AccountWriteLock,
    OperationIntent,
    OperationJournal,
    OperationResult,
    WorkoutIntent,
    WriteResponse,
    event_fingerprint,
    external_id_for_session,
    intent_fingerprint,
    serialize_workout_event,
)


def structured(**kwargs):
    return WorkoutIntent(
        name="Intervals", start_date="2026-09-08", sport="Ride",
        representation="structured", steps=[{"duration": 60}], **kwargs,
    )


def result(intent, outcome="prepared"):
    return OperationResult(
        operation_uid=intent.operation_uid, session_uid=intent.session_uid,
        action=intent.action, outcome=outcome,
    )


def test_create_update_delete_shapes_and_zero_event_id():
    workout = structured()
    create = OperationIntent(operation_uid="op-create", action="create", session_uid="s", workout=workout)
    update = OperationIntent(operation_uid="op-update", action="update", session_uid="s", event_id=0, expected_fingerprint="f", workout=workout)
    delete = OperationIntent(operation_uid="op-delete", action="delete", session_uid="s", event_id=0, expected_fingerprint="f")
    assert (create.action, update.event_id, delete.event_id) == ("create", 0, 0)


@pytest.mark.parametrize("field", ["workout_text", "moving_time", "distance", "duration"])
def test_structured_reports_exact_conflicting_field(field):
    with pytest.raises(ValueError, match=field):
        structured(**{field: 1})


def test_native_text_conflict_and_strength_acceptance():
    with pytest.raises(ValueError, match="steps"):
        WorkoutIntent(name="x", start_date="2026-09-08", sport="Ride", representation="native_text", workout_text="x", steps=[])
    strength = WorkoutIntent(name="Strength", start_date="2026-09-08", sport="StrengthTraining", representation="unstructured_strength", description="gym", moving_time=1800)
    assert strength.category == "WORKOUT"


def test_run_is_rejected():
    with pytest.raises(ValueError, match="unsupported sport"):
        WorkoutIntent(
            name="Intervals", start_date="2026-09-08", sport="Run",
            representation="structured", steps=[{"duration": 60}],
        )


def test_uid_and_action_validation():
    with pytest.raises(ValueError):
        OperationIntent(operation_uid=" op", action="create", session_uid="s", workout=structured())
    with pytest.raises(ValueError):
        OperationIntent(operation_uid="op", action="delete", session_uid="s")


def test_external_id_and_serialization_are_deterministic():
    workout = structured()
    assert workout.timezone == "Europe/Warsaw"
    with pytest.raises(ValueError, match="IANA timezone"):
        WorkoutIntent.model_validate(
            {**workout.model_dump(), "timezone": "No/Such"}
        )
    assert external_id_for_session("session") == external_id_for_session("session")
    serialized = serialize_workout_event(workout, "ns:id")
    assert serialized == serialize_workout_event(workout, "ns:id")
    assert serialized["description"]
    assert serialized["start_date_local"].endswith("T00:00:00")


def test_fingerprints_normalize_missing_and_ignore_fetched_time():
    event = {"id": 1, "name": "x", "fetched_at": "a"}
    changed = {**event, "fetched_at": "b"}
    assert event_fingerprint(event) == event_fingerprint(changed)
    intent = OperationIntent(operation_uid="op", action="create", session_uid="s", workout=structured())
    assert intent_fingerprint("a", "d", intent) == intent_fingerprint("a", "d", intent)
    assert event_fingerprint(event).startswith("sha256:")


def test_serialization_representations_do_not_mix_fields():
    native = WorkoutIntent(
        name="Text", start_date="2026-09-08", sport="Ride",
        representation="native_text", workout_text="steady ride",
    )
    strength = WorkoutIntent(
        name="Gym", start_date="2026-09-08", sport="StrengthTraining",
        representation="unstructured_strength", description="lift", moving_time=600,
    )
    native_payload = serialize_workout_event(native)
    strength_payload = serialize_workout_event(strength)
    assert native_payload["description"] == "steady ride"
    assert "workout_doc" not in native_payload
    assert strength_payload["description"] == "lift"
    assert strength_payload["moving_time"] == 600


def test_structured_serialization_uses_parser_text():
    workout = structured(description="Warm up")
    payload = serialize_workout_event(workout)
    assert payload["description"].startswith("Warm up")
    assert "workout_doc" not in payload


def test_write_response_is_batch():
    intent = OperationIntent(operation_uid="op", action="create", session_uid="s", workout=structured())
    response = WriteResponse(status="ok", decision_uid="decision", results=[result(intent)])
    assert response.results[0].operation_uid == "op"


def test_journal_reload_session_search_and_account_isolation(tmp_path):
    intent = OperationIntent(operation_uid="op", action="create", session_uid="session", workout=structured())
    journal = OperationJournal("account-a", tmp_path)
    journal.save(intent, result(intent), decision_uid="decision")
    record = journal.load("op")
    assert record is not None and record.schema_version == "1.0"
    assert len(journal.find_by_session("session")) == 1
    assert list(OperationJournal("account-b", tmp_path).iter_records()) == []
    assert journal.load("../../escape") is None


def test_journal_stores_fingerprint_and_timestamps(tmp_path):
    intent = OperationIntent(operation_uid="op", action="create", session_uid="session", workout=structured())
    journal = OperationJournal("account", tmp_path)
    journal.save(intent, result(intent), decision_uid="d")
    record = journal.load("op")
    assert record is not None
    assert record.intent_fingerprint
    assert record.created_at and record.updated_at


def test_journal_update_preserves_created_at(tmp_path):
    intent = OperationIntent(operation_uid="op", action="create", session_uid="session", workout=structured())
    journal = OperationJournal("account", tmp_path)
    journal.save(intent, result(intent), decision_uid="d")
    first = journal.load("op")
    journal.save(intent, result(intent, "unknown"), decision_uid="d")
    second = journal.load("op")
    assert first is not None and second is not None
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at


def test_lock_same_directory_context_and_owner_release(tmp_path):
    first = AccountWriteLock("account", tmp_path)
    second = AccountWriteLock("account", tmp_path)
    with first:
        with pytest.raises(RuntimeError, match="WRITE_LOCKED"):
            second.acquire()
        second.release()
    assert not first.path.exists()


def test_lock_different_accounts_are_independent(tmp_path):
    first = AccountWriteLock("a", tmp_path)
    second = AccountWriteLock("b", tmp_path)
    first.acquire()
    second.acquire()
    first.release()
    second.release()


def test_lock_serializes_a_separate_process(tmp_path):
    env = dict(os.environ)
    env["INTERVALS_OPERATION_DIR"] = str(tmp_path)
    child_code = (
        "import sys; "
        "from intervals_mcp_server.operations import AccountWriteLock; "
        "lock=AccountWriteLock('shared'); lock.acquire(); "
        "print('ready', flush=True); sys.stdin.readline(); lock.release()"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", child_code],
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == "ready"
        with pytest.raises(RuntimeError, match="WRITE_LOCKED"):
            AccountWriteLock("shared", tmp_path).acquire()
    finally:
        if process.stdin is not None:
            process.stdin.write("\n")
            process.stdin.flush()
        process.wait(timeout=5)
    assert process.returncode == 0
