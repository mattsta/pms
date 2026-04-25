from __future__ import annotations

from pathlib import Path

from scripts import generate_api_response_contracts as contract_script
from scripts.generate_api_response_contracts import (
    ContractCatalog,
    EndpointContract,
    SchemaContract,
    SchemaFieldContract,
    collect_contract_catalog,
    render_contract_markdown,
)


def test_collect_contract_catalog_contains_endpoints_and_schemas() -> None:
    catalog = collect_contract_catalog()

    assert len(catalog.endpoints) > 0
    assert len(catalog.schemas) > 0
    assert any(endpoint.path == "/api/v1/tasks" for endpoint in catalog.endpoints)
    assert any(schema.name == "TaskResponse" for schema in catalog.schemas)


def test_render_contract_markdown_contains_summary_and_schema_tables() -> None:
    catalog = collect_contract_catalog()
    markdown = render_contract_markdown(catalog)

    assert "# API Response Contracts" in markdown
    assert "## Referenced Schemas" in markdown
    assert (
        "| Method | Path | Purpose | Request Body Type | Success Response |" in markdown
    )
    assert "`/api/v1/tasks`" in markdown
    assert "### `TaskResponse`" in markdown


def test_collect_contract_catalog_preserves_literal_domains_for_plan_test_jobs() -> (
    None
):
    catalog = collect_contract_catalog()
    schemas = {schema.name: schema for schema in catalog.schemas}

    create_fields = {field.name: field for field in schemas["PlanTestJobCreate"].fields}
    update_fields = {field.name: field for field in schemas["PlanTestJobUpdate"].fields}
    response_fields = {
        field.name: field for field in schemas["PlanTestJobResponse"].fields
    }

    assert create_fields["mode"].type_label == "'local' | 'aws'"
    assert update_fields["mode"].type_label == "'local' | 'aws' | null"
    assert response_fields["mode"].type_label == "'local' | 'aws'"


def test_render_contract_markdown_escapes_union_type_cells() -> None:
    catalog = collect_contract_catalog()
    markdown = render_contract_markdown(catalog)

    assert "`'local' \\| 'aws'`" in markdown
    assert "`'local' \\| 'aws' \\| null`" in markdown


def test_collect_contract_catalog_preserves_closed_vocabulary_response_domains() -> (
    None
):
    catalog = collect_contract_catalog()
    schemas = {schema.name: schema for schema in catalog.schemas}

    task_fields = {field.name: field for field in schemas["TaskResponse"].fields}
    project_fields = {field.name: field for field in schemas["ProjectResponse"].fields}
    goal_fields = {field.name: field for field in schemas["GoalResponse"].fields}
    plan_fields = {field.name: field for field in schemas["PlanResponse"].fields}
    saved_search_fields = {
        field.name: field for field in schemas["SavedSearchResponse"].fields
    }
    saved_search_request_fields = {
        field.name: field for field in schemas["SavedSearchRequest"].fields
    }
    saved_search_update_fields = {
        field.name: field for field in schemas["SavedSearchUpdateRequest"].fields
    }
    queue_preset_fields = {
        field.name: field for field in schemas["QueuePresetResponse"].fields
    }
    work_snapshot_totals_fields = {
        field.name: field for field in schemas["WorkSnapshotTotalsResponse"].fields
    }
    automation_run_fields = {
        field.name: field for field in schemas["AutomationRuleRunResponse"].fields
    }
    health_fields = {
        field.name: field for field in schemas["HealthCheckPayload"].fields
    }
    prune_scope_fields = {field.name: field for field in schemas["Scope"].fields}
    policy_usage_fields = {field.name: field for field in schemas["PolicyUsage"].fields}
    retention_policy_fields = {
        field.name: field for field in schemas["TestRunRetentionPolicyResponse"].fields
    }
    task_completion_fields = {
        field.name: field for field in schemas["TaskCompletionActionResponse"].fields
    }
    timeline_fields = {
        field.name: field for field in schemas["TransitionTimelineResponse"].fields
    }
    revision_change_fields = {
        field.name: field for field in schemas["RevisionChangeResponse"].fields
    }
    revision_entry_fields = {
        field.name: field for field in schemas["RevisionEntryResponse"].fields
    }
    retention_alert_fields = {field.name: field for field in schemas["Alert"].fields}
    test_run_retention_fields = {
        field.name: field for field in schemas["TestRunRetentionResponse"].fields
    }

    assert task_fields["status"].type_label == "TaskStatus"
    assert task_fields["priority"].type_label == "Priority"
    assert project_fields["status"].type_label == "ProjectStatus"
    assert goal_fields["status"].type_label == "GoalStatus"
    assert goal_fields["horizon"].type_label == "GoalHorizon"
    assert plan_fields["status"].type_label == "PlanStatus"
    assert plan_fields["format"].type_label == "PlanFormat"
    assert saved_search_request_fields["sort_dir"].type_label == "'asc' | 'desc' | null"
    assert saved_search_update_fields["sort_dir"].type_label == "'asc' | 'desc' | null"
    assert saved_search_fields["scope_type"].type_label == (
        "'global' | 'organization' | 'program' | 'project'"
    )
    assert saved_search_fields["sort_dir"].type_label == "'asc' | 'desc' | null"
    assert queue_preset_fields["population"].type_label == (
        "'visible_operator' | 'scoped_project'"
    )
    assert work_snapshot_totals_fields["risk_level"].type_label == (
        "'low' | 'medium' | 'high' | null"
    )
    assert automation_run_fields["status"].type_label == (
        "'running' | 'skipped' | 'dry_run' | 'success' | 'failed'"
    )
    assert health_fields["status"].type_label == "'healthy' | 'degraded'"
    assert prune_scope_fields["scope_type"].type_label == (
        "'default' | 'project' | 'organization'"
    )
    assert policy_usage_fields["scope_type"].type_label == (
        "'project' | 'organization'"
    )
    assert retention_policy_fields["scope_type"].type_label == (
        "'project' | 'organization'"
    )
    assert task_completion_fields["status"].type_label == "'completed'"
    assert timeline_fields["kind"].type_label == "'workflow' | 'status'"
    assert revision_change_fields["change_type"].type_label == "ChangeType"
    assert revision_entry_fields["change_type"].type_label == "ChangeType"
    assert retention_alert_fields["severity"].type_label == "'warning' | 'critical'"
    assert test_run_retention_fields["sorted_by"].type_label == ("'largest' | 'recent'")
    assert schemas["TaskStatus"].kind == "enum"
    assert schemas["TaskStatus"].enum_values == (
        "'todo'",
        "'in_progress'",
        "'blocked'",
        "'in_review'",
        "'done'",
        "'cancelled'",
    )
    assert schemas["GoalHorizon"].kind == "enum"
    assert schemas["GoalHorizon"].enum_values == (
        "'short_term'",
        "'medium_term'",
        "'long_term'",
    )
    assert schemas["ChangeType"].kind == "enum"
    assert schemas["ChangeType"].enum_values == (
        "'create'",
        "'update'",
        "'delete'",
        "'restore'",
    )


def test_render_contract_markdown_includes_referenced_enum_allowed_values() -> None:
    catalog = collect_contract_catalog()
    markdown = render_contract_markdown(catalog)

    assert "### `TaskStatus`" in markdown
    assert (
        "- Allowed values: `'todo'`, `'in_progress'`, `'blocked'`, `'in_review'`, "
        "`'done'`, `'cancelled'`" in markdown
    )
    assert "### `GoalHorizon`" in markdown
    assert (
        "- Allowed values: `'short_term'`, `'medium_term'`, `'long_term'`" in markdown
    )
    assert "### `ChangeType`" in markdown
    assert (
        "- Allowed values: `'create'`, `'update'`, `'delete'`, `'restore'" in markdown
    )


def test_run_writes_contracts_with_atomic_helper(monkeypatch, tmp_path: Path) -> None:
    catalog = ContractCatalog(
        endpoints=(
            EndpointContract(
                method="GET",
                path="/api/v1/health",
                group="health",
                summary="Health",
                request_label="None",
                response_label="HealthCheckPayload",
                success_status="200",
            ),
        ),
        schemas=(
            SchemaContract(
                name="HealthCheckPayload",
                kind="object",
                description="Health payload",
                enum_values=(),
                fields=(
                    SchemaFieldContract(
                        name="status",
                        type_label="'healthy' | 'degraded'",
                        required=True,
                        description="State",
                    ),
                ),
            ),
        ),
    )
    written: list[tuple[Path, str]] = []

    monkeypatch.setattr(contract_script, "collect_contract_catalog", lambda: catalog)
    monkeypatch.setattr(
        contract_script,
        "format_markdown_with_prettier",
        lambda content, *, filepath: f"formatted::{filepath.name}\n{content}",
    )
    monkeypatch.setattr(
        contract_script,
        "write_text_atomic",
        lambda path, content, **_: written.append((path, content)),
    )

    output_path = tmp_path / "API_RESPONSE_CONTRACTS.md"
    assert contract_script.run(output_path=output_path, check_only=False) == 0
    assert written == [
        (
            output_path,
            "formatted::API_RESPONSE_CONTRACTS.md\n"
            + contract_script.render_contract_markdown(catalog),
        )
    ]
