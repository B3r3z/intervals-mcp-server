"""Verified single-operation workout writes.

This module deliberately performs no batching and never retries a mutation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.operations import (
    AccountWriteLock,
    JournalCorruptError,
    OperationIntent,
    OperationJournal,
    OperationResult,
    WriteResponse,
    WriteStatusResponse,
    event_fingerprint,
    external_id_for_session,
    intent_fingerprint,
    serialize_workout_event,
    SPORTS,
)


Outcome = Literal[
    "confirmed",
    "rejected",
    "conflict",
    "unknown",
    "mismatch",
    "not_attempted",
    "prepared",
    "in_flight",
]


def _result(intent: OperationIntent, outcome: Outcome, **fields: Any) -> OperationResult:
    now = datetime.now(timezone.utc).isoformat()
    if outcome == "prepared" and "prepared_at" not in fields:
        fields["prepared_at"] = now
    if outcome not in {"prepared", "in_flight"} and "completed_at" not in fields:
        fields["completed_at"] = now
    return OperationResult(
        operation_uid=intent.operation_uid,
        session_uid=intent.session_uid,
        action=intent.action,
        outcome=outcome,
        **fields,
    )


def _error_result(
    intent: OperationIntent, code: str, message: str, outcome: Outcome = "rejected", **fields: Any
) -> OperationResult:
    return _result(intent, outcome, code=code, message=message, **fields)


def _api_error(result: Any) -> tuple[str, str, dict[str, Any]] | None:
    if not isinstance(result, dict) or not result.get("error"):
        return None
    return (
        str(result.get("code", "UPSTREAM_ERROR")),
        str(result.get("message", "upstream request failed")),
        {
            key: result[key]
            for key in ("http_status", "status_code", "phase", "write_outcome")
            if key in result
        },
    )


def _result_from_api_error(
    intent: OperationIntent,
    result: dict[str, Any],
    *,
    sent: bool,
    external_id: str | None = None,
    fingerprint: str | None = None,
    event_id: Any = None,
) -> OperationResult:
    code = str(result.get("code", "UPSTREAM_ERROR"))
    outcome: Outcome = (
        "rejected" if not sent or result.get("write_outcome") == "rejected" else "unknown"
    )
    return _result(
        intent,
        outcome,
        code=code,
        message=str(result.get("message", "upstream request failed")),
        event_id=event_id,
        external_id=external_id,
        intent_fingerprint=fingerprint,
        sent_at=datetime.now(timezone.utc).isoformat() if sent else None,
        diagnostics={
            key: result[key]
            for key in (
                "phase",
                "http_status",
                "status_code",
                "write_outcome",
                "recommended_action",
            )
            if key in result
        },
    )


def _same_event(event: dict[str, Any], _intent: OperationIntent, external_id: str) -> bool:
    return event.get("external_id") == external_id


def _step_differences(expected: Any, actual: Any, path: str = "steps") -> list[dict[str, Any]]:
    supported = {
        "duration",
        "distance",
        "until_lap_press",
        "reps",
        "warmup",
        "cooldown",
        "intensity",
        "ramp",
        "freeride",
        "maxeffort",
        "power",
        "hr",
        "pace",
        "cadence",
        "hidepower",
        "text",
        "steps",
    }
    if isinstance(expected, list) and isinstance(actual, list):
        differences = []
        if len(expected) != len(actual):
            differences.append({"field": path, "expected": len(expected), "actual": len(actual)})
        for index, item in enumerate(expected[: len(actual)]):
            differences.extend(_step_differences(item, actual[index], f"{path}[{index}]"))
        return differences
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for field in sorted(supported & (set(expected) | set(actual))):
            differences.extend(
                _step_differences(expected.get(field), actual.get(field), f"{path}.{field}")
            )
        return differences
    return [] if expected == actual else [{"field": path, "expected": expected, "actual": actual}]


def _timed_duration(steps: Any) -> int | None:
    if not isinstance(steps, list):
        return None
    total = 0
    for step in steps:
        if not isinstance(step, dict):
            return None
        if isinstance(step.get("steps"), list):
            nested = _timed_duration(step["steps"])
            if nested is None:
                return None
            total += nested * int(step.get("reps", 1))
        elif step.get("duration") is not None:
            total += int(step["duration"])
        else:
            return None
    return total


def _verification(
    intent: OperationIntent,
    observed: Any,
    external_id: str,
    expected_event_id: Any = None,
) -> OperationResult:
    if not isinstance(observed, dict):
        return _error_result(
            intent,
            "VERIFICATION_INCOMPLETE",
            "verification response is not an event",
            "unknown",
            event_found=False,
            diagnostics={"phase": "verification"},
        )
    required = {"id", "external_id", "category", "type", "name", "start_date_local", "description"}
    missing = sorted(
        field for field in required if field not in observed or observed[field] is None
    )
    if missing:
        return _error_result(
            intent,
            "VERIFICATION_INCOMPLETE",
            "required fields missing: " + ", ".join(missing),
            "unknown",
            event_id=observed.get("id"),
            event_found=True,
            unavailable_fields=missing,
            actual_fingerprint=event_fingerprint(observed),
            checked_fields=sorted(required - set(missing)),
        )
    expected = serialize_workout_event(intent.workout, external_id) if intent.workout else {}
    differences: list[dict[str, Any]] = []
    checked_fields = [
        "id",
        "external_id",
        "category",
        "type",
        "name",
        "start_date_local",
        "description",
    ]
    if str(observed.get("id")) != str(expected_event_id) and expected_event_id is not None:
        differences.append(
            {"field": "id", "expected": expected_event_id, "actual": observed.get("id")}
        )
    for field in ("external_id", "category", "type", "name", "start_date_local", "description"):
        if observed.get(field) != expected.get(field):
            differences.append(
                {"field": field, "expected": expected.get(field), "actual": observed.get(field)}
            )
    doc = observed.get("workout_doc")
    if intent.workout and intent.workout.representation == "structured":
        if not isinstance(doc, dict) or not isinstance(doc.get("steps"), list):
            return _error_result(
                intent,
                "VERIFICATION_INCOMPLETE",
                "structured workout_doc is unavailable",
                "unknown",
                event_id=observed.get("id"),
                event_found=True,
                unavailable_fields=["workout_doc.steps"],
                actual_fingerprint=event_fingerprint(observed),
                checked_fields=checked_fields,
            )
        differences.extend(_step_differences(intent.workout.steps, doc.get("steps")))
        duration = _timed_duration(intent.workout.steps)
        if duration is not None and not differences:
            if doc.get("duration") is None:
                return _error_result(
                    intent,
                    "VERIFICATION_INCOMPLETE",
                    "workout_doc.duration is unavailable",
                    "unknown",
                    event_id=observed.get("id"),
                    event_found=True,
                    unavailable_fields=["workout_doc.duration"],
                    actual_fingerprint=event_fingerprint(observed),
                    checked_fields=checked_fields,
                )
            if doc.get("duration") != duration:
                differences.append(
                    {
                        "field": "workout_doc.duration",
                        "expected": duration,
                        "actual": doc.get("duration"),
                    }
                )
    elif (
        intent.workout
        and intent.workout.representation == "native_text"
        and (not isinstance(doc, dict) or not isinstance(doc.get("steps"), list))
    ):
        return _error_result(
            intent,
            "VERIFICATION_INCOMPLETE",
            "native workout_doc parser result is unavailable",
            "unknown",
            event_id=observed.get("id"),
            event_found=True,
            unavailable_fields=["workout_doc.steps"],
            actual_fingerprint=event_fingerprint(observed),
            checked_fields=checked_fields,
        )
    elif intent.workout and intent.workout.representation == "unstructured_strength":
        if (
            intent.workout.moving_time is not None
            and observed.get("moving_time") != intent.workout.moving_time
        ):
            differences.append(
                {
                    "field": "moving_time",
                    "expected": intent.workout.moving_time,
                    "actual": observed.get("moving_time"),
                }
            )
        checked_fields.append("moving_time")
    if differences:
        return _error_result(
            intent,
            "VERIFICATION_MISMATCH",
            "verified event differs from intent",
            "mismatch",
            event_id=observed.get("id"),
            event_found=True,
            differences=differences,
            actual_fingerprint=event_fingerprint(observed),
            checked_fields=checked_fields,
        )
    return _result(
        intent,
        "confirmed",
        event_id=observed.get("id"),
        external_id=external_id,
        event_found=True,
        checked_fields=checked_fields,
    )


async def _read_event(aid: str, event_id: Any, api_key: str) -> Any:
    return await make_intervals_request(
        f"/athlete/{aid}/events/{event_id}", api_key=api_key, method="GET"
    )


def _response_status(result: OperationResult) -> Literal["ok", "partial", "error"]:
    if result.outcome == "confirmed":
        return "ok"
    if result.outcome in {"unknown", "mismatch", "prepared", "in_flight"}:
        return "partial"
    return "error"


def _package_status(
    results: list[OperationResult],
) -> Literal["ok", "partial", "error"]:
    if results and all(result.outcome == "confirmed" for result in results):
        return "ok"
    if any(result.outcome == "confirmed" for result in results) or any(
        result.outcome in {"unknown", "mismatch", "prepared", "in_flight"}
        for result in results
    ):
        return "partial"
    return "error"


def _in_flight(
    intent: OperationIntent,
    external_id: str,
    fingerprint: str,
    *,
    event_id: Any = None,
    expected_fingerprint: str | None = None,
    target_start_date: str | None = None,
) -> OperationResult:
    return _result(
        intent,
        "in_flight",
        event_id=event_id,
        external_id=external_id,
        intent_fingerprint=fingerprint,
        expected_fingerprint=expected_fingerprint,
        target_start_date=target_start_date,
        sent_at=datetime.now(timezone.utc).isoformat(),
    )


async def _apply_workout_change(
    decision_uid: str,
    operations: list[OperationIntent],
    *,
    _lock_held: bool = False,
) -> WriteResponse:
    """Apply one validated workout operation with read-back verification."""
    config = get_config()
    if not decision_uid.strip():
        return WriteResponse(status="error", decision_uid=decision_uid, results=[])
    if len(operations) != 1:
        op = (
            operations[0]
            if operations
            else OperationIntent.model_construct(
                operation_uid="not_attempted", session_uid="not_attempted", action="create"
            )
        )
        return WriteResponse(
            status="error",
            decision_uid=decision_uid,
            results=[
                _error_result(
                    op, "MULTIPLE_OPERATIONS_NOT_SUPPORTED", "exactly one operation is required"
                )
            ],
        )
    if not config.athlete_id or not config.api_key:
        result = _error_result(
            operations[0], "CONFIGURATION_ERROR", "ATHLETE_ID and API_KEY are required"
        )
        return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
    journal = OperationJournal(config.athlete_id)
    intent = operations[0]
    fingerprint = intent_fingerprint(config.athlete_id, decision_uid, intent)
    lock: AccountWriteLock | None = None
    if not _lock_held:
        lock = AccountWriteLock(config.athlete_id)
        try:
            lock.acquire()
        except RuntimeError:
            result = _error_result(
                intent, "WRITE_LOCKED", "another write is in progress", "rejected"
            )
            return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
    try:
        historical = journal.load(intent.operation_uid)
        if historical:
            if historical.get("intent_fingerprint") == fingerprint:
                historical_result = OperationResult.model_validate(historical["result"])
                if historical_result.outcome in {"prepared", "in_flight"}:
                    historical_result = _error_result(
                        intent,
                        "RECONCILIATION_REQUIRED",
                        "operation was interrupted before completion",
                        "unknown",
                        external_id=historical_result.external_id,
                        intent_fingerprint=fingerprint,
                        diagnostics={"replayed_outcome": historical_result.outcome},
                    )
                    journal.save(intent, historical_result, decision_uid)
                return WriteResponse(
                    status=_response_status(historical_result),
                    decision_uid=decision_uid,
                    results=[historical_result],
                )
            return WriteResponse(
                status="error",
                decision_uid=decision_uid,
                results=[
                    _error_result(
                        intent,
                        "OPERATION_ID_REUSED",
                        "operation UID was used with a different intent",
                    )
                ],
            )
        ext = external_id_for_session(intent.session_uid)
        if intent.action == "create":
            for record in journal.find_by_session(intent.session_uid):
                prior = record.get("result", {})
                if prior.get("outcome") == "confirmed":
                    result = _error_result(
                        intent,
                        "SESSION_ALREADY_EXISTS",
                        "session already has a confirmed operation",
                        "conflict",
                        external_id=ext,
                    )
                    return WriteResponse(
                        status=_response_status(result), decision_uid=decision_uid, results=[result]
                    )
                elif prior.get("outcome") in {"prepared", "in_flight", "unknown", "mismatch"}:
                    result = _error_result(
                        intent,
                        "SESSION_RECONCILIATION_REQUIRED",
                        "session has an unfinished operation",
                        "unknown",
                        external_id=ext,
                    )
                    return WriteResponse(
                        status=_response_status(result), decision_uid=decision_uid, results=[result]
                    )
                continue
            start = intent.workout.start_date if intent.workout else ""
            existing = await make_intervals_request(
                f"/athlete/{config.athlete_id}/events",
                api_key=config.api_key,
                params={"oldest": start, "newest": start},
            )
            if _api_error(existing) and isinstance(existing, dict):
                result = _result_from_api_error(
                    intent, existing, sent=False, external_id=ext, fingerprint=fingerprint
                )
                journal.save(intent, result, decision_uid)
                return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
            if not isinstance(existing, list):
                result = _error_result(
                    intent,
                    "PREFLIGHT_INCOMPLETE",
                    "event lookup response was not a list",
                    "unknown",
                    external_id=ext,
                    intent_fingerprint=fingerprint,
                )
                journal.save(intent, result, decision_uid)
                return WriteResponse(
                    status=_response_status(result),
                    decision_uid=decision_uid,
                    results=[result],
                )
            matches = (
                [row for row in existing if isinstance(row, dict) and _same_event(row, intent, ext)]
                if isinstance(existing, list)
                else []
            )
            if len(matches) > 1:
                result = _error_result(
                    intent,
                    "AMBIGUOUS_SESSION",
                    "multiple events have the session external ID",
                    "conflict",
                    external_id=ext,
                )
                journal.save(intent, result, decision_uid)
                return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
            if matches:
                result = _error_result(
                    intent,
                    "SESSION_ALREADY_EXISTS",
                    "session already has an event",
                    "conflict",
                    event_id=matches[0].get("id"),
                )
                journal.save(intent, result, decision_uid)
                return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
            prepared = _result(intent, "prepared", external_id=ext, intent_fingerprint=fingerprint)
            journal.save(intent, prepared, decision_uid)
            assert intent.workout is not None
            inflight = _in_flight(intent, ext, fingerprint)
            journal.save(intent, inflight, decision_uid)
            mutation = await make_intervals_request(
                f"/athlete/{config.athlete_id}/events",
                api_key=config.api_key,
                method="POST",
                params={"upsertOnUid": False},
                data=serialize_workout_event(intent.workout, ext),
            )
            if _api_error(mutation) and isinstance(mutation, dict):
                result = _result_from_api_error(
                    intent, mutation, sent=True, external_id=ext, fingerprint=fingerprint
                )
                journal.save(intent, result, decision_uid)
                return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
            event_id = mutation.get("id") if isinstance(mutation, dict) else None
            if event_id is None:
                result = _error_result(
                    intent,
                    "VERIFICATION_INCOMPLETE",
                    "mutation response did not contain an event id",
                    "unknown",
                )
            else:
                observed = await _read_event(config.athlete_id, event_id, config.api_key)
                result = _verification(intent, observed, ext, event_id)
            journal.save(intent, result, decision_uid)
            return WriteResponse(
                status=_response_status(result),
                decision_uid=decision_uid,
                results=[result],
            )
        target = await _read_event(config.athlete_id, intent.event_id, config.api_key)
        if _api_error(target) and isinstance(target, dict):
            result = _result_from_api_error(
                intent,
                target,
                sent=False,
                external_id=ext,
                fingerprint=fingerprint,
                event_id=intent.event_id,
            )
            journal.save(intent, result, decision_uid)
            return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
        if (
            not isinstance(target, dict)
            or target.get("category") != "WORKOUT"
            or target.get("external_id") != ext
            or target.get("type") not in SPORTS
            or str(target.get("id")) != str(intent.event_id)
        ):
            result = _error_result(
                intent, "OUT_OF_SCOPE", "target is not the managed workout for this session"
            )
            journal.save(intent, result, decision_uid)
            return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
        if event_fingerprint(target) != intent.expected_fingerprint:
            result = _error_result(
                intent,
                "EXPECTED_FINGERPRINT_MISMATCH",
                "target changed since approval",
                "conflict",
                event_id=intent.event_id,
                actual_fingerprint=event_fingerprint(target),
                expected_fingerprint=intent.expected_fingerprint,
            )
            journal.save(intent, result, decision_uid)
            return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
        target_start_date = str(
            target.get("start_date_local", target.get("date", ""))
        )[:10] or None
        prepared = _result(
            intent,
            "prepared",
            event_id=intent.event_id,
            external_id=ext,
            intent_fingerprint=fingerprint,
            expected_fingerprint=intent.expected_fingerprint,
            target_start_date=target_start_date,
        )
        journal.save(intent, prepared, decision_uid)
        inflight = _in_flight(
            intent,
            ext,
            fingerprint,
            event_id=intent.event_id,
            expected_fingerprint=intent.expected_fingerprint,
            target_start_date=target_start_date,
        )
        journal.save(intent, inflight, decision_uid)
        if intent.action == "delete":
            mutation = await make_intervals_request(
                f"/athlete/{config.athlete_id}/events/{intent.event_id}",
                api_key=config.api_key,
                method="DELETE",
            )
        else:
            assert intent.workout is not None
            mutation = await make_intervals_request(
                f"/athlete/{config.athlete_id}/events/{intent.event_id}",
                api_key=config.api_key,
                method="PUT",
                data=serialize_workout_event(intent.workout, ext),
            )
        if _api_error(mutation) and isinstance(mutation, dict):
            result = _result_from_api_error(
                intent,
                mutation,
                sent=True,
                external_id=ext,
                fingerprint=fingerprint,
                event_id=intent.event_id,
            )
        elif intent.action == "delete":
            reread = await _read_event(config.athlete_id, intent.event_id, config.api_key)
            if isinstance(reread, dict) and not reread.get("error"):
                result = _error_result(
                    intent,
                    "DELETE_STILL_PRESENT",
                    "deleted event is still present",
                    "mismatch",
                    event_id=reread.get("id"),
                    actual_fingerprint=event_fingerprint(reread),
                )
            elif (
                isinstance(reread, dict)
                and reread.get("error")
                and (reread.get("http_status") == 404 or reread.get("code") == "HTTP_404")
            ):
                original_date = target_start_date or ""
                listing = await make_intervals_request(
                    f"/athlete/{config.athlete_id}/events",
                    api_key=config.api_key,
                    params={"oldest": original_date, "newest": original_date},
                    method="GET",
                )
                if isinstance(listing, dict) and listing.get("error"):
                    result = _error_result(
                        intent,
                        "VERIFICATION_INCOMPLETE",
                        "account list verification failed",
                        "unknown",
                        event_id=intent.event_id,
                    )
                elif not isinstance(listing, list):
                    result = _error_result(
                        intent,
                        "VERIFICATION_INCOMPLETE",
                        "account list verification was not a list",
                        "unknown",
                        event_id=intent.event_id,
                    )
                elif not any(
                    isinstance(row, dict) and str(row.get("id")) == str(intent.event_id)
                    for row in listing
                ):
                    result = _result(intent, "confirmed", event_id=intent.event_id)
                else:
                    result = _error_result(
                        intent,
                        "DELETE_NOT_VERIFIED",
                        "deleted event remains visible",
                        "mismatch",
                        event_id=intent.event_id,
                    )
            else:
                result = _error_result(
                    intent,
                    "DELETE_NOT_VERIFIED",
                    "deletion requires account list verification",
                    "unknown",
                    event_id=intent.event_id,
                )
        else:
            reread = await _read_event(config.athlete_id, intent.event_id, config.api_key)
            result = _verification(intent, reread, ext, intent.event_id)
        journal.save(intent, result, decision_uid)
        return WriteResponse(
            status=_response_status(result),
            decision_uid=decision_uid,
            results=[result],
        )

    except JournalCorruptError as exc:
        return WriteResponse(
            status="partial",
            decision_uid=decision_uid,
            results=[
                _error_result(
                    intent,
                    "JOURNAL_CORRUPT",
                    str(exc),
                    "unknown",
                    intent_fingerprint=fingerprint,
                )
            ],
        )
    finally:
        if lock is not None:
            lock.release()


@coach_tool(access="safe_write", upstream="write", local="write")
async def apply_workout_changes(
    decision_uid: str,
    operations: list[OperationIntent],
) -> WriteResponse:
    """Apply a sequential package of operations, stopping on the first failure."""
    if not decision_uid.strip():
        invalid_operations = operations or [
            OperationIntent.model_construct(
                operation_uid="not_attempted",
                session_uid="not_attempted",
                action="create",
            )
        ]
        return WriteResponse(
            status="error",
            decision_uid="invalid",
            results=[
                _error_result(
                    operation, "INVALID_DECISION_UID", "decision_uid is required"
                )
                for operation in invalid_operations
            ],
        )
    if not operations:
        synthetic = OperationIntent.model_construct(
            operation_uid="not_attempted", session_uid="not_attempted", action="create"
        )
        result = _error_result(
            synthetic, "EMPTY_OPERATION_PACKAGE", "at least one operation is required"
        )
        return WriteResponse(status="error", decision_uid=decision_uid, results=[result])
    uids = [operation.operation_uid for operation in operations]
    if len(set(uids)) != len(uids):
        return WriteResponse(
            status="error",
            decision_uid=decision_uid,
            results=[
                _error_result(
                    operation,
                    "DUPLICATE_OPERATION_UID",
                    "operation UIDs must be unique",
                )
                for operation in operations
            ],
        )
    config = get_config()
    if not config.athlete_id or not config.api_key:
        config_results = [
            _error_result(
                operations[0],
                "CONFIGURATION_ERROR",
                "ATHLETE_ID and API_KEY are required",
            )
        ]
        config_results.extend(
            _error_result(
                operation,
                "PACKAGE_STOPPED",
                "package stopped because write configuration is incomplete",
                "not_attempted",
            )
            for operation in operations[1:]
        )
        return WriteResponse(
            status="error", decision_uid=decision_uid, results=config_results
        )
    lock = AccountWriteLock(config.athlete_id)
    try:
        lock.acquire()
    except RuntimeError:
        collision_results = [
            _error_result(operations[0], "WRITE_LOCKED", "another write is in progress", "rejected")
        ]
        collision_results.extend(
            _error_result(
                op, "PACKAGE_STOPPED", "package stopped after lock collision", "not_attempted"
            )
            for op in operations[1:]
        )
        return WriteResponse(status="error", decision_uid=decision_uid, results=collision_results)
    results: list[OperationResult] = []
    try:
        for index, operation in enumerate(operations):
            response = await _apply_workout_change(decision_uid, [operation], _lock_held=True)
            result = response.results[0]
            results.append(result)
            if result.outcome != "confirmed":
                for remaining in operations[index + 1 :]:
                    results.append(
                        _error_result(
                            remaining,
                            "PACKAGE_STOPPED",
                            "package stopped after previous operation",
                            "not_attempted",
                        )
                    )
                break
        status = _package_status(results)
        return WriteResponse(status=status, decision_uid=decision_uid, results=results)
    finally:
        lock.release()


@coach_tool(access="write_status", upstream="read", local="write")
async def get_write_status(operation_uid: str, reconcile: bool = False) -> WriteStatusResponse:
    """Read durable write status; reconciliation performs reads only."""
    config = get_config()
    if not operation_uid.strip():
        synthetic = OperationIntent.model_construct(
            operation_uid="not_attempted", session_uid="not_attempted", action="create"
        )
        return WriteStatusResponse(
            status="error",
            operation_uid=operation_uid or "invalid",
            historical_result=_error_result(
                synthetic, "INVALID_OPERATION_UID", "operation_uid is required"
            ),
        )
    if not config.athlete_id:
        synthetic = OperationIntent.model_construct(
            operation_uid=operation_uid, session_uid="unknown", action="create"
        )
        return WriteStatusResponse(
            status="error",
            operation_uid=operation_uid,
            historical_result=_error_result(
                synthetic, "CONFIGURATION_ERROR", "ATHLETE_ID is required"
            ),
        )
    journal = OperationJournal(config.athlete_id)
    try:
        record = journal.load(operation_uid)
    except JournalCorruptError as exc:
        synthetic = OperationIntent.model_construct(
            operation_uid=operation_uid, session_uid="unknown", action="create"
        )
        return WriteStatusResponse(
            status="error",
            operation_uid=operation_uid,
            historical_result=_error_result(
                synthetic, "JOURNAL_CORRUPT", str(exc), "unknown"
            ),
        )
    if record is None:
        synthetic = OperationIntent.model_construct(
            operation_uid=operation_uid, session_uid="unknown", action="create"
        )
        return WriteStatusResponse(
            status="error",
            operation_uid=operation_uid,
            historical_result=_error_result(
                synthetic, "OPERATION_NOT_FOUND", "operation not found"
            ),
        )
    historical = OperationResult.model_validate(record["result"])
    if not reconcile:
        return WriteStatusResponse(
            status=_response_status(historical),
            operation_uid=operation_uid,
            historical_result=historical,
        )
    intent = OperationIntent.model_validate(record["intent"])
    if not config.api_key:
        return WriteStatusResponse(
            status="error",
            operation_uid=operation_uid,
            historical_result=historical,
            reconciliation_result=_error_result(
                intent, "CONFIGURATION_ERROR", "API_KEY is required for reconciliation"
            ),
        )
    external_id = historical.external_id or external_id_for_session(intent.session_uid)
    event_id = historical.event_id or intent.event_id
    observed: Any = None
    current_observation: dict[str, Any] | None = None
    if event_id is not None:
        observed = await _read_event(config.athlete_id, event_id, config.api_key)
    elif intent.workout is not None:
        observed = await make_intervals_request(
            f"/athlete/{config.athlete_id}/events",
            api_key=config.api_key,
            params={"oldest": intent.workout.start_date, "newest": intent.workout.start_date},
            method="GET",
        )
        if isinstance(observed, list):
            matches = [
                row
                for row in observed
                if isinstance(row, dict) and row.get("external_id") == external_id
            ]
            if len(matches) == 1:
                observed = matches[0]
            elif len(matches) > 1:
                result = _error_result(
                    intent,
                    "AMBIGUOUS_SESSION",
                    "multiple matching events",
                    "conflict",
                    external_id=external_id,
                )
                return WriteStatusResponse(
                    status="error",
                    operation_uid=operation_uid,
                    historical_result=historical,
                    reconciliation_result=result,
                    current_observation={"error": "AMBIGUOUS_SESSION"},
                    reconciled_at=datetime.now(timezone.utc).isoformat(),
                )
            else:
                observed = None
    if (
        intent.action == "delete"
        and isinstance(observed, dict)
        and observed.get("error")
        and (observed.get("http_status") == 404 or observed.get("code") == "HTTP_404")
    ):
        target_date = historical.target_start_date
        if target_date:
            listing = await make_intervals_request(
                f"/athlete/{config.athlete_id}/events",
                api_key=config.api_key,
                params={"oldest": target_date, "newest": target_date},
                method="GET",
            )
            current_observation = {"detail": observed, "account_list": listing}
            if isinstance(listing, list) and not any(
                isinstance(row, dict) and str(row.get("id")) == str(event_id)
                for row in listing
            ):
                result = _result(
                    intent,
                    "confirmed",
                    event_id=event_id,
                    external_id=external_id,
                    event_found=False,
                    target_start_date=target_date,
                )
            else:
                result = _error_result(
                    intent,
                    "RECONCILIATION_INCOMPLETE",
                    "delete absence could not be established",
                    "unknown",
                    external_id=external_id,
                    event_id=event_id,
                    target_start_date=target_date,
                )
        else:
            result = _error_result(
                intent,
                "RECONCILIATION_INCOMPLETE",
                "delete target date is unavailable",
                "unknown",
                external_id=external_id,
                event_id=event_id,
            )
            current_observation = observed
    elif observed is None or (isinstance(observed, dict) and observed.get("error")):
        result = _error_result(
            intent,
            "RECONCILIATION_INCOMPLETE",
            "write state could not be established",
            "unknown",
            external_id=external_id,
            event_id=event_id,
        )
    else:
        result = _verification(intent, observed, external_id, event_id)
        current_observation = observed if isinstance(observed, dict) else None
    if result.outcome == "confirmed" and historical.outcome != "confirmed":
        journal.save(intent, result, record.get("decision_uid"))
    return WriteStatusResponse(
        status=_response_status(result),
        operation_uid=operation_uid,
        historical_result=historical,
        reconciliation_result=result,
        current_observation=current_observation,
        reconciled_at=datetime.now(timezone.utc).isoformat(),
    )
