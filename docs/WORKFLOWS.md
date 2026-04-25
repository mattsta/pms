# PMS Workflows & State Machine Guide

**Purpose**: Flexible workflow system for managing entity lifecycles
**Status**: Fully functional with 3 predefined workflows

---

## Overview

The PMS state machine system provides:

- **Configurable workflows** for different contexts
- **State-specific validation** and metadata
- **Approval gates** for critical transitions
- **Complete audit trail** of all state changes
- **Supports**: Tasks, Projects, Products, and any entity type

---

## Predefined Workflows

### 1. SDLC (Software Development Lifecycle)

**Use For**: Feature development tasks, bug fixes
**States**: 13 total
**Flow**: Linear with optional loops for rework

```
CONCEPT → IDEA → PLANNING → DETAILED_PLAN →
IMPLEMENTING → CODE_REVIEW → UNIT_TESTING →
INTEGRATION_TESTING → STAGING → CONFIRMATION →
PRODUCTION → MONITORING
```

**Special Transitions**:

- CODE_REVIEW ← IMPLEMENTING (rework loop)
- CONFIRMATION → PRODUCTION (requires approval ⚠️)

**Usage**:

```python
from pms.models.workflow_state import create_sdlc_workflow
from pms.core.state_machine import StateMachine

# Create workflow and state machine
sdlc = create_sdlc_workflow()
sm = StateMachine(sdlc, state_transition_repo)

# Assign to task
task.assign_workflow(sdlc.id, "concept")

// Transition with validation
transition = await sm.transition(
    entity_id=task.id,
    from_state="implementing",
    to_state="code_review",
    triggered_by="developer_alice",
    reason="Code complete",
)
```

---

### 2. Agile Sprint Workflow

**Use For**: Sprint-based development, Scrum teams
**States**: 6 total
**Flow**: Flexible with blocking states

```
BACKLOG → SPRINT_PLANNED → IN_PROGRESS ⟷ BLOCKED →
IN_REVIEW → DONE
```

**Special Transitions**:

- IN_PROGRESS ⟷ BLOCKED (bidirectional)
- IN_REVIEW → IN_PROGRESS (changes requested loop)

**Usage**:

```python
from pms.models.workflow_state import create_agile_workflow

agile = create_agile_workflow()
task.assign_workflow(agile.id, "backlog")

# Sprint planning
task.transition_to("sprint_planned", "scrum_master", "Added to sprint")

# Start work
task.transition_to("in_progress", "developer", "Starting implementation")
```

---

### 3. Product Lifecycle

**Use For**: Product maturity tracking
**States**: 9 total
**Flow**: Linear maturity progression

```
CONCEPT → PLANNING → ALPHA → BETA →
RELEASE_CANDIDATE → GA → MATURE →
MAINTENANCE → EOL
```

**Special Transitions**:

- RC → GA (requires approval ⚠️)
- MAINTENANCE → EOL (requires approval ⚠️)

**Usage**:

```python
from pms.models.workflow_state import create_product_lifecycle_workflow

lifecycle = create_product_lifecycle_workflow()
product.assign_workflow(lifecycle.id, "concept")

# Progress through lifecycle
product.transition_to("alpha", "product_manager", "First alpha release")
```

---

## State Machine Engine

### Core Concepts

**WorkflowDefinition**: Complete workflow specification

- States (name, color, terminal flag)
- Transitions (from → to with rules)
- Initial and terminal states

**StateMachine**: Validates and executes transitions

- Checks if transition is allowed
- Enforces approval requirements
- Validates custom rules
- Records transition history

**StateTransition**: Immutable record of state change

- Full attribution (who, when, why)
- Causality tracking
- Duration in previous state
- Flexible metadata

---

## Creating Custom Workflows

```python
from pms.models.workflow_state import WorkflowDefinition, WorkflowState, WorkflowTransition

# Define workflow
my_workflow = WorkflowDefinition(
    id="wf_custom",
    name="my_custom_workflow",
    description="Custom workflow for my process",
    entity_type="task",
    initial_state="start",
    terminal_states=["finished", "abandoned"],
    states=[
        WorkflowState(
            id="wfs_1",
            workflow_id="wf_custom",
            state_name="start",
            display_name="Started",
            color="#blue",
            sort_order=1,
        ),
        WorkflowState(
            id="wfs_2",
            workflow_id="wf_custom",
            state_name="in_progress",
            display_name="In Progress",
            color="#purple",
            sort_order=2,
        ),
        WorkflowState(
            id="wfs_3",
            workflow_id="wf_custom",
            state_name="finished",
            display_name="Finished",
            color="#green",
            is_terminal=True,
            sort_order=3,
        ),
    ],
    transitions=[
        WorkflowTransition(
            id="wft_1",
            workflow_id="wf_custom",
            from_state="start",
            to_state="in_progress",
        ),
        WorkflowTransition(
            id="wft_2",
            workflow_id="wf_custom",
            from_state="in_progress",
            to_state="finished",
            requires_approval=True,  # Approval gate
        ),
    ],
)
```

---

## Validation & Approval

### Checking Transitions

```python
# Check if transition is valid
can_go, error = state_machine.can_transition("implementing", "staging")
if not can_go:
    print(f"Cannot transition: {error}")
```

### Approval Gates

```python
# Transition requiring approval
transition = await state_machine.transition(
    entity_id=task.id,
    from_state="confirmation",
    to_state="production",
    triggered_by="developer",
    approved_by="release_manager",  # ✅ Approval provided
)
```

### Getting Available Transitions

```python
# What states can I go to from here?
available = state_machine.get_available_transitions("implementing")
# Returns: ["code_review", "cancelled"]
```

---

## State Transition History

### Query Timeline

```python
from pms.repositories.state_transition_repository import StateTransitionRepository

state_repo = StateTransitionRepository(db)

# Get complete timeline
timeline = await state_repo.get_timeline("task", task.id)

print(f"Transitions: {len(timeline.transitions)}")
print(f"Total duration: {timeline.total_duration_hours:.1f}h")

# Time in each state
for state, seconds in timeline.state_durations.items():
    hours = seconds / 3600
    print(f"  {state}: {hours:.1f}h")
```

### Analyze Patterns

```python
# How many times was this reopened?
reopen_count = await state_repo.get_reopen_count("task", task.id)

# Time to reach production
time_to_prod = timeline.get_time_to_state("production")
print(f"Time to production: {time_to_prod / 3600:.1f}h")
```

---

## Integration with Features

### Auto-Checkout with Workflows

```python
from pms.automation import Workflow, WorkflowEngine, WorkflowStep
from pms.services.checkout_manager import CheckoutManager

engine = WorkflowEngine(checkout_manager=CheckoutManager(task_repo))

workflow = Workflow(
    name="implement_feature",
    steps=[
        WorkflowStep(
            name="implement",
            action="tool:run_implementation",
            checkout={
                "task_id": "<task-id>",
                "agent_session_id": "agent_worker_1",
                "lease_seconds": 600,
            },
        )
    ],
)

result = await engine.run(workflow)
# Task is exclusively locked for the duration of the step
```

### Progress Updates During Workflow

```python
# Update progress as workflow progresses
task.transition_to("implementing", "agent", "Starting work")
await task_service.update_task_progress(task.id, 25, "25% done", "agent")

task.transition_to("unit_testing", "agent", "Code done, testing")
await task_service.update_task_progress(task.id, 75, "75% done", "agent")

task.transition_to("production", "agent", "Deployed")
await task_service.update_task_progress(task.id, 100, "Complete", "agent")
```

---

## Database Schema

### Workflow Tables

**workflow_definitions**: Workflow configurations
**workflow_states**: All possible states in a workflow
**workflow_transitions**: Allowed transitions with rules
**state_transition_log**: Universal immutable log of ALL state changes

### Entity Workflow Fields

All entities (Task, Project, Product) have:

- `workflow_id`: Assigned workflow (nullable)
- `current_state`: Current state in workflow (nullable)
- `workflow_metadata`: State-specific data (JSON)

---

## Best Practices

### 1. Choose Appropriate Workflow

- **SDLC**: Feature development with quality gates
- **Agile**: Sprint-based iterative work
- **Product Lifecycle**: Long-term product maturity

### 2. Use Approval Gates

Mark critical transitions as `requires_approval=True`:

- Production deployments
- Product GA releases
- Major milestones

### 3. Record Reasons

Always provide meaningful `reason` for transitions:

```python
transition = await sm.transition(
    ...,
    reason="All tests passing, code reviewed by 2 engineers",  # ✅ Good
)
```

### 4. Leverage Metadata

Use `workflow_metadata` for state-specific data:

```python
task.workflow_metadata = {
    "reviewer": "alice@example.com",
    "review_comments": "LGTM, ship it!",
    "tests_passed": True,
}
```

---

## Workflow Alignment

If a task is marked done/cancelled but the workflow is still mid-stream, use the
alignment helper to advance the workflow along the valid path:

```bash
uv run pms workflow align <task_id> --by you
```

If the terminal state is ambiguous, provide the target explicitly:

```bash
uv run pms workflow align <task_id> --by you --to done
```

Preview the alignment without making changes:

```bash
uv run pms workflow align <task_id> --by you --dry-run
```

Goal/objective alignment (CLI):

```bash
uv run pms workflow align <goal_id> --by you --entity-type goal
```

You can also align on completion:

```bash
uv run pms task complete <task_id> --by you --align-workflow
```

API:

```http
POST /api/v1/tasks/{task_id}/workflow/align
{
  "triggered_by": "you",
  "to_state": "done"
}
```

To align goals/objectives:

```http
POST /api/v1/workflow/align
{
  "entity_id": "<goal_or_objective_id>",
  "entity_type": "goal",
  "triggered_by": "you"
}
```

## Label Gate Rules

Labels can gate workflow transitions (require/forbid labels or categories).

Test runs can also trigger workflow transitions when you supply explicit states
to `pms test run` or `pms aws test run`:

```bash
uv run pms test run . --task-id <task-id> --on-success-state integration_testing
```

Example CLI:

```bash
pms label gate add \
  --workflow-id wf_sdlc \
  --entity-type task \
  --from-state code_review \
  --to-state unit_testing \
  --rule-type require_label \
  --label needs-review
```

API:

```http
POST /api/v1/labels/gates
{
  "workflow_id": "wf_sdlc",
  "entity_type": "task",
  "from_state": "code_review",
  "to_state": "unit_testing",
  "rule_type": "require_label",
  "label_id": "<label_id>"
}
```

---

## Examples

See `tests/integration/test_workflow_integration.py` for:

- Complete SDLC workflow (concept → production)
- Invalid transition prevention
- Approval gate enforcement
- State transition history querying

---

**Status**: ✅ Fully Functional
**Tests**: 447 passing, workflow system validated
