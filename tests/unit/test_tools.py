"""Unit tests for PMS agent tools."""

from pms.tools import (
    ALL_AWS_TOOLS,
    ALL_PROJECT_TOOLS,
    ALL_REMOTE_TOOLS,
    AWS_TOOL_NAMES,
    PMS_TOOL_NAMES,
    PROJECT_TOOL_NAMES,
    REMOTE_TOOL_NAMES,
)


class TestProjectTools:
    """Tests for project management tools."""

    def test_all_project_tools_defined(self):
        """Test that all expected project tools are defined."""
        assert (
            len(ALL_PROJECT_TOOLS) == 135
        )  # Includes actors plus orgs/teams/portfolios/programs/queues/custom fields/automation
        assert len(PROJECT_TOOL_NAMES) == 135

    def test_project_tool_names_match(self):
        """Test that project tool names match the MCP naming convention."""
        for name in PROJECT_TOOL_NAMES:
            assert name.startswith("mcp__pms__")

    def test_expected_project_tools_present(self):
        """Test that expected project tools are present."""
        expected_tools = [
            "create_actor",
            "list_actors",
            "get_actor",
            "add_actor_alias",
            "add_actor_membership",
            "create_project",
            "list_projects",
            "get_project",
            "get_project_summary",
            "archive_project",
            "update_project",
            "delete_project",
            "get_dashboard",
            "get_work_snapshot",
            "mark_work_snapshot_reviewed",
            "get_work_daily",
            "create_organization",
            "list_organizations",
            "get_organization",
            "update_organization",
            "get_organization_summary",
            "get_organization_dashboard",
            "create_team",
            "list_teams",
            "get_team",
            "update_team",
            "create_portfolio",
            "list_portfolios",
            "get_portfolio",
            "update_portfolio",
            "get_portfolio_summary",
            "get_portfolio_dashboard",
            "create_program",
            "list_programs",
            "get_program",
            "update_program",
            "get_program_summary",
            "get_program_dashboard",
            "create_goal",
            "list_goals",
            "get_goal",
            "get_goal_summary",
            "update_goal",
            "complete_goal",
            "archive_goal",
            "create_objective",
            "list_objectives",
            "get_objective",
            "update_objective",
            "complete_objective",
            "archive_objective",
            "create_key_result",
            "list_key_results",
            "get_key_result",
            "update_key_result",
            "complete_key_result",
            "archive_key_result",
            "create_plan",
            "list_plans",
            "get_plan",
            "update_plan",
            "create_plan_test_job",
            "list_plan_test_jobs",
            "get_plan_test_job",
            "update_plan_test_job",
            "delete_plan_test_job",
            "run_plan_test_job",
            "create_task",
            "list_tasks",
            "search_tasks",
            "create_saved_search",
            "list_saved_searches",
            "get_saved_search",
            "update_saved_search",
            "delete_saved_search",
            "run_saved_search",
            "list_queue_presets",
            "get_queue_preset",
            "find_duplicate_tasks",
            "preview_merge_duplicate_tasks",
            "merge_duplicate_tasks",
            "get_task_proof_bundle",
            "create_custom_field",
            "list_custom_fields",
            "get_custom_field",
            "update_custom_field",
            "delete_custom_field",
            "restore_custom_field",
            "set_custom_field_value",
            "list_custom_field_values",
            "list_custom_field_values_for_field",
            "add_comment",
            "list_comments",
            "get_comment",
            "delete_comment",
            "restore_comment",
            "add_watcher",
            "list_watchers",
            "remove_watcher",
            "restore_watcher",
            "create_automation_rule",
            "list_automation_rules",
            "get_automation_rule",
            "update_automation_rule",
            "delete_automation_rule",
            "restore_automation_rule",
            "run_automation_rules",
            "list_automation_rule_runs",
            "update_task_progress",
            "add_task_evidence",
            "checkout_task",
            "renew_task_checkout",
            "release_task_checkout",
            "assign_workflow",
            "transition_workflow",
            "create_evidence_gate_rule",
            "list_evidence_gate_rules",
            "delete_evidence_gate_rule",
            "list_test_runs",
            "get_test_run",
            "prune_test_runs",
            "get_test_run_retention",
            "create_test_run",
            "list_ready_tasks",
            "list_stale_tasks",
            "start_task",
            "complete_task",
            "update_task",
            "delete_task",
            "block_task",
            "unblock_task",
            "add_task_dependency",
            "get_task_tree",
            "get_blocked_tasks",
            "bulk_create_tasks",
        ]

        tool_names_without_prefix = [
            name.replace("mcp__pms__", "") for name in PROJECT_TOOL_NAMES
        ]

        for expected in expected_tools:
            assert expected in tool_names_without_prefix, f"Missing tool: {expected}"

    def test_project_tools_have_handlers(self):
        """Test that all project tools have callable handlers."""
        for tool in ALL_PROJECT_TOOLS:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")


class TestRemoteTools:
    """Tests for remote SSH/rsync tools."""

    def test_all_remote_tools_defined(self):
        """Test that all expected remote tools are defined."""
        assert len(ALL_REMOTE_TOOLS) == 6
        assert len(REMOTE_TOOL_NAMES) == 6

    def test_remote_tool_names_match(self):
        """Test that remote tool names match the MCP naming convention."""
        for name in REMOTE_TOOL_NAMES:
            assert name.startswith("mcp__pms__")

    def test_expected_remote_tools_present(self):
        """Test that expected remote tools are present."""
        expected_tools = [
            "list_remote_hosts",
            "get_remote_host",
            "test_remote_connection",
            "execute_remote_command",
            "sync_push",
            "sync_pull",
        ]

        tool_names_without_prefix = [
            name.replace("mcp__pms__", "") for name in REMOTE_TOOL_NAMES
        ]

        for expected in expected_tools:
            assert expected in tool_names_without_prefix, f"Missing tool: {expected}"

    def test_remote_tools_have_handlers(self):
        """Test that all remote tools have callable handlers."""
        for tool in ALL_REMOTE_TOOLS:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")


class TestAWSTools:
    """Tests for AWS spot instance and test server tools."""

    def test_all_aws_tools_defined(self):
        """Test that all expected AWS tools are defined."""
        assert len(ALL_AWS_TOOLS) == 9
        assert len(AWS_TOOL_NAMES) == 9

    def test_aws_tool_names_match(self):
        """Test that AWS tool names match the MCP naming convention."""
        for name in AWS_TOOL_NAMES:
            assert name.startswith("mcp__pms__")

    def test_expected_aws_tools_present(self):
        """Test that expected AWS tools are present."""
        expected_tools = [
            "find_spot_instances",
            "launch_test_server",
            "list_test_servers",
            "get_test_server",
            "terminate_test_server",
            "terminate_all_servers",
            "run_tests_on_server",
            "sync_to_server",
            "exec_on_server",
        ]

        tool_names_without_prefix = [
            name.replace("mcp__pms__", "") for name in AWS_TOOL_NAMES
        ]

        for expected in expected_tools:
            assert expected in tool_names_without_prefix, f"Missing tool: {expected}"

    def test_aws_tools_have_handlers(self):
        """Test that all AWS tools have callable handlers."""
        for tool in ALL_AWS_TOOLS:
            assert hasattr(tool, "handler")
            assert callable(tool.handler)
            assert hasattr(tool, "name")
            assert hasattr(tool, "description")


class TestCombinedTools:
    """Tests for combined tool exports."""

    def test_total_tool_count(self):
        """Test that PMS_TOOL_NAMES contains all tools."""
        expected_total = (
            len(PROJECT_TOOL_NAMES) + len(REMOTE_TOOL_NAMES) + len(AWS_TOOL_NAMES)
        )
        assert len(PMS_TOOL_NAMES) == expected_total
        assert len(PMS_TOOL_NAMES) == 150  # 135 project + 6 remote + 9 AWS

    def test_all_tool_names_unique(self):
        """Test that all tool names are unique."""
        assert len(PMS_TOOL_NAMES) == len(set(PMS_TOOL_NAMES))

    def test_combined_list_matches_components(self):
        """Test that PMS_TOOL_NAMES is the combination of all tool lists."""
        combined = PROJECT_TOOL_NAMES + REMOTE_TOOL_NAMES + AWS_TOOL_NAMES
        assert combined == PMS_TOOL_NAMES


class TestToolSearchConfig:
    """Tests for tool search configuration helpers."""

    def test_get_core_tools_config(self):
        """Test that core tools config has expected structure."""
        from pms.tools import get_core_tools_config

        config = get_core_tools_config()

        # Should have 8 core tools
        assert len(config) == 8

        # All should have defer_loading=False
        for name, cfg in config.items():
            assert cfg == {"defer_loading": False}
            assert isinstance(name, str)

        # Check expected core tools
        expected_core = {
            "create_project",
            "list_projects",
            "get_project",
            "get_dashboard",
            "create_task",
            "list_tasks",
            "start_task",
            "complete_task",
        }
        assert set(config.keys()) == expected_core

    def test_get_defer_config_for_categories_core_only(self):
        """Test defer config with only core tools."""
        from pms.tools import get_defer_config_for_categories

        config = get_defer_config_for_categories()
        assert len(config) == 8  # Only core tools

    def test_get_defer_config_for_categories_with_remote(self):
        """Test defer config including remote tools."""
        from pms.tools import get_defer_config_for_categories

        config = get_defer_config_for_categories(include_remote=True)
        assert len(config) == 14  # 8 core + 6 remote

    def test_get_defer_config_for_categories_with_aws(self):
        """Test defer config including AWS tools."""
        from pms.tools import get_defer_config_for_categories

        config = get_defer_config_for_categories(include_aws=True)
        assert len(config) == 17  # 8 core + 9 AWS

    def test_get_defer_config_for_categories_full(self):
        """Test defer config with all categories."""
        from pms.tools import get_defer_config_for_categories

        config = get_defer_config_for_categories(include_remote=True, include_aws=True)
        assert len(config) == 23  # 8 core + 6 remote + 9 AWS

    def test_get_tool_search_tools_config(self):
        """Test complete tool search API config."""
        from pms.tools import get_tool_search_tools_config

        config = get_tool_search_tools_config("pms")

        assert len(config) == 2

        # First should be tool search tool
        assert config[0]["type"] == "tool_search_tool_regex_20251119"
        assert config[0]["name"] == "tool_search_tool_regex"

        # Second should be mcp_toolset
        assert config[1]["type"] == "mcp_toolset"
        assert config[1]["mcp_server_name"] == "pms"
        assert config[1]["default_config"] == {"defer_loading": True}
        assert len(config[1]["configs"]) == 8  # Core tools

    def test_server_mode_enum(self):
        """Test ServerMode enum values."""
        from pms.tools import ServerMode

        assert ServerMode.FULL.value == "full"
        assert ServerMode.CORE_ONLY.value == "core_only"
        assert ServerMode.WITH_DEFER_METADATA.value == "with_defer_metadata"
