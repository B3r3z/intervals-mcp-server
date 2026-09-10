import asyncio
from typing import Any

import pytest

from intervals_mcp_server.tools import custom_items


def test_custom_items_list_is_structured_and_preserves_raw_content(monkeypatch) -> None:
    payload = [
        {
            "id": 1,
            "name": "Power chart",
            "type": "ACTIVITY_CHART",
            "description": "Untrusted athlete description",
            "content": {
                "script": "do not execute",
                "source": "declared-by-user",
                "units": "W",
                "future_field": {"value": 1},
            },
        }
    ]

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(custom_items.get_custom_items(athlete_id="athlete", detail="full"))

    assert result.status == "partial"
    assert result.data["items"][0] == payload[0]
    assert result.data["items"][0]["content"]["script"] == "do not execute"
    assert result.coverage.source_complete_within_query is None


def test_custom_items_compact_lists_omissions_and_exact_full_continuation(monkeypatch) -> None:
    payload = [
        {
            "id": 7,
            "name": "Chart",
            "type": "FITNESS_CHART",
            "content": {"script": "untrusted"},
            "image": "base64-image",
            "future_field": {"nested": True},
        }
    ]

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))

    item = result.data["items"][0]
    assert item["name"] == "Chart"
    assert set(item["omitted_fields"]) == {"content", "future_field", "image"}
    assert item["full_read"] == {
        "tool": "get_custom_item_by_id",
        "parameters": {"item_id": 7, "athlete_id": "athlete", "detail": "full"},
    }
    assert "content" not in item


def test_custom_item_by_id_full_preserves_unknown_content(monkeypatch) -> None:
    payload = {
        "id": 9,
        "name": "Input",
        "type": "INPUT_FIELD",
        "content": {"script": "never execute", "units": "W"},
        "from_athlete": {"id": "other"},
        "future_field": [1, None, 0],
    }

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(
        custom_items.get_custom_item_by_id(9, athlete_id="athlete", detail="full")
    )

    assert result.status == "partial"
    assert result.data["item"] == payload
    assert result.data["item"]["content"]["script"] == "never execute"
    assert result.data["derived_metadata"]["status"] == "declared_unverified"


def test_custom_reads_distinguish_empty_not_found_and_malformed(monkeypatch) -> None:
    responses: list[Any] = [[], {}, {"items": []}, [{"future_only": True}]]
    calls: list[str] = []

    async def fake_request(**kwargs: Any) -> Any:
        calls.append(kwargs["url"])
        return responses.pop(0)

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    empty = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))
    not_found = asyncio.run(custom_items.get_custom_item_by_id(7, athlete_id="athlete"))
    wrapped = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))
    meaningless = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))

    assert empty.status == "ok" and empty.data["items"] == []
    assert not_found.status == "error" and not_found.error is not None
    assert not_found.error.code == "NOT_FOUND"
    assert wrapped.status == "error" and wrapped.error is not None
    assert wrapped.error.code == "INVALID_UPSTREAM_RESPONSE"
    assert meaningless.status == "error" and meaningless.error is not None
    assert calls == [
        "/athlete/athlete/custom-item",
        "/athlete/athlete/custom-item/7",
        "/athlete/athlete/custom-item",
        "/athlete/athlete/custom-item",
    ]


def test_custom_item_by_id_rejects_bool_before_http(monkeypatch) -> None:
    calls: list[Any] = []

    async def fake_request(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(
        custom_items.get_custom_item_by_id(True, athlete_id="athlete")  # type: ignore[arg-type]
    )

    assert result.status == "error"
    assert result.error is not None and result.error.code == "INVALID_ITEM_ID"
    assert calls == []


def test_custom_item_by_id_requires_matching_positive_returned_id(monkeypatch) -> None:
    responses: list[Any] = [
        {"name": "No explicit ID", "type": "INPUT_FIELD"},
        {"id": 8, "name": "Wrong ID", "type": "INPUT_FIELD"},
    ]

    async def fake_request(**_kwargs: Any) -> Any:
        return responses.pop(0)

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    missing_id = asyncio.run(
        custom_items.get_custom_item_by_id(7, athlete_id="athlete")
    )
    mismatch = asyncio.run(
        custom_items.get_custom_item_by_id(7, athlete_id="athlete")
    )

    assert missing_id.status == "partial"
    assert missing_id.data["full_read"]["parameters"]["item_id"] == 7
    assert mismatch.status == "error"
    assert mismatch.error is not None and mismatch.error.code == "ITEM_ID_MISMATCH"


def test_custom_compact_metadata_is_declared_unverified_without_script_provenance(
    monkeypatch,
) -> None:
    payload = [
        {
            "id": 11,
            "name": "Power input",
            "type": "INPUT_FIELD",
            "content": {
                "units": "W",
                "script": "source code is data",
                "from_athlete": {"id": "not provenance"},
            },
        }
    ]

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))

    item = result.data["items"][0]
    assert result.status == "partial"
    assert item["declared_metadata"] == {"units": "W"}
    assert item["declared_metadata_status"] == "declared_unverified"
    assert set(item["missing_metadata"]) == {"origin", "definition"}
    assert "from_athlete" not in item["declared_metadata"]
    assert "script" not in item["declared_metadata"]


def test_custom_metric_without_declarations_reports_unknown_metadata(monkeypatch) -> None:
    payload = [{"id": 12, "name": "Raw field", "type": "ACTIVITY_FIELD"}]

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(custom_items.get_custom_items(athlete_id="athlete"))

    item = result.data["items"][0]
    assert result.status == "partial"
    assert item["declared_metadata"] == {}
    assert item["declared_metadata_status"] == "unknown"
    assert set(item["missing_metadata"]) == {"unit", "origin", "definition"}


def test_custom_metric_full_keeps_raw_and_derived_warning_outside_it(monkeypatch) -> None:
    payload = {"id": 13, "name": "Raw interval", "type": "INTERVAL_FIELD"}

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(
        custom_items.get_custom_item_by_id(13, athlete_id="athlete", detail="full")
    )

    assert result.status == "partial"
    assert result.data["item"] == payload
    assert result.data["derived_metadata"]["status"] == "unknown"
    assert set(result.data["derived_metadata"]["missing"]) == {
        "unit",
        "origin",
        "definition",
    }


def test_custom_metric_empty_metadata_is_unknown_in_full_response(monkeypatch) -> None:
    payload = [
        {
            "id": 14,
            "name": "Empty declarations",
            "type": "ACTIVITY_STREAM",
            "unit": None,
            "content": {"units": "", "origin": None, "definition": "  "},
        }
    ]

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    result = asyncio.run(
        custom_items.get_custom_items(athlete_id="athlete", detail="full")
    )

    assert result.status == "partial"
    summary = result.data["derived_metadata"][0]
    assert summary["declared"] == {}
    assert summary["status"] == "unknown"
    assert set(summary["missing"]) == {"unit", "origin", "definition"}


@pytest.mark.parametrize(
    ("reader", "detail"),
    [
        ("list", "compact"),
        ("list", "full"),
        ("by_id", "compact"),
        ("by_id", "full"),
    ],
)
def test_custom_non_string_type_is_structured_shape_error(
    monkeypatch, reader: str, detail: str
) -> None:
    payload: Any = (
        [{"id": 501, "name": "Malformed type", "type": {}}]
        if reader == "list"
        else {"id": 501, "name": "Malformed type", "type": {}}
    )

    async def fake_request(**_kwargs: Any) -> Any:
        return payload

    monkeypatch.setattr(custom_items, "make_intervals_request", fake_request)
    if reader == "list":
        result = asyncio.run(
            custom_items.get_custom_items(athlete_id="athlete", detail=detail)
        )
    else:
        result = asyncio.run(
            custom_items.get_custom_item_by_id(
                501, athlete_id="athlete", detail=detail
            )
        )

    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "INVALID_UPSTREAM_RESPONSE"
