"""Organization API routes."""

from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import (
    actor_reference_payload,
    member_payloads,
    resolve_actor_reference_map,
)
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_actor_service,
    get_organization_service,
    get_project_service,
    get_task_service,
    get_work_snapshot_service,
)
from pms.api.models import (
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
    PortfolioResponse,
    ProgramResponse,
    TeamResponse,
)
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject, PaginatedResponse
from pms.models import OrganizationStatus
from pms.models.api_key import ApiKey
from pms.models.value_contracts import RiskLevel
from pms.services.actor_service import ActorService
from pms.services.hierarchy_scope_service import HierarchyScopeService
from pms.services.organization_service import OrganizationService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.work_snapshot_service import WorkSnapshotService

router = APIRouter()


def _organization_response(
    org: object,
    actor_map: dict[str, object],
) -> OrganizationResponse:
    return OrganizationResponse(
        id=org.id,
        name=org.name,
        description=org.description,
        status=org.status.value,
        owner=actor_reference_payload(
            org.owner,
            actor_map,
            actor_id=org.owner_id,
        ),
        members=member_payloads(
            list(org.members),
            actor_map,
            actor_ids=list(org.member_ids),
        ),
        tags=list(org.tags),
        created_at=org.created_at,
        updated_at=org.updated_at,
    )


def _team_response(team: object, actor_map: dict[str, object]) -> TeamResponse:
    return TeamResponse(
        id=team.id,
        org_id=team.org_id,
        name=team.name,
        description=team.description,
        status=team.status.value,
        owner=actor_reference_payload(
            team.owner,
            actor_map,
            actor_id=team.owner_id,
        ),
        members=member_payloads(
            list(team.members),
            actor_map,
            actor_ids=list(team.member_ids),
        ),
        tags=list(team.tags),
        created_at=team.created_at,
        updated_at=team.updated_at,
    )


async def _portfolio_response(
    portfolio: object,
    actor_map: dict[str, object],
    hierarchy_service: HierarchyScopeService,
) -> PortfolioResponse:
    snapshot = await hierarchy_service.get_portfolio_snapshot(
        portfolio.id,
        limit=100000,
        offset=0,
    )
    return PortfolioResponse(
        id=portfolio.id,
        org_id=portfolio.org_id,
        name=portfolio.name,
        description=portfolio.description,
        status=portfolio.status.value,
        owner=actor_reference_payload(
            portfolio.owner,
            actor_map,
            actor_id=portfolio.owner_id,
        ),
        project_ids=[project.id for project in snapshot.projects.items],
        goal_ids=list(portfolio.goal_ids),
        objective_ids=list(portfolio.objective_ids),
        effective_goal_ids=[goal.id for goal in snapshot.goals.items],
        effective_objective_ids=[
            objective.id for objective in snapshot.objectives.items
        ],
        tags=list(portfolio.tags),
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
    )


async def _program_response(
    program: object,
    actor_map: dict[str, object],
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
            actor_map,
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


class OrganizationDashboardItemPayload(TypedDict, total=False):
    """Organization dashboard item payload."""

    organization: OrganizationResponse
    stats: JsonObject
    risk_level: RiskLevel
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    last_reviewed_at: datetime | None
    digest: JsonObject | None
    next_actions: list[JsonObject]
    evidence: JsonObject
    retention: JsonObject | None


class OrganizationDashboardTotalsPayload(TypedDict):
    """Organization dashboard totals payload."""

    total_organizations: int
    total_teams: int
    total_portfolios: int
    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class OrganizationDashboardResponsePayload(TypedDict):
    """Organization dashboard response payload."""

    items: list[OrganizationDashboardItemPayload]
    totals: OrganizationDashboardTotalsPayload
    total_count: int
    offset: int
    limit: int
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


class OrganizationSummaryPayload(TypedDict):
    """Organization summary payload."""

    organization: OrganizationResponse
    stats: JsonObject
    risk_level: RiskLevel
    teams: list[TeamResponse]
    portfolios: list[PortfolioResponse]
    programs: list[ProgramResponse]
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


@router.post("/organizations", response_model=OrganizationResponse, status_code=201)
async def create_organization(
    data: OrganizationCreate,
    organization_service: OrganizationService = Depends(get_organization_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_WRITE)),
) -> OrganizationResponse:
    """Create a new organization."""
    org = await organization_service.create_organization(
        name=data.name,
        description=data.description,
        owner=data.owner,
        members=data.members,
        tags=data.tags,
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [org.owner_id, org.owner, *org.member_ids, *org.members],
    )
    return _organization_response(org, actor_map)


@router.get("/organizations")
async def list_organizations(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    organization_service: OrganizationService = Depends(get_organization_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_READ)),
) -> PaginatedResponse[OrganizationResponse]:
    """List organizations."""
    status_filter = OrganizationStatus(status) if status else None
    result = await organization_service.list_organizations(
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/organizations", params)
    next_path = next_page_path(
        path="/api/v1/organizations",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/organizations/{org_id}",
        "GET /api/v1/organizations/{org_id}/summary",
        "GET /api/v1/organizations/dashboard",
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [
            actor_key
            for org in result.items
            for actor_key in (
                org.owner_id,
                org.owner,
                *org.member_ids,
                *org.members,
            )
        ],
    )
    return {
        "items": [_organization_response(o, actor_map) for o in result.items],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/organizations/dashboard")
async def get_organization_dashboard(
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    include_digest: bool = True,
    include_next_actions: bool = True,
    include_evidence: bool = True,
    include_retention: bool = True,
    next_limit: int = 3,
    organization_service: OrganizationService = Depends(get_organization_service),
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_READ)),
) -> OrganizationDashboardResponsePayload:
    """Get organization dashboard rollups."""
    status_filter = OrganizationStatus(status) if status else None
    dashboard = await organization_service.get_organization_dashboard(
        status=status_filter,
        limit=limit,
        offset=offset,
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [
            actor_key
            for item in dashboard.items
            for actor_key in (
                item.organization.owner_id,
                item.organization.owner,
                *item.organization.member_ids,
                *item.organization.members,
            )
        ],
    )
    items: list[OrganizationDashboardItemPayload] = []
    for item in dashboard.items:
        digest_payload = None
        last_reviewed_at = None
        next_actions: list[JsonObject] = []
        usage_result = None
        if include_digest:
            digest_result = await snapshot_service.get_digest(
                "organization", item.organization.id
            )
            if digest_result:
                digest_payload = digest_result.digest.to_dict()
                last_reviewed_at = digest_result.last_reviewed_at
        if include_evidence or include_retention:
            usage_result = await snapshot_service.get_usage_summary(
                "organization", item.organization.id
            )
            if usage_result and last_reviewed_at is None:
                last_reviewed_at = usage_result.last_reviewed_at
        if include_next_actions:
            next_actions = await snapshot_service.get_next_actions(
                "organization",
                item.organization.id,
                task_service=task_service,
                project_service=project_service,
                limit=next_limit,
            )

        payload: OrganizationDashboardItemPayload = {
            "organization": _organization_response(item.organization, actor_map),
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
        "limit": limit,
        "offset": offset,
        "include_digest": include_digest,
        "include_next_actions": include_next_actions,
        "include_evidence": include_evidence,
        "include_retention": include_retention,
        "next_limit": next_limit,
    }
    self_path = build_query_path("/api/v1/organizations/dashboard", params)
    links: JsonObject = {
        "self": self_path,
        "portfolio_dashboard": "/api/v1/portfolios/dashboard",
        "program_dashboard": "/api/v1/programs/dashboard",
        "work_daily_template": (
            "/api/v1/work-snapshots/organization/{org_id}/daily?view=detail"
        ),
    }
    next_steps: list[str] = [
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
        "GET /api/v1/programs/dashboard?org_id=<org_id>",
        "GET /api/v1/work-snapshots/organization/<org_id>/daily?view=detail",
    ]

    return {
        "items": items,
        "totals": {
            "total_organizations": dashboard.total_organizations,
            "total_teams": dashboard.total_teams,
            "total_portfolios": dashboard.total_portfolios,
            "total_programs": dashboard.total_programs,
            "total_projects": dashboard.total_projects,
            "total_goals": dashboard.total_goals,
            "total_objectives": dashboard.total_objectives,
            "total_tasks": dashboard.total_tasks,
            "blocked_tasks": dashboard.blocked_tasks,
        },
        "total_count": dashboard.total_organizations,
        "offset": offset,
        "limit": limit,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/organizations/{org_id}", response_model=OrganizationResponse)
async def get_organization(
    org_id: str,
    organization_service: OrganizationService = Depends(get_organization_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_READ)),
) -> OrganizationResponse:
    """Get organization by ID."""
    org = await organization_service.get_organization(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [org.owner_id, org.owner, *org.member_ids, *org.members],
    )
    return _organization_response(org, actor_map)


@router.patch("/organizations/{org_id}", response_model=OrganizationResponse)
async def update_organization(
    org_id: str,
    data: OrganizationUpdate,
    organization_service: OrganizationService = Depends(get_organization_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_WRITE)),
) -> OrganizationResponse:
    """Update organization details."""
    status_enum = OrganizationStatus(data.status) if data.status else None
    org = await organization_service.update_organization(
        org_id=org_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        owner=data.owner,
        members=data.members,
        tags=data.tags,
    )

    if org is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [org.owner_id, org.owner, *org.member_ids, *org.members],
    )
    return _organization_response(org, actor_map)


@router.get("/organizations/{org_id}/summary")
async def get_organization_summary(
    org_id: str,
    organization_service: OrganizationService = Depends(get_organization_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.ORGS_READ)),
) -> OrganizationSummaryPayload:
    """Get organization summary with rollups."""
    summary = await organization_service.get_organization_summary(org_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    params: QueryParamMap = {"org_id": org_id}
    self_path = build_query_path(f"/api/v1/organizations/{org_id}/summary", {})
    links: JsonObject = {
        "self": self_path,
        "organization": f"/api/v1/organizations/{org_id}",
        "dashboard": build_query_path(
            "/api/v1/organizations/dashboard",
            {"limit": 50, "offset": 0},
        ),
        "portfolio_dashboard": build_query_path(
            "/api/v1/portfolios/dashboard",
            {"org_id": org_id, "limit": 50, "offset": 0},
        ),
        "program_dashboard": build_query_path(
            "/api/v1/programs/dashboard",
            {"org_id": org_id, "limit": 50, "offset": 0},
        ),
        "work_daily": (
            f"/api/v1/work-snapshots/organization/{org_id}/daily?view=detail"
        ),
    }
    next_steps = normalize_next_steps(
        "GET /api/v1/organizations/dashboard?status=active",
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
        "GET /api/v1/programs/dashboard?org_id=<org_id>",
        "GET /api/v1/work-snapshots/organization/<org_id>/daily?view=detail",
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [
            actor_key
            for entity in (
                summary.organization,
                *summary.teams,
                *summary.portfolios,
                *summary.programs,
            )
            for actor_key in (
                getattr(entity, "owner_id", None),
                getattr(entity, "owner", None),
                *getattr(entity, "member_ids", ()),
                *getattr(entity, "members", ()),
            )
        ],
    )
    hierarchy_service = HierarchyScopeService(
        organization_service.db,
        organization_service.events,
        organization_service.revisions,
        organization_service.metrics,
    )
    return {
        "organization": _organization_response(summary.organization, actor_map),
        "stats": summary.stats.to_dict(),
        "risk_level": summary.risk_level,
        "teams": [_team_response(t, actor_map) for t in summary.teams],
        "portfolios": [
            await _portfolio_response(p, actor_map, hierarchy_service)
            for p in summary.portfolios
        ],
        "programs": [
            await _program_response(pg, actor_map, hierarchy_service)
            for pg in summary.programs
        ],
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }
