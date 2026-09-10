"""Versioned machine-readable contract shared by all read tools.

The models intentionally keep ``data`` unopinionated: Intervals adds fields
over time and callers must be able to distinguish a missing value from zero.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, Literal, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    system: str = "intervals.icu"
    athlete_id: str | None = None
    resource: str
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    upstream_version: str | None = None


class Query(BaseModel):
    model_config = ConfigDict(extra="allow")


class Coverage(BaseModel):
    source_complete_within_query: bool | None = None
    response_complete: bool = True
    truncated: bool = False
    reasons: list[str] = Field(default_factory=list)


class Pagination(BaseModel):
    snapshot_id: str | None = None
    next_cursor: str | None = None


class ErrorInfo(BaseModel):
    code: str
    message: str
    phase: str
    http_status: int | None = None
    recommended_action: str | None = None


class ReadResponse(BaseModel, Generic[T]):
    """The sole response envelope for read operations (contract 1.0)."""

    model_config = ConfigDict(extra="allow")
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["ok", "partial", "error"]
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    source: Source
    query: Query = Field(default_factory=Query)
    data: T
    coverage: Coverage
    pagination: Pagination = Field(default_factory=Pagination)
    warnings: list[str] = Field(default_factory=list)
    error: ErrorInfo | None = None

    def as_text(self) -> str:
        """Compatibility presentation: serialize this exact object."""
        return self.model_dump_json(by_alias=True, exclude_none=False)

    def __str__(self) -> str:
        return self.as_text()



def success(data: T, *, resource: str, athlete_id: str | None = None,
            query: dict[str, Any] | None = None, **kwargs: Any) -> ReadResponse[T]:
    return ReadResponse(status="ok", source=Source(resource=resource, athlete_id=athlete_id),
                        query=Query(**(query or {})), data=data,
                        coverage=Coverage(**kwargs.pop("coverage", {})), **kwargs)


def failure(*, resource: str, code: str, message: str, phase: str,
            http_status: int | None = None, athlete_id: str | None = None,
            query: dict[str, Any] | None = None, recommended_action: str | None = None,
            warnings: list[str] | None = None) -> ReadResponse[list[Any]]:
    return ReadResponse(status="error", source=Source(resource=resource, athlete_id=athlete_id),
                        query=Query(**(query or {})), data=[], coverage=Coverage(
                            source_complete_within_query=None, response_complete=False,
                            reasons=[code]), warnings=warnings or [],
                        error=ErrorInfo(code=code, message=message, phase=phase,
                                         http_status=http_status,
                                         recommended_action=recommended_action))


def upstream_failure(
    value: Any,
    *,
    resource: str,
    athlete_id: str | None = None,
    query: dict[str, Any] | None = None,
) -> ReadResponse[list[Any]] | None:
    """Adapt the API client's structured error without dropping its guidance."""
    if not isinstance(value, dict) or not value.get("error"):
        return None
    return failure(
        resource=resource,
        athlete_id=athlete_id,
        query=query,
        code=str(value.get("code", "UPSTREAM_ERROR")),
        message=str(value.get("message", "upstream request failed")),
        phase=str(value.get("phase", "http")),
        http_status=value.get("http_status") or value.get("status_code"),
        recommended_action=value.get("recommended_action"),
    )


def invalid_upstream_response(
    *,
    resource: str,
    message: str,
    athlete_id: str | None = None,
    query: dict[str, Any] | None = None,
    code: str = "INVALID_UPSTREAM_RESPONSE",
) -> ReadResponse[list[Any]]:
    """Return a fail-closed response for a payload with no supported shape."""
    return failure(
        resource=resource,
        athlete_id=athlete_id,
        query=query,
        code=code,
        message=message,
        phase="response",
    )
