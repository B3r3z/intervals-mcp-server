"""Safe, short-lived local artifacts for large activity reads."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import stat
import tempfile
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ARTIFACT_MANIFEST_VERSION = 1
MAX_ARTIFACT_CHUNK_BYTES = 32_768
_MAX_MANIFEST_BYTES = 65_536
_ARTIFACT_ID = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PAYLOAD_NAME = re.compile(r"^(?P<artifact_id>[0-9a-f]{32})\.json$")
_STORE_LOCK = threading.RLock()
_ARTIFACT_DESCRIPTION = (
    "Local activity JSON assembled from separate stream and interval requests; "
    "its hash does not prove an atomic upstream snapshot."
)

Clock = Callable[[], datetime]


class ArtifactStoreError(RuntimeError):
    """A stable, non-sensitive failure raised by artifact storage helpers."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def artifact_dir() -> Path:
    """Return the configured artifact directory as a canonical path."""
    configured = os.environ.get("INTERVALS_ARTIFACT_DIR")
    root = Path(configured) if configured else Path.cwd() / ".runtime" / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _utc_now(now: Clock | None = None) -> datetime:
    value = (now or (lambda: datetime.now(timezone.utc)))()
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("artifact clock must return an aware datetime")
    return value.astimezone(timezone.utc)


def _positive_env(name: str, default: int, *, allow_zero: bool = False) -> int:
    value = int(os.environ.get(name, str(default)))
    minimum = 0 if allow_zero else 1
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def _pair_paths(root: Path, artifact_id: str) -> tuple[Path, Path]:
    return root / f"{artifact_id}.json", root / f"{artifact_id}.manifest.json"


def _path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def _require_regular_store_file(root: Path, path: Path) -> None:
    if path.parent != root or path.is_symlink():
        raise ArtifactStoreError(
            "ARTIFACT_PATH_UNSAFE", "Artifact storage path is not safe."
        )
    try:
        file_stat = path.stat(follow_symlinks=False)
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ArtifactStoreError(
            "ARTIFACT_READ_FAILED", "Artifact storage could not be read."
        ) from exc
    if not stat.S_ISREG(file_stat.st_mode) or resolved.parent != root:
        raise ArtifactStoreError(
            "ARTIFACT_PATH_UNSAFE", "Artifact storage path is not safe."
        )


def _parse_aware_timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    return parsed.astimezone(timezone.utc)


def _safe_manifest_text(value: Any, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= maximum
        and all(ord(character) >= 32 for character in value)
    )


def _validated_manifest(root: Path, artifact_id: str) -> dict[str, Any]:
    payload_path, sidecar_path = _pair_paths(root, artifact_id)
    payload_exists = _path_exists(payload_path)
    sidecar_exists = _path_exists(sidecar_path)
    if not payload_exists and not sidecar_exists:
        raise ArtifactStoreError("ARTIFACT_NOT_FOUND", "Artifact was not found.")
    if payload_exists:
        _require_regular_store_file(root, payload_path)
    if sidecar_exists:
        _require_regular_store_file(root, sidecar_path)
    if not payload_exists or not sidecar_exists:
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    try:
        if sidecar_path.stat(follow_symlinks=False).st_size > _MAX_MANIFEST_BYTES:
            raise ArtifactStoreError(
                "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
            )
        decoded = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except ArtifactStoreError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        ) from exc
    if not isinstance(decoded, dict):
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    required = {
        "manifest_version",
        "artifact_id",
        "format",
        "encoding",
        "size",
        "artifact_hash",
        "snapshot_id",
        "source",
        "created_at",
        "expires_at",
        "provenance",
        "description",
    }
    if not required.issubset(decoded):
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    size = decoded.get("size")
    digest = decoded.get("artifact_hash")
    provenance = decoded.get("provenance")
    if (
        isinstance(decoded.get("manifest_version"), bool)
        or decoded.get("manifest_version") != ARTIFACT_MANIFEST_VERSION
        or decoded.get("artifact_id") != artifact_id
        or decoded.get("format") != "json"
        or decoded.get("encoding") != "utf-8"
        or isinstance(size, bool)
        or not isinstance(size, int)
        or size < 0
        or not isinstance(digest, str)
        or _SHA256.fullmatch(digest) is None
        or not _safe_manifest_text(decoded.get("snapshot_id"), maximum=256)
        or decoded.get("snapshot_id") != digest
        or not _safe_manifest_text(decoded.get("source"), maximum=512)
        or provenance != _artifact_provenance()
        or decoded.get("description") != _ARTIFACT_DESCRIPTION
    ):
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    created_at = _parse_aware_timestamp(decoded.get("created_at"))
    expires_at = _parse_aware_timestamp(decoded.get("expires_at"))
    if expires_at <= created_at:
        raise ArtifactStoreError(
            "ARTIFACT_MANIFEST_INVALID", "Artifact manifest metadata is invalid."
        )
    try:
        actual_size = payload_path.stat(follow_symlinks=False).st_size
    except OSError as exc:
        raise ArtifactStoreError(
            "ARTIFACT_READ_FAILED", "Artifact storage could not be read."
        ) from exc
    if actual_size != size:
        raise ArtifactStoreError(
            "ARTIFACT_INTEGRITY_MISMATCH", "Artifact integrity verification failed."
        )
    return decoded


def _verify_payload_and_capture(
    root: Path,
    artifact_id: str,
    manifest: dict[str, Any],
    *,
    offset: int = 0,
    max_bytes: int = 0,
) -> bytes:
    """Hash one file pass and retain only the requested overlap in memory."""
    payload_path, _sidecar_path = _pair_paths(root, artifact_id)
    _require_regular_store_file(root, payload_path)
    expected_size = manifest["size"]
    expected_hash = manifest["artifact_hash"]
    captured = bytearray()
    try:
        before = payload_path.stat(follow_symlinks=False)
        digest = hashlib.sha256()
        measured_size = 0
        with payload_path.open("rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ArtifactStoreError(
                    "ARTIFACT_PATH_UNSAFE", "Artifact storage path is not safe."
                )
            while block := handle.read(65_536):
                block_start = measured_size
                block_end = block_start + len(block)
                digest.update(block)
                if max_bytes:
                    overlap_start = max(offset, block_start)
                    overlap_end = min(offset + max_bytes, block_end)
                    if overlap_start < overlap_end:
                        captured.extend(
                            block[
                                overlap_start - block_start : overlap_end - block_start
                            ]
                        )
                measured_size = block_end
            after = os.fstat(handle.fileno())
            if (
                measured_size != expected_size
                or digest.hexdigest() != expected_hash
                or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns
            ):
                raise ArtifactStoreError(
                    "ARTIFACT_INTEGRITY_MISMATCH",
                    "Artifact integrity verification failed.",
                )
    except ArtifactStoreError:
        raise
    except OSError as exc:
        raise ArtifactStoreError(
            "ARTIFACT_READ_FAILED", "Artifact storage could not be read."
        ) from exc
    return bytes(captured)


def _artifact_provenance() -> dict[str, Any]:
    return {
        "snapshot_scope": "local_composite_artifact",
        "upstream_atomic_snapshot": False,
        "upstream_requests": ["activity_streams", "activity_intervals"],
        "stream_selection": "all_returned_streams_no_types_filter",
        "source_complete_within_query": None,
    }


def _sample_counts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    streams = payload.get("streams")
    if not isinstance(streams, list):
        return []
    return [
        {
            "index": index,
            "type": stream.get("type"),
            "count": len(stream["data"]) if isinstance(stream.get("data"), list) else None,
            "data2_count": (
                len(stream["data2"])
                if isinstance(stream.get("data2"), list)
                else None
            ),
        }
        for index, stream in enumerate(streams)
        if isinstance(stream, dict)
        and (
            isinstance(stream.get("data"), list)
            or isinstance(stream.get("data2"), list)
        )
    ]


def _write_atomic(path: Path, raw: bytes, *, prefix: str, suffix: str) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _remove_valid_pair(root: Path, artifact_id: str) -> bool:
    payload_path, sidecar_path = _pair_paths(root, artifact_id)
    try:
        _require_regular_store_file(root, payload_path)
        _require_regular_store_file(root, sidecar_path)
        payload_path.unlink()
        sidecar_path.unlink()
    except (ArtifactStoreError, OSError):
        return False
    return True


def _valid_pairs(root: Path) -> list[tuple[str, datetime]]:
    pairs: list[tuple[str, datetime]] = []
    try:
        entries = list(root.iterdir())
    except OSError:
        return pairs
    for path in entries:
        match = _PAYLOAD_NAME.fullmatch(path.name)
        if match is None:
            continue
        artifact_id = match.group("artifact_id")
        try:
            manifest = _validated_manifest(root, artifact_id)
            _verify_payload_and_capture(root, artifact_id, manifest)
            created_at = _parse_aware_timestamp(manifest["created_at"])
        except ArtifactStoreError:
            continue
        pairs.append((artifact_id, created_at))
    return pairs


def _enforce_retention(root: Path, max_files: int, newest_id: str) -> None:
    if max_files == 0:
        return
    pairs = sorted(
        _valid_pairs(root),
        key=lambda pair: (pair[0] == newest_id, pair[1], pair[0]),
        reverse=True,
    )
    for artifact_id, _created_at in pairs[max_files:]:
        _remove_valid_pair(root, artifact_id)


def write_activity_artifact(
    payload: dict[str, Any],
    *,
    source: str,
    expires_in: int | None = None,
    now: Clock | None = None,
) -> dict[str, Any]:
    """Derive local content identity, then publish payload and sidecar together.

    A failed sidecar write removes the newly named payload. Existing artifacts
    are cleaned or retained only after the new pair has been published. The
    snapshot and artifact hash describe the exact serialized bytes written here.
    """
    ttl_seconds = (
        _positive_env("INTERVALS_ARTIFACT_TTL_SECONDS", 3_600)
        if expires_in is None
        else expires_in
    )
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
        raise ValueError("artifact TTL must be positive")
    if not _safe_manifest_text(source, maximum=512):
        raise ValueError("artifact source must be a non-empty safe string")
    max_bytes = _positive_env("INTERVALS_ARTIFACT_MAX_BYTES", 0, allow_zero=True)
    max_files = _positive_env("INTERVALS_ARTIFACT_MAX_FILES", 0, allow_zero=True)
    raw = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if max_bytes and len(raw) > max_bytes:
        raise ValueError("artifact exceeds configured maximum size")
    digest = hashlib.sha256(raw).hexdigest()
    created_at = _utc_now(now)
    expires_at = created_at + timedelta(seconds=ttl_seconds)
    provenance = _artifact_provenance()
    description = _ARTIFACT_DESCRIPTION

    with _STORE_LOCK:
        try:
            root = artifact_dir()
        except OSError as exc:
            raise ArtifactStoreError(
                "ARTIFACT_READ_FAILED", "Artifact storage could not be read."
            ) from exc
        while True:
            artifact_id = secrets.token_hex(16)
            target, sidecar = _pair_paths(root, artifact_id)
            if not _path_exists(target) and not _path_exists(sidecar):
                break
        stored_manifest = {
            "manifest_version": ARTIFACT_MANIFEST_VERSION,
            "artifact_id": artifact_id,
            "format": "json",
            "encoding": "utf-8",
            "size": len(raw),
            "artifact_hash": digest,
            "snapshot_id": digest,
            "source": source,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "provenance": provenance,
            "description": description,
        }
        side_raw = json.dumps(
            stored_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        try:
            _write_atomic(
                target,
                raw,
                prefix=f".{artifact_id}.",
                suffix=".payload.tmp",
            )
            _write_atomic(
                sidecar,
                side_raw,
                prefix=f".{artifact_id}.",
                suffix=".manifest.tmp",
            )
        except OSError:
            if _path_exists(target) and not target.is_symlink():
                try:
                    target.unlink()
                except OSError:
                    pass
            if _path_exists(sidecar) and not sidecar.is_symlink():
                try:
                    sidecar.unlink()
                except OSError:
                    pass
            raise

        # Cleanup and retention occur only after the new pair is fully published.
        cleanup_expired(root, now=lambda: created_at)
        _enforce_retention(root, max_files, artifact_id)

    return {
        "artifact_id": artifact_id,
        "snapshot_id": digest,
        "format": "json",
        "encoding": "utf-8",
        "size": len(raw),
        "hash": {"algorithm": "sha256", "value": digest},
        "sample_counts": _sample_counts(payload),
        "range": payload.get("range"),
        "source": source,
        "description": description,
        "provenance": provenance,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "access": {"kind": "local_file", "path": str(target)},
        "client_access": {
            "tool": "get_artifact_chunk",
            "artifact_id": artifact_id,
            "encoding": "base64",
            "max_chunk_bytes": MAX_ARTIFACT_CHUNK_BYTES,
            "instructions": (
                "Decode and concatenate chunks as bytes, verify SHA-256 against the "
                "export manifest, then decode the complete UTF-8 JSON document."
            ),
        },
    }


def read_artifact_chunk(
    artifact_id: str,
    *,
    offset: int = 0,
    max_bytes: int = MAX_ARTIFACT_CHUNK_BYTES,
    now: Clock | None = None,
) -> dict[str, Any]:
    """Verify a complete artifact, then return one bounded byte range."""
    if not isinstance(artifact_id, str) or _ARTIFACT_ID.fullmatch(artifact_id) is None:
        raise ArtifactStoreError(
            "INVALID_ARTIFACT_ID", "Artifact ID must be 32 lowercase hexadecimal characters."
        )
    if (
        isinstance(offset, bool)
        or not isinstance(offset, int)
        or offset < 0
        or isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or not 1 <= max_bytes <= MAX_ARTIFACT_CHUNK_BYTES
    ):
        raise ArtifactStoreError(
            "INVALID_CHUNK_RANGE", "Chunk offset or maximum byte count is invalid."
        )

    with _STORE_LOCK:
        try:
            root = artifact_dir()
        except OSError as exc:
            raise ArtifactStoreError(
                "ARTIFACT_READ_FAILED", "Artifact storage could not be read."
            ) from exc
        manifest = _validated_manifest(root, artifact_id)
        expires_at = _parse_aware_timestamp(manifest["expires_at"])
        if expires_at <= _utc_now(now):
            raise ArtifactStoreError("ARTIFACT_EXPIRED", "Artifact has expired.")
        total_bytes = manifest["size"]
        if offset > total_bytes:
            raise ArtifactStoreError(
                "INVALID_CHUNK_RANGE", "Chunk offset exceeds the artifact size."
            )
        chunk = _verify_payload_and_capture(
            root,
            artifact_id,
            manifest,
            offset=offset,
            max_bytes=max_bytes,
        )

    next_offset = offset + len(chunk)
    eof = next_offset >= total_bytes
    return {
        "artifact_id": artifact_id,
        "encoding": "base64",
        "offset": offset,
        "returned_bytes": len(chunk),
        "next_offset": next_offset,
        "total_bytes": total_bytes,
        "eof": eof,
        "chunk_base64": base64.b64encode(chunk).decode("ascii"),
        "chunk_hash": {"algorithm": "sha256", "value": hashlib.sha256(chunk).hexdigest()},
        "artifact_hash": {
            "algorithm": "sha256",
            "value": manifest["artifact_hash"],
        },
        "snapshot_id": manifest["snapshot_id"],
        "source": manifest["source"],
        "description": manifest["description"],
        "provenance": manifest["provenance"],
        "created_at": manifest["created_at"],
        "expires_at": manifest["expires_at"],
    }


def artifact_is_expired(
    manifest: dict[str, Any], *, now: Clock | None = None
) -> bool:
    """Return true for expired or unusable expiry metadata."""
    try:
        return _parse_aware_timestamp(manifest.get("expires_at")) <= _utc_now(now)
    except (ArtifactStoreError, ValueError):
        return True


def cleanup_expired(root: Path | None = None, *, now: Clock | None = None) -> int:
    """Remove expired, validated store pairs and leave suspicious files untouched."""
    configured_directory = artifact_dir()
    if root is not None and root.resolve() != configured_directory:
        return 0
    directory = configured_directory
    current_time = _utc_now(now)
    removed = 0
    with _STORE_LOCK:
        for artifact_id, _created_at in _valid_pairs(directory):
            try:
                manifest = _validated_manifest(directory, artifact_id)
                expiry = _parse_aware_timestamp(manifest["expires_at"])
            except ArtifactStoreError:
                continue
            if expiry <= current_time and _remove_valid_pair(directory, artifact_id):
                removed += 1
    return removed
