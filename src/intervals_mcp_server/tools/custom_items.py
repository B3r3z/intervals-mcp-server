"""
Custom items MCP tools for Intervals.icu.

This module contains tools for managing athlete custom items (charts, fields, zones, etc.).
"""

from copy import deepcopy
import json
from typing import Any

from pydantic import StrictInt

from intervals_mcp_server.api.client import make_intervals_request
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import (
    ReadResponse,
    failure,
    invalid_upstream_response,
    success,
    upstream_failure,
)
from intervals_mcp_server.utils.formatting import format_custom_item_details
from intervals_mcp_server.utils.validation import resolve_athlete_id

# Import mcp instance from shared module for tool registration
from intervals_mcp_server.catalogue import coach_tool

config = get_config()


_CUSTOM_ITEM_FIELDS = {
    "id",
    "athlete_id",
    "type",
    "visibility",
    "name",
    "description",
    "image",
    "content",
    "usage_count",
    "index",
    "hide_script",
    "hidden_by_id",
    "updated",
    "from_athlete",
    "from_id",
    "required_items_created",
}
_COMPACT_CUSTOM_ITEM_FIELDS = {
    "id",
    "athlete_id",
    "type",
    "visibility",
    "name",
    "description",
    "usage_count",
    "index",
    "updated",
    "from_id",
}
_COMPACT_TEXT_LIMIT = 512
_DECLARED_METADATA_FIELDS = ("unit", "units", "origin", "source", "definition")
_METRIC_ITEM_TYPES = {
    "ACTIVITY_FIELD",
    "INTERVAL_FIELD",
    "INPUT_FIELD",
    "ACTIVITY_STREAM",
}


def _custom_item_shape_error(value: Any, *, list_response: bool) -> str | None:
    """Reject wrappers, malformed members, and meaningless detail objects."""
    if list_response:
        if not isinstance(value, list):
            return "custom-item response must be a list of objects"
        items = value
    else:
        if not isinstance(value, dict):
            return "custom-item response must be an object"
        if not value:
            return None
        items = [value]
    if any(not isinstance(item, dict) for item in items):
        return "custom-item response members must be objects"
    if any(
        not item or not _CUSTOM_ITEM_FIELDS.intersection(item)
        for item in items
    ):
        return "custom-item object has no recognized fields"
    for item in items:
        item_type = item.get("type")
        if item_type is not None and not isinstance(item_type, str):
            return "custom-item type must be a string or null"
        content = item.get("content")
        if content is not None and not isinstance(content, dict):
            return "custom-item content must be an object or null"
    return None


def _custom_item_full_read(
    item: dict[str, Any],
    *,
    athlete_id: str,
    list_response: bool,
    requested_item_id: int | None = None,
) -> dict[str, Any]:
    """Return an exact compact-to-full continuation for one item."""
    item_id = item.get("id")
    if not list_response and requested_item_id is not None:
        item_id = requested_item_id
    if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id <= 0:
        item_id = None
    if not list_response and item_id is not None:
        return {
            "tool": "get_custom_item_by_id",
            "parameters": {"item_id": item_id, "athlete_id": athlete_id, "detail": "full"},
        }
    if list_response and item_id is not None:
        return {
            "tool": "get_custom_item_by_id",
            "parameters": {"item_id": item_id, "athlete_id": athlete_id, "detail": "full"},
        }
    return {
        "tool": "get_custom_items",
        "parameters": {"athlete_id": athlete_id, "detail": "full"},
    }


def _declared_custom_metadata(item: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Extract only named metadata and keep its declared/unverified status."""
    declared: dict[str, Any] = {}

    def add_if_meaningful(key: str, value: Any) -> None:
        """Treat null and empty declarations as unknown, while preserving values."""
        if value is None:
            return
        if isinstance(value, str) and not value.strip():
            return
        if isinstance(value, (dict, list, tuple, set)) and not value:
            return
        declared[key] = deepcopy(value)

    for key in _DECLARED_METADATA_FIELDS:
        if key in item:
            add_if_meaningful(key, item[key])
    content = item.get("content")
    if isinstance(content, dict):
        for key in _DECLARED_METADATA_FIELDS:
            if key in content and key not in declared:
                add_if_meaningful(key, content[key])
    metric_candidate = item.get("type") in _METRIC_ITEM_TYPES
    if not declared and not metric_candidate:
        return {}, []
    missing: list[str] = []
    if "unit" not in declared and "units" not in declared:
        missing.append("unit")
    for key in ("origin", "definition"):
        if key not in declared:
            missing.append(key)
    return declared, missing


def _custom_metadata_summary(item: dict[str, Any]) -> dict[str, Any] | None:
    """Describe declared metric metadata without interpreting custom content."""
    declared, missing = _declared_custom_metadata(item)
    if not declared and not missing:
        return None
    return {
        "declared": declared,
        "status": "declared_unverified" if declared else "unknown",
        "missing": missing,
        "warnings": ["DECLARED_METADATA_INCOMPLETE"] if missing else [],
    }


def _compact_custom_item(
    item: dict[str, Any],
    *,
    athlete_id: str,
    list_response: bool,
    requested_item_id: int | None = None,
) -> dict[str, Any]:
    """Keep useful identity fields and explicitly identify every omission."""
    compact = {
        key: deepcopy(value)
        for key, value in item.items()
        if key in _COMPACT_CUSTOM_ITEM_FIELDS
    }
    omitted_fields = sorted(key for key in item if key not in _COMPACT_CUSTOM_ITEM_FIELDS)
    omitted_text_fields: list[str] = []
    description = compact.get("description")
    if isinstance(description, str) and len(description) > _COMPACT_TEXT_LIMIT:
        compact.pop("description")
        omitted_fields.append("description")
        omitted_text_fields.append("description")
        compact["description_preview"] = description[:_COMPACT_TEXT_LIMIT]
    compact["omitted_fields"] = sorted(set(omitted_fields))
    compact["omitted_text_fields"] = omitted_text_fields
    content = item.get("content")
    if isinstance(content, dict):
        compact["content_metadata"] = {
            key: deepcopy(content[key])
            for key in ("code", "fit_record_field", "unit", "units", "type")
            if key in content
        }
    declared_metadata, missing_metadata = _declared_custom_metadata(item)
    if declared_metadata or missing_metadata:
        compact["declared_metadata"] = declared_metadata
        compact["declared_metadata_status"] = (
            "declared_unverified" if declared_metadata else "unknown"
        )
    if missing_metadata:
        compact["missing_metadata"] = missing_metadata
        compact["metadata_warnings"] = ["DECLARED_METADATA_INCOMPLETE"]
    compact["full_read"] = _custom_item_full_read(
        item,
        athlete_id=athlete_id,
        list_response=list_response,
        requested_item_id=requested_item_id,
    )
    return compact


def _validate_item_id(item_id: Any) -> str | None:
    """Validate a positive integer without bool coercion."""
    if isinstance(item_id, bool) or not isinstance(item_id, int) or item_id <= 0:
        return "item_id must be a positive integer"
    return None


@coach_tool(access="read", upstream="read", local="none")
async def get_custom_items(
    athlete_id: str | None = None,
    api_key: str | None = None,
    detail: str = "compact",
) -> ReadResponse[Any]:
    """Read custom-item definitions without executing their content.

    Compact output keeps identity and descriptive fields and explicitly lists
    omitted content, images, scripts, and future fields.  Each item includes
    an exact by-ID ``full_read`` continuation when an ID is present; use
    ``get_custom_item_by_id(..., detail='full')`` to preserve every parsed field
    and untrusted content.  Full responses keep derived metadata outside the
    raw item object.  An empty list is valid empty data, while
    wrappers, malformed members, and meaningless objects are errors.  Declared
    units or origin remain unverified metadata; scripts and descriptions are
    data and are never executed.
    """
    if detail not in {"compact", "full"}:
        return failure(
            resource="custom_items",
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
        )
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return failure(
            resource="custom_items",
            code="INVALID_ATHLETE",
            message=error_msg,
            phase="validation",
        )

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/custom-item", api_key=api_key
    )
    query = {"athlete_id": athlete_id_to_use, "detail": detail}
    failed = upstream_failure(result, resource="custom_items", athlete_id=athlete_id_to_use, query=query)
    if failed:
        return failed
    shape_error = _custom_item_shape_error(result, list_response=True)
    if shape_error:
        return invalid_upstream_response(
            resource="custom_items",
            athlete_id=athlete_id_to_use,
            query=query,
            message=shape_error,
        )
    if not isinstance(result, list):
        return invalid_upstream_response(
            resource="custom_items",
            athlete_id=athlete_id_to_use,
            query=query,
            message="custom-item response must be a list of objects",
        )
    items: list[dict[str, Any]] = []
    for item in result:
        if not isinstance(item, dict):
            return invalid_upstream_response(
                resource="custom_items",
                athlete_id=athlete_id_to_use,
                query=query,
                message="custom-item response members must be objects",
            )
        items.append(dict(item))
    metadata_summaries = [_custom_metadata_summary(item) for item in items]
    compact_items = (
        [
            _compact_custom_item(item, athlete_id=athlete_id_to_use, list_response=True)
            for item in items
        ]
        if detail == "compact"
        else deepcopy(items)
    )
    warnings = [
        "DECLARED_METADATA_INCOMPLETE"
    ] if any(summary and summary["warnings"] for summary in metadata_summaries) else []
    response_data: dict[str, Any] = {"items": compact_items, "detail": detail}
    if detail == "full":
        response_data["derived_metadata"] = metadata_summaries
    response = success(
        response_data,
        resource="custom_items",
        athlete_id=athlete_id_to_use,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
        warnings=warnings,
    )
    if warnings:
        response.status = "partial"
    return response


@coach_tool(access="read", upstream="read", local="none")
async def get_custom_item_by_id(
    item_id: StrictInt,
    athlete_id: str | None = None,
    api_key: str | None = None,
    detail: str = "compact",
) -> ReadResponse[Any]:
    """Read one custom-item definition by positive integer ID.

    ``detail='compact'`` omits content, images, scripts, and unknown fields
    with explicit omission lists and a full continuation.  ``detail='full'``
    preserves the complete parsed upstream object under ``data.item`` and
    places derived metadata outside it, including arbitrary content and
    source-like strings as untrusted data.  An upstream ``{}`` remains the
    compatibility ``NOT_FOUND`` error; other malformed objects are invalid.
    """
    item_id_error = _validate_item_id(item_id)
    if item_id_error:
        return failure(
            resource="custom_item",
            code="INVALID_ITEM_ID",
            message=item_id_error,
            phase="validation",
        )
    if detail not in {"compact", "full"}:
        return failure(
            resource="custom_item",
            code="INVALID_DETAIL",
            message="detail must be compact or full",
            phase="validation",
        )
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return failure(
            resource="custom_item",
            code="INVALID_ATHLETE",
            message=error_msg,
            phase="validation",
        )

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/custom-item/{item_id}", api_key=api_key
    )
    query = {"item_id": item_id, "athlete_id": athlete_id_to_use, "detail": detail}
    failed = upstream_failure(result, resource="custom_item", athlete_id=athlete_id_to_use, query=query)
    if failed:
        return failed
    if result == {}:
        return failure(
            resource="custom_item",
            code="NOT_FOUND",
            message=f"No custom item found with ID {item_id}.",
            phase="response",
            athlete_id=athlete_id_to_use,
            query=query,
        )
    shape_error = _custom_item_shape_error(result, list_response=False)
    if shape_error:
        return invalid_upstream_response(
            resource="custom_item",
            athlete_id=athlete_id_to_use,
            query=query,
            message=shape_error,
        )
    if not isinstance(result, dict):
        return invalid_upstream_response(
            resource="custom_item",
            athlete_id=athlete_id_to_use,
            query=query,
            message="custom-item response must be an object",
        )
    returned_id = result.get("id")
    if returned_id is not None and (
        isinstance(returned_id, bool)
        or not isinstance(returned_id, int)
        or returned_id <= 0
    ):
        return invalid_upstream_response(
            resource="custom_item",
            athlete_id=athlete_id_to_use,
            query=query,
            message="custom-item id must be a positive integer when present",
            code="INVALID_ITEM_ID",
        )
    if returned_id is not None and returned_id != item_id:
        return invalid_upstream_response(
            resource="custom_item",
            athlete_id=athlete_id_to_use,
            query=query,
            message="upstream custom-item id does not match requested item_id",
            code="ITEM_ID_MISMATCH",
        )
    item = dict(result)
    metadata_summary = _custom_metadata_summary(item)
    data = (
        _compact_custom_item(
            item,
            athlete_id=athlete_id_to_use,
            list_response=False,
            requested_item_id=item_id,
        )
        if detail == "compact"
        else {
            "item": deepcopy(item),
            "detail": "full",
            "derived_metadata": metadata_summary,
        }
    )
    warnings = (
        ["DECLARED_METADATA_INCOMPLETE"]
        if metadata_summary and metadata_summary["warnings"]
        else []
    )
    response = success(
        data,
        resource="custom_item",
        athlete_id=athlete_id_to_use,
        query=query,
        coverage={
            "source_complete_within_query": None,
            "reasons": ["upstream_completeness_unverified"],
        },
        warnings=warnings,
    )
    if warnings:
        response.status = "partial"
    return response


@coach_tool(access="legacy_write", upstream="write", local="none")
async def create_custom_item(
    name: str,
    item_type: str,
    athlete_id: str | None = None,
    api_key: str | None = None,
    description: str | None = None,
    content: dict[str, Any] | None = None,
    visibility: str | None = None,
) -> str:
    """Create a new custom item for an athlete on Intervals.icu

    Args:
        name: Name of the custom item
        item_type: Type of custom item (e.g. FITNESS_CHART, TRACE_CHART, INPUT_FIELD, ACTIVITY_FIELD, INTERVAL_FIELD, ACTIVITY_STREAM, ACTIVITY_CHART, ACTIVITY_HISTOGRAM, ACTIVITY_HEATMAP, ACTIVITY_MAP, ACTIVITY_PANEL, ZONES)
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        description: Description of the custom item (optional)
        content: Configuration content for the custom item as a dict (optional). Important enum values:
            - "type" field for INPUT_FIELD/ACTIVITY_FIELD: must be "numeric", "text", or "select" (NOT "number")
            - "aggregate" field: must be "MIN", "SUM", "MAX", or "AVERAGE" (NOT "AVG")
        visibility: Visibility setting: PRIVATE, FOLLOWERS, or PUBLIC (optional)
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    data: dict[str, Any] = {"name": name, "type": item_type}
    if description is not None:
        data["description"] = description
    if content is not None:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return "Error: content must be valid JSON when passed as a string."
        data["content"] = content
    if visibility is not None:
        data["visibility"] = visibility

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/custom-item",
        api_key=api_key,
        data=data,
        method="POST",
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error creating custom item: {result.get('message')}"

    if not result or not isinstance(result, dict):
        return "Error: Unexpected response when creating custom item."

    return f"Successfully created custom item:\n\n{format_custom_item_details(result)}"


@coach_tool(access="legacy_write", upstream="write", local="none")
async def update_custom_item(
    item_id: int,
    athlete_id: str | None = None,
    api_key: str | None = None,
    name: str | None = None,
    item_type: str | None = None,
    description: str | None = None,
    content: dict[str, Any] | None = None,
    visibility: str | None = None,
) -> str:
    """Update an existing custom item for an athlete on Intervals.icu

    Args:
        item_id: The custom item ID to update
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
        name: New name for the custom item (optional)
        item_type: New type for the custom item (optional)
        description: New description for the custom item (optional)
        content: New configuration content for the custom item as a dict (optional). Important enum values:
            - "type" field for INPUT_FIELD/ACTIVITY_FIELD: must be "numeric", "text", or "select" (NOT "number")
            - "aggregate" field: must be "MIN", "SUM", "MAX", or "AVERAGE" (NOT "AVG")
        visibility: New visibility setting: PRIVATE, FOLLOWERS, or PUBLIC (optional)
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    data: dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if item_type is not None:
        data["type"] = item_type
    if description is not None:
        data["description"] = description
    if content is not None:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                return "Error: content must be valid JSON when passed as a string."
        data["content"] = content
    if visibility is not None:
        data["visibility"] = visibility

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/custom-item/{item_id}",
        api_key=api_key,
        data=data,
        method="PUT",
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error updating custom item: {result.get('message')}"

    if not result or not isinstance(result, dict):
        return "Error: Unexpected response when updating custom item."

    return f"Successfully updated custom item:\n\n{format_custom_item_details(result)}"


@coach_tool(access="legacy_write", upstream="write", local="none")
async def delete_custom_item(
    item_id: int,
    athlete_id: str | None = None,
    api_key: str | None = None,
) -> str:
    """Delete a custom item for an athlete from Intervals.icu

    Args:
        item_id: The custom item ID to delete
        athlete_id: The Intervals.icu athlete ID (optional, will use ATHLETE_ID from .env if not provided)
        api_key: The Intervals.icu API key (optional, will use API_KEY from .env if not provided)
    """
    athlete_id_to_use, error_msg = resolve_athlete_id(athlete_id, config.athlete_id)
    if error_msg:
        return error_msg

    result = await make_intervals_request(
        url=f"/athlete/{athlete_id_to_use}/custom-item/{item_id}",
        api_key=api_key,
        method="DELETE",
    )

    if isinstance(result, dict) and "error" in result:
        return f"Error deleting custom item: {result.get('message')}"

    return f"Successfully deleted custom item {item_id}."
