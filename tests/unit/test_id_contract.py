from __future__ import annotations

from pms.core.id_contract import (
    INTERNAL_PREFIX_NATIVE_ENTITY_TYPES,
    namespace_id_contract,
    prefix_native_public_entity_types,
    public_entity_id_style,
    runtime_row_id_contract_scope,
    runtime_row_id_style_for_entity_type,
    uuid_native_public_entity_types,
    validate_public_entity_id_style_coverage,
)


def test_public_entity_id_style_mapping_covers_entity_type_tables() -> None:
    validate_public_entity_id_style_coverage()


def test_public_runtime_id_style_is_explicit_for_key_entity_families() -> None:
    assert public_entity_id_style("api_key") == "prefix_native"
    assert public_entity_id_style("project") == "uuid_native"
    assert public_entity_id_style("task") == "uuid_native"
    assert public_entity_id_style("actor") == "uuid_native"
    assert public_entity_id_style("product") == "uuid_native"
    assert public_entity_id_style("automation_rule") == "uuid_native"
    assert public_entity_id_style("org") == "uuid_native"


def test_prefix_and_uuid_native_public_sets_match_current_contract() -> None:
    assert prefix_native_public_entity_types() == ["api_key"]
    assert "project" in uuid_native_public_entity_types()
    assert "task" in uuid_native_public_entity_types()
    assert "actor" in uuid_native_public_entity_types()


def test_internal_prefix_native_entities_are_tracked_separately() -> None:
    assert {"event", "metric"} == INTERNAL_PREFIX_NATIVE_ENTITY_TYPES


def test_runtime_row_id_style_for_entity_type_returns_none_for_non_public_family() -> (
    None
):
    assert runtime_row_id_style_for_entity_type("workflow") is None
    assert runtime_row_id_style_for_entity_type("api_key") == "prefix_native"
    assert runtime_row_id_style_for_entity_type("project") == "uuid_native"


def test_runtime_row_id_contract_scope_distinguishes_public_and_non_public_families() -> (
    None
):
    assert runtime_row_id_contract_scope("project") == "public_stored_entity_family"
    assert runtime_row_id_contract_scope("api_key") == "public_stored_entity_family"
    assert (
        runtime_row_id_contract_scope("workflow") == "internal_or_non_public_namespace"
    )


def test_namespace_id_contract_builds_consistent_machine_schema_metadata() -> None:
    assert namespace_id_contract("proj", "project") == {
        "namespace_generated_id_format": "proj_<uuid>",
        "namespace_generated_id_kind": "prefix_uuid",
        "runtime_row_id_contract_scope": "public_stored_entity_family",
        "runtime_row_id_style": "uuid_native",
    }
    assert namespace_id_contract("wf", "workflow") == {
        "namespace_generated_id_format": "wf_<uuid>",
        "namespace_generated_id_kind": "prefix_uuid",
        "runtime_row_id_contract_scope": "internal_or_non_public_namespace",
        "runtime_row_id_style": None,
    }
