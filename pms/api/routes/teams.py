"""Team API routes."""

from fastapi import APIRouter, Depends, HTTPException

from pms.api.actor_payloads import (
    actor_reference_payload,
    member_payloads,
    resolve_actor_reference_map,
)
from pms.api.auth import Scopes, require_scope
from pms.api.dependencies import get_actor_service, get_team_service
from pms.api.models import TeamCreate, TeamResponse, TeamUpdate
from pms.api.routes.discoverability import (
    QueryParamMap,
    build_query_path,
    next_page_path,
    normalize_next_steps,
    paginated_links,
)
from pms.api.types import PaginatedResponse
from pms.models import TeamStatus
from pms.models.api_key import ApiKey
from pms.services.actor_service import ActorService
from pms.services.team_service import TeamService

router = APIRouter()


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


@router.post("/teams", response_model=TeamResponse, status_code=201)
async def create_team(
    data: TeamCreate,
    team_service: TeamService = Depends(get_team_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEAMS_WRITE)),
) -> TeamResponse:
    """Create a new team."""
    team = await team_service.create_team(
        name=data.name,
        org_id=data.org_id,
        description=data.description,
        owner=data.owner,
        members=data.members,
        tags=data.tags,
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [team.owner_id, team.owner, *team.member_ids, *team.members],
    )
    return _team_response(team, actor_map)


@router.get("/teams")
async def list_teams(
    status: str | None = None,
    org_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
    team_service: TeamService = Depends(get_team_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEAMS_READ)),
) -> PaginatedResponse[TeamResponse]:
    """List teams."""
    status_filter = TeamStatus(status) if status else None
    result = await team_service.list_teams(
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
    self_path = build_query_path("/api/v1/teams", params)
    next_path = next_page_path(
        path="/api/v1/teams",
        params=params,
        total_count=result.total_count,
        offset=result.offset,
        limit=result.limit,
    )
    next_steps = normalize_next_steps(
        "GET /api/v1/teams/{team_id}",
        "GET /api/v1/teams?org_id=<org_id>",
        "GET /api/v1/organizations/{org_id}/summary",
    )

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [
            actor_key
            for team in result.items
            for actor_key in (
                team.owner_id,
                team.owner,
                *team.member_ids,
                *team.members,
            )
        ],
    )
    return {
        "items": [_team_response(t, actor_map) for t in result.items],
        "total_count": result.total_count,
        "offset": result.offset,
        "limit": result.limit,
        "links": paginated_links(self_path=self_path, next_path=next_path),
        "next_steps": next_steps,
        "params": params,
    }


@router.get("/teams/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: str,
    team_service: TeamService = Depends(get_team_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEAMS_READ)),
) -> TeamResponse:
    """Get team by ID."""
    team = await team_service.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [team.owner_id, team.owner, *team.member_ids, *team.members],
    )
    return _team_response(team, actor_map)


@router.patch("/teams/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: str,
    data: TeamUpdate,
    team_service: TeamService = Depends(get_team_service),
    actor_service: ActorService = Depends(get_actor_service),
    _api_key: ApiKey = Depends(require_scope(Scopes.TEAMS_WRITE)),
) -> TeamResponse:
    """Update team details."""
    status_enum = TeamStatus(data.status) if data.status else None
    team = await team_service.update_team(
        team_id=team_id,
        name=data.name,
        description=data.description,
        status=status_enum,
        owner=data.owner,
        members=data.members,
        tags=data.tags,
    )

    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")

    actor_map = await resolve_actor_reference_map(
        actor_service,
        [team.owner_id, team.owner, *team.member_ids, *team.members],
    )
    return _team_response(team, actor_map)
