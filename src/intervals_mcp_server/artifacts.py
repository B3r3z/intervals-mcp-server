"""Safe, short-lived local artifacts for large activity reads."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def artifact_dir() -> Path:
    configured = os.environ.get("INTERVALS_ARTIFACT_DIR")
    root = Path(configured) if configured else Path.cwd() / ".runtime" / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def write_activity_artifact(payload: dict[str, Any], *, snapshot_id: str,
                            source: str, expires_in: int = 3600) -> dict[str, Any]:
    expires_in = int(os.environ.get("INTERVALS_ARTIFACT_TTL_SECONDS", expires_in))
    if expires_in <= 0:
        raise ValueError("artifact TTL must be positive")
    root = artifact_dir()
    cleanup_expired(root)
    max_files = int(os.environ.get("INTERVALS_ARTIFACT_MAX_FILES", "0"))
    if max_files > 0:
        pairs = sorted((p for p in root.glob("*.json") if not p.name.endswith(".manifest.json")), key=lambda p: p.stat().st_mtime)
        for old in pairs[max(0, max_files - 1):]:
            sidecar_old = old.with_suffix(".manifest.json")
            old.unlink(missing_ok=True)
            if sidecar_old.exists():
                sidecar_old.unlink()
    artifact_id = secrets.token_hex(16)
    target = (root / f"{artifact_id}.json").resolve()
    if target.parent != root:
        raise ValueError("artifact path escapes configured directory")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(raw).hexdigest()
    max_bytes = int(os.environ.get("INTERVALS_ARTIFACT_MAX_BYTES", "0"))
    if max_bytes and len(raw) > max_bytes:
        raise ValueError("artifact exceeds configured maximum size")
    fd, temporary = tempfile.mkstemp(prefix=f".{artifact_id}.", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    created = datetime.now(timezone.utc)
    expiry = created + timedelta(seconds=expires_in)
    sidecar = target.with_suffix(".manifest.json")
    side_raw = json.dumps({"artifact_id": artifact_id, "expires_at": expiry.isoformat(), "hash": digest}, sort_keys=True).encode()
    side_fd, side_temp = tempfile.mkstemp(prefix=f".{artifact_id}.", suffix=".manifest.tmp", dir=root)
    try:
        with os.fdopen(side_fd, "wb") as handle:
            handle.write(side_raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(side_temp, sidecar)
    finally:
        if os.path.exists(side_temp):
            os.unlink(side_temp)
    return {"artifact_id": artifact_id, "snapshot_id": snapshot_id, "format": "json",
            "size": len(raw), "hash": {"algorithm": "sha256", "value": digest},
            "sample_counts": [
                {
                    "index": index,
                    "type": stream.get("type"),
                    "count": (
                        len(stream["data"])
                        if isinstance(stream.get("data"), list)
                        else None
                    ),
                    "data2_count": (
                        len(stream["data2"])
                        if isinstance(stream.get("data2"), list)
                        else None
                    ),
                }
                for index, stream in enumerate(payload.get("streams", []))
                if isinstance(stream, dict)
                and (
                    isinstance(stream.get("data"), list)
                    or isinstance(stream.get("data2"), list)
                )
            ],
            "range": payload.get("range"), "source": source,
            "created_at": created.isoformat(), "expires_at": expiry.isoformat(),
            "access": {"kind": "local_file", "path": str(target)}}


def artifact_is_expired(manifest: dict[str, Any]) -> bool:
    value = manifest.get("expires_at")
    return bool(value and datetime.fromisoformat(value) <= datetime.now(timezone.utc))


def cleanup_expired(root: Path | None = None) -> int:
    directory = root or artifact_dir()
    removed = 0
    for path in directory.glob("*.json"):
        if path.name.endswith(".manifest.json"):
            continue
        try:
            sidecar = path.with_suffix(".manifest.json")
            try:
                expiry = json.loads(sidecar.read_text(encoding="utf-8")).get("expires_at") if sidecar.exists() else None
            except (OSError, ValueError):
                expiry = None
            ttl_expired = datetime.fromisoformat(expiry) <= datetime.now(timezone.utc) if expiry else False
            if ttl_expired:
                path.unlink()
                if sidecar.exists():
                    sidecar.unlink()
                removed += 1
        except (FileNotFoundError, OSError):
            continue
    return removed
