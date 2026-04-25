"""Program API routes."""

from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_actor_service,
    get_program_service,
    get_project_service,
    get_task_service,
    get_work_snapshot_service,
)
from pms.api.models import ProgramCreate, ProgramResponse, ProgramUpdate
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject, PaginatedResponse
from pms.models import ProgramStatus
from pms.models.api_key import ApiKey
from pms.models.value_contracts import RiskLevel
from pms.services.actor_service import ActorService
from pms.services.hierarchy_scope_service import HierarchyScopeService
from pms.services.program_service import ProgramService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.work_snapshot_service import WorkSnapshotService

router = APIRouter()


async def _program_response(
    program: object,
    owner_map: dict[str, object],
    hierarchy_service: HierarchyScopeService,
) -> ProgramResponse:
    snapshot = await hierarchy_service.get_program_snapshot(
        program.id,
        limit=100000,
        offset=0,
    )
    return ProgramResponse(
        id=program.id,
        org_id=program.org_id,
        portfolio_id=program.portfolio_id,
        name=program.name,
        description=program.description,
        status=program.status.value,
        owner=actor_reference_payload(
            program.owner,
            owner_map,
            actor_id=program.owner_id,
        ),
        project_ids=[project.id for project in snapshot.projects.items],
        goal_ids=list(program.goal_ids),
        objective_ids=list(program.objective_ids),
        effective_goal_ids=[goal.id for goal in snapshot.goals.items],
        effective_objective_ids=[
            objective.id for objective in snapshot.objectives.items
        ],
        tags=list(program.tags),
        created_at=program.created_at,
        updated_at=program.updated_at,
    )


class ProgramDashboardItemPayload(TypedDict, total=False):
    """Program dashboard item payload."""

    program: ProgramResponse
    stats: JsonObject
    risk_level: RiskLevel
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    last_reviewed_at: datetime | None
    digest: JsonObject | None
    next_actions: list[JsonObject]
    evidence: JsonObject
    retention: JsonObject | None


class ProgramDashboardTotalsPayload(TypedDict):
    """Program dashboard totals payload."""

    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class ProgramDashboardResponsePayload(TypedDict):
    """Program dashboard response payload."""

    items: list[ProgramDashboardItemPayload]
    totals: ProgramDashboardTotalsPayload
    total_count: int
    offset: int
    limit: int
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


class ProgramSummaryPayload(TypedDict):
    """Program summary payload."""

    program: ProgramResponse
    stats: JsonObject
    risk_level: RiskLevel
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


@router.post("/programs", response_model=ProgramResponse, status_code=201)
async def create_program(
    data: ProgramCreate,
    program_service: ProgramService = Depends(get_program_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_WRITE)),
) -> ProgramResponse:
    """Create a new program."""
    program = await program_service.create_program(
        name=data.name,
        org_id=data.org_id,
        portfolio_id=data.portfolio_id,
        description=data.description,
        owner=data.owner,
        project_ids=data.project_ids,
        goal_ids=data.goal_ids,
        objective_ids=data.objective_ids,
        tags=data.tags,
    )

    owner_map = await resolve_owner_map(actor_service, [program])
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    return await _program_response(program, owner_map, hierarchy_service)


@router.get("/programs")
async def list_programs(
    status: str | None = None,
    org_id: str | None = None,
    portfolio_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    program_service: ProgramService = Depends(get_program_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_READ)),
) -> PaginatedResponse[ProgramResponse]:
    """List programs."""
    status_filter = ProgramStatus(status) if status else None
    result = await program_service.list_programs(
        status=status_filter,
        org_id=org_id,
        portfolio_id=portfolio_id,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "org_id": org_id,
        "portfolio_id": portfolio_id,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/programs", params)
    next_path = next_page_path(
        path="/api/v1/programs",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/programs/{program_id}",
        "GET /api/v1/programs/{program_id}/summary",
        "GET /api/v1/programs/dashboard?portfolio_id=<portfolio_id>",
    )

    owner_map = await resolve_owner_map(actor_service, result.items)
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    return {
        "items": [
            await _program_response(p, owner_map, hierarchy_service)
            for p in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/programs/dashboard")
async def get_program_dashboard(
    status: str | None = None,
    org_id: str | None = None,
    portfolio_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    include_digest: bool = True,
    include_next_actions: bool = True,
    include_evidence: bool = True,
    include_retention: bool = True,
    next_limit: int = 3,
    program_service: ProgramService = Depends(get_program_service),
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_READ)),
) -> ProgramDashboardResponsePayload:
    """Get program dashboard rollups."""
    status_filter = ProgramStatus(status) if status else None
    dashboard = await program_service.get_program_dashboard(
        status=status_filter,
        org_id=org_id,
        portfolio_id=portfolio_id,
        limit=limit,
        offset=offset,
    )

    owner_map = await resolve_owner_map(
        actor_service,
        [item.program for item in dashboard.items],
    )
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    items: list[ProgramDashboardItemPayload] = []
    for item in dashboard.items:
        digest_payload = None
        last_reviewed_at = None
        next_actions: list[JsonObject] = []
        usage_result = None
        if include_digest:
            digest_result = await snapshot_service.get_digest(
                "program", item.program.id
            )
            if digest_result:
                digest_payload = digest_result.digest.to_dict()
                last_reviewed_at = digest_result.last_reviewed_at
        if include_evidence or include_retention:
            usage_result = await snapshot_service.get_usage_summary(
                "program", item.program.id
            )
            if usage_result and last_reviewed_at is None:
                last_reviewed_at = usage_result.last_reviewed_at
        if include_next_actions:
            next_actions = await snapshot_service.get_next_actions(
                "program",
                item.program.id,
                task_service=task_service,
                project_service=project_service,
                limit=next_limit,
            )

        payload: ProgramDashboardItemPayload = {
            "program": await _program_response(
                item.program,
                owner_map,
                hierarchy_service,
            ),
            "stats": item.stats.to_dict(),
            "risk_level": item.risk_level,
            "last_activity_at": item.last_activity_at,
            "last_transition_at": item.last_transition_at,
        }
        if include_digest:
            payload["last_reviewed_at"] = last_reviewed_at
            payload["digest"] = digest_payload
        if include_next_actions:
            payload["next_actions"] = next_actions
        if include_evidence and usage_result:
            payload["last_reviewed_at"] = last_reviewed_at
            payload["evidence"] = usage_result.evidence.to_dict()
        if include_retention:
            payload["retention"] = usage_result.retention if usage_result else None
        items.append(payload)

    params: QueryParamMap = {
        "status": status,
        "org_id": org_id,
        "portfolio_id": portfolio_id,
        "limit": limit,
        "offset": offset,
        "include_digest": include_digest,
        "include_next_actions": include_next_actions,
        "include_evidence": include_evidence,
        "include_retention": include_retention,
        "next_limit": next_limit,
    }
    self_path = build_query_path("/api/v1/programs/dashboard", params)
    links: JsonObject = {
        "self": self_path,
        "portfolio_dashboard": "/api/v1/portfolios/dashboard",
        "organization_dashboard": "/api/v1/organizations/dashboard",
        "work_daily_template": (
            "/api/v1/work-snapshots/program/{program_id}/daily?view=detail"
        ),
    }
    next_steps: list[str] = [
        "GET /api/v1/work-snapshots/program/<program_id>/daily?view=detail",
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
        "GET /api/v1/organizations/dashboard",
    ]

    return {
        "items": items,
        "totals": {
            "total_programs": dashboard.total_programs,
            "total_projects": dashboard.total_projects,
            "total_goals": dashboard.total_goals,
            "total_objectives": dashboard.total_objectives,
            "total_tasks": dashboard.total_tasks,
            "blocked_tasks": dashboard.blocked_tasks,
        },
        "total_count": dashboard.total_programs,
        "offset": offset,
        "limit": limit,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/programs/{program_id}", response_model=ProgramResponse)
async def get_program(
    program_id: str,
    program_service: ProgramService = Depends(get_program_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_READ)),
) -> ProgramResponse:
    """Get program by ID."""
    program = await program_service.get_program(program_id)
    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")

    owner_map = await resolve_owner_map(actor_service, [program])
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    return await _program_response(program, owner_map, hierarchy_service)


@router.patch("/programs/{program_id}", response_model=ProgramResponse)
async def update_program(
    program_id: str,
    data: ProgramUpdate,
    program_service: ProgramService = Depends(get_program_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_WRITE)),
) -> ProgramResponse:
    """Update program details."""
    status_enum = ProgramStatus(data.status) if data.status else None
    program = await program_service.update_program(
        program_id=program_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        owner=data.owner,
        project_ids=data.project_ids,
        goal_ids=data.goal_ids,
        objective_ids=data.objective_ids,
        tags=data.tags,
    )

    if program is None:
        raise HTTPException(status_code=404, detail="Program not found")

    owner_map = await resolve_owner_map(actor_service, [program])
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    return await _program_response(program, owner_map, hierarchy_service)


@router.get("/programs/{program_id}/summary")
async def get_program_summary(
    program_id: str,
    program_service: ProgramService = Depends(get_program_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PROGRAMS_READ)),
) -> ProgramSummaryPayload:
    """Get program summary with rollups."""
    summary = await program_service.get_program_summary(program_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Program not found")
    params: QueryParamMap = {"program_id": program_id}
    links: JsonObject = {
        "self": build_query_path(f"/api/v1/programs/{program_id}/summary", {}),
        "program": f"/api/v1/programs/{program_id}",
        "dashboard": build_query_path(
            "/api/v1/programs/dashboard",
            {
                "org_id": summary.program.org_id,
                "portfolio_id": summary.program.portfolio_id,
                "limit": 50,
                "offset": 0,
            },
        ),
        "work_daily": f"/api/v1/work-snapshots/program/{program_id}/daily?view=detail",
    }
    if summary.program.portfolio_id:
        links["portfolio_dashboard"] = build_query_path(
            "/api/v1/portfolios/dashboard",
            {
                "org_id": summary.program.org_id,
                "limit": 50,
                "offset": 0,
            },
        )
    if summary.program.org_id:
        links["organization_dashboard"] = build_query_path(
            "/api/v1/organizations/dashboard",
            {"status": "active", "limit": 50, "offset": 0},
        )
    next_steps = normalize_next_steps(
        "GET /api/v1/programs/dashboard?portfolio_id=<portfolio_id>",
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
        "GET /api/v1/work-snapshots/program/<program_id>/daily?view=detail",
    )

    owner_map = await resolve_owner_map(actor_service, [summary.program])
    hierarchy_service = HierarchyScopeService(
        program_service.db,
        program_service.events,
        program_service.revisions,
        program_service.metrics,
    )
    return {
        "program": await _program_response(
            summary.program,
            owner_map,
            hierarchy_service,
        ),
        "stats": summary.stats.to_dict(),
        "risk_level": summary.risk_level,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }
