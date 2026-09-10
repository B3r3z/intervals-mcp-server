"""Corrupt durable history must never authorize replay or an upstream request."""

import json
from types import SimpleNamespace

import pytest

from intervals_mcp_server.operations import (
    JournalCorruptError,
    OperationIntent,
    OperationJournal,
    OperationResult,
    WorkoutIntent,
    external_id_for_session,
    intent_fingerprint,
)
from intervals_mcp_server.tools import writes


def _intent(uid: str = "recorded-op") -> OperationIntent:
    return OperationIntent(
        operation_uid=uid,
        session_uid="recorded-session",
        action="create",
        workout=WorkoutIntent(
            name="Ride",
            start_date="2026-09-10",
            sport="Ride",
            representation="native_text",
            workout_text="steady",
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("reader", ["replay", "status", "reconcile", "session_lookup", "save"])
@pytest.mark.parametrize(
    "corruption",
    [
        "result_operation_uid",
        "result_session_uid",
        "result_action",
        "incomplete_result",
        "invalid_intent",
        "changed_intent",
        "changed_decision",
        "wrong_fingerprint",
        "wrong_result_fingerprint",
        "unsupported_version",
        "changed_account",
        "missing_account",
    ],
)
async def test_inconsistent_history_is_a_structured_error_before_http(
    monkeypatch, tmp_path, reader, corruption
):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(
        writes, "get_config", lambda: SimpleNamespace(athlete_id="athlete", api_key="test")
    )

    async def no_http(*_args, **_kwargs):
        pytest.fail("corrupt history must be rejected before any upstream request")

    monkeypatch.setattr(writes, "make_intervals_request", no_http)
    intent = _intent()
    journal = OperationJournal("athlete", tmp_path)
    journal.save(
        intent,
        OperationResult(
            operation_uid=intent.operation_uid,
            session_uid=intent.session_uid,
            action="create",
            outcome="confirmed",
            event_id=42,
            external_id=external_id_for_session(intent.session_uid),
        ),
        "decision",
    )
    path = next(tmp_path.glob("*.json"))
    record = json.loads(path.read_text(encoding="utf-8"))
    if corruption.startswith("result_"):
        field = corruption.removeprefix("result_")
        record["result"][field] = "update" if field == "action" else "different-identity"
    elif corruption == "incomplete_result":
        record["result"] = {"outcome": "confirmed"}
    elif corruption == "invalid_intent":
        record["intent"] = None
    elif corruption == "changed_intent":
        record["intent"]["workout"]["name"] = "Changed intent"
    elif corruption == "changed_decision":
        record["decision_uid"] = "other-decision"
    elif corruption == "wrong_fingerprint":
        record["intent_fingerprint"] = "sha256:" + "0" * 64
    elif corruption == "wrong_result_fingerprint":
        record["result"]["intent_fingerprint"] = "sha256:" + "0" * 64
    elif corruption == "changed_account":
        record["account"] = "other-account"
    elif corruption == "missing_account":
        del record["account"]
    else:
        record["schema_version"] = "2.0"
    path.write_text(json.dumps(record), encoding="utf-8")
    corrupt_bytes = path.read_bytes()

    if reader == "save":
        with pytest.raises(JournalCorruptError):
            journal.save(
                intent,
                OperationResult(
                    operation_uid=intent.operation_uid,
                    session_uid=intent.session_uid,
                    action="create",
                    outcome="unknown",
                ),
                "decision",
            )
        assert path.read_bytes() == corrupt_bytes
        return
    if reader in {"replay", "session_lookup"}:
        response = await writes.apply_workout_changes(
            "decision", [intent if reader == "replay" else _intent("next-op")]
        )
        result = response.results[0]
        assert result.operation_uid == (intent.operation_uid if reader == "replay" else "next-op")
    else:
        status = await writes.get_write_status(intent.operation_uid, reconcile=reader == "reconcile")
        result = status.historical_result
        assert status.status == "error"
        assert status.reconciliation_result is None
        assert result.operation_uid == intent.operation_uid

    assert result.code == "JOURNAL_CORRUPT"
    assert result.outcome == "unknown"
    assert path.read_bytes() == corrupt_bytes


@pytest.mark.parametrize("decision", [None, ""])
@pytest.mark.parametrize("outcome", ["prepared", "in_flight"])
def test_version_one_history_without_optional_result_fields_remains_readable(
    tmp_path, decision, outcome
):
    intent = _intent()
    journal = OperationJournal("athlete", tmp_path)
    # The previous schema allows interrupted results without timestamps or
    # result fingerprints. Loading them must not migrate or enrich the file.
    payload = {
        "schema_version": "1.0",
        "account": "athlete",
        "decision_uid": decision,
        "intent_fingerprint": intent_fingerprint("athlete", decision or "", intent),
        "intent": intent.model_dump(mode="json"),
        "result": {
            "operation_uid": intent.operation_uid,
            "session_uid": intent.session_uid,
            "action": "create",
            "outcome": outcome,
            "event_id": 0,
        },
        "created_at": "2026-09-09T12:00:00+00:00",
        "updated_at": "2026-09-09T12:00:00+00:00",
    }
    path = journal._path(intent.operation_uid)
    path.write_text(json.dumps(payload), encoding="utf-8")
    original = path.read_bytes()
    record = journal.load(intent.operation_uid)
    assert record is not None
    assert record.decision_uid == decision
    assert record.result.outcome == outcome
    assert record.result.prepared_at is None and record.result.sent_at is None
    assert record.result.intent_fingerprint is None
    assert record.result.event_id == 0
    assert journal.find_by_session(intent.session_uid) == [record]
    assert path.read_bytes() == original


def test_save_returns_preserved_result_without_mutating_input_or_history(tmp_path):
    create = _intent()
    intent = OperationIntent(
        operation_uid=create.operation_uid,
        session_uid=create.session_uid,
        action="update",
        event_id=0,
        expected_fingerprint="before",
        workout=create.workout,
    )
    journal = OperationJournal("athlete", tmp_path)
    preserved = {
        "prepared_at": "2026-09-09T12:00:00+00:00",
        "sent_at": "2026-09-09T12:00:01+00:00",
        "event_id": 0,
        "external_id": "previous-namespace:identity",
        "intent_fingerprint": intent_fingerprint("athlete", "decision", intent),
        "expected_fingerprint": "before",
        "target_start_date": "2026-09-09",
    }
    journal.save(
        intent,
        OperationResult(
            operation_uid=intent.operation_uid,
            session_uid=intent.session_uid,
            action="update",
            outcome="in_flight",
            **preserved,
        ),
        "decision",
    )
    historical = journal.load(intent.operation_uid)
    incoming = OperationResult(
        operation_uid=intent.operation_uid,
        session_uid=intent.session_uid,
        action="update",
        outcome="unknown",
    )
    original_input = incoming.model_dump()
    saved = journal.save(intent, incoming, "decision")
    assert incoming.model_dump() == original_input
    assert all(getattr(saved, field) == value for field, value in preserved.items())
    assert historical is not None and historical.result.outcome == "in_flight"

    # A returned wrong target is real mismatch evidence, not corrupt identity.
    observed = incoming.model_copy(update={"outcome": "mismatch", "event_id": 99})
    persisted = journal.save(intent, observed, "decision")
    assert persisted.event_id == 99
    assert persisted.external_id == preserved["external_id"]


@pytest.mark.parametrize("change", ["intent", "decision", "result_identity"])
def test_save_cannot_rebind_or_replace_existing_history(tmp_path, change):
    intent = _intent()
    result = OperationResult(
        operation_uid=intent.operation_uid,
        session_uid=intent.session_uid,
        action="create",
        outcome="in_flight",
    )
    journal = OperationJournal("athlete", tmp_path)
    journal.save(intent, result, "decision")
    path = next(tmp_path.glob("*.json"))
    original = path.read_bytes()
    changed_intent = intent.model_copy(update={"session_uid": "different"}) if change == "intent" else intent
    changed_result = result.model_copy(update={"session_uid": "different"}) if change == "result_identity" else result
    with pytest.raises(JournalCorruptError):
        journal.save(changed_intent, changed_result, "other" if change == "decision" else "decision")
    assert path.read_bytes() == original


def test_session_lookup_skips_another_accounts_nested_record(tmp_path):
    other = OperationJournal("other", tmp_path)
    other._path("other-op").write_text(
        json.dumps({"account": "other", "intent": None, "result": None}), encoding="utf-8"
    )
    assert OperationJournal("athlete", tmp_path).find_by_session("recorded-session") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["corruption", "io_error"])
async def test_reconciliation_preserves_observations_when_persistence_fails(
    monkeypatch, tmp_path, failure
):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(
        writes, "get_config", lambda: SimpleNamespace(athlete_id="athlete", api_key="test")
    )
    intent = _intent()
    journal = OperationJournal("athlete", tmp_path)
    historical = OperationResult(
        operation_uid=intent.operation_uid,
        session_uid=intent.session_uid,
        action="create",
        outcome="unknown",
        event_id=0,
        external_id=external_id_for_session(intent.session_uid),
    )
    journal.save(intent, historical, "decision")
    path = next(tmp_path.glob("*.json"))
    event = {
        "id": 0,
        "external_id": historical.external_id,
        "category": "WORKOUT",
        "type": "Ride",
        "name": "Ride",
        "start_date_local": "2026-09-10T00:00:00",
        "description": "steady",
        "workout_doc": {"steps": []},
    }
    calls = []

    async def readback(url, **kwargs):
        calls.append((url, kwargs.get("method", "GET")))
        assert url.endswith("/events/0")
        if failure == "corruption":
            path.write_text("not-json", encoding="utf-8")
        return event

    def unavailable(*_args, **_kwargs):
        raise OSError("synthetic persistence failure")

    monkeypatch.setattr(writes, "make_intervals_request", readback)
    if failure == "io_error":
        monkeypatch.setattr(OperationJournal, "save", unavailable)
    status = await writes.get_write_status(intent.operation_uid, reconcile=True)
    assert len(calls) == 1 and calls[0][1] == "GET"
    assert status.historical_result == historical
    assert status.current_observation == event
    assert status.reconciliation_result is not None
    assert status.reconciliation_result.outcome == "unknown"
    assert status.reconciliation_result.code == (
        "JOURNAL_CORRUPT" if failure == "corruption" else "JOURNAL_WRITE_FAILED"
    )
    assert status.reconciliation_result.diagnostics["read_back_outcome"] == "confirmed"


def test_load_rejects_a_valid_record_copied_under_another_operation(tmp_path):
    intent = _intent()
    journal = OperationJournal("athlete", tmp_path)
    journal.save(intent, OperationResult(
        operation_uid=intent.operation_uid,
        session_uid=intent.session_uid,
        action="create",
        outcome="prepared",
    ))
    journal._path("another-op").write_bytes(journal._path(intent.operation_uid).read_bytes())
    with pytest.raises(JournalCorruptError):
        journal.load("another-op")
