"""Coordinator agent for orchestrating PMS operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from claude_code_sdk import (
    AssistantMessage,
    ClaudeCodeOptions,
    ClaudeSDKClient,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from pms.agents.priming import build_system_prompt
from pms.tools.server import PMS_TOOL_NAMES, create_pms_server

if TYPE_CHECKING:
    from pms.memory.priming import ContextPrimer
    from pms.services import (
        GoalService,
        OrganizationService,
        PlanService,
        PlanTestJobService,
        PortfolioService,
        ProgramService,
        ProjectService,
        QueueService,
        SavedSearchService,
        TaskService,
        TeamService,
        TestRunRetentionService,
        TestRunService,
        WorkSnapshotService,
    )


@dataclass
class AgentResult:
    """Result from agent execution."""

    success: bool
    message: str
    tool_calls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


COORDINATOR_SYSTEM_PROMPT = """You are the PMS (Project Management System) coordinator agent.

Your role is to help users manage their projects and tasks effectively.

You have access to the following capabilities:
- Create, list, and manage projects
- Create, list, and manage goals with horizons and progress
- Create, update, and link plan artifacts to projects and goals
- Create, update, and track tasks within projects
- Set task dependencies and priorities
- View project dashboards and summaries
- Track blocked and overdue tasks

When working with the user:
1. Be concise and action-oriented
2. Use the available tools to accomplish tasks
3. Report progress clearly
4. Suggest next steps when appropriate

For complex requests, break them down into manageable steps and execute them in order."""


class CoordinatorAgent:
    """
    Main coordinator agent for PMS operations.

    Orchestrates project and task management through Claude SDK.
    """

    def __init__(
        self,
        project_service: ProjectService,
        task_service: TaskService,
        goal_service: GoalService | None = None,
        plan_service: PlanService | None = None,
        plan_test_job_service: PlanTestJobService | None = None,
        organization_service: OrganizationService | None = None,
        team_service: TeamService | None = None,
        portfolio_service: PortfolioService | None = None,
        program_service: ProgramService | None = None,
        test_run_service: TestRunService | None = None,
        test_run_retention_service: TestRunRetentionService | None = None,
        saved_search_service: SavedSearchService | None = None,
        queue_service: QueueService | None = None,
        work_snapshot_service: WorkSnapshotService | None = None,
        context_primer: ContextPrimer | None = None,
        prime_context: bool = True,
        max_turns: int = 20,
        model: str = "claude-sonnet-4-5",
    ) -> None:
        """
        Initialize coordinator agent.

        Args:
            project_service: ProjectService instance
            task_service: TaskService instance
            goal_service: GoalService instance (optional)
            plan_service: PlanService instance (optional)
            plan_test_job_service: PlanTestJobService instance (optional)
            organization_service: OrganizationService instance (optional)
            team_service: TeamService instance (optional)
            portfolio_service: PortfolioService instance (optional)
            program_service: ProgramService instance (optional)
            test_run_retention_service: TestRunRetentionService instance (optional)
            saved_search_service: SavedSearchService instance (optional)
            queue_service: QueueService instance (optional)
            work_snapshot_service: WorkSnapshotService instance (optional)
            context_primer: ContextPrimer instance (optional)
            prime_context: Whether to include context primer in prompts
            max_turns: Maximum agent turns before stopping
            model: Claude model to use
        """
        self.project_service = project_service
        self.task_service = task_service
        self.goal_service = goal_service
        self.plan_service = plan_service
        self.plan_test_job_service = plan_test_job_service
        self.organization_service = organization_service
        self.team_service = team_service
        self.portfolio_service = portfolio_service
        self.program_service = program_service
        self.test_run_service = test_run_service
        self.test_run_retention_service = test_run_retention_service
        self.saved_search_service = saved_search_service
        self.queue_service = queue_service
        self.work_snapshot_service = work_snapshot_service
        self.context_primer = context_primer
        self.prime_context = prime_context
        self.max_turns = max_turns
        self.model = model

        if self.context_primer is None and self.prime_context:
            from pms.memory.priming import get_default_context_primer

            self.context_primer = get_default_context_primer()

        # Create MCP server with tools
        self._server = create_pms_server(
            project_service=project_service,
            task_service=task_service,
            goal_service=goal_service,
            plan_service=plan_service,
            plan_test_job_service=plan_test_job_service,
            organization_service=organization_service,
            team_service=team_service,
            portfolio_service=portfolio_service,
            program_service=program_service,
            test_run_service=test_run_service,
            test_run_retention_service=test_run_retention_service,
            saved_search_service=saved_search_service,
            queue_service=queue_service,
            work_snapshot_service=work_snapshot_service,
        )

    def _create_options(self) -> ClaudeCodeOptions:
        """Create agent options with tools configured."""
        system_prompt = build_system_prompt(
            COORDINATOR_SYSTEM_PROMPT,
            self.context_primer,
            self.prime_context,
        )
        return ClaudeCodeOptions(
            model=self.model,
            max_turns=self.max_turns,
            system_prompt=system_prompt,
            mcp_servers={"pms": self._server},
            allowed_tools=PMS_TOOL_NAMES,
        )

    async def run(self, prompt: str) -> AgentResult:
        """
        Run the agent with a user prompt.

        Args:
            prompt: User's request/question

        Returns:
            AgentResult with success status and message
        """
        options = self._create_options()
        tool_calls: list[str] = []
        errors: list[str] = []
        final_message = ""

        try:
            async with ClaudeSDKClient(options=options) as client:
                await client.query(prompt)

                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                final_message = block.text
                            elif isinstance(block, ToolUseBlock):
                                tool_calls.append(f"{block.name}({block.input})")
                            elif isinstance(block, ToolResultBlock) and block.is_error:
                                errors.append(str(block.content))

            return AgentResult(
                success=len(errors) == 0,
                message=final_message,
                tool_calls=tool_calls,
                errors=errors,
            )

        except Exception as e:
            return AgentResult(
                success=False,
                message=f"Agent execution failed: {e}",
                tool_calls=tool_calls,
                errors=[str(e)],
            )

    async def run_streaming(self, prompt: str):  # type: ignore[no-untyped-def]
        """
        Run the agent with streaming output.

        Args:
            prompt: User's request/question

        Yields:
            Messages as they arrive
        """
        options = self._create_options()
        options.include_partial_messages = True

        async with ClaudeSDKClient(options=options) as client:
            await client.query(prompt)

            async for message in client.receive_response():
                yield message


# Agent configuration for use with ClaudeCodeOptions.agents
COORDINATOR_AGENT_CONFIG: dict[str, Any] = {
    "description": "Main coordinator for project and task management",
    "prompt": COORDINATOR_SYSTEM_PROMPT,
    "tools": PMS_TOOL_NAMES,
    "model": "sonnet",
}


# Sub-agent configurations
PROJECT_AGENT_CONFIG: dict[str, Any] = {
    "description": "Specialized agent for project operations like create, archive, summarize",
    "prompt": """You are a project management specialist. Focus on:
- Creating and organizing projects
- Tracking project health and progress
- Generating project summaries and dashboards
- Archiving completed projects

Use the project-related tools to accomplish user requests efficiently.""",
    "tools": [
        "mcp__pms__create_project",
        "mcp__pms__list_projects",
        "mcp__pms__get_project",
        "mcp__pms__get_project_summary",
        "mcp__pms__archive_project",
        "mcp__pms__get_dashboard",
    ],
    "model": "haiku",
}


TASK_AGENT_CONFIG: dict[str, Any] = {
    "description": "Specialized agent for task operations like create, update, track",
    "prompt": """You are a task management specialist. Focus on:
- Creating and organizing tasks
- Tracking task status and dependencies
- Managing blocked tasks
- Bulk task operations

Use the task-related tools to accomplish user requests efficiently.""",
    "tools": [
        "mcp__pms__create_task",
        "mcp__pms__list_tasks",
        "mcp__pms__start_task",
        "mcp__pms__complete_task",
        "mcp__pms__block_task",
        "mcp__pms__unblock_task",
        "mcp__pms__add_task_dependency",
        "mcp__pms__get_task_tree",
        "mcp__pms__get_blocked_tasks",
        "mcp__pms__bulk_create_tasks",
    ],
    "model": "haiku",
}


def get_agent_configs() -> dict[str, dict[str, Any]]:
    """
    Get all agent configurations for use with ClaudeCodeOptions.

    Returns:
        Dictionary of agent name -> configuration
    """
    return {
        "coordinator": COORDINATOR_AGENT_CONFIG,
        "project": PROJECT_AGENT_CONFIG,
        "task": TASK_AGENT_CONFIG,
    }
