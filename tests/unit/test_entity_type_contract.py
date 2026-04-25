from __future__ import annotations

import pytest

from pms.core.entity_type_contract import (
    db_backed_extra_entity_types,
    entity_table_for_type,
    namespace_registered_entity_types,
    normalize_entity_type,
    supported_entity_types,
    validate_entity_type,
)


def test_entity_type_aliases_normalize_to_canonical_values() -> None:
    assert normalize_entity_type("org") == "organization"
    assert normalize_entity_type("keyresult") == "key_result"
    assert normalize_entity_type("key-results") == "key_result"


def test_validate_entity_type_uses_namespace_backed_types() -> None:
    assert validate_entity_type("task") == "task"
    assert validate_entity_type("project") == "project"
    assert validate_entity_type("api_key") == "api_key"


def test_supported_entity_types_include_namespace_and_db_backed_extras() -> None:
    supported = supported_entity_types()

    assert "api_key" in supported
    assert "actor" in supported
    assert "automation_rule" in supported
    assert "product" in supported


def test_namespace_and_db_backed_entity_type_sets_are_explicitly_distinguished() -> (
    None
):
    registered = namespace_registered_entity_types()
    extras = db_backed_extra_entity_types()

    assert "api_key" in registered
    assert "actor" not in registered
    assert "automation_rule" not in registered
    assert "product" not in registered

    assert extras == ["actor", "automation_rule", "product"]


def test_validate_entity_type_with_allowed_subset_returns_suggestions() -> None:
    with pytest.raises(ValueError) as exc_info:
        validate_entity_type("tas", allowed={"task", "goal", "objective"})
    message = str(exc_info.value)
    assert "Unknown entity_type 'tas'." in message
    assert "Supported entity_type values: goal, objective, task." in message
    assert "Did you mean 'task'?" in message


def test_entity_table_for_type_returns_relational_table() -> None:
    assert entity_table_for_type("org") == "organizations"
    assert entity_table_for_type("task") == "tasks"
    assert entity_table_for_type("workflow") is None
