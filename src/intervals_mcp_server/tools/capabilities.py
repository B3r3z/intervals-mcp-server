"""Capability introspection; live verification is deliberately never inferred."""

import os
from intervals_mcp_server.config import get_config
from intervals_mcp_server.contracts import ReadResponse, success
from intervals_mcp_server.catalogue import ToolCatalogue, coach_tool, default_catalogue


@coach_tool(access="introspection", upstream="none", local="write")
async def get_capabilities() -> ReadResponse[dict]:
    """Describe implemented/configured/live-verified integration capabilities."""
    return capabilities_for(default_catalogue())


def capabilities_for(catalogue: ToolCatalogue) -> ReadResponse[dict]:
    """Describe the same immutable catalogue installed in the calling server."""
    config = get_config()
    mode = catalogue.mode
    safe = catalogue.names("safe_write", "write_status")
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
            "implemented": catalogue.names("read"),
            "configured": bool(config.api_key and config.athlete_id),
            "live_verified": False,
        },
        "tool_catalogue": catalogue.describe(),
        "streams": {
            "preview": True,
            "range": True,
            "range_max_samples": 10_000,
            "full": "export_only",
        },
        "export": {
            "local_artifact_export": True,
            "source": "intervals-mcp-server artifact store",
            "description": (
                "Temporary UTF-8 JSON assembled from separate Intervals.icu stream "
                "and interval requests; its hash verifies local bytes, not an atomic "
                "upstream snapshot."
            ),
            "client_access": {
                "tool": "get_artifact_chunk",
                "encoding": "base64",
                "max_chunk_bytes": 32_768,
            },
            "source_complete_within_query": None,
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
            "legacy_tools": catalogue.names("legacy_write"),
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
            "publish_analysis_comment": {
                "implemented": True,
                "same_version_replay": "durable local journal; retained records required",
                "verification": "independent activity-message GET by acknowledged ID and exact content",
                "upstream_idempotency": "unverified",
                "lost_acknowledgement_id": "unknown; no automatic republish",
                "live_verified": False,
            },
            "get_analysis_comment_status": {
                "implemented": True,
                "reconcile_reads_only": True,
                "local_journal_may_change": True,
                "live_verified": False,
            },
            "operation_journal": True,
            "live_verified": False,
        },
    }
    response = success(data, resource="capabilities", athlete_id=config.athlete_id)
    response.source.system = "intervals-mcp-server"
    return response
