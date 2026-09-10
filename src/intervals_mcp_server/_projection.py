"""Private field-copying primitives shared by bounded evidence presentations."""

from copy import deepcopy
from typing import Any

COMPACT_TEXT_CHARS = 4_000


def copy_projected(
    row: dict[str, Any],
    fields: tuple[str, ...],
    *,
    path: str,
    truncated_text: list[dict[str, Any]],
) -> tuple[dict[str, Any], set[str]]:
    projected: dict[str, Any] = {}
    for field in fields:
        if field not in row:
            continue
        value = deepcopy(row[field])
        if isinstance(value, str) and len(value) > COMPACT_TEXT_CHARS:
            truncated_text.append(
                {
                    "path": f"{path}.{field}",
                    "original_chars": len(value),
                    "returned_chars": COMPACT_TEXT_CHARS,
                }
            )
            value = value[:COMPACT_TEXT_CHARS]
        projected[field] = value
    return projected, set(row).difference(fields)


def project_record_list(
    rows: list[dict[str, Any]],
    fields: tuple[str, ...],
    *,
    limit: int,
    path: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    truncated_text: list[dict[str, Any]] = []
    omitted_fields: set[str] = set()
    projected: list[dict[str, Any]] = []
    for index, row in enumerate(rows[:limit]):
        item, omitted = copy_projected(
            row,
            fields,
            path=f"{path}[{index}]",
            truncated_text=truncated_text,
        )
        projected.append(item)
        omitted_fields.update(omitted)
    return projected, {
        "returned_records": len(projected),
        "omitted_records": max(0, len(rows) - limit),
        "omitted_fields": sorted(omitted_fields),
        "truncated_text": truncated_text,
        "upstream_order_preserved": True,
        "order_semantics": "unknown",
    }
