"""Workflow helpers shared by CLI and MCP tools."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from pms.core.events import EventType
from pms.core.state_machine import StateMachine
from pms.models.workflow_state import get_workflow_by_id, get_workflow_registry
from pms.repositories import GoalRepository, ObjectiveRepository, TaskRepository


def resolve_workflow(workflow_name_or_id: str) -> Any | None:
    """Resolve a workflow definition by name or ID."""
    workflows = get_workflow_registry()
    if workflow_name_or_id in workflows:
        return workflows[workflow_name_or_id]
    return next(
        (
            workflow
            for workflow in workflows.values()
            if workflow.name == workflow_name_or_id
            or workflow.id == workflow_name_or_id
        ),
        None,
    )


async def assign_workflow(
    *,
    db: Any,
    event_store: Any,
    revision_store: Any,
    metrics: Any,
    entity_type: str,
    entity_id: str,
    workflow_name: str,
    initial_state: str,
) -> tuple[Any | None, Any | None, str | None, str | None]:
    """Assign a workflow to an entity and persist the change."""
    workflow = resolve_workflow(workflow_name)
    if workflow is None:
        return None, None, None, f"Workflow '{workflow_name}' not found"

    match entity_type:
        case "task":
            repo = TaskRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Task"
            update_event = EventType.TASK_UPDATED
        case "goal":
            repo = GoalRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Goal"
            update_event = EventType.GOAL_UPDATED
        case "objective":
            repo = ObjectiveRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Objective"
            update_event = EventType.OBJECTIVE_UPDATED
        case _:
            return None, None, None, "Unsupported entity type"

    if entity is None:
        return None, None, label, f"{label} '{entity_id}' not found"

    entity.assign_workflow(workflow.id, initial_state)
    await repo.save(
        entity,
        update_event,
        {"workflow_assigned": workflow.name, "initial_state": initial_state},
    )

    return entity, workflow, label, None


async def load_workflow_entity(
    *,
    db: Any,
    event_store: Any,
    revision_store: Any,
    metrics: Any,
    entity_type: str,
    entity_id: str,
) -> tuple[Any | None, Any | None, Any | None, Any | None, str | None, str | None]:
    """Load an entity and its workflow for transition evaluation."""
    match entity_type:
        case "task":
            repo = TaskRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Task"
            update_event = EventType.TASK_UPDATED
        case "goal":
            repo = GoalRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Goal"
            update_event = EventType.GOAL_UPDATED
        case "objective":
            repo = ObjectiveRepository(db, event_store, revision_store, metrics)
            entity = await repo.get_by_id(entity_id)
            label = "Objective"
            update_event = EventType.OBJECTIVE_UPDATED
        case _:
            return None, None, None, None, None, "Unsupported entity type"

    if entity is None:
        return None, None, None, None, label, f"{label} '{entity_id}' not found"

    if entity.workflow_id is None:
        if entity_type == "task":
            return (
                None,
                None,
                None,
                None,
                label,
                (
                    f"{label} has no assigned workflow. "
                    "Use `pms task start|block|review|complete` for status changes "
                    "or `pms workflow assign` to attach a workflow."
                ),
            )
        return (
            None,
            None,
            None,
            None,
            label,
            f"{label} has no assigned workflow. Use `pms workflow assign`.",
        )

    workflow = get_workflow_by_id(entity.workflow_id)
    if workflow is None:
        return None, None, None, None, label, "Workflow not found"

    if entity_type != "task":
        workflow = replace(workflow, entity_type=entity_type)

    return entity, repo, workflow, update_event, label, None


async def execute_workflow_transition(
    *,
    entity: Any,
    repo: Any,
    workflow: Any,
    update_event: Any,
    entity_type: str,
    to_state: str,
    triggered_by: str,
    reason: str | None,
    approved_by: str | None,
    state_repo: Any,
    label_service: Any,
    evidence_gate_service: Any,
) -> tuple[Any | None, str | None, bool]:
    """Validate and execute a workflow transition."""
    gate_result = await label_service.evaluate_gates(
        workflow_id=workflow.id,
        entity_type=workflow.entity_type,
        entity_id=entity.id,
        from_state=entity.current_state,
        to_state=to_state,
    )
    if not gate_result.allowed:
        reason = gate_result.reason or "Label gate blocked transition"
        return None, reason, False

    if entity_type == "task":
        evidence_result = await evidence_gate_service.evaluate_gates(
            workflow_id=workflow.id,
            entity_type=workflow.entity_type,
            entity_id=entity.id,
            from_state=entity.current_state,
            to_state=to_state,
        )
        if not evidence_result.allowed:
            reason = evidence_result.reason or "Evidence gate blocked transition"
            return None, reason, False

    state_machine = StateMachine(workflow, state_repo)
    context = {"approved_by": approved_by} if approved_by else {}
    can_transition, error = state_machine.can_transition(
        entity.current_state,
        to_state,
        context=context,
    )
    if not can_transition:
        needs_approval = "approval" in (error or "").lower()
        return None, error or "Invalid transition", needs_approval

    transition = await state_machine.transition(
        entity_id=entity.id,
        from_state=entity.current_state,
        to_state=to_state,
        triggered_by=triggered_by,
        reason=reason,
        approved_by=approved_by,
    )

    entity.transition_to(to_state, triggered_by, reason)
    await repo.save(
        entity,
        update_event,
        {"state_transition": f"{transition.from_state} -> {transition.to_state}"},
    )

    return transition, None, False
