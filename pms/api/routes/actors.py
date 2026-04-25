"""Actor identity graph API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import (
    actor_reference_payload,
    checkout_payload,
)
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service
from pms.api.models import (
    ActorAliasCreate,
    ActorAliasResponse,
    ActorCreate,
    ActorGraphResponse,
    ActorMembershipCreate,
    ActorMembershipResponse,
    ActorResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models import ActorKind, ActorMembershipRole, ActorStatus
from pms.models.api_key import ApiKey
from pms.services.actor_service import ActorService

router = APIRouter()


def _actor_response(
    actor: object,
    *,
    last_activity_at: object | None = None,
    last_transition_at: object | None = None,
) -> ActorResponse:
    payload = actor.to_dict()  # type: ignore[attr-defined]
    payload["last_activity_at"] = last_activity_at
    payload["last_transition_at"] = last_transition_at
    return ActorResponse(**payload)


def _actor_alias_response(alias: object) -> ActorAliasResponse:
    return ActorAliasResponse(**alias.to_dict())  # type: ignore[arg-type]


def _actor_membership_response(membership: object) -> ActorMembershipResponse:
    return ActorMembershipResponse(**membership.to_dict())  # type: ignore[arg-type]


def _owned_entity_path(kind: str, entity_id: str) -> str | None:
    path_map = {
        "goals": f"/api/v1/goals/{entity_id}",
        "objectives": f"/api/v1/objectives/{entity_id}",
        "key_results": f"/api/v1/key_results/{entity_id}",
        "products": f"/api/v1/products/{entity_id}",
        "organizations": f"/api/v1/organizations/{entity_id}",
        "teams": f"/api/v1/teams/{entity_id}",
        "portfolios": f"/api/v1/portfolios/{entity_id}",
        "programs": f"/api/v1/programs/{entity_id}",
        "queues": f"/api/v1/queues/{entity_id}",
    }
    return path_map.get(kind)


@router.post("/actors", response_model=ActorResponse, status_code=201)
async def create_actor(
    data: ActorCreate,
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ACTORS_WRITE)),
) -> ActorResponse:
    """Create a canonical actor."""
    try:
        actor = await actor_service.create_actor(
            name=data.name,
            kind=ActorKind(data.kind),
            handle=data.handle,
            description=data.description,
            tags=data.tags,
            metadata=data.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _actor_response(actor)


@router.get("/actors")
async def list_actors(
    kind: str | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ACTORS_READ)),
) -> PaginatedResponse[ActorResponse]:
    """List actors."""
    kind_filter = ActorKind(kind) if kind else None
    status_filter = ActorStatus(status) if status else None
    result = await actor_service.list_actors(
        kind=kind_filter,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    activity_map = await actor_service.get_last_activity_map(
        [actor.id for actor in result.items]
    )
    transition_map = await actor_service.get_last_transition_map(
        [actor.id for actor in result.items]
    )
    params: QueryParamMap = {
        "kind": kind,
        "status": status,
        "limit": result.limit,
        "offset": result.offset,
    }
    self_path = build_query_path("/api/v1/actors", params)
    next_path = next_page_path(
        path="/api/v1/actors",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    return {
        "items": [
            _actor_response(
                actor,
                last_activity_at=activity_map.get(actor.id),
                last_transition_at=transition_map.get(actor.id),
            )
            for actor in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": normalize_next_steps(
            "GET /api/v1/actors/{actor}",
            "POST /api/v1/actors/{actor}/aliases",
            "POST /api/v1/actors/{actor}/memberships",
        ),
        "params": params,
    }


@router.get("/actors/{actor}", response_model=ActorGraphResponse)
async def get_actor(
    actor: str,
    include_inherited: bool = True,
    task_limit: int = 25,
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ACTORS_READ)),
) -> ActorGraphResponse:
    """Get actor graph and workload summary."""
    snapshot = await actor_service.get_actor_graph(
        actor,
        include_inherited=include_inherited,
        task_limit=task_limit,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Actor not found")

    parent_actors: dict[str, object] = {}
    for membership in snapshot.parent_memberships:
        actor = await actor_service.get_actor(membership.parent_actor_id)
        if actor is not None:
            parent_actors[membership.parent_actor_id] = actor

    child_actors: dict[str, object] = {}
    for membership in snapshot.child_memberships:
        actor = await actor_service.get_actor(membership.member_actor_id)
        if actor is not None:
            child_actors[membership.member_actor_id] = actor

    assignee_map: dict[str, object] = {}
    if snapshot.assigned_tasks is not None:
        for task in snapshot.assigned_tasks.items:
            if task.assignee_id and task.assignee_id not in assignee_map:
                actor = await actor_service.get_actor(task.assignee_id)
                if actor is not None:
                    assignee_map[task.assignee_id] = actor
                    assignee_map[actor.handle] = actor
            elif task.assignee and task.assignee not in assignee_map:
                actor = await actor_service.get_actor(task.assignee)
                if actor is not None:
                    assignee_map[task.assignee] = actor
                    assignee_map[actor.id] = actor

    checkout_actor_map: dict[str, object] = {}
    if snapshot.checked_out_tasks is not None:
        for task in snapshot.checked_out_tasks.items:
            if (
                task.checkout_actor_id
                and task.checkout_actor_id not in checkout_actor_map
            ):
                actor = await actor_service.get_actor(task.checkout_actor_id)
                if actor is not None:
                    checkout_actor_map[task.checkout_actor_id] = actor

    workload = snapshot.workload.to_dict() if snapshot.workload is not None else {}
    if snapshot.assigned_tasks is not None:
        workload.update(
            {
                "assignment_scope": (
                    "direct_and_inherited" if include_inherited else "direct_only"
                ),
                "assigned_tasks": snapshot.assigned_tasks.total_count,
                "tasks": [
                    {
                        "id": task.id,
                        "title": task.title,
                        "status": task.status.value,
                        "project_id": task.project_id,
                        "assignee": actor_reference_payload(
                            task.assignee,
                            assignee_map,
                            actor_id=task.assignee_id,
                        ),
                        "links": {
                            "self": f"/api/v1/tasks/{task.id}",
                            "project": (
                                f"/api/v1/projects/{task.project_id}"
                                if task.project_id
                                else None
                            ),
                        },
                    }
                    for task in snapshot.assigned_tasks.items
                ],
            }
        )
    if snapshot.checkout_summary is not None:
        workload["checkout_scope"] = "direct_only"
        workload["checkouts"] = snapshot.checkout_summary.to_dict()
    if snapshot.checked_out_tasks is not None:
        workload["checkout_tasks"] = [
            {
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "project_id": task.project_id,
                "checkout": checkout_payload(
                    agent_session_id=task.checkout_agent_session_id,
                    actor_obj=(
                        checkout_actor_map.get(task.checkout_actor_id)
                        if task.checkout_actor_id
                        else None
                    ),
                    checked_out_at=task.checked_out_at,
                    lease_until=task.checkout_lease_until,
                    expired=task.checkout_expired,
                ),
                "links": {
                    "self": f"/api/v1/tasks/{task.id}",
                    "project": (
                        f"/api/v1/projects/{task.project_id}"
                        if task.project_id
                        else None
                    ),
                    "status": (
                        f"/api/v1/checkout/status?agent_session_id={task.checkout_agent_session_id}"
                        if task.checkout_agent_session_id
                        else None
                    ),
                },
            }
            for task in snapshot.checked_out_tasks.items
        ]

    ownership = snapshot.ownership or {"counts": {"total_owned": 0}, "items": {}}
    ownership_items: dict[str, list[dict[str, object | None]]] = {}
    for kind, items in ownership.get("items", {}).items():
        ownership_items[kind] = []
        for item in items:
            self_path = _owned_entity_path(kind, item["id"])
            ownership_items[kind].append(
                {
                    **item,
                    "links": {
                        "self": self_path,
                        "actor": f"/api/v1/actors/{snapshot.actor.handle}",
                    },
                }
            )

    project_workloads = [
        {
            **item,
            "links": {
                "project": (
                    f"/api/v1/projects/{item['project_id']}"
                    if item.get("project_id")
                    else None
                ),
                "tasks": (
                    f"/api/v1/tasks/search?assignee={snapshot.actor.handle}&project_id={item['project_id']}"
                    if item.get("project_id")
                    else None
                ),
            },
        }
        for item in snapshot.project_workloads
    ]

    graph_links = {
        "self": f"/api/v1/actors/{snapshot.actor.handle}",
        "tasks_list": f"/api/v1/tasks/search?assignee={snapshot.actor.handle}",
        "actors": "/api/v1/actors",
        "project": (
            project_workloads[0]["links"]["project"] if project_workloads else None
        ),
        "goal": (
            ownership_items["goals"][0]["links"]["self"]
            if ownership_items.get("goals")
            else None
        ),
        "queue": (
            ownership_items["queues"][0]["links"]["self"]
            if ownership_items.get("queues")
            else None
        ),
    }

    return ActorGraphResponse(
        actor=_actor_response(
            snapshot.actor,
            last_activity_at=snapshot.last_activity_at,
            last_transition_at=snapshot.last_transition_at,
        ),
        last_activity_at=snapshot.last_activity_at,
        last_transition_at=snapshot.last_transition_at,
        aliases=[_actor_alias_response(alias) for alias in snapshot.aliases],
        memberships={
            "parents": [
                {
                    "membership": _actor_membership_response(membership).model_dump(),
                    "actor": _actor_response(
                        parent_actors[membership.parent_actor_id]
                    ).model_dump(),
                }
                for membership in snapshot.parent_memberships
                if membership.parent_actor_id in parent_actors
            ],
            "children": [
                {
                    "membership": _actor_membership_response(membership).model_dump(),
                    "actor": _actor_response(
                        child_actors[membership.member_actor_id]
                    ).model_dump(),
                }
                for membership in snapshot.child_memberships
                if membership.member_actor_id in child_actors
            ],
        },
        workload=workload,
        ownership={
            "counts": ownership.get("counts", {}),
            "items": ownership_items,
        },
        project_workloads=project_workloads,
        graph_navigation={
            "basis": "actor",
            "actor_handle": snapshot.actor.handle,
            "links": graph_links,
        },
        links={
            "self": f"/api/v1/actors/{snapshot.actor.handle}",
            "tasks": f"/api/v1/tasks/search?assignee={snapshot.actor.handle}",
            "actors": "/api/v1/actors",
        },
        next_steps=normalize_next_steps(
            f"GET /api/v1/tasks/search?assignee={snapshot.actor.handle}",
            f"POST /api/v1/actors/{snapshot.actor.handle}/aliases",
            f"POST /api/v1/actors/{snapshot.actor.handle}/memberships",
        ),
    )


@router.post(
    "/actors/{actor}/aliases", response_model=ActorAliasResponse, status_code=201
)
async def add_actor_alias(
    actor: str,
    data: ActorAliasCreate,
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ACTORS_WRITE)),
) -> ActorAliasResponse:
    """Add an alias to an actor."""
    try:
        alias = await actor_service.add_alias(actor, data.alias)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _actor_alias_response(alias)


@router.post(
    "/actors/{actor}/memberships",
    response_model=ActorMembershipResponse,
    status_code=201,
)
async def add_actor_membership(
    actor: str,
    data: ActorMembershipCreate,
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ACTORS_WRITE)),
) -> ActorMembershipResponse:
    """Add a membership edge beneath the given actor."""
    try:
        membership = await actor_service.add_membership(
            parent_actor=actor,
            member_actor=data.member,
            role=ActorMembershipRole(data.role),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _actor_membership_response(membership)
