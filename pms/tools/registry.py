"""Tool registry with metadata for tool search and deferred loading.

This module provides a registry of all PMS tools with metadata to support
Claude's Tool Search feature for efficient context management.

Tool Search allows Claude to dynamically discover tools instead of loading
all definitions upfront, reducing context usage by 85%+ for large tool libraries.

Usage with Claude API (defer_loading):
    When using PMS tools via MCP, configure defer_loading at the mcp_toolset level:

    ```python
    tools = [
        {"type": "tool_search_tool_regex_20251119", "name": "tool_search_tool_regex"},
        {
            "type": "mcp_toolset",
            "mcp_server_name": "pms",
            "default_config": {"defer_loading": True},
            "configs": {
                # Keep core tools loaded immediately
                **{name: {"defer_loading": False} for name in CORE_TOOL_NAMES}
            }
        }
    ]
    ```

Usage with Claude Agent SDK:
    The SDK handles tool discovery automatically, but you can still organize
    tools by category for more fine-grained control over which tools are
    available in different contexts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class ToolCategory(Enum):
    """Categories for organizing PMS tools."""

    # Core project management - always useful
    PROJECT = "project"
    TASK = "task"
    GOAL = "goal"
    PLAN = "plan"
    ACTOR = "actor"
    ORGANIZATION = "organization"
    TEAM = "team"
    PORTFOLIO = "portfolio"
    PROGRAM = "program"

    # Remote operations - SSH and file sync
    REMOTE = "remote"

    # AWS cloud operations - spot instances and test servers
    AWS_SPOT = "aws_spot"
    AWS_TEST = "aws_test"


@dataclass(frozen=True)
class ToolMetadata:
    """Metadata for a PMS tool.

    Attributes:
        name: Tool name (without mcp__pms__ prefix)
        mcp_name: Full MCP tool name (mcp__pms__<name>)
        description: Brief description of what the tool does
        category: Tool category for organization
        is_core: Whether this is a core tool that should always be loaded
        search_keywords: Additional keywords for tool search discovery
    """

    name: str
    description: str
    category: ToolCategory
    is_core: bool = False
    search_keywords: tuple[str, ...] = ()

    @property
    def mcp_name(self) -> str:
        """Full MCP tool name."""
        return f"mcp__pms__{self.name}"


# =============================================================================
# Tool Registry - All PMS Tools with Metadata
# =============================================================================

TOOL_REGISTRY: list[ToolMetadata] = [
    # -------------------------------------------------------------------------
    # Actor Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_actor",
        description="Create a canonical actor for humans, personas, teams, or runtime agents",
        category=ToolCategory.ACTOR,
        is_core=False,
        search_keywords=("identity", "persona", "user", "assignee"),
    ),
    ToolMetadata(
        name="list_actors",
        description="List actors, optionally filtered by kind or status",
        category=ToolCategory.ACTOR,
        is_core=False,
        search_keywords=("identity", "persona", "team", "user"),
    ),
    ToolMetadata(
        name="get_actor",
        description="Get actor graph details, workload, and memberships",
        category=ToolCategory.ACTOR,
        is_core=False,
        search_keywords=("identity", "persona", "workload", "memberships"),
    ),
    ToolMetadata(
        name="add_actor_alias",
        description="Add an alias to an existing actor",
        category=ToolCategory.ACTOR,
        is_core=False,
        search_keywords=("identity", "alias", "handle"),
    ),
    ToolMetadata(
        name="add_actor_membership",
        description="Add a membership edge between actors such as persona or team membership",
        category=ToolCategory.ACTOR,
        is_core=False,
        search_keywords=("identity", "membership", "persona", "team"),
    ),
    # -------------------------------------------------------------------------
    # Project Tools (Core)
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_project",
        description="Create a new project with name, description, and tags",
        category=ToolCategory.PROJECT,
        is_core=True,
        search_keywords=("new", "add", "initialize"),
    ),
    ToolMetadata(
        name="list_projects",
        description="List all projects, optionally filtered by status",
        category=ToolCategory.PROJECT,
        is_core=True,
        search_keywords=("show", "all", "filter"),
    ),
    ToolMetadata(
        name="get_project",
        description="Get detailed information about a specific project",
        category=ToolCategory.PROJECT,
        is_core=True,
        search_keywords=("details", "info", "show"),
    ),
    ToolMetadata(
        name="get_project_summary",
        description="Get a summary of project progress and task statistics",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("progress", "stats", "overview"),
    ),
    ToolMetadata(
        name="archive_project",
        description="Archive a completed or inactive project",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("close", "complete", "finish"),
    ),
    ToolMetadata(
        name="update_project",
        description="Update project fields like name, description, tags",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("modify", "edit", "change"),
    ),
    ToolMetadata(
        name="delete_project",
        description="Delete a project and all its tasks",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("remove", "delete", "drop"),
    ),
    ToolMetadata(
        name="get_dashboard",
        description="Get an overview dashboard of all projects and recent activity",
        category=ToolCategory.PROJECT,
        is_core=True,
        search_keywords=("overview", "summary", "status"),
    ),
    ToolMetadata(
        name="get_work_snapshot",
        description="Get a unified work snapshot with digest and retention",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("snapshot", "digest", "review", "rollup"),
    ),
    ToolMetadata(
        name="mark_work_snapshot_reviewed",
        description="Record a review checkpoint for a work snapshot",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("snapshot", "review", "checkpoint"),
    ),
    ToolMetadata(
        name="get_work_daily",
        description="Get a daily review summary with snapshot and queues",
        category=ToolCategory.PROJECT,
        is_core=False,
        search_keywords=("daily", "review", "snapshot", "queues"),
    ),
    # -------------------------------------------------------------------------
    # Goal Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_goal",
        description="Create a new goal with horizon and optional links",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "okr", "planning"),
    ),
    ToolMetadata(
        name="list_goals",
        description="List goals, optionally filtered by status or horizon",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("show", "filter", "roadmap"),
    ),
    ToolMetadata(
        name="get_goal",
        description="Get detailed information about a specific goal",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("details", "info", "show"),
    ),
    ToolMetadata(
        name="get_goal_summary",
        description="Get rollup summary for a goal across objectives and tasks",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("summary", "rollup", "stats"),
    ),
    ToolMetadata(
        name="update_goal",
        description="Update goal fields like status, horizon, progress",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("modify", "edit", "change"),
    ),
    ToolMetadata(
        name="complete_goal",
        description="Mark a goal as completed",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("done", "finish", "close"),
    ),
    ToolMetadata(
        name="archive_goal",
        description="Archive a goal",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("archive", "retire"),
    ),
    ToolMetadata(
        name="create_objective",
        description="Create a new objective under a goal",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "outcome"),
    ),
    ToolMetadata(
        name="list_objectives",
        description="List objectives, optionally filtered by goal or status",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objectives", "filter"),
    ),
    ToolMetadata(
        name="get_objective",
        description="Get detailed information about an objective",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "details"),
    ),
    ToolMetadata(
        name="update_objective",
        description="Update objective fields like status or progress",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "edit"),
    ),
    ToolMetadata(
        name="complete_objective",
        description="Mark an objective as completed",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "done"),
    ),
    ToolMetadata(
        name="archive_objective",
        description="Archive an objective",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("objective", "archive"),
    ),
    ToolMetadata(
        name="create_key_result",
        description="Create a new key result under an objective",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_result", "metric"),
    ),
    ToolMetadata(
        name="list_key_results",
        description="List key results, optionally filtered by objective or status",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_results", "metrics"),
    ),
    ToolMetadata(
        name="get_key_result",
        description="Get detailed information about a key result",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_result", "details"),
    ),
    ToolMetadata(
        name="update_key_result",
        description="Update key result fields like status or progress",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_result", "edit"),
    ),
    ToolMetadata(
        name="complete_key_result",
        description="Mark a key result as completed",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_result", "done"),
    ),
    ToolMetadata(
        name="archive_key_result",
        description="Archive a key result",
        category=ToolCategory.GOAL,
        is_core=False,
        search_keywords=("key_result", "archive"),
    ),
    # -------------------------------------------------------------------------
    # Plan Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_plan",
        description="Create a plan artifact with JSON/YAML content",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "outline", "decompose"),
    ),
    ToolMetadata(
        name="list_plans",
        description="List plans, optionally filtered by status or links",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plans", "status", "filter"),
    ),
    ToolMetadata(
        name="get_plan",
        description="Get plan details by name or ID",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "details"),
    ),
    ToolMetadata(
        name="update_plan",
        description="Update plan fields like status or content",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "edit", "update"),
    ),
    ToolMetadata(
        name="create_plan_test_job",
        description="Create a plan-linked test job definition",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "job"),
    ),
    ToolMetadata(
        name="list_plan_test_jobs",
        description="List test jobs for a plan",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "jobs"),
    ),
    ToolMetadata(
        name="get_plan_test_job",
        description="Get details for a plan test job by ID",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "job", "details"),
    ),
    ToolMetadata(
        name="update_plan_test_job",
        description="Update a plan test job definition",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "job", "update"),
    ),
    ToolMetadata(
        name="delete_plan_test_job",
        description="Delete a plan test job by ID",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "job", "delete"),
    ),
    ToolMetadata(
        name="run_plan_test_job",
        description="Run a plan test job and record the test run",
        category=ToolCategory.PLAN,
        is_core=False,
        search_keywords=("plan", "test", "job", "run"),
    ),
    # -------------------------------------------------------------------------
    # Organization Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_organization",
        description="Create a new organization with members and tags",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("org", "company", "team"),
    ),
    ToolMetadata(
        name="list_organizations",
        description="List organizations, optionally filtered by status",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("orgs", "filter", "list"),
    ),
    ToolMetadata(
        name="get_organization",
        description="Get organization details by name or ID",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("org", "details"),
    ),
    ToolMetadata(
        name="update_organization",
        description="Update organization fields like status or members",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("org", "edit", "update"),
    ),
    ToolMetadata(
        name="get_organization_summary",
        description="Get organization rollup summary and risk signals",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("org", "summary", "rollup"),
    ),
    ToolMetadata(
        name="get_organization_dashboard",
        description="Get organization dashboard rollups with totals across teams and work",
        category=ToolCategory.ORGANIZATION,
        is_core=False,
        search_keywords=("org", "dashboard", "rollup"),
    ),
    # -------------------------------------------------------------------------
    # Team Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_team",
        description="Create a team within an organization",
        category=ToolCategory.TEAM,
        is_core=False,
        search_keywords=("team", "org"),
    ),
    ToolMetadata(
        name="list_teams",
        description="List teams, optionally filtered by org or status",
        category=ToolCategory.TEAM,
        is_core=False,
        search_keywords=("teams", "org"),
    ),
    ToolMetadata(
        name="get_team",
        description="Get team details by name or ID",
        category=ToolCategory.TEAM,
        is_core=False,
        search_keywords=("team", "details"),
    ),
    ToolMetadata(
        name="update_team",
        description="Update team fields like members or status",
        category=ToolCategory.TEAM,
        is_core=False,
        search_keywords=("team", "edit", "update"),
    ),
    # -------------------------------------------------------------------------
    # Portfolio Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_portfolio",
        description="Create a portfolio linking projects and goals",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolio", "roadmap"),
    ),
    ToolMetadata(
        name="list_portfolios",
        description="List portfolios, optionally filtered by org or status",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolios", "org"),
    ),
    ToolMetadata(
        name="get_portfolio",
        description="Get portfolio details by name or ID",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolio", "details"),
    ),
    ToolMetadata(
        name="update_portfolio",
        description="Update portfolio fields like links or status",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolio", "edit", "update"),
    ),
    ToolMetadata(
        name="get_portfolio_summary",
        description="Get portfolio rollup summary and risk signals",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolio", "summary", "rollup"),
    ),
    ToolMetadata(
        name="get_portfolio_dashboard",
        description="Get portfolio dashboard rollups with totals across projects and work",
        category=ToolCategory.PORTFOLIO,
        is_core=False,
        search_keywords=("portfolio", "dashboard", "rollup"),
    ),
    # -------------------------------------------------------------------------
    # Program Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_program",
        description="Create a program linking projects and goals",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("program", "initiative"),
    ),
    ToolMetadata(
        name="list_programs",
        description="List programs, optionally filtered by org or portfolio",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("programs", "portfolio"),
    ),
    ToolMetadata(
        name="get_program",
        description="Get program details by name or ID",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("program", "details"),
    ),
    ToolMetadata(
        name="update_program",
        description="Update program fields like links or status",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("program", "edit", "update"),
    ),
    ToolMetadata(
        name="get_program_summary",
        description="Get program rollup summary and risk signals",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("program", "summary", "rollup"),
    ),
    ToolMetadata(
        name="get_program_dashboard",
        description="Get program dashboard rollups with totals across projects and work",
        category=ToolCategory.PROGRAM,
        is_core=False,
        search_keywords=("program", "dashboard", "rollup"),
    ),
    # -------------------------------------------------------------------------
    # Task Tools (Core)
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="create_task",
        description="Create a new task within a project",
        category=ToolCategory.TASK,
        is_core=True,
        search_keywords=("add", "new", "todo"),
    ),
    ToolMetadata(
        name="list_tasks",
        description="List tasks, optionally filtered by project or status",
        category=ToolCategory.TASK,
        is_core=True,
        search_keywords=("show", "all", "filter"),
    ),
    ToolMetadata(
        name="search_tasks",
        description="Search tasks with rich filters and date ranges",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("search", "find", "query", "filter"),
    ),
    ToolMetadata(
        name="create_saved_search",
        description="Create a saved search queue for tasks",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "search"),
    ),
    ToolMetadata(
        name="list_saved_searches",
        description="List saved search queues",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "list"),
    ),
    ToolMetadata(
        name="get_saved_search",
        description="Get a saved search queue by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "detail"),
    ),
    ToolMetadata(
        name="update_saved_search",
        description="Update a saved search queue",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "update"),
    ),
    ToolMetadata(
        name="delete_saved_search",
        description="Delete a saved search queue",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "delete"),
    ),
    ToolMetadata(
        name="run_saved_search",
        description="Run a saved search queue and list tasks",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "saved", "run"),
    ),
    ToolMetadata(
        name="list_queue_presets",
        description="List smart queue presets (ready/stale/blocked/overdue/at-risk)",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "preset", "ready", "stale"),
    ),
    ToolMetadata(
        name="get_queue_preset",
        description="Get tasks from a smart queue preset",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("queue", "preset", "tasks"),
    ),
    ToolMetadata(
        name="find_duplicate_tasks",
        description="Find duplicate tasks by normalized title",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("duplicates", "dedupe", "merge"),
    ),
    ToolMetadata(
        name="preview_merge_duplicate_tasks",
        description="Preview duplicate task merges with conflicts and warnings",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("duplicates", "preview", "merge"),
    ),
    ToolMetadata(
        name="merge_duplicate_tasks",
        description="Merge duplicate tasks by linking them to a primary task",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("duplicates", "merge", "dedupe"),
    ),
    ToolMetadata(
        name="get_task_proof_bundle",
        description="Get a proof bundle with evidence and test runs for a task",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("proof", "evidence", "bundle", "tests", "artifacts"),
    ),
    ToolMetadata(
        name="create_custom_field",
        description="Create a custom field definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "schema", "metadata"),
    ),
    ToolMetadata(
        name="list_custom_fields",
        description="List custom field definitions",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "metadata", "list"),
    ),
    ToolMetadata(
        name="get_custom_field",
        description="Get details for a custom field definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "details"),
    ),
    ToolMetadata(
        name="update_custom_field",
        description="Update a custom field definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "update"),
    ),
    ToolMetadata(
        name="delete_custom_field",
        description="Archive a custom field definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "delete", "archive"),
    ),
    ToolMetadata(
        name="restore_custom_field",
        description="Restore a custom field definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "restore"),
    ),
    ToolMetadata(
        name="set_custom_field_value",
        description="Set a custom field value for an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "value", "set"),
    ),
    ToolMetadata(
        name="list_custom_field_values",
        description="List custom field values for an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "value", "list"),
    ),
    ToolMetadata(
        name="list_custom_field_values_for_field",
        description="List custom field values for a definition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("custom", "field", "history", "values"),
    ),
    ToolMetadata(
        name="add_comment",
        description="Add a comment to an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("comment", "note", "discussion"),
    ),
    ToolMetadata(
        name="list_comments",
        description="List comments for an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("comment", "list", "discussion"),
    ),
    ToolMetadata(
        name="get_comment",
        description="Get a comment by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("comment", "details"),
    ),
    ToolMetadata(
        name="delete_comment",
        description="Archive a comment by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("comment", "delete", "archive"),
    ),
    ToolMetadata(
        name="restore_comment",
        description="Restore a comment by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("comment", "restore"),
    ),
    ToolMetadata(
        name="add_watcher",
        description="Add a watcher subscription to an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("watcher", "subscribe", "notify"),
    ),
    ToolMetadata(
        name="list_watchers",
        description="List watchers for an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("watcher", "list", "subscribe"),
    ),
    ToolMetadata(
        name="remove_watcher",
        description="Remove a watcher subscription from an entity",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("watcher", "remove", "unsubscribe"),
    ),
    ToolMetadata(
        name="restore_watcher",
        description="Restore a watcher subscription by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("watcher", "restore"),
    ),
    ToolMetadata(
        name="create_automation_rule",
        description="Create an automation rule",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "create"),
    ),
    ToolMetadata(
        name="list_automation_rules",
        description="List automation rules",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "list"),
    ),
    ToolMetadata(
        name="get_automation_rule",
        description="Get details for an automation rule",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "details"),
    ),
    ToolMetadata(
        name="update_automation_rule",
        description="Update an automation rule",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "update"),
    ),
    ToolMetadata(
        name="delete_automation_rule",
        description="Archive an automation rule",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "delete"),
    ),
    ToolMetadata(
        name="restore_automation_rule",
        description="Restore an automation rule",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "rule", "restore"),
    ),
    ToolMetadata(
        name="run_automation_rules",
        description="Run automation rules for an event",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "run", "event"),
    ),
    ToolMetadata(
        name="list_automation_rule_runs",
        description="List automation rule execution history",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("automation", "runs", "history"),
    ),
    ToolMetadata(
        name="update_task_progress",
        description="Update task progress with percent and status message",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("progress", "status", "update"),
    ),
    ToolMetadata(
        name="add_task_evidence",
        description="Attach evidence to a task",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("evidence", "proof", "attach"),
    ),
    ToolMetadata(
        name="checkout_task",
        description="Checkout a task for exclusive work",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("checkout", "lock", "lease"),
    ),
    ToolMetadata(
        name="renew_task_checkout",
        description="Renew a task checkout lease",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("checkout", "renew", "lease"),
    ),
    ToolMetadata(
        name="release_task_checkout",
        description="Release a task checkout lease",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("checkout", "release", "unlock"),
    ),
    ToolMetadata(
        name="assign_workflow",
        description="Assign a workflow to a task, goal, or objective",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("workflow", "assign", "state"),
    ),
    ToolMetadata(
        name="transition_workflow",
        description="Transition workflow state for a task, goal, or objective",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("workflow", "transition", "state"),
    ),
    ToolMetadata(
        name="create_evidence_gate_rule",
        description="Create an evidence gate rule for workflow transitions",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("evidence", "gate", "workflow", "policy"),
    ),
    ToolMetadata(
        name="list_evidence_gate_rules",
        description="List evidence gate rules for a workflow transition",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("evidence", "gate", "workflow", "list"),
    ),
    ToolMetadata(
        name="delete_evidence_gate_rule",
        description="Delete an evidence gate rule by ID",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("evidence", "gate", "workflow", "delete"),
    ),
    ToolMetadata(
        name="create_test_run",
        description="Create a test run record with output, logs, and artifacts",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("tests", "record", "create", "logs", "artifacts"),
    ),
    ToolMetadata(
        name="list_test_runs",
        description="List test runs with optional filters and payloads",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("tests", "runs", "history", "logs"),
    ),
    ToolMetadata(
        name="get_test_run",
        description="Get a test run with output, logs, and artifacts",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("tests", "run", "logs", "artifacts"),
    ),
    ToolMetadata(
        name="prune_test_runs",
        description="Prune stored test run outputs by size or age",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("tests", "prune", "retention", "cleanup"),
    ),
    ToolMetadata(
        name="get_test_run_retention",
        description="Get test run retention usage summary",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("tests", "retention", "usage", "storage", "logs"),
    ),
    ToolMetadata(
        name="list_ready_tasks",
        description="List tasks ready to start (no blocking dependencies)",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("ready", "unblocked", "available"),
    ),
    ToolMetadata(
        name="list_stale_tasks",
        description="List tasks with no recent updates",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("stale", "inactive", "aging"),
    ),
    ToolMetadata(
        name="start_task",
        description="Start working on a task (move to in_progress)",
        category=ToolCategory.TASK,
        is_core=True,
        search_keywords=("begin", "work", "progress"),
    ),
    ToolMetadata(
        name="complete_task",
        description="Mark a task as completed",
        category=ToolCategory.TASK,
        is_core=True,
        search_keywords=("done", "finish", "close"),
    ),
    ToolMetadata(
        name="update_task",
        description="Update task fields like title, description, priority",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("modify", "edit", "change"),
    ),
    ToolMetadata(
        name="delete_task",
        description="Delete a task",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("remove", "cancel", "drop"),
    ),
    ToolMetadata(
        name="block_task",
        description="Mark a task as blocked with a reason",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("blocked", "stuck", "impediment"),
    ),
    ToolMetadata(
        name="unblock_task",
        description="Remove the blocked status from a task",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("unblock", "resume", "continue"),
    ),
    ToolMetadata(
        name="add_task_dependency",
        description="Add a dependency between two tasks",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("depends", "requires", "link"),
    ),
    ToolMetadata(
        name="get_task_tree",
        description="Get the task hierarchy tree for a project",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("hierarchy", "subtasks", "children"),
    ),
    ToolMetadata(
        name="get_blocked_tasks",
        description="Get all blocked tasks across projects",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("blocked", "stuck", "impediments"),
    ),
    ToolMetadata(
        name="bulk_create_tasks",
        description="Create multiple tasks at once",
        category=ToolCategory.TASK,
        is_core=False,
        search_keywords=("batch", "multiple", "many"),
    ),
    # -------------------------------------------------------------------------
    # Remote Tools (SSH/rsync)
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="list_remote_hosts",
        description="List all configured remote SSH hosts",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("ssh", "servers", "hosts"),
    ),
    ToolMetadata(
        name="get_remote_host",
        description="Get details of a specific remote host",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("ssh", "server", "host", "details"),
    ),
    ToolMetadata(
        name="test_remote_connection",
        description="Test SSH connection to a remote host",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("ssh", "ping", "check", "connectivity"),
    ),
    ToolMetadata(
        name="execute_remote_command",
        description="Execute a shell command on a remote host via SSH",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("ssh", "run", "shell", "exec"),
    ),
    ToolMetadata(
        name="sync_push",
        description="Push local files to a remote host using rsync",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("rsync", "upload", "deploy", "copy"),
    ),
    ToolMetadata(
        name="sync_pull",
        description="Pull files from a remote host to local using rsync",
        category=ToolCategory.REMOTE,
        is_core=False,
        search_keywords=("rsync", "download", "fetch", "copy"),
    ),
    # -------------------------------------------------------------------------
    # AWS Spot Instance Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="find_spot_instances",
        description="Find cost-effective AWS spot instances for testing",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "spot", "cheap", "price"),
    ),
    ToolMetadata(
        name="launch_test_server",
        description="Launch an AWS spot instance test server",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "start", "create", "spin"),
    ),
    ToolMetadata(
        name="list_test_servers",
        description="List all active AWS test servers",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "servers", "instances"),
    ),
    ToolMetadata(
        name="get_test_server",
        description="Get details of a specific AWS test server",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "server", "instance", "details"),
    ),
    ToolMetadata(
        name="terminate_test_server",
        description="Terminate a specific AWS test server",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "stop", "kill", "delete"),
    ),
    ToolMetadata(
        name="terminate_all_servers",
        description="Terminate all AWS test servers",
        category=ToolCategory.AWS_SPOT,
        is_core=False,
        search_keywords=("aws", "ec2", "cleanup", "stop", "kill"),
    ),
    # -------------------------------------------------------------------------
    # AWS Test Runner Tools
    # -------------------------------------------------------------------------
    ToolMetadata(
        name="run_tests_on_server",
        description="Sync project to server and run test suite",
        category=ToolCategory.AWS_TEST,
        is_core=False,
        search_keywords=("aws", "test", "pytest", "run", "ci"),
    ),
    ToolMetadata(
        name="sync_to_server",
        description="Sync project files to an AWS test server",
        category=ToolCategory.AWS_TEST,
        is_core=False,
        search_keywords=("aws", "rsync", "upload", "deploy"),
    ),
    ToolMetadata(
        name="exec_on_server",
        description="Execute a command on an AWS test server",
        category=ToolCategory.AWS_TEST,
        is_core=False,
        search_keywords=("aws", "ssh", "run", "exec", "command"),
    ),
]


# =============================================================================
# Derived Tool Name Lists
# =============================================================================


def _get_tools_by_category(category: ToolCategory) -> list[ToolMetadata]:
    """Get all tools in a category."""
    return [t for t in TOOL_REGISTRY if t.category == category]


def _get_core_tools() -> list[ToolMetadata]:
    """Get tools marked as core (should always be loaded)."""
    return [t for t in TOOL_REGISTRY if t.is_core]


def _get_deferred_tools() -> list[ToolMetadata]:
    """Get tools that can be deferred (not core)."""
    return [t for t in TOOL_REGISTRY if not t.is_core]


# Core tool names - these should NOT be deferred for best performance
CORE_TOOL_NAMES: list[str] = [t.mcp_name for t in _get_core_tools()]

# Deferred tool names - these can be discovered via tool search
DEFERRED_TOOL_NAMES: list[str] = [t.mcp_name for t in _get_deferred_tools()]

# Category-based tool name lists
PROJECT_CATEGORY_TOOLS: list[str] = [
    t.mcp_name for t in _get_tools_by_category(ToolCategory.PROJECT)
]
TASK_CATEGORY_TOOLS: list[str] = [
    t.mcp_name for t in _get_tools_by_category(ToolCategory.TASK)
]
REMOTE_CATEGORY_TOOLS: list[str] = [
    t.mcp_name for t in _get_tools_by_category(ToolCategory.REMOTE)
]
AWS_SPOT_CATEGORY_TOOLS: list[str] = [
    t.mcp_name for t in _get_tools_by_category(ToolCategory.AWS_SPOT)
]
AWS_TEST_CATEGORY_TOOLS: list[str] = [
    t.mcp_name for t in _get_tools_by_category(ToolCategory.AWS_TEST)
]


# =============================================================================
# Helper Functions
# =============================================================================


def get_tool_metadata(tool_name: str) -> ToolMetadata | None:
    """Get metadata for a tool by name (with or without mcp__pms__ prefix)."""
    # Normalize the name
    if tool_name.startswith("mcp__pms__"):
        tool_name = tool_name.replace("mcp__pms__", "")

    for tool in TOOL_REGISTRY:
        if tool.name == tool_name:
            return tool
    return None


def search_tools(query: str) -> list[ToolMetadata]:
    """Search tools by name, description, or keywords.

    This is a simple local search. For production use with many tools,
    consider using Claude's built-in tool_search_tool_regex or
    tool_search_tool_bm25.
    """
    query_lower = query.lower()
    results = []

    for tool in TOOL_REGISTRY:
        # Check name
        if query_lower in tool.name.lower():
            results.append(tool)
            continue

        # Check description
        if query_lower in tool.description.lower():
            results.append(tool)
            continue

        # Check keywords
        if any(query_lower in kw.lower() for kw in tool.search_keywords):
            results.append(tool)
            continue

    return results


def get_defer_loading_config(
    always_load: list[str] | None = None,
    categories_to_load: list[ToolCategory] | None = None,
) -> dict[str, dict[str, bool]]:
    """Generate defer_loading configs for MCP toolset configuration.

    This helps configure which tools should be immediately available
    vs discovered via tool search.

    Args:
        always_load: Tool names (without prefix) to always load
        categories_to_load: Tool categories to always load

    Returns:
        A dict suitable for mcp_toolset.configs

    Example:
        config = get_defer_loading_config(
            always_load=["create_project", "create_task"],
            categories_to_load=[ToolCategory.PROJECT]
        )

        # Use in Claude API:
        tools = [{
            "type": "mcp_toolset",
            "mcp_server_name": "pms",
            "default_config": {"defer_loading": True},
            "configs": config
        }]
    """
    configs: dict[str, dict[str, bool]] = {}

    # Add explicitly specified tools
    if always_load:
        for name in always_load:
            tool = get_tool_metadata(name)
            if tool:
                configs[tool.name] = {"defer_loading": False}

    # Add tools from specified categories
    if categories_to_load:
        for category in categories_to_load:
            for tool in _get_tools_by_category(category):
                configs[tool.name] = {"defer_loading": False}

    # Always include core tools
    for tool in _get_core_tools():
        configs[tool.name] = {"defer_loading": False}

    return configs


def get_tools_summary() -> str:
    """Get a human-readable summary of all tools organized by category."""
    lines = ["PMS Tools Summary", "=" * 50]

    for category in ToolCategory:
        tools = _get_tools_by_category(category)
        if not tools:
            continue

        lines.append(f"\n{category.value.upper()} ({len(tools)} tools):")
        for tool in tools:
            core_marker = " [CORE]" if tool.is_core else ""
            lines.append(f"  - {tool.name}{core_marker}: {tool.description}")

    lines.append(f"\nTotal: {len(TOOL_REGISTRY)} tools")
    lines.append(f"Core (always loaded): {len(CORE_TOOL_NAMES)} tools")
    lines.append(f"Deferred (discoverable): {len(DEFERRED_TOOL_NAMES)} tools")

    return "\n".join(lines)
