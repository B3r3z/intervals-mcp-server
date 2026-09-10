"""Read-back must verify the prescription inside each structured workout target."""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from intervals_mcp_server.operations import (
    OperationIntent,
    OperationJournal,
    WorkoutIntent,
    external_id_for_session,
    serialize_workout_event,
)
from intervals_mcp_server.tools import writes


TARGET_UNITS = {"power": "%ftp", "hr": "%hr", "pace": "%pace", "cadence": "cadence"}


def _intent(steps: list[dict[str, Any]] | None = None) -> OperationIntent:
    return OperationIntent(
        operation_uid="target-verification",
        session_uid="target-session",
        action="create",
        workout=WorkoutIntent(
            name="Target verification",
            start_date="2026-09-11",
            sport="Ride",
            representation="structured",
            steps=steps if steps is not None else [
                {"duration": 300, "power": {"value": 50.0, "units": "%ftp"}},
            ],
        ),
    )


def _event(intent: OperationIntent) -> dict[str, Any]:
    assert intent.workout is not None
    event = serialize_workout_event(intent.workout, external_id_for_session(intent.session_uid))
    event["id"] = 42
    event["workout_doc"] = {
        "steps": deepcopy(intent.workout.steps),
        "duration": writes._timed_duration(intent.workout.steps),
    }
    return event


def _verify(intent: OperationIntent, event: dict[str, Any]):
    return writes._verification(intent, event, external_id_for_session(intent.session_uid), 42)


def test_original_50_percent_ftp_to_999_watts_regression():
    intent = _intent()
    event = _event(intent)
    event["workout_doc"]["steps"][0]["power"] = {"value": 999, "units": "w"}

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    assert result.code == "VERIFICATION_MISMATCH"
    assert result.differences == [
        {"field": "workout_doc.steps[0].power.units", "expected": "%ftp", "actual": "w"},
        {"field": "workout_doc.steps[0].power.value", "expected": 50, "actual": 999},
    ]
    assert "workout_doc.steps" in result.checked_fields
    assert "workout_doc.duration" not in result.checked_fields


@pytest.mark.parametrize("target", TARGET_UNITS)
@pytest.mark.parametrize("field,changed", [("value", 999), ("units", "w")])
def test_single_targets_verify_value_and_units(target, field, changed):
    intent = _intent([
        {"duration": 300, target: {"value": 50.0, "units": TARGET_UNITS[target]}},
    ])
    event = _event(intent)
    assert _verify(intent, event).outcome == "confirmed"
    expected = event["workout_doc"]["steps"][0][target][field]
    event["workout_doc"]["steps"][0][target][field] = changed

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    assert result.differences == [{
        "field": f"workout_doc.steps[0].{target}.{field}",
        "expected": expected,
        "actual": changed,
    }]


@pytest.mark.parametrize("target", TARGET_UNITS)
@pytest.mark.parametrize("field,changed", [("start", 30), ("end", 99), ("target", "lap")])
def test_range_and_averaging_targets_are_verified(target, field, changed):
    intent = _intent([{
        "duration": 300,
        target: {"start": 40.0, "end": 60.0, "units": TARGET_UNITS[target], "target": "3s"},
    }])
    event = _event(intent)
    assert _verify(intent, event).outcome == "confirmed"
    expected = event["workout_doc"]["steps"][0][target][field]
    event["workout_doc"]["steps"][0][target][field] = changed

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    assert result.differences == [{
        "field": f"workout_doc.steps[0].{target}.{field}",
        "expected": expected,
        "actual": changed,
    }]


@pytest.mark.parametrize("field", ["value", "units"])
@pytest.mark.parametrize("missing", [True, False])
def test_required_target_value_and_units_cannot_disappear(field, missing):
    intent = _intent()
    event = _event(intent)
    if missing:
        del event["workout_doc"]["steps"][0]["power"][field]
    else:
        event["workout_doc"]["steps"][0]["power"][field] = None

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    assert result.differences[0]["field"] == f"workout_doc.steps[0].power.{field}"
    assert result.differences[0]["actual"] is None


@pytest.mark.parametrize("changed", [None, 50, [], {"unrelated": 50}])
def test_malformed_target_is_never_confirmed(changed):
    intent = _intent()
    event = _event(intent)
    event["workout_doc"]["steps"][0]["power"] = changed
    assert _verify(intent, event).outcome == "mismatch"


def test_optional_null_and_extra_resolved_metadata_remain_compatible():
    intent = _intent()
    event = _event(intent)
    step = event["workout_doc"]["steps"][0]
    step.update({"hr": None, "cadence": None, "_power": {"value": 114}, "parser_note": "extra"})
    step["power"].update({"start": None, "end": None, "target": None, "resolved": 114})
    # JSON integer and float representations of the same number are equivalent.
    step["power"]["value"] = 50

    result = _verify(intent, event)

    assert result.outcome == "confirmed"
    assert result.differences == []
    assert result.checked_fields[-2:] == ["workout_doc.steps", "workout_doc.duration"]


@pytest.mark.parametrize("number,boolean", [(0.0, False), (1.0, True)])
def test_boolean_cannot_impersonate_numeric_power(number, boolean):
    intent = _intent([{"duration": 300, "power": {"value": number, "units": "%ftp"}}])
    event = _event(intent)
    event["workout_doc"]["steps"][0]["power"]["value"] = boolean
    assert _verify(intent, event).outcome == "mismatch"


@pytest.mark.parametrize("field", ["duration", "workout_doc.duration", "until_lap_press"])
def test_boolean_and_numeric_step_or_duration_values_are_distinct(field):
    intent = _intent([{"duration": 1, "until_lap_press": True}])
    event = _event(intent)
    if field == "workout_doc.duration":
        event["workout_doc"]["duration"] = True
    else:
        event["workout_doc"]["steps"][0][field] = 1 if field == "until_lap_press" else True

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    expected_path = field if field.startswith("workout_doc") else f"workout_doc.steps[0].{field}"
    assert result.differences[0]["field"] == expected_path


def test_targets_inside_repeat_steps_are_checked_and_duration_is_counted():
    intent = _intent([{
        "reps": 3,
        "steps": [
            {"duration": 120, "power": {"value": 80.0, "units": "%ftp"}},
            {"duration": 60, "hr": {"value": 65.0, "units": "%hr"}},
        ],
    }])
    event = _event(intent)
    assert event["workout_doc"]["duration"] == 540
    assert _verify(intent, event).outcome == "confirmed"
    event["workout_doc"]["steps"][0]["steps"][1]["hr"]["value"] = 95

    result = _verify(intent, event)

    assert result.outcome == "mismatch"
    assert result.differences == [{
        "field": "workout_doc.steps[0].steps[1].hr.value", "expected": 65, "actual": 95,
    }]


def test_added_supported_target_cannot_be_treated_as_metadata():
    intent = _intent()
    event = _event(intent)
    event["workout_doc"]["steps"][0]["cadence"] = {"value": 120, "units": "cadence"}
    result = _verify(intent, event)
    assert result.outcome == "mismatch"
    assert result.differences[0]["field"] == "workout_doc.steps[0].cadence"


@pytest.mark.parametrize("changed,expected_outcome", [(None, "unknown"), (301, "mismatch")])
def test_duration_check_reports_coverage_and_unavailability(changed, expected_outcome):
    intent = _intent()
    event = _event(intent)
    event["workout_doc"]["duration"] = changed

    result = _verify(intent, event)

    assert result.outcome == expected_outcome
    assert "workout_doc.steps" in result.checked_fields
    if changed is None:
        assert result.unavailable_fields == ["workout_doc.duration"]
        assert "workout_doc.duration" not in result.checked_fields
    else:
        assert "workout_doc.duration" in result.checked_fields
        assert result.differences == [{
            "field": "workout_doc.duration", "expected": 300, "actual": changed,
        }]


@pytest.mark.asyncio
async def test_mismatched_readback_is_durable_and_reconcile_only_reads(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(
        writes, "get_config", lambda: SimpleNamespace(athlete_id="athlete", api_key="test")
    )
    intent = _intent()
    event = _event(intent)
    event["workout_doc"]["steps"][0]["power"] = {"value": 999, "units": "w"}
    calls: list[str] = []

    async def request(url, **kwargs):
        method = kwargs.get("method", "GET")
        calls.append(method)
        if method == "POST":
            return {"id": 42}
        return event if url.endswith("/42") else []

    monkeypatch.setattr(writes, "make_intervals_request", request)
    initial = await writes.apply_workout_changes("target-decision", [intent])
    assert initial.results[0].outcome == "mismatch"
    assert calls == ["GET", "POST", "GET"]
    historical_bytes = next(tmp_path.glob("*.json")).read_bytes()

    replay = await writes.apply_workout_changes("target-decision", [intent])
    assert replay.results[0].outcome == "mismatch"
    assert calls == ["GET", "POST", "GET"]

    reconciled = await writes.get_write_status(intent.operation_uid, reconcile=True)
    assert reconciled.historical_result.outcome == "mismatch"
    assert reconciled.reconciliation_result is not None
    assert reconciled.reconciliation_result.outcome == "mismatch"
    assert calls == ["GET", "POST", "GET", "GET"]
    assert next(tmp_path.glob("*.json")).read_bytes() == historical_bytes

    event["workout_doc"]["steps"][0]["power"] = {"value": 50, "units": "%ftp"}
    matched = await writes.get_write_status(intent.operation_uid, reconcile=True)
    assert matched.reconciliation_result is not None
    assert matched.reconciliation_result.outcome == "confirmed"
    assert calls == ["GET", "POST", "GET", "GET", "GET"]
    record = OperationJournal("athlete", tmp_path).load(intent.operation_uid)
    assert record is not None
    assert record.result.outcome == "confirmed"
    assert record.result.checked_fields[-2:] == ["workout_doc.steps", "workout_doc.duration"]
