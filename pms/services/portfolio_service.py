"""Portfolio service for portfolio operations and rollups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Portfolio, PortfolioStats, PortfolioStatus
from pms.models.value_contracts import RiskLevel
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.goal_service import GoalService
from pms.services.hierarchy_scope_service import (
    HierarchyScopeService,
    HierarchyScopeSnapshot,
)
from pms.services.link_validation import validate_reference_ids
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
class PortfolioSummary:
    """Summary of a portfolio with rollup metrics."""

    portfolio: Portfolio
    stats: PortfolioStats
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    risk_level: RiskLevel = "low"


@dataclass
class PortfolioDashboardItem:
    """Compact dashboard item for a portfolio."""

    portfolio: Portfolio
    stats: PortfolioStats
    risk_level: RiskLevel
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None


@dataclass
class PortfolioDashboard:
    """Dashboard view for portfolios."""

    items: list[PortfolioDashboardItem]
    total_portfolios: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class PortfolioService:
    """Service for portfolio management operations."""

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
    ) -> PortfolioService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
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

    async def _assign_project_to_portfolio_in_transaction(
        self, portfolio: Portfolio, project_id: str
    ) -> None:
        await self._project_repo.assign_to_portfolio(
            project_id,
            portfolio.id,
            message=f"Assigned to portfolio {portfolio.id}",
        )
        if portfolio.org_id:
            await self._project_repo.assign_to_org(
                project_id,
                portfolio.org_id,
                message=f"Assigned to org {portfolio.org_id}",
            )

    async def _validate_scope_write_inputs(
        self,
        *,
        project_ids: list[str] | None,
        goal_ids: list[str] | None,
        objective_ids: list[str] | None,
    ) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
        """Validate project, goal, and objective links for a portfolio write."""
        validated_project_ids = await validate_reference_ids(
            self._project_repo,
            project_ids,
            field_name="project_ids",
            entity_label="Project",
        )
        validated_goal_ids = await validate_reference_ids(
            self._goal_repo,
            goal_ids,
            field_name="goal_ids",
            entity_label="Goal",
        )
        validated_objective_ids = await validate_reference_ids(
            self._objective_repo,
            objective_ids,
            field_name="objective_ids",
            entity_label="Objective",
        )
        return validated_project_ids, validated_goal_ids, validated_objective_ids

    async def create_portfolio(
        self,
        name: str,
        org_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Portfolio:
        """Create a new portfolio."""
        (
            validated_project_ids,
            validated_goal_ids,
            validated_objective_ids,
        ) = await self._validate_scope_write_inputs(
            project_ids=project_ids,
            goal_ids=goal_ids,
            objective_ids=objective_ids,
        )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._portfolio_repo.db.transaction():
            portfolio = await self._portfolio_repo._create_in_transaction(
                name=name,
                org_id=org_id,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                goal_ids=validated_goal_ids,
                objective_ids=validated_objective_ids,
                tags=tags,
                message=f"Created portfolio '{name}'",
            )

            if validated_project_ids:
                for project_id in validated_project_ids:
                    await self._assign_project_to_portfolio_in_transaction(
                        portfolio, project_id
                    )

            await self.metrics.record_counter("portfolio.created")
            await self.metrics.flush()

        return await self._portfolio_repo.get_by_id(portfolio.id) or portfolio

    async def get_portfolio(self, portfolio_id: str) -> Portfolio | None:
        """Get portfolio by ID."""
        return await self._portfolio_repo.get_by_id(portfolio_id)

    async def get_portfolio_by_name(self, name: str) -> Portfolio | None:
        """Get portfolio by name."""
        return await self._portfolio_repo.get_by_name(name)

    async def get_portfolio_scope_snapshot(
        self,
        portfolio_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> HierarchyScopeSnapshot:
        """Return authoritative linked entities for a portfolio."""
        return await self._hierarchy.get_portfolio_snapshot(
            portfolio_id,
            limit=limit,
            offset=offset,
        )

    async def get_portfolio_project_ids(self, portfolio_id: str) -> list[str]:
        """Return authoritative project ids for a portfolio."""
        return await self._hierarchy.get_project_ids_for_scope(
            "portfolio", portfolio_id
        )

    async def list_portfolios(
        self,
        status: PortfolioStatus | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Portfolio]:
        """List portfolios with optional filters."""
        return await self._portfolio_repo.list_filtered(
            org_id=org_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_portfolio(
        self,
        portfolio_id: str,
        name: str | None = None,
        description: str | None = None,
        status: PortfolioStatus | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Portfolio | None:
        """Update portfolio details."""
        (
            validated_project_ids,
            validated_goal_ids,
            validated_objective_ids,
        ) = await self._validate_scope_write_inputs(
            project_ids=project_ids,
            goal_ids=goal_ids,
            objective_ids=objective_ids,
        )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._portfolio_repo.db.transaction():
            existing = await self._portfolio_repo.get_by_id(portfolio_id)
            if existing is None:
                return None
            portfolio = await self._portfolio_repo._update_in_transaction(
                portfolio_id=portfolio_id,
                name=name,
                description=description,
                status=status,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                goal_ids=validated_goal_ids,
                objective_ids=validated_objective_ids,
                tags=tags,
            )

            if portfolio:
                if validated_project_ids is not None:
                    old_ids = set(existing.project_ids)
                    new_ids = set(validated_project_ids)
                    for project_id in new_ids - old_ids:
                        await self._assign_project_to_portfolio_in_transaction(
                            portfolio, project_id
                        )
                    for project_id in old_ids - new_ids:
                        project = await self._project_repo.get_by_id(project_id)
                        if project and project.portfolio_id == portfolio.id:
                            await self._project_repo.assign_to_portfolio(
                                project_id,
                                None,
                                message=f"Unlinked from portfolio {portfolio.id}",
                            )

                await self.metrics.record_counter("portfolio.updated")
                await self.metrics.flush()

        if portfolio is None:
            return None
        return await self._portfolio_repo.get_by_id(portfolio.id) or portfolio

    async def archive_portfolio(self, portfolio_id: str) -> Portfolio | None:
        """Archive a portfolio."""
        async with self._portfolio_repo.db.transaction():
            portfolio = await self._portfolio_repo.archive(portfolio_id)
            if portfolio:
                await self.metrics.record_counter("portfolio.archived")
                await self.metrics.flush()
        return portfolio

    async def get_portfolio_summary(self, portfolio_id: str) -> PortfolioSummary | None:
        """Get portfolio summary with rollup metrics."""
        portfolio = await self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            return None

        project_ids = await self.get_portfolio_project_ids(portfolio_id)
        goals, objectives, tasks = await collect_rollup_entities(
            self._goal_repo,
            self._objective_repo,
            self._task_repo,
            portfolio.goal_ids,
            portfolio.objective_ids,
            project_ids,
        )
        programs_result = await self._program_repo.get_by_portfolio(
            portfolio_id, limit=1000, offset=0
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

        portfolio_params = (portfolio_id,)
        portfolio_field_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as portfolio_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'portfolio' AND entity_id = ?
            GROUP BY entity_id
            """,
            portfolio_params,
            key_name="portfolio_id",
        )
        portfolio_comment_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as portfolio_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'portfolio' AND entity_id = ?
            GROUP BY entity_id
            """,
            portfolio_params,
            key_name="portfolio_id",
        )
        portfolio_label_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as portfolio_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'portfolio' AND entity_id = ?
            GROUP BY entity_id
            """,
            portfolio_params,
            key_name="portfolio_id",
        )
        portfolio_watcher_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as portfolio_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'portfolio' AND entity_id = ?
            GROUP BY entity_id
            """,
            portfolio_params,
            key_name="portfolio_id",
        )
        portfolio_review_activity = await fetch_grouped_review_activity(
            self.db,
            scope_type="portfolio",
            params=portfolio_params,
            key_name="portfolio_id",
            select_key_sql="review.scope_id",
            where_sql="review.scope_id = ?",
        )
        program_side_activity = max_datetime(
            [
                (
                    await fetch_grouped_review_activity(
                        self.db,
                        scope_type="program",
                        params=portfolio_params,
                        key_name="portfolio_id",
                        select_key_sql="p.portfolio_id",
                        join_sql="JOIN programs p ON review.scope_id = p.id",
                        where_sql="p.portfolio_id = ?",
                    )
                ).get(portfolio_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.portfolio_id as portfolio_id, MAX(cf.updated_at) as ts
                        FROM custom_field_values cf
                        JOIN programs p ON cf.entity_id = p.id
                        WHERE cf.entity_type = 'program' AND p.portfolio_id = ?
                        GROUP BY p.portfolio_id
                        """,
                        portfolio_params,
                        key_name="portfolio_id",
                    )
                ).get(portfolio_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.portfolio_id as portfolio_id, MAX(c.updated_at) as ts
                        FROM comments c
                        JOIN programs p ON c.entity_id = p.id
                        WHERE c.entity_type = 'program' AND p.portfolio_id = ?
                        GROUP BY p.portfolio_id
                        """,
                        portfolio_params,
                        key_name="portfolio_id",
                    )
                ).get(portfolio_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.portfolio_id as portfolio_id,
                               MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
                        FROM label_assignments la
                        JOIN programs p ON la.entity_id = p.id
                        WHERE la.entity_type = 'program' AND p.portfolio_id = ?
                        GROUP BY p.portfolio_id
                        """,
                        portfolio_params,
                        key_name="portfolio_id",
                    )
                ).get(portfolio_id),
                (
                    await fetch_grouped_max_timestamps(
                        self.db,
                        """
                        SELECT p.portfolio_id as portfolio_id,
                               MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
                        FROM entity_watchers ew
                        JOIN programs p ON ew.entity_id = p.id
                        WHERE ew.entity_type = 'program' AND p.portfolio_id = ?
                        GROUP BY p.portfolio_id
                        """,
                        portfolio_params,
                        key_name="portfolio_id",
                    )
                ).get(portfolio_id),
            ]
        )

        metrics = build_rollup_metrics(effective_goals, objectives, tasks)
        last_activity = max_datetime(
            [
                portfolio.updated_at,
                portfolio_field_activity.get(portfolio_id),
                portfolio_comment_activity.get(portfolio_id),
                portfolio_label_activity.get(portfolio_id),
                portfolio_watcher_activity.get(portfolio_id),
                portfolio_review_activity.get(portfolio_id),
                max_datetime(program.updated_at for program in programs_result.items),
                program_side_activity,
                *project_activity.values(),
                *goal_activity.values(),
                *objective_activity.values(),
            ]
        )
        transition_repo = StateTransitionRepository(self.db)
        portfolio_transitions = await transition_repo.get_last_transition_map(
            "portfolio_status", [portfolio_id]
        )
        program_transitions = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT p.portfolio_id as portfolio_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN programs p ON st.entity_id = p.id
            WHERE st.entity_type = 'program_status' AND p.portfolio_id = ?
            GROUP BY p.portfolio_id
            """,
            portfolio_params,
            key_name="portfolio_id",
        )
        last_transition = max_datetime(
            [
                portfolio_transitions.get(portfolio_id),
                program_transitions.get(portfolio_id),
                *project_transition.values(),
                *goal_transition.values(),
                *objective_transition.values(),
            ]
        )
        stats = PortfolioStats(
            portfolio_id=portfolio_id,
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

        return PortfolioSummary(
            portfolio=portfolio,
            stats=stats,
            last_activity_at=last_activity,
            last_transition_at=last_transition,
            risk_level=metrics.risk_level,
        )

    async def get_portfolio_dashboard(
        self,
        status: PortfolioStatus | None = None,
        org_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PortfolioDashboard:
        """Get dashboard view for portfolios with rollups."""
        result = await self.list_portfolios(
            status=status, org_id=org_id, limit=limit, offset=offset
        )

        items: list[PortfolioDashboardItem] = []
        total_projects = 0
        total_goals = 0
        total_objectives = 0
        total_tasks = 0
        blocked_tasks = 0

        for portfolio in result.items:
            summary = await self.get_portfolio_summary(portfolio.id)
            if summary is None:
                continue

            stats = summary.stats
            items.append(
                PortfolioDashboardItem(
                    portfolio=summary.portfolio,
                    stats=stats,
                    risk_level=summary.risk_level,
                    last_activity_at=summary.last_activity_at,
                    last_transition_at=summary.last_transition_at,
                )
            )

            total_projects += stats.total_projects
            total_goals += stats.total_goals
            total_objectives += stats.total_objectives
            total_tasks += stats.total_tasks
            blocked_tasks += stats.blocked_tasks

        items = sort_items_by_bubbled_recency(
            items,
            activity_of=lambda item: item.last_activity_at,
            transition_of=lambda item: item.last_transition_at,
            updated_of=lambda item: item.portfolio.updated_at,
            label_of=lambda item: item.portfolio.name,
            id_of=lambda item: item.portfolio.id,
        )

        return PortfolioDashboard(
            items=items,
            total_portfolios=result.total_count,
            total_projects=total_projects,
            total_goals=total_goals,
            total_objectives=total_objectives,
            total_tasks=total_tasks,
            blocked_tasks=blocked_tasks,
        )
