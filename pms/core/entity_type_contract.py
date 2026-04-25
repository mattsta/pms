"""Shared entity_type normalization and validation rules.

This module deliberately distinguishes between:

- namespace-backed entity families that participate in the prefixed ID registry
- DB-backed extras that are valid public entity types but are not namespace
  generated today

That split matters because the namespace registry is also an ID-generation
surface. UUID-native entities should not be registered there until their ID
contract is intentionally promoted.
"""

from __future__ import annotations

from collections.abc import Collection
from difflib import get_close_matches

from pms.core.namespace import get_namespace_registry

ENTITY_TYPE_ALIASES: dict[str, str] = {
    "org": "organization",
    "keyresult": "key_result",
    "keyresults": "key_result",
    "key_results": "key_result",
}

ENTITY_TYPE_TABLES: dict[str, str] = {
    "actor": "actors",
    "organization": "organizations",
    "team": "teams",
    "portfolio": "portfolios",
    "program": "programs",
    "product": "products",
    "project": "projects",
    "plan": "plans",
    "goal": "goals",
    "objective": "objectives",
    "key_result": "key_results",
    "task": "tasks",
    "milestone": "milestones",
    "remote_host": "remote_hosts",
    "test_server": "test_servers",
    "test_run": "test_runs",
    "session": "sessions",
    "automation_rule": "automation_rules",
    "api_key": "api_keys",
}

DB_BACKED_ENTITY_TYPE_EXTRAS: frozenset[str] = frozenset(
    {
        "actor",
        "automation_rule",
        "product",
    }
)


def namespace_registered_entity_types() -> list[str]:
    """Return canonical entity families backed by the namespace registry."""
    registry = get_namespace_registry()
    return sorted({namespace.name for namespace in registry.list_all()})


def db_backed_extra_entity_types() -> list[str]:
    """Return valid DB-backed entity families that are not namespace-generated."""
    registered = set(namespace_registered_entity_types())
    extras = set(ENTITY_TYPE_TABLES).difference(registered)
    return sorted(extras)


def normalize_entity_type(entity_type: str) -> str:
    """Return the canonical entity_type token."""
    normalized = entity_type.strip().lower().replace("-", "_").replace(" ", "_")
    return ENTITY_TYPE_ALIASES.get(normalized, normalized)


def supported_entity_types(
    *,
    allowed: Collection[str] | None = None,
) -> list[str]:
    """Return supported canonical entity_type values for a given surface."""
    if allowed is not None:
        return sorted({normalize_entity_type(value) for value in allowed})

    names = set(namespace_registered_entity_types())
    names.update(ENTITY_TYPE_TABLES)
    return sorted(names)


def suggest_entity_types(
    entity_type: str,
    *,
    allowed: Collection[str] | None = None,
    limit: int = 1,
) -> list[str]:
    """Suggest likely canonical entity_type values."""
    raw = entity_type.strip().lower()
    normalized = normalize_entity_type(entity_type)
    candidates = supported_entity_types(allowed=allowed)

    suggestions: list[str] = []
    for candidate in get_close_matches(normalized, candidates, n=limit, cutoff=0.6):
        if candidate not in suggestions:
            suggestions.append(candidate)
    if raw != normalized:
        for candidate in get_close_matches(raw, candidates, n=limit, cutoff=0.6):
            if candidate not in suggestions:
                suggestions.append(candidate)
    return suggestions[:limit]


def validate_entity_type(
    entity_type: str,
    *,
    allowed: Collection[str] | None = None,
    field_name: str = "entity_type",
) -> str:
    """Validate and canonicalize an entity_type token."""
    normalized = normalize_entity_type(entity_type)
    candidates = supported_entity_types(allowed=allowed)
    if normalized in candidates:
        return normalized

    message = f"Unknown {field_name} '{entity_type}'."
    suggestions = suggest_entity_types(entity_type, allowed=allowed)
    if allowed is None:
        message += " Use a registered PMS entity type."
    else:
        message += f" Supported {field_name} values: {', '.join(candidates)}."
    if suggestions:
        suggestion_text = ", ".join(f"'{value}'" for value in suggestions)
        message += f" Did you mean {suggestion_text}?"
    raise ValueError(message)


def entity_table_for_type(entity_type: str) -> str | None:
    """Return the direct relational table for an entity_type when one exists."""
    return ENTITY_TYPE_TABLES.get(normalize_entity_type(entity_type))
