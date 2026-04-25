"""Workflow API routes."""

from collections import deque
from dataclasses import replace
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_db,
    get_evidence_gate_service,
    get_label_service,
)
from pms.api.models import (
    WorkflowAlign,
    WorkflowAlignResponse,
    WorkflowAssign,
    WorkflowTransition,
    WorkflowTransitionResponse,
)
from pms.api.types import JsonObject
from pms.core.entity_type_contract import validate_entity_type
from pms.core.events import EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.core.state_machine import StateMachine
from pms.db.connection import Database
from pms.models import Goal, Objective, Task
from pms.models.api_key import ApiKey
from pms.models.workflow_state import (
    WorkflowDefinition,
    get_workflow_by_id,
    get_workflow_registry,
)
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.evidence_gate_service import EvidenceGateService
from pms.services.label_service import LabelService

router = APIRouter()


class WorkflowSummaryPayload(TypedDict):
    """Workflow summary payload."""

    id: str
    name: str
    description: str | None
    entity_type: str
    states_count: int
    initial_state: str
    terminal_states: list[str]


class WorkflowListPayload(TypedDict):
    """Workflow list response payload."""

    workflows: list[WorkflowSummaryPayload]


# Workflow registry
WORKFLOWS = get_workflow_registry()


def _workflow_for_entity(workflow_name: str, entity_type: str) -> WorkflowDefinition:
    """Get a workflow definition scoped to the target entity type."""
    if workflow_name not in WORKFLOWS:
        raise HTTPException(
            status_code=404, detail=f"Workflow '{workflow_name}' not found"
        )
    workflow = WORKFLOWS[workflow_name]
    return replace(workflow, entity_type=entity_type)


def _normalize_state_name(state_name: str) -> str:
    return state_name.replace("-", "_").lower()


def _find_workflow_path(
    workflow: WorkflowDefinition,
    start_state: str,
    target_state: str,
) -> list[str] | None:
    if start_state == target_state:
        return [start_state]

    states = {start_state, target_state}
    for state in getattr(workflow, "states", []):
        state_name = getattr(state, "state_name", None)
        if state_name:
            states.add(state_name)
    for transition in getattr(workflow, "transitions", []):
        if transition.from_state:
            states.add(transition.from_state)
        if transition.to_state:
            states.add(transition.to_state)

    adjacency: dict[str, set[str]] = {state: set() for state in states}
    for transition in getattr(workflow, "transitions", []):
        if transition.from_state == "*":
            for state in states:
                adjacency[state].add(transition.to_state)
        else:
            adjacency.setdefault(transition.from_state, set()).add(transition.to_state)

    visited = {start_state}
    queue = deque([(start_state, [start_state])])
    while queue:
        current, path = queue.popleft()
        for next_state in sorted(adjacency.get(current, [])):
            if next_state == target_state:
                return [*path, next_state]
            if next_state in visited:
                continue
            visited.add(next_state)
            queue.append((next_state, [*path, next_state]))
    return None


def _suggest_terminal_state(
    status_value: str, terminal_states: list[str]
) -> str | None:
    if not terminal_states:
        return None

    terminal_map = {state: _normalize_state_name(state) for state in terminal_states}

    def match(preferences: tuple[str, ...]) -> str | None:
        for pref in preferences:
            for state, normalized in terminal_map.items():
                if normalized == pref:
                    return state
        return None

    if status_value in {"done", "completed"}:
        match_state = match(
            (
                "done",
                "completed",
                "complete",
                "finished",
                "success",
                "succeeded",
                "released",
                "shipped",
            )
        )
        if match_state:
            return match_state
        non_cancelled = [
            state
            for state, normalized in terminal_map.items()
            if normalized not in {"cancelled", "canceled"}
        ]
        if len(non_cancelled) == 1:
            return non_cancelled[0]
        return None

    if status_value in {"cancelled", "canceled", "archived"}:
        return match(
            (
                "cancelled",
                "canceled",
                "archived",
                "abandoned",
                "rejected",
            )
        )

    return None


@router.get("/workflows")
async def list_workflows(
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_READ)),
) -> WorkflowListPayload:
    """List available workflows."""
    return {
        "workflows": [
            {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "entity_type": wf.entity_type,
                "states_count": len(wf.states),
                "initial_state": wf.initial_state,
                "terminal_states": wf.terminal_states,
            }
            for wf in WORKFLOWS.values()
        ]
    }


@router.get("/workflows/{workflow_ref}")
async def show_workflow(
    workflow_ref: str,
    view: str = "detail",
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_READ)),
) -> JsonObject:
    """Show workflow states and transitions."""
    if view not in {"overview", "detail", "trace"}:
        raise HTTPException(status_code=400, detail="Invalid view")
    workflow = WORKFLOWS.get(workflow_ref)
    workflow_key = workflow_ref if workflow is not None else None
    if workflow is None:
        for key, candidate in WORKFLOWS.items():
            if candidate.name == workflow_ref or candidate.id == workflow_ref:
                workflow = candidate
                workflow_key = key
                break

    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if view == "overview":
        return {
            "key": workflow_key,
            "name": workflow.name,
            "id": workflow.id,
            "entity_type": workflow.entity_type,
            "states_count": len(workflow.states),
            "initial_state": workflow.initial_state,
            "terminal_states": list(workflow.terminal_states),
            "is_default": workflow.is_default,
        }

    payload = workflow.to_dict()
    payload["key"] = workflow_key
    payload["states"] = sorted(
        workflow.states,
        key=lambda state: state.sort_order,
    )
    payload["transitions"] = sorted(
        workflow.transitions,
        key=lambda transition: (transition.from_state, transition.to_state),
    )
    payload["states"] = [state.to_dict() for state in payload["states"]]
    payload["transitions"] = [
        transition.to_dict() for transition in payload["transitions"]
    ]
    return payload


@router.post("/tasks/{task_id}/workflow/assign")
async def assign_workflow_to_task(
    task_id: str,
    data: WorkflowAssign,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> JsonObject:
    """Assign a workflow to a task."""
    if data.workflow_name not in WORKFLOWS:
        raise HTTPException(
            status_code=404, detail=f"Workflow '{data.workflow_name}' not found"
        )

    workflow = WORKFLOWS[data.workflow_name]

    # Get task
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)

    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Assign workflow
    task.assign_workflow(workflow.id, data.initial_state)
    await task_repo.save(
        task,
        EventType.TASK_UPDATED,
        {"workflow_assigned": workflow.name, "initial_state": data.initial_state},
    )

    return {
        "status": "assigned",
        "task_id": task.id,
        "workflow": workflow.name,
        "current_state": task.current_state,
    }


@router.post(
    "/tasks/{task_id}/workflow/transition", response_model=WorkflowTransitionResponse
)
async def transition_workflow_state(
    task_id: str,
    data: WorkflowTransition,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    evidence_gate_service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> WorkflowTransitionResponse:
    """Transition task to new workflow state."""
    # Get task
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    task_repo = TaskRepository(db, event_store, revision_store, metrics)
    state_repo = StateTransitionRepository(db)

    task = await task_repo.get_by_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.workflow_id is None:
        raise HTTPException(status_code=400, detail="Task has no assigned workflow")

    # Get workflow
    workflow = get_workflow_by_id(task.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if task.current_state is None:
        raise HTTPException(
            status_code=400, detail="Task has no current workflow state"
        )
    from_state = task.current_state

    gate_result = await label_service.evaluate_gates(
        workflow_id=workflow.id,
        entity_type=workflow.entity_type,
        entity_id=task.id,
        from_state=from_state,
        to_state=data.to_state,
    )
    if not gate_result.allowed:
        raise HTTPException(
            status_code=400,
            detail=gate_result.reason or "Label gate blocked transition",
        )

    evidence_result = await evidence_gate_service.evaluate_gates(
        workflow_id=workflow.id,
        entity_type=workflow.entity_type,
        entity_id=task.id,
        from_state=from_state,
        to_state=data.to_state,
    )
    if not evidence_result.allowed:
        raise HTTPException(
            status_code=400,
            detail=evidence_result.reason or "Evidence gate blocked transition",
        )

    # Validate and execute transition
    sm = StateMachine(workflow, state_repo)
    context = {}
    if data.approved_by:
        context["approved_by"] = data.approved_by

    can_transition, error = sm.can_transition(
        from_state,
        data.to_state,
        context=context,
    )

    if not can_transition:
        raise HTTPException(status_code=400, detail=f"Invalid transition: {error}")

    # Execute transition
    transition = await sm.transition(
        entity_id=task.id,
        from_state=from_state,
        to_state=data.to_state,
        triggered_by=data.triggered_by,
        reason=data.reason,
        approved_by=data.approved_by,
    )

    # Update task
    task.transition_to(data.to_state, data.triggered_by, data.reason)
    await task_repo.save(
        task,
        EventType.TASK_UPDATED,
        {"state_transition": f"{transition.from_state} → {transition.to_state}"},
    )

    return WorkflowTransitionResponse(
        entity_id=transition.entity_id,
        from_state=transition.from_state,
        to_state=transition.to_state,
        triggered_by=transition.triggered_by,
        timestamp=transition.timestamp,
    )


async def _align_entity_workflow(
    data: WorkflowAlign,
    db: Database,
    label_service: LabelService,
    evidence_gate_service: EvidenceGateService,
) -> WorkflowAlignResponse:
    if not data.entity_id:
        raise HTTPException(status_code=400, detail="entity_id is required")
    try:
        normalized_entity_type = validate_entity_type(
            data.entity_type,
            allowed={"task", "goal", "objective"},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    state_repo = StateTransitionRepository(db)
    repo: TaskRepository | GoalRepository | ObjectiveRepository
    entity: Task | Goal | Objective | None

    match normalized_entity_type:
        case "task":
            repo = TaskRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(data.entity_id)
            update_event = EventType.TASK_UPDATED
        case "goal":
            repo = GoalRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(data.entity_id)
            update_event = EventType.GOAL_UPDATED
        case "objective":
            repo = ObjectiveRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(data.entity_id)
            update_event = EventType.OBJECTIVE_UPDATED

    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    if entity.workflow_id is None:
        raise HTTPException(status_code=400, detail="Entity has no assigned workflow")

    workflow = get_workflow_by_id(entity.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if normalized_entity_type != "task":
        workflow = replace(workflow, entity_type=normalized_entity_type)

    status_value = entity.status
    status_str = (
        status_value.value if hasattr(status_value, "value") else str(status_value)
    )
    status_terminal = status_str in {"done", "cancelled", "completed", "archived"}
    workflow_terminal = (
        entity.current_state in workflow.terminal_states
        if entity.current_state
        else False
    )

    if status_terminal == workflow_terminal:
        return WorkflowAlignResponse(
            entity_id=entity.id,
            from_state=entity.current_state,
            target_state=entity.current_state or "",
            applied_transitions=[],
            remaining=[],
            aligned=True,
        )

    if not status_terminal and workflow_terminal:
        raise HTTPException(
            status_code=409,
            detail="Workflow is terminal but status is not; update status first.",
        )

    if entity.current_state is None:
        raise HTTPException(
            status_code=400, detail="Entity has no current workflow state"
        )

    target_state = data.to_state or _suggest_terminal_state(
        status_str, workflow.terminal_states
    )
    if target_state is None:
        raise HTTPException(
            status_code=400,
            detail="Unable to infer terminal workflow state; provide to_state.",
        )

    if target_state == entity.current_state:
        return WorkflowAlignResponse(
            entity_id=entity.id,
            from_state=entity.current_state,
            target_state=target_state,
            applied_transitions=[],
            remaining=[],
            aligned=True,
        )

    path = _find_workflow_path(workflow, entity.current_state, target_state)
    if path is None:
        raise HTTPException(
            status_code=400,
            detail=f"No workflow path from {entity.current_state} to {target_state}",
        )

    if data.dry_run or not data.auto:
        return WorkflowAlignResponse(
            entity_id=entity.id,
            from_state=entity.current_state,
            target_state=target_state,
            applied_transitions=[],
            remaining=path[1:],
            aligned=False,
        )

    reason = data.reason or f"Align workflow to status {status_str}"
    applied: list[str] = []
    sm = StateMachine(workflow, state_repo)

    for next_state in path[1:]:
        current_state = entity.current_state
        if current_state is None:
            raise HTTPException(
                status_code=400, detail="Entity has no current workflow state"
            )
        gate_result = await label_service.evaluate_gates(
            workflow_id=workflow.id,
            entity_type=workflow.entity_type,
            entity_id=entity.id,
            from_state=current_state,
            to_state=next_state,
        )
        if not gate_result.allowed:
            raise HTTPException(
                status_code=400,
                detail=gate_result.reason or "Label gate blocked transition",
            )

        if normalized_entity_type == "task":
            evidence_result = await evidence_gate_service.evaluate_gates(
                workflow_id=workflow.id,
                entity_type=workflow.entity_type,
                entity_id=entity.id,
                from_state=current_state,
                to_state=next_state,
            )
            if not evidence_result.allowed:
                raise HTTPException(
                    status_code=400,
                    detail=evidence_result.reason or "Evidence gate blocked transition",
                )

        context = {}
        if data.approved_by:
            context["approved_by"] = data.approved_by

        can_transition, error = sm.can_transition(
            current_state,
            next_state,
            context=context,
        )
        if not can_transition:
            raise HTTPException(status_code=400, detail=f"Invalid transition: {error}")

        transition = await sm.transition(
            entity_id=entity.id,
            from_state=current_state,
            to_state=next_state,
            triggered_by=data.triggered_by,
            reason=reason,
            approved_by=data.approved_by,
        )

        entity.transition_to(next_state, data.triggered_by, reason)
        match normalized_entity_type:
            case "task":
                if isinstance(repo, TaskRepository) and isinstance(entity, Task):
                    await repo.save(
                        entity,
                        update_event,
                        {
                            "state_transition": (
                                f"{transition.from_state} → {transition.to_state}"
                            )
                        },
                    )
            case "goal":
                if isinstance(repo, GoalRepository) and isinstance(entity, Goal):
                    await repo.save(
                        entity,
                        update_event,
                        {
                            "state_transition": (
                                f"{transition.from_state} → {transition.to_state}"
                            )
                        },
                    )
            case "objective":
                if isinstance(repo, ObjectiveRepository) and isinstance(
                    entity, Objective
                ):
                    await repo.save(
                        entity,
                        update_event,
                        {
                            "state_transition": (
                                f"{transition.from_state} → {transition.to_state}"
                            )
                        },
                    )
        applied.append(f"{transition.from_state}->{transition.to_state}")

    return WorkflowAlignResponse(
        entity_id=entity.id,
        from_state=path[0],
        target_state=target_state,
        applied_transitions=applied,
        remaining=[],
        aligned=True,
    )


@router.post("/workflow/align", response_model=WorkflowAlignResponse)
async def align_workflow_state(
    data: WorkflowAlign,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    evidence_gate_service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> WorkflowAlignResponse:
    """Align workflow state with entity status (task/goal/objective)."""
    return await _align_entity_workflow(
        data=data,
        db=db,
        label_service=label_service,
        evidence_gate_service=evidence_gate_service,
    )


@router.post("/tasks/{task_id}/workflow/align", response_model=WorkflowAlignResponse)
async def align_task_workflow_state(
    task_id: str,
    data: WorkflowAlign,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    evidence_gate_service: EvidenceGateService = Depends(get_evidence_gate_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> WorkflowAlignResponse:
    """Align task workflow state with task status."""
    payload = data.model_copy(update={"entity_id": task_id, "entity_type": "task"})
    return await _align_entity_workflow(
        data=payload,
        db=db,
        label_service=label_service,
        evidence_gate_service=evidence_gate_service,
    )


@router.post("/goals/{goal_id}/workflow/assign")
async def assign_workflow_to_goal(
    goal_id: str,
    data: WorkflowAssign,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> JsonObject:
    """Assign a workflow to a goal."""
    workflow = _workflow_for_entity(data.workflow_name, "goal")

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    goal_repo = GoalRepository(db, event_store, revision_store, metrics)

    goal = await goal_repo.get_by_id(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    goal.assign_workflow(workflow.id, data.initial_state)
    await goal_repo.save(
        goal,
        EventType.GOAL_UPDATED,
        {"workflow_assigned": workflow.name, "initial_state": data.initial_state},
    )

    return {
        "status": "assigned",
        "goal_id": goal.id,
        "workflow": workflow.name,
        "current_state": goal.current_state,
    }


@router.post(
    "/goals/{goal_id}/workflow/transition", response_model=WorkflowTransitionResponse
)
async def transition_goal_workflow_state(
    goal_id: str,
    data: WorkflowTransition,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> WorkflowTransitionResponse:
    """Transition a goal to a new workflow state."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    goal_repo = GoalRepository(db, event_store, revision_store, metrics)
    state_repo = StateTransitionRepository(db)

    goal = await goal_repo.get_by_id(goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    if goal.workflow_id is None:
        raise HTTPException(status_code=400, detail="Goal has no assigned workflow")

    workflow = get_workflow_by_id(goal.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = replace(workflow, entity_type="goal")
    if goal.current_state is None:
        raise HTTPException(
            status_code=400, detail="Goal has no current workflow state"
        )
    from_state = goal.current_state
    gate_result = await label_service.evaluate_gates(
        workflow_id=workflow.id,
        entity_type=workflow.entity_type,
        entity_id=goal.id,
        from_state=from_state,
        to_state=data.to_state,
    )
    if not gate_result.allowed:
        raise HTTPException(
            status_code=400,
            detail=gate_result.reason or "Label gate blocked transition",
        )
    sm = StateMachine(workflow, state_repo)
    context = {}
    if data.approved_by:
        context["approved_by"] = data.approved_by

    can_transition, error = sm.can_transition(
        from_state,
        data.to_state,
        context=context,
    )

    if not can_transition:
        raise HTTPException(status_code=400, detail=f"Invalid transition: {error}")

    transition = await sm.transition(
        entity_id=goal.id,
        from_state=from_state,
        to_state=data.to_state,
        triggered_by=data.triggered_by,
        reason=data.reason,
        approved_by=data.approved_by,
    )

    goal.transition_to(data.to_state, data.triggered_by, data.reason)
    await goal_repo.save(
        goal,
        EventType.GOAL_UPDATED,
        {"state_transition": f"{transition.from_state} → {transition.to_state}"},
    )

    return WorkflowTransitionResponse(
        entity_id=transition.entity_id,
        from_state=transition.from_state,
        to_state=transition.to_state,
        triggered_by=transition.triggered_by,
        timestamp=transition.timestamp,
    )


@router.post("/objectives/{objective_id}/workflow/assign")
async def assign_workflow_to_objective(
    objective_id: str,
    data: WorkflowAssign,
    db: Database = Depends(get_db),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> JsonObject:
    """Assign a workflow to an objective."""
    workflow = _workflow_for_entity(data.workflow_name, "objective")

    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    objective_repo = ObjectiveRepository(db, event_store, revision_store, metrics)

    objective = await objective_repo.get_by_id(objective_id)
    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    objective.assign_workflow(workflow.id, data.initial_state)
    await objective_repo.save(
        objective,
        EventType.OBJECTIVE_UPDATED,
        {"workflow_assigned": workflow.name, "initial_state": data.initial_state},
    )

    return {
        "status": "assigned",
        "objective_id": objective.id,
        "workflow": workflow.name,
        "current_state": objective.current_state,
    }


@router.post(
    "/objectives/{objective_id}/workflow/transition",
    response_model=WorkflowTransitionResponse,
)
async def transition_objective_workflow_state(
    objective_id: str,
    data: WorkflowTransition,
    db: Database = Depends(get_db),
    label_service: LabelService = Depends(get_label_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.WORKFLOWS_WRITE)),
) -> WorkflowTransitionResponse:
    """Transition an objective to a new workflow state."""
    event_store = EventStore(db)
    revision_store = RevisionStore(db)
    metrics = MetricsCollector(db)
    objective_repo = ObjectiveRepository(db, event_store, revision_store, metrics)
    state_repo = StateTransitionRepository(db)

    objective = await objective_repo.get_by_id(objective_id)
    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    if objective.workflow_id is None:
        raise HTTPException(
            status_code=400, detail="Objective has no assigned workflow"
        )

    workflow = get_workflow_by_id(objective.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow = replace(workflow, entity_type="objective")
    if objective.current_state is None:
        raise HTTPException(
            status_code=400, detail="Objective has no current workflow state"
        )
    from_state = objective.current_state
    gate_result = await label_service.evaluate_gates(
        workflow_id=workflow.id,
        entity_type=workflow.entity_type,
        entity_id=objective.id,
        from_state=from_state,
        to_state=data.to_state,
    )
    if not gate_result.allowed:
        raise HTTPException(
            status_code=400,
            detail=gate_result.reason or "Label gate blocked transition",
        )
    sm = StateMachine(workflow, state_repo)
    context = {}
    if data.approved_by:
        context["approved_by"] = data.approved_by

    can_transition, error = sm.can_transition(
        from_state,
        data.to_state,
        context=context,
    )

    if not can_transition:
        raise HTTPException(status_code=400, detail=f"Invalid transition: {error}")

    transition = await sm.transition(
        entity_id=objective.id,
        from_state=from_state,
        to_state=data.to_state,
        triggered_by=data.triggered_by,
        reason=data.reason,
        approved_by=data.approved_by,
    )

    objective.transition_to(data.to_state, data.triggered_by, data.reason)
    await objective_repo.save(
        objective,
        EventType.OBJECTIVE_UPDATED,
        {"state_transition": f"{transition.from_state} → {transition.to_state}"},
    )

    return WorkflowTransitionResponse(
        entity_id=transition.entity_id,
        from_state=transition.from_state,
        to_state=transition.to_state,
        triggered_by=transition.triggered_by,
        timestamp=transition.timestamp,
    )
