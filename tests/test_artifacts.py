import asyncio
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from intervals_mcp_server.artifacts import (
    ArtifactStoreError,
    cleanup_expired,
    read_artifact_chunk,
    write_activity_artifact,
)
from intervals_mcp_server.tools.activities import export_activity_data, get_activity_streams
from intervals_mcp_server.tools.artifacts import get_artifact_chunk


def _snapshot(payload: dict[str, Any]) -> str:
    raw = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_artifact(
    payload: dict[str, Any], *, source: str = "a", **kwargs: Any
) -> dict[str, Any]:
    return write_activity_artifact(
        payload, snapshot_id=_snapshot(payload), source=source, **kwargs
    )


def test_artifact_real_hash_duplicate_streams_and_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALS_ARTIFACT_TTL_SECONDS", "3600")
    created_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    payload = {
        "streams": [
            {"type": "x", "data": [1, None], "data2": [7]},
            {"type": "x", "data": [0]},
        ],
        "intervals": [],
    }
    manifest = _write_artifact(
        payload,
        source="activity/a",
        expires_in=1,
        now=lambda: created_at,
    )
    path = tmp_path / (manifest["artifact_id"] + ".json")
    raw = path.read_bytes()
    assert manifest["size"] == len(raw)
    assert manifest["hash"]["value"] == hashlib.sha256(raw).hexdigest()
    assert len(manifest["sample_counts"]) == 2 and json.loads(raw) == payload
    assert manifest["sample_counts"][0]["data2_count"] == 1
    assert manifest["expires_at"] == (created_at + timedelta(seconds=1)).isoformat()
    assert cleanup_expired(tmp_path, now=lambda: created_at + timedelta(seconds=2)) == 1


def test_artifact_chunks_reconstruct_exact_utf8_json(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    created_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    payload = {
        "activity_id": "a-multibyte",
        "streams": [
            {"type": "custom", "data": [0, None, "zażółć 🚴"], "data2": [7]},
            {"type": "custom", "data": []},
        ],
        "intervals": {"icu_intervals": []},
    }
    manifest = _write_artifact(
        payload,
        source="activity/a-multibyte",
        now=lambda: created_at,
    )

    reconstructed = bytearray()
    offset = 0
    chunks = 0
    while True:
        chunk = read_artifact_chunk(
            manifest["artifact_id"],
            offset=offset,
            max_bytes=17,
            now=lambda: created_at,
        )
        reconstructed.extend(base64.b64decode(chunk["chunk_base64"], validate=True))
        chunks += 1
        if chunk["eof"]:
            break
        offset = chunk["next_offset"]

    assert chunks >= 2
    assert hashlib.sha256(reconstructed).hexdigest() == manifest["hash"]["value"]
    assert json.loads(reconstructed.decode("utf-8")) == payload


def test_artifact_max_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALS_ARTIFACT_MAX_BYTES", "1")
    with pytest.raises(ValueError):
        _write_artifact({"streams": [], "intervals": []})


def test_artifact_max_files(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALS_ARTIFACT_MAX_FILES", "2")
    created_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    first = _write_artifact(
        {"streams": [], "intervals": []},
        now=lambda: created_at,
    )
    second = _write_artifact(
        {"streams": [{"type": "x", "data": [2]}], "intervals": []},
        now=lambda: created_at + timedelta(seconds=1),
    )
    third = _write_artifact(
        {"streams": [{"type": "x", "data": [3]}], "intervals": []},
        now=lambda: created_at + timedelta(seconds=2),
    )
    assert not (tmp_path / f"{first['artifact_id']}.json").exists()
    assert (tmp_path / f"{second['artifact_id']}.json").exists()
    assert (tmp_path / f"{third['artifact_id']}.json").exists()
    assert len(list(tmp_path.glob("*.manifest.json"))) == 2


def test_artifact_corrupt_sidecar_safe(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    orphan = tmp_path / "orphan.manifest.json"
    orphan.write_text("not-json", encoding="utf-8")
    unrelated = tmp_path / "coaching-notes.json"
    unrelated.write_text('{"keep":true}', encoding="utf-8")
    suspicious_id = "0" * 32
    suspicious = tmp_path / f"{suspicious_id}.json"
    suspicious.write_text("{}", encoding="utf-8")
    assert cleanup_expired(tmp_path) == 0
    assert orphan.exists()
    assert unrelated.exists()
    assert suspicious.exists()


def test_cleanup_never_uses_an_unconfigured_directory(tmp_path, monkeypatch):
    configured = tmp_path / "configured"
    outside = tmp_path / "outside"
    outside.mkdir()
    unrelated = outside / ("2" * 32 + ".json")
    unrelated.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(configured))

    assert cleanup_expired(outside) == 0
    assert unrelated.exists()


def test_artifact_sidecar_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact({"streams": [], "intervals": []})
    assert (tmp_path / f"{manifest['artifact_id']}.manifest.json").exists()
    assert manifest["client_access"]["tool"] == "get_artifact_chunk"
    assert manifest["provenance"]["upstream_atomic_snapshot"] is False


def test_failed_export_does_not_clean_existing_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    created_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    existing = _write_artifact(
        {"streams": [], "intervals": []},
        expires_in=1,
        now=lambda: created_at,
    )
    payload_path = tmp_path / f"{existing['artifact_id']}.json"
    sidecar_path = tmp_path / f"{existing['artifact_id']}.manifest.json"
    monkeypatch.setenv("INTERVALS_ARTIFACT_MAX_BYTES", "1")

    with pytest.raises(ValueError):
        _write_artifact(
            {"streams": [{"type": "large", "data": [1]}], "intervals": []},
            now=lambda: created_at + timedelta(seconds=2),
        )

    assert payload_path.exists()
    assert sidecar_path.exists()

    monkeypatch.delenv("INTERVALS_ARTIFACT_MAX_BYTES")
    with pytest.raises(ValueError):
        write_activity_artifact(
            {"streams": [{"type": "invalid", "data": [float("nan")]}]},
            snapshot_id="0" * 64,
            source="a",
            now=lambda: created_at + timedelta(seconds=2),
        )
    assert payload_path.exists()
    assert sidecar_path.exists()


def test_artifact_chunk_tool_has_local_source_bounds_and_eof(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact(
        {"streams": [{"type": "x", "data": [0, None]}], "intervals": []},
        source="activity/a",
    )

    first = asyncio.run(
        get_artifact_chunk(manifest["artifact_id"], offset=0, max_bytes=5)
    )
    assert first.status == "partial"
    assert first.source.system == "intervals-mcp-server"
    assert first.coverage.response_complete is True
    assert first.coverage.truncated is True
    assert first.data["returned_bytes"] == 5
    assert first.data["next_offset"] == 5
    assert "path" not in json.dumps(first.data)

    eof = asyncio.run(
        get_artifact_chunk(
            manifest["artifact_id"], offset=manifest["size"], max_bytes=5
        )
    )
    assert eof.status == "ok"
    assert eof.data["eof"] is True
    assert eof.data["returned_bytes"] == 0
    assert base64.b64decode(eof.data["chunk_base64"], validate=True) == b""

    too_far = asyncio.run(
        get_artifact_chunk(
            manifest["artifact_id"], offset=manifest["size"] + 1, max_bytes=5
        )
    )
    assert too_far.status == "error"
    assert too_far.error is not None
    assert too_far.error.code == "INVALID_CHUNK_RANGE"
    assert too_far.source.system == "intervals-mcp-server"


@pytest.mark.parametrize(
    ("artifact_id", "offset", "max_bytes", "code"),
    [
        ("A" * 32, 0, 1, "INVALID_ARTIFACT_ID"),
        ("../" + "0" * 29, 0, 1, "INVALID_ARTIFACT_ID"),
        (r"C:\artifact\payload.json", 0, 1, "INVALID_ARTIFACT_ID"),
        ("0" * 31 + "/", 0, 1, "INVALID_ARTIFACT_ID"),
        ("0" * 32, -1, 1, "INVALID_CHUNK_RANGE"),
        ("0" * 32, 0, 0, "INVALID_CHUNK_RANGE"),
        ("0" * 32, 0, 32_769, "INVALID_CHUNK_RANGE"),
    ],
)
def test_artifact_chunk_domain_errors(
    artifact_id: str, offset: int, max_bytes: int, code: str
) -> None:
    result = asyncio.run(
        get_artifact_chunk(artifact_id, offset=offset, max_bytes=max_bytes)
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == code


def test_expired_artifact_is_rejected_without_returning_a_chunk(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    created_at = datetime(2000, 1, 1, 12, tzinfo=UTC)
    manifest = _write_artifact(
        {"streams": [], "intervals": []},
        expires_in=1,
        now=lambda: created_at,
    )

    with pytest.raises(ArtifactStoreError) as caught:
        read_artifact_chunk(
            manifest["artifact_id"],
            now=lambda: created_at + timedelta(seconds=1),
        )
    assert caught.value.code == "ARTIFACT_EXPIRED"
    response = asyncio.run(get_artifact_chunk(manifest["artifact_id"]))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ARTIFACT_EXPIRED"
    assert response.data == []


def test_artifact_tamper_is_rejected_before_any_chunk(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact(
        {"streams": [{"type": "x", "data": [1]}], "intervals": []},
    )
    payload_path = tmp_path / f"{manifest['artifact_id']}.json"
    tampered = bytearray(payload_path.read_bytes())
    tampered[-2] = ord("1") if tampered[-2] != ord("1") else ord("2")
    payload_path.write_bytes(tampered)

    with pytest.raises(ArtifactStoreError) as caught:
        read_artifact_chunk(manifest["artifact_id"])
    assert caught.value.code == "ARTIFACT_INTEGRITY_MISMATCH"
    response = asyncio.run(get_artifact_chunk(manifest["artifact_id"]))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ARTIFACT_INTEGRITY_MISMATCH"
    assert response.data == []


def test_old_or_malformed_manifest_requires_reexport(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    artifact_id = "1" * 32
    (tmp_path / f"{artifact_id}.json").write_text("{}", encoding="utf-8")
    (tmp_path / f"{artifact_id}.manifest.json").write_text(
        json.dumps(
            {
                "artifact_id": artifact_id,
                "expires_at": "2099-01-01T00:00:00+00:00",
                "hash": hashlib.sha256(b"{}").hexdigest(),
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ArtifactStoreError) as caught:
        read_artifact_chunk(artifact_id)
    assert caught.value.code == "ARTIFACT_MANIFEST_INVALID"
    response = asyncio.run(get_artifact_chunk(artifact_id))
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "ARTIFACT_MANIFEST_INVALID"


@pytest.mark.parametrize("corruption", ["boolean-version", "deep-json"])
def test_manifest_corruption_is_normalized(
    tmp_path, monkeypatch, corruption: str
) -> None:
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact({"streams": [], "intervals": []})
    sidecar = tmp_path / f"{manifest['artifact_id']}.manifest.json"
    if corruption == "boolean-version":
        metadata = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata["manifest_version"] = True
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
    else:
        sidecar.write_text("[" * 1_500 + "0" + "]" * 1_500, encoding="utf-8")

    with pytest.raises(ArtifactStoreError) as caught:
        read_artifact_chunk(manifest["artifact_id"])
    assert caught.value.code == "ARTIFACT_MANIFEST_INVALID"


def test_manifest_path_is_ignored_and_not_returned(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact({"streams": [], "intervals": []})
    sidecar = tmp_path / f"{manifest['artifact_id']}.manifest.json"
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    metadata["path"] = str(tmp_path.parent / "outside.json")
    sidecar.write_text(json.dumps(metadata), encoding="utf-8")

    chunk = read_artifact_chunk(manifest["artifact_id"], max_bytes=1)
    assert chunk["returned_bytes"] == 1
    assert "path" not in chunk


def test_payload_symlink_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = _write_artifact({"streams": [], "intervals": []})
    payload_path = tmp_path / f"{manifest['artifact_id']}.json"
    outside = tmp_path.parent / f"outside-{manifest['artifact_id']}.json"
    outside.write_bytes(payload_path.read_bytes())
    payload_path.unlink()
    try:
        os.symlink(outside, payload_path)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")

    with pytest.raises(ArtifactStoreError) as caught:
        read_artifact_chunk(manifest["artifact_id"])
    assert caught.value.code == "ARTIFACT_PATH_UNSAFE"


def test_stream_range_cap_rejects_before_upstream_request(monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_request(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return []

    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request", fake_request
    )
    result = asyncio.run(
        get_activity_streams(
            "activity",
            mode="range",
            start_index=0,
            end_index=10_001,
        )
    )
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "RANGE_TOO_LARGE"
    assert "get_artifact_chunk" in (result.error.recommended_action or "")
    assert calls == []


def test_export_serialization_failure_is_structured_and_publishes_nothing(
    tmp_path, monkeypatch
) -> None:
    calls = 0

    async def malformed_unicode(**_kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{"type": "custom", "data": ["\ud800"]}]
        return {"icu_intervals": []}

    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request",
        malformed_unicode,
    )
    result = asyncio.run(export_activity_data("activity"))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "ARTIFACT_WRITE_FAILED"
    assert list(tmp_path.iterdir()) == []


def test_export_and_chunks_preserve_nullable_interval_groups(
    tmp_path, monkeypatch
) -> None:
    interval_payload = {
        "id": "activity",
        "analyzed": "2026-09-09T20:00:00Z",
        "icu_intervals": [{"id": 1, "start_index": 0, "end_index": 2}],
        "icu_groups": None,
    }

    async def live_shape(**kwargs: Any) -> Any:
        if kwargs["url"].endswith("/streams"):
            return [{"type": "time", "data": [0, 1]}]
        return interval_payload

    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(
        "intervals_mcp_server.tools.activities.make_intervals_request",
        live_shape,
    )

    exported = asyncio.run(export_activity_data("activity"))

    assert exported.status == "ok"
    assert exported.error is None
    manifest = exported.data
    reconstructed = bytearray()
    offset = 0
    chunk_count = 0
    while True:
        response = asyncio.run(
            get_artifact_chunk(manifest["artifact_id"], offset=offset, max_bytes=17)
        )
        assert response.error is None
        chunk = response.data
        reconstructed.extend(base64.b64decode(chunk["chunk_base64"], validate=True))
        chunk_count += 1
        if chunk["eof"]:
            break
        offset = chunk["next_offset"]

    assert chunk_count >= 2
    assert len(reconstructed) == manifest["size"]
    assert hashlib.sha256(reconstructed).hexdigest() == manifest["hash"]["value"]
    decoded = json.loads(reconstructed.decode("utf-8"))
    assert decoded["intervals"] == interval_payload
    assert decoded["intervals"]["icu_groups"] is None


def test_artifact_store_unavailable_is_a_structured_public_error(monkeypatch):
    def unavailable() -> Any:
        raise PermissionError("sensitive configured path")

    monkeypatch.setattr("intervals_mcp_server.artifacts.artifact_dir", unavailable)
    result = asyncio.run(get_artifact_chunk("0" * 32))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "ARTIFACT_READ_FAILED"
    assert "sensitive" not in result.as_text()


def test_missing_artifact_is_a_structured_public_error(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    result = asyncio.run(get_artifact_chunk("0" * 32))
    assert result.status == "error"
    assert result.error is not None
    assert result.error.code == "ARTIFACT_NOT_FOUND"
    assert result.data == []
