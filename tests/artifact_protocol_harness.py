"""Synthetic MCP stdio proof for byte-exact activity artifact retrieval.

Run from the repository root with::

    uv run python -m tests.artifact_protocol_harness --output <path>

The client reconstructs the artifact only from MCP base64 chunks. It never
opens the server-side artifact path.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, TextIO, cast

from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _request_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _text_json(result: Any) -> tuple[dict[str, Any] | None, int]:
    blocks = [block for block in result.content if getattr(block, "type", None) == "text"]
    if len(blocks) != 1:
        return None, 0
    raw = blocks[0].text
    return json.loads(raw), len(raw.encode("utf-8"))


def _call_tool_result_bytes(result: Any) -> int:
    value = result.model_dump(mode="json", by_alias=True, exclude_none=False)
    return len(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _schema_errors(schema: Any, structured: Any) -> list[str]:
    if not isinstance(schema, dict):
        return ["outputSchema is absent"]
    if structured is None:
        return ["structuredContent is absent"]
    return [
        error.message
        for error in Draft202012Validator(schema).iter_errors(structured)
    ]


async def capture_artifact_report() -> dict[str, Any]:
    """Export and reconstruct a multibyte activity through public MCP tools."""
    with tempfile.TemporaryDirectory(prefix="intervals-artifact-protocol-") as temp_dir:
        temp_path = Path(temp_dir)
        request_log = temp_path / "requests.jsonl"
        artifact_root = temp_path / "artifacts"
        errlog = cast(TextIO, tempfile.TemporaryFile(mode="w+", encoding="utf-8"))
        env = dict(os.environ)
        env.update(
            {
                "API_KEY": "synthetic-artifact-key",
                "ATHLETE_ID": "i123",
                "INTERVALS_ACCESS_MODE": "readonly",
                "INTERVALS_API_BASE_URL": "https://synthetic.invalid/api/v1",
                "INTERVALS_ARTIFACT_DIR": str(artifact_root),
                "PYTHON_DOTENV_DISABLED": "1",
                "READ_FIXTURE_REQUEST_LOG": str(request_log),
            }
        )
        env["PYTHONPATH"] = os.path.abspath("src") + os.pathsep + os.path.abspath(".")
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "tests.stdio_read_fixture_server"],
            env=env,
        )
        calls: list[dict[str, Any]] = []
        reconstructed = bytearray()
        chunk_hashes_valid = True
        artifact_hashes: set[str] = set()
        chunk_metadata_has_path = False
        chunk_count = 0
        offset = 0
        async with stdio_client(params, errlog=errlog) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                tool_by_name = {tool.name: tool for tool in listed.tools}

                export_result = await session.call_tool(
                    "export_activity_data", {"activity_id": "a-artifact"}
                )
                export_structured = export_result.structuredContent
                if not isinstance(export_structured, dict):
                    raise AssertionError("export structured content is absent")
                export_text, export_text_bytes = _text_json(export_result)
                export_errors = _schema_errors(
                    tool_by_name["export_activity_data"].outputSchema,
                    export_structured,
                )
                calls.append(
                    {
                        "tool": "export_activity_data",
                        "mcp_is_error": export_result.isError is True,
                        "domain_status": export_structured.get("status"),
                        "output_schema_valid": not export_errors,
                        "structured_text_agree": export_text == export_structured,
                        "utf8_json_text_bytes": export_text_bytes,
                        "utf8_call_tool_result_bytes": _call_tool_result_bytes(
                            export_result
                        ),
                    }
                )
                manifest = export_structured["data"]
                artifact_id = manifest["artifact_id"]

                while True:
                    result = await session.call_tool(
                        "get_artifact_chunk",
                        {
                            "artifact_id": artifact_id,
                            "offset": offset,
                            "max_bytes": 256,
                        },
                    )
                    structured = result.structuredContent
                    if not isinstance(structured, dict):
                        raise AssertionError("chunk structured content is absent")
                    text_value, text_bytes = _text_json(result)
                    errors = _schema_errors(
                        tool_by_name["get_artifact_chunk"].outputSchema,
                        structured,
                    )
                    data = structured["data"]
                    chunk = base64.b64decode(data["chunk_base64"], validate=True)
                    reconstructed.extend(chunk)
                    chunk_count += 1
                    chunk_hashes_valid = chunk_hashes_valid and (
                        len(chunk) == data["returned_bytes"]
                        and hashlib.sha256(chunk).hexdigest()
                        == data["chunk_hash"]["value"]
                    )
                    artifact_hashes.add(data["artifact_hash"]["value"])
                    chunk_metadata_has_path = chunk_metadata_has_path or (
                        "path" in json.dumps(data)
                    )
                    calls.append(
                        {
                            "tool": "get_artifact_chunk",
                            "mcp_is_error": result.isError is True,
                            "domain_status": structured.get("status"),
                            "source_system": structured.get("source", {}).get("system"),
                            "response_complete": structured.get("coverage", {}).get(
                                "response_complete"
                            ),
                            "output_schema_valid": not errors,
                            "structured_text_agree": text_value == structured,
                            "utf8_json_text_bytes": text_bytes,
                            "utf8_call_tool_result_bytes": _call_tool_result_bytes(result),
                        }
                    )
                    if data["eof"]:
                        break
                    if data["next_offset"] <= offset:
                        raise AssertionError("artifact chunk cursor did not advance")
                    offset = data["next_offset"]

                invalid_result = await session.call_tool(
                    "get_artifact_chunk",
                    {"artifact_id": "../00000000000000000000000000000"},
                )
                invalid_structured = invalid_result.structuredContent
                if not isinstance(invalid_structured, dict):
                    raise AssertionError("error structured content is absent")
                invalid_text, invalid_text_bytes = _text_json(invalid_result)
                invalid_errors = _schema_errors(
                    tool_by_name["get_artifact_chunk"].outputSchema,
                    invalid_structured,
                )
                calls.append(
                    {
                        "tool": "get_artifact_chunk",
                        "mcp_is_error": invalid_result.isError is True,
                        "domain_status": invalid_structured.get("status"),
                        "domain_error_code": invalid_structured.get("error", {}).get(
                            "code"
                        ),
                        "source_system": invalid_structured.get("source", {}).get(
                            "system"
                        ),
                        "response_complete": invalid_structured.get(
                            "coverage", {}
                        ).get("response_complete"),
                        "output_schema_valid": not invalid_errors,
                        "structured_text_agree": invalid_text == invalid_structured,
                        "utf8_json_text_bytes": invalid_text_bytes,
                        "utf8_call_tool_result_bytes": _call_tool_result_bytes(
                            invalid_result
                        ),
                    }
                )

        errlog.seek(0)
        stderr = errlog.read()
        if "synthetic-artifact-key" in stderr:
            raise AssertionError("synthetic API key leaked to MCP stderr")
        decoded = json.loads(reconstructed.decode("utf-8"))
        requests = _request_rows(request_log)
        reconstructed_hash = hashlib.sha256(reconstructed).hexdigest()
        return {
            "protocol": "MCP ClientSession over stdio",
            "upstream": "httpx.MockTransport synthetic fixtures; all other requests blocked",
            "proof_boundary": (
                "Artifact reconstructed only from MCP base64 chunks; JSON-RPC framing "
                "excluded from byte counts."
            ),
            "mcp_calls": len(calls),
            "upstream_requests": len(requests),
            "upstream_request_log": requests,
            "artifact_bytes": len(reconstructed),
            "utf8_json_text_bytes": sum(
                call["utf8_json_text_bytes"] for call in calls
            ),
            "utf8_call_tool_result_bytes": sum(
                call["utf8_call_tool_result_bytes"] for call in calls
            ),
            "artifact_chunks": chunk_count,
            "artifact_sha256": reconstructed_hash,
            "export_manifest_hash_matches": (
                manifest["hash"]["value"] == reconstructed_hash
            ),
            "all_chunk_artifact_hashes_match": artifact_hashes == {reconstructed_hash},
            "all_chunk_hashes_match": chunk_hashes_valid,
            "multibyte_json_reconstructed": (
                decoded["streams"][3]["type"] == "oddech-żółć-🚴"
                and decoded["intervals"]["icu_intervals"][0]["name"]
                == "Próba syntetyczna 🚴"
            ),
            "duplicates_data2_null_zero_and_custom_preserved": (
                [row["type"] for row in decoded["streams"]].count("watts") == 2
                and decoded["streams"][1]["data"] == [0, 245, None, 247, 0, 251]
                and decoded["streams"][2]["data2"] == [0, 243, None, 245, 0, 249]
                and "data" not in decoded["streams"][2]
                and decoded["streams"][3]["custom"]
                == {"label": "wielobajtowy ślad"}
            ),
            "chunk_metadata_has_path": chunk_metadata_has_path,
            "invalid_artifact_id_is_domain_error": (
                calls[-1]["mcp_is_error"] is False
                and calls[-1]["domain_status"] == "error"
                and calls[-1]["domain_error_code"] == "INVALID_ARTIFACT_ID"
            ),
            "calls": calls,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = asyncio.run(capture_artifact_report())
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
