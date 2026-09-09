import hashlib
import json
from intervals_mcp_server.artifacts import write_activity_artifact, cleanup_expired


def test_artifact_real_hash_duplicate_streams_and_expiry(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    payload = {
        "streams": [
            {"type": "x", "data": [1, None], "data2": [7]},
            {"type": "x", "data": [0]},
        ],
        "intervals": [],
    }
    manifest = write_activity_artifact(payload, snapshot_id="s", source="activity/a", expires_in=1)
    path = tmp_path / (manifest["artifact_id"] + ".json")
    raw = path.read_bytes()
    assert manifest["size"] == len(raw) and manifest["hash"]["value"] == hashlib.sha256(raw).hexdigest()
    assert len(manifest["sample_counts"]) == 2 and json.loads(raw) == payload
    assert manifest["sample_counts"][0]["data2_count"] == 1
    import time
    time.sleep(1.1)
    assert cleanup_expired(tmp_path) >= 1


def test_artifact_max_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALS_ARTIFACT_MAX_BYTES", "1")
    import pytest
    with pytest.raises(ValueError):
        write_activity_artifact({"streams": [], "intervals": []}, snapshot_id="s", source="a")


def test_artifact_max_files(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setenv("INTERVALS_ARTIFACT_MAX_FILES", "1")
    write_activity_artifact({"streams": [], "intervals": []}, snapshot_id="1", source="a")
    write_activity_artifact({"streams": [], "intervals": []}, snapshot_id="2", source="a")
    assert len(list(tmp_path.glob("*.manifest.json"))) <= 1


def test_artifact_corrupt_sidecar_safe(tmp_path):
    orphan = tmp_path / "orphan.manifest.json"
    orphan.write_text("not-json", encoding="utf-8")
    assert cleanup_expired(tmp_path) == 0


def test_artifact_sidecar_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERVALS_ARTIFACT_DIR", str(tmp_path))
    manifest = write_activity_artifact({"streams": [], "intervals": []}, snapshot_id="s", source="a")
    assert (tmp_path / f"{manifest['artifact_id']}.manifest.json").exists()
