"""Agent Orchestrator for multi-agent coordination.

Enables specialized agents to collaborate on complex tasks through:
- Intelligent routing based on task analysis
- Context preservation across agent handoffs
- Parallel agent execution
- Failure handling and recovery

Architecture:
    ┌──────────────────────────────────────────────────────────┐
    │                  Agent Orchestrator                       │
    │                                                           │
    │   ┌─────────────┐  ┌─────────────┐  ┌────────────────┐ │
    │   │   Router    │  │  Context    │  │    Executor    │ │
    │   │             │  │  Manager    │  │                │ │
    │   └──────┬──────┘  └──────┬──────┘  └────────┬───────┘ │
    │          │                │                   │         │
    │          └────────────────┴───────────────────┘         │
    │                           │                             │
    └───────────────────────────┼─────────────────────────────┘
                                │
                  ┌─────────────┴──────────────┐
                  │                            │
         ┌────────▼────────┐         ┌────────▼────────┐
         │  CoordinatorAgent│         │  ProjectAgent   │
         │   (All tools)    │         │  (6 tools)      │
         └─────────────────┘         └─────────────────┘
                  │
         ┌────────▼────────┐
         │   TaskAgent     │
         │  (10 tools)     │
         └─────────────────┘

Usage:
    orchestrator = AgentOrchestrator()

    # Automatic routing
    result = await orchestrator.execute("create a new project called API")

    # Explicit delegation
    result = await orchestrator.delegate(
        to_agent="project",
        task="list all active projects",
        context=shared_context
    )

    # Parallel execution
    results = await orchestrator.execute_parallel([
        ("project", "list projects"),
        ("task", "list blocked tasks"),
    ])
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pms.config.logging import logger, new_correlation_id
from pms.core.ids import EntityType, generate_id

# =============================================================================
# Data Models
# =============================================================================


class AgentCapability(StrEnum):
    """Agent capabilities for routing decisions."""

    PROJECT_MANAGEMENT = "project_management"
    TASK_MANAGEMENT = "task_management"
    CODE_GENERATION = "code_generation"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    GITHUB_INTEGRATION = "github_integration"
    ANALYSIS = "analysis"
    GENERAL = "general"


@dataclass
class AgentInfo:
    """Information about a registered agent."""

    agent_id: str
    name: str
    model: str
    capabilities: list[AgentCapability]
    tool_count: int
    description: str = ""
    active: bool = True
    health_status: str = "unknown"  # unknown, healthy, degraded, unhealthy


@dataclass
class SharedContext:
    """Shared context passed between agents."""

    session_id: str
    correlation_id: str
    agent_session_id: str = ""
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    working_memory: dict[str, Any] = field(default_factory=dict)
    task_queue: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_message(self, role: str, content: str, agent: str | None = None) -> None:
        """Add message to conversation history."""
        self.conversation_history.append(
            {
                "role": role,
                "content": content,
                "agent": agent,
                "timestamp": datetime.now().isoformat(),
            }
        )

    def set_memory(self, key: str, value: Any) -> None:
        """Store value in working memory."""
        self.working_memory[key] = value

    def get_memory(self, key: str, default: Any = None) -> Any:
        """Retrieve value from working memory."""
        return self.working_memory.get(key, default)


@dataclass
class AgentResult:
    """Result from agent execution."""

    success: bool
    message: str
    agent_id: str
    tool_calls: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    context: SharedContext | None = None


# =============================================================================
# Agent Orchestrator
# =============================================================================


class AgentOrchestrator:
    """
    Orchestrates multiple specialized agents for complex workflows.

    Responsibilities:
    - Route tasks to appropriate agents
    - Preserve context across agent transitions
    - Execute agents in parallel when beneficial
    - Handle failures and retry with different agents
    - Track agent health and performance
    """

    def __init__(self) -> None:
        self._agents: dict[str, AgentInfo] = {}
        self._agent_instances: dict[str, Any] = {}  # Actual agent objects
        self._default_agent: str = "coordinator"

        logger.info("Agent Orchestrator initialized")

    def register_agent(
        self,
        agent_id: str,
        agent_instance: Any,
        capabilities: list[AgentCapability],
        model: str = "sonnet",
        description: str = "",
    ) -> None:
        """
        Register an agent with the orchestrator.

        Args:
            agent_id: Unique agent identifier
            agent_instance: Agent object (must have run() method)
            capabilities: List of agent capabilities
            model: Model name (sonnet, opus, haiku)
            description: Human-readable description
        """
        # Count tools if available
        tool_count = 0
        if hasattr(agent_instance, "tools"):
            tool_count = len(agent_instance.tools)

        info = AgentInfo(
            agent_id=agent_id,
            name=agent_id.replace("_", " ").title(),
            model=model,
            capabilities=capabilities,
            tool_count=tool_count,
            description=description,
            active=True,
            health_status="healthy",
        )

        self._agents[agent_id] = info
        self._agent_instances[agent_id] = agent_instance

        logger.info(
            "Agent registered",
            agent_id=agent_id,
            capabilities=[c.value for c in capabilities],
            tool_count=tool_count,
        )

    def unregister_agent(self, agent_id: str) -> None:
        """Unregister an agent."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            del self._agent_instances[agent_id]
            logger.info("Agent unregistered", agent_id=agent_id)

    def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        return list(self._agents.values())

    def get_agent(self, agent_id: str) -> AgentInfo | None:
        """Get agent information."""
        return self._agents.get(agent_id)

    # =============================================================================
    # Routing Logic
    # =============================================================================

    def route(self, task: str, context: SharedContext | None = None) -> str:
        """
        Determine which agent should handle the task.

        Uses keyword matching and capability analysis.

        Args:
            task: Task description
            context: Optional shared context

        Returns:
            Agent ID to use
        """
        task_lower = task.lower()

        # Keyword-based routing
        if (
            any(keyword in task_lower for keyword in ["project", "projects"])
            and "project" in self._agents
            and self._agents["project"].active
        ):
            return "project"

        if (
            any(keyword in task_lower for keyword in ["task", "tasks", "todo"])
            and "task" in self._agents
            and self._agents["task"].active
        ):
            return "task"

        if (
            any(keyword in task_lower for keyword in ["test", "tests", "testing"])
            and "test_generator" in self._agents
            and self._agents["test_generator"].active
        ):
            return "test_generator"

        if (
            any(
                keyword in task_lower for keyword in ["deploy", "deployment", "release"]
            )
            and "deployer" in self._agents
            and self._agents["deployer"].active
        ):
            return "deployer"

        if (
            any(
                keyword in task_lower
                for keyword in ["github", "issue", "pr", "pull request"]
            )
            and "github" in self._agents
            and self._agents["github"].active
        ):
            return "github"

        if (
            any(
                keyword in task_lower
                for keyword in ["fix", "error", "failure", "broken"]
            )
            and "autofix" in self._agents
            and self._agents["autofix"].active
        ):
            return "autofix"

        # Default to coordinator
        return self._default_agent

    def find_agents_with_capability(
        self,
        capability: AgentCapability,
    ) -> list[str]:
        """
        Find all agents with a specific capability.

        Args:
            capability: Capability to search for

        Returns:
            List of agent IDs
        """
        return [
            agent_id
            for agent_id, info in self._agents.items()
            if capability in info.capabilities and info.active
        ]

    # =============================================================================
    # Execution
    # =============================================================================

    async def execute(
        self,
        task: str,
        context: SharedContext | None = None,
        agent_id: str | None = None,
    ) -> AgentResult:
        """
        Execute a task using automatic agent selection or specified agent.

        Args:
            task: Task description
            context: Shared context (created if not provided)
            agent_id: Optional specific agent to use

        Returns:
            Agent execution result
        """
        # Create context if not provided
        if context is None:
            context = SharedContext(
                session_id=f"session_{new_correlation_id()}",
                correlation_id=new_correlation_id(),
                agent_session_id=generate_id(EntityType.SESSION),
            )
        elif not context.agent_session_id:
            context.agent_session_id = generate_id(EntityType.SESSION)

        # Route to appropriate agent
        selected_agent = agent_id or self.route(task, context)

        logger.info(
            "Executing task",
            task=task[:100],
            selected_agent=selected_agent,
            correlation_id=context.correlation_id,
        )

        # Add task to conversation history
        context.add_message("user", task)

        start_time = datetime.now()

        try:
            # Get agent instance
            if selected_agent not in self._agent_instances:
                raise ValueError(f"Agent '{selected_agent}' not found")

            agent = self._agent_instances[selected_agent]

            # Execute agent (assumes agent has run() method)
            if hasattr(agent, "run"):
                result = await agent.run(task)

                # Build result
                agent_result = AgentResult(
                    success=result.success if hasattr(result, "success") else True,
                    message=result.message
                    if hasattr(result, "message")
                    else str(result),
                    agent_id=selected_agent,
                    tool_calls=result.tool_calls
                    if hasattr(result, "tool_calls")
                    else [],
                    errors=result.errors if hasattr(result, "errors") else [],
                    duration_seconds=(datetime.now() - start_time).total_seconds(),
                    context=context,
                )

                # Add result to conversation history
                context.add_message(
                    "assistant", agent_result.message, agent=selected_agent
                )

                logger.info(
                    "Task completed",
                    agent=selected_agent,
                    success=agent_result.success,
                    duration=agent_result.duration_seconds,
                )

                return agent_result
            else:
                raise ValueError(f"Agent '{selected_agent}' does not have run() method")

        except Exception as e:
            logger.error(
                "Task execution failed",
                agent=selected_agent,
                error=str(e),
                exc_info=True,
            )

            return AgentResult(
                success=False,
                message=f"Execution failed: {e}",
                agent_id=selected_agent,
                errors=[str(e)],
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                context=context,
            )

    async def delegate(
        self,
        to_agent: str,
        task: str,
        context: SharedContext,
        from_agent: str | None = None,
    ) -> AgentResult:
        """
        Delegate a task from one agent to another with full context.

        Args:
            to_agent: Target agent ID
            task: Task to delegate
            context: Shared context to preserve
            from_agent: Source agent ID (for logging)

        Returns:
            Result from target agent
        """
        logger.info(
            "Delegating task",
            from_agent=from_agent or "user",
            to_agent=to_agent,
            task=task[:100],
        )

        # Add delegation to conversation history
        context.add_message(
            "system",
            f"Delegating to {to_agent}: {task}",
            agent=from_agent,
        )

        # Execute on target agent with preserved context
        return await self.execute(task, context=context, agent_id=to_agent)

    async def execute_parallel(
        self,
        tasks: list[tuple[str, str]],  # [(agent_id, task), ...]
        context: SharedContext | None = None,
        merge_strategy: str = "all_success",
    ) -> list[AgentResult]:
        """
        Execute multiple tasks in parallel across different agents.

        Args:
            tasks: List of (agent_id, task) tuples
            context: Shared context
            merge_strategy: How to combine results:
                - "all_success": All must succeed
                - "any_success": At least one must succeed
                - "best_effort": Return all results regardless

        Returns:
            List of agent results
        """
        if context is None:
            context = SharedContext(
                session_id=f"session_{new_correlation_id()}",
                correlation_id=new_correlation_id(),
                agent_session_id=generate_id(EntityType.SESSION),
            )
        elif not context.agent_session_id:
            context.agent_session_id = generate_id(EntityType.SESSION)

        logger.info(
            "Executing parallel tasks",
            task_count=len(tasks),
            agents=[agent_id for agent_id, _ in tasks],
        )

        # Execute all tasks concurrently
        results = await asyncio.gather(
            *[self.execute(task, context, agent_id) for agent_id, task in tasks],
            return_exceptions=True,
        )

        # Handle exceptions
        agent_results: list[AgentResult] = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                agent_id, task = tasks[i]
                agent_results.append(
                    AgentResult(
                        success=False,
                        message=f"Execution failed: {result}",
                        agent_id=agent_id,
                        errors=[str(result)],
                    )
                )
            elif isinstance(result, AgentResult):
                agent_results.append(result)

        # Apply merge strategy
        if merge_strategy == "all_success":
            overall_success = all(r.success for r in agent_results)
            if not overall_success:
                logger.warning(
                    "Not all parallel tasks succeeded",
                    failed_count=sum(1 for r in agent_results if not r.success),
                )
        elif merge_strategy == "any_success":
            overall_success = any(r.success for r in agent_results)
            if not overall_success:
                logger.error("No parallel tasks succeeded")

        return agent_results

    # =============================================================================
    # Agent Health Monitoring
    # =============================================================================

    async def check_agent_health(self, agent_id: str) -> bool:
        """
        Check if an agent is healthy.

        Args:
            agent_id: Agent to check

        Returns:
            True if healthy
        """
        if agent_id not in self._agents:
            return False

        info = self._agents[agent_id]

        # Simple health check: verify agent is active and instance exists
        is_healthy = info.active and agent_id in self._agent_instances

        info.health_status = "healthy" if is_healthy else "unhealthy"
        return is_healthy

    async def check_all_health(self) -> dict[str, bool]:
        """
        Check health of all registered agents.

        Returns:
            Dict of agent_id -> healthy status
        """
        health = {}
        for agent_id in self._agents:
            health[agent_id] = await self.check_agent_health(agent_id)
        return health

    # =============================================================================
    # Statistics
    # =============================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get orchestrator statistics."""
        return {
            "total_agents": len(self._agents),
            "active_agents": sum(1 for a in self._agents.values() if a.active),
            "agents_by_capability": self._count_by_capability(),
            "total_tools": sum(a.tool_count for a in self._agents.values()),
        }

    def _count_by_capability(self) -> dict[str, int]:
        """Count agents by capability."""
        counts: dict[str, int] = {}
        for agent in self._agents.values():
            if not agent.active:
                continue
            for cap in agent.capabilities:
                counts[cap.value] = counts.get(cap.value, 0) + 1
        return counts


# =============================================================================
# Factory Function
# =============================================================================


def create_orchestrator(
    project_service: Any = None,
    task_service: Any = None,
    goal_service: Any = None,
    plan_service: Any = None,
    plan_test_job_service: Any = None,
    organization_service: Any = None,
    team_service: Any = None,
    portfolio_service: Any = None,
    program_service: Any = None,
    test_run_service: Any = None,
    test_run_retention_service: Any = None,
    saved_search_service: Any = None,
    queue_service: Any = None,
    work_snapshot_service: Any = None,
) -> AgentOrchestrator:
    """
    Create and configure an agent orchestrator with all available agents.

    Args:
        project_service: ProjectService instance (optional)
        task_service: TaskService instance (optional)
        goal_service: GoalService instance (optional)
        plan_service: PlanService instance (optional)
        plan_test_job_service: PlanTestJobService instance (optional)
        organization_service: OrganizationService instance (optional)
        team_service: TeamService instance (optional)
        portfolio_service: PortfolioService instance (optional)
        program_service: ProgramService instance (optional)
        test_run_service: TestRunService instance (optional)
        test_run_retention_service: TestRunRetentionService instance (optional)
        saved_search_service: SavedSearchService instance (optional)
        queue_service: QueueService instance (optional)
        work_snapshot_service: WorkSnapshotService instance (optional)

    Returns:
        Configured orchestrator

    Note:
        If services are not provided, agents will be registered lazily
        when services become available via register_agent().
    """
    orchestrator = AgentOrchestrator()

    # Register all agents if services are provided
    if project_service and task_service:
        from pms.agents.coordinator import CoordinatorAgent
        from pms.agents.project_agent import ProjectAgent
        from pms.agents.task_agent import TaskAgent
        from pms.memory.priming import get_default_context_primer

        context_primer = get_default_context_primer()

        # Register coordinator (full capabilities)
        coordinator = CoordinatorAgent(
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
            context_primer=context_primer,
        )
        orchestrator.register_agent(
            agent_id="coordinator",
            agent_instance=coordinator,
            capabilities=[AgentCapability.GENERAL],
            model="sonnet",
            description="Main orchestrator for project and task management",
        )

        # Register project agent (specialized)
        project_agent = ProjectAgent(
            project_service=project_service,
            context_primer=context_primer,
        )
        orchestrator.register_agent(
            agent_id="project",
            agent_instance=project_agent,
            capabilities=[AgentCapability.PROJECT_MANAGEMENT],
            model="haiku",
            description="Project lifecycle and health tracking specialist",
        )

        # Register task agent (specialized)
        task_agent = TaskAgent(
            task_service=task_service,
            context_primer=context_primer,
        )
        orchestrator.register_agent(
            agent_id="task",
            agent_instance=task_agent,
            capabilities=[AgentCapability.TASK_MANAGEMENT],
            model="haiku",
            description="Task operations and dependency management specialist",
        )

        logger.info(
            "Agent orchestrator created with {} agents", len(orchestrator.list_agents())
        )
    else:
        logger.info("Agent orchestrator created (agents will be registered later)")

    return orchestrator


# Global orchestrator instance
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_orchestrator()
    return _orchestrator


def set_orchestrator(orchestrator: AgentOrchestrator) -> None:
    """Set the global orchestrator instance (for testing)."""
    global _orchestrator
    _orchestrator = orchestrator
