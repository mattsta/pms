"""Organization service for org-level operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import (
    Organization,
    OrganizationStats,
    OrganizationStatus,
    Portfolio,
    Program,
    Team,
)
from pms.models.value_contracts import RiskLevel
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.repositories.team_repository import TeamRepository
from pms.services.goal_service import GoalService
from pms.services.hierarchy_scope_service import HierarchyScopeService
from pms.services.rollup_utils import (
    apply_effective_goal_rollups,
    build_rollup_metrics,
    collect_rollup_entities,
    fetch_grouped_max_timestamps,
    fetch_grouped_review_activity,
    max_datetime,
    sort_items_by_bubbled_recency,
)

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class OrganizationSummary:
    """Summary of an organization with rollup metrics."""

    organization: Organization
    stats: OrganizationStats
    teams: list[Team]
    portfolios: list[Portfolio]
    programs: list[Program]
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    risk_level: RiskLevel = "low"


@dataclass
class OrganizationDashboardItem:
    """Compact dashboard item for an organization."""

    organization: Organization
    stats: OrganizationStats
    risk_level: RiskLevel
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None


@dataclass
class OrganizationDashboard:
    """Dashboard view for organizations."""

    items: list[OrganizationDashboardItem]
    total_organizations: int
    total_teams: int
    total_portfolios: int
    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class OrganizationService:
    """Service for organization management and rollups."""

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

        self._org_repo = OrganizationRepository(
            db, event_store, revision_store, metrics
        )
        self._team_repo = TeamRepository(db, event_store, revision_store, metrics)
        self._portfolio_repo = PortfolioRepository(
            db, event_store, revision_store, metrics
        )
        self._program_repo = ProgramRepository(db, event_store, revision_store, metrics)
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        self._objective_repo = ObjectiveRepository(
            db, event_store, revision_store, metrics
        )
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._hierarchy = HierarchyScopeService(
            db, event_store, revision_store, metrics
        )

        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> OrganizationService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._org_repo.with_context(self._context)
        self._team_repo.with_context(self._context)
        self._portfolio_repo.with_context(self._context)
        self._program_repo.with_context(self._context)
        self._project_repo.with_context(self._context)
        self._goal_repo.with_context(self._context)
        self._objective_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
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

    async def create_organization(
        self,
        name: str,
        description: str | None = None,
        owner: str | None = None,
        members: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Organization:
        """Create a new organization."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        canonical_members, member_ids = await self._resolve_member_identities(members)
        async with self._org_repo.db.transaction():
            org = await self._org_repo.create(
                name=name,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                members=canonical_members,
                member_ids=member_ids,
                tags=tags,
                message=f"Created organization '{name}'",
            )

            await self.metrics.record_counter("organization.created")
            await self.metrics.flush()

        return org

    async def get_organization(self, org_id: str) -> Organization | None:
        """Get organization by ID."""
        return await self._org_repo.get_by_id(org_id)

    async def get_organization_by_name(self, name: str) -> Organization | None:
        """Get organization by name."""
        return await self._org_repo.get_by_name(name)

    async def list_organizations(
        self,
        status: OrganizationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Organization]:
        """List organizations."""
        if status:
            return await self._org_repo.get_by_status(
                status, limit=limit, offset=offset
            )
        return await self._org_repo.get_all(limit=limit, offset=offset)

    async def update_organization(
        self,
        org_id: str,
        name: str | None = None,
        description: str | None = None,
        status: OrganizationStatus | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        members: list[str] | None = None,
        clear_members: bool = False,
        tags: list[str] | None = None,
    ) -> Organization | None:
        """Update an organization."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        canonical_members, member_ids = await self._resolve_member_identities(members)
        async with self._org_repo.db.transaction():
            org = await self._org_repo.update(
                org_id=org_id,
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

            if org:
                await self.metrics.record_counter("organization.updated")
                await self.metrics.flush()

        return org

    async def archive_organization(self, org_id: str) -> Organization | None:
        """Archive an organization."""
        async with self._org_repo.db.transaction():
            org = await self._org_repo.archive(org_id)
            if org:
                await self.metrics.record_counter("organization.archived")
                await self.metrics.flush()
        return org

    async def get_organization_summary(self, org_id: str) -> OrganizationSummary | None:
        """Get organization summary with rollups."""
        organization = await self._org_repo.get_by_id(org_id)
        if organization is None:
            return None

        teams_result = await self._team_repo.get_by_org(org_id, limit=1000, offset=0)
        portfolios_result = await self._portfolio_repo.get_by_org(
            org_id, limit=1000, offset=0
        )
        programs_result = await self._program_repo.get_by_org(
            org_id, limit=1000, offset=0
        )

        project_ids = await self._hierarchy.get_project_ids_for_scope(
            "organization",
            org_id,
        )

        goals, objectives, tasks = await collect_rollup_entities(
            self._goal_repo,
            self._objective_repo,
            self._task_repo,
            [],
            [],
            project_ids,
        )

        goal_service = GoalService(self.db, self.events, self.revisions, self.metrics)
        effective_rollups = await goal_service.get_effective_rollups_for_goals(goals)
        effective_goals = apply_effective_goal_rollups(goals, effective_rollups)
        goal_activity = await goal_service.get_last_activity_map(
            [goal.id for goal in goals]
        )
        objective_activity = await goal_service.get_objective_last_activity_map(
            [objective.id for objective in objectives]
        )
        from pms.services.project_service import ProjectService

        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        project_activity = await project_service.get_last_activity_map(project_ids)
        project_transition = await project_service.get_last_transition_map(project_ids)
        goal_transition = await goal_service.get_last_transition_map(
            [goal.id for goal in goals]
        )
        objective_transition = await goal_service.get_objective_last_transition_map(
            [objective.id for objective in objectives]
        )

        org_params = (org_id,)
        org_field_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as org_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'organization' AND entity_id = ?
            GROUP BY entity_id
            """,
            org_params,
            key_name="org_id",
        )
        org_comment_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as org_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'organization' AND entity_id = ?
            GROUP BY entity_id
            """,
            org_params,
            key_name="org_id",
        )
        org_label_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as org_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'organization' AND entity_id = ?
            GROUP BY entity_id
            """,
            org_params,
            key_name="org_id",
        )
        org_watcher_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as org_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'organization' AND entity_id = ?
            GROUP BY entity_id
            """,
            org_params,
            key_name="org_id",
        )
        org_review_activity = await fetch_grouped_review_activity(
            self.db,
            scope_type="organization",
            params=org_params,
            key_name="org_id",
            select_key_sql="review.scope_id",
            where_sql="review.scope_id = ?",
        )

        child_params = (org_id,)
        team_side_activity = max_datetime(
            [
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT t.org_id as org_id, MAX(cf.updated_at) as ts
                        FROM custom_field_values cf
                        JOIN teams t ON cf.entity_id = t.id
                        WHERE cf.entity_type = 'team' AND t.org_id = ?
                        GROUP BY t.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT t.org_id as org_id, MAX(c.updated_at) as ts
                        FROM comments c
                        JOIN teams t ON c.entity_id = t.id
                        WHERE c.entity_type = 'team' AND t.org_id = ?
                        GROUP BY t.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT t.org_id as org_id,
                               MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
                        FROM label_assignments la
                        JOIN teams t ON la.entity_id = t.id
                        WHERE la.entity_type = 'team' AND t.org_id = ?
                        GROUP BY t.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT t.org_id as org_id,
                               MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
                        FROM entity_watchers ew
                        JOIN teams t ON ew.entity_id = t.id
                        WHERE ew.entity_type = 'team' AND t.org_id = ?
                        GROUP BY t.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
            ]
        )
        portfolio_side_activity = max_datetime(
            [
                (
                    await fetch_grouped_review_activity(
                        self.db,
                        scope_type="portfolio",
                        params=child_params,
                        key_name="org_id",
                        select_key_sql="p.org_id",
                        join_sql="JOIN portfolios p ON review.scope_id = p.id",
                        where_sql="p.org_id = ?",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id, MAX(cf.updated_at) as ts
                        FROM custom_field_values cf
                        JOIN portfolios p ON cf.entity_id = p.id
                        WHERE cf.entity_type = 'portfolio' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id, MAX(c.updated_at) as ts
                        FROM comments c
                        JOIN portfolios p ON c.entity_id = p.id
                        WHERE c.entity_type = 'portfolio' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id,
                               MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
                        FROM label_assignments la
                        JOIN portfolios p ON la.entity_id = p.id
                        WHERE la.entity_type = 'portfolio' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id,
                               MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
                        FROM entity_watchers ew
                        JOIN portfolios p ON ew.entity_id = p.id
                        WHERE ew.entity_type = 'portfolio' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
            ]
        )
        program_side_activity = max_datetime(
            [
                (
                    await fetch_grouped_review_activity(
                        self.db,
                        scope_type="program",
                        params=child_params,
                        key_name="org_id",
                        select_key_sql="p.org_id",
                        join_sql="JOIN programs p ON review.scope_id = p.id",
                        where_sql="p.org_id = ?",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id, MAX(cf.updated_at) as ts
                        FROM custom_field_values cf
                        JOIN programs p ON cf.entity_id = p.id
                        WHERE cf.entity_type = 'program' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id, MAX(c.updated_at) as ts
                        FROM comments c
                        JOIN programs p ON c.entity_id = p.id
                        WHERE c.entity_type = 'program' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id,
                               MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
                        FROM label_assignments la
                        JOIN programs p ON la.entity_id = p.id
                        WHERE la.entity_type = 'program' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.org_id as org_id,
                               MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
                        FROM entity_watchers ew
                        JOIN programs p ON ew.entity_id = p.id
                        WHERE ew.entity_type = 'program' AND p.org_id = ?
                        GROUP BY p.org_id
                        """,
                        child_params,
                        key_name="org_id",
                    )
                ).get(org_id),
            ]
        )

        metrics = build_rollup_metrics(effective_goals, objectives, tasks)
        last_activity = max_datetime(
            [
                organization.updated_at,
                org_field_activity.get(org_id),
                org_comment_activity.get(org_id),
                org_label_activity.get(org_id),
                org_watcher_activity.get(org_id),
                org_review_activity.get(org_id),
                max_datetime(team.updated_at for team in teams_result.items),
                team_side_activity,
                max_datetime(
                    portfolio.updated_at for portfolio in portfolios_result.items
                ),
                portfolio_side_activity,
                max_datetime(program.updated_at for program in programs_result.items),
                program_side_activity,
                *project_activity.values(),
                *goal_activity.values(),
                *objective_activity.values(),
            ]
        )
        transition_repo = StateTransitionRepository(self.db)
        org_transitions = await transition_repo.get_last_transition_map(
            "organization_status", [org_id]
        )
        team_transitions = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT t.org_id as org_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN teams t ON st.entity_id = t.id
            WHERE st.entity_type = 'team_status' AND t.org_id = ?
            GROUP BY t.org_id
            """,
            child_params,
            key_name="org_id",
        )
        portfolio_transitions = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT p.org_id as org_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN portfolios p ON st.entity_id = p.id
            WHERE st.entity_type = 'portfolio_status' AND p.org_id = ?
            GROUP BY p.org_id
            """,
            child_params,
            key_name="org_id",
        )
        program_transitions = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT p.org_id as org_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN programs p ON st.entity_id = p.id
            WHERE st.entity_type = 'program_status' AND p.org_id = ?
            GROUP BY p.org_id
            """,
            child_params,
            key_name="org_id",
        )
        last_transition = max_datetime(
            [
                org_transitions.get(org_id),
                team_transitions.get(org_id),
                portfolio_transitions.get(org_id),
                program_transitions.get(org_id),
                *project_transition.values(),
                *goal_transition.values(),
                *objective_transition.values(),
            ]
        )
        stats = OrganizationStats(
            organization_id=org_id,
            total_teams=teams_result.total_count,
            total_portfolios=portfolios_result.total_count,
            total_programs=programs_result.total_count,
            total_projects=len(project_ids),
            total_goals=metrics.total_goals,
            completed_goals=metrics.completed_goals,
            avg_goal_progress=metrics.avg_goal_progress,
            total_objectives=metrics.total_objectives,
            completed_objectives=metrics.completed_objectives,
            avg_objective_progress=metrics.avg_objective_progress,
            total_tasks=metrics.total_tasks,
            blocked_tasks=metrics.blocked_tasks,
            horizon_breakdown=metrics.horizon_breakdown,
            horizon_completion=metrics.horizon_completion,
            risk_score=metrics.risk_score,
        )

        return OrganizationSummary(
            organization=organization,
            stats=stats,
            teams=teams_result.items,
            portfolios=portfolios_result.items,
            programs=programs_result.items,
            last_activity_at=last_activity,
            last_transition_at=last_transition,
            risk_level=metrics.risk_level,
        )

    async def get_organization_dashboard(
        self,
        status: OrganizationStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> OrganizationDashboard:
        """Get dashboard view for organizations with rollups."""
        result = await self.list_organizations(
            status=status, limit=limit, offset=offset
        )

        items: list[OrganizationDashboardItem] = []
        total_teams = 0
        total_portfolios = 0
        total_programs = 0
        total_projects = 0
        total_goals = 0
        total_objectives = 0
        total_tasks = 0
        blocked_tasks = 0

        for org in result.items:
            summary = await self.get_organization_summary(org.id)
            if summary is None:
                continue

            stats = summary.stats
            items.append(
                OrganizationDashboardItem(
                    organization=summary.organization,
                    stats=stats,
                    risk_level=summary.risk_level,
                    last_activity_at=summary.last_activity_at,
                    last_transition_at=summary.last_transition_at,
                )
            )

            total_teams += stats.total_teams
            total_portfolios += stats.total_portfolios
            total_programs += stats.total_programs
            total_projects += stats.total_projects
            total_goals += stats.total_goals
            total_objectives += stats.total_objectives
            total_tasks += stats.total_tasks
            blocked_tasks += stats.blocked_tasks

        items = sort_items_by_bubbled_recency(
            items,
            activity_of=lambda item: item.last_activity_at,
            transition_of=lambda item: item.last_transition_at,
            updated_of=lambda item: item.organization.updated_at,
            label_of=lambda item: item.organization.name,
            id_of=lambda item: item.organization.id,
        )

        return OrganizationDashboard(
            items=items,
            total_organizations=result.total_count,
            total_teams=total_teams,
            total_portfolios=total_portfolios,
            total_programs=total_programs,
            total_projects=total_projects,
            total_goals=total_goals,
            total_objectives=total_objectives,
            total_tasks=total_tasks,
            blocked_tasks=blocked_tasks,
        )
