"""Goals API routes."""

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service, get_goal_service
from pms.api.models import (
    CompletionContextResponse,
    GoalCreate,
    GoalDetailResponse,
    GoalEffectiveHierarchyResponse,
    GoalEffectiveRollupResponse,
    GoalExecutionFocusTaskResponse,
    GoalExecutionSummaryResponse,
    GoalListItemResponse,
    GoalResponse,
    GoalSummaryResponse,
    GoalSummaryStatsResponse,
    GoalUpdate,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models import GoalHorizon, GoalStatus
from pms.models.api_key import ApiKey
from pms.services.actor_service import ActorService
from pms.services.goal_service import GoalService, goal_lifecycle_terminal_reason

router = APIRouter()


def _goal_response(goal: object, owner_map: dict[str, object]) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        name=goal.name,
        description=goal.description,
        status=goal.status.value,
        horizon=goal.horizon.value,
        target_date=goal.target_date,
        owner=actor_reference_payload(
            goal.owner,
            owner_map,
            actor_id=goal.owner_id,
        ),
        product_id=goal.product_id,
        project_id=goal.project_id,
        tags=list(goal.tags),
        progress_percent=goal.progress_percent,
        workflow_id=goal.workflow_id,
        current_state=goal.current_state,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


def _goal_effective_rollup_response(
    effective_rollup: object | None,
) -> GoalEffectiveRollupResponse | None:
    if effective_rollup is None:
        return None
    return GoalEffectiveRollupResponse(
        progress_percent=effective_rollup.progress_percent,
        status=effective_rollup.status,
        basis=effective_rollup.basis,
        reason=effective_rollup.reason,
    )


def _goal_effective_hierarchy_response(
    effective_hierarchy: object,
) -> GoalEffectiveHierarchyResponse:
    return GoalEffectiveHierarchyResponse(
        objective_count=effective_hierarchy.objective_count,
        completed_objectives=effective_hierarchy.completed_objectives,
        key_result_count=effective_hierarchy.key_result_count,
        completed_key_results=effective_hierarchy.completed_key_results,
        average_progress=effective_hierarchy.average_progress,
        basis=effective_hierarchy.basis,
        reason=effective_hierarchy.reason,
    )


def _goal_execution_response(
    execution: object | None,
) -> GoalExecutionSummaryResponse | None:
    if execution is None:
        return None
    focus_task = None
    if execution.focus_task is not None:
        focus_task = GoalExecutionFocusTaskResponse(
            id=execution.focus_task.id,
            title=execution.focus_task.title,
            status=execution.focus_task.status,
            current_progress_percent=execution.focus_task.current_progress_percent,
            reason=execution.focus_task.reason,
            completion_criteria_count=(execution.focus_task.completion_criteria_count),
            has_completion_criteria=execution.focus_task.has_completion_criteria,
        )
    return GoalExecutionSummaryResponse(
        total_tasks=execution.total_tasks,
        completed_tasks=execution.completed_tasks,
        in_progress_tasks=execution.in_progress_tasks,
        blocked_tasks=execution.blocked_tasks,
        average_task_progress=execution.average_task_progress,
        completion_percent=execution.completion_percent,
        readiness_state=execution.readiness_state,
        consistency_status=execution.consistency_status,
        consistency_reason=execution.consistency_reason,
        terminal_reason=execution.terminal_reason,
        focus_task=focus_task,
        population_basis=execution.population_basis,
        scoped_goal_count=execution.scoped_goal_count,
    )


def _goal_focus_task_id(execution: object | None) -> str | None:
    if execution is None or execution.focus_task is None:
        return None
    return execution.focus_task.id


def _goal_terminal_reason(
    goal: object,
    *,
    effective_rollup: object | None,
    execution: object | None,
) -> str | None:
    return goal_lifecycle_terminal_reason(
        goal,
        effective_rollup=effective_rollup,
        execution=execution,
    )


def _goal_summary_links(goal_id: str, project_id: str | None) -> dict[str, str]:
    links = {
        "self": f"/api/v1/goals/{goal_id}/summary",
        "goal": f"/api/v1/goals/{goal_id}",
        "objectives": f"/api/v1/goals/{goal_id}/objectives",
        "plans": f"/api/v1/plans?goal_id={goal_id}",
        "project": f"/api/v1/projects/{project_id}" if project_id else "",
        "tasks": f"/api/v1/tasks?project_id={project_id}" if project_id else "",
        "guide": "/api/v1/",
    }
    return {key: value for key, value in links.items() if value}


def _goal_detail_links(goal_id: str, project_id: str | None) -> dict[str, str]:
    links = {
        "self": f"/api/v1/goals/{goal_id}",
        "summary": f"/api/v1/goals/{goal_id}/summary",
        "objectives": f"/api/v1/goals/{goal_id}/objectives",
        "plans": f"/api/v1/plans?goal_id={goal_id}",
        "project": f"/api/v1/projects/{project_id}" if project_id else "",
        "tasks": f"/api/v1/tasks?project_id={project_id}" if project_id else "",
        "guide": "/api/v1/",
    }
    return {key: value for key, value in links.items() if value}


def _goal_detail_next_steps(
    *,
    goal_id: str,
    project_id: str | None,
    focus_task_id: str | None,
    terminal_reason: str | None,
) -> list[str]:
    return normalize_next_steps(
        f"GET /api/v1/goals/{goal_id}/summary",
        f"GET /api/v1/goals/{goal_id}/objectives",
        f"GET /api/v1/plans?goal_id={goal_id}",
        f"GET /api/v1/projects/{project_id}" if project_id else "",
        f"GET /api/v1/tasks/{focus_task_id}" if focus_task_id else "",
        (
            f"GET /api/v1/tasks?project_id={project_id}"
            if project_id and terminal_reason is not None
            else ""
        ),
        "GET /api/v1/goals?status=completed" if terminal_reason is not None else "",
    )


def _goal_summary_next_steps(
    *,
    goal_id: str,
    project_id: str | None,
    focus_task_id: str | None,
    terminal_reason: str | None,
) -> list[str]:
    return normalize_next_steps(
        f"GET /api/v1/goals/{goal_id}",
        f"GET /api/v1/goals/{goal_id}/objectives",
        f"GET /api/v1/plans?goal_id={goal_id}",
        f"GET /api/v1/projects/{project_id}" if project_id else "",
        f"GET /api/v1/tasks/{focus_task_id}" if focus_task_id else "",
        (
            f"GET /api/v1/tasks?project_id={project_id}"
            if project_id and terminal_reason is not None
            else ""
        ),
        "GET /api/v1/goals?status=completed" if terminal_reason is not None else "",
    )


def _goal_completion_context(
    *,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> CompletionContextResponse | None:
    if terminal_reason is None:
        return None
    return CompletionContextResponse(
        summary=(
            "This goal is terminal. Inspect linked tasks, project state, or "
            "completed goals instead of treating the goal as active work."
        ),
        next_steps=normalize_next_steps(
            f"GET /api/v1/goals/{goal_id}",
            f"GET /api/v1/goals/{goal_id}/summary",
            (f"GET /api/v1/tasks?project_id={project_id}" if project_id else ""),
            (f"GET /api/v1/projects/{project_id}" if project_id else ""),
            "GET /api/v1/goals?status=completed",
        ),
    )


@router.post("/goals", response_model=GoalResponse, status_code=201)
async def create_goal(
    data: GoalCreate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> GoalResponse:
    """Create a new goal."""
    goal = await goal_service.create_goal(
        name=data.name,
        description=data.description,
        horizon=GoalHorizon(data.horizon),
        target_date=data.target_date,
        owner=data.owner,
        product_id=data.product_id,
        project_id=data.project_id,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    owner_map = await resolve_owner_map(actor_service, [goal])
    return _goal_response(goal, owner_map)


@router.get("/goals")
async def list_goals(
    status: str | None = None,
    horizon: str | None = None,
    product_id: str | None = None,
    project_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> PaginatedResponse[GoalListItemResponse]:
    """List all goals with optional filters."""
    status_filter = GoalStatus(status) if status else None
    horizon_filter = GoalHorizon(horizon) if horizon else None

    result = await goal_service.list_goals(
        status=status_filter,
        horizon=horizon_filter,
        product_id=product_id,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "horizon": horizon,
        "product_id": product_id,
        "project_id": project_id,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/goals", params)
    next_path = next_page_path(
        path="/api/v1/goals",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/goals/{goal_id}",
        "GET /api/v1/goals/{goal_id}/summary",
        "GET /api/v1/goals/{goal_id}/objectives",
    )

    goal_ids = [goal.id for goal in result.items]
    owner_map = await resolve_owner_map(actor_service, result.items)
    effective_rollups = await goal_service.get_effective_rollups_for_goals(result.items)
    execution_summaries = await goal_service.get_execution_summaries_for_goals(
        result.items
    )
    activity_map = await goal_service.get_last_activity_map(goal_ids)
    transition_map = await goal_service.get_last_transition_map(goal_ids)
    items: list[GoalListItemResponse] = []
    for goal in result.items:
        effective_rollup = effective_rollups.get(goal.id)
        execution = execution_summaries.get(goal.id)
        terminal_reason = _goal_terminal_reason(
            goal,
            effective_rollup=effective_rollup,
            execution=execution,
        )
        items.append(
            GoalListItemResponse(
                **_goal_response(goal, owner_map).model_dump(),
                effective_rollup=_goal_effective_rollup_response(effective_rollup),
                last_activity_at=activity_map.get(goal.id),
                last_transition_at=transition_map.get(goal.id),
                terminal_reason=terminal_reason,
                links=_goal_detail_links(goal.id, goal.project_id),
                next_steps=_goal_detail_next_steps(
                    goal_id=goal.id,
                    project_id=goal.project_id,
                    focus_task_id=_goal_focus_task_id(execution),
                    terminal_reason=terminal_reason,
                ),
            )
        )

    return {
        "items": items,
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/goals/{goal_id}", response_model=GoalDetailResponse)
async def get_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> GoalDetailResponse:
    """Get a goal by ID."""
    summary = await goal_service.get_goal_summary(goal_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    owner_map = await resolve_owner_map(actor_service, [summary.goal])
    activity_map = await goal_service.get_last_activity_map([summary.goal.id])
    transition_map = await goal_service.get_last_transition_map([summary.goal.id])
    terminal_reason = _goal_terminal_reason(
        summary.goal,
        effective_rollup=summary.effective_rollup,
        execution=summary.execution,
    )
    completion_context = _goal_completion_context(
        goal_id=summary.goal.id,
        project_id=summary.goal.project_id,
        terminal_reason=terminal_reason,
    )
    focus_task_id = _goal_focus_task_id(summary.execution)
    next_steps = (
        list(completion_context.next_steps)
        if completion_context is not None
        else _goal_detail_next_steps(
            goal_id=summary.goal.id,
            project_id=summary.goal.project_id,
            focus_task_id=focus_task_id,
            terminal_reason=terminal_reason,
        )
    )
    return GoalDetailResponse(
        **_goal_response(summary.goal, owner_map).model_dump(),
        stats=GoalSummaryStatsResponse(
            objective_count=summary.objective_count,
            completed_objectives=summary.completed_objectives,
            key_result_count=summary.key_result_count,
            completed_key_results=summary.completed_key_results,
            average_progress=summary.average_progress,
        ),
        effective_rollup=_goal_effective_rollup_response(summary.effective_rollup),
        effective_hierarchy=_goal_effective_hierarchy_response(
            summary.effective_hierarchy
        ),
        execution=_goal_execution_response(summary.execution),
        last_activity_at=activity_map.get(summary.goal.id),
        last_transition_at=transition_map.get(summary.goal.id),
        terminal_reason=terminal_reason,
        completion_context=completion_context,
        links=_goal_detail_links(summary.goal.id, summary.goal.project_id),
        next_steps=next_steps,
    )


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: str,
    data: GoalUpdate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> GoalResponse:
    """Update a goal."""
    status_enum = GoalStatus(data.status) if data.status else None
    horizon_enum = GoalHorizon(data.horizon) if data.horizon else None

    goal = await goal_service.update_goal(
        goal_id=goal_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        horizon=horizon_enum,
        target_date=data.target_date,
        owner=data.owner,
        product_id=data.product_id,
        project_id=data.project_id,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    owner_map = await resolve_owner_map(actor_service, [goal])
    return _goal_response(goal, owner_map)


@router.post("/goals/{goal_id}/complete")
async def complete_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Mark a goal as completed."""
    goal = await goal_service.complete_goal(goal_id)

    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    return {"status": "completed", "goal_id": goal.id}


@router.post("/goals/{goal_id}/archive")
async def archive_goal(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Archive a goal."""
    goal = await goal_service.archive_goal(goal_id)

    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")

    return {"status": "archived", "goal_id": goal.id}


@router.get("/goals/{goal_id}/summary", response_model=GoalSummaryResponse)
async def get_goal_summary(
    goal_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> GoalSummaryResponse:
    """Get goal summary with rollup metrics."""
    summary = await goal_service.get_goal_summary(goal_id)

    if summary is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    owner_map = await resolve_owner_map(actor_service, [summary.goal])
    activity_map = await goal_service.get_last_activity_map([summary.goal.id])
    transition_map = await goal_service.get_last_transition_map([summary.goal.id])
    terminal_reason = _goal_terminal_reason(
        summary.goal,
        effective_rollup=summary.effective_rollup,
        execution=summary.execution,
    )
    links = _goal_summary_links(summary.goal.id, summary.goal.project_id)
    next_steps = _goal_summary_next_steps(
        goal_id=summary.goal.id,
        project_id=summary.goal.project_id,
        focus_task_id=_goal_focus_task_id(summary.execution),
        terminal_reason=terminal_reason,
    )
    completion_context = _goal_completion_context(
        goal_id=summary.goal.id,
        project_id=summary.goal.project_id,
        terminal_reason=terminal_reason,
    )
    return GoalSummaryResponse(
        goal=_goal_response(summary.goal, owner_map),
        stats=GoalSummaryStatsResponse(
            objective_count=summary.objective_count,
            completed_objectives=summary.completed_objectives,
            key_result_count=summary.key_result_count,
            completed_key_results=summary.completed_key_results,
            average_progress=summary.average_progress,
        ),
        effective_rollup=_goal_effective_rollup_response(summary.effective_rollup),
        effective_hierarchy=_goal_effective_hierarchy_response(
            summary.effective_hierarchy
        ),
        execution=_goal_execution_response(summary.execution),
        terminal_reason=terminal_reason,
        completion_context=completion_context,
        last_activity_at=activity_map.get(summary.goal.id),
        last_transition_at=transition_map.get(summary.goal.id),
        links=links,
        next_steps=next_steps,
    )
