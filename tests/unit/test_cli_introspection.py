"""Tests for CLI Introspection and Namespace Commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from pms.cli.app import cli


class TestCapabilitiesCommands:
    """Tests for pms capabilities commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_capabilities_info(self, runner):
        """Test capabilities info command."""
        result = runner.invoke(cli, ["capabilities", "info"])
        assert result.exit_code == 0
        assert "PMS - Project Management System" in result.output
        assert "Version:" in result.output
        assert "Total Capabilities:" in result.output
        assert "Capability Summary:" in result.output

    def test_capabilities_info_json(self, runner):
        """Test capabilities info with JSON format."""
        result = runner.invoke(cli, ["capabilities", "info", "--format", "json"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert "version" in data
        assert "total_capabilities" in data
        assert "capabilities" in data
        assert isinstance(data["capabilities"], dict)

    def test_capabilities_list(self, runner):
        """Test capabilities list command."""
        result = runner.invoke(cli, ["capabilities", "list"])
        assert result.exit_code == 0
        # Should show tables for different categories
        assert "Namespaces" in result.output or "Total:" in result.output

    def test_capabilities_list_type_filter(self, runner):
        """Test capabilities list with type filter."""
        result = runner.invoke(cli, ["capabilities", "list", "--type", "namespaces"])
        assert result.exit_code == 0
        # Should show namespace table
        assert "proj" in result.output or "task" in result.output

    def test_capabilities_list_json(self, runner):
        """Test capabilities list with JSON format."""
        result = runner.invoke(
            cli,
            [
                "capabilities",
                "list",
                "--type",
                "namespaces",
                "--view",
                "trace",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert len(data["items"]) > 0
        namespace_item = next(
            item for item in data["items"] if item["raw"]["prefix"] == "proj"
        )
        assert namespace_item["raw"]["namespace_generated_id_format"] == "proj_<uuid>"
        assert (
            namespace_item["raw"]["runtime_row_id_contract_scope"]
            == "public_stored_entity_family"
        )
        assert namespace_item["raw"]["runtime_row_id_style"] == "uuid_native"
        workflow_item = next(
            item for item in data["items"] if item["raw"]["prefix"] == "wf"
        )
        assert (
            workflow_item["raw"]["runtime_row_id_contract_scope"]
            == "internal_or_non_public_namespace"
        )
        assert workflow_item["raw"]["runtime_row_id_style"] is None

    def test_capabilities_schema(self, runner):
        """Test capabilities schema command."""
        result = runner.invoke(cli, ["capabilities", "schema"])
        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert "version" in data or "namespaces" in data
        proj = data["namespaces"]["proj"]
        assert proj["namespace_generated_id_format"] == "proj_<uuid>"
        assert proj["runtime_row_id_contract_scope"] == "public_stored_entity_family"
        assert proj["runtime_row_id_style"] == "uuid_native"
        assert (
            data["namespaces"]["wf"]["runtime_row_id_contract_scope"]
            == "internal_or_non_public_namespace"
        )
        assert data["namespaces"]["wf"]["runtime_row_id_style"] is None

    def test_capabilities_schema_output(self, runner, tmp_path):
        """Test capabilities schema output to file."""
        output_file = tmp_path / "schema.json"
        result = runner.invoke(
            cli, ["capabilities", "schema", "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert isinstance(data, dict)

    def test_capabilities_docs(self, runner):
        """Test capabilities docs command."""
        result = runner.invoke(cli, ["capabilities", "docs"])
        assert result.exit_code == 0
        # Should contain markdown
        assert "PMS" in result.output
        assert "#" in result.output  # Markdown headers
        assert "Namespace Schema Details" in result.output
        assert "effective_goal_ids" in result.output
        assert "Namespace-generated IDs use the typed-ID" in result.output
        assert "Runtime row-ID contract scope" in result.output
        assert "internal_or_non_public_namespace" in result.output

    def test_capabilities_docs_text(self, runner):
        """Test capabilities docs with text format."""
        result = runner.invoke(cli, ["capabilities", "docs", "--format", "text"])
        assert result.exit_code == 0
        assert "PMS" in result.output
        assert "NAMESPACE SCHEMA DETAILS" in result.output
        assert "effective_goal_ids" in result.output
        assert "Runtime row-ID contract scope" in result.output
        assert "Runtime row-ID style: not applicable" in result.output

    def test_capabilities_docs_output(self, runner, tmp_path, monkeypatch):
        """Test capabilities docs output to file."""
        monkeypatch.setattr(
            "pms.utils.markdown_formatting.format_markdown_with_prettier",
            lambda content, *, filepath: f"formatted::{Path(filepath).name}\n{content}",
        )
        output_file = tmp_path / "CAPABILITIES.md"
        result = runner.invoke(
            cli, ["capabilities", "docs", "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert content.startswith("formatted::CAPABILITIES.md\n")
        assert "PMS" in content

    def test_capabilities_health(self, runner):
        """Test capabilities health command."""
        result = runner.invoke(cli, ["capabilities", "health"])
        assert result.exit_code == 0
        assert "Health" in result.output or "healthy" in result.output.lower()

    def test_capabilities_health_json(self, runner):
        """Test capabilities health with JSON format."""
        result = runner.invoke(cli, ["capabilities", "health", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "healthy" in data
        assert "components" in data


class TestNamespaceCommands:
    """Tests for pms namespace commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_namespace_list(self, runner):
        """Test namespace list command."""
        result = runner.invoke(cli, ["namespace", "list"])
        assert result.exit_code == 0
        assert "Namespaces" in result.output
        # Should show some built-in namespaces
        assert "proj" in result.output
        assert "task" in result.output

    def test_namespace_list_builtin(self, runner):
        """Test namespace list with builtin filter."""
        result = runner.invoke(cli, ["namespace", "list", "--builtin"])
        assert result.exit_code == 0
        # Should show only built-in namespaces (which have the checkmark)
        assert "proj" in result.output

    def test_namespace_list_json(self, runner):
        """Test namespace list with JSON format."""
        result = runner.invoke(cli, ["namespace", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "items" in data
        assert len(data["items"]) > 0
        assert "prefix" in data["items"][0]
        assert "name" in data["items"][0]
        project_item = next(item for item in data["items"] if item["prefix"] == "proj")
        assert project_item["namespace_generated_id_format"] == "proj_<uuid>"
        assert (
            project_item["runtime_row_id_contract_scope"]
            == "public_stored_entity_family"
        )
        assert project_item["runtime_row_id_style"] == "uuid_native"

    def test_namespace_show(self, runner):
        """Test namespace show command."""
        result = runner.invoke(cli, ["namespace", "show", "proj"])
        assert result.exit_code == 0
        assert "project" in result.output.lower()
        assert "Prefix:" in result.output
        assert "Built-in:" in result.output
        assert "Namespace-generated ID format:" in result.output
        assert "Runtime row-ID contract scope:" in result.output
        assert "Runtime row-ID style:" in result.output
        assert "Example Namespace ID:" in result.output

    def test_namespace_show_with_schema(self, runner):
        """Test namespace show with schema."""
        result = runner.invoke(cli, ["namespace", "show", "task"])
        assert result.exit_code == 0
        assert "task" in result.output.lower()
        # Should show example ID
        assert "task_" in result.output

    def test_namespace_show_portfolio_schema_describes_effective_scope_fields(
        self, runner
    ):
        """Test namespace show reflects direct/effective portfolio field semantics."""
        result = runner.invoke(cli, ["namespace", "show", "port"])
        assert result.exit_code == 0
        assert "effective_goal_ids" in result.output
        assert "effective_objective_ids" in result.output
        assert "Hydrated scope readback only" in result.output

    def test_namespace_show_api_key(self, runner):
        """Test namespace show for api_key built-in coverage."""
        result = runner.invoke(cli, ["namespace", "show", "apikey"])
        assert result.exit_code == 0
        assert "api_key" in result.output.lower()
        assert "apikey_" in result.output
        assert "Runtime row-ID style: prefix_native" in result.output

    def test_namespace_show_workflow_marks_runtime_contract_not_applicable(
        self, runner
    ):
        """Test namespace show for non-public runtime row-ID families."""
        result = runner.invoke(cli, ["namespace", "show", "wf"])
        assert result.exit_code == 0
        assert (
            "Runtime row-ID contract scope: internal_or_non_public_namespace"
            in result.output
        )
        assert "Runtime row-ID style: not applicable" in result.output

    def test_namespace_show_json_includes_id_contract_metadata(self, runner):
        """Test namespace show JSON export includes ID-contract metadata."""
        result = runner.invoke(cli, ["namespace", "show", "task", "--format", "json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["namespace_generated_id_format"] == "task_<uuid>"
        assert payload["namespace_generated_id_kind"] == "prefix_uuid"
        assert payload["runtime_row_id_contract_scope"] == "public_stored_entity_family"
        assert payload["runtime_row_id_style"] == "uuid_native"

    def test_namespace_show_csv_includes_id_contract_metadata(self, runner):
        """Test namespace show CSV export includes ID-contract metadata."""
        result = runner.invoke(cli, ["namespace", "show", "task", "--format", "csv"])
        assert result.exit_code == 0
        header = result.output.splitlines()[0]
        row = result.output.splitlines()[1]
        assert "namespace_generated_id_format" in header
        assert "runtime_row_id_contract_scope" in header
        assert "runtime_row_id_style" in header
        assert "task_<uuid>" in row
        assert "public_stored_entity_family" in row
        assert "uuid_native" in row

    def test_namespace_show_not_found(self, runner):
        """Test namespace show with non-existent namespace."""
        result = runner.invoke(cli, ["namespace", "show", "nonexistent"])
        assert result.exit_code == 0  # Click doesn't set exit code for app errors
        assert "not found" in result.output.lower()

    def test_namespace_list_csv_includes_id_contract_metadata(self, runner):
        """Test namespace list CSV export includes ID-contract metadata."""
        result = runner.invoke(cli, ["namespace", "list", "--format", "csv"])
        assert result.exit_code == 0
        header = result.output.splitlines()[0]
        first_row = result.output.splitlines()[1]
        assert "namespace_generated_id_format" in header
        assert "runtime_row_id_contract_scope" in header
        assert "runtime_row_id_style" in header
        assert "apikey_<uuid>" in first_row
        assert "public_stored_entity_family" in first_row

    def test_namespace_schema(self, runner):
        """Test namespace schema command."""
        result = runner.invoke(cli, ["namespace", "schema"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data or "namespaces" in data
        proj = data["namespaces"]["proj"]
        assert "id_format" not in proj
        assert proj["namespace_generated_id_format"] == "proj_<uuid>"
        assert proj["runtime_row_id_contract_scope"] == "public_stored_entity_family"
        assert proj["runtime_row_id_style"] == "uuid_native"
        assert (
            data["namespaces"]["wf"]["runtime_row_id_contract_scope"]
            == "internal_or_non_public_namespace"
        )
        assert data["namespaces"]["wf"]["runtime_row_id_style"] is None

    def test_namespace_schema_output(self, runner, tmp_path):
        """Test namespace schema output to file."""
        output_file = tmp_path / "namespaces.json"
        result = runner.invoke(
            cli, ["namespace", "schema", "--output", str(output_file)]
        )
        assert result.exit_code == 0
        assert output_file.exists()
        data = json.loads(output_file.read_text())
        assert isinstance(data, dict)

    def test_namespace_generate_id(self, runner):
        """Test namespace generate-id command."""
        result = runner.invoke(cli, ["namespace", "generate-id", "task"])
        assert result.exit_code == 0
        assert "task_" in result.output
        # Verify UUID format
        output = result.output.strip()
        assert len(output.split("_")[1]) == 36  # UUID length

    def test_namespace_generate_id_multiple(self, runner):
        """Test namespace generate-id with count."""
        result = runner.invoke(
            cli, ["namespace", "generate-id", "proj", "--count", "5"]
        )
        assert result.exit_code == 0
        lines = result.output.strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            assert line.startswith("proj_")

    def test_namespace_generate_id_invalid(self, runner):
        """Test namespace generate-id with invalid namespace."""
        result = runner.invoke(cli, ["namespace", "generate-id", "invalid"])
        assert "Error" in result.output

    def test_namespace_register(self, runner):
        """Test namespace register command."""
        # Use unique prefix to avoid conflicts
        import uuid

        prefix = f"test{uuid.uuid4().hex[:4]}"
        result = runner.invoke(
            cli,
            [
                "namespace",
                "register",
                prefix,
                "test_entity",
                "-d",
                "Test entity type",
            ],
        )
        assert result.exit_code == 0
        assert "Registered namespace" in result.output

    def test_namespace_register_duplicate(self, runner):
        """Test namespace register with existing prefix."""
        result = runner.invoke(
            cli, ["namespace", "register", "proj", "project_override", "-d", "Override"]
        )
        assert result.exit_code == 0
        assert "already exists" in result.output.lower()

    def test_namespace_unregister_builtin(self, runner):
        """Test namespace unregister on built-in."""
        result = runner.invoke(cli, ["namespace", "unregister", "proj", "-y"])
        assert result.exit_code == 0
        assert "cannot unregister" in result.output.lower()


class TestCapabilitiesIntegration:
    """Integration tests for capabilities commands."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_capabilities_info_matches_list(self, runner):
        """Test that info counts match list counts."""
        # Get info
        info_result = runner.invoke(cli, ["capabilities", "info", "--format", "json"])
        info_data = json.loads(info_result.output)

        # Get list of namespaces
        list_result = runner.invoke(
            cli, ["capabilities", "list", "--type", "namespaces", "--format", "json"]
        )
        list_data = json.loads(list_result.output)

        # Count should match
        assert info_data["capabilities"]["namespaces"] == len(list_data["items"])

    def test_namespace_in_namespace_list(self, runner):
        """Test that registered namespace appears in namespace list."""
        import uuid

        prefix = f"int{uuid.uuid4().hex[:4]}"

        # Register a custom namespace
        result = runner.invoke(
            cli,
            [
                "namespace",
                "register",
                prefix,
                "integration_test",
                "-d",
                "Integration test namespace",
            ],
        )
        assert "Registered namespace" in result.output

        # Check it appears in namespace list (uses registry directly, not cached introspector)
        result = runner.invoke(cli, ["namespace", "list", "--format", "json"])
        data = json.loads(result.output)

        # Find our namespace
        found = any(ns.get("prefix") == prefix for ns in data["items"])
        assert found

    def test_health_includes_namespaces(self, runner):
        """Test that health check includes namespace registry."""
        result = runner.invoke(cli, ["capabilities", "health", "--format", "json"])
        data = json.loads(result.output)

        assert "components" in data
        assert "namespace_registry" in data["components"]


class TestCLIHelp:
    """Test CLI help messages."""

    @pytest.fixture
    def runner(self):
        """Create CLI test runner."""
        return CliRunner()

    def test_capabilities_help(self, runner):
        """Test capabilities group help."""
        result = runner.invoke(cli, ["capabilities", "--help"])
        assert result.exit_code == 0
        assert "Discover system capabilities" in result.output
        assert "info" in result.output
        assert "list" in result.output
        assert "schema" in result.output
        assert "docs" in result.output
        assert "health" in result.output

    def test_namespace_help(self, runner):
        """Test namespace group help."""
        result = runner.invoke(cli, ["namespace", "--help"])
        assert result.exit_code == 0
        assert "entity namespaces" in result.output.lower()
        assert "list" in result.output
        assert "show" in result.output
        assert "register" in result.output
        assert "unregister" in result.output
        assert "schema" in result.output
        assert "generate-id" in result.output

    def test_capabilities_list_help(self, runner):
        """Test capabilities list help."""
        result = runner.invoke(cli, ["capabilities", "list", "--help"])
        assert result.exit_code == 0
        assert "--type" in result.output
        assert "--format" in result.output
        assert "namespaces" in result.output
        assert "tools" in result.output

    def test_namespace_register_help(self, runner):
        """Test namespace register help."""
        result = runner.invoke(cli, ["namespace", "register", "--help"])
        assert result.exit_code == 0
        assert "PREFIX" in result.output
        assert "NAME" in result.output
        assert "--description" in result.output
        assert "--module" in result.output
        assert "--schema" in result.output
