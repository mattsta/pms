"""Program service for program operations and rollups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import Program, ProgramStats, ProgramStatus
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
class ProgramSummary:
    """Summary of a program with rollup metrics."""

    program: Program
    stats: ProgramStats
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    risk_level: RiskLevel = "low"


@dataclass
class ProgramDashboardItem:
    """Compact dashboard item for a program."""

    program: Program
    stats: ProgramStats
    risk_level: RiskLevel
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None


@dataclass
class ProgramDashboard:
    """Dashboard view for programs."""

    items: list[ProgramDashboardItem]
    total_programs: int
    total_projects: int
    total_goals: int
    total_objectives: int
    total_tasks: int
    blocked_tasks: int


class ProgramService:
    """Service for program management operations."""

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

        self._program_repo = ProgramRepository(db, event_store, revision_store, metrics)
        self._portfolio_repo = PortfolioRepository(
            db, event_store, revision_store, metrics
        )
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
    ) -> ProgramService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._program_repo.with_context(self._context)
        self._portfolio_repo.with_context(self._context)
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

    async def _validate_scope_write_inputs(
        self,
        *,
        project_ids: list[str] | None,
        goal_ids: list[str] | None,
        objective_ids: list[str] | None,
    ) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
        """Validate project, goal, and objective links for a program write."""
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

    async def create_program(
        self,
        name: str,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        description: str | None = None,
        owner: str | None = None,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Program:
        """Create a new program."""
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
        async with self._program_repo.db.transaction():
            program = await self._program_repo._create_in_transaction(
                name=name,
                org_id=org_id,
                portfolio_id=portfolio_id,
                description=description,
                owner=canonical_owner,
                owner_id=owner_id,
                goal_ids=validated_goal_ids,
                objective_ids=validated_objective_ids,
                tags=tags,
                message=f"Created program '{name}'",
            )

            if validated_project_ids:
                for project_id in validated_project_ids:
                    await self._project_repo.assign_to_program(
                        project_id,
                        program.id,
                        message=f"Assigned to program {program.id}",
                    )
                    if program.portfolio_id:
                        await self._project_repo.assign_to_portfolio(
                            project_id,
                            program.portfolio_id,
                            message=f"Assigned to portfolio {program.portfolio_id}",
                        )
                    if program.org_id:
                        await self._project_repo.assign_to_org(
                            project_id,
                            program.org_id,
                            message=f"Assigned to org {program.org_id}",
                        )

            await self.metrics.record_counter("program.created")
            await self.metrics.flush()

        return await self._program_repo.get_by_id(program.id) or program

    async def get_program(self, program_id: str) -> Program | None:
        """Get program by ID."""
        return await self._program_repo.get_by_id(program_id)

    async def get_program_by_name(self, name: str) -> Program | None:
        """Get program by name."""
        return await self._program_repo.get_by_name(name)

    async def get_program_scope_snapshot(
        self,
        program_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> HierarchyScopeSnapshot:
        """Return authoritative linked entities for a program."""
        return await self._hierarchy.get_program_snapshot(
            program_id,
            limit=limit,
            offset=offset,
        )

    async def get_program_project_ids(self, program_id: str) -> list[str]:
        """Return authoritative project ids for a program."""
        return await self._hierarchy.get_project_ids_for_scope("program", program_id)

    async def list_programs(
        self,
        status: ProgramStatus | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Program]:
        """List programs with optional filters."""
        return await self._program_repo.list_filtered(
            org_id=org_id,
            portfolio_id=portfolio_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_program(
        self,
        program_id: str,
        name: str | None = None,
        description: str | None = None,
        status: ProgramStatus | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        project_ids: list[str] | None = None,
        goal_ids: list[str] | None = None,
        objective_ids: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Program | None:
        """Update program details."""
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
        async with self._program_repo.db.transaction():
            existing = await self._program_repo.get_by_id(program_id)
            if existing is None:
                return None
            program = await self._program_repo._update_in_transaction(
                program_id=program_id,
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

            if program:
                if validated_project_ids is not None:
                    old_ids = set(existing.project_ids)
                    new_ids = set(validated_project_ids)
                    for project_id in new_ids - old_ids:
                        await self._project_repo.assign_to_program(
                            project_id,
                            program.id,
                            message=f"Assigned to program {program.id}",
                        )
                        if program.portfolio_id:
                            await self._project_repo.assign_to_portfolio(
                                project_id,
                                program.portfolio_id,
                                message=f"Assigned to portfolio {program.portfolio_id}",
                            )
                        if program.org_id:
                            await self._project_repo.assign_to_org(
                                project_id,
                                program.org_id,
                                message=f"Assigned to org {program.org_id}",
                            )
                    for project_id in old_ids - new_ids:
                        project = await self._project_repo.get_by_id(project_id)
                        if project and project.program_id == program.id:
                            await self._project_repo.assign_to_program(
                                project_id,
                                None,
                                message=f"Unlinked from program {program.id}",
                            )

                await self.metrics.record_counter("program.updated")
                await self.metrics.flush()

        if program is None:
            return None
        return await self._program_repo.get_by_id(program.id) or program

    async def archive_program(self, program_id: str) -> Program | None:
        """Archive a program."""
        async with self._program_repo.db.transaction():
            program = await self._program_repo.archive(program_id)
            if program:
                await self.metrics.record_counter("program.archived")
                await self.metrics.flush()
        return program

    async def get_program_summary(self, program_id: str) -> ProgramSummary | None:
        """Get program summary with rollup metrics."""
        program = await self._program_repo.get_by_id(program_id)
        if program is None:
            return None

        project_ids = await self.get_program_project_ids(program_id)
        goals, objectives, tasks = await collect_rollup_entities(
            self._goal_repo,
            self._objective_repo,
            self._task_repo,
            program.goal_ids,
            program.objective_ids,
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

        program_params = (program_id,)
        program_field_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as program_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'program' AND entity_id = ?
            GROUP BY entity_id
            """,
            program_params,
            key_name="program_id",
        )
        program_comment_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as program_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'program' AND entity_id = ?
            GROUP BY entity_id
            """,
            program_params,
            key_name="program_id",
        )
        program_label_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as program_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'program' AND entity_id = ?
            GROUP BY entity_id
            """,
            program_params,
            key_name="program_id",
        )
        program_watcher_activity = await fetch_grouped_max_timestamps(
            self.db,
            """
            SELECT entity_id as program_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'program' AND entity_id = ?
            GROUP BY entity_id
            """,
            program_params,
            key_name="program_id",
        )
        program_review_activity = await fetch_grouped_review_activity(
            self.db,
            scope_type="program",
            params=program_params,
            key_name="program_id",
            select_key_sql="review.scope_id",
            where_sql="review.scope_id = ?",
        )

        metrics = build_rollup_metrics(effective_goals, objectives, tasks)
        last_activity = max_datetime(
            [
                program.updated_at,
                program_field_activity.get(program_id),
                program_comment_activity.get(program_id),
                program_label_activity.get(program_id),
                program_watcher_activity.get(program_id),
                program_review_activity.get(program_id),
                *project_activity.values(),
                *goal_activity.values(),
                *objective_activity.values(),
            ]
        )
        transition_repo = StateTransitionRepository(self.db)
        program_transitions = await transition_repo.get_last_transition_map(
            "program_status", [program_id]
        )
        last_transition = max_datetime(
            [
                program_transitions.get(program_id),
                *project_transition.values(),
                *goal_transition.values(),
                *objective_transition.values(),
            ]
        )
        stats = ProgramStats(
            program_id=program_id,
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

        return ProgramSummary(
            program=program,
            stats=stats,
            last_activity_at=last_activity,
            last_transition_at=last_transition,
            risk_level=metrics.risk_level,
        )

    async def get_program_dashboard(
        self,
        status: ProgramStatus | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ProgramDashboard:
        """Get dashboard view for programs with rollups."""
        result = await self.list_programs(
            status=status,
            org_id=org_id,
            portfolio_id=portfolio_id,
            limit=limit,
            offset=offset,
        )

        items: list[ProgramDashboardItem] = []
        total_projects = 0
        total_goals = 0
        total_objectives = 0
        total_tasks = 0
        blocked_tasks = 0

        for program in result.items:
            summary = await self.get_program_summary(program.id)
            if summary is None:
                continue

            stats = summary.stats
            items.append(
                ProgramDashboardItem(
                    program=summary.program,
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
            updated_of=lambda item: item.program.updated_at,
            label_of=lambda item: item.program.name,
            id_of=lambda item: item.program.id,
        )

        return ProgramDashboard(
            items=items,
            total_programs=result.total_count,
            total_projects=total_projects,
            total_goals=total_goals,
            total_objectives=total_objectives,
            total_tasks=total_tasks,
            blocked_tasks=blocked_tasks,
        )
