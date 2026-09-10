"""Durable, single-attempt publication of a coach analysis version."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Literal, TypeGuard
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.catalogue import coach_tool
from intervals_mcp_server.config import get_config
from intervals_mcp_server.operations import AccountWriteLock, JournalCorruptError, canonical_hash

Outcome = Literal["prepared", "in_flight", "confirmed", "rejected", "conflict", "unknown", "mismatch"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Intent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    analysis_uid: str = Field(min_length=1, max_length=256)
    activity_id: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=100_000)

    @field_validator("analysis_uid", "activity_id")
    @classmethod
    def identity(cls, value: str) -> str:
        if value.strip() != value or any(ord(char) < 32 for char in value):
            raise ValueError("identity must be trimmed and contain no control characters")
        return value

    @field_validator("content")
    @classmethod
    def nonblank_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("analysis content must not be blank")
        return value


class AnalysisCommentResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    analysis_uid: str
    activity_id: str
    content_fingerprint: str
    outcome: Outcome
    code: str
    message_id: int | None = Field(default=None, gt=0, lt=2**63)
    prepared_at: str = Field(default_factory=_now)
    sent_at: str | None = None
    completed_at: str | None = None
    checked_fields: list[str] = Field(default_factory=list)


class AnalysisCommentResponse(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["ok", "partial", "error"]
    analysis_uid: str
    result: AnalysisCommentResult


class AnalysisCommentStatus(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["ok", "partial", "error"]
    analysis_uid: str
    historical_result: AnalysisCommentResult | None = None
    reconciliation_result: AnalysisCommentResult | None = None
    current_observation: dict[str, Any] | None = None
    reconciled_at: str | None = None
    code: str | None = None


class _Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["analysis_comment"] = "analysis_comment"
    account: str
    intent: _Intent
    intent_fingerprint: str
    result: AnalysisCommentResult


class _CommentJournal:
    """Typed comment records, separate from existing workout journal files."""

    def __init__(self, account: str):
        self.account = account
        self.directory = (Path(os.getenv("INTERVALS_OPERATION_DIR", ".runtime/operations")) / "analysis-comments").resolve()
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, uid: str) -> Path:
        key = canonical_hash({"account": self.account, "analysis_uid": uid}).split(":", 1)[1]
        path = self.directory / f"{key}.json"
        if path.is_symlink() or path.resolve().parent != self.directory:
            raise JournalCorruptError("comment journal path is not confined")
        return path

    def fingerprint(self, intent: _Intent) -> str:
        return canonical_hash({"account": self.account, "intent": intent.model_dump()})

    def load(self, uid: str) -> _Record | None:
        path = self._path(uid)
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise JournalCorruptError("comment journal is unreadable") from exc
        try:
            record = _Record.model_validate_json(raw)
        except ValueError as exc:
            raise JournalCorruptError("comment journal is invalid") from exc
        if (
            record.account != self.account
            or record.intent.analysis_uid != uid
            or record.intent_fingerprint != self.fingerprint(record.intent)
            or record.result.analysis_uid != uid
            or record.result.activity_id != record.intent.activity_id
            or record.result.content_fingerprint != canonical_hash(record.intent.content)
            or (record.result.outcome == "confirmed" and (
                record.result.message_id is None
                or record.result.sent_at is None
                or record.result.completed_at is None
            ))
            or (record.result.outcome == "in_flight" and record.result.sent_at is None)
            or (record.result.message_id is not None and record.result.sent_at is None)
        ):
            raise JournalCorruptError("comment journal identity does not match")
        return record

    def save(self, intent: _Intent, result: AnalysisCommentResult) -> None:
        path = self._path(intent.analysis_uid)
        record = _Record(account=self.account, intent=intent, intent_fingerprint=self.fingerprint(intent), result=result)
        fd, temporary = tempfile.mkstemp(dir=self.directory, prefix=".comment-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(record.model_dump_json().encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def _status(result: AnalysisCommentResult) -> Literal["ok", "partial", "error"]:
    if result.outcome == "confirmed":
        return "ok"
    return "partial" if result.outcome in {"unknown", "mismatch", "prepared", "in_flight"} else "error"


def _response(result: AnalysisCommentResult) -> AnalysisCommentResponse:
    return AnalysisCommentResponse(status=_status(result), analysis_uid=result.analysis_uid, result=result)


def _finish(result: AnalysisCommentResult, outcome: Outcome, code: str, **fields: Any) -> AnalysisCommentResult:
    return result.model_copy(update={"outcome": outcome, "code": code, "completed_at": _now(), **fields})


def _valid_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value < 2**63


def _message_list(value: Any) -> TypeGuard[list[dict[str, Any]]]:
    return isinstance(value, list) and all(isinstance(row, dict) for row in value)


async def _verify(
    intent: _Intent, result: AnalysisCommentResult, api_key: str,
) -> tuple[AnalysisCommentResult, dict[str, Any] | None]:
    # Current verification must not inherit fields checked in an earlier observation.
    result = result.model_copy(update={"checked_fields": []})
    if result.message_id is None:
        return _finish(result, "unknown", "MESSAGE_ID_UNAVAILABLE"), None
    messages = await make_intervals_request(
        url=f"/activity/{quote(intent.activity_id, safe='')}/messages", api_key=api_key,
        method="GET",
    )
    if not _message_list(messages):
        return _finish(result, "unknown", "READ_BACK_UNAVAILABLE"), None
    matches = [row for row in messages if _valid_id(row.get("id")) and row["id"] == result.message_id]
    if len(matches) != 1:
        # This list can be limited: absence never proves failed publication or deletion.
        return _finish(result, "unknown", "MESSAGE_NOT_OBSERVED" if not matches else "AMBIGUOUS_MESSAGE_ID"), None
    message = matches[0]
    checked = ["id"]
    if message.get("activity_id") is not None:
        checked.append("activity_id")
        if message["activity_id"] != intent.activity_id:
            return _finish(result, "mismatch", "ACTIVITY_ID_MISMATCH", checked_fields=checked), message
    if message.get("deleted") is not None or message.get("deleted_by_id") is not None:
        return _finish(result, "mismatch", "MESSAGE_DELETED", checked_fields=checked + ["deleted", "deleted_by_id"]), message
    if not isinstance(message.get("content"), str):
        return _finish(result, "unknown", "MESSAGE_CONTENT_UNAVAILABLE", checked_fields=checked), message
    checked.append("content")
    if message["content"] != intent.content:
        return _finish(result, "mismatch", "MESSAGE_CONTENT_MISMATCH", checked_fields=checked), message
    return _finish(result, "confirmed", "READ_BACK_CONFIRMED", checked_fields=checked), message


@coach_tool(access="safe_write", upstream="write", local="write")
async def publish_analysis_comment(
    activity_id: StrictStr, analysis_uid: StrictStr, content: StrictStr,
) -> AnalysisCommentResponse:
    """Publish one coach analysis version and verify its exact message ID and content.

    Keep analysis_uid stable for retries of the same version. A new version uses
    a new UID and appends a comment. Same UID with changed activity/content is a
    conflict. Durable records prevent another POST after an uncertain outcome;
    use get_analysis_comment_status for read-only reconciliation. Retain the
    operation journal: upstream idempotency and live behavior are unverified.
    Content is preserved exactly, with a local limit of 100,000 characters.
    No message is edited or deleted. An acknowledgement alone is not confirmation.
    """
    result = AnalysisCommentResult(
        analysis_uid=analysis_uid, activity_id=activity_id,
        content_fingerprint=canonical_hash(content), outcome="prepared", code="PREPARED",
    )
    try:
        intent = _Intent(activity_id=activity_id, analysis_uid=analysis_uid, content=content)
    except ValidationError:
        return _response(_finish(result, "rejected", "INVALID_ANALYSIS_INTENT"))
    config = get_config()
    if not config.athlete_id or not config.api_key:
        return _response(_finish(result, "rejected", "CONFIGURATION_ERROR"))
    try:
        lock = AccountWriteLock(config.athlete_id)
        lock.acquire()
    except RuntimeError:
        return _response(_finish(result, "rejected", "WRITE_LOCKED"))
    except OSError:
        return _response(_finish(result, "rejected", "PUBLICATION_PREPARATION_FAILED"))
    sent = False
    try:
        journal = _CommentJournal(config.athlete_id)
        previous = journal.load(analysis_uid)
        if previous is not None:
            if previous.intent_fingerprint != journal.fingerprint(intent):
                return _response(_finish(result, "conflict", "ANALYSIS_UID_REUSED"))
            historical = previous.result
            if historical.outcome in {"prepared", "in_flight"}:
                historical = _finish(historical, "unknown", "PUBLICATION_INTERRUPTED")
                journal.save(intent, historical)
            return _response(historical)
        journal.save(intent, result)
        activity = await make_intervals_request(url=f"/activity/{quote(activity_id, safe='')}", api_key=config.api_key, method="GET")
        if not isinstance(activity, dict) or activity.get("error") is True or activity.get("id") != activity_id:
            result = _finish(result, "rejected", "ACTIVITY_PREFLIGHT_FAILED")
            journal.save(intent, result)
            return _response(result)
        messages = await make_intervals_request(url=f"/activity/{quote(activity_id, safe='')}/messages", api_key=config.api_key, method="GET")
        if not _message_list(messages):
            result = _finish(result, "rejected", "MESSAGES_PREFLIGHT_FAILED")
            journal.save(intent, result)
            return _response(result)
        result = result.model_copy(update={"outcome": "in_flight", "code": "IN_FLIGHT", "sent_at": _now()})
        journal.save(intent, result)
        sent = True
        acknowledged = await make_intervals_request(
            url=f"/activity/{quote(activity_id, safe='')}/messages", api_key=config.api_key,
            method="POST", data={"content": content},
        )
        if isinstance(acknowledged, dict) and acknowledged.get("error") is True:
            rejected = acknowledged.get("write_outcome") == "rejected"
            result = _finish(result, "rejected" if rejected else "unknown", "PUBLICATION_REJECTED" if rejected else "PUBLICATION_UNCERTAIN")
        elif isinstance(acknowledged, dict) and _valid_id(acknowledged.get("id")):
            result = result.model_copy(update={"message_id": acknowledged["id"]})
            # Preserve the acknowledged identity even if read-back or the process fails.
            journal.save(intent, result)
            result, _ = await _verify(intent, result, config.api_key)
        else:
            result = _finish(result, "unknown", "MESSAGE_ID_UNAVAILABLE")
        journal.save(intent, result)
        return _response(result)
    except JournalCorruptError:
        return _response(_finish(result, "unknown", "JOURNAL_CORRUPT"))
    except Exception:
        # No exception may turn an in-flight operation into permission to send again.
        # The already persisted record remains the authoritative replay guard.
        return _response(_finish(result, "unknown" if sent else "rejected", "PUBLICATION_INTERRUPTED" if sent else "PUBLICATION_PREPARATION_FAILED"))
    finally:
        lock.release()


@coach_tool(access="write_status", upstream="read", local="write")
async def get_analysis_comment_status(
    analysis_uid: StrictStr, reconcile: bool = False,
) -> AnalysisCommentStatus:
    """Inspect a coach analysis publication; optional reconciliation only reads upstream.

    Historical confirmation is distinct from current observation. A missing
    acknowledgement ID cannot be recovered by matching prose or timestamps.
    Absence from a limited message list remains unknown. Reconciliation can
    update the local journal but never publishes, edits or deletes a comment.
    """
    config = get_config()
    if not analysis_uid.strip() or not config.athlete_id:
        return AnalysisCommentStatus(status="error", analysis_uid=analysis_uid, code="INVALID_ID_OR_CONFIGURATION")
    lock: AccountWriteLock | None = None
    record: _Record | None = None
    try:
        if reconcile:
            lock = AccountWriteLock(config.athlete_id)
            try:
                lock.acquire()
            except RuntimeError:
                lock = None
                return AnalysisCommentStatus(status="error", analysis_uid=analysis_uid, code="WRITE_LOCKED")
        journal = _CommentJournal(config.athlete_id)
        record = journal.load(analysis_uid)
        if record is None:
            return AnalysisCommentStatus(status="error", analysis_uid=analysis_uid, code="ANALYSIS_NOT_FOUND")
        historical = record.result
        if not reconcile:
            visible = historical
            if historical.outcome in {"prepared", "in_flight"}:
                visible = _finish(historical, "unknown", "RECONCILIATION_REQUIRED")
            return AnalysisCommentStatus(status=_status(visible), analysis_uid=analysis_uid, historical_result=historical, code=visible.code)
        if not config.api_key:
            return AnalysisCommentStatus(status="error", analysis_uid=analysis_uid, historical_result=historical, code="CONFIGURATION_ERROR")
        if historical.outcome == "rejected" and historical.sent_at is None:
            return AnalysisCommentStatus(status="error", analysis_uid=analysis_uid, historical_result=historical, code=historical.code)
        current, observation = await _verify(record.intent, historical, config.api_key)
        if current.outcome == "confirmed" and historical.outcome != "confirmed":
            journal.save(record.intent, current)
        return AnalysisCommentStatus(
            status=_status(current), analysis_uid=analysis_uid, historical_result=historical,
            reconciliation_result=current, current_observation=observation, reconciled_at=_now(),
        )
    except JournalCorruptError:
        return AnalysisCommentStatus(status="partial", analysis_uid=analysis_uid, code="JOURNAL_CORRUPT")
    except Exception:
        return AnalysisCommentStatus(status="partial", analysis_uid=analysis_uid, historical_result=record.result if record else None, code="RECONCILIATION_UNAVAILABLE")
    finally:
        if lock is not None:
            lock.release()
