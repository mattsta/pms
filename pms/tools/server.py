"""MCP server factory for PMS tools with tool search support.

This module creates MCP servers with support for Claude's Tool Search feature,
which allows deferred loading of tools to reduce context window usage by 85%+.

Tool Search Architecture:
    PMS tools are organized into two groups:
    - Core tools (8): Always loaded immediately for common operations
    - Extended tools: Loaded on-demand via tool search

    When using Claude's API with tool search, configure mcp_toolset like:

    ```python
    tools = [
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search"},
        {
            "type": "mcp_toolset",
            "mcp_server_name": "pms",
            "default_config": {"defer_loading": True},
            "configs": get_core_tools_config()  # Load core tools immediately
        }
    ]
    ```
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Any

from claude_code_sdk import create_sdk_mcp_server

from pms.tools.project_tools import (
    ALL_PROJECT_TOOLS,
    set_services,
)
from pms.tools.remote_tools import (
    ALL_REMOTE_TOOLS,
    set_remote_service,
)

# Optional AWS tools (require boto3)
try:
    from pms.tools.aws_tools import (
        ALL_AWS_TOOLS,
        set_aws_services,
    )

    _AWS_AVAILABLE = True
except ImportError:
    from typing import Any as _Any

    ALL_AWS_TOOLS = []
    _AWS_AVAILABLE = False

    def set_aws_services(*args: _Any, **kwargs: _Any) -> None:  # type: ignore[misc]
        pass


if TYPE_CHECKING:
    pass


# =============================================================================
# Tool Metadata for Tool Search
# =============================================================================

# Core tools that should NEVER be deferred (most frequently used)
_CORE_TOOL_NAMES = {
    "create_project",
    "list_projects",
    "get_project",
    "get_dashboard",
    "create_task",
    "list_tasks",
    "start_task",
    "complete_task",
}


class ServerMode(Enum):
    """Server configuration modes for tool search support."""

    # All tools loaded (no tool search)
    FULL = "full"

    # Only core tools (8 tools, minimal context)
    CORE_ONLY = "core_only"

    # All tools with defer_loading metadata attached
    WITH_DEFER_METADATA = "with_defer_metadata"


def _attach_defer_metadata(tools: list[Any]) -> list[Any]:
    """Attach defer_loading metadata to tools based on core/extended classification."""
    for tool in tools:
        # Core tools should NOT be deferred
        tool.defer_loading = tool.name not in _CORE_TOOL_NAMES
    return tools


def _filter_core_tools(tools: list[Any]) -> list[Any]:
    """Filter to only include core tools."""
    return [t for t in tools if t.name in _CORE_TOOL_NAMES]


# =============================================================================
# Server Factory Functions
# =============================================================================


def create_pms_server(
    project_service: Any,
    task_service: Any,
    goal_service: Any | None = None,
    plan_service: Any | None = None,
    plan_test_job_service: Any | None = None,
    organization_service: Any | None = None,
    team_service: Any | None = None,
    portfolio_service: Any | None = None,
    program_service: Any | None = None,
    test_run_service: Any | None = None,
    test_run_retention_service: Any | None = None,
    saved_search_service: Any | None = None,
    queue_service: Any | None = None,
    work_snapshot_service: Any | None = None,
    custom_field_service: Any | None = None,
    comment_service: Any | None = None,
    automation_rule_service: Any | None = None,
    remote_service: Any | None = None,
    spot_finder: Any | None = None,
    fleet_manager: Any | None = None,
    test_runner: Any | None = None,
    name: str = "pms",
    version: str = "1.0.0",
    mode: ServerMode = ServerMode.WITH_DEFER_METADATA,
) -> Any:
    """
    Create an MCP server with PMS tools.

    This factory creates a unified MCP server that combines all PMS tool modules:
    - Project tools: Task and project management
    - Remote tools: SSH and rsync operations (optional)
    - AWS tools: Spot instances and test servers (optional, requires boto3)

    Tool Search Support:
        By default (mode=WITH_DEFER_METADATA), tools are tagged with defer_loading
        metadata. Core tools (8) are marked as defer_loading=False, while extended
        tools (all other project/remote/AWS tools) are marked as defer_loading=True.

        When using Claude's API with tool search:
        1. Add tool_search_tool to your tools list
        2. Configure mcp_toolset with default_config.defer_loading=True
        3. Override core tools with defer_loading=False using get_core_tools_config()

    Args:
        project_service: Initialized ProjectService instance
        task_service: Initialized TaskService instance
        goal_service: Optional GoalService for goal tools
        plan_service: Optional PlanService for plan tools
        plan_test_job_service: Optional PlanTestJobService for plan test jobs
        organization_service: Optional OrganizationService for org tools
        team_service: Optional TeamService for team tools
        portfolio_service: Optional PortfolioService for portfolio tools
        program_service: Optional ProgramService for program tools
        remote_service: Optional RemoteService for SSH/rsync tools
        spot_finder: Optional SpotFinder for AWS spot instance discovery
        fleet_manager: Optional FleetManager for test server management
        test_runner: Optional TestRunner for remote test execution
        test_run_retention_service: Optional TestRunRetentionService for pruning
        saved_search_service: Optional SavedSearchService for saved queues
        queue_service: Optional QueueService for smart queues
    work_snapshot_service: Optional WorkSnapshotService for snapshots
    custom_field_service: Optional CustomFieldService for custom fields
    comment_service: Optional CommentService for comments/watchers
    automation_rule_service: Optional AutomationRuleService for automation rules
    name: Server name for MCP registration
        version: Server version
        mode: Server configuration mode (FULL, CORE_ONLY, or WITH_DEFER_METADATA)

    Returns:
        An MCP server config dict ready for use with ClaudeCodeOptions
    """
    # Initialize project tools (always available)
    set_services(
        project_service,
        task_service,
        goal_service,
        plan_service,
        plan_test_job_service,
        organization_service,
        team_service,
        portfolio_service,
        program_service,
        test_run_service,
        test_run_retention_service,
        saved_search_service,
        queue_service,
        work_snapshot_service,
        custom_field_service,
        comment_service,
        automation_rule_service,
    )

    # Build tool list starting with project tools
    all_tools = list(ALL_PROJECT_TOOLS)

    # Initialize remote tools if service provided
    if remote_service is not None:
        set_remote_service(remote_service)
        all_tools.extend(ALL_REMOTE_TOOLS)

    # Initialize AWS tools if services provided and boto3 available
    if _AWS_AVAILABLE and any([spot_finder, fleet_manager, test_runner]):
        set_aws_services(
            spot_finder=spot_finder,
            fleet_manager=fleet_manager,
            test_runner=test_runner,
        )
        all_tools.extend(ALL_AWS_TOOLS)

    # Apply mode-specific filtering/tagging
    match mode:
        case ServerMode.CORE_ONLY:
            all_tools = _filter_core_tools(all_tools)
        case ServerMode.WITH_DEFER_METADATA:
            all_tools = _attach_defer_metadata(all_tools)
        case _:
            pass

    # Create and return MCP server
    return create_sdk_mcp_server(
        name=name,
        version=version,
        tools=all_tools,
    )


def create_core_pms_server(
    project_service: Any,
    task_service: Any,
    name: str = "pms",
    version: str = "1.0.0",
) -> Any:
    """
    Create an MCP server with only core PMS tools.

    This is a lightweight server with only the 8 most essential tools:
    - create_project, list_projects, get_project, get_dashboard
    - create_task, list_tasks, start_task, complete_task

    Use this when you want minimal context usage and don't need remote/AWS tools.

    Args:
        project_service: Initialized ProjectService instance
        task_service: Initialized TaskService instance
        name: Server name for MCP registration
        version: Server version

    Returns:
        An MCP server config dict with only core tools
    """
    return create_pms_server(
        project_service=project_service,
        task_service=task_service,
        name=name,
        version=version,
        mode=ServerMode.CORE_ONLY,
    )


# =============================================================================
# Tool Search Configuration Helpers
# =============================================================================


def get_core_tools_config() -> dict[str, dict[str, bool]]:
    """
    Get mcp_toolset configs to keep core tools loaded (not deferred).

    Use this when configuring Claude API with tool search:

    ```python
    tools = [
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search"},
        {
            "type": "mcp_toolset",
            "mcp_server_name": "pms",
            "default_config": {"defer_loading": True},
            "configs": get_core_tools_config()
        }
    ]
    ```

    Returns:
        Dict mapping tool names to {"defer_loading": False}
    """
    return {name: {"defer_loading": False} for name in _CORE_TOOL_NAMES}


def get_defer_config_for_categories(
    include_remote: bool = False,
    include_aws: bool = False,
) -> dict[str, dict[str, bool]]:
    """
    Get mcp_toolset configs for specific tool categories.

    Args:
        include_remote: If True, remote tools won't be deferred
        include_aws: If True, AWS tools won't be deferred

    Returns:
        Dict mapping tool names to {"defer_loading": False}
    """
    config = get_core_tools_config()

    if include_remote:
        remote_names = {
            "list_remote_hosts",
            "get_remote_host",
            "test_remote_connection",
            "execute_remote_command",
            "sync_push",
            "sync_pull",
        }
        config.update({name: {"defer_loading": False} for name in remote_names})

    if include_aws:
        aws_names = {
            "find_spot_instances",
            "launch_test_server",
            "list_test_servers",
            "get_test_server",
            "terminate_test_server",
            "terminate_all_servers",
            "run_tests_on_server",
            "sync_to_server",
            "exec_on_server",
        }
        config.update({name: {"defer_loading": False} for name in aws_names})

    return config


def get_tool_search_tools_config(server_name: str = "pms") -> list[dict[str, Any]]:
    """
    Get complete tool search configuration for Claude API.

    Returns a tools list ready to use with Claude's Messages API:

    ```python
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model="claude-sonnet-4-5-20250929",
        betas=["advanced-tool-use-2025-11-20", "mcp-client-2025-11-20"],
        max_tokens=2048,
        mcp_servers=[{"type": "url", "name": "pms", "url": "..."}],
        tools=get_tool_search_tools_config("pms"),
        messages=[...]
    )
    ```

    Args:
        server_name: Name of the PMS MCP server

    Returns:
        List of tool definitions including tool_search_tool and mcp_toolset config
    """
    return [
        # Tool search tool for discovering PMS tools
        {
            "type": "tool_search_tool_regex_20251119",
            "name": "tool_search_tool_regex",
        },
        # PMS toolset with defer_loading configured
        {
            "type": "mcp_toolset",
            "mcp_server_name": server_name,
            "default_config": {"defer_loading": True},
            "configs": get_core_tools_config(),
        },
    ]


# Tool name constants for allowed_tools configuration
# Organized by module for clarity

# Project, goal, and task management tools (always available)
PROJECT_TOOL_NAMES = [
    "mcp__pms__create_actor",
    "mcp__pms__list_actors",
    "mcp__pms__get_actor",
    "mcp__pms__add_actor_alias",
    "mcp__pms__add_actor_membership",
    "mcp__pms__create_project",
    "mcp__pms__list_projects",
    "mcp__pms__get_project",
    "mcp__pms__get_project_summary",
    "mcp__pms__archive_project",
    "mcp__pms__update_project",
    "mcp__pms__delete_project",
    "mcp__pms__get_dashboard",
    "mcp__pms__get_work_snapshot",
    "mcp__pms__mark_work_snapshot_reviewed",
    "mcp__pms__get_work_daily",
    "mcp__pms__create_organization",
    "mcp__pms__list_organizations",
    "mcp__pms__get_organization",
    "mcp__pms__update_organization",
    "mcp__pms__get_organization_summary",
    "mcp__pms__get_organization_dashboard",
    "mcp__pms__create_team",
    "mcp__pms__list_teams",
    "mcp__pms__get_team",
    "mcp__pms__update_team",
    "mcp__pms__create_portfolio",
    "mcp__pms__list_portfolios",
    "mcp__pms__get_portfolio",
    "mcp__pms__update_portfolio",
    "mcp__pms__get_portfolio_summary",
    "mcp__pms__get_portfolio_dashboard",
    "mcp__pms__create_program",
    "mcp__pms__list_programs",
    "mcp__pms__get_program",
    "mcp__pms__update_program",
    "mcp__pms__get_program_summary",
    "mcp__pms__get_program_dashboard",
    "mcp__pms__create_goal",
    "mcp__pms__list_goals",
    "mcp__pms__get_goal",
    "mcp__pms__get_goal_summary",
    "mcp__pms__update_goal",
    "mcp__pms__complete_goal",
    "mcp__pms__archive_goal",
    "mcp__pms__create_objective",
    "mcp__pms__list_objectives",
    "mcp__pms__get_objective",
    "mcp__pms__update_objective",
    "mcp__pms__complete_objective",
    "mcp__pms__archive_objective",
    "mcp__pms__create_key_result",
    "mcp__pms__list_key_results",
    "mcp__pms__get_key_result",
    "mcp__pms__update_key_result",
    "mcp__pms__complete_key_result",
    "mcp__pms__archive_key_result",
    "mcp__pms__create_plan",
    "mcp__pms__list_plans",
    "mcp__pms__get_plan",
    "mcp__pms__update_plan",
    "mcp__pms__create_plan_test_job",
    "mcp__pms__list_plan_test_jobs",
    "mcp__pms__get_plan_test_job",
    "mcp__pms__update_plan_test_job",
    "mcp__pms__delete_plan_test_job",
    "mcp__pms__run_plan_test_job",
    "mcp__pms__create_task",
    "mcp__pms__list_tasks",
    "mcp__pms__start_task",
    "mcp__pms__complete_task",
    "mcp__pms__update_task_progress",
    "mcp__pms__update_task",
    "mcp__pms__add_task_evidence",
    "mcp__pms__checkout_task",
    "mcp__pms__renew_task_checkout",
    "mcp__pms__release_task_checkout",
    "mcp__pms__assign_workflow",
    "mcp__pms__transition_workflow",
    "mcp__pms__delete_task",
    "mcp__pms__block_task",
    "mcp__pms__unblock_task",
    "mcp__pms__add_task_dependency",
    "mcp__pms__get_task_tree",
    "mcp__pms__get_blocked_tasks",
    "mcp__pms__search_tasks",
    "mcp__pms__create_saved_search",
    "mcp__pms__list_saved_searches",
    "mcp__pms__get_saved_search",
    "mcp__pms__update_saved_search",
    "mcp__pms__delete_saved_search",
    "mcp__pms__run_saved_search",
    "mcp__pms__list_queue_presets",
    "mcp__pms__get_queue_preset",
    "mcp__pms__find_duplicate_tasks",
    "mcp__pms__preview_merge_duplicate_tasks",
    "mcp__pms__merge_duplicate_tasks",
    "mcp__pms__get_task_proof_bundle",
    "mcp__pms__create_custom_field",
    "mcp__pms__list_custom_fields",
    "mcp__pms__get_custom_field",
    "mcp__pms__update_custom_field",
    "mcp__pms__delete_custom_field",
    "mcp__pms__restore_custom_field",
    "mcp__pms__set_custom_field_value",
    "mcp__pms__list_custom_field_values",
    "mcp__pms__list_custom_field_values_for_field",
    "mcp__pms__add_comment",
    "mcp__pms__list_comments",
    "mcp__pms__get_comment",
    "mcp__pms__delete_comment",
    "mcp__pms__restore_comment",
    "mcp__pms__add_watcher",
    "mcp__pms__list_watchers",
    "mcp__pms__remove_watcher",
    "mcp__pms__restore_watcher",
    "mcp__pms__create_automation_rule",
    "mcp__pms__list_automation_rules",
    "mcp__pms__get_automation_rule",
    "mcp__pms__update_automation_rule",
    "mcp__pms__delete_automation_rule",
    "mcp__pms__restore_automation_rule",
    "mcp__pms__run_automation_rules",
    "mcp__pms__list_automation_rule_runs",
    "mcp__pms__create_evidence_gate_rule",
    "mcp__pms__list_evidence_gate_rules",
    "mcp__pms__delete_evidence_gate_rule",
    "mcp__pms__create_test_run",
    "mcp__pms__list_test_runs",
    "mcp__pms__get_test_run",
    "mcp__pms__prune_test_runs",
    "mcp__pms__get_test_run_retention",
    "mcp__pms__list_ready_tasks",
    "mcp__pms__list_stale_tasks",
    "mcp__pms__bulk_create_tasks",
]

# Remote SSH/rsync tools (require RemoteService)
REMOTE_TOOL_NAMES = [
    "mcp__pms__list_remote_hosts",
    "mcp__pms__get_remote_host",
    "mcp__pms__test_remote_connection",
    "mcp__pms__execute_remote_command",
    "mcp__pms__sync_push",
    "mcp__pms__sync_pull",
]

# AWS spot instance and test server tools (require boto3 and AWS services)
AWS_TOOL_NAMES = [
    "mcp__pms__find_spot_instances",
    "mcp__pms__launch_test_server",
    "mcp__pms__list_test_servers",
    "mcp__pms__get_test_server",
    "mcp__pms__terminate_test_server",
    "mcp__pms__terminate_all_servers",
    "mcp__pms__run_tests_on_server",
    "mcp__pms__sync_to_server",
    "mcp__pms__exec_on_server",
]

# Combined list of all tool names
PMS_TOOL_NAMES = PROJECT_TOOL_NAMES + REMOTE_TOOL_NAMES + AWS_TOOL_NAMES
