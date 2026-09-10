"""Small blind-agent bridge for the deterministic V1 MCP evaluation.

The bridge talks to a real stdio ``ClientSession``.  Its output files contain
only the MCP result or tool catalogue; fixture request logs and byte/cost
audits remain under the explicitly supplied private state directory.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Sequence

from tests.v1_protocol_support import (
    append_private_audit,
    call_and_record,
    canonical_json_bytes,
    open_session,
)


def _json_value(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True, exclude_none=False)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--state-dir",
        type=Path,
        required=True,
        help="Private persistent server state, request logs, and audit directory.",
    )
    parser.add_argument(
        "--case",
        default=None,
        help="Optional private audit label for a deterministic evaluation case.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List the public MCP tools.")
    list_parser.add_argument("--output", type=Path, required=True)

    call_parser = subparsers.add_parser("call", help="Call one public MCP tool.")
    call_parser.add_argument("name")
    call_parser.add_argument("--args-file", type=Path, required=True)
    call_parser.add_argument("--output", type=Path, required=True)
    return parser


async def _list_tools(
    state_dir: Path, case: str | None, output: Path, repo_root: Path
) -> None:
    request_log = state_dir / "request-log.jsonl"
    async with open_session(
        repo_root=repo_root,
        state_dir=state_dir,
        request_log=request_log,
    ) as (_session, tools, _errlog):
        catalogue = {
            "tools": [
                _dump(tool)
                for tool in sorted(tools.values(), key=lambda item: item.name)
            ]
        }
    _write_json(output, catalogue)
    append_private_audit(
        state_dir,
        case=case,
        tool="tools/list",
        arguments={},
        text_bytes=canonical_json_bytes(catalogue),
        result_bytes=canonical_json_bytes(catalogue),
        request_delta=0,
        started_at=datetime.now(timezone.utc).isoformat(),
        finished_at=datetime.now(timezone.utc).isoformat(),
    )


async def _call_tool(
    state_dir: Path,
    case: str | None,
    name: str,
    arguments_path: Path,
    output: Path,
    repo_root: Path,
) -> None:
    arguments = _json_value(arguments_path)
    if not isinstance(arguments, dict):
        raise SystemExit("--args-file must contain a JSON object")
    request_log = state_dir / "request-log.jsonl"
    async with open_session(
        repo_root=repo_root,
        state_dir=state_dir,
        request_log=request_log,
    ) as (session, tools, _errlog):
        result, record = await call_and_record(
            session,
            tools,
            request_log,
            name,
            arguments,
        )
    _write_json(output, _dump(result))
    append_private_audit(
        state_dir,
        case=case,
        tool=name,
        arguments=arguments,
        text_bytes=int(record["utf8_json_text_bytes"]),
        result_bytes=int(record["utf8_call_tool_result_bytes"]),
        request_delta=int(record["http_attempts"]),
        started_at=record.get("started_at", datetime.now(timezone.utc).isoformat()),
        finished_at=record.get("finished_at", datetime.now(timezone.utc).isoformat()),
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    state_dir = args.state_dir.resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "list":
        asyncio.run(_list_tools(state_dir, args.case, args.output.resolve(), repo_root))
    else:
        asyncio.run(
            _call_tool(
                state_dir,
                args.case,
                args.name,
                args.args_file.resolve(),
                args.output.resolve(),
                repo_root,
            )
        )


if __name__ == "__main__":
    main()
