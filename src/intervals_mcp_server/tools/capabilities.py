"""Capability introspection; live verification is deliberately never inferred."""

import os
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import ReadResponse, success
from intervals_mcp_server.mcp_instance import mcp


@mcp.tool()
async def get_capabilities() -> ReadResponse[dict]:
    """Describe implemented/configured/live-verified integration capabilities."""
    config = get_config()
    mode = os.getenv("INTERVALS_ACCESS_MODE", "admin").lower()
    if mode not in {"admin", "coach", "readonly"}:
        mode = "readonly"
    safe = ["get_write_status"]
    if mode != "readonly":
        safe.insert(0, "apply_workout_changes")
    data = {
        "server": {
            "version": "0.1.0",
            "mode": mode,
            "live_verified": False,
        },
        "contract": {
            "version": "1.0",
            "implemented": True,
            "configured": bool(config.athlete_id),
            "live_verified": False,
        },
        "access": {"mode": "api_key", "configured": bool(config.api_key), "live_verified": False},
        "read_surface": {
            "implemented": [
                "get_activities",
                "get_activity_details",
                "get_activity_intervals",
                "get_activity_streams",
                "get_activity_messages",
                "get_events",
                "get_event_by_id",
                "get_wellness_data",
                "get_athlete_power_curves",
            ],
            "configured": bool(config.api_key and config.athlete_id),
            "live_verified": False,
        },
        "streams": {"preview": True, "range": True, "full": "export_only"},
        "export": {
            "local_artifact_export": True,
            "configured": True,
            "artifact_dir": str(
                __import__(
                    "intervals_mcp_server.artifacts", fromlist=["artifact_dir"]
                ).artifact_dir()
            ),
            "ttl_seconds": int(os.getenv("INTERVALS_ARTIFACT_TTL_SECONDS", "3600")),
            "max_bytes": int(os.getenv("INTERVALS_ARTIFACT_MAX_BYTES", "0")),
            "max_files": int(os.getenv("INTERVALS_ARTIFACT_MAX_FILES", "0")),
            "live_verified": False,
        },
        "write_guarantees": {
            "conditional_event_write": "unverified",
            "external_id_semantics": "unverified",
            "live_verified": False,
        },
        "settings_history": {"status": "unavailable", "live_verified": False},
        "write_surface": {
            "mode": mode,
            "safe": safe,
            "legacy": mode == "admin",
            "apply_workout_changes": {
                "implemented": True,
                "single_operation": False,
                "package": True,
                "live_verified": False,
            },
            "get_write_status": {
                "implemented": True,
                "reconcile_reads_only": True,
                "live_verified": False,
            },
            "operation_journal": True,
            "live_verified": False,
        },
    }
    return success(data, resource="capabilities", athlete_id=config.athlete_id)
