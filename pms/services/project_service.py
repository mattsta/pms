"""Project service for high-level project operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import Revision, RevisionStore
from pms.models import GoalStatus, Project, ProjectStats, ProjectStatus, TaskStatus
from pms.models.json_types import JsonValue
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.organization_repository import OrganizationRepository
from pms.repositories.portfolio_repository import PortfolioRepository
from pms.repositories.program_repository import ProgramRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.goal_service import GoalService
from pms.services.rollup_utils import (
    fetch_grouped_review_activity,
    max_datetime,
    sort_items_by_bubbled_recency,
)

if TYPE_CHECKING:
    from pms.db.connection import Database

type TimestampSource = JsonValue | datetime


@dataclass
class ProjectSummary:
    """Summary of a project with key metrics."""

    project: Project
    stats: ProjectStats | None
    recent_activity_count: int = 0
    health_score: float = 0.0  # 0.0 to 1.0
    last_activity_at: datetime | None = None
    last_transition_at: datetime | None = None
    effective_status: ProjectStatus | None = None
    terminal_reason: str | None = None


@dataclass(frozen=True)
class ProjectLifecycleRollup:
    """Derived lifecycle state for a project from its linked execution graph."""

    effective_status: ProjectStatus
    terminal_reason: str | None = None


@dataclass
class ProjectDashboard:
    """Dashboard view of all projects."""

    active_projects: list[ProjectSummary]
    total_projects: int
    total_tasks: int
    completed_tasks: int
    blocked_tasks: int
    overdue_tasks: int
    goal_horizon_stats: dict[str, dict[str, float | int]] = field(default_factory=dict)
    visible_goal_horizon_stats: dict[str, dict[str, float | int]] = field(
        default_factory=dict
    )


class ProjectService:
    """
    Service for project management operations.

    Coordinates between repositories and provides high-level
    business operations with proper event sourcing and metrics.
    """

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

        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._org_repo = OrganizationRepository(
            db, event_store, revision_store, metrics
        )
        self._portfolio_repo = PortfolioRepository(
            db, event_store, revision_store, metrics
        )
        self._program_repo = ProgramRepository(db, event_store, revision_store, metrics)
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> ProjectService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._project_repo.with_context(self._context)
        self._org_repo.with_context(self._context)
        self._portfolio_repo.with_context(self._context)
        self._program_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
        return self

    def _parse_timestamp(self, value: TimestampSource) -> datetime | None:
        """Normalize stored timestamps into datetimes."""
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    async def _fetch_grouped_max_timestamps(
        self,
        query: str,
        params: tuple[object, ...],
        *,
        key_name: str = "project_id",
    ) -> dict[str, datetime | None]:
        """Run a grouped timestamp query keyed by project id."""
        rows = await self.db.fetch_all(query, params)
        return {
            row[key_name]: self._parse_timestamp(row.get("ts"))
            for row in rows
            if row.get(key_name)
        }

    async def get_last_activity_map(
        self,
        project_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep activity timestamps keyed by project id."""
        unique_ids = list(
            dict.fromkeys(project_id for project_id in project_ids if project_id)
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        projects = await self._project_repo.get_by_ids(unique_ids)
        activity_map: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        for project in projects:
            activity_map[project.id] = self._parse_timestamp(project.updated_at)

        task_rows = await self.db.fetch_all(
            f"SELECT id, project_id FROM tasks WHERE project_id IN ({placeholders})",
            params,
        )
        task_activity_by_project: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        if task_rows:
            task_activity = await self._task_repo.get_last_activity_map(
                [row["id"] for row in task_rows]
            )
            for row in task_rows:
                project_id = row["project_id"]
                task_activity_by_project[project_id] = max_datetime(
                    [
                        task_activity_by_project.get(project_id),
                        task_activity.get(row["id"]),
                    ]
                )

        goal_rows = await self.db.fetch_all(
            f"SELECT id, project_id FROM goals WHERE project_id IN ({placeholders})",
            params,
        )
        goal_service = GoalService(self.db, self.events, self.revisions, self.metrics)
        goal_activity_map = await goal_service.get_last_activity_map(
            [row["id"] for row in goal_rows]
        )
        goal_activity: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        for row in goal_rows:
            project_id = row["project_id"]
            goal_activity[project_id] = max_datetime(
                [
                    goal_activity.get(project_id),
                    goal_activity_map.get(row["id"]),
                ]
            )

        plan_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT project_id, MAX(updated_at) as ts
            FROM plans
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        test_run_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT project_id, MAX(finished_at) as ts
            FROM test_runs
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        project_field_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as project_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'project' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        project_comment_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as project_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'project' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        project_label_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as project_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'project' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        project_watcher_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as project_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'project' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        plan_field_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT p.project_id as project_id, MAX(cf.updated_at) as ts
            FROM custom_field_values cf
            JOIN plans p ON cf.entity_id = p.id
            WHERE cf.entity_type = 'plan' AND p.project_id IN ({placeholders})
            GROUP BY p.project_id
            """,
            params,
        )
        plan_comment_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT p.project_id as project_id, MAX(c.updated_at) as ts
            FROM comments c
            JOIN plans p ON c.entity_id = p.id
            WHERE c.entity_type = 'plan' AND p.project_id IN ({placeholders})
            GROUP BY p.project_id
            """,
            params,
        )
        plan_label_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT p.project_id as project_id,
                   MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
            FROM label_assignments la
            JOIN plans p ON la.entity_id = p.id
            WHERE la.entity_type = 'plan' AND p.project_id IN ({placeholders})
            GROUP BY p.project_id
            """,
            params,
        )
        plan_watcher_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT p.project_id as project_id,
                   MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
            FROM entity_watchers ew
            JOIN plans p ON ew.entity_id = p.id
            WHERE ew.entity_type = 'plan' AND p.project_id IN ({placeholders})
            GROUP BY p.project_id
            """,
            params,
        )
        plan_job_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT project_id, MAX(updated_at) as ts
            FROM plan_test_jobs
            WHERE project_id IN ({placeholders}) AND archived_at IS NULL
            GROUP BY project_id
            """,
            params,
        )
        review_activity = await fetch_grouped_review_activity(
            self.db,
            scope_type="project",
            params=params,
            key_name="project_id",
            select_key_sql="review.scope_id",
            where_sql=f"review.scope_id IN ({placeholders})",
        )

        for project_id in unique_ids:
            activity_map[project_id] = max_datetime(
                [
                    activity_map.get(project_id),
                    task_activity_by_project.get(project_id),
                    goal_activity.get(project_id),
                    plan_activity.get(project_id),
                    test_run_activity.get(project_id),
                    project_field_activity.get(project_id),
                    project_comment_activity.get(project_id),
                    project_label_activity.get(project_id),
                    project_watcher_activity.get(project_id),
                    plan_field_activity.get(project_id),
                    plan_comment_activity.get(project_id),
                    plan_label_activity.get(project_id),
                    plan_watcher_activity.get(project_id),
                    plan_job_activity.get(project_id),
                    review_activity.get(project_id),
                ]
            )

        return activity_map

    async def get_last_transition_map(
        self,
        project_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep transition timestamps keyed by project id."""
        unique_ids = list(
            dict.fromkeys(project_id for project_id in project_ids if project_id)
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        state_repo = StateTransitionRepository(self.db)
        project_status = await state_repo.get_last_transition_map(
            "project_status",
            unique_ids,
        )

        task_rows = await self.db.fetch_all(
            f"SELECT id, project_id FROM tasks WHERE project_id IN ({placeholders})",
            params,
        )
        task_transition_by_project: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        if task_rows:
            task_transitions = await self._task_repo.get_last_transition_map(
                [row["id"] for row in task_rows]
            )
            for row in task_rows:
                project_id = row["project_id"]
                task_transition_by_project[project_id] = max_datetime(
                    [
                        task_transition_by_project.get(project_id),
                        task_transitions.get(row["id"]),
                    ]
                )

        goal_rows = await self.db.fetch_all(
            f"SELECT id, project_id FROM goals WHERE project_id IN ({placeholders})",
            params,
        )
        goal_service = GoalService(self.db, self.events, self.revisions, self.metrics)
        goal_transition_map = await goal_service.get_last_transition_map(
            [row["id"] for row in goal_rows]
        )
        goal_transition_by_project: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        for row in goal_rows:
            project_id = row["project_id"]
            goal_transition_by_project[project_id] = max_datetime(
                [
                    goal_transition_by_project.get(project_id),
                    goal_transition_map.get(row["id"]),
                ]
            )

        plan_status_by_project = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT p.project_id as project_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN plans p ON st.entity_id = p.id
            WHERE st.entity_type = 'plan_status'
              AND p.project_id IN ({placeholders})
            GROUP BY p.project_id
            """,
            params,
        )

        transition_map: dict[str, datetime | None] = {
            project_id: None for project_id in unique_ids
        }
        for project_id in unique_ids:
            transition_map[project_id] = max_datetime(
                [
                    project_status.get(project_id),
                    task_transition_by_project.get(project_id),
                    goal_transition_by_project.get(project_id),
                    plan_status_by_project.get(project_id),
                ]
            )

        return transition_map

    async def get_lifecycle_rollup_map(
        self,
        projects: list[Project],
    ) -> dict[str, ProjectLifecycleRollup]:
        """Derive project lifecycle from linked task, goal, and plan execution."""
        if not projects:
            return {}

        unique_ids = list(
            dict.fromkeys(project.id for project in projects if project.id)
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)

        task_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) AS total_tasks,
                SUM(
                    CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END
                ) AS terminal_tasks
            FROM tasks
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        goal_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) AS total_goals,
                SUM(
                    CASE WHEN status IN ('completed', 'archived') THEN 1 ELSE 0 END
                ) AS terminal_goals
            FROM goals
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        plan_rows = await self.db.fetch_all(
            f"""
            SELECT
                COALESCE(p.project_id, g.project_id, og.project_id) AS project_id,
                COUNT(*) AS total_plans,
                SUM(
                    CASE WHEN p.status IN ('completed', 'archived') THEN 1 ELSE 0 END
                ) AS terminal_plans,
                SUM(
                    CASE WHEN p.status = 'active' THEN 1 ELSE 0 END
                ) AS active_plans
            FROM plans p
            LEFT JOIN goals g ON p.goal_id = g.id
            LEFT JOIN objectives o ON p.objective_id = o.id
            LEFT JOIN goals og ON o.goal_id = og.id
            WHERE COALESCE(p.project_id, g.project_id, og.project_id) IN ({placeholders})
            GROUP BY COALESCE(p.project_id, g.project_id, og.project_id)
            """,
            params,
        )

        task_rollups = {
            row["project_id"]: (
                int(row["total_tasks"] or 0),
                int(row["terminal_tasks"] or 0),
            )
            for row in task_rows
            if row.get("project_id")
        }
        goal_rollups = {
            row["project_id"]: (
                int(row["total_goals"] or 0),
                int(row["terminal_goals"] or 0),
            )
            for row in goal_rows
            if row.get("project_id")
        }
        plan_rollups = {
            row["project_id"]: (
                int(row["total_plans"] or 0),
                int(row["terminal_plans"] or 0),
                int(row["active_plans"] or 0),
            )
            for row in plan_rows
            if row.get("project_id")
        }

        rollups: dict[str, ProjectLifecycleRollup] = {}
        for project in projects:
            if project.status == ProjectStatus.ARCHIVED:
                rollups[project.id] = ProjectLifecycleRollup(
                    effective_status=ProjectStatus.ARCHIVED,
                    terminal_reason="project is already archived",
                )
                continue

            total_tasks, terminal_tasks = task_rollups.get(project.id, (0, 0))
            total_goals, terminal_goals = goal_rollups.get(project.id, (0, 0))
            total_plans, terminal_plans, active_plans = plan_rollups.get(
                project.id,
                (0, 0, 0),
            )

            has_any_scope = any(
                count > 0 for count in (total_tasks, total_goals, total_plans)
            )
            has_terminal_execution_scope = (
                (total_tasks > 0 and terminal_tasks == total_tasks)
                or (total_goals > 0 and terminal_goals == total_goals)
                or terminal_plans > 0
            )
            has_live_execution_scope = (
                (total_tasks > terminal_tasks)
                or (total_goals > terminal_goals)
                or active_plans > 0
            )
            all_scopes_terminal = (
                has_any_scope
                and has_terminal_execution_scope
                and not has_live_execution_scope
            )

            if all_scopes_terminal:
                rollups[project.id] = ProjectLifecycleRollup(
                    effective_status=ProjectStatus.COMPLETED,
                    terminal_reason="all linked execution scopes are already terminal",
                )
                continue

            # A stored-completed project should only reopen when live execution actually
            # exists. Draft plans are planning residue, not active execution by
            # themselves, so they should not resurrect an otherwise terminal project.
            if project.status == ProjectStatus.COMPLETED and has_live_execution_scope:
                rollups[project.id] = ProjectLifecycleRollup(
                    effective_status=ProjectStatus.ACTIVE,
                )
                continue

            rollups[project.id] = ProjectLifecycleRollup(
                effective_status=project.status,
            )

        return rollups

    async def _resolve_scope_links(
        self,
        org_id: str | None,
        portfolio_id: str | None,
        program_id: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        if program_id:
            program = await self._program_repo.get_by_id(program_id)
            if program is None:
                raise ValueError(f"Program '{program_id}' not found")
            if program.portfolio_id:
                if portfolio_id and portfolio_id != program.portfolio_id:
                    raise ValueError(
                        "Program belongs to a different portfolio than the one provided"
                    )
                portfolio_id = portfolio_id or program.portfolio_id
            if program.org_id:
                if org_id and org_id != program.org_id:
                    raise ValueError(
                        "Program belongs to a different organization than the one provided"
                    )
                org_id = org_id or program.org_id

        if portfolio_id:
            portfolio = await self._portfolio_repo.get_by_id(portfolio_id)
            if portfolio is None:
                raise ValueError(f"Portfolio '{portfolio_id}' not found")
            if portfolio.org_id:
                if org_id and org_id != portfolio.org_id:
                    raise ValueError(
                        "Portfolio belongs to a different organization than the one provided"
                    )
                org_id = org_id or portfolio.org_id

        if org_id:
            org = await self._org_repo.get_by_id(org_id)
            if org is None:
                raise ValueError(f"Organization '{org_id}' not found")

        return org_id, portfolio_id, program_id

    async def _add_project_to_program(self, program_id: str, project_id: str) -> None:
        program = await self._program_repo.get_by_id(program_id)
        if program is None:
            raise ValueError(f"Program '{program_id}' not found")
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' not found")
        if project.program_id == program_id:
            return
        await self._project_repo.assign_to_program(
            project_id=project_id,
            program_id=program_id,
            message=f"Assigned to program {program_id}",
        )

    async def _remove_project_from_program(
        self, program_id: str, project_id: str
    ) -> None:
        project = await self._project_repo.get_by_id(project_id)
        if project is None or project.program_id != program_id:
            return
        await self._project_repo.assign_to_program(
            project_id=project_id,
            program_id=None,
            message=f"Unlinked from program {program_id}",
        )

    async def _add_project_to_portfolio(
        self, portfolio_id: str, project_id: str
    ) -> None:
        portfolio = await self._portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio '{portfolio_id}' not found")
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise ValueError(f"Project '{project_id}' not found")
        if project.portfolio_id == portfolio_id:
            return
        await self._project_repo.assign_to_portfolio(
            project_id=project_id,
            portfolio_id=portfolio_id,
            message=f"Assigned to portfolio {portfolio_id}",
        )

    async def _remove_project_from_portfolio(
        self, portfolio_id: str, project_id: str
    ) -> None:
        project = await self._project_repo.get_by_id(project_id)
        if project is None or project.portfolio_id != portfolio_id:
            return
        await self._project_repo.assign_to_portfolio(
            project_id=project_id,
            portfolio_id=None,
            message=f"Unlinked from portfolio {portfolio_id}",
        )

    async def create_project(
        self,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        product_id: str | None = None,
    ) -> Project:
        """Create a new project with initial setup."""
        async with self._project_repo.db.transaction():
            (
                resolved_org_id,
                resolved_portfolio_id,
                resolved_program_id,
            ) = await self._resolve_scope_links(org_id, portfolio_id, program_id)
            project = await self._project_repo.create(
                name=name,
                description=description,
                tags=tags,
                org_id=resolved_org_id,
                portfolio_id=resolved_portfolio_id,
                program_id=resolved_program_id,
                product_id=product_id,
                message=f"Created project '{name}'",
            )

            await self.metrics.record_counter(
                "project.created",
                labels={"name": name},
            )
            await self.metrics.flush()

        return project

    async def get_project(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        return await self._project_repo.get_by_id(project_id)

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name."""
        return await self._project_repo.get_by_name(name)

    async def list_projects(
        self,
        status: ProjectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Project]:
        """List projects with optional filtering."""
        if status:
            return await self._project_repo.get_by_status(status, limit, offset)
        return await self._project_repo.get_all(limit, offset)

    async def list_all_projects(
        self,
        status: ProjectStatus | None = None,
        *,
        batch_size: int = 200,
    ) -> list[Project]:
        """List all projects for a status, paging until exhaustion."""
        offset = 0
        items: list[Project] = []
        while True:
            result = await self.list_projects(
                status=status, limit=batch_size, offset=offset
            )
            items.extend(result.items)
            if not result.has_more:
                break
            offset += result.limit
        return items

    async def build_project_summary_map(
        self,
        projects: list[Project],
    ) -> dict[str, ProjectSummary]:
        """Build lifecycle-aware summaries for a project set using shared bulk rollups."""
        if not projects:
            return {}

        project_ids = [project.id for project in projects]
        stats_map = await self._project_repo.get_stats_bulk(project_ids)
        stats_map = await self._with_effective_task_rollups(stats_map)
        stats_map = await self._with_effective_goal_rollups(stats_map)
        activity_map = await self.get_last_activity_map(project_ids)
        transition_map = await self.get_last_transition_map(project_ids)
        lifecycle_rollups = await self.get_lifecycle_rollup_map(projects)

        summaries: dict[str, ProjectSummary] = {}
        for project in projects:
            stats = stats_map.get(project.id)
            lifecycle_rollup = lifecycle_rollups.get(project.id)
            summaries[project.id] = ProjectSummary(
                project=project,
                stats=stats,
                health_score=self._calculate_health_score(stats),
                last_activity_at=activity_map.get(project.id),
                last_transition_at=transition_map.get(project.id),
                effective_status=(
                    lifecycle_rollup.effective_status
                    if lifecycle_rollup is not None
                    else project.status
                ),
                terminal_reason=(
                    lifecycle_rollup.terminal_reason
                    if lifecycle_rollup is not None
                    else None
                ),
            )
        return summaries

    async def update_project(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        tags: list[str] | None = None,
        product_id: str | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
    ) -> Project | None:
        """Update project details."""
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            return None

        async with self._project_repo.db.transaction():
            resolved_org_id = project.org_id
            resolved_portfolio_id = project.portfolio_id
            resolved_program_id = project.program_id
            if org_id is not None or portfolio_id is not None or program_id is not None:
                candidate_org: str | None
                candidate_portfolio: str | None
                candidate_program: str | None
                if program_id is not None:
                    candidate_org = org_id
                    candidate_portfolio = portfolio_id
                    candidate_program = program_id
                elif portfolio_id is not None:
                    candidate_org = org_id if org_id is not None else project.org_id
                    candidate_portfolio = portfolio_id
                    candidate_program = project.program_id
                else:
                    candidate_org = org_id
                    candidate_portfolio = project.portfolio_id
                    candidate_program = project.program_id

                (
                    resolved_org_id,
                    resolved_portfolio_id,
                    resolved_program_id,
                ) = await self._resolve_scope_links(
                    candidate_org, candidate_portfolio, candidate_program
                )

            updated = await self._project_repo.update(
                project_id=project_id,
                name=name,
                description=description,
                status=status,
                tags=tags,
            )

            if product_id is not None and product_id != project.product_id:
                assigned = await self._project_repo.assign_to_product(
                    project_id=project_id,
                    product_id=product_id,
                    message=f"Assigned to product {product_id}",
                )
                if assigned is not None:
                    updated = assigned

            if resolved_program_id != project.program_id:
                assigned = await self._project_repo.assign_to_program(
                    project_id=project_id,
                    program_id=resolved_program_id,
                    message=f"Assigned to program {resolved_program_id or '-'}",
                )
                if assigned is not None:
                    updated = assigned

            if resolved_portfolio_id != project.portfolio_id:
                assigned = await self._project_repo.assign_to_portfolio(
                    project_id=project_id,
                    portfolio_id=resolved_portfolio_id,
                    message=f"Assigned to portfolio {resolved_portfolio_id or '-'}",
                )
                if assigned is not None:
                    updated = assigned

            if resolved_org_id != project.org_id:
                assigned = await self._project_repo.assign_to_org(
                    project_id=project_id,
                    org_id=resolved_org_id,
                    message=f"Assigned to org {resolved_org_id or '-'}",
                )
                if assigned is not None:
                    updated = assigned

            if updated:
                await self.metrics.record_counter("project.updated")
                await self.metrics.flush()

        return updated

    async def archive_project(self, project_id: str) -> Project | None:
        """Archive a project."""
        async with self._project_repo.db.transaction():
            project = await self._project_repo.archive(project_id)
            if project:
                await self.metrics.record_counter("project.archived")
                await self.metrics.flush()

        return project

    async def get_project_summary(self, project_id: str) -> ProjectSummary | None:
        """Get project summary with stats and health score."""
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            return None

        # Count recent activity (events in last 7 days)
        recent_events = await self.events.get_all_events(limit=100)
        recent_activity_count = sum(
            1 for e in recent_events if e.aggregate_id == project_id
        )
        summary = (await self.build_project_summary_map([project])).get(project.id)
        if summary is None:
            return None
        summary.recent_activity_count = recent_activity_count
        return summary

    async def get_dashboard(self) -> ProjectDashboard:
        """Get dashboard overview of all projects."""
        # Dashboard truthfulness depends on seeing the whole active population, not
        # just the first repository page.
        from pms.repositories.task_repository import TaskRepository

        dashboard_candidates = [
            project
            for project in await self.list_all_projects()
            if project.status != ProjectStatus.ARCHIVED
        ]
        lifecycle_rollups = await self.get_lifecycle_rollup_map(dashboard_candidates)
        active_projects = [
            project
            for project in dashboard_candidates
            if lifecycle_rollups.get(
                project.id, ProjectLifecycleRollup(project.status)
            ).effective_status
            == ProjectStatus.ACTIVE
        ]
        project_rollup = await self._project_repo.get_global_rollup()
        task_repo = TaskRepository(self.db, self.events, self.revisions, self.metrics)
        instance_task_rollup = await task_repo.get_global_rollup()
        summary_map = await self.build_project_summary_map(active_projects)
        summaries = []
        total_tasks = 0
        completed_tasks = 0
        blocked_tasks = 0
        overdue_tasks = 0

        for project in active_projects:
            summary = summary_map.get(project.id)
            if summary is None:
                continue
            summaries.append(summary)
            stats = summary.stats
            if stats:
                total_tasks += stats.total_tasks or 0
                completed_tasks += stats.completed_tasks or 0
                blocked_tasks += stats.blocked_tasks or 0
                overdue_tasks += stats.overdue_tasks or 0

        summaries = sort_items_by_bubbled_recency(
            summaries,
            activity_of=lambda summary: summary.last_activity_at,
            transition_of=lambda summary: summary.last_transition_at,
            updated_of=lambda summary: summary.project.updated_at,
            label_of=lambda summary: summary.project.name,
            id_of=lambda summary: summary.project.id,
        )

        goal_horizon_stats = await self._compute_effective_goal_horizon_stats()
        return ProjectDashboard(
            active_projects=summaries,
            total_projects=project_rollup["total_projects"],
            total_tasks=instance_task_rollup["total_tasks"],
            completed_tasks=instance_task_rollup["completed_tasks"],
            blocked_tasks=blocked_tasks,
            overdue_tasks=overdue_tasks,
            goal_horizon_stats=goal_horizon_stats,
        )

    async def compute_effective_goal_horizon_stats(
        self,
        project_ids: list[str] | None = None,
    ) -> dict[str, dict[str, float | int]]:
        """Build execution-aware goal horizon stats for all or selected projects."""
        return await self._compute_effective_goal_horizon_stats(project_ids)

    async def _with_effective_goal_rollups(
        self, stats_map: dict[str, ProjectStats]
    ) -> dict[str, ProjectStats]:
        """Overlay execution-aware goal rollup stats onto project stats."""
        if not stats_map:
            return stats_map

        goal_service = GoalService(self.db, self.events, self.revisions, self.metrics)
        goal_rollups = await goal_service.get_project_goal_rollup_stats(
            list(stats_map.keys())
        )
        for project_id, stats in stats_map.items():
            effective = goal_rollups.get(project_id)
            if effective is None:
                continue
            stats.total_goals = effective.total_goals
            stats.completed_goals = effective.completed_goals
            stats.avg_goal_progress = effective.avg_progress
        return stats_map

    async def _with_effective_task_rollups(
        self, stats_map: dict[str, ProjectStats]
    ) -> dict[str, ProjectStats]:
        """Overlay execution-aware task counts onto project stats."""
        if not stats_map:
            return stats_map

        from pms.services.task_service import TaskService

        task_service = TaskService(self.db, self.events, self.revisions, self.metrics)
        for project_id, stats in stats_map.items():
            tasks: list = []
            offset = 0
            page_size = 500
            while True:
                result = await task_service.list_tasks(
                    project_id=project_id,
                    include_subtasks=True,
                    limit=page_size,
                    offset=offset,
                )
                tasks.extend(result.items)
                if not result.has_more:
                    break
                offset += result.limit

            stats.total_tasks = len(tasks)
            stats.completed_tasks = sum(1 for task in tasks if task.status.is_terminal)
            stats.in_progress_tasks = sum(
                1 for task in tasks if task.status == TaskStatus.IN_PROGRESS
            )
            stats.blocked_tasks = sum(
                1 for task in tasks if task.status == TaskStatus.BLOCKED
            )
        return stats_map

    async def _compute_effective_goal_horizon_stats(
        self,
        project_ids: list[str] | None = None,
    ) -> dict[str, dict[str, float | int]]:
        """Build execution-aware goal horizon stats across all goals."""
        goal_rows = await self.db.fetch_all("SELECT * FROM goals")
        if not goal_rows:
            return {}

        goal_service = GoalService(self.db, self.events, self.revisions, self.metrics)
        project_id_filter = set(project_ids or [])
        goals = [
            goal_service._goal_repo._model_from_row(row)
            for row in goal_rows
            if not project_id_filter or row["project_id"] in project_id_filter
        ]
        if not goals:
            return {}
        effective_rollups = await goal_service.get_effective_rollups_for_goals(goals)

        aggregates: dict[str, dict[str, float | int]] = {}
        for goal in goals:
            horizon = goal.horizon.value
            stats = aggregates.setdefault(
                horizon,
                {"total_goals": 0, "completed_goals": 0, "avg_progress": 0.0},
            )
            stats["total_goals"] += 1
            effective = effective_rollups.get(goal.id)
            if effective is None:
                progress = goal.progress_percent
                completed = goal.status == GoalStatus.COMPLETED
            else:
                progress = effective.progress_percent
                completed = effective.status == GoalStatus.COMPLETED.value
            if completed:
                stats["completed_goals"] += 1
            stats["avg_progress"] += float(progress)

        for stats in aggregates.values():
            total_goals = int(stats["total_goals"])
            stats["avg_progress"] = (
                float(stats["avg_progress"]) / total_goals if total_goals else 0.0
            )
        return aggregates

    async def _compute_last_activity(self, project: Project) -> datetime | None:
        """Compute last activity timestamp for a project including children."""
        return (await self.get_last_activity_map([project.id])).get(project.id)

    async def _compute_last_transition(self, project: Project) -> datetime | None:
        """Compute deep transition timestamp for a project and its graph."""
        return (await self.get_last_transition_map([project.id])).get(project.id)

    async def search_projects(
        self,
        query: str,
        status: ProjectStatus | None = None,
        tags: list[str] | None = None,
    ) -> list[Project]:
        """Search for projects."""
        return await self._project_repo.search(query, status, tags)

    async def reconcile_project_state(self, project_id: str) -> Project | None:
        """
        Reconcile project state by rebuilding from events.

        This is useful for recovery or verification.
        """
        project = await self._project_repo.rebuild_from_events(project_id)
        if project:
            await self.metrics.record_counter(
                "project.reconciled",
                labels={"project_id": project_id},
            )
        return project

    async def reconcile_project_lifecycle(self, project_id: str) -> Project | None:
        """Persist the effective lifecycle state derived from the linked graph."""
        project = await self._project_repo.get_by_id(project_id)
        if project is None or project.status == ProjectStatus.ARCHIVED:
            return project

        lifecycle_rollup = (await self.get_lifecycle_rollup_map([project])).get(
            project.id
        )
        if lifecycle_rollup is None:
            return project

        if (
            lifecycle_rollup.effective_status == ProjectStatus.COMPLETED
            and project.status != ProjectStatus.COMPLETED
        ):
            await self._project_repo.complete(
                project_id,
                message="Reconciled project lifecycle from linked execution state",
            )
            return await self._project_repo.get_by_id(project_id)

        if (
            lifecycle_rollup.effective_status == ProjectStatus.ACTIVE
            and project.status == ProjectStatus.COMPLETED
        ):
            await self._project_repo.reactivate(
                project_id,
                message="Reopened project because linked execution is no longer terminal",
            )
            return await self._project_repo.get_by_id(project_id)

        return project

    async def get_project_history(
        self,
        project_id: str,
        limit: int = 50,
    ) -> list[Revision[Project]]:
        """Get project revision history."""
        return await self._project_repo.get_history(project_id, limit)

    async def get_project_at_revision(
        self,
        project_id: str,
        revision_number: int,
    ) -> Project | None:
        """Get project state at a specific revision."""
        return await self._project_repo.get_at_revision(project_id, revision_number)

    def _calculate_health_score(self, stats: ProjectStats | None) -> float:
        """
        Calculate project health score (0.0 to 1.0).

        Factors:
        - Completion rate (higher is better)
        - Blocked task ratio (lower is better)
        - Overdue task ratio (lower is better)
        - Progress vs estimates (closer is better)
        """
        if stats is None or stats.total_tasks == 0:
            return 1.0  # New project with no tasks is healthy

        # Completion rate contributes 50%
        completion_score = stats.completion_percent / 100 * 0.5

        # Blocked ratio contributes 25%
        blocked_ratio = stats.blocked_tasks / stats.total_tasks
        blocked_score = (1 - blocked_ratio) * 0.25

        # Overdue ratio contributes 25%
        overdue_ratio = stats.overdue_tasks / stats.total_tasks
        overdue_score = (1 - overdue_ratio) * 0.25

        return min(1.0, completion_score + blocked_score + overdue_score)
