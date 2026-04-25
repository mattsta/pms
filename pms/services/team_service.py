"""Team service for team operations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Team, TeamStatus
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.team_repository import TeamRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class TeamService:
    """Service for team management operations."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        self.db = db
        self.events = event_store
        self.revisions = revision_store
        self.metrics = metrics

        self._team_repo = TeamRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> TeamService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._team_repo.with_context(self._context)
        return self

    async def _resolve_owner_identity(
        self,
        owner: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve owner input to canonical actor-facing value plus actor id."""
        if owner is None:
            return None, None
        from pms.services.actor_service import ActorService

        actor_service = ActorService(self.db, self.events, self.revisions, self.metrics)
        actor_service.with_context(
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            correlation_id=self._context.correlation_id,
        )
        return await actor_service.canonicalize_actor_reference(owner)

    async def _resolve_member_identities(
        self,
        members: list[str] | None,
    ) -> tuple[list[str] | None, list[str]]:
        """Resolve member inputs to canonical actor-facing values plus actor ids."""
        if members is None:
            return None, []
        from pms.services.actor_service import ActorService

        actor_service = ActorService(self.db, self.events, self.revisions, self.metrics)
        actor_service.with_context(
            user_id=self._context.user_id,
            session_id=self._context.session_id,
            correlation_id=self._context.correlation_id,
        )
        return await actor_service.canonicalize_actor_references(members)

    async def create_team(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Team:
        """Create a new team."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        canonical_members, member_ids = await self._resolve_member_identities(members)
        async with self._team_repo.db.transaction():
            team = await self._team_repo.create(
                name=name,
                org_id=org_id,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                members=canonical_members,
                member_ids=member_ids,
                tags=tags,
                message=f"Created team '{name}'",
            )

            await self.metrics.record_counter("team.created")
            await self.metrics.flush()

        return team

    async def get_team(self, team_id: str) -> Team | None:
        """Get team by ID."""
        return await self._team_repo.get_by_id(team_id)

    async def get_team_by_name(self, name: str) -> Team | None:
        """Get team by name."""
        return await self._team_repo.get_by_name(name)

    async def list_teams(
        self,
        status: TeamStatus | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Team]:
        """List teams with optional filters."""
        return await self._team_repo.list_filtered(
            org_id=org_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_team(
        self,
        team_id: str,
        name: str | None = None,
        description: str | None = None,
        status: TeamStatus | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        members: list[str] | None = None,
        clear_members: bool = False,
        tags: list[str] | None = None,
    ) -> Team | None:
        """Update team details."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        canonical_members, member_ids = await self._resolve_member_identities(members)
        async with self._team_repo.db.transaction():
            team = await self._team_repo.update(
                team_id=team_id,
                name=name,
                description=description,
                status=status,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                members=canonical_members,
                member_ids=member_ids,
                clear_members=clear_members,
                tags=tags,
            )

            if team:
                await self.metrics.record_counter("team.updated")
                await self.metrics.flush()

        return team

    async def archive_team(self, team_id: str) -> Team | None:
        """Archive a team."""
        async with self._team_repo.db.transaction():
            team = await self._team_repo.archive(team_id)
            if team:
                await self.metrics.record_counter("team.archived")
                await self.metrics.flush()
        return team
