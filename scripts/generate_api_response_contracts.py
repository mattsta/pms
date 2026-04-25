"""Generate a typed API request/response contract reference from live OpenAPI."""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

from pms.utils.atomic_files import write_text_atomic
from pms.utils.markdown_formatting import format_markdown_with_prettier

REPO_ROOT = Path(__file__).resolve().parents[1]
HTTP_METHODS: tuple[str, ...] = ("GET", "POST", "PUT", "PATCH", "DELETE")
SUCCESS_STATUS_PRIORITY: tuple[str, ...] = ("200", "201", "202", "204")

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]
type JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, order=True)
class EndpointContract:
    """Contract summary for one method+path operation."""

    method: str
    path: str
    group: str
    summary: str
    request_label: str
    response_label: str
    success_status: str


@dataclass(frozen=True, order=True)
class SchemaFieldContract:
    """Top-level schema field contract."""

    name: str
    type_label: str
    required: bool
    description: str


@dataclass(frozen=True, order=True)
class SchemaContract:
    """Top-level contract for a referenced OpenAPI schema."""

    name: str
    kind: str
    description: str
    enum_values: tuple[str, ...]
    fields: tuple[SchemaFieldContract, ...]


@dataclass(frozen=True)
class ContractCatalog:
    """Rendered contract inputs."""

    endpoints: tuple[EndpointContract, ...]
    schemas: tuple[SchemaContract, ...]


def ensure_runtime_dirs() -> None:
    """Set local runtime directories so OpenAPI import is sandbox-safe."""
    if "PMS_DATA_DIR" not in os.environ:
        os.environ["PMS_DATA_DIR"] = str(REPO_ROOT / ".tmp" / "api-response-contracts")
    if "PMS_LOG_DIR" not in os.environ:
        os.environ["PMS_LOG_DIR"] = str(Path(os.environ["PMS_DATA_DIR"]) / "logs")
    if "PMS_DATABASE_PATH" not in os.environ:
        os.environ["PMS_DATABASE_PATH"] = str(
            Path(os.environ["PMS_DATA_DIR"]) / "pms.db"
        )

    Path(os.environ["PMS_DATA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(os.environ["PMS_LOG_DIR"]).mkdir(parents=True, exist_ok=True)


def _obj(value: JsonValue | None) -> JsonObject:
    if isinstance(value, dict):
        return value
    return {}


def _array(value: JsonValue | None) -> list[JsonValue]:
    if isinstance(value, list):
        return value
    return []


def _text(value: JsonValue | None) -> str:
    if isinstance(value, str):
        return value
    return ""


def _schema_name_from_ref(ref: str) -> str:
    raw = ref.rsplit("/", maxsplit=1)[-1]
    if raw.endswith("-Output"):
        return raw.removesuffix("-Output")
    if raw.endswith("-Input"):
        return raw.removesuffix("-Input")
    return raw


def _literal_value_label(value: JsonValue) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f"'{value}'"
    return str(value)


def _join_type_labels(labels: list[str]) -> str:
    unique_labels: list[str] = []
    for label in labels:
        if not label or label == "unknown":
            continue
        if label not in unique_labels:
            unique_labels.append(label)
    if not unique_labels:
        return "unknown"
    return " | ".join(unique_labels)


def _schema_refs(schema: JsonObject) -> tuple[str, ...]:
    refs: set[str] = set()
    ref_value = _text(schema.get("$ref"))
    if ref_value:
        refs.add(_schema_name_from_ref(ref_value))

    items = _obj(schema.get("items"))
    if items:
        refs.update(_schema_refs(items))

    properties = _obj(schema.get("properties"))
    for value in properties.values():
        refs.update(_schema_refs(_obj(value)))

    for key in ("oneOf", "anyOf", "allOf"):
        for option in _array(schema.get(key)):
            refs.update(_schema_refs(_obj(option)))

    return tuple(sorted(refs))


def _schema_type_label(schema: JsonObject) -> str:
    for key in ("oneOf", "anyOf"):
        options = _array(schema.get(key))
        if options:
            return _join_type_labels(
                [_schema_type_label(_obj(option)) for option in options]
            )

    refs = _schema_refs(schema)
    if refs:
        if len(refs) == 1:
            return refs[0]
        return " | ".join(refs)

    if "const" in schema:
        return _literal_value_label(schema["const"])

    enum_values = _array(schema.get("enum"))
    if enum_values:
        return _join_type_labels([_literal_value_label(value) for value in enum_values])

    schema_type = _text(schema.get("type"))
    if schema_type == "array":
        items = _obj(schema.get("items"))
        return f"array<{_schema_type_label(items)}>"
    if schema_type == "object":
        properties = _obj(schema.get("properties"))
        if properties:
            property_names = sorted(properties)
            preview = property_names[:6]
            suffix = ""
            remaining = len(property_names) - len(preview)
            if remaining > 0:
                suffix = f", +{remaining} more"
            return "object{" + ", ".join(preview) + suffix + "}"
        additional_properties = schema.get("additionalProperties")
        if additional_properties is True:
            return "map<string, json>"
        additional_schema = _obj(
            additional_properties if isinstance(additional_properties, dict) else None
        )
        if additional_schema:
            return f"map<string, {_schema_type_label(additional_schema)}>"
        return "object"
    if schema_type:
        return schema_type
    return "unknown"


def _operation_group(path: str) -> str:
    if path == "/api/v1/health":
        return "health"
    suffix = path.removeprefix("/api/v1/")
    if not suffix:
        return "root"
    return suffix.split("/", maxsplit=1)[0]


def _select_success_response(operation: JsonObject) -> tuple[str, JsonObject]:
    responses = _obj(operation.get("responses"))
    for status in SUCCESS_STATUS_PRIORITY:
        response = _obj(responses.get(status))
        if response:
            return status, response

    success_codes = sorted(
        status for status in responses if status.isdigit() and 200 <= int(status) < 300
    )
    if success_codes:
        status = success_codes[0]
        return status, _obj(responses.get(status))

    default_response = _obj(responses.get("default"))
    if default_response:
        return "default", default_response
    return "unknown", {}


def _content_schema(content: JsonObject) -> JsonObject:
    json_content = _obj(content.get("application/json"))
    if json_content:
        return _obj(json_content.get("schema"))
    for payload in content.values():
        candidate = _obj(payload)
        schema = _obj(candidate.get("schema"))
        if schema:
            return schema
    return {}


def _request_contract(operation: JsonObject) -> tuple[str, tuple[str, ...]]:
    request_body = _obj(operation.get("requestBody"))
    if not request_body:
        return "None", ()
    content = _obj(request_body.get("content"))
    schema = _content_schema(content)
    if not schema:
        return "Body (undocumented schema)", ()
    label = _schema_type_label(schema)
    return label, _schema_refs(schema)


def _response_contract(operation: JsonObject) -> tuple[str, str, tuple[str, ...]]:
    status, response = _select_success_response(operation)
    content = _obj(response.get("content"))
    schema = _content_schema(content)
    if not schema:
        return status, "No body", ()
    label = _schema_type_label(schema)
    return status, label, _schema_refs(schema)


def _collect_schema_fields(
    schema: JsonObject,
    *,
    components: JsonObject,
) -> tuple[SchemaFieldContract, ...]:
    required_names = {
        name for name in _array(schema.get("required")) if isinstance(name, str)
    }

    fields: dict[str, SchemaFieldContract] = {}

    for part in _array(schema.get("allOf")):
        for inherited in _collect_schema_fields(_obj(part), components=components):
            existing = fields.get(inherited.name)
            if existing is None:
                fields[inherited.name] = inherited
            else:
                fields[inherited.name] = SchemaFieldContract(
                    name=existing.name,
                    type_label=existing.type_label or inherited.type_label,
                    required=existing.required or inherited.required,
                    description=existing.description or inherited.description,
                )

    ref_value = _text(schema.get("$ref"))
    if ref_value:
        ref_name = _schema_name_from_ref(ref_value)
        referenced = _obj(_obj(components.get("schemas")).get(ref_name))
        for inherited in _collect_schema_fields(referenced, components=components):
            existing = fields.get(inherited.name)
            if existing is None:
                fields[inherited.name] = inherited
            else:
                fields[inherited.name] = SchemaFieldContract(
                    name=existing.name,
                    type_label=existing.type_label or inherited.type_label,
                    required=existing.required or inherited.required,
                    description=existing.description or inherited.description,
                )

    properties = _obj(schema.get("properties"))
    for name in sorted(properties):
        property_schema = _obj(properties.get(name))
        fields[name] = SchemaFieldContract(
            name=name,
            type_label=_schema_type_label(property_schema),
            required=name in required_names,
            description=_text(property_schema.get("description")),
        )

    return tuple(sorted(fields.values(), key=lambda field: field.name))


def _schema_kind(schema: JsonObject) -> str:
    if "const" in schema:
        return "const"

    if _array(schema.get("enum")):
        return "enum"

    schema_type = _text(schema.get("type"))
    if schema_type:
        return schema_type

    ref_value = _text(schema.get("$ref"))
    if ref_value:
        return "ref"
    if _array(schema.get("allOf")):
        return "allOf"
    if _array(schema.get("oneOf")):
        return "oneOf"
    if _array(schema.get("anyOf")):
        return "anyOf"
    return "unknown"


def _schema_enum_values(schema: JsonObject) -> tuple[str, ...]:
    if "const" in schema:
        return (_literal_value_label(schema["const"]),)

    enum_values = _array(schema.get("enum"))
    if not enum_values:
        return ()
    return tuple(_literal_value_label(value) for value in enum_values)


def _expand_referenced_schema_names(
    initial_names: set[str],
    *,
    schemas_obj: JsonObject,
) -> set[str]:
    expanded = set(initial_names)
    pending = list(initial_names)

    while pending:
        schema_name = pending.pop()
        schema = _obj(schemas_obj.get(schema_name))
        if not schema:
            continue
        for ref_name in _schema_refs(schema):
            if ref_name in expanded:
                continue
            expanded.add(ref_name)
            pending.append(ref_name)

    return expanded


def collect_contract_catalog() -> ContractCatalog:
    """Collect endpoint and schema contracts from live OpenAPI."""
    ensure_runtime_dirs()

    from pms.api.app import app

    openapi = _obj(app.openapi())
    paths = _obj(openapi.get("paths"))
    components = _obj(openapi.get("components"))
    schemas_obj = _obj(components.get("schemas"))

    endpoints: list[EndpointContract] = []
    referenced_schema_names: set[str] = set()

    for path in sorted(paths):
        if not path.startswith("/api/v1"):
            continue
        operation_map = _obj(paths.get(path))
        for method in HTTP_METHODS:
            operation = _obj(operation_map.get(method.lower()))
            if not operation:
                continue

            summary = _text(operation.get("summary")) or _text(
                operation.get("operationId")
            )
            request_label, request_refs = _request_contract(operation)
            success_status, response_label, response_refs = _response_contract(
                operation
            )
            referenced_schema_names.update(request_refs)
            referenced_schema_names.update(response_refs)

            endpoints.append(
                EndpointContract(
                    method=method,
                    path=path,
                    group=_operation_group(path),
                    summary=summary,
                    request_label=request_label,
                    response_label=response_label,
                    success_status=success_status,
                )
            )

    expanded_schema_names = _expand_referenced_schema_names(
        referenced_schema_names,
        schemas_obj=schemas_obj,
    )

    schema_contracts: list[SchemaContract] = []
    for schema_name in sorted(expanded_schema_names):
        schema = _obj(schemas_obj.get(schema_name))
        if not schema:
            continue
        schema_contracts.append(
            SchemaContract(
                name=schema_name,
                kind=_schema_kind(schema),
                description=_text(schema.get("description")),
                enum_values=_schema_enum_values(schema),
                fields=_collect_schema_fields(schema, components=components),
            )
        )

    return ContractCatalog(
        endpoints=tuple(
            sorted(
                endpoints,
                key=lambda endpoint: (endpoint.group, endpoint.path, endpoint.method),
            )
        ),
        schemas=tuple(sorted(schema_contracts, key=lambda schema: schema.name)),
    )


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|")


def render_contract_markdown(catalog: ContractCatalog) -> str:
    """Render endpoint contract documentation markdown."""
    grouped: dict[str, list[EndpointContract]] = {}
    for endpoint in catalog.endpoints:
        grouped.setdefault(endpoint.group, []).append(endpoint)

    lines: list[str] = []
    lines.append("# API Response Contracts")
    lines.append("")
    lines.append(
        "Generated from live OpenAPI route + schema contracts. This supplements (does not replace) `docs/API_REFERENCE.md`."
    )
    lines.append("")
    lines.append("Regenerate:")
    lines.append("")
    lines.append("```bash")
    lines.append("uv run python scripts/generate_api_response_contracts.py")
    lines.append("```")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Endpoint contracts: **{len(catalog.endpoints)}**")
    lines.append(f"- Referenced schemas: **{len(catalog.schemas)}**")
    lines.append("")

    for group in sorted(grouped):
        endpoints = grouped[group]
        lines.append(f"## `{group}` ({len(endpoints)})")
        lines.append("")
        lines.append(
            "| Method | Path | Purpose | Request Body Type | Success Response |"
        )
        lines.append("| --- | --- | --- | --- | --- |")
        for endpoint in endpoints:
            purpose = endpoint.summary or "-"
            success_label = f"{endpoint.success_status} {endpoint.response_label}"
            lines.append(
                "| "
                f"`{endpoint.method}` | "
                f"`{endpoint.path}` | "
                f"{_escape_cell(purpose)} | "
                f"`{_escape_cell(endpoint.request_label)}` | "
                f"`{_escape_cell(success_label)}` |"
            )
        lines.append("")

    lines.append("## Referenced Schemas")
    lines.append("")
    for schema in catalog.schemas:
        lines.append(f"### `{schema.name}`")
        lines.append("")
        lines.append(f"- Kind: `{schema.kind}`")
        if schema.description:
            lines.append(f"- Description: {schema.description}")
        if schema.enum_values:
            lines.append(
                "- Allowed values: "
                + ", ".join(f"`{_escape_cell(value)}`" for value in schema.enum_values)
            )
        if not schema.fields:
            lines.append("- Top-level fields: _none_")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Field | Type | Required | Description |")
        lines.append("| --- | --- | --- | --- |")
        for field in schema.fields:
            required_text = "yes" if field.required else "no"
            description = field.description or "-"
            lines.append(
                "| "
                f"`{field.name}` | "
                f"`{_escape_cell(field.type_label)}` | "
                f"{required_text} | "
                f"{_escape_cell(description)} |"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def run(output_path: Path, check_only: bool) -> int:
    """Write or check generated contract documentation."""
    catalog = collect_contract_catalog()
    rendered = format_markdown_with_prettier(
        render_contract_markdown(catalog),
        filepath=output_path,
    )

    if check_only:
        if not output_path.exists():
            print(f"Contract check failed: missing file {output_path}")
            return 1
        existing = output_path.read_text()
        if existing != rendered:
            print(
                "Contract check failed: API response contracts are out of date.\n"
                f"Run: uv run python scripts/generate_api_response_contracts.py --output {output_path}"
            )
            return 1
        print(
            "Contract check passed: "
            f"{output_path} (endpoints={len(catalog.endpoints)}, schemas={len(catalog.schemas)})"
        )
        return 0

    write_text_atomic(output_path, rendered)
    print(
        "Wrote API response contracts: "
        f"{output_path} (endpoints={len(catalog.endpoints)}, schemas={len(catalog.schemas)})"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate API request/response contract reference from live OpenAPI."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "docs" / "API_RESPONSE_CONTRACTS.md",
        help="Output markdown path.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check mode: fail if output differs from generated content.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run(output_path=args.output, check_only=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
