"""Runtime ID contract for public PMS entity families.

The namespace registry and prefixed-ID utilities are not currently the same
thing as the runtime row-ID contract for most first-class PMS entities.

Today:

- most public stored entities use UUID-native runtime IDs
- a small subset of public entities are prefix-native
- some internal entities also use prefixed IDs without being primary operator
  surfaces

This module makes that split explicit so interface work, documentation, and
future conversions stop relying on implication.
"""

from __future__ import annotations

from typing import Any, Literal

from pms.core.entity_type_contract import ENTITY_TYPE_TABLES, normalize_entity_type

type RuntimeIdStyle = Literal["uuid_native", "prefix_native"]
type RuntimeIdContractScope = Literal[
    "public_stored_entity_family",
    "internal_or_non_public_namespace",
]

# Public entity families accepted across CLI/API/MCP surfaces that have a direct
# relational home in the database.
PUBLIC_ENTITY_ID_STYLES: dict[str, RuntimeIdStyle] = {
    "actor": "uuid_native",
    "organization": "uuid_native",
    "team": "uuid_native",
    "portfolio": "uuid_native",
    "program": "uuid_native",
    "product": "uuid_native",
    "project": "uuid_native",
    "plan": "uuid_native",
    "goal": "uuid_native",
    "objective": "uuid_native",
    "key_result": "uuid_native",
    "task": "uuid_native",
    "milestone": "uuid_native",
    "remote_host": "uuid_native",
    "test_server": "uuid_native",
    "test_run": "uuid_native",
    "session": "uuid_native",
    "automation_rule": "uuid_native",
    "api_key": "prefix_native",
}

# Internal/supporting families already emitted with typed prefixes in active
# codepaths. These are not the main operator-facing work graph.
INTERNAL_PREFIX_NATIVE_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "event",
        "metric",
    }
)


def public_entity_id_style(entity_type: str) -> RuntimeIdStyle:
    """Return the runtime ID style for a public stored entity family."""
    normalized = normalize_entity_type(entity_type)
    try:
        return PUBLIC_ENTITY_ID_STYLES[normalized]
    except KeyError as exc:
        msg = f"Unknown public entity_type '{entity_type}' for runtime ID style lookup."
        raise ValueError(msg) from exc


def runtime_row_id_style_for_entity_type(entity_type: str) -> RuntimeIdStyle | None:
    """Return the runtime row-ID style when the entity family is public.

    Some namespace entries exist for internal/supporting types that are not part
    of the public stored-entity ID contract. Those return ``None`` here.
    """
    try:
        return public_entity_id_style(entity_type)
    except ValueError:
        return None


def runtime_row_id_contract_scope(entity_type: str) -> RuntimeIdContractScope:
    """Classify whether a namespace participates in the public row-ID contract."""
    normalized = normalize_entity_type(entity_type)
    if normalized in PUBLIC_ENTITY_ID_STYLES:
        return "public_stored_entity_family"
    return "internal_or_non_public_namespace"


def namespace_id_contract(prefix: str, name: str) -> dict[str, Any]:
    """Build the machine-readable ID metadata for a namespace entry."""
    return {
        "namespace_generated_id_format": f"{prefix}_<uuid>",
        "namespace_generated_id_kind": "prefix_uuid",
        "runtime_row_id_contract_scope": runtime_row_id_contract_scope(name),
        "runtime_row_id_style": runtime_row_id_style_for_entity_type(name),
    }


def prefix_native_public_entity_types() -> list[str]:
    """Return public entity families that already use prefixed runtime IDs."""
    return sorted(
        entity_type
        for entity_type, style in PUBLIC_ENTITY_ID_STYLES.items()
        if style == "prefix_native"
    )


def uuid_native_public_entity_types() -> list[str]:
    """Return public entity families that currently use UUID-native runtime IDs."""
    return sorted(
        entity_type
        for entity_type, style in PUBLIC_ENTITY_ID_STYLES.items()
        if style == "uuid_native"
    )


def validate_public_entity_id_style_coverage() -> None:
    """Fail fast if the public ID-style mapping drifts from entity coverage."""
    missing = sorted(set(ENTITY_TYPE_TABLES).difference(PUBLIC_ENTITY_ID_STYLES))
    extras = sorted(set(PUBLIC_ENTITY_ID_STYLES).difference(ENTITY_TYPE_TABLES))
    if missing or extras:
        parts: list[str] = []
        if missing:
            parts.append(f"missing styles for: {', '.join(missing)}")
        if extras:
            parts.append(f"unexpected styles for: {', '.join(extras)}")
        raise ValueError("; ".join(parts))
