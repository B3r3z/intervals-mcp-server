"""Check the Intervals.icu OpenAPI surface used by this MCP server.

The pinned fixture is deliberately a projection, not a vendored copy of the
complete upstream document.  This checker never writes either the source spec
or the fixture.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import difflib
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPOSITORY_ROOT / "tests" / "contracts" / "intervals-openapi-used-surface.json"

SELECTED_OPERATIONS: tuple[tuple[str, str, str], ...] = (
    ("GET", "/api/v1/activity/{id}", "getActivity"),
    ("GET", "/api/v1/activity/{id}/intervals", "getIntervals"),
    ("GET", "/api/v1/activity/{id}/interval-stats", "getIntervalStats"),
    ("GET", "/api/v1/activity/{id}/best-efforts", "findBestEfforts"),
    ("GET", "/api/v1/activity/{id}/messages", "listActivityMessages"),
    ("POST", "/api/v1/activity/{id}/messages", "sendActivityMessage"),
    ("GET", "/api/v1/activity/{id}/streams{ext}", "getActivityStreams"),
    ("GET", "/api/v1/activity/{id}/power-curves{ext}", "listActivityPowerCurves_1"),
    ("GET", "/api/v1/athlete/{id}/activities", "listActivities"),
    ("GET", "/api/v1/athlete/{id}/events{format}", "listEvents"),
    ("POST", "/api/v1/athlete/{id}/events", "createEvent"),
    ("GET", "/api/v1/athlete/{id}/events/{eventId}", "showEvent"),
    ("PUT", "/api/v1/athlete/{id}/events/{eventId}", "updateEvent"),
    ("DELETE", "/api/v1/athlete/{id}/events/{eventId}", "deleteEvent"),
    ("GET", "/api/v1/athlete/{id}/wellness{ext}", "listWellnessRecords"),
    ("GET", "/api/v1/athlete/{id}/power-curves{ext}", "listAthletePowerCurves"),
    ("GET", "/api/v1/athlete/{athleteId}/sport-settings/{id}", "getSettings_1"),
    ("GET", "/api/v1/athlete/{id}/custom-item", "listCustomItems"),
    ("POST", "/api/v1/athlete/{id}/custom-item", "createCustomItem"),
    ("GET", "/api/v1/athlete/{id}/custom-item/{itemId}", "getCustomItem"),
    ("PUT", "/api/v1/athlete/{id}/custom-item/{itemId}", "updateCustomItem"),
    ("DELETE", "/api/v1/athlete/{id}/custom-item/{itemId}", "deleteCustomItem"),
)

REQUEST_SCHEMAS: tuple[str, ...] = ("CustomItem", "EventEx", "NewActivityMsg")
RESPONSE_SCHEMAS: tuple[str, ...] = ("Message", "NewMsg")
SECURITY_SCHEMES: tuple[str, ...] = ("APIKey", "AccessToken")

EXCEPTIONS: tuple[dict[str, Any], ...] = (
    {
        "id": "blank-json-suffix",
        "scope": {
            "operations": [
                "GET /api/v1/activity/{id}/streams{ext}",
                "GET /api/v1/activity/{id}/power-curves{ext}",
                "GET /api/v1/athlete/{id}/events{format}",
                "GET /api/v1/athlete/{id}/power-curves{ext}",
                "GET /api/v1/athlete/{id}/wellness{ext}",
            ],
            "parameters": ["ext", "format"],
        },
        "rationale": (
            "The server requests JSON by using a blank ext/format suffix; this is also the "
            "shape used by reviewed Intervals examples."
        ),
    },
    {
        "id": "power-curves-generated-filter-requirements",
        "scope": {
            "operations": ["GET /api/v1/athlete/{id}/power-curves{ext}"],
            "parameters": ["f1", "f2", "f3"],
        },
        "rationale": (
            "The generated contract marks f1/f2/f3 as required, but the current implementation "
            "and reviewed Intervals examples omit them. The required type query parameter is not "
            "exempt."
        ),
    },
    {
        "id": "root-security-and-vs-api-key",
        "scope": {
            "root_security": [{"APIKey": [], "AccessToken": []}],
            "selected_server_scheme": "APIKey",
        },
        "rationale": (
            "The root OpenAPI security object combines APIKey and AccessToken, while this personal "
            "server intentionally authenticates with the documented Basic APIKey scheme."
        ),
    },
)


class ProjectionError(ValueError):
    """Raised when the selected OpenAPI surface cannot be projected."""


def _as_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectionError(f"{context} must be an object")
    return value


def _resolve_local_ref(document: dict[str, Any], value: Any, context: str) -> dict[str, Any]:
    obj = _as_object(value, context)
    reference = obj.get("$ref")
    if reference is None:
        return obj
    if not isinstance(reference, str) or not reference.startswith("#/"):
        raise ProjectionError(f"{context} uses unsupported reference {reference!r}")

    current: Any = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ProjectionError(f"{context} has unresolved reference {reference}")
        current = current[part]
    return _as_object(current, context)


def _schema_descriptor(document: dict[str, Any], value: Any, context: str) -> dict[str, Any]:
    schema = _resolve_local_ref(document, value, context)
    descriptor: dict[str, Any] = {}
    for key in ("type", "format", "default"):
        if key in schema:
            descriptor[key] = schema[key]
    items = schema.get("items")
    if isinstance(items, dict):
        item_schema = _resolve_local_ref(document, items, f"{context}.items")
        descriptor["items"] = {
            key: item_schema[key] for key in ("type", "format") if key in item_schema
        }
    return descriptor


def _project_parameters(
    document: dict[str, Any],
    path_item: dict[str, Any],
    operation: dict[str, Any],
    operation_key: str,
    *,
    required: bool = True,
) -> list[dict[str, Any]]:
    parameters: dict[tuple[str, str], dict[str, Any]] = {}
    for owner, raw_parameters in (
        ("path", path_item.get("parameters", [])),
        ("operation", operation.get("parameters", [])),
    ):
        if not isinstance(raw_parameters, list):
            raise ProjectionError(f"{operation_key} {owner} parameters must be an array")
        for index, raw_parameter in enumerate(raw_parameters):
            parameter = _resolve_local_ref(
                document,
                raw_parameter,
                f"{operation_key} {owner} parameter {index}",
            )
            location = parameter.get("in")
            name = parameter.get("name")
            if not isinstance(location, str) or not isinstance(name, str):
                raise ProjectionError(f"{operation_key} has a parameter without in/name")
            parameters[(location, name)] = parameter

    projected: list[dict[str, Any]] = []
    for (location, name), parameter in sorted(parameters.items()):
        if (parameter.get("required") is True) != required:
            continue
        projected.append(
            {
                "in": location,
                "name": name,
                "required": required,
                "schema": _schema_descriptor(
                    document,
                    parameter.get("schema", {}),
                    f"{operation_key} parameter {name} schema",
                ),
            }
        )
    return projected


def _request_schema_name(
    document: dict[str, Any], operation: dict[str, Any], operation_key: str
) -> str | None:
    request_body = operation.get("requestBody")
    if request_body is None:
        return None
    body = _resolve_local_ref(document, request_body, f"{operation_key} requestBody")
    content = _as_object(body.get("content", {}), f"{operation_key} requestBody.content")
    media = content.get("application/json")
    if media is None:
        return None
    media_object = _as_object(media, f"{operation_key} application/json")
    schema = _as_object(media_object.get("schema", {}), f"{operation_key} request schema")
    reference = schema.get("$ref")
    if not isinstance(reference, str) or not reference.startswith("#/components/schemas/"):
        raise ProjectionError(f"{operation_key} request schema must use a component reference")
    return reference.rsplit("/", 1)[-1]


def _project_schemas(document: dict[str, Any]) -> dict[str, Any]:
    components = _as_object(document.get("components", {}), "components")
    schemas = _as_object(components.get("schemas", {}), "components.schemas")
    projection: dict[str, Any] = {}
    for name in REQUEST_SCHEMAS:
        schema = _resolve_local_ref(document, schemas.get(name), f"schema {name}")
        properties = _as_object(schema.get("properties", {}), f"schema {name}.properties")
        required = schema.get("required", [])
        if not isinstance(required, list):
            raise ProjectionError(f"schema {name}.required must be an array")
        projection[name] = {
            "allowed_fields": sorted(properties),
            "required_fields": sorted(str(field) for field in required),
        }
    return projection


def _project_security(document: dict[str, Any]) -> dict[str, Any]:
    components = _as_object(document.get("components", {}), "components")
    schemes = _as_object(components.get("securitySchemes", {}), "components.securitySchemes")
    projected_schemes: dict[str, Any] = {}
    for name in SECURITY_SCHEMES:
        scheme = _resolve_local_ref(document, schemes.get(name), f"security scheme {name}")
        projected_schemes[name] = {
            key: scheme[key]
            for key in ("type", "scheme", "bearerFormat", "description")
            if key in scheme
        }
    root_security = document.get("security", [])
    if not isinstance(root_security, list):
        raise ProjectionError("root security must be an array")
    return {"root": root_security, "schemes": projected_schemes}


def project_spec(document: dict[str, Any], source_sha256: str) -> dict[str, Any]:
    """Return the normalized projection of the selected API surface."""
    paths = _as_object(document.get("paths", {}), "paths")
    operations: list[dict[str, Any]] = []
    for method, path, expected_operation_id in SELECTED_OPERATIONS:
        path_item = _as_object(paths.get(path), f"path {path}")
        operation = _as_object(
            path_item.get(method.lower()), f"operation {method} {path}"
        )
        operation_id = operation.get("operationId")
        if not isinstance(operation_id, str):
            raise ProjectionError(f"operation {method} {path} has no operationId")
        operation_key = f"{method} {path}"
        projected: dict[str, Any] = {
            "method": method,
            "operationId": operation_id,
            "path": path,
            "required_parameters": _project_parameters(
                document, path_item, operation, operation_key
            ),
        }
        if path == "/api/v1/activity/{id}/messages":
            projected["optional_parameters"] = _project_parameters(
                document, path_item, operation, operation_key, required=False
            )
            # Only these response shapes establish evidence for verified publication.
            responses = _as_object(operation.get("responses"), f"{operation_key} responses")
            projected["responses"] = {"200": deepcopy(responses.get("200"))}
        request_schema = _request_schema_name(document, operation, operation_key)
        if request_schema is not None:
            projected["request_schema"] = request_schema
        if operation_id != expected_operation_id:
            projected["selection_expected_operationId"] = expected_operation_id
        operations.append(projected)

    info = _as_object(document.get("info", {}), "info")
    raw_servers = document.get("servers", [])
    if not isinstance(raw_servers, list):
        raise ProjectionError("servers must be an array")
    servers = []
    for index, raw_server in enumerate(raw_servers):
        server = _as_object(raw_server, f"server {index}")
        if isinstance(server.get("url"), str):
            servers.append({"url": server["url"]})

    return {
        "projection_version": 1,
        "source": {
            "sha256": source_sha256.upper(),
            "openapi": document.get("openapi"),
            "title": info.get("title"),
            "version": info.get("version"),
            "servers": servers,
        },
        "security": _project_security(document),
        "operations": operations,
        "schemas": _project_schemas(document),
        "response_schemas": {
            name: deepcopy(_resolve_local_ref(
                document, {"$ref": f"#/components/schemas/{name}"}, f"schema {name}"
            ))
            for name in RESPONSE_SCHEMAS
        },
        "exceptions": list(deepcopy(EXCEPTIONS)),
    }


def _load_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ProjectionError(f"cannot read {label} {path}: {exc}") from exc
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProjectionError(f"{label} {path} is not valid JSON: {exc}") from exc
    return _as_object(value, label), raw


def _semantic_projection(projection: dict[str, Any]) -> dict[str, Any]:
    semantic = deepcopy(projection)
    source = _as_object(semantic.get("source", {}), "projection source")
    source.pop("sha256", None)
    return semantic


def _projection_diff(expected: dict[str, Any], actual: dict[str, Any]) -> str:
    expected_text = json.dumps(expected, indent=2, sort_keys=True).splitlines()
    actual_text = json.dumps(actual, indent=2, sort_keys=True).splitlines()
    return "\n".join(
        difflib.unified_diff(
            expected_text,
            actual_text,
            fromfile="pinned-used-surface",
            tofile="candidate-used-surface",
            lineterm="",
        )
    )


def check_contract(
    spec_path: Path,
    fixture_path: Path = DEFAULT_FIXTURE,
    *,
    allow_new_source_hash: bool = False,
) -> tuple[bool, str]:
    """Compare a full OpenAPI document with the pinned used-surface fixture."""
    try:
        fixture, _ = _load_json(fixture_path, "fixture")
        fixture_source = _as_object(fixture.get("source", {}), "fixture source")
        pinned_hash = fixture_source.get("sha256")
        if not isinstance(pinned_hash, str) or not pinned_hash:
            raise ProjectionError("fixture source.sha256 is missing")

        document, raw_spec = _load_json(spec_path, "OpenAPI document")
        actual_hash = hashlib.sha256(raw_spec).hexdigest().upper()
        if actual_hash != pinned_hash.upper() and not allow_new_source_hash:
            return (
                False,
                "OpenAPI source SHA256 mismatch: "
                f"expected {pinned_hash.upper()}, got {actual_hash}. "
                "Use --allow-new-source-hash only to perform an explicit semantic drift check; "
                "it does not update the pinned provenance.",
            )

        candidate = project_spec(document, actual_hash)
        expected_semantic = _semantic_projection(fixture)
        candidate_semantic = _semantic_projection(candidate)
        if candidate_semantic != expected_semantic:
            return (
                False,
                "Intervals.icu selected OpenAPI surface drifted:\n"
                + _projection_diff(expected_semantic, candidate_semantic),
            )
        if actual_hash != pinned_hash.upper():
            return (
                True,
                f"Selected {len(SELECTED_OPERATIONS)}-operation surface matches, but source SHA256 changed from "
                f"{pinned_hash.upper()} to {actual_hash}; pinned provenance was not updated.",
            )
        return True, (
            f"Selected {len(SELECTED_OPERATIONS)}-operation OpenAPI surface and source SHA256 match."
        )
    except ProjectionError as exc:
        return False, f"OpenAPI contract check failed: {exc}"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a full Intervals.icu OpenAPI file against the pinned used surface."
    )
    parser.add_argument("--spec", required=True, type=Path, help="Path to the full OpenAPI JSON")
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Pinned used-surface fixture (defaults to the repository fixture)",
    )
    parser.add_argument(
        "--allow-new-source-hash",
        action="store_true",
        help="Explicitly compare semantics when the full document hash changed",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    ok, message = check_contract(
        args.spec,
        args.fixture,
        allow_new_source_hash=args.allow_new_source_hash,
    )
    stream = sys.stdout if ok else sys.stderr
    print(message, file=stream)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
