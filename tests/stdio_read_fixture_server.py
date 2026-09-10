"""Synthetic Intervals upstream used by the stdio MCP protocol harness.

The process installs an ``httpx.MockTransport`` before starting the real
FastMCP server.  Every allowed response is synthetic and every other request
is rejected, so this module cannot reach a live Intervals account.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


_FIXTURE_RESPONSES: dict[str, Any] = {
    "/api/v1/activity/a-session": {
        "id": "a-session",
        "source": "STRAVA",
        "start_date_local": "2026-09-08T07:30:00",
        "_note": "This activity is hidden by the source privacy policy.",
    },
    "/api/v1/activity/a-session/intervals": {
        "icu_intervals": [
            {"id": 11, "start_index": 0, "end_index": 3, "average_watts": 0}
        ],
        "icu_groups": [{"id": 2, "name": "Synthetic set", "intervals": [11]}],
    },
    "/api/v1/activity/a-session/interval-stats": {
        "start_index": 0,
        "end_index": 3,
        "average_watts": 0,
        "average_heartrate": None,
        "source_note": "Synthetic interval stats",
    },
    "/api/v1/activity/a-session/best-efforts": {
        "efforts": [
            {
                "start_index": 0,
                "end_index": 3,
                "average": None,
                "duration": 3,
                "distance": 12.5,
            }
        ],
        "source_note": "Synthetic best efforts",
    },
    "/api/v1/activity/a-session/messages": [
        {
            "id": 7,
            "author": "athlete",
            "content": "Synthetic feedback: hard but controlled.",
            "created": "2026-09-08T09:00:00+02:00",
        }
    ],
    "/api/v1/activity/a-session/streams": [
        {"type": "time", "data": [0, 1.5, 1.5, None]},
        {
            "type": "watts",
            "data": [0, 250, None, 0],
            "data2": [0, 249, None, 0],
            "valueType": "power",
        },
        {"type": "watts", "data": [0, 251, None, 0], "source": "secondary"},
        {"type": "TymeBreathRate", "data": [0, 31, None, 0], "custom": None},
    ],
    "/api/v1/activity/a-artifact/streams": [
        {"type": "time", "data": [0, 1, 2, 3, 4, 5]},
        {
            "type": "watts",
            "data": [0, 245, None, 247, 0, 251],
            "data2": [0, 244, None, 246, 0, 250],
            "units": "W",
        },
        {
            "type": "watts",
            "data2": [0, 243, None, 245, 0, 249],
            "source": "duplicate-data2-only",
        },
        {
            "type": "oddech-żółć-🚴",
            "data": [0, None, "spokojnie", "mocniej", 0, "meta"],
            "custom": {"label": "wielobajtowy ślad"},
        },
    ],
    "/api/v1/activity/a-artifact/intervals": {
        "icu_intervals": [
            {
                "id": 21,
                "start_index": 0,
                "end_index": 6,
                "name": "Próba syntetyczna 🚴",
                "average_watts": 0,
            }
        ],
        "icu_groups": [],
    },
    "/api/v1/activity/a-m1/streams": [
        {"type": "time", "data": [0, 1.5, 1.5, None]},
        {"type": "watts", "data": [200, 201, None, 0]},
        {"type": "raw_watts", "data": [198, 199, None, 0]},
        {"type": "heartrate", "data": [140, 141, None, 0]},
        {"type": "raw_heartrate", "data": [139, 140, None, 0]},
        {"type": "cadence", "data": [80, 81, None, 0]},
    ],
    "/api/v1/activity/a-session/power-curves": [
        {
            "stream_type": "watts",
            "fatigue": "normal",
            "after_kj": 0,
            "secs": [5, 60],
            "values": [0, None],
            "start_index": [0, 2],
            "end_index": [1, 3],
            "wkg_activity_id": ["a-zero", None],
            "submax_values": [[0], [1]],
            "future_field": {"keep": True},
        }
    ],
    "/api/v1/activity/a-context": {
        "id": "a-context",
        "name": "Synthetic session context",
        "type": "Ride",
        "start_date_local": "2026-09-08T07:30:00",
        "description": "Wielobajtowy opis: żółć i rower 🚴",
        "moving_time": 3600,
        "elapsed_time": 3720,
        "icu_ftp": 245,
        "lthr": 165,
        "athlete_max_hr": 190,
        "icu_hr_zones": [130, 150, 170],
        "icu_hr_zone_times": [0, 600, 0],
        "icu_zone_times": [0, 900, 0],
        "hr_load": 0,
        "hr_load_type": "HRSS",
        "pace_load_type": None,
        "icu_training_load_data": {"origin": "synthetic-upstream"},
        "kg_lifted": 0,
        "paired_event_id": 42,
        "icu_intervals": [
            {
                "id": 31,
                "start_index": 0,
                "end_index": 4,
                "average_watts": 0,
                "average_heartrate": None,
                "future_field": {"keep_in_full": True},
            }
        ],
        "icu_groups": [
            {"id": 3, "name": "Synthetic group", "intervals": [31]}
        ],
    },
    "/api/v1/activity/a-context/messages": [
        {
            "id": 17,
            "author": "athlete",
            "content": "Ciężko, ale równo 🚴",
            "created": "2026-09-08T09:00:00+02:00",
            "future_field": 0,
        }
    ],
    "/api/v1/athlete/i123/events/42": {
        "id": 42,
        "name": "Synthetic planned workout",
        "category": "WORKOUT",
        "type": "Ride",
        "start_date_local": "2026-09-07T18:00:00",
        "description": "Stored plan before resolved targets",
        "icu_ftp": 255,
    },
    "/api/v1/athlete/i123/sport-settings/Ride": {
        "id": 7,
        "types": ["Ride"],
        "ftp": 250,
        "w_prime": 20000,
        "after_kj0": 1500,
        "threshold_pace": 4.2,
        "pace_units": "MINS_KM",
        "pace_zones": [80.0, 90.0, 100.0],
        "load_order": "POWER_HR_PACE",
        "future_field": {"keep": True},
    },
    "/api/v1/athlete/i123/custom-item": [
        {
            "id": 7,
            "name": "Synthetic power field",
            "type": "ACTIVITY_FIELD",
            "content": {
                "units": "W",
                "script": "do not execute",
                "future_field": {"keep": True},
            },
        }
    ],
    "/api/v1/athlete/i123/custom-item/7": {
        "id": 7,
        "name": "Synthetic power field",
        "type": "ACTIVITY_FIELD",
        "content": {
            "units": "W",
            "origin": "declared-by-athlete",
            "definition": "Synthetic upstream field",
            "script": "do not execute",
            "future_field": {"keep": True},
        },
    },
    "/api/v1/athlete/i123/custom-item/999": {},
    "/api/v1/athlete/i123/wellness": {
        "2026-09-08": {
            "hrv": 42,
            "hrvSDNN": 55,
            "vo2max": 48.1,
            "custom_hrv": 77,
        }
    },
    "/api/v1/athlete/i123/power-curves": {
        "list": [
            {
                "id": "s0",
                "label": "This season",
                "start_date_local": "2026-01-01",
                "end_date_local": "2026-09-09",
                "weight": 0,
                "moving_time": 12345,
                "secs": [5, 60],
                "values": [0, None],
                "activity_id": ["a-zero", None],
                "watts_per_kg": [0, None],
                "wkg_activity_id": ["a-zero", None],
            },
            {
                "id": "s1",
                "label": "Last season",
                "filter_label": None,
                "secs": [5],
                "values": [300],
                "activity_id": ["a-last"],
            },
        ]
    },
    # Intentionally violates the documented event-list response shape.
    "/api/v1/athlete/i123/events": {"unexpected": []},
}


_FIXTURE_QUERY_RESPONSES: dict[tuple[str, tuple[tuple[str, str], ...]], Any] = {
    (
        "/api/v1/athlete/i123/events",
        (
            ("newest", "2026-09-07"),
            ("oldest", "2026-09-07"),
            ("resolve", "true"),
        ),
    ): [
        {
            "id": 42,
            "name": "Synthetic planned workout",
            "category": "WORKOUT",
            "type": "Ride",
            "start_date_local": "2026-09-07T18:00:00",
            "description": "Resolved current stored plan",
            "icu_ftp": 255,
            "workout_doc": {
                "ftp": 260,
                "lthr": 166,
                "threshold_pace": 4.1,
                "pace_units": "MINS_KM",
                "steps": [
                    {
                        "duration": 300,
                        "_power": {"value": 220, "start": 210, "end": 230},
                        "_hr": {"value": 150, "start": 145, "end": 155},
                        "_pace": {"value": 4.0, "start": 3.9, "end": 4.1},
                    }
                ],
            },
        }
    ],
}


def _record_request(request: httpx.Request) -> None:
    log_path = os.environ.get("READ_FIXTURE_REQUEST_LOG")
    if not log_path:
        raise RuntimeError("READ_FIXTURE_REQUEST_LOG is required")
    row = {
        "method": request.method,
        "path": request.url.path,
        "query": sorted(request.url.params.multi_items()),
    }
    with Path(log_path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _handle(request: httpx.Request) -> httpx.Response:
    _record_request(request)
    if request.url.host != "synthetic.invalid" or request.method != "GET":
        raise RuntimeError(f"blocked non-fixture request: {request.method} {request.url}")
    query_key = tuple(sorted(request.url.params.multi_items()))
    try:
        payload = _FIXTURE_QUERY_RESPONSES.get(
            (request.url.path, query_key), _FIXTURE_RESPONSES[request.url.path]
        )
    except KeyError as exc:
        raise RuntimeError(f"blocked unknown fixture route: {request.url.path}") from exc
    return httpx.Response(200, json=payload, request=request)


def main() -> None:
    """Run the repository's actual MCP server with the synthetic transport."""
    from intervals_mcp_server import server
    from intervals_mcp_server.api import client as api_client

    fixture_client = httpx.AsyncClient(transport=httpx.MockTransport(_handle))
    api_client.httpx_client = fixture_client
    server.mcp.run()


if __name__ == "__main__":
    main()
