"""Objectives API routes."""

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service, get_goal_service
from pms.api.models import (
    ObjectiveCreate,
    ObjectiveDetailResponse,
    ObjectiveEffectiveHierarchyResponse,
    ObjectiveEffectiveRollupResponse,
    ObjectiveListItemResponse,
    ObjectiveResponse,
    ObjectiveSummaryStatsResponse,
    ObjectiveUpdate,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models import GoalStatus
from pms.models.api_key import ApiKey
from pms.services.actor_service import ActorService
from pms.services.goal_service import GoalService, objective_lifecycle_terminal_reason

router = APIRouter()


def _objective_response(
    objective: object,
    owner_map: dict[str, object],
) -> ObjectiveResponse:
    return ObjectiveResponse(
        id=objective.id,
        goal_id=objective.goal_id,
        name=objective.name,
        description=objective.description,
        status=objective.status.value,
        target_date=objective.target_date,
        owner=actor_reference_payload(
            objective.owner,
            owner_map,
            actor_id=objective.owner_id,
        ),
        tags=list(objective.tags),
        progress_percent=objective.progress_percent,
        workflow_id=objective.workflow_id,
        current_state=objective.current_state,
        created_at=objective.created_at,
        updated_at=objective.updated_at,
    )


def _objective_effective_rollup_response(
    effective_rollup: object | None,
) -> ObjectiveEffectiveRollupResponse | None:
    if effective_rollup is None:
        return None
    return ObjectiveEffectiveRollupResponse(
        progress_percent=effective_rollup.progress_percent,
        status=effective_rollup.status,
        basis=effective_rollup.basis,
        reason=effective_rollup.reason,
    )


def _objective_effective_hierarchy_response(
    effective_hierarchy: object | None,
) -> ObjectiveEffectiveHierarchyResponse | None:
    if effective_hierarchy is None:
        return None
    return ObjectiveEffectiveHierarchyResponse(
        key_result_count=effective_hierarchy.key_result_count,
        completed_key_results=effective_hierarchy.completed_key_results,
        average_progress=effective_hierarchy.average_progress,
        basis=effective_hierarchy.basis,
        reason=effective_hierarchy.reason,
    )


def _objective_links(
    *,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    include_guide: bool,
) -> dict[str, str]:
    links: dict[str, str] = {
        "self": f"/api/v1/objectives/{objective_id}",
        "goal": f"/api/v1/goals/{goal_id}",
        "goal_summary": f"/api/v1/goals/{goal_id}/summary",
        "key_results": f"/api/v1/objectives/{objective_id}/key-results",
    }
    if project_id:
        links["project"] = f"/api/v1/projects/{project_id}"
    if include_guide:
        links["guide"] = "/api/v1/"
    return links


def _objective_next_steps(
    *,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> list[str]:
    return normalize_next_steps(
        f"GET /api/v1/objectives/{objective_id}",
        f"GET /api/v1/objectives/{objective_id}/key-results",
        f"GET /api/v1/goals/{goal_id}",
        f"GET /api/v1/goals/{goal_id}/summary",
        f"GET /api/v1/projects/{project_id}" if project_id else "",
        (
            f"GET /api/v1/goals/{goal_id}/objectives?status=completed"
            if terminal_reason is not None
            else ""
        ),
    )


def _objective_completion_context(
    *,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> dict[str, object] | None:
    if terminal_reason is None:
        return None
    return {
        "summary": f"This objective is terminal. {terminal_reason}.",
        "next_steps": _objective_next_steps(
            objective_id=objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    }


def _objective_list_item_response(
    *,
    objective: object,
    owner_map: dict[str, object],
    project_id: str | None,
    summary: object,
    last_activity_at: object | None,
    last_transition_at: object | None,
) -> ObjectiveListItemResponse:
    effective_rollup = _objective_effective_rollup_response(summary.effective_rollup)
    effective_hierarchy = _objective_effective_hierarchy_response(
        summary.effective_hierarchy
    )
    terminal_reason = objective_lifecycle_terminal_reason(
        objective,
        effective_rollup=summary.effective_rollup,
    )
    return ObjectiveListItemResponse(
        **_objective_response(objective, owner_map).model_dump(),
        project_id=project_id,
        effective_rollup=effective_rollup,
        effective_hierarchy=effective_hierarchy,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        terminal_reason=terminal_reason,
        links=_objective_links(
            objective_id=objective.id,
            goal_id=objective.goal_id,
            project_id=project_id,
            include_guide=True,
        ),
        next_steps=_objective_next_steps(
            objective_id=objective.id,
            goal_id=objective.goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    )


def _objective_detail_response(
    *,
    objective: object,
    owner_map: dict[str, object],
    project_id: str | None,
    summary: object,
    last_activity_at: object | None,
    last_transition_at: object | None,
) -> ObjectiveDetailResponse:
    list_payload = _objective_list_item_response(
        objective=objective,
        owner_map=owner_map,
        project_id=project_id,
        summary=summary,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
    )
    terminal_reason = objective_lifecycle_terminal_reason(
        objective,
        effective_rollup=summary.effective_rollup,
    )
    return ObjectiveDetailResponse(
        **list_payload.model_dump(),
        stats=ObjectiveSummaryStatsResponse(
            key_result_count=summary.key_result_count,
            completed_key_results=summary.completed_key_results,
            average_progress=summary.average_progress,
        ),
        completion_context=_objective_completion_context(
            objective_id=objective.id,
            goal_id=objective.goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    )


@router.post(
    "/goals/{goal_id}/objectives", response_model=ObjectiveResponse, status_code=201
)
async def create_objective(
    goal_id: str,
    data: ObjectiveCreate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> ObjectiveResponse:
    """Create a new objective for a goal."""
    objective = await goal_service.create_objective(
        goal_id=goal_id,
        name=data.name,
        description=data.description,
        target_date=data.target_date,
        owner=data.owner,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    owner_map = await resolve_owner_map(actor_service, [objective])
    return _objective_response(objective, owner_map)


@router.get(
    "/goals/{goal_id}/objectives",
    response_model=PaginatedResponse[ObjectiveListItemResponse],
)
async def list_objectives(
    goal_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> PaginatedResponse[ObjectiveListItemResponse]:
    """List objectives for a goal."""
    status_filter = GoalStatus(status) if status else None
    result = await goal_service.list_objectives(
        goal_id=goal_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    list_path = f"/api/v1/goals/{goal_id}/objectives"
    self_path = build_query_path(list_path, params)
    next_path = next_page_path(
        path=list_path,
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/objectives/{objective_id}",
        "GET /api/v1/objectives/{objective_id}/key-results",
        "PATCH /api/v1/objectives/{objective_id}",
    )

    goal = await goal_service.get_goal(goal_id)
    project_id = goal.project_id if goal is not None else None
    owner_map = await resolve_owner_map(actor_service, result.items)
    summaries = await goal_service.get_objective_summaries_for_objectives(result.items)
    activity_map = await goal_service.get_objective_last_activity_map(
        [objective.id for objective in result.items]
    )
    transition_map = await goal_service.get_objective_last_transition_map(
        [objective.id for objective in result.items]
    )
    return {
        "items": [
            _objective_list_item_response(
                objective=objective,
                owner_map=owner_map,
                project_id=project_id,
                summary=summaries[objective.id],
                last_activity_at=activity_map.get(objective.id),
                last_transition_at=transition_map.get(objective.id),
            )
            for objective in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": {"goal_id": goal_id, **params},
    }


@router.get("/objectives/{objective_id}", response_model=ObjectiveDetailResponse)
async def get_objective(
    objective_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> ObjectiveDetailResponse:
    """Get an objective by ID."""
    objective = await goal_service.get_objective(objective_id)

    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    summary = await goal_service.get_objective_summary(objective_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    goal = await goal_service.get_goal(objective.goal_id)
    project_id = goal.project_id if goal is not None else None
    owner_map = await resolve_owner_map(actor_service, [objective])
    activity_map = await goal_service.get_objective_last_activity_map([objective_id])
    transition_map = await goal_service.get_objective_last_transition_map(
        [objective_id]
    )
    return _objective_detail_response(
        objective=objective,
        owner_map=owner_map,
        project_id=project_id,
        summary=summary,
        last_activity_at=activity_map.get(objective_id),
        last_transition_at=transition_map.get(objective_id),
    )


@router.patch("/objectives/{objective_id}", response_model=ObjectiveResponse)
async def update_objective(
    objective_id: str,
    data: ObjectiveUpdate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> ObjectiveResponse:
    """Update an objective."""
    status_enum = GoalStatus(data.status) if data.status else None

    objective = await goal_service.update_objective(
        objective_id=objective_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        target_date=data.target_date,
        owner=data.owner,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    owner_map = await resolve_owner_map(actor_service, [objective])
    return _objective_response(objective, owner_map)


@router.post("/objectives/{objective_id}/complete")
async def complete_objective(
    objective_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Mark an objective as completed."""
    objective = await goal_service.complete_objective(objective_id)

    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    return {"status": "completed", "objective_id": objective.id}


@router.post("/objectives/{objective_id}/archive")
async def archive_objective(
    objective_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Archive an objective."""
    objective = await goal_service.archive_objective(objective_id)

    if objective is None:
        raise HTTPException(status_code=404, detail="Objective not found")

    return {"status": "archived", "objective_id": objective.id}
