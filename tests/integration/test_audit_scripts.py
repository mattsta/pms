"""Integration coverage for reusable audit scripts."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.audit_actor_reference_integrity import (
    run_audit as run_actor_reference_integrity_audit,
)
from scripts.audit_actor_surface_truth import (
    run_audit as run_actor_surface_truth_audit,
)
from scripts.audit_actor_workload_math import (
    run_audit as run_actor_workload_math_audit,
)
from scripts.audit_api_goal_lifecycle_contracts import (
    run_audit as run_api_goal_lifecycle_contract_audit,
)
from scripts.audit_api_key_result_lifecycle_contracts import (
    run_audit as run_api_key_result_lifecycle_contract_audit,
)
from scripts.audit_api_objective_lifecycle_contracts import (
    run_audit as run_api_objective_lifecycle_contract_audit,
)
from scripts.audit_api_project_lifecycle_contracts import (
    run_audit as run_api_project_lifecycle_contract_audit,
)
from scripts.audit_atomic_artifact_writes import (
    run_audit as run_atomic_artifact_write_audit,
)
from scripts.audit_cli_api_contract_parity import (
    run_audit as run_cli_api_contract_parity_audit,
)
from scripts.audit_cli_goal_lifecycle_contracts import (
    run_audit as run_cli_goal_lifecycle_contract_audit,
)
from scripts.audit_cli_interactive_chooser_contracts import (
    run_audit as run_cli_interactive_chooser_contract_audit,
)
from scripts.audit_cli_json_mutation_parity import run_audit as run_json_mutation_audit
from scripts.audit_cli_json_output_rendering import (
    run_audit as run_cli_json_output_rendering_audit,
)
from scripts.audit_cli_key_result_lifecycle_contracts import (
    run_audit as run_cli_key_result_lifecycle_contract_audit,
)
from scripts.audit_cli_objective_lifecycle_contracts import (
    run_audit as run_cli_objective_lifecycle_contract_audit,
)
from scripts.audit_cli_recent_terminal_summary_contracts import (
    run_audit as run_cli_recent_terminal_summary_contract_audit,
)
from scripts.audit_cli_surface_contracts import run_audit as run_cli_surface_audit
from scripts.audit_cli_text_summary_contracts import (
    run_audit as run_cli_text_summary_contract_audit,
)
from scripts.audit_cli_tty_table_contracts import (
    run_audit as run_cli_tty_table_contract_audit,
)
from scripts.audit_client_lifecycle_list_payload_parity import (
    run_audit as run_client_lifecycle_list_payload_parity_audit,
)
from scripts.audit_client_lifecycle_list_surface_contracts import (
    run_audit as run_client_lifecycle_list_surface_contract_audit,
)
from scripts.audit_client_operator_payload_parity import (
    run_audit as run_client_operator_payload_parity_audit,
)
from scripts.audit_client_operator_surface_contracts import (
    run_audit as run_client_operator_surface_contract_audit,
)
from scripts.audit_command_prefix_templates import run_audit as run_command_prefix_audit
from scripts.audit_continuation_quality import run_audit as run_continuation_audit
from scripts.audit_cross_surface_lifecycle_aggregate_source_contracts import (
    run_audit as run_cross_surface_lifecycle_aggregate_source_contract_audit,
)
from scripts.audit_cross_surface_operator_dashboard_contracts import (
    run_audit as run_cross_surface_operator_dashboard_contract_audit,
)
from scripts.audit_cross_surface_project_lifecycle_contracts import (
    run_audit as run_cross_surface_project_lifecycle_contract_audit,
)
from scripts.audit_docs_runtime_truth import run_audit as run_docs_runtime_truth_audit
from scripts.audit_env_isolation import run_audit as run_env_isolation_audit
from scripts.audit_execution_backed_rollups import (
    run_audit as run_execution_rollup_audit,
)
from scripts.audit_goal_execution_scope import (
    run_audit as run_goal_execution_scope_audit,
)
from scripts.audit_graph_discoverability import (
    run_audit as run_graph_discoverability_audit,
)
from scripts.audit_graph_report_surface import (
    run_audit as run_graph_report_surface_audit,
)
from scripts.audit_graph_summary_surface_truth import (
    run_audit as run_graph_summary_surface_truth_audit,
)
from scripts.audit_graph_timestamp_rollups import (
    run_audit as run_graph_timestamp_rollup_audit,
)
from scripts.audit_hierarchy_edge_authority import (
    run_audit as run_hierarchy_edge_authority_audit,
)
from scripts.audit_local_server_surface_truth import (
    run_audit as run_local_server_surface_truth_audit,
)
from scripts.audit_mcp_goal_lifecycle_contracts import (
    run_audit as run_mcp_goal_lifecycle_contract_audit,
)
from scripts.audit_mcp_key_result_lifecycle_contracts import (
    run_audit as run_mcp_key_result_lifecycle_contract_audit,
)
from scripts.audit_mcp_objective_lifecycle_contracts import (
    run_audit as run_mcp_objective_lifecycle_contract_audit,
)
from scripts.audit_mcp_project_lifecycle_contracts import (
    run_audit as run_mcp_project_lifecycle_contract_audit,
)
from scripts.audit_mcp_tool_parity import run_audit as run_mcp_tool_parity_audit
from scripts.audit_planning_state import run_audit as run_planning_state_audit
from scripts.audit_release_version_consistency import (
    run_audit as run_release_version_consistency_audit,
)
from scripts.audit_runtime_guards import run_audit as run_runtime_guard_audit
from scripts.audit_scenario_packages import run_audit as run_scenario_package_audit
from scripts.audit_secret_hygiene import run_audit as run_secret_hygiene_audit
from scripts.audit_server_deployment_doc_truth import (
    run_audit as run_server_deployment_doc_truth_audit,
)
from scripts.audit_service_transaction_boundaries import (
    run_audit as run_service_transaction_boundary_audit,
)
from scripts.audit_visibility_population_contracts import (
    run_audit as run_visibility_population_audit,
)
from scripts.cleanup_fixture_backlog import (
    run_cleanup as run_fixture_cleanup,
)
from scripts.cleanup_fixture_backlog import (
    run_report as run_fixture_cleanup_report,
)
from scripts.report_active_goal_backlog import (
    run_report as run_active_goal_backlog_report,
)


class TestAuditScripts:
    """Tests for reusable audit script contracts."""

    def test_continuation_quality_audit_is_clean(self) -> None:
        """Continuation audit should pass on the checked-in entry surfaces."""
        result = run_continuation_audit()
        assert result.issues == ()

    def test_scenario_package_audit_is_clean(self) -> None:
        """Scenario package audit should pass on the checked-in scenario docs."""
        issues = run_scenario_package_audit()
        assert issues == ()

    def test_runtime_guard_audit_is_clean(self) -> None:
        """Maintained scenario contract smokes should stay bounded and auditable."""
        issues = run_runtime_guard_audit()
        assert issues == ()

    def test_json_mutation_parity_audit_is_clean(self) -> None:
        """Core create/update commands should keep machine-readable parity."""
        issues = run_json_mutation_audit()
        assert issues == ()

    def test_cli_json_output_rendering_audit_is_clean(self) -> None:
        """JSON branches should not render through rich console helpers."""
        issues = run_cli_json_output_rendering_audit()
        assert issues == ()

    def test_cli_tty_table_contract_audit_is_clean(self) -> None:
        """TTY-backed and non-interactive task tables should keep semantic anchors."""
        issues = run_cli_tty_table_contract_audit()
        assert issues == ()

    def test_cli_text_summary_contract_audit_is_clean(self) -> None:
        """TTY-backed and non-interactive text summaries should keep semantic anchors."""
        issues = run_cli_text_summary_contract_audit()
        assert issues == ()

    def test_cli_interactive_chooser_contract_audit_is_clean(self) -> None:
        """Duplicate-entity chooser retries should keep stable semantic anchors."""
        issues = run_cli_interactive_chooser_contract_audit()
        assert issues == ()

    def test_cli_goal_lifecycle_contract_audit_is_clean(self) -> None:
        """Goal show and goal summary JSON should stay aligned with lifecycle rollups."""
        issues = asyncio.run(run_cli_goal_lifecycle_contract_audit())
        assert issues == ()

    def test_cli_key_result_lifecycle_contract_audit_is_clean(self) -> None:
        """Key-result list/show JSON should stay aligned with lifecycle rollups."""
        issues = asyncio.run(run_cli_key_result_lifecycle_contract_audit())
        assert issues == ()

    def test_cli_objective_lifecycle_contract_audit_is_clean(self) -> None:
        """Objective list/show JSON should stay aligned with lifecycle rollups."""
        issues = asyncio.run(run_cli_objective_lifecycle_contract_audit())
        assert issues == ()

    def test_cli_recent_terminal_summary_contract_audit_is_clean(self) -> None:
        """Recent-terminal text summaries should keep semantic anchors."""
        issues = run_cli_recent_terminal_summary_contract_audit()
        assert issues == ()

    def test_client_operator_surface_contract_audit_is_clean(self) -> None:
        """Maintained Python and Rust clients should keep operator-surface semantics aligned."""
        issues = run_client_operator_surface_contract_audit()
        assert issues == ()

    def test_client_operator_payload_parity_audit_is_clean(self) -> None:
        """Maintained Python and Rust clients should return the same dashboard-family payloads."""
        issues = run_client_operator_payload_parity_audit()
        assert issues == ()

    def test_client_lifecycle_list_payload_parity_audit_is_clean(self) -> None:
        """Maintained Python and Rust clients should agree on lifecycle list semantics."""
        issues = run_client_lifecycle_list_payload_parity_audit()
        assert issues == ()

    def test_client_lifecycle_list_surface_contract_audit_is_clean(self) -> None:
        """Maintained lifecycle-list source contracts should stay aligned."""
        issues = run_client_lifecycle_list_surface_contract_audit()
        assert issues == ()

    def test_api_project_lifecycle_contract_audit_is_clean(self) -> None:
        """Project API surfaces should stay aligned with shared lifecycle rollups."""
        issues = asyncio.run(run_api_project_lifecycle_contract_audit())
        assert issues == ()

    def test_api_goal_lifecycle_contract_audit_is_clean(self) -> None:
        """Goal API aggregate surfaces should stay aligned with shared lifecycle rollups."""
        issues = asyncio.run(run_api_goal_lifecycle_contract_audit())
        assert issues == ()

    def test_api_key_result_lifecycle_contract_audit_is_clean(self) -> None:
        """Key result API aggregate surfaces should stay aligned with lifecycle fields."""
        issues = asyncio.run(run_api_key_result_lifecycle_contract_audit())
        assert issues == ()

    def test_mcp_key_result_lifecycle_contract_audit_is_clean(self) -> None:
        """Key-result MCP aggregate surfaces should stay aligned with lifecycle fields."""
        issues = asyncio.run(run_mcp_key_result_lifecycle_contract_audit())
        assert issues == ()

    def test_api_objective_lifecycle_contract_audit_is_clean(self) -> None:
        """Objective API aggregate surfaces should stay aligned with shared lifecycle rollups."""
        issues = asyncio.run(run_api_objective_lifecycle_contract_audit())
        assert issues == ()

    def test_cross_surface_project_lifecycle_contract_audit_is_clean(self) -> None:
        """CLI, API, and MCP project lifecycle surfaces should stay aligned."""
        issues = run_cross_surface_project_lifecycle_contract_audit()
        assert issues == ()

    def test_cross_surface_lifecycle_aggregate_source_contract_audit_is_clean(
        self,
    ) -> None:
        """Static goal/project lifecycle aggregate field and link contracts should stay aligned."""
        issues = run_cross_surface_lifecycle_aggregate_source_contract_audit()
        assert issues == ()

    def test_cross_surface_operator_dashboard_contract_audit_is_clean(self) -> None:
        """CLI, API, and MCP aggregate dashboards should stay aligned."""
        issues = run_cross_surface_operator_dashboard_contract_audit()
        assert issues == ()

    def test_cli_surface_contract_audit_is_clean(self) -> None:
        """Broad JSON entry/show/list surfaces should stay machine-usable."""
        result = run_cli_surface_audit()
        assert result.issues == ()

    def test_planning_state_audit_is_clean(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Planning-state lifecycle and operator views should stay reconciled."""
        from pms.config.settings import reload_settings

        data_dir = tmp_path / "planning-state-audit"
        monkeypatch.setenv("PMS_DATA_DIR", str(data_dir))
        monkeypatch.setenv("PMS_DATABASE_PATH", str(data_dir / "pms.db"))
        monkeypatch.setenv("PMS_LOG_DIR", str(data_dir / "logs"))
        monkeypatch.setenv("PMS_ENV_FILE", str(data_dir / ".env"))
        monkeypatch.setenv("PMS_WRITE_MODE", "direct")
        monkeypatch.setenv("PMS_CLI_ARGV0", "uv run pms")
        monkeypatch.delenv("PMS_SERVER_BASE_URL", raising=False)
        monkeypatch.delenv("PMS_API_KEY", raising=False)
        monkeypatch.delenv("PMS_API_KEY_PATH", raising=False)
        reload_settings()

        init_result = subprocess.run(
            ["uv", "run", "pms", "init"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert init_result.returncode == 0, init_result.stdout + init_result.stderr

        issues = run_planning_state_audit()
        assert issues == ()

    def test_secret_hygiene_audit_is_clean(self) -> None:
        """Repo-local secrets should not remain tracked in git."""
        issues = run_secret_hygiene_audit()
        assert issues == ()

    def test_service_transaction_boundary_audit_is_clean(self) -> None:
        """Service mutation orchestration should keep explicit outer transaction ownership."""
        issues = run_service_transaction_boundary_audit()
        assert issues == ()

    def test_execution_backed_rollup_audit_is_clean(self) -> None:
        """Execution-backed goal/KR specs should stay in sync with live task progress."""
        issues = run_execution_rollup_audit()
        assert issues == ()

    def test_goal_execution_scope_audit_is_clean(self) -> None:
        """Multi-goal goal summaries should require explicit execution links."""
        issues = run_goal_execution_scope_audit()
        assert issues == ()

    def test_graph_timestamp_rollup_audit_is_clean(self) -> None:
        """Graph timestamp surfaces should keep deep rollup composition contracts."""
        issues = run_graph_timestamp_rollup_audit()
        assert issues == ()

    def test_graph_summary_surface_truth_audit_is_clean(self) -> None:
        """CLI summary surfaces should agree on bubbled graph recency end to end."""
        issues = run_graph_summary_surface_truth_audit()
        assert issues == ()

    def test_graph_discoverability_audit_is_clean(self) -> None:
        """Primary show surfaces should stay traversable up and down the work graph."""
        issues = run_graph_discoverability_audit()
        assert issues == ()

    def test_graph_report_surface_audit_is_clean(self) -> None:
        """Unified graph reporting should keep plans, tasks, actors, and evidence aligned."""
        issues = run_graph_report_surface_audit()
        assert issues == ()

    def test_hierarchy_edge_authority_audit_is_clean(self) -> None:
        """Hierarchy read surfaces should derive from authoritative scope edges."""
        issues = run_hierarchy_edge_authority_audit()
        assert issues == ()

    def test_command_prefix_template_audit_is_clean(self) -> None:
        """API guidance should use invocation-agnostic command templates."""
        issues = run_command_prefix_audit()
        assert issues == ()

    def test_docs_runtime_truth_audit_is_clean(self) -> None:
        """Key operator guides should describe effective runtime write behavior."""
        issues = run_docs_runtime_truth_audit()
        assert issues == ()

    def test_env_isolation_audit_is_clean(self) -> None:
        """Maintained shell harnesses should keep config writes inside isolated env files."""
        issues = run_env_isolation_audit()
        assert issues == ()

    def test_mcp_tool_parity_audit_is_clean(self) -> None:
        """MCP server exports should stay aligned with registry metadata."""
        issues = run_mcp_tool_parity_audit()
        assert issues == ()

    def test_mcp_project_lifecycle_contract_audit_is_clean(self) -> None:
        """MCP project tools should stay aligned with shared lifecycle rollups."""
        issues = run_mcp_project_lifecycle_contract_audit()
        assert issues == ()

    def test_mcp_goal_lifecycle_contract_audit_is_clean(self) -> None:
        """MCP goal summary tools should stay aligned with shared lifecycle rollups."""
        issues = asyncio.run(run_mcp_goal_lifecycle_contract_audit())
        assert issues == ()

    def test_mcp_objective_lifecycle_contract_audit_is_clean(self) -> None:
        """MCP objective tools should stay aligned with shared lifecycle rollups."""
        issues = asyncio.run(run_mcp_objective_lifecycle_contract_audit())
        assert issues == ()

    def test_visibility_population_audit_is_clean(self) -> None:
        """Visible-vs-retained list contracts should stay explicit and truthful."""
        issues = run_visibility_population_audit()
        assert issues == ()

    def test_actor_reference_integrity_audit_is_clean(self) -> None:
        """Canonical actor refs should stay aligned across actor-aware surfaces."""
        issues = run_actor_reference_integrity_audit()
        assert issues == ()

    def test_actor_surface_truth_audit_is_clean(self) -> None:
        """Actor list/show surfaces should bubble deep activity and transitions."""
        issues = run_actor_surface_truth_audit()
        assert issues == ()

    def test_actor_workload_math_audit_is_clean(self) -> None:
        """Actor workload rollups should stay mathematically consistent."""
        issues = run_actor_workload_math_audit()
        assert issues == ()

    def test_atomic_artifact_write_audit_is_clean(self) -> None:
        """Named report/summary artifact writers should keep atomic helper usage."""
        issues = run_atomic_artifact_write_audit()
        assert issues == ()

    def test_release_version_consistency_audit_is_clean(self) -> None:
        """Release-facing version surfaces should stay aligned."""
        issues = run_release_version_consistency_audit()
        assert issues == ()

    def test_server_deployment_doc_truth_audit_is_clean(self) -> None:
        """Deployment guide should stay grounded in the live server/runtime contract."""
        issues = run_server_deployment_doc_truth_audit()
        assert issues == ()

    def test_local_server_surface_truth_audit_is_clean(self) -> None:
        """Default local server URLs should stay aligned across docs and client surfaces."""
        issues = run_local_server_surface_truth_audit()
        assert issues == ()

    def test_active_goal_backlog_report_classifies_residual_active_goals(self) -> None:
        """Active-goal backlog reporting should distinguish actionable work from retained residue."""
        result = run_active_goal_backlog_report()
        assert "summary" in result
        assert "severity_counts" in result["summary"]
        assert "recommendation" in result["summary"]

    def test_fixture_cleanup_report_classifies_known_fixture_projects(
        self, tmp_path
    ) -> None:
        """Fixture cleanup reporting should recognize named fixture projects and orphans."""
        data_dir = tmp_path / "fixture-cleanup-report"
        env = os.environ.copy()
        env["PMS_DATA_DIR"] = str(data_dir)
        env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
        env["PMS_LOG_DIR"] = str(data_dir / "logs")
        env["PMS_ENV_FILE"] = str(data_dir / ".env")
        env["PMS_WRITE_MODE"] = "direct"
        env["PMS_CLI_ARGV0"] = "uv run pms"
        env.pop("PMS_SERVER_BASE_URL", None)
        env.pop("PMS_API_KEY", None)
        env.pop("PMS_API_KEY_PATH", None)

        def run_cli(*args: str) -> str:
            result = subprocess.run(
                ["uv", "run", "pms", *args],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        def extract_id(output: str) -> str:
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith("ID:"):
                    return stripped.split("ID:", 1)[1].strip()
            raise AssertionError(f"unable to extract ID from output:\n{output}")

        run_cli("init")
        run_cli("project", "create", "Audit Project fixture-seed", "--format", "json")
        goal_payload = json.loads(
            run_cli(
                "goal",
                "create",
                "Audit Goal",
                "--project",
                "Audit Project fixture-seed",
                "--format",
                "json",
            )
        )
        goal_id = goal_payload["goal"]["id"]
        objective_payload = json.loads(
            run_cli(
                "objective",
                "create",
                "Audit Objective",
                "--goal-id",
                goal_id,
                "--format",
                "json",
            )
        )
        objective_id = objective_payload["objective"]["id"]
        key_result_id = extract_id(
            run_cli(
                "keyresult",
                "create",
                "Audit KR",
                "--objective-id",
                objective_id,
            )
        )
        run_cli(
            "plan",
            "create",
            "Audit Plan",
            "--project",
            "Audit Project fixture-seed",
            "--status",
            "active",
            "--content",
            "{}",
            "--output-format",
            "json",
        )
        run_cli(
            "task",
            "create",
            "Audit Active Task",
            "--project",
            "Audit Project fixture-seed",
            "--format",
            "json",
        )

        run_cli("project", "create", "Completed Parent Project", "--format", "json")
        completed_goal_payload = json.loads(
            run_cli(
                "goal",
                "create",
                "Completed Parent Goal",
                "--project",
                "Completed Parent Project",
                "--format",
                "json",
            )
        )
        completed_goal_id = completed_goal_payload["goal"]["id"]
        completed_objective_payload = json.loads(
            run_cli(
                "objective",
                "create",
                "Completed Parent Objective",
                "--goal-id",
                completed_goal_id,
                "--format",
                "json",
            )
        )
        completed_objective_id = completed_objective_payload["objective"]["id"]
        completed_key_result_id = extract_id(
            run_cli(
                "keyresult",
                "create",
                "Completed Parent KR",
                "--objective-id",
                completed_objective_id,
            )
        )
        run_cli("project", "complete", "Completed Parent Project")

        report = run_fixture_cleanup_report(data_dir / "pms.db")
        assert report["summary"]["fixture_project_count"] == 1
        assert report["summary"]["orphan_active_objective_count"] == 1
        assert report["summary"]["orphan_active_key_result_count"] == 1
        assert report["summary"]["recommended_action"] == "apply_cleanup"
        assert completed_key_result_id

    def test_fixture_cleanup_apply_normalizes_fixture_and_orphan_state(
        self, tmp_path
    ) -> None:
        """Fixture cleanup should archive/cancel residue and close orphan lifecycle gaps."""
        data_dir = tmp_path / "fixture-cleanup-apply"
        env = os.environ.copy()
        env["PMS_DATA_DIR"] = str(data_dir)
        env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
        env["PMS_LOG_DIR"] = str(data_dir / "logs")
        env["PMS_ENV_FILE"] = str(data_dir / ".env")
        env["PMS_WRITE_MODE"] = "direct"
        env["PMS_CLI_ARGV0"] = "uv run pms"
        env.pop("PMS_SERVER_BASE_URL", None)
        env.pop("PMS_API_KEY", None)
        env.pop("PMS_API_KEY_PATH", None)

        def run_cli(*args: str) -> str:
            result = subprocess.run(
                ["uv", "run", "pms", *args],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            return result.stdout

        def extract_id(output: str) -> str:
            for line in output.splitlines():
                stripped = line.strip()
                if stripped.startswith("ID:"):
                    return stripped.split("ID:", 1)[1].strip()
            raise AssertionError(f"unable to extract ID from output:\n{output}")

        run_cli("init")

        run_cli("project", "create", "Audit Project cleanup-apply", "--format", "json")
        fixture_goal = json.loads(
            run_cli(
                "goal",
                "create",
                "Fixture Goal",
                "--project",
                "Audit Project cleanup-apply",
                "--format",
                "json",
            )
        )
        fixture_goal_id = fixture_goal["goal"]["id"]
        fixture_objective = json.loads(
            run_cli(
                "objective",
                "create",
                "Fixture Objective",
                "--goal-id",
                fixture_goal_id,
                "--format",
                "json",
            )
        )
        fixture_objective_id = fixture_objective["objective"]["id"]
        fixture_key_result_id = extract_id(
            run_cli(
                "keyresult",
                "create",
                "Fixture KR",
                "--objective-id",
                fixture_objective_id,
            )
        )
        run_cli(
            "plan",
            "create",
            "Fixture Plan",
            "--project",
            "Audit Project cleanup-apply",
            "--status",
            "active",
            "--content",
            "{}",
            "--output-format",
            "json",
        )
        run_cli(
            "task",
            "create",
            "Fixture Task",
            "--project",
            "Audit Project cleanup-apply",
            "--format",
            "json",
        )

        run_cli("project", "create", "Archived Parent Project", "--format", "json")
        run_cli(
            "task",
            "create",
            "Archived Parent Open Task",
            "--project",
            "Archived Parent Project",
            "--format",
            "json",
        )
        run_cli("project", "delete", "Archived Parent Project")

        run_cli("project", "create", "Completed Parent Project", "--format", "json")
        completed_goal = json.loads(
            run_cli(
                "goal",
                "create",
                "Completed Parent Goal",
                "--project",
                "Completed Parent Project",
                "--format",
                "json",
            )
        )
        completed_goal_id = completed_goal["goal"]["id"]
        completed_objective = json.loads(
            run_cli(
                "objective",
                "create",
                "Completed Parent Objective",
                "--goal-id",
                completed_goal_id,
                "--format",
                "json",
            )
        )
        completed_objective_id = completed_objective["objective"]["id"]
        completed_key_result_id = extract_id(
            run_cli(
                "keyresult",
                "create",
                "Completed Parent KR",
                "--objective-id",
                completed_objective_id,
            )
        )
        run_cli("project", "complete", "Completed Parent Project")

        result = run_fixture_cleanup(data_dir / "pms.db")
        assert result["actions"]["fixture_projects_archived"] == 1
        assert result["actions"]["fixture_tasks_cancelled"] == 1
        assert result["actions"]["fixture_goals_archived"] == 1
        assert result["actions"]["fixture_objectives_archived"] == 1
        assert result["actions"]["fixture_key_results_archived"] == 1
        assert result["actions"]["fixture_plans_archived"] == 1
        assert result["actions"]["orphan_tasks_cancelled"] == 1
        assert result["actions"]["orphan_objectives_completed"] == 1
        assert result["actions"]["orphan_key_results_completed"] == 1
        assert result["after"]["active_projects"] == 0
        assert result["after"]["active_goals"] == 0
        assert result["after"]["orphan_active_objective_count"] == 0
        assert result["after"]["orphan_active_key_result_count"] == 0
        assert result["after"]["orphan_open_task_count"] == 0

        with sqlite3.connect(data_dir / "pms.db") as conn:
            fixture_status = conn.execute(
                "SELECT status FROM projects WHERE name = ?",
                ("Audit Project cleanup-apply",),
            ).fetchone()
            fixture_key_result_status = conn.execute(
                "SELECT status FROM key_results WHERE id = ?",
                (fixture_key_result_id,),
            ).fetchone()
            objective_status = conn.execute(
                "SELECT status FROM objectives WHERE id = ?",
                (completed_objective_id,),
            ).fetchone()
            key_result_status = conn.execute(
                "SELECT status FROM key_results WHERE id = ?",
                (completed_key_result_id,),
            ).fetchone()

        assert fixture_status == ("archived",)
        assert fixture_key_result_status == ("archived",)
        assert objective_status == ("completed",)
        assert key_result_status == ("completed",)

    def test_cli_api_contract_parity_audit_reads_latest_artifact(
        self, tmp_path
    ) -> None:
        """Captured parity artifacts should be machine-auditable."""
        artifact = tmp_path / "latest.json"
        artifact.write_text('{"surfaces": []}', encoding="utf-8")

        issues = run_cli_api_contract_parity_audit(artifact_path=artifact)
        assert issues == ()

    def test_rust_parity_fixture_script_selects_startable_task_in_isolated_env(
        self, tmp_path
    ) -> None:
        """Rust parity fixture setup should produce a valid startable task in isolated state."""
        env = os.environ.copy()
        data_dir = tmp_path / "rust-parity-fixture"
        env["PMS_DATA_DIR"] = str(data_dir)
        env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
        env["PMS_LOG_DIR"] = str(data_dir / "logs")
        env["PMS_ENV_FILE"] = str(data_dir / ".env")
        env["PMS_WRITE_MODE"] = "direct"
        env["PMS_CLI_ARGV0"] = "uv run pms"
        env.pop("PMS_SERVER_BASE_URL", None)
        env.pop("PMS_API_KEY", None)
        env.pop("PMS_API_KEY_PATH", None)

        fixture_env = tmp_path / "fixture.env"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/setup_rust_client_parity_fixture.py",
                "--output-env",
                str(fixture_env),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        contents = fixture_env.read_text(encoding="utf-8").splitlines()
        values = dict(line.split("=", 1) for line in contents if line and "=" in line)
        assert values["PROJECT_ID"]
        assert values["PLAN_ID"]
        assert values["FIRST_TASK_ID"]
        assert values["STARTABLE_TASK_ID"]

    def test_rust_parity_fixture_script_creates_fallback_task_when_workspace_is_exhausted(
        self, tmp_path
    ) -> None:
        """Rust parity fixture setup should stay usable after repeated runs exhaust quickstart tasks."""
        env = os.environ.copy()
        data_dir = tmp_path / "rust-parity-reused"
        env["PMS_DATA_DIR"] = str(data_dir)
        env["PMS_DATABASE_PATH"] = str(data_dir / "pms.db")
        env["PMS_LOG_DIR"] = str(data_dir / "logs")
        env["PMS_ENV_FILE"] = str(data_dir / ".env")
        env["PMS_WRITE_MODE"] = "direct"
        env["PMS_CLI_ARGV0"] = "uv run pms"
        env.pop("PMS_SERVER_BASE_URL", None)
        env.pop("PMS_API_KEY", None)
        env.pop("PMS_API_KEY_PATH", None)

        quickstart = subprocess.run(
            ["uv", "run", "pms", "quickstart", "--defaults", "--format", "json"],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert quickstart.returncode == 0, quickstart.stdout + quickstart.stderr
        quickstart_payload = json.loads(quickstart.stdout)
        project_id = quickstart_payload["artifacts_created"]["project"]["id"]

        task_list = subprocess.run(
            [
                "uv",
                "run",
                "pms",
                "task",
                "list",
                "--project",
                project_id,
                "--format",
                "json",
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert task_list.returncode == 0, task_list.stdout + task_list.stderr
        task_payload = json.loads(task_list.stdout)
        for item in task_payload["items"]:
            task_id = item["id"]
            if item["status"] == "todo":
                start = subprocess.run(
                    ["uv", "run", "pms", "task", "start", task_id, "--by", "pytest"],
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                assert start.returncode == 0, start.stdout + start.stderr
            complete = subprocess.run(
                ["uv", "run", "pms", "task", "complete", task_id, "--by", "pytest"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            assert complete.returncode == 0, complete.stdout + complete.stderr

        fixture_env = tmp_path / "fixture-reused.env"
        result = subprocess.run(
            [
                sys.executable,
                "scripts/setup_rust_client_parity_fixture.py",
                "--output-env",
                str(fixture_env),
            ],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        contents = fixture_env.read_text(encoding="utf-8").splitlines()
        values = dict(line.split("=", 1) for line in contents if line and "=" in line)
        assert values["PROJECT_ID"] == project_id
        assert values["STARTABLE_TASK_ID"]
        assert values["STARTABLE_TASK_ID"] not in {
            item["id"] for item in task_payload["items"]
        }
