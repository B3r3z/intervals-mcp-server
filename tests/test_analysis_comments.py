from copy import deepcopy
import json

import httpx
from mcp.server.fastmcp import FastMCP
import pytest
import pytest_asyncio

from intervals_mcp_server.api import client
from intervals_mcp_server.config import Config
from intervals_mcp_server.operations import AccountWriteLock
from intervals_mcp_server.tools import analysis_comments as comments


class Upstream:
    def __init__(self):
        self.messages = []
        self.calls = []
        self.mode = "ok"
        self.next_id = 100

    def request(self, request):
        self.calls.append((request.method, request.url.path))
        if request.url.path == "/activity/activity" and request.method == "GET":
            return httpx.Response(200, json={"id": "activity"})
        assert request.url.path == "/activity/activity/messages"
        if request.method == "GET":
            if self.mode == "invalid_preflight":
                return httpx.Response(200, json={"bad": "shape"})
            if self.mode == "missing_from_read" and self.posts:
                return httpx.Response(200, json=self.messages[:-1])
            if self.mode == "read_error" and self.posts:
                return httpx.Response(503, json={})
            return httpx.Response(200, json=self.messages)
        assert request.method == "POST"
        body = json.loads(request.content)
        assert set(body) == {"content"}
        if self.mode == "reject":
            return httpx.Response(403, json={})
        row = {"id": self.next_id, "activity_id": "activity", "content": body["content"], "athlete_id": "i123"}
        self.next_id += 1
        self.messages.append(row)
        if self.mode == "timeout":
            raise httpx.ReadTimeout("simulated lost acknowledgement")
        if self.mode == "no_id":
            return httpx.Response(200, json={})
        if self.mode == "bool_id":
            return httpx.Response(200, json={"id": True})
        if self.mode == "content_mismatch":
            row["content"] = "different stored content"
        if self.mode == "content_missing":
            del row["content"]
        if self.mode == "deleted":
            row["deleted"] = "2026-09-09T10:00:00Z"
        if self.mode == "wrong_activity":
            row["activity_id"] = "another-activity"
        if self.mode == "duplicate_id":
            self.messages.append(deepcopy(row))
        return httpx.Response(200, json={"id": row["id"]})

    @property
    def posts(self):
        return sum(method == "POST" for method, _ in self.calls)


@pytest_asyncio.fixture
async def upstream(monkeypatch, tmp_path):
    remote = Upstream()
    config = Config("fixture-key", "i123", "https://fixture", "test")
    monkeypatch.setenv("INTERVALS_OPERATION_DIR", str(tmp_path))
    monkeypatch.setattr(comments, "get_config", lambda: config)
    monkeypatch.setattr(client, "get_config", lambda: config)
    monkeypatch.setattr(client, "httpx_client", None)

    async def no_delay(_seconds):
        pass

    monkeypatch.setattr(client.asyncio, "sleep", no_delay)
    transport = httpx.AsyncClient(transport=httpx.MockTransport(remote.request))
    async with client.setup_api_client(FastMCP("comment-test"), client=transport):
        yield remote


@pytest.mark.asyncio
async def test_publish_verifies_id_then_replay_and_new_version(upstream):
    upstream.messages.append({"id": 5, "content": "analysis"})
    first = await comments.publish_analysis_comment("activity", "v1", "analysis")
    assert first.result.outcome == "confirmed"
    assert first.result.message_id == 100
    assert first.result.checked_fields == ["id", "activity_id", "content"]
    assert upstream.calls[-2:] == [("POST", "/activity/activity/messages"), ("GET", "/activity/activity/messages")]
    before = list(upstream.calls)
    replay = await comments.publish_analysis_comment("activity", "v1", "analysis")
    assert replay == first
    assert upstream.calls == before
    conflict = await comments.publish_analysis_comment("activity", "v1", "changed")
    target_conflict = await comments.publish_analysis_comment("different", "v1", "analysis")
    assert conflict.result.outcome == target_conflict.result.outcome == "conflict"
    assert upstream.calls == before
    second = await comments.publish_analysis_comment("activity", "v2", "revised analysis")
    assert second.result.outcome == "confirmed"
    assert upstream.posts == 2
    assert [row["content"] for row in upstream.messages] == ["analysis", "analysis", "revised analysis"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,outcome", [
    ("timeout", "unknown"), ("no_id", "unknown"), ("bool_id", "unknown"),
    ("missing_from_read", "unknown"), ("read_error", "unknown"),
    ("content_missing", "unknown"), ("content_mismatch", "mismatch"),
    ("wrong_activity", "mismatch"), ("deleted", "mismatch"),
    ("duplicate_id", "unknown"), ("reject", "unknown"),
])
async def test_uncertain_or_mismatched_publication_never_posts_again(upstream, mode, outcome):
    upstream.mode = mode
    first = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert first.result.outcome == outcome
    assert upstream.posts == 1
    replay = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert replay == first
    await comments.get_analysis_comment_status("version", reconcile=True)
    assert upstream.posts == 1
    assert {method for method, _ in upstream.calls} <= {"GET", "POST"}


@pytest.mark.asyncio
async def test_known_id_reconciliation_and_manual_edit_preserve_history(upstream):
    upstream.mode = "missing_from_read"
    first = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert first.result.outcome == "unknown" and first.result.message_id == 100
    upstream.mode = "ok"
    reconciled = await comments.get_analysis_comment_status("version", reconcile=True)
    assert reconciled.historical_result.outcome == "unknown"
    assert reconciled.reconciliation_result.outcome == "confirmed"
    upstream.messages[0]["content"] = "manual edit"
    edited = await comments.get_analysis_comment_status("version", reconcile=True)
    assert edited.historical_result.outcome == "confirmed"
    assert edited.reconciliation_result.outcome == "mismatch"
    upstream.mode = "missing_from_read"
    missing = await comments.get_analysis_comment_status("version", reconcile=True)
    assert missing.historical_result.outcome == "confirmed"
    assert missing.historical_result.checked_fields == ["id", "activity_id", "content"]
    assert missing.reconciliation_result.outcome == "unknown"
    assert missing.reconciliation_result.checked_fields == []
    assert (await comments.publish_analysis_comment("activity", "version", "analysis")).result.outcome == "confirmed"
    assert upstream.posts == 1


@pytest.mark.asyncio
async def test_lost_id_cannot_be_recovered_by_matching_text(upstream):
    upstream.mode = "timeout"
    await comments.publish_analysis_comment("activity", "version", "analysis")
    upstream.mode = "ok"
    before = list(upstream.calls)
    status = await comments.get_analysis_comment_status("version", reconcile=True)
    assert status.reconciliation_result.outcome == "unknown"
    assert status.reconciliation_result.code == "MESSAGE_ID_UNAVAILABLE"
    assert upstream.calls == before


@pytest.mark.asyncio
async def test_preflight_lock_and_validation_prevent_publication(upstream):
    for uid, content in [("", "analysis"), ("trim ", "analysis"), ("v1", " ")]:
        assert (await comments.publish_analysis_comment("activity", uid, content)).result.outcome == "rejected"
    assert upstream.calls == []
    with AccountWriteLock("i123"):
        assert (await comments.publish_analysis_comment("activity", "locked", "analysis")).result.code == "WRITE_LOCKED"
    assert upstream.calls == []
    upstream.mode = "invalid_preflight"
    assert (await comments.publish_analysis_comment("activity", "version", "analysis")).result.code == "MESSAGES_PREFLIGHT_FAILED"
    assert upstream.posts == 0


@pytest.mark.asyncio
async def test_durable_record_failure_before_or_after_post_prevents_retry(upstream, monkeypatch):
    original = comments._CommentJournal.save

    def fail_first_save(self, intent, result):
        raise OSError("synthetic unavailable journal")

    monkeypatch.setattr(comments._CommentJournal, "save", fail_first_save)
    rejected = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert rejected.result.outcome == "rejected"
    assert upstream.calls == []

    def fail_ack_save(self, intent, result):
        if result.message_id is not None:
            raise OSError("synthetic persistence failure after POST")
        return original(self, intent, result)

    monkeypatch.setattr(comments._CommentJournal, "save", fail_ack_save)
    uncertain = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert uncertain.result.outcome == "unknown" and upstream.posts == 1
    monkeypatch.setattr(comments._CommentJournal, "save", original)
    replay = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert replay.result.outcome == "unknown" and replay.result.message_id is None
    assert upstream.posts == 1


@pytest.mark.asyncio
async def test_corrupt_and_interrupted_records_never_authorize_a_post(upstream, tmp_path):
    first = await comments.publish_analysis_comment("activity", "version", "analysis")
    before = list(upstream.calls)
    record_path = next((tmp_path / "analysis-comments").glob("*.json"))
    original = record_path.read_text()
    record_path.write_text("{")
    corrupt = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert corrupt.result.code == "JOURNAL_CORRUPT"
    assert upstream.calls == before
    record = json.loads(original)
    record["result"].update(outcome="in_flight", code="IN_FLIGHT", completed_at=None)
    record_path.write_text(json.dumps(record))
    interrupted = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert interrupted.result.outcome == "unknown"
    assert interrupted.result.message_id == first.result.message_id
    assert upstream.calls == before


@pytest.mark.asyncio
async def test_cancellation_during_post_leaves_durable_replay_guard(upstream, monkeypatch):
    class Crash(BaseException):
        pass

    original = comments.make_intervals_request

    async def crash(**kwargs):
        if kwargs.get("method") == "POST":
            raise Crash()
        return await original(**kwargs)

    monkeypatch.setattr(comments, "make_intervals_request", crash)
    with pytest.raises(Crash):
        await comments.publish_analysis_comment("activity", "version", "analysis")
    monkeypatch.setattr(comments, "make_intervals_request", original)
    replay = await comments.publish_analysis_comment("activity", "version", "analysis")
    assert replay.result.outcome == "unknown"
    assert replay.result.sent_at is not None
    assert upstream.posts == 0
