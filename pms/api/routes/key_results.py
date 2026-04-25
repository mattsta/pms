"""Key Results API routes."""

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service, get_goal_service
from pms.api.models import (
    CompletionContextResponse,
    KeyResultCreate,
    KeyResultDetailResponse,
    KeyResultEffectiveRollupResponse,
    KeyResultListItemResponse,
    KeyResultResponse,
    KeyResultUpdate,
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
from pms.services.goal_service import GoalService, key_result_lifecycle_terminal_reason

router = APIRouter()


def _key_result_response(
    key_result: object,
    owner_map: dict[str, object],
) -> KeyResultResponse:
    return KeyResultResponse(
        id=key_result.id,
        objective_id=key_result.objective_id,
        name=key_result.name,
        description=key_result.description,
        status=key_result.status.value,
        current_value=key_result.current_value,
        target_value=key_result.target_value,
        unit=key_result.unit,
        owner=actor_reference_payload(
            key_result.owner,
            owner_map,
            actor_id=key_result.owner_id,
        ),
        tags=list(key_result.tags),
        progress_percent=key_result.progress_percent,
        created_at=key_result.created_at,
        updated_at=key_result.updated_at,
    )


def _key_result_effective_rollup_response(
    key_result: object,
) -> KeyResultEffectiveRollupResponse:
    return KeyResultEffectiveRollupResponse(
        progress_percent=key_result.progress_percent,
        status=key_result.status.value,
        basis="stored_key_result",
        reason=None,
    )


def _key_result_links(
    *,
    key_result_id: str,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    include_guide: bool,
) -> dict[str, str]:
    links: dict[str, str] = {
        "self": f"/api/v1/key-results/{key_result_id}",
        "objective": f"/api/v1/objectives/{objective_id}",
        "objective_key_results": f"/api/v1/objectives/{objective_id}/key-results",
        "goal": f"/api/v1/goals/{goal_id}",
        "goal_summary": f"/api/v1/goals/{goal_id}/summary",
    }
    if project_id:
        links["project"] = f"/api/v1/projects/{project_id}"
    if include_guide:
        links["guide"] = "/api/v1/"
    return links


def _key_result_next_steps(
    *,
    key_result_id: str,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> list[str]:
    return normalize_next_steps(
        f"GET /api/v1/key-results/{key_result_id}",
        f"GET /api/v1/objectives/{objective_id}",
        f"GET /api/v1/objectives/{objective_id}/key-results",
        f"GET /api/v1/goals/{goal_id}",
        f"GET /api/v1/goals/{goal_id}/summary",
        f"GET /api/v1/projects/{project_id}" if project_id else "",
        (
            f"GET /api/v1/objectives/{objective_id}/key-results?status=completed"
            if terminal_reason is not None
            else ""
        ),
    )


def _key_result_completion_context(
    *,
    key_result_id: str,
    objective_id: str,
    goal_id: str,
    project_id: str | None,
    terminal_reason: str | None,
) -> CompletionContextResponse | None:
    if terminal_reason is None:
        return None
    return CompletionContextResponse(
        summary=f"This key result is terminal. {terminal_reason}.",
        next_steps=_key_result_next_steps(
            key_result_id=key_result_id,
            objective_id=objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    )


def _key_result_list_item_response(
    *,
    key_result: object,
    owner_map: dict[str, object],
    goal_id: str,
    project_id: str | None,
    last_activity_at: object | None,
    last_transition_at: object | None,
) -> KeyResultListItemResponse:
    terminal_reason = key_result_lifecycle_terminal_reason(key_result)
    return KeyResultListItemResponse(
        **_key_result_response(key_result, owner_map).model_dump(),
        goal_id=goal_id,
        project_id=project_id,
        effective_rollup=_key_result_effective_rollup_response(key_result),
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
        terminal_reason=terminal_reason,
        links=_key_result_links(
            key_result_id=key_result.id,
            objective_id=key_result.objective_id,
            goal_id=goal_id,
            project_id=project_id,
            include_guide=True,
        ),
        next_steps=_key_result_next_steps(
            key_result_id=key_result.id,
            objective_id=key_result.objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    )


def _key_result_detail_response(
    *,
    key_result: object,
    owner_map: dict[str, object],
    goal_id: str,
    project_id: str | None,
    last_activity_at: object | None,
    last_transition_at: object | None,
) -> KeyResultDetailResponse:
    list_payload = _key_result_list_item_response(
        key_result=key_result,
        owner_map=owner_map,
        goal_id=goal_id,
        project_id=project_id,
        last_activity_at=last_activity_at,
        last_transition_at=last_transition_at,
    )
    terminal_reason = key_result_lifecycle_terminal_reason(key_result)
    return KeyResultDetailResponse(
        **list_payload.model_dump(),
        completion_context=_key_result_completion_context(
            key_result_id=key_result.id,
            objective_id=key_result.objective_id,
            goal_id=goal_id,
            project_id=project_id,
            terminal_reason=terminal_reason,
        ),
    )


@router.post(
    "/objectives/{objective_id}/key-results",
    response_model=KeyResultResponse,
    status_code=201,
)
async def create_key_result(
    objective_id: str,
    data: KeyResultCreate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> KeyResultResponse:
    """Create a new key result for an objective."""
    key_result = await goal_service.create_key_result(
        objective_id=objective_id,
        name=data.name,
        description=data.description,
        current_value=data.current_value,
        target_value=data.target_value,
        unit=data.unit,
        owner=data.owner,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    owner_map = await resolve_owner_map(actor_service, [key_result])
    return _key_result_response(key_result, owner_map)


@router.get(
    "/objectives/{objective_id}/key-results",
    response_model=PaginatedResponse[KeyResultListItemResponse],
)
async def list_key_results(
    objective_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> PaginatedResponse[KeyResultResponse]:
    """List key results for an objective."""
    status_filter = GoalStatus(status) if status else None
    result = await goal_service.list_key_results(
        objective_id=objective_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    list_path = f"/api/v1/objectives/{objective_id}/key-results"
    self_path = build_query_path(list_path, params)
    next_path = next_page_path(
        path=list_path,
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        f"GET /api/v1/objectives/{objective_id}",
        "GET /api/v1/key-results/{key_result_id}",
        "PATCH /api/v1/key-results/{key_result_id}",
        "POST /api/v1/key-results/{key_result_id}/complete",
    )

    objective = await goal_service.get_objective(objective_id)
    goal = (
        await goal_service.get_goal(objective.goal_id)
        if objective is not None
        else None
    )
    goal_id = goal.id if goal is not None else objective.goal_id if objective else ""
    project_id = goal.project_id if goal is not None else None
    owner_map = await resolve_owner_map(actor_service, result.items)
    activity_map = await goal_service.get_key_result_last_activity_map(
        [key_result.id for key_result in result.items]
    )
    transition_map = await goal_service.get_key_result_last_transition_map(
        [key_result.id for key_result in result.items]
    )
    return {
        "items": [
            _key_result_list_item_response(
                key_result=key_result,
                owner_map=owner_map,
                goal_id=goal_id,
                project_id=project_id,
                last_activity_at=activity_map.get(key_result.id),
                last_transition_at=transition_map.get(key_result.id),
            )
            for key_result in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": {"objective_id": objective_id, **params},
    }


@router.get("/key-results/{key_result_id}", response_model=KeyResultDetailResponse)
async def get_key_result(
    key_result_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_READ)),
) -> KeyResultResponse:
    """Get a key result by ID."""
    key_result = await goal_service.get_key_result(key_result_id)

    if key_result is None:
        raise HTTPException(status_code=404, detail="Key result not found")

    objective = await goal_service.get_objective(key_result.objective_id)
    goal = (
        await goal_service.get_goal(objective.goal_id)
        if objective is not None
        else None
    )
    goal_id = goal.id if goal is not None else objective.goal_id if objective else ""
    project_id = goal.project_id if goal is not None else None
    owner_map = await resolve_owner_map(actor_service, [key_result])
    activity_map = await goal_service.get_key_result_last_activity_map([key_result_id])
    transition_map = await goal_service.get_key_result_last_transition_map(
        [key_result_id]
    )
    return _key_result_detail_response(
        key_result=key_result,
        owner_map=owner_map,
        goal_id=goal_id,
        project_id=project_id,
        last_activity_at=activity_map.get(key_result_id),
        last_transition_at=transition_map.get(key_result_id),
    )


@router.patch("/key-results/{key_result_id}", response_model=KeyResultResponse)
async def update_key_result(
    key_result_id: str,
    data: KeyResultUpdate,
    goal_service: GoalService = Depends(get_goal_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> KeyResultResponse:
    """Update a key result."""
    status_enum = GoalStatus(data.status) if data.status else None

    key_result = await goal_service.update_key_result(
        key_result_id=key_result_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        current_value=data.current_value,
        target_value=data.target_value,
        unit=data.unit,
        owner=data.owner,
        tags=data.tags,
        progress_percent=data.progress_percent,
    )

    if key_result is None:
        raise HTTPException(status_code=404, detail="Key result not found")

    owner_map = await resolve_owner_map(actor_service, [key_result])
    return _key_result_response(key_result, owner_map)


@router.post("/key-results/{key_result_id}/complete")
async def complete_key_result(
    key_result_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Mark a key result as completed."""
    key_result = await goal_service.complete_key_result(key_result_id)

    if key_result is None:
        raise HTTPException(status_code=404, detail="Key result not found")

    return {"status": "completed", "key_result_id": key_result.id}


@router.post("/key-results/{key_result_id}/archive")
async def archive_key_result(
    key_result_id: str,
    goal_service: GoalService = Depends(get_goal_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.GOALS_WRITE)),
) -> dict[str, str]:
    """Archive a key result."""
    key_result = await goal_service.archive_key_result(key_result_id)

    if key_result is None:
        raise HTTPException(status_code=404, detail="Key result not found")

    return {"status": "archived", "key_result_id": key_result.id}
