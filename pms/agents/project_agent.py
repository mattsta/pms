"""ProjectAgent - Specialized agent for project operations."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from claude_code_sdk import ClaudeCodeOptions, ClaudeSDKClient, TextBlock
from loguru import logger

from pms.agents.priming import build_system_prompt
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService

if TYPE_CHECKING:
    from pms.memory.priming import ContextPrimer

SYSTEM_PROMPT = """You are a project management specialist. Focus on:
- Creating and organizing projects
- Tracking project health and progress
- Generating project summaries and dashboards
- Archiving completed projects

Use the project-related tools to accomplish user requests efficiently.
Be concise and action-oriented."""

PROJECT_TOOLS = [
    "mcp__pms__create_project",
    "mcp__pms__list_projects",
    "mcp__pms__get_project",
    "mcp__pms__get_project_summary",
    "mcp__pms__archive_project",
    "mcp__pms__get_dashboard",
]


@dataclass
class AgentResult:
    success: bool
    message: str
    tool_calls: list[str]
    errors: list[str]


class ProjectAgent:
    """Lightweight agent specialized for project operations."""

    def __init__(
        self,
        project_service: ProjectService,
        task_service: TaskService | None = None,
        context_primer: ContextPrimer | None = None,
        prime_context: bool = True,
    ):
        self.project_service = project_service
        self.task_service = task_service
        self.context_primer = context_primer
        self.prime_context = prime_context
        self.tools = PROJECT_TOOLS

    async def run(self, prompt: str, max_turns: int = 10) -> AgentResult:
        """Execute agent with prompt."""
        logger.info("ProjectAgent executing: {}", prompt[:100])

        tool_calls: list[str] = []
        errors: list[str] = []

        try:
            # Note: create_pms_server returns an MCP server config, not directly usable with ClaudeCodeOptions
            # The MCP server is managed separately in production. This is a simplified version.
            # For now, we'll work without the full server integration.

            system_prompt = build_system_prompt(
                SYSTEM_PROMPT,
                self.context_primer,
                self.prime_context,
            )
            options = ClaudeCodeOptions(
                model="haiku",
                max_turns=max_turns,
                system_prompt=system_prompt,
            )

            async with ClaudeSDKClient(options=options) as client:
                messages: list[dict[str, str]] = [{"role": "user", "content": prompt}]
                response = await client.create_message(messages=messages)  # type: ignore[attr-defined]

                # Extract message and tool calls
                message_parts = []
                for block in response.content:
                    if isinstance(block, TextBlock):
                        message_parts.append(block.text)
                    elif hasattr(block, "name"):  # Tool use block
                        tool_calls.append(block.name)

                message = "".join(message_parts) if message_parts else "Task completed"

            logger.info("ProjectAgent completed: {} tools called", len(tool_calls))

            return AgentResult(
                success=True,
                message=message,
                tool_calls=tool_calls,
                errors=errors,
            )

        except Exception as e:
            logger.error("ProjectAgent failed: {}", str(e))
            errors.append(str(e))
            return AgentResult(
                success=False,
                message=f"Agent failed: {e}",
                tool_calls=tool_calls,
                errors=errors,
            )
