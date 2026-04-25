"""Portfolio API routes."""

from datetime import datetime
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import actor_reference_payload, resolve_owner_map
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import (
    get_actor_service,
    get_portfolio_service,
    get_project_service,
    get_task_service,
    get_work_snapshot_service,
)
from pms.api.models import PortfolioCreate, PortfolioResponse, PortfolioUpdate
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import JsonObject, PaginatedResponse
from pms.models import PortfolioStatus
from pms.models.api_key import ApiKey
from pms.models.value_contracts import RiskLevel
from pms.services.actor_service import ActorService
from pms.services.hierarchy_scope_service import HierarchyScopeService
from pms.services.portfolio_service import PortfolioService
from pms.services.project_service import ProjectService
from pms.services.task_service import TaskService
from pms.services.work_snapshot_service import WorkSnapshotService

router = APIRouter()


async def _portfolio_response(
    portfolio: object,
    owner_map: dict[str, object],
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
            owner_map,
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


class PortfolioDashboardItemPayload(TypedDict, total=False):
    """Portfolio dashboard item payload."""

    portfolio: PortfolioResponse
    stats: JsonObject
    risk_level: RiskLevel
    last_activity_at: datetime | None
    last_transition_at: datetime | None
    last_reviewed_at: datetime | None
    digest: JsonObject | None
    next_actions: list[JsonObject]
    evidence: JsonObject
    retention: JsonObject | None


class PortfolioDashboardTotalsPayload(TypedDict):
    """Portfolio dashboard totals payload."""

    total_portfolios: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class PortfolioDashboardResponsePayload(TypedDict):
    """Portfolio dashboard response payload."""

    items: list[PortfolioDashboardItemPayload]
    totals: PortfolioDashboardTotalsPayload
    total_count: int
    offset: int
    limit: int
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


class PortfolioSummaryPayload(TypedDict):
    """Portfolio summary payload."""

    portfolio: PortfolioResponse
    stats: JsonObject
    risk_level: RiskLevel
    links: JsonObject
    next_steps: list[str]
    params: JsonObject


@router.post("/portfolios", response_model=PortfolioResponse, status_code=201)
async def create_portfolio(
    data: PortfolioCreate,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_WRITE)),
) -> PortfolioResponse:
    """Create a new portfolio."""
    portfolio = await portfolio_service.create_portfolio(
        name=data.name,
        org_id=data.org_id,
        description=data.description,
        owner=data.owner,
        project_ids=data.project_ids,
        goal_ids=data.goal_ids,
        objective_ids=data.objective_ids,
        tags=data.tags,
    )

    owner_map = await resolve_owner_map(actor_service, [portfolio])
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    return await _portfolio_response(portfolio, owner_map, hierarchy_service)


@router.get("/portfolios")
async def list_portfolios(
    status: str | None = None,
    org_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_READ)),
) -> PaginatedResponse[PortfolioResponse]:
    """List portfolios."""
    status_filter = PortfolioStatus(status) if status else None
    result = await portfolio_service.list_portfolios(
        status=status_filter,
        org_id=org_id,
        limit=limit,
        offset=offset,
    )
    params: QueryParamMap = {
        "status": status,
        "org_id": org_id,
        "limit": limit,
        "offset": offset,
    }
    self_path = build_query_path("/api/v1/portfolios", params)
    next_path = next_page_path(
        path="/api/v1/portfolios",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/portfolios/{portfolio_id}",
        "GET /api/v1/portfolios/{portfolio_id}/summary",
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
    )

    owner_map = await resolve_owner_map(actor_service, result.items)
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    return {
        "items": [
            await _portfolio_response(p, owner_map, hierarchy_service)
            for p in result.items
        ],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/portfolios/dashboard")
async def get_portfolio_dashboard(
    status: str | None = None,
    org_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    include_digest: bool = True,
    include_next_actions: bool = True,
    include_evidence: bool = True,
    include_retention: bool = True,
    next_limit: int = 3,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    project_service: ProjectService = Depends(get_project_service),
    task_service: TaskService = Depends(get_task_service),
    snapshot_service: WorkSnapshotService = Depends(get_work_snapshot_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_READ)),
) -> PortfolioDashboardResponsePayload:
    """Get portfolio dashboard rollups."""
    status_filter = PortfolioStatus(status) if status else None
    dashboard = await portfolio_service.get_portfolio_dashboard(
        status=status_filter,
        org_id=org_id,
        limit=limit,
        offset=offset,
    )

    owner_map = await resolve_owner_map(
        actor_service,
        [item.portfolio for item in dashboard.items],
    )
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    items: list[PortfolioDashboardItemPayload] = []
    for item in dashboard.items:
        digest_payload = None
        last_reviewed_at = None
        next_actions: list[JsonObject] = []
        usage_result = None
        if include_digest:
            digest_result = await snapshot_service.get_digest(
                "portfolio", item.portfolio.id
            )
            if digest_result:
                digest_payload = digest_result.digest.to_dict()
                last_reviewed_at = digest_result.last_reviewed_at
        if include_evidence or include_retention:
            usage_result = await snapshot_service.get_usage_summary(
                "portfolio", item.portfolio.id
            )
            if usage_result and last_reviewed_at is None:
                last_reviewed_at = usage_result.last_reviewed_at
        if include_next_actions:
            next_actions = await snapshot_service.get_next_actions(
                "portfolio",
                item.portfolio.id,
                task_service=task_service,
                project_service=project_service,
                limit=next_limit,
            )

        payload: PortfolioDashboardItemPayload = {
            "portfolio": await _portfolio_response(
                item.portfolio,
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
        "limit": limit,
        "offset": offset,
        "include_digest": include_digest,
        "include_next_actions": include_next_actions,
        "include_evidence": include_evidence,
        "include_retention": include_retention,
        "next_limit": next_limit,
    }
    self_path = build_query_path("/api/v1/portfolios/dashboard", params)
    links: JsonObject = {
        "self": self_path,
        "organization_dashboard": "/api/v1/organizations/dashboard",
        "program_dashboard": "/api/v1/programs/dashboard",
        "work_daily_template": (
            "/api/v1/work-snapshots/portfolio/{portfolio_id}/daily?view=detail"
        ),
    }
    next_steps: list[str] = [
        "GET /api/v1/programs/dashboard?portfolio_id=<portfolio_id>",
        "GET /api/v1/work-snapshots/portfolio/<portfolio_id>/daily?view=detail",
        "GET /api/v1/organizations/dashboard",
    ]

    return {
        "items": items,
        "totals": {
            "total_portfolios": dashboard.total_portfolios,
            "total_projects": dashboard.total_projects,
            "total_goals": dashboard.total_goals,
            "total_objectives": dashboard.total_objectives,
            "total_tasks": dashboard.total_tasks,
            "blocked_tasks": dashboard.blocked_tasks,
        },
        "total_count": dashboard.total_portfolios,
        "offset": offset,
        "limit": limit,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def get_portfolio(
    portfolio_id: str,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_READ)),
) -> PortfolioResponse:
    """Get portfolio by ID."""
    portfolio = await portfolio_service.get_portfolio(portfolio_id)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    owner_map = await resolve_owner_map(actor_service, [portfolio])
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    return await _portfolio_response(portfolio, owner_map, hierarchy_service)


@router.patch("/portfolios/{portfolio_id}", response_model=PortfolioResponse)
async def update_portfolio(
    portfolio_id: str,
    data: PortfolioUpdate,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_WRITE)),
) -> PortfolioResponse:
    """Update portfolio details."""
    status_enum = PortfolioStatus(data.status) if data.status else None
    portfolio = await portfolio_service.update_portfolio(
        portfolio_id=portfolio_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        owner=data.owner,
        project_ids=data.project_ids,
        goal_ids=data.goal_ids,
        objective_ids=data.objective_ids,
        tags=data.tags,
    )

    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    owner_map = await resolve_owner_map(actor_service, [portfolio])
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    return await _portfolio_response(portfolio, owner_map, hierarchy_service)


@router.get("/portfolios/{portfolio_id}/summary")
async def get_portfolio_summary(
    portfolio_id: str,
    portfolio_service: PortfolioService = Depends(get_portfolio_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.PORTFOLIOS_READ)),
) -> PortfolioSummaryPayload:
    """Get portfolio summary with rollups."""
    summary = await portfolio_service.get_portfolio_summary(portfolio_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    params: QueryParamMap = {"portfolio_id": portfolio_id}
    links: JsonObject = {
        "self": build_query_path(f"/api/v1/portfolios/{portfolio_id}/summary", {}),
        "portfolio": f"/api/v1/portfolios/{portfolio_id}",
        "dashboard": build_query_path(
            "/api/v1/portfolios/dashboard",
            {"org_id": summary.portfolio.org_id, "limit": 50, "offset": 0},
        ),
        "program_dashboard": build_query_path(
            "/api/v1/programs/dashboard",
            {"portfolio_id": portfolio_id, "limit": 50, "offset": 0},
        ),
        "work_daily": (
            f"/api/v1/work-snapshots/portfolio/{portfolio_id}/daily?view=detail"
        ),
    }
    if summary.portfolio.org_id:
        links["organization_dashboard"] = build_query_path(
            "/api/v1/organizations/dashboard",
            {"status": "active", "limit": 50, "offset": 0},
        )
    next_steps = normalize_next_steps(
        "GET /api/v1/portfolios/dashboard?org_id=<org_id>",
        "GET /api/v1/programs/dashboard?portfolio_id=<portfolio_id>",
        "GET /api/v1/work-snapshots/portfolio/<portfolio_id>/daily?view=detail",
    )

    owner_map = await resolve_owner_map(actor_service, [summary.portfolio])
    hierarchy_service = HierarchyScopeService(
        portfolio_service.db,
        portfolio_service.events,
        portfolio_service.revisions,
        portfolio_service.metrics,
    )
    return {
        "portfolio": await _portfolio_response(
            summary.portfolio,
            owner_map,
            hierarchy_service,
        ),
        "stats": summary.stats.to_dict(),
        "risk_level": summary.risk_level,
        "links": links,
        "next_steps": next_steps,
        "params": params,
    }
