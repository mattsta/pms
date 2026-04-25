"""Goal service for high-level goal operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models import (
    Goal,
    GoalHorizon,
    GoalStatus,
    KeyResult,
    Objective,
    Task,
    TaskStatus,
)
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.key_result_repository import KeyResultRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.product_repository import ProductRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.state_transition_repository import StateTransitionRepository
from pms.repositories.task_repository import TaskRepository
from pms.services.link_validation import validate_optional_reference_id
from pms.services.rollup_utils import max_datetime

if TYPE_CHECKING:
    from pms.db.connection import Database


@dataclass
class GoalSummary:
    """Summary of a goal with rollup metrics."""

    goal: Goal
    objective_count: int
    completed_objectives: int
    key_result_count: int
    completed_key_results: int
    average_progress: float
    execution: GoalExecutionSummary | None
    effective_rollup: GoalEffectiveRollup
    effective_hierarchy: GoalEffectiveHierarchy


@dataclass
class ObjectiveSummary:
    """Summary of an objective with key-result-aware rollup metrics."""

    objective: Objective
    key_result_count: int
    completed_key_results: int
    average_progress: float
    effective_rollup: ObjectiveEffectiveRollup
    effective_hierarchy: ObjectiveEffectiveHierarchy


@dataclass(frozen=True)
class GoalEffectiveRollup:
    """Effective operator-facing rollup combining stored goal and execution state."""

    progress_percent: int
    status: str
    basis: str
    reason: str | None


@dataclass(frozen=True)
class ObjectiveEffectiveRollup:
    """Effective operator-facing rollup combining stored objective and key result state."""

    progress_percent: int
    status: str
    basis: str
    reason: str | None


@dataclass(frozen=True)
class GoalEffectiveHierarchy:
    """Execution-aware hierarchy-facing rollup without fabricating stored counts."""

    objective_count: int
    completed_objectives: int
    key_result_count: int
    completed_key_results: int
    average_progress: float
    basis: str
    reason: str | None


@dataclass(frozen=True)
class ObjectiveEffectiveHierarchy:
    """Key-result-aware hierarchy-facing rollup for one objective."""

    key_result_count: int
    completed_key_results: int
    average_progress: float
    basis: str
    reason: str | None


@dataclass(frozen=True)
class GoalExecutionSummary:
    """Execution progress for tasks linked through the goal's project."""

    total_tasks: int
    completed_tasks: int
    in_progress_tasks: int
    blocked_tasks: int
    average_task_progress: float
    completion_percent: float
    readiness_state: str
    consistency_status: str
    consistency_reason: str | None
    focus_task: GoalExecutionFocusTaskSummary | None
    terminal_reason: str | None
    population_basis: str = "project_scoped_execution_alias"
    scoped_goal_count: int = 1


@dataclass(frozen=True)
class GoalExecutionFocusTaskSummary:
    """Most actionable task currently linked to a goal's execution scope."""

    id: str
    title: str
    status: str
    current_progress_percent: int
    reason: str
    completion_criteria_count: int
    has_completion_criteria: bool


def goal_lifecycle_terminal_reason(
    goal: Goal,
    *,
    effective_rollup: GoalEffectiveRollup,
    execution: GoalExecutionSummary | None,
) -> str | None:
    """Return the operator-facing terminal reason for one goal lifecycle view."""
    if execution is not None and execution.terminal_reason is not None:
        return execution.terminal_reason
    effective_status = effective_rollup.status
    if effective_status == GoalStatus.ARCHIVED.value:
        return "goal is already archived"
    if (
        effective_status == GoalStatus.COMPLETED.value
        or goal.status == GoalStatus.COMPLETED
    ):
        return "goal is already marked completed"
    return None


def objective_lifecycle_terminal_reason(
    objective: Objective,
    *,
    effective_rollup: ObjectiveEffectiveRollup,
) -> str | None:
    """Return the operator-facing terminal reason for one objective lifecycle view."""
    effective_status = effective_rollup.status
    if effective_status == GoalStatus.ARCHIVED.value:
        return "objective is already archived"
    if effective_status == GoalStatus.COMPLETED.value:
        if effective_rollup.basis == "key_result_rollup":
            return "all linked key results are already complete"
        if objective.status == GoalStatus.COMPLETED:
            return "objective is already marked completed"
        return "objective is already terminal"
    return None


def key_result_lifecycle_terminal_reason(key_result: KeyResult) -> str | None:
    """Return the operator-facing terminal reason for one key result lifecycle view."""
    if key_result.status == GoalStatus.ARCHIVED:
        return "key result is already archived"
    if key_result.status == GoalStatus.COMPLETED:
        return "key result is already marked completed"
    return None


@dataclass(frozen=True)
class GoalRollupSnapshot:
    """Stable rollup view of a goal's active objectives."""

    objective_count: int
    average_progress: int
    status: GoalStatus | None


@dataclass(frozen=True)
class ProjectGoalRollupStats:
    """Execution-aware goal rollup stats for a single project."""

    project_id: str
    total_goals: int
    completed_goals: int
    avg_progress: float


@dataclass(frozen=True)
class ObjectiveKeyResultRollupStats:
    """Aggregated key result rollup stats for one objective."""

    key_result_count: int
    completed_key_results: int
    active_key_results: int
    on_hold_key_results: int
    archived_key_results: int
    average_progress: float


class GoalService:
    """Service for goal management operations."""

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

        self._goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        self._objective_repo = ObjectiveRepository(
            db, event_store, revision_store, metrics
        )
        self._key_result_repo = KeyResultRepository(
            db, event_store, revision_store, metrics
        )
        self._plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        self._product_repo = ProductRepository(db, event_store, revision_store, metrics)
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> GoalService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._goal_repo.with_context(self._context)
        self._objective_repo.with_context(self._context)
        self._key_result_repo.with_context(self._context)
        self._task_repo.with_context(self._context)
        return self

    def _parse_timestamp(self, value: object) -> datetime | None:
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
        key_name: str,
    ) -> dict[str, datetime | None]:
        """Run a grouped timestamp query keyed by entity id."""
        rows = await self.db.fetch_all(query, params)
        return {
            row[key_name]: self._parse_timestamp(row.get("ts"))
            for row in rows
            if row.get(key_name)
        }

    async def get_objective_last_activity_map(
        self,
        objective_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep activity timestamps keyed by objective id."""
        unique_ids = list(
            dict.fromkeys(
                objective_id for objective_id in objective_ids if objective_id
            )
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        objective_rows = await self.db.fetch_all(
            f"SELECT id, updated_at FROM objectives WHERE id IN ({placeholders})",
            params,
        )
        activity_map: dict[str, datetime | None] = {
            objective_id: None for objective_id in unique_ids
        }
        for row in objective_rows:
            activity_map[row["id"]] = self._parse_timestamp(row.get("updated_at"))

        key_result_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT objective_id, MAX(updated_at) as ts
            FROM key_results
            WHERE objective_id IN ({placeholders})
            GROUP BY objective_id
            """,
            params,
            key_name="objective_id",
        )
        objective_field_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as objective_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'objective' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="objective_id",
        )
        objective_comment_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as objective_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'objective' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="objective_id",
        )
        objective_label_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as objective_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'objective' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="objective_id",
        )
        objective_watcher_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as objective_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'objective' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="objective_id",
        )
        key_result_field_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT kr.objective_id as objective_id, MAX(cf.updated_at) as ts
            FROM custom_field_values cf
            JOIN key_results kr ON cf.entity_id = kr.id
            WHERE cf.entity_type = 'key_result' AND kr.objective_id IN ({placeholders})
            GROUP BY kr.objective_id
            """,
            params,
            key_name="objective_id",
        )
        key_result_comment_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT kr.objective_id as objective_id, MAX(c.updated_at) as ts
            FROM comments c
            JOIN key_results kr ON c.entity_id = kr.id
            WHERE c.entity_type = 'key_result' AND kr.objective_id IN ({placeholders})
            GROUP BY kr.objective_id
            """,
            params,
            key_name="objective_id",
        )
        key_result_label_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT kr.objective_id as objective_id,
                   MAX(COALESCE(la.archived_at, la.updated_at, la.created_at)) as ts
            FROM label_assignments la
            JOIN key_results kr ON la.entity_id = kr.id
            WHERE la.entity_type = 'key_result' AND kr.objective_id IN ({placeholders})
            GROUP BY kr.objective_id
            """,
            params,
            key_name="objective_id",
        )
        key_result_watcher_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT kr.objective_id as objective_id,
                   MAX(COALESCE(ew.archived_at, ew.updated_at, ew.created_at)) as ts
            FROM entity_watchers ew
            JOIN key_results kr ON ew.entity_id = kr.id
            WHERE ew.entity_type = 'key_result' AND kr.objective_id IN ({placeholders})
            GROUP BY kr.objective_id
            """,
            params,
            key_name="objective_id",
        )

        for objective_id in unique_ids:
            activity_map[objective_id] = max_datetime(
                [
                    activity_map.get(objective_id),
                    key_result_activity.get(objective_id),
                    objective_field_activity.get(objective_id),
                    objective_comment_activity.get(objective_id),
                    objective_label_activity.get(objective_id),
                    objective_watcher_activity.get(objective_id),
                    key_result_field_activity.get(objective_id),
                    key_result_comment_activity.get(objective_id),
                    key_result_label_activity.get(objective_id),
                    key_result_watcher_activity.get(objective_id),
                ]
            )

        return activity_map

    async def get_last_activity_map(
        self,
        goal_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep activity timestamps keyed by goal id."""
        unique_ids = list(dict.fromkeys(goal_id for goal_id in goal_ids if goal_id))
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        goal_rows = await self.db.fetch_all(
            f"SELECT id, updated_at FROM goals WHERE id IN ({placeholders})",
            params,
        )
        activity_map: dict[str, datetime | None] = {
            goal_id: None for goal_id in unique_ids
        }
        for row in goal_rows:
            activity_map[row["id"]] = self._parse_timestamp(row.get("updated_at"))

        objective_rows = await self.db.fetch_all(
            f"SELECT id, goal_id FROM objectives WHERE goal_id IN ({placeholders})",
            params,
        )
        objective_activity = await self.get_objective_last_activity_map(
            [row["id"] for row in objective_rows]
        )
        objective_activity_by_goal: dict[str, datetime | None] = {
            goal_id: None for goal_id in unique_ids
        }
        for row in objective_rows:
            goal_id = row["goal_id"]
            objective_activity_by_goal[goal_id] = max_datetime(
                [
                    objective_activity_by_goal.get(goal_id),
                    objective_activity.get(row["id"]),
                ]
            )

        goal_field_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as goal_id, MAX(updated_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'goal' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="goal_id",
        )
        goal_comment_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as goal_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'goal' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="goal_id",
        )
        goal_label_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as goal_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'goal' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="goal_id",
        )
        goal_watcher_activity = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT entity_id as goal_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'goal' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
            key_name="goal_id",
        )

        for goal_id in unique_ids:
            activity_map[goal_id] = max_datetime(
                [
                    activity_map.get(goal_id),
                    objective_activity_by_goal.get(goal_id),
                    goal_field_activity.get(goal_id),
                    goal_comment_activity.get(goal_id),
                    goal_label_activity.get(goal_id),
                    goal_watcher_activity.get(goal_id),
                ]
            )

        return activity_map

    async def get_objective_last_transition_map(
        self,
        objective_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep transition timestamps keyed by objective id."""
        unique_ids = list(
            dict.fromkeys(
                objective_id for objective_id in objective_ids if objective_id
            )
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        state_repo = StateTransitionRepository(self.db)
        objective_status = await state_repo.get_last_transition_map(
            "objective_status",
            unique_ids,
        )
        key_result_status = await self._fetch_grouped_max_timestamps(
            f"""
            SELECT kr.objective_id as objective_id, MAX(st.timestamp) as ts
            FROM state_transition_log st
            JOIN key_results kr ON st.entity_id = kr.id
            WHERE st.entity_type = 'key_result_status'
              AND kr.objective_id IN ({placeholders})
            GROUP BY kr.objective_id
            """,
            params,
            key_name="objective_id",
        )

        transition_map: dict[str, datetime | None] = {
            objective_id: None for objective_id in unique_ids
        }
        for objective_id in unique_ids:
            transition_map[objective_id] = max_datetime(
                [
                    objective_status.get(objective_id),
                    key_result_status.get(objective_id),
                ]
            )
        return transition_map

    async def get_last_transition_map(
        self,
        goal_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep transition timestamps keyed by goal id."""
        unique_ids = list(dict.fromkeys(goal_id for goal_id in goal_ids if goal_id))
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        state_repo = StateTransitionRepository(self.db)
        goal_status = await state_repo.get_last_transition_map(
            "goal_status",
            unique_ids,
        )

        objective_rows = await self.db.fetch_all(
            f"SELECT id, goal_id FROM objectives WHERE goal_id IN ({placeholders})",
            params,
        )
        objective_transitions = await self.get_objective_last_transition_map(
            [row["id"] for row in objective_rows]
        )
        objective_by_goal: dict[str, datetime | None] = {
            goal_id: None for goal_id in unique_ids
        }
        for row in objective_rows:
            goal_id = row["goal_id"]
            objective_by_goal[goal_id] = max_datetime(
                [
                    objective_by_goal.get(goal_id),
                    objective_transitions.get(row["id"]),
                ]
            )

        transition_map: dict[str, datetime | None] = {
            goal_id: None for goal_id in unique_ids
        }
        for goal_id in unique_ids:
            transition_map[goal_id] = max_datetime(
                [
                    goal_status.get(goal_id),
                    objective_by_goal.get(goal_id),
                ]
            )
        return transition_map

    async def create_goal(
        self,
        name: str,
        description: str | None = None,
        horizon: GoalHorizon = GoalHorizon.SHORT_TERM,
        target_date: datetime | None = None,
        owner: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
    ) -> Goal:
        """Create a new goal."""
        validated_product_id = await validate_optional_reference_id(
            self._product_repo,
            product_id,
            field_name="product_id",
            entity_label="Product",
        )
        validated_project_id = await validate_optional_reference_id(
            self._project_repo,
            project_id,
            field_name="project_id",
            entity_label="Project",
        )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._goal_repo.db.transaction():
            goal = await self._goal_repo.create(
                name=name,
                description=description,
                horizon=horizon,
                target_date=target_date,
                owner=canonical_owner,
                owner_id=owner_id,
                product_id=validated_product_id,
                project_id=validated_project_id,
                tags=tags,
                progress_percent=progress_percent,
            )

            if goal.project_id:
                await self._reconcile_project_lifecycle(goal.project_id)
            await self.metrics.record_counter("goal.created")
            await self.metrics.flush()

        return goal

    async def get_goal(self, goal_id: str) -> Goal | None:
        """Get a goal by ID."""
        return await self._goal_repo.get_by_id(goal_id)

    async def get_goal_by_name(self, name: str) -> Goal | None:
        """Get a goal by name."""
        return await self._goal_repo.get_by_name(name)

    async def list_goals(
        self,
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """List goals with optional filters."""
        return await self._goal_repo.list_filtered(
            status=status,
            horizon=horizon,
            product_id=product_id,
            project_id=project_id,
            limit=limit,
            offset=offset,
        )

    async def update_goal(
        self,
        goal_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> Goal | None:
        """Update goal details."""
        existing = await self._goal_repo.get_by_id(goal_id)
        if existing is None:
            return None

        validated_product_id = await validate_optional_reference_id(
            self._product_repo,
            product_id,
            field_name="product_id",
            entity_label="Product",
        )
        validated_project_id = await validate_optional_reference_id(
            self._project_repo,
            project_id,
            field_name="project_id",
            entity_label="Project",
        )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self._goal_repo.db.transaction():
            goal = await self._goal_repo.update(
                goal_id=goal_id,
                name=name,
                description=description,
                status=status,
                horizon=horizon,
                target_date=target_date,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                product_id=validated_product_id,
                project_id=validated_project_id,
                tags=tags,
                progress_percent=progress_percent,
            )

            if goal:
                project_ids = sorted(
                    {
                        project_id
                        for project_id in (
                            existing.project_id,
                            goal.project_id,
                        )
                        if project_id
                    }
                )
                for project_id in project_ids:
                    await self._reconcile_project_lifecycle(project_id)
                await self.metrics.record_counter("goal.updated")
                await self.metrics.flush()

        return goal

    async def archive_goal(self, goal_id: str) -> Goal | None:
        """Archive a goal."""
        async with self._goal_repo.db.transaction():
            goal = await self._goal_repo.archive(goal_id)

            if goal:
                if goal.project_id:
                    await self._reconcile_project_lifecycle(goal.project_id)
                await self.metrics.record_counter("goal.archived")
                await self.metrics.flush()

        return goal

    async def complete_goal(self, goal_id: str) -> Goal | None:
        """Complete a goal."""
        async with self._goal_repo.db.transaction():
            goal = await self._goal_repo.complete(goal_id)

            if goal:
                if goal.project_id:
                    await self._reconcile_project_lifecycle(goal.project_id)
                await self.metrics.record_counter("goal.completed")
                await self.metrics.flush()

        return goal

    async def create_objective(
        self,
        goal_id: str,
        name: str,
        description: str | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
    ) -> Objective:
        """Create a new objective for a goal."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self.db.transaction():
            objective = await self._objective_repo.create(
                goal_id=goal_id,
                name=name,
                description=description,
                target_date=target_date,
                owner=canonical_owner,
                owner_id=owner_id,
                tags=tags,
                progress_percent=progress_percent,
            )

            await self.metrics.record_counter("objective.created")
            await self.metrics.flush()

            await self._update_goal_rollup(goal_id)
        return objective

    async def get_objective(self, objective_id: str) -> Objective | None:
        """Get an objective by ID."""
        return await self._objective_repo.get_by_id(objective_id)

    async def list_objectives(
        self,
        goal_id: str | None = None,
        status: GoalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Objective]:
        """List objectives with optional filters."""
        return await self._objective_repo.list_filtered(
            goal_id=goal_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def update_objective(
        self,
        objective_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
        message: str | None = None,
    ) -> Objective | None:
        """Update objective details."""
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)
        async with self.db.transaction():
            objective = await self._objective_repo.update(
                objective_id=objective_id,
                name=name,
                description=description,
                status=status,
                target_date=target_date,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                tags=tags,
                progress_percent=progress_percent,
                message=message,
            )

            if objective:
                await self.metrics.record_counter("objective.updated")
                await self.metrics.flush()
                await self._update_goal_rollup(objective.goal_id)
        return objective

    async def complete_objective(self, objective_id: str) -> Objective | None:
        """Complete an objective."""
        async with self.db.transaction():
            objective = await self._objective_repo.complete(objective_id)

            if objective:
                await self.metrics.record_counter("objective.completed")
                await self.metrics.flush()
                await self._update_goal_rollup(objective.goal_id)

        return objective

    async def archive_objective(self, objective_id: str) -> Objective | None:
        """Archive an objective."""
        async with self.db.transaction():
            objective = await self._objective_repo.archive(objective_id)

            if objective:
                await self.metrics.record_counter("objective.archived")
                await self.metrics.flush()
                await self._update_goal_rollup(objective.goal_id)

        return objective

    async def create_key_result(
        self,
        objective_id: str,
        name: str,
        description: str | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
    ) -> KeyResult:
        """Create a new key result for an objective."""
        progress = self._calculate_progress_percent(
            current_value=current_value,
            target_value=target_value,
            fallback=progress_percent,
        )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)

        async with self.db.transaction():
            key_result = await self._key_result_repo.create(
                objective_id=objective_id,
                name=name,
                description=description,
                current_value=current_value,
                target_value=target_value,
                unit=unit,
                owner=canonical_owner,
                owner_id=owner_id,
                tags=tags,
                progress_percent=progress,
            )

            await self.metrics.record_counter("key_result.created")
            await self.metrics.flush()

            await self._update_objective_rollup_in_transaction(objective_id)
        return key_result

    async def get_key_result(self, key_result_id: str) -> KeyResult | None:
        """Get a key result by ID."""
        return await self._key_result_repo.get_by_id(key_result_id)

    async def list_key_results(
        self,
        objective_id: str | None = None,
        status: GoalStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[KeyResult]:
        """List key results with optional filters."""
        return await self._key_result_repo.list_filtered(
            objective_id=objective_id,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_key_result_last_activity_map(
        self,
        key_result_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep activity timestamps keyed by key result id."""
        return await self._key_result_repo.get_last_activity_map(key_result_ids)

    async def get_key_result_last_transition_map(
        self,
        key_result_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return deep transition timestamps keyed by key result id."""
        return await self._key_result_repo.get_last_transition_map(key_result_ids)

    async def update_key_result(
        self,
        key_result_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        clear_owner: bool = False,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
        message: str | None = None,
    ) -> KeyResult | None:
        """Update key result details."""
        progress = None
        if (
            current_value is not None
            or target_value is not None
            or progress_percent is not None
        ):
            progress = self._calculate_progress_percent(
                current_value=current_value,
                target_value=target_value,
                fallback=progress_percent,
            )
        canonical_owner, owner_id = await self._resolve_owner_identity(owner)

        async with self.db.transaction():
            key_result = await self._key_result_repo.update(
                key_result_id=key_result_id,
                name=name,
                description=description,
                status=status,
                current_value=current_value,
                target_value=target_value,
                unit=unit,
                owner=canonical_owner,
                owner_id=owner_id,
                clear_owner=clear_owner,
                tags=tags,
                progress_percent=progress,
                message=message,
            )

            if key_result:
                await self.metrics.record_counter("key_result.updated")
                await self.metrics.flush()
                await self._update_objective_rollup_in_transaction(
                    key_result.objective_id
                )
        return key_result

    async def _resolve_owner_identity(
        self,
        owner: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve owner input to canonical actor-facing value plus actor id."""
        if owner is None:
            return None, None
        from pms.services.actor_service import ActorService

        actor_service = ActorService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        return await actor_service.canonicalize_actor_reference(owner)

    async def _reconcile_project_lifecycle(self, project_id: str | None) -> None:
        """Reconcile project lifecycle after goal-scoped execution changes."""
        if not project_id:
            return

        from pms.services.project_service import ProjectService

        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        await project_service.reconcile_project_lifecycle(project_id)

    async def complete_key_result(self, key_result_id: str) -> KeyResult | None:
        """Complete a key result."""
        async with self.db.transaction():
            key_result = await self._key_result_repo.complete(key_result_id)

            if key_result:
                await self.metrics.record_counter("key_result.completed")
                await self.metrics.flush()
                await self._update_objective_rollup_in_transaction(
                    key_result.objective_id
                )

        return key_result

    async def archive_key_result(self, key_result_id: str) -> KeyResult | None:
        """Archive a key result."""
        async with self.db.transaction():
            key_result = await self._key_result_repo.archive(key_result_id)

            if key_result:
                await self.metrics.record_counter("key_result.archived")
                await self.metrics.flush()
                await self._update_objective_rollup_in_transaction(
                    key_result.objective_id
                )

        return key_result

    async def get_goal_summary(self, goal_id: str) -> GoalSummary | None:
        """Get goal summary with rollup metrics."""
        goal = await self._goal_repo.get_by_id(goal_id)
        if goal is None:
            return None

        objectives = await self._objective_repo.get_by_goal(goal_id)
        objective_items = objectives.items
        objective_ids = [obj.id for obj in objective_items]
        objective_count = objectives.total_count
        completed_objectives = sum(
            1 for obj in objective_items if obj.status == GoalStatus.COMPLETED
        )

        key_result_count = 0
        completed_key_results = 0
        for obj in objective_items:
            key_results = await self._key_result_repo.get_by_objective(obj.id)
            key_result_count += key_results.total_count
            completed_key_results += sum(
                1 for kr in key_results.items if kr.status == GoalStatus.COMPLETED
            )

        average_progress = self._average_progress(
            [obj.progress_percent for obj in objective_items]
        )
        project_goal_count = 1
        if goal.project_id:
            project_goals = await self._goal_repo.get_by_project(
                goal.project_id,
                limit=1000,
                offset=0,
            )
            project_goal_count = max(project_goals.total_count, 1)
        execution_summary = await self._get_goal_execution_summary(
            goal,
            objective_ids=objective_ids,
            scoped_goal_count=project_goal_count,
        )
        effective_rollup = self._effective_rollup(goal, execution_summary)
        effective_hierarchy = self._effective_hierarchy(
            objective_count=objective_count,
            completed_objectives=completed_objectives,
            key_result_count=key_result_count,
            completed_key_results=completed_key_results,
            average_progress=average_progress,
            effective_rollup=effective_rollup,
        )

        return GoalSummary(
            goal=goal,
            objective_count=objective_count,
            completed_objectives=completed_objectives,
            key_result_count=key_result_count,
            completed_key_results=completed_key_results,
            average_progress=average_progress,
            execution=execution_summary,
            effective_rollup=effective_rollup,
            effective_hierarchy=effective_hierarchy,
        )

    async def get_objective_summary(self, objective_id: str) -> ObjectiveSummary | None:
        """Get objective summary with key-result-aware rollup metrics."""
        objective = await self._objective_repo.get_by_id(objective_id)
        if objective is None:
            return None

        summaries = await self.get_objective_summaries_for_objectives([objective])
        return summaries.get(objective_id)

    async def get_effective_rollups_for_goals(
        self, goals: list[Goal]
    ) -> dict[str, GoalEffectiveRollup]:
        """Return execution-aware effective rollups keyed by goal id."""
        execution_by_goal = await self.get_execution_summaries_for_goals(goals)
        return {
            goal.id: self._effective_rollup(
                goal,
                execution_by_goal.get(goal.id),
            )
            for goal in goals
        }

    async def get_execution_summaries_for_goals(
        self, goals: list[Goal]
    ) -> dict[str, GoalExecutionSummary | None]:
        """Return execution summaries keyed by goal id."""
        return await self._execution_summaries_for_goals(goals)

    async def get_objective_summaries_for_objectives(
        self,
        objectives: list[Objective],
    ) -> dict[str, ObjectiveSummary]:
        """Return objective summaries keyed by objective id."""
        unique_objectives_by_id: dict[str, Objective] = {}
        for objective in objectives:
            if objective.id and objective.id not in unique_objectives_by_id:
                unique_objectives_by_id[objective.id] = objective
        unique_objectives = list(unique_objectives_by_id.values())
        if not unique_objectives:
            return {}

        objective_ids = [objective.id for objective in unique_objectives]
        rollup_stats = await self._key_result_rollup_stats_for_objectives(objective_ids)
        summaries: dict[str, ObjectiveSummary] = {}
        for objective in unique_objectives:
            stats = rollup_stats.get(
                objective.id,
                ObjectiveKeyResultRollupStats(
                    key_result_count=0,
                    completed_key_results=0,
                    active_key_results=0,
                    on_hold_key_results=0,
                    archived_key_results=0,
                    average_progress=0.0,
                ),
            )
            effective_rollup = self._objective_effective_rollup(objective, stats)
            effective_hierarchy = self._objective_effective_hierarchy(
                objective=objective,
                rollup_stats=stats,
                effective_rollup=effective_rollup,
            )
            summaries[objective.id] = ObjectiveSummary(
                objective=objective,
                key_result_count=stats.key_result_count,
                completed_key_results=stats.completed_key_results,
                average_progress=stats.average_progress,
                effective_rollup=effective_rollup,
                effective_hierarchy=effective_hierarchy,
            )
        return summaries

    async def get_project_goal_rollup_stats(
        self, project_ids: list[str]
    ) -> dict[str, ProjectGoalRollupStats]:
        """Return execution-aware goal rollup stats keyed by project id."""
        unique_project_ids = list(dict.fromkeys(pid for pid in project_ids if pid))
        if not unique_project_ids:
            return {}

        goals_by_project: dict[str, list[Goal]] = {}
        for project_id in unique_project_ids:
            result = await self._goal_repo.get_by_project(
                project_id, limit=1000, offset=0
            )
            goals_by_project[project_id] = result.items

        all_goals = [
            goal
            for project_goals in goals_by_project.values()
            for goal in project_goals
        ]
        effective_rollups = await self.get_effective_rollups_for_goals(all_goals)

        stats: dict[str, ProjectGoalRollupStats] = {}
        for project_id, goals in goals_by_project.items():
            rollups = [
                effective_rollups[goal.id]
                for goal in goals
                if goal.id in effective_rollups
            ]
            completed_goals = sum(
                1 for rollup in rollups if rollup.status == GoalStatus.COMPLETED.value
            )
            avg_progress = (
                sum(rollup.progress_percent for rollup in rollups) / len(rollups)
                if rollups
                else 0.0
            )
            stats[project_id] = ProjectGoalRollupStats(
                project_id=project_id,
                total_goals=len(goals),
                completed_goals=completed_goals,
                avg_progress=avg_progress,
            )
        return stats

    async def _get_goal_execution_summary(
        self,
        goal: Goal,
        *,
        objective_ids: list[str],
        scoped_goal_count: int = 1,
    ) -> GoalExecutionSummary | None:
        """Build linked execution stats for a goal, preferring explicit graph links."""
        project_id = goal.project_id
        if project_id is None:
            return None

        (
            task_items,
            population_basis,
            effective_scoped_goal_count,
        ) = await self._resolve_goal_execution_scope(
            goal,
            objective_ids=objective_ids,
            scoped_goal_count=scoped_goal_count,
        )
        if not task_items:
            if population_basis == "goal_scope_requires_explicit_links":
                return GoalExecutionSummary(
                    total_tasks=0,
                    completed_tasks=0,
                    in_progress_tasks=0,
                    blocked_tasks=0,
                    average_task_progress=0.0,
                    completion_percent=0.0,
                    readiness_state="execution_scope_unlinked",
                    consistency_status="unlinked_goal_execution_scope",
                    consistency_reason=(
                        f"project has {scoped_goal_count} retained goals; "
                        "link tasks through goal/objective plans to claim execution"
                    ),
                    focus_task=None,
                    terminal_reason=None,
                    population_basis=population_basis,
                    scoped_goal_count=scoped_goal_count,
                )
            return GoalExecutionSummary(
                total_tasks=0,
                completed_tasks=0,
                in_progress_tasks=0,
                blocked_tasks=0,
                average_task_progress=0.0,
                completion_percent=0.0,
                readiness_state="no_execution_tasks",
                consistency_status=(
                    "ambiguous_project_scoped_execution"
                    if effective_scoped_goal_count > 1
                    else "aligned"
                ),
                consistency_reason=(
                    (
                        f"project-scoped execution is ambiguous because project has {scoped_goal_count} retained goals"
                    )
                    if effective_scoped_goal_count > 1
                    else "goal has no linked execution tasks"
                ),
                focus_task=None,
                terminal_reason=None,
                population_basis=population_basis,
                scoped_goal_count=scoped_goal_count,
            )

        completed_tasks = sum(
            1 for task in task_items if task.status == TaskStatus.DONE
        )
        in_progress_tasks = sum(
            1 for task in task_items if task.status == TaskStatus.IN_PROGRESS
        )
        blocked_tasks = sum(
            1 for task in task_items if task.status == TaskStatus.BLOCKED
        )
        average_task_progress = self._average_progress(
            [task.current_progress_percent for task in task_items]
        )
        completion_percent = (completed_tasks / len(task_items)) * 100
        focus_task = self._select_execution_focus(task_items)
        readiness_state = self._execution_readiness_state(
            task_items,
            focus_task,
            scoped_goal_count=effective_scoped_goal_count,
        )
        consistency_status, consistency_reason = self._execution_consistency_status(
            task_items=task_items,
            completion_percent=completion_percent,
            average_task_progress=average_task_progress,
            focus_task=focus_task,
            scoped_goal_count=effective_scoped_goal_count,
        )
        return GoalExecutionSummary(
            total_tasks=len(task_items),
            completed_tasks=completed_tasks,
            in_progress_tasks=in_progress_tasks,
            blocked_tasks=blocked_tasks,
            average_task_progress=average_task_progress,
            completion_percent=completion_percent,
            readiness_state=readiness_state,
            consistency_status=consistency_status,
            consistency_reason=consistency_reason,
            focus_task=focus_task,
            terminal_reason=(
                "all execution tasks are already complete"
                if focus_task is None
                and all(
                    task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}
                    for task in task_items
                )
                else None
            ),
            population_basis=population_basis,
            scoped_goal_count=scoped_goal_count,
        )

    async def _execution_summaries_for_goals(
        self, goals: list[Goal]
    ) -> dict[str, GoalExecutionSummary]:
        """Build execution summaries keyed by goal id."""
        summaries: dict[str, GoalExecutionSummary] = {}
        goal_counts: dict[str, int] = {}
        unique_project_ids = list(
            dict.fromkeys(goal.project_id for goal in goals if goal.project_id)
        )
        for project_id in unique_project_ids:
            project_goals = await self._goal_repo.get_by_project(
                project_id,
                limit=1000,
                offset=0,
            )
            goal_counts[project_id] = max(project_goals.total_count, 1)
        for goal in goals:
            objective_result = await self._objective_repo.get_by_goal(goal.id)
            summary = await self._get_goal_execution_summary(
                goal,
                objective_ids=[obj.id for obj in objective_result.items],
                scoped_goal_count=goal_counts.get(goal.project_id or "", 1),
            )
            if summary is not None:
                summaries[goal.id] = summary
        return summaries

    async def _resolve_goal_execution_scope(
        self,
        goal: Goal,
        *,
        objective_ids: list[str],
        scoped_goal_count: int,
    ) -> tuple[list[Task], str, int]:
        """Resolve execution tasks for a goal using explicit graph links when available."""
        linked_task_ids = await self._goal_linked_task_ids(goal.id, objective_ids)
        if linked_task_ids:
            return (
                await self._task_repo.get_by_ids(linked_task_ids),
                "goal_plan_task_graph",
                1,
            )

        if goal.project_id is None:
            return [], "goal_plan_task_graph", 1

        if scoped_goal_count > 1:
            return [], "goal_scope_requires_explicit_links", scoped_goal_count

        task_result = await self._task_repo.get_by_project(
            goal.project_id,
            limit=1000,
            offset=0,
        )
        return (
            task_result.items,
            "project_scoped_execution_alias",
            scoped_goal_count,
        )

    async def _goal_linked_task_ids(
        self,
        goal_id: str,
        objective_ids: list[str],
    ) -> list[str]:
        """Return distinct task ids linked to a goal through plans or objective plans."""
        task_ids: list[str] = []

        goal_plans = await self._plan_repo.list_plans(
            goal_id=goal_id, limit=1000, offset=0
        )
        for plan in goal_plans.items:
            task_ids.extend(plan.task_ids)

        for objective_id in objective_ids:
            objective_plans = await self._plan_repo.list_plans(
                objective_id=objective_id,
                limit=1000,
                offset=0,
            )
            for plan in objective_plans.items:
                task_ids.extend(plan.task_ids)

        return list(dict.fromkeys(task_id for task_id in task_ids if task_id))

    def _select_execution_focus(
        self, tasks: list[Task]
    ) -> GoalExecutionFocusTaskSummary | None:
        if not tasks:
            return None
        if all(
            task.status in {TaskStatus.DONE, TaskStatus.CANCELLED} for task in tasks
        ):
            return None

        focus_task = min(
            tasks,
            key=lambda task: (
                self._execution_focus_rank(task.status),
                -self._sort_timestamp(task.updated_at),
            ),
        )
        return GoalExecutionFocusTaskSummary(
            id=focus_task.id,
            title=focus_task.title,
            status=focus_task.status.value,
            current_progress_percent=focus_task.current_progress_percent,
            reason=self._execution_focus_reason(focus_task.status),
            completion_criteria_count=self._completion_criteria_count(focus_task),
            has_completion_criteria=self._completion_criteria_count(focus_task) > 0,
        )

    def _sort_timestamp(self, value: datetime | str | None) -> float:
        if isinstance(value, datetime):
            return value.timestamp()
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"
            try:
                return datetime.fromisoformat(normalized).timestamp()
            except ValueError:
                return 0.0
        return 0.0

    def _execution_focus_rank(self, status: TaskStatus) -> int:
        if status == TaskStatus.IN_PROGRESS:
            return 0
        if status == TaskStatus.IN_REVIEW:
            return 1
        if status == TaskStatus.TODO:
            return 2
        if status == TaskStatus.BLOCKED:
            return 3
        if status == TaskStatus.DONE:
            return 4
        if status == TaskStatus.CANCELLED:
            return 5
        return 6

    def _execution_focus_reason(self, status: TaskStatus) -> str:
        if status == TaskStatus.IN_PROGRESS:
            return "active execution in progress"
        if status == TaskStatus.BLOCKED:
            return "blocked execution needs unblocking"
        if status == TaskStatus.IN_REVIEW:
            return "review-ready work can be closed"
        if status == TaskStatus.TODO:
            return "next ready work to start"
        if status == TaskStatus.DONE:
            return "most actionable task already completed"
        if status == TaskStatus.CANCELLED:
            return "remaining task is cancelled"
        return "best available task focus"

    def _execution_readiness_state(
        self,
        task_items: list[Task],
        focus_task: GoalExecutionFocusTaskSummary | None,
        *,
        scoped_goal_count: int = 1,
    ) -> str:
        if not task_items:
            return "no_execution_tasks"
        if scoped_goal_count > 1:
            return "execution_scope_ambiguous"
        if focus_task is None:
            if all(
                task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}
                for task in task_items
            ):
                return "execution_complete"
            return "no_actionable_execution"
        if focus_task.status == TaskStatus.IN_PROGRESS.value:
            return "execution_in_progress"
        if focus_task.status == TaskStatus.IN_REVIEW.value:
            return "execution_ready_for_review"
        if focus_task.status == TaskStatus.TODO.value:
            return "execution_ready_to_start"
        if focus_task.status == TaskStatus.BLOCKED.value:
            return "execution_blocked"
        return "execution_mixed"

    def _execution_consistency_status(
        self,
        *,
        task_items: list[Task],
        completion_percent: float,
        average_task_progress: float,
        focus_task: GoalExecutionFocusTaskSummary | None,
        scoped_goal_count: int = 1,
    ) -> tuple[str, str | None]:
        if not task_items:
            return ("aligned", "goal has no linked execution tasks")
        if scoped_goal_count > 1:
            return (
                "ambiguous_project_scoped_execution",
                (
                    f"project-scoped execution is ambiguous because project has {scoped_goal_count} retained goals"
                ),
            )
        if focus_task is None and all(
            task.status in {TaskStatus.DONE, TaskStatus.CANCELLED}
            for task in task_items
        ):
            return (
                "execution_terminal",
                "all linked execution tasks are already terminal",
            )
        if average_task_progress == 0 and completion_percent == 0:
            return ("aligned", "linked execution has not started yet")
        if completion_percent > 0:
            return (
                "execution_ahead_of_goal_rollup",
                "linked execution has completed tasks while goal rollups may still lag",
            )
        if average_task_progress > 0:
            return (
                "execution_ahead_of_goal_rollup",
                "linked execution is progressing while goal rollups may still lag",
            )
        return ("aligned", None)

    def _effective_rollup(
        self,
        goal: Goal,
        execution: GoalExecutionSummary | None,
    ) -> GoalEffectiveRollup:
        if execution is None:
            return GoalEffectiveRollup(
                progress_percent=goal.progress_percent,
                status=goal.status.value,
                basis="stored_goal",
                reason=None,
            )

        execution_signal = max(
            int(round(execution.average_task_progress)),
            int(round(execution.completion_percent)),
        )

        if execution.consistency_status == "execution_ahead_of_goal_rollup":
            return GoalEffectiveRollup(
                progress_percent=max(goal.progress_percent, execution_signal),
                status=GoalStatus.ACTIVE.value,
                basis="execution_projection",
                reason=execution.consistency_reason,
            )

        if execution.consistency_status == "execution_terminal":
            return GoalEffectiveRollup(
                progress_percent=(
                    100
                    if execution.terminal_reason is not None
                    else max(goal.progress_percent, execution_signal)
                ),
                status=(
                    GoalStatus.COMPLETED.value
                    if execution.terminal_reason is not None
                    else goal.status.value
                ),
                basis="execution_terminal",
                reason=execution.consistency_reason,
            )

        return GoalEffectiveRollup(
            progress_percent=goal.progress_percent,
            status=goal.status.value,
            basis="stored_goal",
            reason=execution.consistency_reason,
        )

    def _effective_hierarchy(
        self,
        *,
        objective_count: int,
        completed_objectives: int,
        key_result_count: int,
        completed_key_results: int,
        average_progress: float,
        effective_rollup: GoalEffectiveRollup,
    ) -> GoalEffectiveHierarchy:
        """Return hierarchy stats that expose execution-led progress without faking counts."""
        effective_average = max(
            average_progress, float(effective_rollup.progress_percent)
        )
        return GoalEffectiveHierarchy(
            objective_count=objective_count,
            completed_objectives=completed_objectives,
            key_result_count=key_result_count,
            completed_key_results=completed_key_results,
            average_progress=effective_average,
            basis=effective_rollup.basis,
            reason=effective_rollup.reason,
        )

    async def _key_result_rollup_stats_for_objectives(
        self,
        objective_ids: list[str],
    ) -> dict[str, ObjectiveKeyResultRollupStats]:
        """Return grouped key result rollup stats keyed by objective id."""
        unique_ids = list(
            dict.fromkeys(
                objective_id for objective_id in objective_ids if objective_id
            )
        )
        if not unique_ids:
            return {}

        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT
                objective_id,
                COUNT(*) AS key_result_count,
                SUM(CASE WHEN status = '{GoalStatus.COMPLETED.value}' THEN 1 ELSE 0 END)
                    AS completed_key_results,
                SUM(CASE WHEN status = '{GoalStatus.ACTIVE.value}' THEN 1 ELSE 0 END)
                    AS active_key_results,
                SUM(CASE WHEN status = '{GoalStatus.ON_HOLD.value}' THEN 1 ELSE 0 END)
                    AS on_hold_key_results,
                SUM(CASE WHEN status = '{GoalStatus.ARCHIVED.value}' THEN 1 ELSE 0 END)
                    AS archived_key_results,
                AVG(progress_percent) AS average_progress
            FROM key_results
            WHERE objective_id IN ({placeholders})
            GROUP BY objective_id
            """,
            tuple(unique_ids),
        )
        stats: dict[str, ObjectiveKeyResultRollupStats] = {}
        for row in rows:
            objective_id = row.get("objective_id")
            if not objective_id:
                continue
            stats[objective_id] = ObjectiveKeyResultRollupStats(
                key_result_count=int(row.get("key_result_count") or 0),
                completed_key_results=int(row.get("completed_key_results") or 0),
                active_key_results=int(row.get("active_key_results") or 0),
                on_hold_key_results=int(row.get("on_hold_key_results") or 0),
                archived_key_results=int(row.get("archived_key_results") or 0),
                average_progress=float(row.get("average_progress") or 0.0),
            )
        return stats

    def _objective_effective_rollup(
        self,
        objective: Objective,
        rollup_stats: ObjectiveKeyResultRollupStats,
    ) -> ObjectiveEffectiveRollup:
        """Return the operator-facing effective rollup for one objective."""
        if objective.status == GoalStatus.ARCHIVED:
            return ObjectiveEffectiveRollup(
                progress_percent=objective.progress_percent,
                status=objective.status.value,
                basis="stored_objective",
                reason=None,
            )

        if rollup_stats.key_result_count == 0:
            return ObjectiveEffectiveRollup(
                progress_percent=objective.progress_percent,
                status=objective.status.value,
                basis="stored_objective",
                reason=None,
            )

        if rollup_stats.completed_key_results == rollup_stats.key_result_count:
            return ObjectiveEffectiveRollup(
                progress_percent=100,
                status=GoalStatus.COMPLETED.value,
                basis="key_result_rollup",
                reason="all linked key results are already complete",
            )

        if rollup_stats.on_hold_key_results == rollup_stats.key_result_count:
            return ObjectiveEffectiveRollup(
                progress_percent=int(round(rollup_stats.average_progress)),
                status=GoalStatus.ON_HOLD.value,
                basis="key_result_rollup",
                reason="all linked key results are on hold",
            )

        return ObjectiveEffectiveRollup(
            progress_percent=int(round(rollup_stats.average_progress)),
            status=GoalStatus.ACTIVE.value,
            basis="key_result_rollup",
            reason="derived from linked key results",
        )

    def _objective_effective_hierarchy(
        self,
        *,
        objective: Objective,
        rollup_stats: ObjectiveKeyResultRollupStats,
        effective_rollup: ObjectiveEffectiveRollup,
    ) -> ObjectiveEffectiveHierarchy:
        """Return hierarchy stats that expose key-result-led objective state."""
        if rollup_stats.key_result_count == 0:
            average_progress = float(objective.progress_percent)
        else:
            average_progress = max(
                rollup_stats.average_progress,
                float(effective_rollup.progress_percent),
            )

        return ObjectiveEffectiveHierarchy(
            key_result_count=rollup_stats.key_result_count,
            completed_key_results=rollup_stats.completed_key_results,
            average_progress=average_progress,
            basis=effective_rollup.basis,
            reason=effective_rollup.reason,
        )

    def _completion_criteria_count(self, task: Task) -> int:
        raw_value = task.workflow_metadata.get("completion_criteria")
        if not isinstance(raw_value, list):
            return 0
        return sum(1 for item in raw_value if isinstance(item, str) and item.strip())

    async def _update_objective_rollup_in_transaction(self, objective_id: str) -> None:
        """Recalculate objective progress and update goal rollup."""
        objective = await self._objective_repo.get_by_id(objective_id)
        if objective is None:
            return

        key_results = await self._key_result_repo.get_by_objective(objective_id)
        if key_results.total_count == 0:
            await self._update_goal_rollup(objective.goal_id)
            return

        avg_progress = self._average_progress(
            [kr.progress_percent for kr in key_results.items]
        )
        status = (
            GoalStatus.COMPLETED
            if all(kr.status == GoalStatus.COMPLETED for kr in key_results.items)
            else None
        )

        await self._objective_repo.update(
            objective_id=objective_id,
            progress_percent=int(avg_progress),
            status=status,
            message="Auto-rollup objective progress",
        )

        await self._update_goal_rollup(objective.goal_id)

    async def _update_goal_rollup(self, goal_id: str) -> None:
        """Recalculate goal progress based on objectives."""
        max_attempts = 3
        for _ in range(max_attempts):
            before_snapshot = await self._compute_goal_rollup_snapshot(goal_id)
            if before_snapshot is None:
                return

            await self._goal_repo.update(
                goal_id=goal_id,
                progress_percent=before_snapshot.average_progress,
                status=before_snapshot.status,
                message="Auto-rollup goal progress",
            )

            after_snapshot = await self._compute_goal_rollup_snapshot(goal_id)
            if after_snapshot == before_snapshot:
                goal = await self._goal_repo.get_by_id(goal_id)
                if goal is not None:
                    await self._reconcile_project_lifecycle(goal.project_id)
                return

        final_snapshot = await self._compute_goal_rollup_snapshot(goal_id)
        if final_snapshot is None:
            return
        await self._goal_repo.update(
            goal_id=goal_id,
            progress_percent=final_snapshot.average_progress,
            status=final_snapshot.status,
            message="Auto-rollup goal progress",
        )
        goal = await self._goal_repo.get_by_id(goal_id)
        if goal is not None:
            await self._reconcile_project_lifecycle(goal.project_id)

    async def _compute_goal_rollup_snapshot(
        self, goal_id: str
    ) -> GoalRollupSnapshot | None:
        """Compute the current rollup snapshot for a goal."""
        objectives = await self._objective_repo.get_by_goal(goal_id)
        if objectives.total_count == 0:
            return None

        average_progress = int(
            self._average_progress([obj.progress_percent for obj in objectives.items])
        )
        status = (
            GoalStatus.COMPLETED
            if all(obj.status == GoalStatus.COMPLETED for obj in objectives.items)
            else None
        )
        return GoalRollupSnapshot(
            objective_count=objectives.total_count,
            average_progress=average_progress,
            status=status,
        )

    def _average_progress(self, values: list[int]) -> float:
        """Compute average progress from values."""
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _calculate_progress_percent(
        self,
        current_value: float | None,
        target_value: float | None,
        fallback: int | None,
    ) -> int:
        """Calculate progress percent from current/target values."""
        if current_value is None or target_value in (None, 0):
            return fallback or 0
        ratio = max(0.0, min(current_value / target_value, 1.0))
        return int(round(ratio * 100))

    async def search_goals(
        self,
        query: str,
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Goal]:
        """Search goals by name, description, or tags."""
        return await self._goal_repo.search(
            query=query,
            status=status,
            horizon=horizon,
            tags=tags,
            limit=limit,
        )
