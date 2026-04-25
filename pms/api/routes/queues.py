"""API routes for saved searches and smart queues."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import (
    actor_reference_payload,
    checkout_payload,
    resolve_actor_reference_map,
)
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_actor_service,
    get_queue_service,
    get_saved_search_service,
)
from pms.api.models import (
    QueuePresetResponse,
    SavedSearchListResponse,
    SavedSearchRequest,
    SavedSearchResponse,
    SavedSearchRunResponse,
    SavedSearchUpdateRequest,
    TaskResponse,
)
from pms.api.routes.detail_contracts import build_task_detail_links
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.models.api_key import ApiKey
from pms.models.saved_search import SavedSearch
from pms.models.task import Task
from pms.services.actor_service import ActorService
from pms.services.queue_service import QueueService
from pms.services.saved_search_service import SavedSearchService

router = APIRouter()


def _task_to_response(
    task: Task,
    *,
    assignee_map: dict[str, Any] | None = None,
    checkout_actor_map: dict[str, Any] | None = None,
) -> TaskResponse:
    assignee = actor_reference_payload(
        task.assignee,
        assignee_map or {},
        actor_id=task.assignee_id,
    )
    checkout_actor = None
    if checkout_actor_map and task.checkout_actor_id:
        checkout_actor = checkout_actor_map.get(task.checkout_actor_id)
    links = build_task_detail_links(task.id)
    assignee_links = assignee.get("links", {}) if assignee is not None else {}
    actor_link = assignee_links.get("actor")
    if isinstance(actor_link, str) and actor_link:
        links["actor"] = actor_link
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
        parent_id=task.parent_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        complexity_points=task.complexity_points,
        actual_hours=task.actual_hours,
        current_progress_percent=task.current_progress_percent,
        assignee=assignee,
        checkout=checkout_payload(
            agent_session_id=task.checkout_agent_session_id,
            actor_obj=checkout_actor,
            checked_out_at=task.checked_out_at,
            lease_until=task.checkout_lease_until,
            version=task.checkout_version,
            expired=task.checkout_expired,
        ),
        workflow_id=task.workflow_id,
        current_state=task.current_state,
        created_at=task.created_at,
        updated_at=task.updated_at,
        links=links,
    )


def _saved_to_response(
    saved: SavedSearch,
    *,
    actor_map: dict[str, Any] | None = None,
) -> SavedSearchResponse:
    return SavedSearchResponse(
        id=saved.id,
        name=saved.name,
        description=saved.description,
        owner=actor_reference_payload(
            saved.owner,
            actor_map or {},
            actor_id=saved.owner_id,
        ),
        scope_type=saved.scope_type,
        scope_id=saved.scope_id,
        filters=saved.filters,
        sort_by=saved.sort_by,
        sort_dir=saved.sort_dir,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
        archived_at=saved.archived_at,
    )


@router.post("/queues", response_model=SavedSearchResponse, status_code=201)
async def create_saved_search(
    data: SavedSearchRequest,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> SavedSearchResponse:
    """Create a saved search queue."""
    saved = await service.create(
        name=data.name,
        description=data.description,
        owner=data.owner,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        filters=data.filters,
        sort_by=data.sort_by,
        sort_dir=data.sort_dir,
    )
    owner_map = await resolve_actor_reference_map(
        actor_service,
        [saved.owner_id, saved.owner],
    )
    return _saved_to_response(saved, actor_map=owner_map)


@router.get("/queues", response_model=SavedSearchListResponse)
async def list_saved_searches(
    owner: str | None = None,
    scope_type: str | None = None,
    scope_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    include_archived: bool = False,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> SavedSearchListResponse:
    """List saved searches."""
    result = await service.list(
        owner=owner,
        scope_type=scope_type,
        scope_id=scope_id,
        limit=limit,
        offset=offset,
        include_archived=include_archived,
    )
    params: QueryParamMap = {
        "owner": owner,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "limit": limit,
        "offset": offset,
        "include_archived": include_archived,
    }
    owner_refs: list[str] = []
    for item in result.items:
        if item.owner_id:
            owner_refs.append(item.owner_id)
        if item.owner:
            owner_refs.append(item.owner)
    owner_map = await resolve_actor_reference_map(actor_service, owner_refs)
    self_path = build_query_path("/api/v1/queues", params)
    next_path = next_page_path(
        path="/api/v1/queues",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/queues/{queue_id}",
        "GET /api/v1/queues/{queue_id}/run",
        "GET /api/v1/queues/presets",
    )
    return SavedSearchListResponse(
        items=[_saved_to_response(item, actor_map=owner_map) for item in result.items],
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
        links=paginated_links(self_path=self_path, next_path=next_path),
        next_steps=next_steps,
        params=params,
    )


@router.get("/queues/presets", response_model=list[QueuePresetResponse])
async def list_queue_presets(
    project_id: str | None = None,
    limit: int = 5,
    stale_days: int = 14,
    at_risk_days: int = 7,
    queue_service: QueueService = Depends(get_queue_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> list[QueuePresetResponse]:
    """List smart queue presets."""
    presets = await queue_service.list_presets(
        project_id=project_id,
        limit=limit,
        stale_days=stale_days,
        at_risk_days=at_risk_days,
    )
    base_params: QueryParamMap = {
        "project_id": project_id,
        "limit": limit,
        "stale_days": stale_days,
        "at_risk_days": at_risk_days,
    }
    assignee_refs: list[str] = []
    checkout_actor_map: dict[str, Any] = {}
    for summary in presets:
        for task in summary.items:
            if task.assignee_id:
                assignee_refs.append(task.assignee_id)
            if task.assignee:
                assignee_refs.append(task.assignee)
            if (
                task.checkout_actor_id
                and task.checkout_actor_id not in checkout_actor_map
            ):
                checkout_actor_map[
                    task.checkout_actor_id
                ] = await actor_service.get_actor(task.checkout_actor_id)
    assignee_map = await resolve_actor_reference_map(actor_service, assignee_refs)
    return [
        QueuePresetResponse(
            name=summary.name,
            description=summary.description,
            population="visible_operator" if project_id is None else "scoped_project",
            total_count=summary.total_count,
            items=[
                _task_to_response(
                    task,
                    assignee_map=assignee_map,
                    checkout_actor_map=checkout_actor_map,
                )
                for task in summary.items
            ],
            links={
                "self": build_query_path(
                    f"/api/v1/queues/presets/{summary.name}",
                    {**base_params, "offset": 0},
                ),
                "list": build_query_path("/api/v1/queues/presets", base_params),
                "queues": "/api/v1/queues",
                "guide": "/api/v1/",
            },
            next_steps=normalize_next_steps(
                f"GET /api/v1/queues/presets/{summary.name}",
                "GET /api/v1/tasks/search",
                "GET /api/v1/queues",
            ),
            params={**base_params, "preset": summary.name, "offset": 0},
        )
        for summary in presets
    ]


@router.get("/queues/presets/{preset}", response_model=QueuePresetResponse)
async def get_queue_preset(
    preset: str,
    project_id: str | None = None,
    limit: int = 10,
    offset: int = 0,
    stale_days: int = 14,
    at_risk_days: int = 7,
    queue_service: QueueService = Depends(get_queue_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> QueuePresetResponse:
    """Get a specific smart queue preset."""
    summary = await queue_service.get_preset(
        name=preset,
        project_id=project_id,
        limit=limit,
        offset=offset,
        stale_days=stale_days,
        at_risk_days=at_risk_days,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Queue preset not found")
    params: QueryParamMap = {
        "project_id": project_id,
        "limit": limit,
        "offset": offset,
        "stale_days": stale_days,
        "at_risk_days": at_risk_days,
    }
    assignee_refs: list[str] = []
    checkout_actor_map: dict[str, Any] = {}
    for task in summary.items:
        if task.assignee_id:
            assignee_refs.append(task.assignee_id)
        if task.assignee:
            assignee_refs.append(task.assignee)
        if task.checkout_actor_id and task.checkout_actor_id not in checkout_actor_map:
            checkout_actor_map[task.checkout_actor_id] = await actor_service.get_actor(
                task.checkout_actor_id
            )
    assignee_map = await resolve_actor_reference_map(actor_service, assignee_refs)
    preset_path = f"/api/v1/queues/presets/{summary.name}"
    self_path = build_query_path(preset_path, params)
    next_path = next_page_path(
        path=preset_path,
        params=params,
        total_count=summary.total_count,
        offset=offset,
        limit=limit,
    )
    return QueuePresetResponse(
        name=summary.name,
        description=summary.description,
        population="visible_operator" if project_id is None else "scoped_project",
        total_count=summary.total_count,
        items=[
            _task_to_response(
                task,
                assignee_map=assignee_map,
                checkout_actor_map=checkout_actor_map,
            )
            for task in summary.items
        ],
        links={
            "self": self_path,
            "next": next_path,
            "list": build_query_path(
                "/api/v1/queues/presets",
                {
                    "project_id": project_id,
                    "limit": limit,
                    "stale_days": stale_days,
                    "at_risk_days": at_risk_days,
                },
            ),
            "queues": "/api/v1/queues",
            "guide": "/api/v1/",
        },
        next_steps=normalize_next_steps(
            "GET /api/v1/tasks/search",
            "GET /api/v1/tasks/ready",
            "GET /api/v1/queues",
        ),
        params={**params, "preset": summary.name},
    )


@router.get("/queues/{queue_id}", response_model=SavedSearchResponse)
async def get_saved_search(
    queue_id: str,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> SavedSearchResponse:
    """Get a saved search by ID."""
    saved = await service.get(queue_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    owner_map = await resolve_actor_reference_map(
        actor_service,
        [saved.owner_id, saved.owner],
    )
    return _saved_to_response(saved, actor_map=owner_map)


@router.put("/queues/{queue_id}", response_model=SavedSearchResponse)
async def update_saved_search(
    queue_id: str,
    data: SavedSearchUpdateRequest,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> SavedSearchResponse:
    """Update a saved search."""
    saved = await service.update(
        search_id=queue_id,
        name=data.name,
        description=data.description,
        owner=data.owner,
        scope_type=data.scope_type,
        scope_id=data.scope_id,
        filters=data.filters,
        sort_by=data.sort_by,
        sort_dir=data.sort_dir,
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    owner_map = await resolve_actor_reference_map(
        actor_service,
        [saved.owner_id, saved.owner],
    )
    return _saved_to_response(saved, actor_map=owner_map)


@router.delete("/queues/{queue_id}")
async def delete_saved_search(
    queue_id: str,
    service: SavedSearchService = Depends(get_saved_search_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> dict[str, str]:
    """Delete a saved search."""
    deleted = await service.delete(queue_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return {"status": "deleted", "id": queue_id}


@router.post("/queues/{queue_id}/restore", response_model=SavedSearchResponse)
async def restore_saved_search(
    queue_id: str,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_WRITE)),
) -> SavedSearchResponse:
    """Restore a saved search."""
    saved = await service.restore(queue_id)
    if saved is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    owner_map = await resolve_actor_reference_map(
        actor_service,
        [saved.owner_id, saved.owner],
    )
    return _saved_to_response(saved, actor_map=owner_map)


@router.get("/queues/{queue_id}/run", response_model=SavedSearchRunResponse)
async def run_saved_search(
    queue_id: str,
    limit: int = 100,
    offset: int = 0,
    service: SavedSearchService = Depends(get_saved_search_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TASKS_READ)),
) -> SavedSearchRunResponse:
    """Run a saved search and return matching tasks."""
    run = await service.run(queue_id, limit=limit, offset=offset)
    if run is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    owner_map = await resolve_actor_reference_map(
        actor_service,
        [run.saved_search.owner_id, run.saved_search.owner],
    )
    assignee_refs: list[str] = []
    checkout_actor_map: dict[str, Any] = {}
    for task in run.result.items:
        if task.assignee_id:
            assignee_refs.append(task.assignee_id)
        if task.assignee:
            assignee_refs.append(task.assignee)
        if task.checkout_actor_id and task.checkout_actor_id not in checkout_actor_map:
            checkout_actor_map[task.checkout_actor_id] = await actor_service.get_actor(
                task.checkout_actor_id
            )
    assignee_map = await resolve_actor_reference_map(actor_service, assignee_refs)
    params: QueryParamMap = {
        "limit": limit,
        "offset": offset,
    }
    run_path = f"/api/v1/queues/{queue_id}/run"
    self_path = build_query_path(run_path, params)
    next_path = next_page_path(
        path=run_path,
        params=params,
        total_count=run.result.total_count,
        offset=run.result.offset,
        limit=run.result.limit,
    )
    links = paginated_links(self_path=self_path, next_path=next_path)
    links["queue"] = f"/api/v1/queues/{queue_id}"
    next_steps = normalize_next_steps(
        "GET /api/v1/queues/{queue_id}",
        "GET /api/v1/queues/{queue_id}/run",
        "GET /api/v1/tasks/search?query=<term>",
    )
    return SavedSearchRunResponse(
        saved_search=_saved_to_response(run.saved_search, actor_map=owner_map),
        items=[
            _task_to_response(
                task,
                assignee_map=assignee_map,
                checkout_actor_map=checkout_actor_map,
            )
            for task in run.result.items
        ],
        total_count=run.result.total_count,
        offset=run.result.offset,
        limit=run.result.limit,
        links=links,
        next_steps=next_steps,
        params={"queue_id": queue_id, **params},
    )
