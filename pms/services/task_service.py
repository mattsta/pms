"""Task service for high-level task operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

from pms.core.events import EventStore
from pms.core.metrics import MetricsCollector
from pms.core.revisions import Revision, RevisionStore
from pms.models import (
    DuplicateTaskGroup,
    GoalStatus,
    PlanStatus,
    Priority,
    Task,
    TaskDependency,
    TaskStatus,
    TaskWithContext,
)
from pms.models.enums import DependencyType
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.repositories.base import QueryResult, RepositoryContext
from pms.repositories.goal_repository import GoalRepository
from pms.repositories.objective_repository import ObjectiveRepository
from pms.repositories.plan_repository import PlanRepository
from pms.repositories.project_repository import ProjectRepository
from pms.repositories.task_repository import TaskRepository

if TYPE_CHECKING:
    from pms.db.connection import Database
    from pms.models.progress_update import ProgressTimeline

type ConflictComparableValue = JsonValue | datetime | tuple[str, ...]


class TaskCreatePayload(TypedDict, total=False):
    title: str
    description: str | None
    priority: str
    complexity_points: int | None
    tags: list[str]


@dataclass
class TaskTree:
    """Hierarchical task tree structure."""

    task: Task
    children: list[TaskTree] = field(default_factory=list)
    depth: int = 0

    def flatten(self) -> list[tuple[Task, int]]:
        """Flatten tree to list of (task, depth) tuples."""
        result = [(self.task, self.depth)]
        for child in self.children:
            result.extend(child.flatten())
        return result


@dataclass
class DependencyGraph:
    """Graph of task dependencies."""

    task_id: str
    blocking: list[str] = field(default_factory=list)  # Tasks this blocks
    blocked_by: list[str] = field(default_factory=list)  # Tasks blocking this
    is_blocked: bool = False


@dataclass
class TaskBatch:
    """Batch of tasks for bulk operations."""

    tasks: list[Task]
    success_count: int = 0
    failure_count: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class MergeDuplicateResult:
    """Result of merging duplicate tasks."""

    primary_task: Task
    duplicate_tasks: list[Task]
    links_added: int = 0
    duplicates_cancelled: int = 0


@dataclass
class TaskCompletionResult:
    """Completion result with downstream execution effects."""

    task: Task
    newly_unblocked_tasks: list[Task] = field(default_factory=list)


@dataclass
class DuplicateMergeConflict:
    """Field conflict between primary and duplicate tasks."""

    field: str
    primary_value: JsonValue
    duplicate_value: JsonValue
    duplicate_task_id: str

    def to_dict(self) -> ModelObject:
        return {
            "field": self.field,
            "primary_value": self.primary_value,
            "duplicate_value": self.duplicate_value,
            "duplicate_task_id": self.duplicate_task_id,
        }


@dataclass
class DuplicateMergePreviewItem:
    """Preview details for a duplicate task."""

    task: Task
    already_linked: bool
    conflicts: list[DuplicateMergeConflict] = field(default_factory=list)

    def to_dict(self) -> ModelObject:
        return {
            "task": self.task.to_dict(),
            "already_linked": self.already_linked,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }


@dataclass
class DuplicateMergePreview:
    """Preview of a duplicate merge operation."""

    primary_task: Task
    duplicates: list[DuplicateMergePreviewItem] = field(default_factory=list)
    missing_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    can_merge: bool = False
    suggested_primary_id: str | None = None
    suggested_primary_reason: str | None = None

    def to_dict(self) -> ModelObject:
        return {
            "primary_task": self.primary_task.to_dict(),
            "duplicates": [item.to_dict() for item in self.duplicates],
            "missing_ids": list(self.missing_ids),
            "warnings": list(self.warnings),
            "can_merge": self.can_merge,
            "suggested_primary_id": self.suggested_primary_id,
            "suggested_primary_reason": self.suggested_primary_reason,
        }


class TaskService:
    """
    Service for task management operations.

    Handles task lifecycle, dependencies, hierarchy,
    and coordination with project context.
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

        self._task_repo = TaskRepository(db, event_store, revision_store, metrics)
        self._project_repo = ProjectRepository(db, event_store, revision_store, metrics)
        self._plan_repo = PlanRepository(db, event_store, revision_store, metrics)
        self._goal_repo = GoalRepository(db, event_store, revision_store, metrics)
        self._objective_repo = ObjectiveRepository(
            db, event_store, revision_store, metrics
        )
        self._context = RepositoryContext()

    def with_context(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        correlation_id: str | None = None,
    ) -> TaskService:
        """Set context for subsequent operations."""
        self._context = RepositoryContext(
            user_id=user_id,
            session_id=session_id,
            correlation_id=correlation_id,
        )
        self._task_repo.with_context(self._context)
        self._project_repo.with_context(self._context)
        self._plan_repo.with_context(self._context)
        self._goal_repo.with_context(self._context)
        self._objective_repo.with_context(self._context)
        return self

    async def _draft_plan_execution_lock_names(self, task_id: str) -> list[str]:
        """Return linked draft plan names that currently lock task execution."""
        linked_plans = await self._plan_repo.list_by_task_id(task_id)
        return sorted(
            plan.name for plan in linked_plans if plan.status == PlanStatus.DRAFT
        )

    async def _ensure_execution_allowed(self, task_id: str) -> None:
        """Disallow execution changes for tasks attached to draft plans."""
        draft_plan_names = await self._draft_plan_execution_lock_names(task_id)
        if draft_plan_names:
            names = ", ".join(sorted(draft_plan_names))
            raise ValueError(
                "Task execution is locked while linked plan is still draft: "
                f"{names}. Activate the plan before recording progress or "
                "changing task execution state."
            )

    async def _reconcile_linked_execution_state(self, task: Task) -> None:
        """Reconcile plan and project statuses after task execution changes."""
        linked_plans = await self._plan_repo.list_by_task_id(task.id)
        for plan in linked_plans:
            await self._reconcile_plan_status(plan.id)

        project_ids = {task.project_id}
        for plan in linked_plans:
            if plan.project_id is not None:
                project_ids.add(plan.project_id)

        for project_id in sorted(project_ids):
            await self._reconcile_project_execution_state(project_id)

    async def _reconcile_project_execution_state(self, project_id: str) -> None:
        """Reconcile project and goal lifecycle from linked execution state."""
        await self._reconcile_project_goals(project_id)
        await self._reconcile_project_status(project_id)

    async def _link_task_to_active_plans(self, project_id: str, task_id: str) -> None:
        """Append a new task only when the project has one unambiguous active plan."""
        active_plans = await self._plan_repo.list_plans(
            status=PlanStatus.ACTIVE,
            project_id=project_id,
            limit=1000,
            offset=0,
        )
        if len(active_plans.items) != 1:
            return
        plan = active_plans.items[0]
        existing_task_ids = list(plan.task_ids)
        if task_id in existing_task_ids:
            return
        await self._plan_repo.update(
            plan_id=plan.id,
            task_ids=[*existing_task_ids, task_id],
            message="Auto-linked new project task into active plan lineage",
        )

    async def _reconcile_plan_status(self, plan_id: str) -> None:
        """Keep plan status aligned with linked task and goal execution."""
        plan = await self._plan_repo.get_by_id(plan_id)
        if plan is None or plan.status == PlanStatus.ARCHIVED:
            return

        linked_tasks = await self._task_repo.get_by_ids(list(plan.task_ids))
        has_linked_tasks = bool(plan.task_ids)
        any_started = any(
            task.status != TaskStatus.TODO or task.current_progress_percent > 0
            for task in linked_tasks
        )
        all_terminal = has_linked_tasks and all(
            task.status.is_terminal for task in linked_tasks
        )

        target_status = plan.status
        if all_terminal:
            target_status = PlanStatus.COMPLETED
        elif has_linked_tasks and (any_started or plan.status == PlanStatus.COMPLETED):
            target_status = PlanStatus.ACTIVE

        if target_status != plan.status:
            await self._plan_repo.update(
                plan_id=plan.id,
                status=target_status,
                message=("Reconciled plan lifecycle from linked execution state"),
            )

    async def _reconcile_project_status(self, project_id: str) -> None:
        """Keep project status aligned with linked task and goal execution."""
        from pms.services.project_service import ProjectService

        project_service = ProjectService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        await project_service.reconcile_project_lifecycle(project_id)

    async def _reconcile_project_goals(self, project_id: str) -> None:
        """Keep execution-only project goals aligned with linked task execution."""
        goals = await self._goal_repo.get_by_project(project_id, limit=1000, offset=0)
        if goals.total_count == 0:
            return

        task_rollup = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) AS total_tasks,
                SUM(
                    CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END
                ) AS terminal_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        )
        total_tasks = int(task_rollup["total_tasks"] or 0) if task_rollup else 0
        terminal_tasks = int(task_rollup["terminal_tasks"] or 0) if task_rollup else 0
        execution_terminal = total_tasks > 0 and terminal_tasks == total_tasks
        task_progress_rows = await self.db.fetch_all(
            """
            SELECT current_progress_percent
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        )
        execution_average_progress = (
            int(
                round(
                    sum(
                        int(row["current_progress_percent"] or 0)
                        for row in task_progress_rows
                    )
                    / total_tasks
                )
            )
            if total_tasks > 0
            else 0
        )
        execution_completion_percent = (
            int(round((terminal_tasks / total_tasks) * 100)) if total_tasks > 0 else 0
        )
        execution_signal = max(
            execution_average_progress,
            execution_completion_percent,
        )

        for goal in goals.items:
            if goal.status == GoalStatus.ARCHIVED:
                continue

            objective_rollup = await self.db.fetch_one(
                """
                SELECT
                    COUNT(*) AS total_objectives
                FROM objectives
                WHERE goal_id = ?
                  AND status != 'archived'
                """,
                (goal.id,),
            )
            total_objectives = (
                int(objective_rollup["total_objectives"] or 0)
                if objective_rollup
                else 0
            )
            if total_objectives > 0:
                objectives = await self._objective_repo.get_by_goal(
                    goal.id,
                    limit=1000,
                    offset=0,
                )
                objective_ids = [objective.id for objective in objectives.items]
                key_result_counts: dict[str, int] = {}
                if objective_ids:
                    placeholders = ", ".join("?" for _ in objective_ids)
                    key_result_rows = await self.db.fetch_all(
                        f"""
                        SELECT objective_id, COUNT(*) AS count
                        FROM key_results
                        WHERE objective_id IN ({placeholders})
                          AND status != ?
                        GROUP BY objective_id
                        """,
                        (*objective_ids, GoalStatus.ARCHIVED.value),
                    )
                    key_result_counts = {
                        str(row["objective_id"]): int(row["count"] or 0)
                        for row in key_result_rows
                    }

                objective_changed = False
                for objective in objectives.items:
                    if key_result_counts.get(objective.id, 0) > 0:
                        continue

                    target_status = (
                        GoalStatus.COMPLETED
                        if execution_terminal
                        else GoalStatus.ACTIVE
                    )
                    target_progress = 100 if execution_terminal else execution_signal
                    if (
                        objective.status != target_status
                        or objective.progress_percent != target_progress
                    ):
                        await self._objective_repo.update(
                            objective_id=objective.id,
                            status=target_status,
                            progress_percent=target_progress,
                            message=(
                                "Reconciled objective lifecycle from linked execution state"
                            ),
                        )
                        objective_changed = True

                if objective_changed:
                    await self._reconcile_goal_rollup(goal.id)
                continue

            if execution_terminal and goal.status != GoalStatus.COMPLETED:
                await self._goal_repo.complete(
                    goal.id,
                    message="Reconciled goal lifecycle from linked execution state",
                )
                continue

            if not execution_terminal and goal.status == GoalStatus.COMPLETED:
                await self._goal_repo.update(
                    goal_id=goal.id,
                    status=GoalStatus.ACTIVE,
                    progress_percent=0,
                    message=(
                        "Reopened goal because linked execution is no longer terminal"
                    ),
                )

    async def _reconcile_goal_rollup(self, goal_id: str) -> None:
        """Recalculate goal progress/status from current objective state."""
        goal = await self._goal_repo.get_by_id(goal_id)
        if goal is None or goal.status == GoalStatus.ARCHIVED:
            return

        objectives = await self._objective_repo.get_by_goal(
            goal_id,
            limit=1000,
            offset=0,
        )
        if objectives.total_count == 0:
            return

        average_progress = int(
            round(
                sum(objective.progress_percent for objective in objectives.items)
                / objectives.total_count
            )
        )
        target_status = (
            GoalStatus.COMPLETED
            if all(
                objective.status == GoalStatus.COMPLETED
                for objective in objectives.items
            )
            else GoalStatus.ACTIVE
        )

        if goal.status != target_status or goal.progress_percent != average_progress:
            await self._goal_repo.update(
                goal_id=goal_id,
                status=target_status,
                progress_percent=average_progress,
                message="Reconciled goal lifecycle from objective execution state",
            )

    async def create_task(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        milestone_id: str | None = None,
        parent_id: str | None = None,
        priority: Priority = Priority.MEDIUM,
        complexity_points: int | None = None,
        due_date: datetime | None = None,
        assignee: str | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        """Create a new task."""
        if parent_id:
            parent = await self._task_repo.get_by_id(parent_id)
            if parent is None:
                raise ValueError("Parent task not found")
            if parent.project_id != project_id:
                raise ValueError("Parent task must belong to the same project")

        (
            canonical_assigned_to,
            assignee_id,
        ) = await self._resolve_assignee_identity(assignee)

        async with self.db.transaction():
            task = await self._task_repo.create(
                project_id=project_id,
                title=title,
                description=description,
                milestone_id=milestone_id,
                parent_id=parent_id,
                priority=priority,
                complexity_points=complexity_points,
                due_date=due_date,
                assignee=canonical_assigned_to,
                assignee_id=assignee_id,
                tags=tags,
                message=f"Created task '{title}'",
            )

            await self.metrics.record_counter(
                "task.created",
                labels={"project_id": project_id, "priority": priority.value},
            )
            await self.metrics.flush()
            await self._link_task_to_active_plans(project_id, task.id)
            await self._reconcile_project_execution_state(project_id)

        return task

    async def get_task(self, task_id: str) -> Task | None:
        """Get a task by ID."""
        return await self._task_repo.get_by_id(task_id)

    async def get_tasks_by_ids(self, task_ids: list[str]) -> list[Task]:
        """Get tasks by ID."""
        return await self._task_repo.get_by_ids(task_ids)

    async def get_task_with_context(self, task_id: str) -> TaskWithContext | None:
        """Get a task with full context (dependencies, project, etc.)."""
        return await self._task_repo.get_with_context(task_id)

    async def list_tasks(
        self,
        project_id: str | None = None,
        status: TaskStatus | None = None,
        assignee: str | None = None,
        assignee_any: list[str] | None = None,
        include_subtasks: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks with optional filtering."""
        if project_id:
            result = await self._task_repo.get_by_project(
                project_id,
                status=status,
                assignee=assignee,
                assignee_any=assignee_any,
                include_subtasks=include_subtasks,
                limit=limit,
                offset=offset,
            )
        else:
            result = await self._task_repo.get_all(
                limit=limit,
                offset=offset,
                status=status,
                assignee=assignee,
                assignee_any=assignee_any,
                include_subtasks=include_subtasks,
            )
        return await self._overlay_latest_progress(result)

    async def _overlay_latest_progress(
        self,
        result: QueryResult[Task],
    ) -> QueryResult[Task]:
        """Project latest progress-update truth onto task snapshots."""
        if not result.items:
            return result

        task_ids = [task.id for task in result.items]
        placeholders = ", ".join("?" * len(task_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT task_id, percent_complete, timestamp
            FROM task_progress_updates
            WHERE task_id IN ({placeholders})
            ORDER BY timestamp DESC
            """,
            tuple(task_ids),
        )

        latest_progress: dict[str, tuple[int, datetime | None]] = {}
        for row in rows:
            task_id = str(row["task_id"])
            if task_id in latest_progress:
                continue
            timestamp = row["timestamp"]
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            latest_progress[task_id] = (int(row["percent_complete"] or 0), timestamp)

        for task in result.items:
            latest = latest_progress.get(task.id)
            if latest is None:
                continue
            latest_percent, latest_timestamp = latest
            if latest_timestamp is not None and (
                task.last_progress_update_at is None
                or latest_timestamp >= task.last_progress_update_at
            ):
                task.current_progress_percent = latest_percent
                task.last_progress_update_at = latest_timestamp
                continue
            if latest_percent > task.current_progress_percent:
                task.current_progress_percent = latest_percent
        return result

    async def search_tasks(
        self,
        query: str | None = None,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        priorities: list[Priority] | None = None,
        assignee: str | None = None,
        assignee_any: list[str] | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        updated_from: datetime | None = None,
        updated_to: datetime | None = None,
        due_from: datetime | None = None,
        due_to: datetime | None = None,
        tags: list[str] | None = None,
        label_ids: list[str] | None = None,
        label_category_ids: list[str] | None = None,
        include_terminal: bool = False,
        sort_by: str | None = None,
        sort_dir: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """Search tasks with rich filters."""
        result = await self._task_repo.search(
            query=query,
            project_id=project_id,
            statuses=statuses,
            priorities=priorities,
            assignee=assignee,
            assignee_any=assignee_any,
            created_from=created_from,
            created_to=created_to,
            updated_from=updated_from,
            updated_to=updated_to,
            due_from=due_from,
            due_to=due_to,
            tags=tags,
            label_ids=label_ids,
            label_category_ids=label_category_ids,
            include_terminal=include_terminal,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

        await self.metrics.record_counter(
            "task.search",
            labels={"project_id": project_id or "all"},
        )
        await self.metrics.flush_best_effort(context="task.search_tasks")
        return await self._overlay_latest_progress(result)

    async def list_ready_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        exclude_checked_out: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks ready to start (no blocking dependencies)."""
        from pms.models.workflow_state import get_workflow_by_id
        from pms.repositories.base import QueryResult as ResultPage

        result = await self._task_repo.get_ready_tasks(
            project_id=project_id,
            statuses=statuses,
            exclude_checked_out=exclude_checked_out,
            limit=limit,
            offset=offset,
        )

        filtered: list[Task] = []
        for task in result.items:
            if task.workflow_id and task.current_state:
                workflow = get_workflow_by_id(task.workflow_id)
                if workflow and task.current_state in workflow.terminal_states:
                    continue
            filtered.append(task)

        if len(filtered) != len(result.items):
            result = ResultPage(
                items=filtered,
                total_count=len(filtered),
                offset=result.offset,
                limit=result.limit,
            )

        await self.metrics.record_counter(
            "task.ready_listed",
            labels={"project_id": project_id or "all"},
        )
        await self.metrics.flush_best_effort(context="task.list_ready_tasks")
        return result

    async def list_stale_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        stale_after_days: int = 14,
        updated_before: datetime | None = None,
        include_terminal: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks with no recent updates."""
        result = await self._task_repo.get_stale_tasks(
            project_id=project_id,
            statuses=statuses,
            stale_after_days=stale_after_days,
            updated_before=updated_before,
            include_terminal=include_terminal,
            limit=limit,
            offset=offset,
        )

        await self.metrics.record_counter(
            "task.stale_listed",
            labels={"project_id": project_id or "all"},
        )
        await self.metrics.flush_best_effort(context="task.list_stale_tasks")
        return result

    async def find_duplicate_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        include_terminal: bool = False,
        min_count: int = 2,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[DuplicateTaskGroup]:
        """Find duplicate tasks by normalized title."""
        result = await self._task_repo.find_duplicate_tasks(
            project_id=project_id,
            statuses=statuses,
            include_terminal=include_terminal,
            min_count=min_count,
            limit=limit,
            offset=offset,
        )

        for group in result.items:
            suggested_id, suggested_reason = self._suggest_primary_task(group.tasks)
            group.suggested_primary_id = suggested_id
            group.suggested_primary_reason = suggested_reason

        await self.metrics.record_counter(
            "task.duplicates_detected",
            labels={"project_id": project_id or "all"},
        )
        await self.metrics.flush_best_effort(context="task.find_duplicate_tasks")
        return result

    async def preview_merge_duplicate_tasks(
        self,
        primary_task_id: str,
        duplicate_task_ids: list[str],
    ) -> DuplicateMergePreview | None:
        """Preview conflicts and warnings before merging duplicates."""
        primary_task = await self._task_repo.get_by_id(primary_task_id)
        if primary_task is None:
            return None

        duplicates: list[DuplicateMergePreviewItem] = []
        missing_ids: list[str] = []
        warnings: list[str] = []

        for duplicate_id in duplicate_task_ids:
            if duplicate_id == primary_task_id:
                continue
            duplicate_task = await self._task_repo.get_by_id(duplicate_id)
            if duplicate_task is None:
                missing_ids.append(duplicate_id)
                continue

            deps = await self._task_repo.get_dependencies(duplicate_id)
            already_linked = any(
                dep.depends_on_id == primary_task_id
                and dep.dependency_type == DependencyType.DUPLICATES
                for dep in deps
            )

            conflicts = self._build_duplicate_conflicts(primary_task, duplicate_task)
            duplicates.append(
                DuplicateMergePreviewItem(
                    task=duplicate_task,
                    already_linked=already_linked,
                    conflicts=conflicts,
                )
            )

            if duplicate_task.project_id != primary_task.project_id:
                warnings.append(
                    f"Duplicate {duplicate_id} is in a different project ({duplicate_task.project_id})."
                )

            match (primary_task.status, duplicate_task.status):
                case (TaskStatus.DONE, status) if not status.is_terminal:
                    warnings.append(
                        f"Primary task {primary_task_id} is done but duplicate {duplicate_id} is active."
                    )
                case (TaskStatus.CANCELLED, status) if not status.is_terminal:
                    warnings.append(
                        f"Primary task {primary_task_id} is cancelled but duplicate {duplicate_id} is active."
                    )
                case _:
                    pass

            if duplicate_task.updated_at > primary_task.updated_at:
                warnings.append(
                    f"Duplicate {duplicate_id} was updated after the primary task."
                )

        can_merge = bool(duplicates)
        suggested_primary_id, suggested_reason = self._suggest_primary_task(
            [primary_task, *[item.task for item in duplicates]]
        )

        if suggested_primary_id and suggested_primary_id != primary_task_id:
            warnings.append(
                f"Suggested primary task is {suggested_primary_id} ({suggested_reason})."
            )

        preview = DuplicateMergePreview(
            primary_task=primary_task,
            duplicates=duplicates,
            missing_ids=missing_ids,
            warnings=warnings,
            can_merge=can_merge,
            suggested_primary_id=suggested_primary_id,
            suggested_primary_reason=suggested_reason,
        )

        await self.metrics.record_counter(
            "task.duplicates_previewed",
            labels={"primary_task_id": primary_task_id},
        )
        await self.metrics.flush_best_effort(
            context="task.preview_merge_duplicate_tasks"
        )

        return preview

    async def merge_duplicate_tasks(
        self,
        primary_task_id: str,
        duplicate_task_ids: list[str],
        cancel_duplicates: bool = True,
    ) -> MergeDuplicateResult | None:
        """Mark tasks as duplicates of a primary task."""
        primary_task = await self._task_repo.get_by_id(primary_task_id)
        if primary_task is None:
            return None

        async with self.db.transaction():
            links_added = 0
            duplicates_cancelled = 0
            merged_tasks: list[Task] = []

            for duplicate_id in duplicate_task_ids:
                if duplicate_id == primary_task_id:
                    continue
                duplicate_task = await self._task_repo.get_by_id(duplicate_id)
                if duplicate_task is None:
                    continue

                existing = await self._task_repo.get_dependencies(duplicate_id)
                already_linked = any(
                    dep.depends_on_id == primary_task_id
                    and dep.dependency_type == DependencyType.DUPLICATES
                    for dep in existing
                )

                if not already_linked:
                    await self._task_repo.add_dependency(
                        task_id=duplicate_id,
                        depends_on_id=primary_task_id,
                        dependency_type=DependencyType.DUPLICATES,
                    )
                    links_added += 1

                if cancel_duplicates and duplicate_task.status not in (
                    TaskStatus.CANCELLED,
                    TaskStatus.DONE,
                ):
                    await self._task_repo.update_status(
                        duplicate_id,
                        TaskStatus.CANCELLED,
                        reason=f"Duplicate of {primary_task_id}",
                        message="Marked duplicate task",
                    )
                    duplicates_cancelled += 1

                merged_tasks.append(
                    await self._task_repo.get_by_id(duplicate_id) or duplicate_task
                )

            await self.metrics.record_counter(
                "task.duplicates_merged",
                labels={"primary_task_id": primary_task_id},
            )
            await self.metrics.flush()

        return MergeDuplicateResult(
            primary_task=primary_task,
            duplicate_tasks=merged_tasks,
            links_added=links_added,
            duplicates_cancelled=duplicates_cancelled,
        )

    def _build_duplicate_conflicts(
        self,
        primary_task: Task,
        duplicate_task: Task,
    ) -> list[DuplicateMergeConflict]:
        def normalize(value: ConflictComparableValue) -> JsonValue:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, tuple):
                return list(sorted(value))
            return value

        fields: list[tuple[str, ConflictComparableValue, ConflictComparableValue]] = [
            ("project_id", primary_task.project_id, duplicate_task.project_id),
            ("title", primary_task.title, duplicate_task.title),
            ("description", primary_task.description, duplicate_task.description),
            ("status", primary_task.status.value, duplicate_task.status.value),
            ("priority", primary_task.priority.value, duplicate_task.priority.value),
            ("assignee", primary_task.assignee, duplicate_task.assignee),
            ("due_date", primary_task.due_date, duplicate_task.due_date),
            (
                "complexity_points",
                primary_task.complexity_points,
                duplicate_task.complexity_points,
            ),
            ("actual_hours", primary_task.actual_hours, duplicate_task.actual_hours),
            ("workflow_id", primary_task.workflow_id, duplicate_task.workflow_id),
            ("current_state", primary_task.current_state, duplicate_task.current_state),
            ("tags", primary_task.tags, duplicate_task.tags),
        ]

        conflicts: list[DuplicateMergeConflict] = []
        for field_name, primary_value, duplicate_value in fields:
            if normalize(primary_value) != normalize(duplicate_value):
                conflicts.append(
                    DuplicateMergeConflict(
                        field=field_name,
                        primary_value=normalize(primary_value),
                        duplicate_value=normalize(duplicate_value),
                        duplicate_task_id=duplicate_task.id,
                    )
                )
        return conflicts

    def _suggest_primary_task(
        self,
        candidates: list[Task],
    ) -> tuple[str | None, str | None]:
        if not candidates:
            return None, None

        def status_score(status: TaskStatus) -> int:
            match status:
                case TaskStatus.IN_PROGRESS:
                    return 5
                case TaskStatus.IN_REVIEW:
                    return 4
                case TaskStatus.TODO:
                    return 3
                case TaskStatus.BLOCKED:
                    return 2
                case TaskStatus.DONE:
                    return 1
                case TaskStatus.CANCELLED:
                    return 0
                case _:
                    return 0

        def score(task: Task) -> tuple[int, datetime]:
            base = status_score(task.status)
            if task.description:
                base += 1
            if task.assignee:
                base += 1
            if task.due_date:
                base += 1
            if task.current_progress_percent > 0:
                base += 1
            return base, task.updated_at

        ranked = sorted(candidates, key=score, reverse=True)
        best = ranked[0]
        best_score, _ = score(best)

        reason_parts = [f"score {best_score}"]
        reason_parts.append(f"status {best.status.value}")
        return best.id, ", ".join(reason_parts)

    async def start_task(self, task_id: str, reason: str | None = None) -> Task | None:
        """Start working on a task."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.IN_PROGRESS,
                reason=reason,
                message="Started task",
            )

            if task:
                await self.metrics.record_counter(
                    "task.started",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def complete_task(
        self,
        task_id: str,
        actual_hours: float | None = None,
        notes: str | None = None,
    ) -> Task | None:
        """Mark a task as complete."""
        result = await self.complete_task_with_effects(
            task_id,
            actual_hours=actual_hours,
            notes=notes,
        )
        return result.task if result else None

    async def complete_task_with_effects(
        self,
        task_id: str,
        actual_hours: float | None = None,
        notes: str | None = None,
    ) -> TaskCompletionResult | None:
        """Mark a task as complete and return downstream execution effects."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.complete(
                task_id,
                notes=notes,
                actual_hours=actual_hours,
                message="Completed task",
            )

            if task:
                await self.metrics.record_counter(
                    "task.completed",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()

                # Check if any dependent tasks can now be unblocked
                newly_unblocked_tasks = await self._check_unblock_dependents(task_id)
                await self._reconcile_linked_execution_state(task)
                return TaskCompletionResult(
                    task=task,
                    newly_unblocked_tasks=newly_unblocked_tasks,
                )

        return None

    async def block_task(
        self,
        task_id: str,
        reason: str | None = None,
    ) -> Task | None:
        """Mark a task as blocked."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.BLOCKED,
                reason=reason,
                message=f"Blocked: {reason}" if reason else "Task blocked",
            )

            if task:
                await self.metrics.record_counter(
                    "task.blocked",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def unblock_task(self, task_id: str) -> Task | None:
        """Unblock a task (move to TODO)."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.TODO,
                message="Task unblocked",
            )

            if task:
                await self.metrics.record_counter(
                    "task.unblocked",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def cancel_task(self, task_id: str, reason: str | None = None) -> Task | None:
        """Cancel a task."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.CANCELLED,
                reason=reason,
                message=f"Task cancelled: {reason}" if reason else "Task cancelled",
            )

            if task:
                await self.metrics.record_counter(
                    "task.cancelled",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def submit_for_review(self, task_id: str) -> Task | None:
        """Submit a task for review."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.IN_REVIEW,
                message="Submitted for review",
            )

            if task:
                await self.metrics.record_counter(
                    "task.submitted_for_review",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def reopen_task(self, task_id: str) -> Task | None:
        """Reopen a completed or cancelled task."""
        await self._ensure_execution_allowed(task_id)
        async with self.db.transaction():
            task = await self._task_repo.update_status(
                task_id,
                TaskStatus.TODO,
                message="Task reopened",
            )

            if task:
                await self.metrics.record_counter(
                    "task.reopened",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def add_dependency(
        self,
        task_id: str,
        depends_on_id: str,
        dependency_type: DependencyType = DependencyType.BLOCKS,
    ) -> TaskDependency | None:
        """Add a dependency between tasks."""
        async with self.db.transaction():
            dependency = await self._task_repo._add_dependency_in_transaction(
                task_id,
                depends_on_id,
                dependency_type,
            )

            if dependency:
                await self.metrics.record_counter(
                    "task.dependency_added",
                    labels={
                        "task_id": task_id,
                        "depends_on_id": depends_on_id,
                    },
                )

                # Auto-block task if dependency isn't done
                depends_on = await self._task_repo.get_by_id(depends_on_id)
                current_task = await self._task_repo.get_by_id(task_id)
                if depends_on and depends_on.status != TaskStatus.DONE:
                    if current_task and current_task.status == TaskStatus.TODO:
                        await self.block_task(
                            task_id,
                            f"Blocked by: {depends_on.title}",
                        )
                else:
                    await self._check_unblock_task(task_id)

            await self.metrics.flush()

        return dependency

    async def remove_dependency(
        self,
        task_id: str,
        depends_on_id: str,
    ) -> bool:
        """Remove a dependency between tasks."""
        async with self.db.transaction():
            removed = await self._task_repo._remove_dependency_in_transaction(
                task_id, depends_on_id
            )

            if removed:
                await self.metrics.record_counter("task.dependency_removed")
                await self.metrics.flush()

                # Check if task can be unblocked
                await self._check_unblock_task(task_id)

        return removed

    async def get_task_tree(
        self,
        project_id: str,
        root_task_id: str | None = None,
    ) -> list[TaskTree]:
        """Get hierarchical task tree for a project."""
        # Get all tasks for project
        result = await self._task_repo.get_by_project(project_id, include_subtasks=True)

        # Build tree structure
        task_map: dict[str, TaskTree] = {}
        roots: list[TaskTree] = []

        # Create nodes
        for task in result.items:
            task_map[task.id] = TaskTree(task=task)

        # Link parent-child relationships
        for task in result.items:
            node = task_map[task.id]
            if task.parent_id and task.parent_id in task_map:
                parent_node = task_map[task.parent_id]
                parent_node.children.append(node)
                node.depth = parent_node.depth + 1
            elif root_task_id is None or task.parent_id is None:
                roots.append(node)

        # If specific root requested, filter
        if root_task_id and root_task_id in task_map:
            return [task_map[root_task_id]]

        return roots

    async def get_dependency_graph(self, task_id: str) -> DependencyGraph:
        """Get dependency graph for a task."""
        dependencies = await self._task_repo.get_dependencies(task_id)
        dependents = await self._task_repo.get_dependents(task_id)
        task = await self._task_repo.get_by_id(task_id)

        return DependencyGraph(
            task_id=task_id,
            blocked_by=[d.depends_on_id for d in dependencies],
            blocking=[d.task_id for d in dependents],
            is_blocked=task.status == TaskStatus.BLOCKED if task else False,
        )

    async def get_blocked_tasks(
        self,
        project_id: str | None = None,
    ) -> list[Task]:
        """Get all blocked tasks."""
        blocked_tasks = await self._task_repo.get_blocked_tasks(project_id)
        effective_blocked_tasks: list[Task] = []
        for task in blocked_tasks:
            unblocked = await self._check_unblock_task(task.id)
            if unblocked is not None:
                continue
            current = await self._task_repo.get_by_id(task.id)
            if current is not None and current.status == TaskStatus.BLOCKED:
                effective_blocked_tasks.append(current)
        return effective_blocked_tasks

    async def get_execution_lock_plan_names(self, task_id: str) -> list[str]:
        """Return current draft-plan execution locks for a task."""
        return await self._draft_plan_execution_lock_names(task_id)

    async def get_overdue_tasks(
        self,
        project_id: str | None = None,
    ) -> list[Task]:
        """Get all overdue tasks."""
        return await self._task_repo.get_overdue_tasks(project_id)

    async def bulk_create_tasks(
        self,
        project_id: str,
        tasks: list[TaskCreatePayload],
    ) -> TaskBatch:
        """Create multiple tasks in batch."""
        batch = TaskBatch(tasks=[])

        for task_data in tasks:
            try:
                task = await self.create_task(
                    project_id=project_id,
                    title=task_data["title"],
                    description=task_data.get("description"),
                    priority=Priority(task_data.get("priority", "medium")),
                    complexity_points=task_data.get("complexity_points"),
                    tags=task_data.get("tags"),
                )
                batch.tasks.append(task)
                batch.success_count += 1
            except Exception as e:
                batch.failure_count += 1
                batch.errors.append(
                    f"Failed to create '{task_data.get('title', 'unknown')}': {e}"
                )

        return batch

    async def get_task_history(
        self,
        task_id: str,
        limit: int = 50,
    ) -> list[Revision[Task]]:
        """Get task revision history."""
        return await self._task_repo.get_history(task_id, limit)

    async def update_task_progress(
        self,
        task_id: str,
        percent_complete: int,
        status_message: str,
        updated_by: str,
        metadata: JsonObject | None = None,
    ) -> Task | None:
        """Update task progress."""
        from pms.repositories.progress_repository import ProgressRepository

        await self._ensure_execution_allowed(task_id)
        existing_task = await self._task_repo.get_by_id(task_id)
        if existing_task is None:
            return None

        auto_started = (
            existing_task.status == TaskStatus.TODO and 0 < percent_complete < 100
        )
        async with self.db.transaction():
            if auto_started:
                await self._task_repo.update_status(
                    task_id,
                    TaskStatus.IN_PROGRESS,
                    reason="progress_update",
                    message="Auto-started task from progress update",
                )

            progress_repo = ProgressRepository(self.db)

            # Record progress update
            progress_update = await progress_repo.record_progress(
                task_id=task_id,
                percent_complete=percent_complete,
                status_message=status_message,
                updated_by=updated_by,
                metadata=metadata,
            )

            # Update task snapshot and event stream
            task = await self._task_repo.update_progress(
                task_id=task_id,
                percent_complete=percent_complete,
                updated_at=progress_update.timestamp,
                status_message=status_message,
                updated_by=updated_by,
            )
            if (
                task is not None
                and percent_complete >= 100
                and not task.status.is_terminal
            ):
                task = await self._task_repo.update_status(
                    task_id,
                    TaskStatus.DONE,
                    reason="progress_update",
                    message="Auto-completed task from progress update",
                )

            # Record metrics
            if task:
                if auto_started:
                    await self.metrics.record_counter(
                        "task.started",
                        labels={"task_id": task_id, "trigger": "progress_update"},
                    )
                await self.metrics.record_gauge(
                    "task.progress_percent",
                    float(percent_complete),
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()
                await self._reconcile_linked_execution_state(task)

        return task

    async def update_task(
        self,
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        parent_id: str | None = None,
        clear_parent: bool = False,
        priority: Priority | None = None,
        complexity_points: int | None = None,
        assignee: str | None = None,
        clear_assignee: bool = False,
        completion_criteria: list[str] | None = None,
        clear_completion_criteria: bool = False,
    ) -> Task | None:
        """Update mutable task fields."""
        if parent_id is not None or clear_parent:
            task = await self._task_repo.get_by_id(task_id)
            if task is None:
                return None
            if parent_id:
                parent = await self._task_repo.get_by_id(parent_id)
                if parent is None:
                    raise ValueError("Parent task not found")
                if parent.project_id != task.project_id:
                    raise ValueError("Parent task must belong to the same project")

        canonical_assigned_to = None
        assignee_id = None
        if assignee is not None:
            (
                canonical_assigned_to,
                assignee_id,
            ) = await self._resolve_assignee_identity(assignee)

        async with self.db.transaction():
            task = await self._task_repo.update_task(
                task_id=task_id,
                title=title,
                description=description,
                parent_id=parent_id,
                clear_parent=clear_parent,
                priority=priority,
                complexity_points=complexity_points,
                assignee=canonical_assigned_to,
                assignee_id=assignee_id,
                clear_assignee=clear_assignee,
                completion_criteria=completion_criteria,
                clear_completion_criteria=clear_completion_criteria,
            )

            if task:
                await self.metrics.record_counter(
                    "task.updated",
                    labels={"task_id": task_id},
                )
                await self.metrics.flush()

        return task

    async def _resolve_assignee_identity(
        self,
        assignee: str | None,
    ) -> tuple[str | None, str | None]:
        """Resolve assignment input to canonical actor-facing value plus actor id."""
        if assignee is None:
            return None, None
        from pms.services.actor_service import ActorService

        actor_service = ActorService(
            self.db,
            self.events,
            self.revisions,
            self.metrics,
        )
        return await actor_service.canonicalize_actor_reference(assignee)

    async def get_progress_timeline(self, task_id: str) -> ProgressTimeline:
        """Get complete progress timeline for a task."""
        from pms.repositories.progress_repository import ProgressRepository

        progress_repo = ProgressRepository(self.db)
        return await progress_repo.get_timeline(task_id)

    async def get_last_activity(self, task_id: str) -> datetime | None:
        """Get last activity timestamp for a task."""
        activity = await self._task_repo.get_last_activity_map([task_id])
        return activity.get(task_id)

    async def get_last_activity_map(
        self, task_ids: list[str]
    ) -> dict[str, datetime | None]:
        """Get last activity timestamps for a batch of tasks."""
        return await self._task_repo.get_last_activity_map(task_ids)

    async def get_last_transition_map(
        self,
        task_ids: list[str],
        *,
        kind: str = "workflow",
    ) -> dict[str, datetime | None]:
        """Get last transition timestamps for tasks (workflow or status)."""
        from pms.repositories.state_transition_repository import (
            StateTransitionRepository,
        )

        entity_type = "task_workflow" if kind == "workflow" else "task_status"
        state_repo = StateTransitionRepository(self.db)
        return await state_repo.get_last_transition_map(entity_type, task_ids)

    async def get_last_transition(
        self,
        task_id: str,
        *,
        kind: str = "workflow",
    ) -> datetime | None:
        """Get last transition timestamp for a task."""
        transitions = await self.get_last_transition_map([task_id], kind=kind)
        return transitions.get(task_id)

    async def _check_unblock_dependents(self, completed_task_id: str) -> list[Task]:
        """Check if dependent tasks can be unblocked after completion."""
        dependents = await self._task_repo.get_dependents(completed_task_id)
        newly_unblocked_tasks: list[Task] = []

        for dep in dependents:
            unblocked = await self._check_unblock_task(dep.task_id)
            if unblocked is not None:
                newly_unblocked_tasks.append(unblocked)

        return newly_unblocked_tasks

    async def _check_unblock_task(self, task_id: str) -> Task | None:
        """Check if a task can be unblocked based on its dependencies."""
        task = await self._task_repo.get_by_id(task_id)
        if task is None or task.status != TaskStatus.BLOCKED:
            return None

        # Get all dependencies
        dependencies = await self._task_repo.get_dependencies(task_id)
        blocking_dependencies = [
            dep for dep in dependencies if dep.dependency_type == DependencyType.BLOCKS
        ]
        if not blocking_dependencies:
            return None

        # Check if all blocking dependencies are done
        all_done = True
        for dep in blocking_dependencies:
            depends_on = await self._task_repo.get_by_id(dep.depends_on_id)
            if depends_on and depends_on.status != TaskStatus.DONE:
                all_done = False
                break

        if all_done:
            if await self._draft_plan_execution_lock_names(task_id):
                return None
            return await self.unblock_task(task_id)
        return None
