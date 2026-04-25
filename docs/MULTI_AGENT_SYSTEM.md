# Multi-Agent System Documentation

## Overview

PMS has a **3-agent system** with intelligent routing, context preservation, and parallel execution capabilities.

## Active Agents

### 1. CoordinatorAgent

- **Role:** General orchestration and complex tasks
- **Tools:** Full MCP tool access via `pms.tools.server`
- **Use When:** Complex multi-step operations, analysis, planning

### 2. ProjectAgent

- **Role:** Fast project management operations
- **Tools:** Prompt-only today (no MCP tool wiring)
- **Use When:** "project", "projects" keywords detected

### 3. TaskAgent

- **Role:** Fast task management operations
- **Tools:** Prompt-only today (no MCP tool wiring)
- **Use When:** "task", "tasks", "todo" keywords detected

## Agent Orchestrator

The `AgentOrchestrator` provides:

- **Automatic routing** based on keyword analysis
- **Context preservation** across agent transitions
- **Parallel execution** of multiple agents
- **Lightweight health status tracking** (no active probes)

## Usage

### Via Python API

```python
from pms.agents import get_orchestrator

# Get orchestrator (auto-configures with services)
orch = get_orchestrator()

# Execute with automatic routing
result = await orch.execute("list all active projects")
# Routes to ProjectAgent (Haiku) - faster, cheaper

result = await orch.execute("analyze project health and suggest improvements")
# Routes to CoordinatorAgent (Sonnet) - better for analysis

# Explicit agent selection
result = await orch.execute("create new tasks", agent_id="task")

# Parallel execution
results = await orch.execute_parallel([
    ("project", "list all projects"),
    ("task", "list blocked tasks"),
])

# Delegation with context preservation
context = SharedContext(session_id="<session-id>", correlation_id="<correlation-id>")
context.set_memory("current_project", "proj_xyz")

result = await orch.delegate(
    to_agent="task",
    task="create 5 tasks for this project",
    context=context
)
```

### Via CLI (Not yet wired)

```bash
No CLI subcommands are implemented yet for multi-agent orchestration.
```

## Routing Keywords

| Keywords             | Routes To            | Model  |
| -------------------- | -------------------- | ------ |
| project, projects    | ProjectAgent         | Haiku  |
| task, tasks, todo    | TaskAgent            | Haiku  |
| test, tests, testing | TestGeneratorAgent\* | Haiku  |
| deploy, deployment   | DeployerAgent\*      | Haiku  |
| fix, error, failure  | AutoFixAgent\*       | Haiku  |
| (default/complex)    | CoordinatorAgent     | Sonnet |

\*Coming soon

## Benefits

1. **Cost Optimization:** Haiku agents are 20x cheaper than Sonnet
2. **Speed:** Specialized agents are faster for simple operations
3. **Scalability:** Add more specialized agents without changing existing code
4. **Context Efficiency:** Each agent only loads tools it needs

## Implementation Details

- **Location:** `pms/agents/orchestrator.py`
- **Agents:** `pms/agents/project_agent.py`, `pms/agents/task_agent.py`
- **Registration:** Automatic when services are provided
- **Health Checks:** Status field exists, but no periodic health probes

## Next Steps

Planned specialized agents:

- TestGeneratorAgent - Autonomous test generation
- AutoFixAgent - Automatic bug fixing
- DeployerAgent - Deployment orchestration
