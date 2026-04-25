"""Agent definitions for Claude SDK."""

from pms.agents.coordinator import (
    COORDINATOR_AGENT_CONFIG,
    COORDINATOR_SYSTEM_PROMPT,
    PROJECT_AGENT_CONFIG,
    TASK_AGENT_CONFIG,
    AgentResult,
    CoordinatorAgent,
    get_agent_configs,
)
from pms.agents.orchestrator import (
    AgentOrchestrator,
    create_orchestrator,
    get_orchestrator,
)
from pms.agents.project_agent import ProjectAgent
from pms.agents.task_agent import TaskAgent

__all__ = [
    "AgentResult",
    "CoordinatorAgent",
    "ProjectAgent",
    "TaskAgent",
    "AgentOrchestrator",
    "create_orchestrator",
    "get_orchestrator",
    "COORDINATOR_AGENT_CONFIG",
    "COORDINATOR_SYSTEM_PROMPT",
    "PROJECT_AGENT_CONFIG",
    "TASK_AGENT_CONFIG",
    "get_agent_configs",
]
