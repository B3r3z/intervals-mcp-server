"""Validated write intents and durable local operation journal primitives."""

from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SPORTS = {
    "Ride",
    "VirtualRide",
    "MountainBikeRide",
    "GravelRide",
    "WeightTraining",
    "StrengthTraining",
}
DERIVED = ("moving_time", "icu_training_load", "distance", "duration")


class JournalCorruptError(RuntimeError):
    """Raised when a durable operation record cannot be trusted."""


class WorkoutIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    category: Literal["WORKOUT"] = "WORKOUT"
    start_date: str
    timezone: str = "Europe/Warsaw"
    sport: str
    representation: Literal["structured", "native_text", "unstructured_strength"]
    description: str | None = None
    workout_text: str | None = None
    steps: list[dict[str, Any]] | None = None
    moving_time: int | None = None
    icu_training_load: float | None = None
    distance: float | None = None
    duration: int | None = None

    @field_validator("name", "start_date", "sport")
    @classmethod
    def nonempty(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("value must be non-empty and trimmed")
        return value

    @field_validator("start_date")
    @classmethod
    def iso_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("start_date must be ISO local date") from exc
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_representation(self) -> "WorkoutIntent":
        if self.sport not in SPORTS:
            raise ValueError("unsupported sport")
        if self.representation == "structured":
            if not self.steps:
                raise ValueError("structured representation requires non-empty steps")
            conflicts = [
                field for field in ("workout_text", *DERIVED) if getattr(self, field) is not None
            ]
            if conflicts:
                raise ValueError("structured forbids fields: " + ", ".join(conflicts))
        elif self.representation == "native_text":
            if not self.workout_text:
                raise ValueError("native_text requires workout_text")
            conflicts = [
                field
                for field in ("steps", "description", *DERIVED)
                if getattr(self, field) is not None
            ]
            if conflicts:
                raise ValueError("native_text forbids fields: " + ", ".join(conflicts))
        else:
            if self.sport not in {"WeightTraining", "StrengthTraining"} or not self.description:
                raise ValueError("strength representation requires strength sport and description")
            conflicts = [
                field
                for field in ("steps", "workout_text", "icu_training_load", "distance", "duration")
                if getattr(self, field) is not None
            ]
            if conflicts:
                raise ValueError("unstructured_strength forbids fields: " + ", ".join(conflicts))
        return self


class OperationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_uid: str
    action: Literal["create", "update", "delete"]
    session_uid: str
    event_id: str | int | None = None
    expected_fingerprint: str | None = None
    workout: WorkoutIntent | None = None

    @field_validator("operation_uid", "session_uid")
    @classmethod
    def valid_uid(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("UID must be non-empty and trimmed")
        return value

    @model_validator(mode="after")
    def validate_action(self) -> "OperationIntent":
        if self.action == "create":
            valid = (
                self.workout is not None
                and self.event_id is None
                and self.expected_fingerprint is None
            )
        elif self.action == "update":
            valid = (
                self.event_id is not None
                and bool(self.expected_fingerprint)
                and self.workout is not None
            )
        else:
            valid = (
                self.event_id is not None
                and bool(self.expected_fingerprint)
                and self.workout is None
            )
        if not valid:
            raise ValueError(f"invalid fields for {self.action} operation")
        return self


class OperationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_uid: str
    session_uid: str
    action: Literal["create", "update", "delete"]
    outcome: Literal[
        "confirmed",
        "rejected",
        "conflict",
        "unknown",
        "mismatch",
        "not_attempted",
        "prepared",
        "in_flight",
    ]
    event_id: str | int | None = None
    external_id: str | None = None
    code: str | None = None
    message: str | None = None
    intent_fingerprint: str | None = None
    expected_fingerprint: str | None = None
    actual_fingerprint: str | None = None
    differences: list[dict[str, Any]] = Field(default_factory=list)
    checked_fields: list[str] = Field(default_factory=list)
    unavailable_fields: list[str] = Field(default_factory=list)
    event_found: bool | None = None
    prepared_at: str | None = None
    completed_at: str | None = None
    sent_at: str | None = None
    target_start_date: str | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("operation_uid", "session_uid")
    @classmethod
    def result_uid(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("UID must be non-empty and trimmed")
        return value


class WriteResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["ok", "partial", "error"]
    decision_uid: str
    results: list[OperationResult]

    @field_validator("decision_uid")
    @classmethod
    def decision_uid_valid(cls, value: str) -> str:
        if not value or value.strip() != value:
            raise ValueError("decision_uid must be non-empty and trimmed")
        return value


class WriteStatusResponse(BaseModel):
    """Durable historical result plus an optional current read-only observation."""

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["ok", "partial", "error"]
    operation_uid: str
    historical_result: OperationResult
    reconciliation_result: OperationResult | None = None
    current_observation: dict[str, Any] | None = None
    reconciled_at: str | None = None


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def intent_fingerprint(account: str, decision_uid: str, intent: OperationIntent) -> str:
    return canonical_hash(
        {"account": account, "decision_uid": decision_uid, "intent": intent.model_dump(mode="json")}
    )


def event_fingerprint(event: dict[str, Any]) -> str:
    fields = (
        "id",
        "external_id",
        "category",
        "type",
        "name",
        "start_date_local",
        "end_date_local",
        "description",
        "workout_doc",
        "completed",
        "paired_activity_id",
    )
    return canonical_hash({field: event.get(field) for field in fields})


def serialize_workout_event(
    workout: WorkoutIntent, external_id: str | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "category": workout.category,
        "type": workout.sport,
        "name": workout.name,
        "start_date_local": workout.start_date + "T00:00:00",
        "external_id": external_id,
    }
    if workout.representation == "structured":
        from .utils.types import Step, WorkoutDoc

        doc = WorkoutDoc(
            description=workout.description,
            steps=[Step.from_dict(step) for step in workout.steps or []],
        )
        payload["description"] = str(doc)
    elif workout.representation == "native_text":
        payload["description"] = workout.workout_text
    else:
        payload["description"] = workout.description
        if workout.moving_time is not None:
            payload["moving_time"] = workout.moving_time
    return payload


def external_id_for_session(session_uid: str, namespace: str | None = None) -> str:
    value = namespace or os.getenv("INTERVALS_WRITE_NAMESPACE", "tatra-v3")
    return f"{value}:{hashlib.sha256(session_uid.encode()).hexdigest()}"


class OperationJournal:
    def __init__(self, account: str, directory: str | Path | None = None):
        self.account = account
        self.directory = Path(
            directory or os.getenv("INTERVALS_OPERATION_DIR") or ".runtime/operations"
        ).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, uid: str) -> Path:
        key = hashlib.sha256(f"{self.account}:{uid}".encode()).hexdigest()
        return self.directory / f"{key}.json"

    def save(
        self, intent: OperationIntent, result: OperationResult, decision_uid: str | None = None
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        target = self._path(intent.operation_uid)
        created_at = now
        prior_result: dict[str, Any] = {}
        if target.exists():
            try:
                prior = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise JournalCorruptError(
                    f"unreadable operation journal: {target.name}"
                ) from exc
            if not isinstance(prior, dict) or prior.get("account") != self.account:
                raise JournalCorruptError(f"invalid operation journal: {target.name}")
            created_at = prior.get("created_at", now)
            if isinstance(prior.get("result"), dict):
                prior_result = prior["result"]
        result_data = result.model_dump(mode="json")
        for field in (
            "prepared_at",
            "sent_at",
            "event_id",
            "external_id",
            "intent_fingerprint",
            "expected_fingerprint",
            "target_start_date",
        ):
            if result_data.get(field) is None and prior_result.get(field) is not None:
                result_data[field] = prior_result[field]
                setattr(result, field, prior_result[field])
        payload = {
            "schema_version": "1.0",
            "account": self.account,
            "decision_uid": decision_uid,
            "intent_fingerprint": intent_fingerprint(self.account, decision_uid or "", intent),
            "intent": intent.model_dump(mode="json"),
            "result": result_data,
            "created_at": created_at,
            "updated_at": now,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        fd, temp = tempfile.mkstemp(dir=self.directory, prefix=".journal-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def load(self, uid: str) -> dict[str, Any] | None:
        path = self._path(uid)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise JournalCorruptError(f"unreadable operation journal: {path.name}") from exc
        if not isinstance(record, dict) or record.get("account") != self.account:
            raise JournalCorruptError(f"invalid operation journal: {path.name}")
        return record

    def iter_records(self):
        for path in sorted(self.directory.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise JournalCorruptError(
                    f"unreadable operation journal: {path.name}"
                ) from exc
            if not isinstance(record, dict):
                raise JournalCorruptError(f"invalid operation journal: {path.name}")
            if record.get("account") == self.account:
                yield record

    def find_by_session(self, session_uid: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self.iter_records()
            if record.get("intent", {}).get("session_uid") == session_uid
        ]


class AccountWriteLock:
    def __init__(self, account: str, directory: str | Path | None = None):
        root = Path(
            directory or os.getenv("INTERVALS_OPERATION_DIR") or ".runtime/operations"
        ).resolve()
        self.path = root / (hashlib.sha256(account.encode()).hexdigest() + ".lock")
        self.token = secrets.token_hex(16)
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError("WRITE_LOCKED") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(self.token)
        self.acquired = True

    def release(self) -> None:
        try:
            if self.path.read_text(encoding="utf-8") == self.token:
                self.path.unlink()
        except FileNotFoundError:
            pass
        self.acquired = False

    def __enter__(self) -> "AccountWriteLock":
        if not self.acquired:
            self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
