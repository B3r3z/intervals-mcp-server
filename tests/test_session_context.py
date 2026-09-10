from __future__ import annotations

import asyncio
from typing import Any

import pytest

from intervals_mcp_server.tools.session_context import get_session_context


def _patch_activity_requests(
    monkeypatch: pytest.MonkeyPatch,
    responses: dict[str, Any],
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return responses[kwargs["url"]]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake
    )
    return calls


@pytest.mark.parametrize(
    "arguments",
    [
        {"activity_id": ""},
        {"activity_id": "a1", "sections": []},
        {"activity_id": "a1", "sections": ["comments", "comments"]},
        {"activity_id": "a1", "detail": "verbose"},
    ],
)
def test_context_validation_errors_are_local_and_make_no_request(
    monkeypatch: pytest.MonkeyPatch, arguments: dict[str, Any]
) -> None:
    calls: list[dict[str, Any]] = []

    async def unexpected(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", unexpected
    )

    result = asyncio.run(get_session_context(**arguments))

    assert result.status == "error"
    assert result.source.system == "intervals-mcp-server"
    assert calls == []


def test_default_context_uses_embedded_intervals_and_valid_empty_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "start_date_local": "2026-09-08T07:30:00",
                "icu_ftp": 250,
                "lthr": 165,
                "athlete_max_hr": 190,
                "icu_hr_zones": [130, 150, 170],
                "icu_hr_zone_times": [0, 600, 0],
                "icu_zone_times": [0, 900, 0],
                "moving_time": 3600,
                "elapsed_time": 3720,
                "kg_lifted": 0,
                "hr_load_type": "HRSS",
                "pace_load_type": None,
                "icu_training_load_data": {"source": "upstream"},
                "icu_intervals": [],
                "icu_groups": [],
            },
            "/activity/a1/messages": [],
        },
    )

    result = asyncio.run(get_session_context("a1"))

    assert result.status == "ok"
    assert result.data["requested_sections"] == ["details", "intervals", "comments"]
    sections = result.data["sections"]
    assert set(sections) == {"details", "intervals", "comments"}
    assert sections["intervals"]["status"] == "ok"
    assert sections["intervals"]["data"] == {
        "icu_intervals": [],
        "icu_groups": [],
    }
    assert sections["comments"]["status"] == "ok"
    assert sections["comments"]["data"] == []
    assert "icu_intervals" not in sections["details"]["data"]
    assert "icu_groups" not in sections["details"]["data"]
    assert sections["details"]["thresholds"]["activity_assigned"]["icu_ftp"] == {
        "value": 250,
        "unit": "W",
    }
    assert sections["details"]["data"]["icu_hr_zone_times"] == [0, 600, 0]
    assert sections["details"]["data"]["kg_lifted"] == 0
    assert sections["details"]["field_semantics"] == {
        "scope": "historical_activity",
        "units": {
            "kg_lifted": "kg",
            "moving_time": "s",
            "elapsed_time": "s",
            "icu_hr_zones": "bpm",
            "icu_hr_zone_times": "s",
            "icu_zone_times": "s",
            "lthr": "bpm",
            "athlete_max_hr": "bpm",
        },
        "opaque_upstream_provenance_fields": [
            "hr_load_type",
            "pace_load_type",
            "icu_training_load_data",
        ],
        "interpretation": "Opaque load provenance values are preserved without model inference.",
    }
    assert [call["url"] for call in calls] == [
        "/activity/a1",
        "/activity/a1/messages",
    ]
    assert calls[0]["params"] == {"intervals": True}


def test_context_preserves_nullable_embedded_interval_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "icu_intervals": [
                    {"id": 1, "start_index": 0, "end_index": 60}
                ],
                "icu_groups": None,
            }
        },
    )

    result = asyncio.run(
        get_session_context("a1", sections=["intervals"], detail="compact")
    )

    assert result.status == "ok"
    section = result.data["sections"]["intervals"]
    assert section["status"] == "ok"
    assert section["data"]["icu_groups"] is None
    assert section["projection"]["returned_records"]["icu_groups"] is None
    assert section["projection"]["omitted_records"]["icu_groups"] is None
    assert [call["url"] for call in calls] == ["/activity/a1"]


def test_compact_details_full_follow_up_retrieves_embedded_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "icu_intervals": [{"id": 1, "start_index": 0, "end_index": 10}],
                "icu_groups": [{"id": 7, "intervals": [1]}],
            },
            "/activity/a1/messages": [],
        },
    )

    result = asyncio.run(get_session_context("a1"))

    follow_up = result.data["sections"]["details"]["projection"]["full_follow_up"]
    assert follow_up == {
        "tool": "get_activity_details",
        "parameters": {"activity_id": "a1", "include_intervals": True},
    }


def test_comments_only_does_not_fetch_activity_or_require_athlete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1/messages": [
                {
                    "id": 1, "content": "Hard but controlled", "athlete_id": "i123",
                    "activity_id": "a1", "deleted": "2026-09-09T12:00:00Z", "deleted_by_id": "i123",
                }
            ]
        },
    )

    result = asyncio.run(get_session_context("a1", sections=["comments"]))

    assert result.status == "ok"
    assert list(result.data["sections"]) == ["comments"]
    assert [call["url"] for call in calls] == ["/activity/a1/messages"]
    section = result.data["sections"]["comments"]
    assert section["coverage"]["source_complete_within_query"] is None
    assert section["data"][0]["athlete_id"] == "i123"
    assert section["data"][0]["activity_id"] == "a1"
    assert section["data"][0]["deleted"] == "2026-09-09T12:00:00Z"
    assert section["data"][0]["deleted_by_id"] == "i123"


def test_successful_empty_comments_survive_wellness_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "start_date_local": "2026-09-08T07:30:00",
            },
            "/activity/a1/messages": [],
        },
    )
    wellness_calls: list[dict[str, Any]] = []

    async def wellness_fake(**kwargs: Any) -> Any:
        wellness_calls.append(kwargs)
        return {
            "error": True,
            "code": "HTTP_503",
            "message": "synthetic unavailable",
            "phase": "http",
        }

    monkeypatch.setattr(
        "intervals_mcp_server.tools.wellness.make_intervals_request", wellness_fake
    )

    result = asyncio.run(
        get_session_context(
            "a1",
            sections=["comments", "wellness"],
            athlete_id="i1",
        )
    )

    assert result.status == "partial"
    sections = result.data["sections"]
    assert sections["comments"]["status"] == "ok"
    assert sections["comments"]["data"] == []
    assert sections["wellness"]["status"] == "error"
    assert sections["wellness"]["error"]["code"] == "HTTP_503"
    assert [call["url"] for call in activity_calls] == [
        "/activity/a1",
        "/activity/a1/messages",
    ]
    assert wellness_calls[0]["params"] == {
        "oldest": "2026-09-08",
        "newest": "2026-09-08",
    }


def test_missing_embedded_intervals_falls_back_and_preserves_groups_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "icu_groups": [{"id": 7, "name": "Set"}],
            },
            "/activity/a1/intervals": {
                "error": True,
                "code": "HTTP_503",
                "message": "synthetic unavailable",
                "phase": "http",
            },
        },
    )

    result = asyncio.run(get_session_context("a1", sections=["intervals"]))

    section = result.data["sections"]["intervals"]
    assert result.status == "partial"
    assert section["status"] == "partial"
    assert section["availability"] == "partial"
    assert section["data"] == {"icu_groups": [{"id": 7, "name": "Set"}]}
    assert section["missing"] == ["icu_intervals"]
    assert section["dependencies"]["dedicated_intervals"] == "error"
    assert [call["url"] for call in calls] == [
        "/activity/a1",
        "/activity/a1/intervals",
    ]


def test_malformed_embedded_intervals_does_not_trigger_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Morning ride",
                "icu_intervals": None,
                "icu_groups": [],
            },
        },
    )

    result = asyncio.run(get_session_context("a1", sections=["intervals"]))

    section = result.data["sections"]["intervals"]
    assert result.status == "error"
    assert section["status"] == "error"
    assert section["error"]["code"] == "INVALID_UPSTREAM_RESPONSE"
    assert [call["url"] for call in calls] == ["/activity/a1"]


def test_plan_resolve_uses_raw_event_date_and_exact_numeric_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    activity_calls = _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "start_date_local": "2026-09-08T07:30:00",
                "paired_event_id": 42,
                "icu_ftp": 245,
            }
        },
    )
    event_calls: list[dict[str, Any]] = []
    raw_event = {
        "id": 42,
        "name": "Planned workout",
        "category": "WORKOUT",
        "start_date_local": "2026-09-07T18:00:00",
        "icu_ftp": 255,
    }
    resolved_event = {
        **raw_event,
        "workout_doc": {
            "ftp": 260,
            "steps": [
                {
                    "duration": 300,
                    "_power": {"value": 220, "start": 210, "end": 230},
                }
            ],
        },
    }

    async def events_fake(**kwargs: Any) -> Any:
        event_calls.append(kwargs)
        if kwargs["url"].endswith("/events/42"):
            assert "params" not in kwargs
            return raw_event
        return [resolved_event]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context(
            "a1", sections=["plan"], detail="full", athlete_id="i1"
        )
    )

    section = result.data["sections"]["plan"]
    assert result.status == "ok"
    assert section["data"]["raw_event"] == raw_event
    assert section["data"]["resolved_event"] == resolved_event
    assert section["data"]["thresholds"]["activity_assigned"]["icu_ftp"] == {
        "value": 245,
        "unit": "W",
    }
    assert section["data"]["thresholds"]["event_provided"]["icu_ftp"] == {
        "value": 255,
        "unit": "W",
    }
    assert section["data"]["thresholds"]["workout_document"]["ftp"] == {
        "value": 260,
        "unit": "W",
    }
    assert "PLAN_IS_CURRENT_STORED_VERSION" in section["warnings"]
    assert activity_calls[0]["url"] == "/activity/a1"
    assert event_calls == [
        {"url": "/athlete/i1/events/42", "api_key": None},
        {
            "url": "/athlete/i1/events",
            "api_key": None,
            "params": {
                "oldest": "2026-09-07",
                "newest": "2026-09-07",
                "resolve": True,
            },
        },
    ]


def test_ambiguous_plan_resolution_preserves_raw_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )
    raw = {
        "id": 42,
        "name": "Planned workout",
        "start_date_local": "2026-09-07T18:00:00",
    }

    async def events_fake(**kwargs: Any) -> Any:
        if kwargs["url"].endswith("/events/42"):
            return raw
        return [dict(raw), {**raw, "name": "Duplicate"}]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert result.status == "partial"
    assert section["status"] == "partial"
    assert section["data"]["raw_event"]["id"] == 42
    assert section["data"]["resolved_event"] is None
    assert section["error"]["code"] == "AMBIGUOUS_PAIRED_EVENT"


def test_raw_event_identity_must_match_link_before_resolved_day_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )
    event_calls: list[dict[str, Any]] = []

    async def events_fake(**kwargs: Any) -> Any:
        event_calls.append(kwargs)
        return {
            "id": 41,
            "name": "Wrong event",
            "start_date_local": "2026-09-07T18:00:00",
        }

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert section["status"] == "partial"
    assert section["error"]["code"] == "PAIRED_EVENT_ID_MISMATCH"
    assert section["data"]["raw_event"]["id"] == 41
    assert len(event_calls) == 1


def test_compact_plan_error_still_bounds_raw_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )

    async def events_fake(**_kwargs: Any) -> Any:
        return {
            "id": 42,
            "name": "Plan",
            "description": "x" * 5000,
            "start_date_local": "not-a-date",
            "workout_doc": {"steps": [{"text": "y" * 33000}]},
        }

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert section["error"]["code"] == "PAIRED_EVENT_DATE_INVALID"
    assert len(section["data"]["raw_event"]["description"]) == 4000
    assert "steps" not in section["data"]["raw_event"]["workout_doc"]
    assert section["projection"]["full_follow_up"]["parameters"]["detail"] == "full"


def test_plan_resolve_error_preserves_raw_event_and_upstream_error_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )
    raw = {
        "id": 42,
        "name": "Plan",
        "start_date_local": "2026-09-07T18:00:00",
    }

    async def events_fake(**kwargs: Any) -> Any:
        if kwargs["url"].endswith("/events/42"):
            return raw
        return {
            "error": True,
            "code": "HTTP_429",
            "message": "slow down",
            "phase": "http",
            "http_status": 429,
            "recommended_action": "retry after backoff",
        }

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert section["status"] == "partial"
    assert section["data"]["raw_event"] == raw
    assert section["upstream_error"] == {
        "code": "HTTP_429",
        "message": "slow down",
        "phase": "http",
        "http_status": 429,
        "recommended_action": "retry after backoff",
    }


def test_full_plan_flags_malformed_workout_document_without_dropping_raw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )
    raw = {
        "id": 42,
        "name": "Plan",
        "start_date_local": "2026-09-07T18:00:00",
    }
    resolved = {**raw, "workout_doc": {"steps": {"unexpected": []}}}

    async def events_fake(**kwargs: Any) -> Any:
        return raw if kwargs["url"].endswith("/events/42") else [resolved]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context(
            "a1", sections=["plan"], detail="full", athlete_id="i1"
        )
    )

    section = result.data["sections"]["plan"]
    assert section["status"] == "partial"
    assert section["data"]["resolved_event"] == resolved
    assert section["error"]["code"] == "WORKOUT_DOCUMENT_MALFORMED"


def test_null_workout_document_and_null_targets_remain_available_source_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )
    raw = {
        "id": 42,
        "name": "Plan",
        "start_date_local": "2026-09-07T18:00:00",
        "workout_doc": None,
    }
    resolved = {
        **raw,
        "workout_doc": {
            "steps": [
                {"duration": 300, "_power": None, "_hr": None, "_pace": None}
            ]
        },
    }

    async def events_fake(**kwargs: Any) -> Any:
        return raw if kwargs["url"].endswith("/events/42") else [resolved]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert section["status"] == "ok"
    assert section["data"]["raw_event"]["workout_doc"] is None
    assert section["data"]["resolved_event"]["workout_doc"]["steps"] == [
        {"duration": 300, "_power": None, "_hr": None, "_pace": None}
    ]


def test_missing_plan_link_uses_error_status_and_unavailable_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {"/activity/a1": {"id": "a1", "name": "Unpaired ride"}},
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert result.status == "error"
    assert section["status"] == "error"
    assert section["availability"] == "unavailable"
    assert section["error"]["code"] == "PAIRED_EVENT_MISSING"
    assert "paired_event_id" not in section["data"]


@pytest.mark.parametrize(
    ("paired_event_id", "error_code"),
    [
        (0, "INVALID_PAIRED_EVENT_ID"),
        (False, "INVALID_PAIRED_EVENT_ID"),
        (-1, "INVALID_PAIRED_EVENT_ID"),
    ],
)
def test_null_zero_bool_and_negative_plan_links_are_distinct_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    paired_event_id: Any,
    error_code: str,
) -> None:
    activity = {
        "id": "a1",
        "name": "Invalid pairing",
        "paired_event_id": paired_event_id,
    }
    calls = _patch_activity_requests(
        monkeypatch,
        {"/activity/a1": activity},
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    assert section["status"] == "error"
    assert section["data"]["paired_event_id"] is paired_event_id
    assert section["error"]["code"] == error_code
    assert [call["url"] for call in calls] == ["/activity/a1"]


def test_compact_limits_and_whole_workout_tree_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_text = "ż" * 4100
    messages = [
        {"id": index, "content": long_text if index == 0 else f"message-{index}"}
        for index in range(21)
    ]
    intervals = [
        {"id": index, "average_watts": 0, "future": "keep only in full"}
        for index in range(101)
    ]
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
                "icu_intervals": intervals,
                "icu_groups": [],
            },
            "/activity/a1/messages": messages,
        },
    )
    steps = [
        {
            "duration": 300,
            "_power": {"value": 220, "start": 210, "end": 230},
        }
    ]

    async def events_fake(**kwargs: Any) -> Any:
        raw = {
            "id": 42,
            "name": "Plan",
            "start_date_local": "2026-09-07T18:00:00",
        }
        if kwargs["url"].endswith("/events/42"):
            return raw
        return [{**raw, "workout_doc": {"steps": steps}}]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context(
            "a1",
            sections=["intervals", "comments", "plan"],
            athlete_id="i1",
        )
    )

    sections = result.data["sections"]
    assert len(sections["intervals"]["data"]["icu_intervals"]) == 100
    assert sections["intervals"]["projection"]["omitted_records"] == {
        "icu_intervals": 1,
        "icu_groups": 0,
    }
    assert "future" in sections["intervals"]["projection"]["omitted_fields"]
    compact_messages = sections["comments"]["data"]
    assert len(compact_messages) == 20
    assert len(compact_messages[0]["content"]) == 4000
    assert len(compact_messages[0]["content_fingerprint"]) == 64
    assert sections["comments"]["projection"]["omitted_records"] == 1
    assert sections["plan"]["data"]["resolved_event"]["workout_doc"]["steps"] == steps


def test_large_workout_tree_is_omitted_whole_with_full_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_activity_requests(
        monkeypatch,
        {
            "/activity/a1": {
                "id": "a1",
                "name": "Completed ride",
                "paired_event_id": 42,
            }
        },
    )

    async def events_fake(**kwargs: Any) -> Any:
        raw = {
            "id": 42,
            "name": "Plan",
            "start_date_local": "2026-09-07T18:00:00",
        }
        if kwargs["url"].endswith("/events/42"):
            return raw
        return [
            {
                **raw,
                "workout_doc": {
                    "steps": [{"text": "x" * 33000}],
                },
            }
        ]

    monkeypatch.setattr(
        "intervals_mcp_server.tools.events.make_intervals_request", events_fake
    )

    result = asyncio.run(
        get_session_context("a1", sections=["plan"], athlete_id="i1")
    )

    section = result.data["sections"]["plan"]
    workout_doc = section["data"]["resolved_event"]["workout_doc"]
    assert "steps" not in workout_doc
    assert section["projection"]["workout_steps"] == {
        "status": "omitted",
        "reason": "compact_size_limit",
        "limit_bytes": 32768,
    }
    assert section["projection"]["full_follow_up"] == {
        "tool": "get_session_context",
        "parameters": {
            "activity_id": "a1",
            "sections": ["plan"],
            "detail": "full",
            "athlete_id": "i1",
        },
    }
