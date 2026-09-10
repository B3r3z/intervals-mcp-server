"""MCP access to bounded, integrity-checked local artifact bytes."""

from typing import Any

from pydantic import StrictInt

from intervals_mcp_server.artifacts import (
    MAX_ARTIFACT_CHUNK_BYTES,
    ArtifactStoreError,
    read_artifact_chunk,
)
from intervals_mcp_server.contracts import ReadResponse, failure, success
from intervals_mcp_server.catalogue import coach_tool


def _local_source(response: ReadResponse[Any]) -> ReadResponse[Any]:
    response.source.system = "intervals-mcp-server"
    return response


@coach_tool(access="read", upstream="none", local="read")
async def get_artifact_chunk(
    artifact_id: str,
    offset: StrictInt = 0,
    max_bytes: StrictInt = MAX_ARTIFACT_CHUNK_BYTES,
) -> ReadResponse[Any]:
    """Read one verified byte range from a temporary activity export.

    Use the opaque ``artifact_id`` returned by ``export_activity_data``. Decode
    each base64 chunk and concatenate the raw bytes in offset order. Verify the
    SHA-256 of all bytes against the export manifest before decoding the full
    document as UTF-8 JSON; an individual chunk can split a multibyte character.
    ``response_complete`` covers this requested chunk only. ``eof`` and
    ``next_offset`` state whether more artifact bytes remain. The artifact is a
    local composite of separate stream and interval requests, so upstream source
    completeness and atomicity remain unknown.
    """
    query = {
        "artifact_id": artifact_id,
        "offset": offset,
        "max_bytes": max_bytes,
    }
    try:
        data = read_artifact_chunk(
            artifact_id,
            offset=offset,
            max_bytes=max_bytes,
        )
    except ArtifactStoreError as exc:
        phase = "validation" if exc.code.startswith("INVALID_") else "artifact"
        recommended_action = (
            "Use a lowercase 32-hex artifact ID and a byte range within the artifact."
            if phase == "validation"
            else "Run export_activity_data again and restart retrieval from offset 0."
        )
        return _local_source(
            failure(
                resource="artifact_chunk",
                code=exc.code,
                message=exc.message,
                phase=phase,
                query=query,
                recommended_action=recommended_action,
            )
        )
    has_remaining_bytes = not data["eof"]
    reasons = ["source_completeness_unknown"]
    if has_remaining_bytes:
        reasons.append("artifact_has_remaining_bytes")
    response = success(
        data,
        resource="artifact_chunk",
        query=query,
        coverage={
            "source_complete_within_query": None,
            "response_complete": True,
            "truncated": has_remaining_bytes,
            "reasons": reasons,
        },
        pagination={
            "snapshot_id": data["snapshot_id"],
            "next_cursor": str(data["next_offset"]) if has_remaining_bytes else None,
        },
        warnings=[
            "Artifact hash verifies local content assembled from separate upstream reads; "
            "it does not prove an atomic upstream snapshot."
        ],
    )
    if has_remaining_bytes:
        response.status = "partial"
    return _local_source(response)
