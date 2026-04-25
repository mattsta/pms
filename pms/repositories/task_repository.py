"""Task repository with event sourcing and dependency management."""

from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import (
    DuplicateTaskGroup,
    Priority,
    Task,
    TaskDependency,
    TaskStatus,
    TaskWithContext,
)
from pms.models.base import now_utc
from pms.models.enums import DependencyType
from pms.repositories.base import EventSourcedRepository, QueryResult
from pms.repositories.state_transition_repository import StateTransitionRepository

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database

_TASK_PROJECTION_EVENT_TYPE: ContextVar[EventType | None] = ContextVar(
    "task_projection_event_type",
    default=None,
)
_TASK_PROJECTION_PAYLOAD: ContextVar[dict[str, Any] | None] = ContextVar(
    "task_projection_payload",
    default=None,
)


class TaskRepository(EventSourcedRepository[Task]):
    """Repository for Task entities with hierarchy and dependency support."""

    def __init__(
        self,
        db: Database,
        event_store: EventStore,
        revision_store: RevisionStore,
        metrics: MetricsCollector,
    ) -> None:
        super().__init__(db, event_store, revision_store, metrics)

    @property
    def entity_type(self) -> str:
        return "task"

    @property
    def table_name(self) -> str:
        return "tasks"

    @staticmethod
    def _append_assignment_filter(
        *,
        where_clauses: list[str],
        params: list[Any],
        assignee: str | None = None,
        assignee_any: list[str] | None = None,
    ) -> None:
        """Append assignment filters across actor ids and stored assignee values."""
        if assignee is not None:
            where_clauses.append("(assignee = ? OR assignee_id = ?)")
            params.extend([assignee, assignee])
            return
        if assignee_any:
            placeholders = ", ".join("?" * len(assignee_any))
            where_clauses.append(
                f"(assignee IN ({placeholders}) OR assignee_id IN ({placeholders}))"
            )
            params.extend(assignee_any)
            params.extend(assignee_any)

    def _model_from_row(self, row: dict[str, Any]) -> Task:
        """Convert database row to Task."""
        tags_raw = row.get("tags", "[]")
        # Handle both JSON string (from DB) and already-decoded list (from revision content)
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        # Handle datetime fields
        due_date = None
        if row.get("due_date"):
            due_date = (
                datetime.fromisoformat(row["due_date"])
                if isinstance(row["due_date"], str)
                else row["due_date"]
            )

        completed_at = None
        if row.get("completed_at"):
            completed_at = (
                datetime.fromisoformat(row["completed_at"])
                if isinstance(row["completed_at"], str)
                else row["completed_at"]
            )

        # Handle checkout timestamps
        checked_out_at = None
        if row.get("checked_out_at"):
            checked_out_at = (
                datetime.fromisoformat(row["checked_out_at"])
                if isinstance(row["checked_out_at"], str)
                else row["checked_out_at"]
            )

        checkout_lease_until = None
        if row.get("checkout_lease_until"):
            checkout_lease_until = (
                datetime.fromisoformat(row["checkout_lease_until"])
                if isinstance(row["checkout_lease_until"], str)
                else row["checkout_lease_until"]
            )

        last_progress_update_at = None
        if row.get("last_progress_update_at"):
            last_progress_update_at = (
                datetime.fromisoformat(row["last_progress_update_at"])
                if isinstance(row["last_progress_update_at"], str)
                else row["last_progress_update_at"]
            )

        # Parse workflow metadata
        workflow_metadata_raw = row.get("workflow_metadata", "{}")
        workflow_metadata = (
            json.loads(workflow_metadata_raw)
            if isinstance(workflow_metadata_raw, str)
            else workflow_metadata_raw
        )

        created_at = row["created_at"]
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        updated_at = row["updated_at"]
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)

        return Task(
            id=row["id"],
            project_id=row["project_id"],
            milestone_id=row.get("milestone_id"),
            parent_id=row.get("parent_id"),
            title=row["title"],
            description=row.get("description"),
            status=TaskStatus(row["status"]),
            priority=Priority(row["priority"]),
            complexity_points=row.get("complexity_points"),
            actual_hours=row.get("actual_hours"),
            current_progress_percent=row.get("current_progress_percent", 0),
            last_progress_update_at=last_progress_update_at,
            checkout_agent_session_id=row.get("checkout_agent_session_id"),
            checkout_actor_id=row.get("checkout_actor_id"),
            checked_out_at=checked_out_at,
            checkout_lease_until=checkout_lease_until,
            checkout_attempts=row.get("checkout_attempts", 0),
            checkout_version=row.get("checkout_version", 0),
            workflow_id=row.get("workflow_id"),
            current_state=row.get("current_state"),
            workflow_metadata=workflow_metadata,
            due_date=due_date,
            assignee=row.get("assignee"),
            assignee_id=row.get("assignee_id"),
            tags=tuple(tags),
            sort_order=row.get("sort_order", 0),
            completed_at=completed_at,
            created_at=created_at,
            updated_at=updated_at,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Task) -> dict[str, Any]:
        """Convert Task to database row."""
        return {
            "id": model.id,
            "project_id": model.project_id,
            "milestone_id": model.milestone_id,
            "parent_id": model.parent_id,
            "title": model.title,
            "description": model.description,
            "status": model.status.value,
            "priority": model.priority.value,
            "complexity_points": model.complexity_points,
            "actual_hours": model.actual_hours,
            "current_progress_percent": model.current_progress_percent,
            "last_progress_update_at": model.last_progress_update_at.isoformat()
            if model.last_progress_update_at
            else None,
            "checkout_agent_session_id": model.checkout_agent_session_id,
            "checkout_actor_id": model.checkout_actor_id,
            "checked_out_at": model.checked_out_at.isoformat()
            if model.checked_out_at
            else None,
            "checkout_lease_until": model.checkout_lease_until.isoformat()
            if model.checkout_lease_until
            else None,
            "checkout_attempts": model.checkout_attempts,
            "checkout_version": model.checkout_version,
            "workflow_id": model.workflow_id,
            "current_state": model.current_state,
            "workflow_metadata": json.dumps(model.workflow_metadata),
            "due_date": model.due_date.isoformat() if model.due_date else None,
            "assignee": model.assignee,
            "assignee_id": model.assignee_id,
            "tags": json.dumps(list(model.tags)),
            "sort_order": model.sort_order,
            "completed_at": model.completed_at.isoformat()
            if model.completed_at
            else None,
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
        status: TaskStatus | None = None,
        assignee: str | None = None,
        assignee_any: list[str] | None = None,
        include_subtasks: bool = True,
    ) -> QueryResult[Task]:
        """Get all tasks with optional task-specific filters."""
        with self.metrics.time_operation(f"{self.entity_type}.get_all"):
            where_clauses: list[str] = []
            params: list[Any] = []

            if status is not None:
                where_clauses.append("status = ?")
                params.append(status.value)

            self._append_assignment_filter(
                where_clauses=where_clauses,
                params=params,
                assignee=assignee,
                assignee_any=assignee_any,
            )

            if not include_subtasks:
                where_clauses.append("parent_id IS NULL")

            where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            count_result = await self.db.fetch_one(
                f"SELECT COUNT(*) as count FROM {self.table_name}{where_sql}",
                tuple(params),
            )
            total = count_result["count"] if count_result else 0

            order_dir = "DESC" if order_desc else "ASC"
            rows = await self.db.fetch_all(
                f"""
                SELECT * FROM {self.table_name}
                {where_sql}
                ORDER BY {order_by} {order_dir}
                LIMIT ? OFFSET ?
                """,
                (*params, limit, offset),
            )

            return QueryResult(
                items=[self._model_from_row(row) for row in rows],
                total_count=total,
                offset=offset,
                limit=limit,
            )

    async def get_global_rollup(self) -> dict[str, int]:
        """Return task counts across all non-archived projects."""
        row = await self.db.fetch_one(
            """
            SELECT
                COUNT(t.id) AS total_tasks,
                COALESCE(SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END), 0)
                    AS completed_tasks
            FROM tasks t
            JOIN projects p ON p.id = t.project_id
            WHERE p.status != 'archived'
            """
        )
        return {
            "total_tasks": int(row["total_tasks"] or 0) if row else 0,
            "completed_tasks": int(row["completed_tasks"] or 0) if row else 0,
        }

    async def get_assignment_rollup(
        self,
        *,
        assignee_any: list[str],
        project_id: str | None = None,
    ) -> dict[str, int]:
        """Return workload counts for a set of assignment tokens."""
        empty = {
            "total_tasks": 0,
            "active_tasks": 0,
            "terminal_tasks": 0,
            "todo_tasks": 0,
            "in_progress_tasks": 0,
            "in_review_tasks": 0,
            "blocked_tasks": 0,
            "done_tasks": 0,
            "cancelled_tasks": 0,
        }
        if not assignee_any:
            return empty

        where_clauses: list[str] = []
        params: list[Any] = []
        if project_id is not None:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        self._append_assignment_filter(
            where_clauses=where_clauses,
            params=params,
            assignee_any=assignee_any,
        )

        where_sql = " AND ".join(where_clauses)
        row = await self.db.fetch_one(
            f"""
            SELECT
                COUNT(*) AS total_tasks,
                COALESCE(
                    SUM(CASE WHEN status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END),
                    0
                ) AS active_tasks,
                COALESCE(
                    SUM(CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END),
                    0
                ) AS terminal_tasks,
                COALESCE(SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END), 0)
                    AS todo_tasks,
                COALESCE(SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END), 0)
                    AS in_progress_tasks,
                COALESCE(SUM(CASE WHEN status = 'in_review' THEN 1 ELSE 0 END), 0)
                    AS in_review_tasks,
                COALESCE(SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END), 0)
                    AS blocked_tasks,
                COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0)
                    AS done_tasks,
                COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS cancelled_tasks
            FROM tasks
            WHERE {where_sql}
            """,
            tuple(params),
        )
        if row is None:
            return empty
        return {key: int(row[key] or 0) for key in empty}

    async def get_assignment_rollup_by_project(
        self,
        *,
        assignee_any: list[str],
    ) -> list[dict[str, Any]]:
        """Return assignment rollups grouped by project."""
        if not assignee_any:
            return []

        where_clauses: list[str] = []
        params: list[Any] = []
        self._append_assignment_filter(
            where_clauses=where_clauses,
            params=params,
            assignee_any=assignee_any,
        )

        where_sql = " AND ".join(where_clauses)
        rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) AS total_tasks,
                COALESCE(
                    SUM(CASE WHEN status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END),
                    0
                ) AS active_tasks,
                COALESCE(
                    SUM(CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END),
                    0
                ) AS terminal_tasks,
                COALESCE(SUM(CASE WHEN status = 'todo' THEN 1 ELSE 0 END), 0)
                    AS todo_tasks,
                COALESCE(SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END), 0)
                    AS in_progress_tasks,
                COALESCE(SUM(CASE WHEN status = 'in_review' THEN 1 ELSE 0 END), 0)
                    AS in_review_tasks,
                COALESCE(SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END), 0)
                    AS blocked_tasks,
                COALESCE(SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END), 0)
                    AS done_tasks,
                COALESCE(SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END), 0)
                    AS cancelled_tasks
            FROM tasks
            WHERE {where_sql}
            GROUP BY project_id
            ORDER BY total_tasks DESC, project_id
            """,
            tuple(params),
        )
        return [{key: row[key] for key in row} for row in rows]

    @staticmethod
    def _preserve_status_fields(task: Task, latest: Task) -> None:
        """Keep status-owned fields from another task snapshot."""
        task.status = latest.status
        task.actual_hours = latest.actual_hours
        task.completed_at = latest.completed_at
        task.checkout_agent_session_id = latest.checkout_agent_session_id
        task.checkout_actor_id = latest.checkout_actor_id
        task.checked_out_at = latest.checked_out_at
        task.checkout_lease_until = latest.checkout_lease_until
        task.checkout_attempts = latest.checkout_attempts
        task.checkout_version = latest.checkout_version

    @staticmethod
    def _preserve_progress_fields(task: Task, latest: Task) -> None:
        """Keep progress fields from another task snapshot."""
        task.current_progress_percent = latest.current_progress_percent
        task.last_progress_update_at = latest.last_progress_update_at

    @staticmethod
    def _preserve_workflow_fields(task: Task, latest: Task) -> None:
        """Keep workflow assignment/state fields from another task snapshot."""
        task.workflow_id = latest.workflow_id
        task.current_state = latest.current_state

    @staticmethod
    def _preserve_metadata_fields(task: Task, latest: Task) -> None:
        """Keep mutable descriptive fields from a newer task snapshot."""
        task.milestone_id = latest.milestone_id
        task.parent_id = latest.parent_id
        task.title = latest.title
        task.description = latest.description
        task.priority = latest.priority
        task.complexity_points = latest.complexity_points
        task.due_date = latest.due_date
        task.assignee = latest.assignee
        task.assignee_id = latest.assignee_id
        task.tags = latest.tags
        task.sort_order = latest.sort_order

    @staticmethod
    def _newer_merge_source(current: Task, candidate: Task | None) -> Task:
        """Choose the newer state source for field-preserving projection merges."""
        if candidate is None:
            return current
        if candidate.last_event_sequence > current.last_event_sequence:
            return candidate
        if candidate.last_event_sequence < current.last_event_sequence:
            return current
        if candidate.last_revision_number > current.last_revision_number:
            return candidate
        if candidate.last_revision_number < current.last_revision_number:
            return current
        if candidate.updated_at > current.updated_at:
            return candidate
        return current

    async def save(
        self,
        model: Task,
        event_type: EventType,
        payload: dict[str, Any],
        message: str | None = None,
    ) -> Task:
        """Persist a task while exposing the event type to projection merge logic."""
        event_type_token = _TASK_PROJECTION_EVENT_TYPE.set(event_type)
        payload_token = _TASK_PROJECTION_PAYLOAD.set(payload)
        try:
            return await super().save(model, event_type, payload, message)
        finally:
            _TASK_PROJECTION_PAYLOAD.reset(payload_token)
            _TASK_PROJECTION_EVENT_TYPE.reset(event_type_token)

    async def _update_projection(self, model: Task, is_create: bool) -> None:
        """Update task projection while preserving newer terminal state."""
        if is_create:
            await super()._update_projection(model, is_create)
            return

        current = await self.get_by_id(model.id)
        previous_revision_task: Task | None = None
        if model.last_revision_number > 1:
            previous_revision = await self.revisions.get_revision(
                self.entity_type,
                model.id,
                model.last_revision_number - 1,
            )
            if previous_revision is not None and isinstance(
                previous_revision.content, dict
            ):
                previous_revision_task = self._model_from_row(previous_revision.content)
        if current is not None:
            incoming_is_terminal = model.status.is_terminal
            current_is_terminal = current.status.is_terminal
            event_type = _TASK_PROJECTION_EVENT_TYPE.get()
            payload = _TASK_PROJECTION_PAYLOAD.get() or {}
            merge_source = self._newer_merge_source(current, previous_revision_task)
            workflow_owned_update = event_type == EventType.TASK_UPDATED and (
                "workflow_assigned" in payload or "state_transition" in payload
            )

            if merge_source.workflow_metadata != model.workflow_metadata:
                merged_workflow_metadata = dict(merge_source.workflow_metadata)
                merged_workflow_metadata.update(model.workflow_metadata)
                model.workflow_metadata = merged_workflow_metadata

            if event_type == EventType.TASK_UPDATED:
                self._preserve_status_fields(model, merge_source)
                self._preserve_progress_fields(model, merge_source)
                if not workflow_owned_update:
                    self._preserve_workflow_fields(model, merge_source)
            elif event_type == EventType.TASK_PROGRESS_UPDATED:
                self._preserve_status_fields(model, merge_source)
                self._preserve_metadata_fields(model, merge_source)
                self._preserve_workflow_fields(model, merge_source)
            elif event_type in {
                EventType.TASK_STATUS_CHANGED,
                EventType.TASK_COMPLETED,
            }:
                self._preserve_metadata_fields(model, merge_source)
                self._preserve_workflow_fields(model, merge_source)

            if current.updated_at > model.updated_at:
                self._preserve_status_fields(model, current)
                if current.current_progress_percent > model.current_progress_percent:
                    model.current_progress_percent = current.current_progress_percent
                if current.last_progress_update_at is not None and (
                    model.last_progress_update_at is None
                    or current.last_progress_update_at > model.last_progress_update_at
                ):
                    model.last_progress_update_at = current.last_progress_update_at
                if current.checked_out_at is not None and (
                    model.checked_out_at is None
                    or current.checked_out_at > model.checked_out_at
                ):
                    model.checked_out_at = current.checked_out_at
                    model.checkout_agent_session_id = current.checkout_agent_session_id
                    model.checkout_actor_id = current.checkout_actor_id
                    model.checkout_lease_until = current.checkout_lease_until
                    model.checkout_attempts = current.checkout_attempts
                    model.checkout_version = current.checkout_version
                model.updated_at = current.updated_at
                self._preserve_workflow_fields(model, current)
            explicit_reopen = (
                event_type == EventType.TASK_STATUS_CHANGED
                and payload.get("new_status") == TaskStatus.TODO.value
            )
            if current_is_terminal and not incoming_is_terminal and not explicit_reopen:
                model.status = current.status
                model.completed_at = current.completed_at
                if current.current_progress_percent > model.current_progress_percent:
                    model.current_progress_percent = current.current_progress_percent
                if current.last_progress_update_at is not None and (
                    model.last_progress_update_at is None
                    or current.last_progress_update_at > model.last_progress_update_at
                ):
                    model.last_progress_update_at = current.last_progress_update_at
                if current.updated_at > model.updated_at:
                    model.updated_at = current.updated_at
                if current.last_event_sequence > model.last_event_sequence:
                    model.last_event_sequence = current.last_event_sequence
                if current.last_revision_number > model.last_revision_number:
                    model.last_revision_number = current.last_revision_number

        await super()._update_projection(model, is_create)

    async def create(
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
        assignee_id: str | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Task:
        """Create a new task."""
        task = Task(
            project_id=project_id,
            milestone_id=milestone_id,
            parent_id=parent_id,
            title=title,
            description=description,
            priority=priority,
            complexity_points=complexity_points,
            due_date=due_date,
            assignee=assignee,
            assignee_id=assignee_id,
            tags=tuple(tags) if tags else (),
        )

        payload = {
            "project_id": project_id,
            "title": title,
            "description": description,
            "milestone_id": milestone_id,
            "parent_id": parent_id,
            "priority": priority.value,
            "complexity_points": complexity_points,
            "due_date": due_date.isoformat() if due_date else None,
            "assignee": assignee,
            "assignee_id": assignee_id,
            "tags": tags or [],
        }

        return await self.save(
            task,
            EventType.TASK_CREATED,
            payload,
            message=message or f"Created task '{title}'",
        )

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
        assignee_id: str | None = None,
        clear_assignee: bool = False,
        completion_criteria: list[str] | None = None,
        clear_completion_criteria: bool = False,
        message: str | None = None,
    ) -> Task | None:
        """Update mutable task fields."""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        changes: dict[str, Any] = {}

        if title is not None and title != task.title:
            task.title = title
            changes["title"] = title

        if description is not None and description != task.description:
            task.description = description
            changes["description"] = description

        if clear_parent and task.parent_id is not None:
            task.parent_id = None
            changes["parent_id"] = None
        elif parent_id is not None and parent_id != task.parent_id:
            task.parent_id = parent_id
            changes["parent_id"] = parent_id

        if priority is not None and priority != task.priority:
            task.priority = priority
            changes["priority"] = priority.value

        if (
            complexity_points is not None
            and complexity_points != task.complexity_points
        ):
            task.complexity_points = complexity_points
            changes["complexity_points"] = complexity_points

        if clear_assignee:
            if task.assignee is not None or task.assignee_id is not None:
                task.assignee = None
                task.assignee_id = None
                changes["assignee"] = None
                changes["assignee_id"] = None
        elif assignee is not None and (
            assignee != task.assignee or assignee_id != task.assignee_id
        ):
            task.assignee = assignee
            task.assignee_id = assignee_id
            changes["assignee"] = assignee
            changes["assignee_id"] = assignee_id

        if clear_completion_criteria:
            if "completion_criteria" in task.workflow_metadata:
                task.workflow_metadata = {
                    key: value
                    for key, value in task.workflow_metadata.items()
                    if key != "completion_criteria"
                }
                changes["completion_criteria"] = []
        elif completion_criteria is not None:
            normalized_criteria = [
                item.strip() for item in completion_criteria if item.strip()
            ]
            if task.workflow_metadata.get("completion_criteria") != normalized_criteria:
                task.workflow_metadata = {
                    **task.workflow_metadata,
                    "completion_criteria": normalized_criteria,
                }
                changes["completion_criteria"] = normalized_criteria

        if not changes:
            return task

        task.touch()

        return await self.save(
            task,
            EventType.TASK_UPDATED,
            changes,
            message=message or "Updated task",
        )

    async def update_progress(
        self,
        task_id: str,
        percent_complete: int,
        updated_at: datetime,
        status_message: str | None = None,
        updated_by: str | None = None,
    ) -> Task | None:
        """Update task progress with event tracking."""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        await self._preserve_current_workflow_metadata(task)
        task.current_progress_percent = percent_complete
        task.last_progress_update_at = updated_at
        task.updated_at = updated_at

        return await self.save(
            task,
            EventType.TASK_PROGRESS_UPDATED,
            {
                "percent_complete": percent_complete,
                "status_message": status_message,
                "updated_by": updated_by,
                "last_progress_update_at": updated_at.isoformat(),
            },
            message="Updated task progress",
        )

    async def update_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        reason: str | None = None,
        actual_hours: float | None = None,
        message: str | None = None,
    ) -> Task | None:
        """Update task status with proper state transitions."""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        await self._preserve_current_workflow_metadata(task)
        old_status = task.status

        # Apply status change
        match new_status:
            case TaskStatus.IN_PROGRESS:
                task.start()
            case TaskStatus.BLOCKED:
                task.block(reason)
            case TaskStatus.IN_REVIEW:
                task.submit_for_review()
            case TaskStatus.DONE:
                task.complete()
                if task.current_progress_percent < 100:
                    task.current_progress_percent = 100
                    task.last_progress_update_at = now_utc()
                if actual_hours is not None:
                    task.actual_hours = actual_hours
            case TaskStatus.CANCELLED:
                task.cancel()
            case TaskStatus.TODO:
                if task.status.is_terminal:
                    task.reopen()
                else:
                    task.status = TaskStatus.TODO
                    task.touch()

        return await self.save(
            task,
            EventType.TASK_STATUS_CHANGED,
            {
                "old_status": old_status.value,
                "new_status": new_status.value,
                "reason": reason,
                "actual_hours": actual_hours,
            },
            message=message
            or f"Status changed: {old_status.value} -> {new_status.value}",
        )

    async def complete(
        self,
        task_id: str,
        notes: str | None = None,
        actual_hours: float | None = None,
        message: str | None = None,
    ) -> Task | None:
        """Mark task as completed."""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        await self._preserve_current_workflow_metadata(task)
        already_done = task.status == TaskStatus.DONE
        now = now_utc()
        if not already_done:
            task.complete()
        if task.current_progress_percent < 100:
            task.current_progress_percent = 100
            task.last_progress_update_at = now
        if already_done:
            task.updated_at = now
        if actual_hours is not None:
            task.actual_hours = actual_hours

        return await self.save(
            task,
            EventType.TASK_COMPLETED,
            {"notes": notes, "actual_hours": actual_hours},
            message=message
            or ("Task completion reconciled" if already_done else "Task completed"),
        )

    async def _preserve_current_workflow_metadata(self, task: Task) -> None:
        """Keep newer metadata when this operation does not explicitly own it."""
        current = await self.get_by_id(task.id)
        if current is None:
            return
        task.workflow_metadata = dict(current.workflow_metadata)

    async def add_dependency(
        self,
        task_id: str,
        depends_on_id: str,
        dependency_type: DependencyType = DependencyType.BLOCKS,
    ) -> TaskDependency | None:
        """Add a dependency between tasks (supports cross-project)."""

        async def _add() -> TaskDependency | None:
            return await self._add_dependency_in_transaction(
                task_id,
                depends_on_id,
                dependency_type,
            )

        return await self._run_in_owned_transaction(
            _add,
            operation_name="add_dependency",
        )

    async def _add_dependency_in_transaction(
        self,
        task_id: str,
        depends_on_id: str,
        dependency_type: DependencyType = DependencyType.BLOCKS,
    ) -> TaskDependency | None:
        """Add a dependency assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_add_dependency_in_transaction")
        # Validate both tasks exist
        task = await self.get_by_id(task_id)
        depends_on = await self.get_by_id(depends_on_id)

        if task is None or depends_on is None:
            return None

        # Check for circular dependency
        if await self._would_create_cycle(task_id, depends_on_id):
            raise ValueError("Adding this dependency would create a circular reference")

        # Create dependency
        dep = TaskDependency(
            task_id=task_id,
            depends_on_id=depends_on_id,
            dependency_type=dependency_type,
        )

        await self.db.execute(
            """
            INSERT INTO task_dependencies (id, task_id, depends_on_id, dependency_type, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                dep.id,
                task_id,
                depends_on_id,
                dependency_type.value,
                dep.created_at.isoformat(),
            ),
        )

        # Record event
        event = DomainEvent(
            event_type=EventType.DEPENDENCY_ADDED,
            aggregate_type="task",
            aggregate_id=task_id,
            payload={
                "depends_on_id": depends_on_id,
                "dependency_type": dependency_type.value,
            },
            metadata=self._context.to_metadata(),
        )
        await self.events.append(event)

        return dep

    async def remove_dependency(self, task_id: str, depends_on_id: str) -> bool:
        """Remove a dependency between tasks."""

        async def _remove() -> bool:
            return await self._remove_dependency_in_transaction(task_id, depends_on_id)

        return await self._run_in_owned_transaction(
            _remove,
            operation_name="remove_dependency",
        )

    async def _remove_dependency_in_transaction(
        self, task_id: str, depends_on_id: str
    ) -> bool:
        """Remove a dependency assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_remove_dependency_in_transaction")
        result = await self.db.execute(
            "DELETE FROM task_dependencies WHERE task_id = ? AND depends_on_id = ?",
            (task_id, depends_on_id),
        )

        if result.rowcount > 0:
            event = DomainEvent(
                event_type=EventType.DEPENDENCY_REMOVED,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={"depends_on_id": depends_on_id},
                metadata=self._context.to_metadata(),
            )
            await self.events.append(event)
            return True

        return False

    async def get_dependencies(self, task_id: str) -> list[TaskDependency]:
        """Get tasks that this task depends on."""
        rows = await self.db.fetch_all(
            "SELECT * FROM task_dependencies WHERE task_id = ?",
            (task_id,),
        )
        return [
            TaskDependency(
                id=row["id"],
                task_id=row["task_id"],
                depends_on_id=row["depends_on_id"],
                dependency_type=DependencyType(row["dependency_type"]),
            )
            for row in rows
        ]

    async def get_dependents(self, task_id: str) -> list[TaskDependency]:
        """Get tasks that depend on this task."""
        rows = await self.db.fetch_all(
            "SELECT * FROM task_dependencies WHERE depends_on_id = ?",
            (task_id,),
        )
        return [
            TaskDependency(
                id=row["id"],
                task_id=row["task_id"],
                depends_on_id=row["depends_on_id"],
                dependency_type=DependencyType(row["dependency_type"]),
            )
            for row in rows
        ]

    async def get_by_ids(self, task_ids: list[str]) -> list[Task]:
        """Get tasks by IDs, preserving input order."""
        if not task_ids:
            return []

        unique_ids = list(dict.fromkeys(task_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"SELECT * FROM tasks WHERE id IN ({placeholders})",
            tuple(unique_ids),
        )
        task_map = {row["id"]: self._model_from_row(row) for row in rows}
        return [task_map[task_id] for task_id in unique_ids if task_id in task_map]

    def _parse_timestamp(self, value: Any) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _merge_activity(
        self,
        activity: dict[str, datetime | None],
        task_id: str,
        candidate: datetime | None,
    ) -> None:
        if candidate is None:
            return
        current = activity.get(task_id)
        if current is None or candidate > current:
            activity[task_id] = candidate

    async def get_last_activity_map(
        self,
        task_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Get last activity timestamps for tasks across activity sources."""
        if not task_ids:
            return {}

        unique_ids = list(dict.fromkeys(task_ids))
        placeholders = ", ".join("?" * len(unique_ids))

        rows = await self.db.fetch_all(
            f"""
            SELECT id, updated_at, last_progress_update_at
            FROM tasks
            WHERE id IN ({placeholders})
            """,
            tuple(unique_ids),
        )
        activity: dict[str, datetime | None] = {task_id: None for task_id in unique_ids}
        for row in rows:
            task_id = row["id"]
            self._merge_activity(
                activity, task_id, self._parse_timestamp(row.get("updated_at"))
            )
            self._merge_activity(
                activity,
                task_id,
                self._parse_timestamp(row.get("last_progress_update_at")),
            )

        progress_rows = await self.db.fetch_all(
            f"""
            SELECT task_id, MAX(timestamp) as ts
            FROM task_progress_updates
            WHERE task_id IN ({placeholders})
            GROUP BY task_id
            """,
            tuple(unique_ids),
        )
        for row in progress_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        evidence_rows = await self.db.fetch_all(
            f"""
            SELECT task_id, MAX(created_at) as ts
            FROM task_evidence
            WHERE task_id IN ({placeholders})
            GROUP BY task_id
            """,
            tuple(unique_ids),
        )
        for row in evidence_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        custom_field_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as task_id, MAX(created_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'task' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(unique_ids),
        )
        for row in custom_field_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        comment_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as task_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'task' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(unique_ids),
        )
        for row in comment_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        label_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as task_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'task' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(unique_ids),
        )
        for row in label_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        watcher_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as task_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'task' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            tuple(unique_ids),
        )
        for row in watcher_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        transition_map = await self.get_last_transition_map(unique_ids)
        for task_id, transition_ts in transition_map.items():
            self._merge_activity(activity, task_id, transition_ts)

        checkout_rows = await self.db.fetch_all(
            f"""
            SELECT task_id, MAX(timestamp) as ts
            FROM task_checkout_log
            WHERE task_id IN ({placeholders})
            GROUP BY task_id
            """,
            tuple(unique_ids),
        )
        for row in checkout_rows:
            self._merge_activity(
                activity,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        return activity

    async def get_last_transition_map(
        self,
        task_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Get the most recent transition timestamp per task."""
        if not task_ids:
            return {}

        unique_ids = list(dict.fromkeys(task_ids))
        transition_map: dict[str, datetime | None] = {
            task_id: None for task_id in unique_ids
        }
        placeholders = ", ".join("?" * len(unique_ids))

        legacy_rows = await self.db.fetch_all(
            f"""
            SELECT task_id, MAX(timestamp) as ts
            FROM task_state_transitions
            WHERE task_id IN ({placeholders})
            GROUP BY task_id
            """,
            tuple(unique_ids),
        )
        for row in legacy_rows:
            self._merge_activity(
                transition_map,
                row["task_id"],
                self._parse_timestamp(row.get("ts")),
            )

        state_repo = StateTransitionRepository(self.db)
        workflow_transitions = await state_repo.get_last_transition_map(
            "task_workflow",
            unique_ids,
        )
        status_transitions = await state_repo.get_last_transition_map(
            "task_status",
            unique_ids,
        )
        for task_id in unique_ids:
            self._merge_activity(
                transition_map,
                task_id,
                workflow_transitions.get(task_id),
            )
            self._merge_activity(
                transition_map,
                task_id,
                status_transitions.get(task_id),
            )

        return transition_map

    async def get_by_project(
        self,
        project_id: str,
        status: TaskStatus | None = None,
        assignee: str | None = None,
        assignee_any: list[str] | None = None,
        include_subtasks: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """Get tasks for a project with optional filters."""
        where_clauses = ["project_id = ?"]
        params: list[Any] = [project_id]

        if status:
            where_clauses.append("status = ?")
            params.append(status.value)

        self._append_assignment_filter(
            where_clauses=where_clauses,
            params=params,
            assignee=assignee,
            assignee_any=assignee_any,
        )

        if not include_subtasks:
            where_clauses.append("parent_id IS NULL")

        where_sql = " AND ".join(where_clauses)

        # Get count
        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM tasks WHERE {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        # Get tasks
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            ORDER BY sort_order, created_at
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_subtasks(self, parent_id: str) -> list[Task]:
        """Get direct subtasks of a task."""
        rows = await self.db.fetch_all(
            "SELECT * FROM tasks WHERE parent_id = ? ORDER BY sort_order",
            (parent_id,),
        )
        return [self._model_from_row(row) for row in rows]

    async def get_with_context(self, task_id: str) -> TaskWithContext | None:
        """Get task with full context (subtasks, dependencies, names)."""
        task = await self.get_by_id(task_id)
        if task is None:
            return None

        subtasks = await self.get_subtasks(task_id)
        dependencies = await self.get_dependencies(task_id)
        dependents = await self.get_dependents(task_id)

        # Get project name
        project_row = await self.db.fetch_one(
            "SELECT name FROM projects WHERE id = ?",
            (task.project_id,),
        )
        project_name = project_row["name"] if project_row else ""

        # Get milestone name
        milestone_name = None
        if task.milestone_id:
            ms_row = await self.db.fetch_one(
                "SELECT name FROM milestones WHERE id = ?",
                (task.milestone_id,),
            )
            milestone_name = ms_row["name"] if ms_row else None

        # Get parent title
        parent_title = None
        if task.parent_id:
            parent_row = await self.db.fetch_one(
                "SELECT title FROM tasks WHERE id = ?",
                (task.parent_id,),
            )
            parent_title = parent_row["title"] if parent_row else None

        return TaskWithContext(
            task=task,
            subtasks=subtasks,
            dependencies=dependencies,
            dependents=dependents,
            project_name=project_name,
            milestone_name=milestone_name,
            parent_title=parent_title,
        )

    async def get_blocked_tasks(self, project_id: str | None = None) -> list[Task]:
        """Get all blocked tasks, optionally filtered by project."""
        sql = "SELECT * FROM tasks WHERE status = ?"
        params: list[Any] = [TaskStatus.BLOCKED.value]

        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)

        rows = await self.db.fetch_all(sql, tuple(params))
        return [self._model_from_row(row) for row in rows]

    async def get_overdue_tasks(self, project_id: str | None = None) -> list[Task]:
        """Get all overdue tasks."""
        sql = """
            SELECT * FROM tasks
            WHERE due_date < datetime('now')
            AND status NOT IN (?, ?)
        """
        params: list[Any] = [TaskStatus.DONE.value, TaskStatus.CANCELLED.value]

        if project_id:
            sql += " AND project_id = ?"
            params.append(project_id)

        rows = await self.db.fetch_all(sql, tuple(params))
        return [self._model_from_row(row) for row in rows]

    async def search(
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
        where_clauses = []
        params: list[Any] = []

        if query:
            where_clauses.append("(title LIKE ? OR description LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if statuses:
            placeholders = ", ".join("?" * len(statuses))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend([status.value for status in statuses])
        elif not include_terminal:
            where_clauses.append("status NOT IN (?, ?)")
            params.extend([TaskStatus.DONE.value, TaskStatus.CANCELLED.value])

        if priorities:
            placeholders = ", ".join("?" * len(priorities))
            where_clauses.append(f"priority IN ({placeholders})")
            params.extend([priority.value for priority in priorities])

        self._append_assignment_filter(
            where_clauses=where_clauses,
            params=params,
            assignee=assignee,
            assignee_any=assignee_any,
        )

        if created_from:
            where_clauses.append("created_at >= ?")
            params.append(created_from.isoformat())
        if created_to:
            where_clauses.append("created_at <= ?")
            params.append(created_to.isoformat())

        if updated_from:
            where_clauses.append("updated_at >= ?")
            params.append(updated_from.isoformat())
        if updated_to:
            where_clauses.append("updated_at <= ?")
            params.append(updated_to.isoformat())

        if due_from:
            where_clauses.append("due_date >= ?")
            params.append(due_from.isoformat())
        if due_to:
            where_clauses.append("due_date <= ?")
            params.append(due_to.isoformat())

        if tags:
            tag_clauses = []
            for tag in tags:
                tag_clauses.append("tags LIKE ?")
                params.append(f'%"{tag}"%')
            where_clauses.append(f"({' OR '.join(tag_clauses)})")

        if label_ids:
            placeholders = ", ".join("?" * len(label_ids))
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1 FROM label_assignments la
                    WHERE la.entity_type = 'task'
                      AND la.entity_id = tasks.id
                      AND la.label_id IN ({placeholders})
                      AND la.archived_at IS NULL
                )
                """
            )
            params.extend(label_ids)

        if label_category_ids:
            placeholders = ", ".join("?" * len(label_category_ids))
            where_clauses.append(
                f"""
                EXISTS (
                    SELECT 1
                    FROM label_assignments la
                    INNER JOIN labels l ON la.label_id = l.id
                    WHERE la.entity_type = 'task'
                      AND la.entity_id = tasks.id
                      AND l.category_id IN ({placeholders})
                      AND la.archived_at IS NULL
                      AND l.archived_at IS NULL
                )
                """
            )
            params.extend(label_category_ids)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM tasks WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        order_by = self._build_search_order(sort_by, sort_dir)

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            {order_by}
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    def _build_search_order(self, sort_by: str | None, sort_dir: str | None) -> str:
        sort_key = (sort_by or "updated_at").lower()
        direction = "ASC" if (sort_dir or "desc").lower() == "asc" else "DESC"

        match sort_key:
            case "created_at":
                return f"ORDER BY created_at {direction}"
            case "due_date":
                return (
                    "ORDER BY "
                    f"CASE WHEN due_date IS NULL THEN 1 ELSE 0 END, "
                    f"due_date {direction}"
                )
            case "priority":
                return (
                    "ORDER BY "
                    "CASE priority "
                    "WHEN 'critical' THEN 4 "
                    "WHEN 'high' THEN 3 "
                    "WHEN 'medium' THEN 2 "
                    "WHEN 'low' THEN 1 "
                    "ELSE 0 END "
                    f"{direction}, updated_at DESC"
                )
            case _:
                return f"ORDER BY updated_at {direction}"

    async def find_duplicate_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        include_terminal: bool = False,
        min_count: int = 2,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[DuplicateTaskGroup]:
        """Find tasks with duplicate normalized titles."""
        where_clauses = []
        params: list[Any] = []

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if statuses:
            placeholders = ", ".join("?" * len(statuses))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend([status.value for status in statuses])
        elif not include_terminal:
            where_clauses.append("status NOT IN (?, ?)")
            params.extend([TaskStatus.DONE.value, TaskStatus.CANCELLED.value])

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        count_row = await self.db.fetch_one(
            f"""
            SELECT COUNT(*) as count FROM (
                SELECT LOWER(TRIM(title)) as normalized_title
                FROM tasks
                WHERE {where_sql}
                GROUP BY normalized_title
                HAVING COUNT(*) >= ?
            ) as dupes
            """,
            (*params, min_count),
        )
        total_groups = count_row["count"] if count_row else 0

        group_rows = await self.db.fetch_all(
            f"""
            SELECT LOWER(TRIM(title)) as normalized_title, COUNT(*) as count
            FROM tasks
            WHERE {where_sql}
            GROUP BY normalized_title
            HAVING COUNT(*) >= ?
            ORDER BY count DESC, normalized_title ASC
            LIMIT ? OFFSET ?
            """,
            (*params, min_count, limit, offset),
        )

        groups: list[DuplicateTaskGroup] = []
        for row in group_rows:
            normalized_title = row["normalized_title"]
            task_rows = await self.db.fetch_all(
                f"""
                SELECT * FROM tasks
                WHERE {where_sql} AND LOWER(TRIM(title)) = ?
                ORDER BY updated_at DESC
                """,
                (*params, normalized_title),
            )
            groups.append(
                DuplicateTaskGroup(
                    normalized_title=normalized_title,
                    tasks=[self._model_from_row(task_row) for task_row in task_rows],
                )
            )

        return QueryResult(
            items=groups,
            total_count=total_groups,
            offset=offset,
            limit=limit,
        )

    async def _would_create_cycle(self, task_id: str, depends_on_id: str) -> bool:
        """Check if adding a dependency would create a cycle."""
        # Simple cycle detection using DFS
        visited = set()
        stack = [depends_on_id]

        while stack:
            current = stack.pop()
            if current == task_id:
                return True

            if current in visited:
                continue
            visited.add(current)

            deps = await self.get_dependencies(current)
            for dep in deps:
                stack.append(dep.depends_on_id)

        return False

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Task | None:
        """Rebuild task state from events."""
        if not events:
            return None

        task = None

        for event in events:
            match event.event_type:
                case EventType.TASK_CREATED:
                    p = event.payload
                    task = Task(
                        id=event.aggregate_id,
                        project_id=p.get("project_id", ""),
                        title=p.get("title", ""),
                        description=p.get("description"),
                        milestone_id=p.get("milestone_id"),
                        parent_id=p.get("parent_id"),
                        priority=Priority(p.get("priority", "medium")),
                        complexity_points=p.get("complexity_points"),
                        assignee=p.get("assignee"),
                        assignee_id=p.get("assignee_id"),
                        tags=tuple(p.get("tags", [])),
                    )
                case EventType.TASK_UPDATED if task:
                    p_update = event.payload
                    changes = p_update.get("changes", {})
                    if "title" in changes:
                        task.title = changes["title"]
                    if "description" in changes:
                        task.description = changes["description"]
                    if "parent_id" in changes:
                        task.parent_id = changes["parent_id"]
                    if "priority" in changes:
                        task.priority = Priority(changes["priority"])
                    if "complexity_points" in changes:
                        task.complexity_points = changes["complexity_points"]
                    if "assignee" in changes:
                        task.assignee = changes["assignee"]
                    if "assignee_id" in changes:
                        task.assignee_id = changes["assignee_id"]
                case EventType.TASK_STATUS_CHANGED if task:
                    p2 = event.payload
                    task.status = TaskStatus(p2.get("new_status", "todo"))
                    if p2.get("actual_hours"):
                        task.actual_hours = p2["actual_hours"]
                case EventType.TASK_COMPLETED if task:
                    p3 = event.payload
                    task.status = TaskStatus.DONE
                    if p3.get("actual_hours"):
                        task.actual_hours = p3["actual_hours"]

        return task

    # ============================================================
    # CHECKOUT METHODS - Distributed Agent Coordination
    # ============================================================

    async def checkout_task(
        self,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        checkout_actor_id: str | None = None,
        force: bool = False,
        checkout_parent: bool = True,
    ) -> Task | None:
        """
        Check out a task for exclusive work with optimistic locking.

        Args:
            task_id: Task to check out
            agent_session_id: Unique agent session identifier
            lease_seconds: Duration of lease (default 5 minutes)
            force: Force checkout even if held by another agent (dangerous!)
            checkout_parent: Also checkout parent task if this is a subtask

        Returns:
            Task with checkout or None if not found

        Raises:
            TaskCheckoutConflict: If task is already checked out
            TaskCheckoutBlocked: If dependencies prevent checkout
        """

        async def _checkout() -> Task | None:
            return await self._checkout_task_in_transaction(
                task_id=task_id,
                agent_session_id=agent_session_id,
                lease_seconds=lease_seconds,
                checkout_actor_id=checkout_actor_id,
                force=force,
                checkout_parent=checkout_parent,
            )

        return await self._run_in_owned_transaction(
            _checkout,
            operation_name="checkout_task",
        )

    async def _checkout_task_in_transaction(
        self,
        *,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        checkout_actor_id: str | None = None,
        force: bool = False,
        checkout_parent: bool = True,
    ) -> Task | None:
        """Check out a task assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_checkout_task_in_transaction")
        from pms.exceptions.base import TaskCheckoutBlocked, TaskCheckoutConflict

        # Fetch task
        task = await self.get_by_id(task_id)
        if not task:
            return None

        # Already owned by requesting agent - renew instead
        if (
            task.checkout_agent_session_id == agent_session_id
            and not task.checkout_expired
        ):
            return await self._renew_checkout_in_transaction(
                task_id=task_id,
                agent_session_id=agent_session_id,
                lease_seconds=lease_seconds,
                checkout_actor_id=checkout_actor_id,
            )

        # Held by another agent (not expired)
        if task.is_checked_out and not force:
            await self._log_checkout_action(
                task_id=task_id,
                agent_session_id=agent_session_id,
                action="conflict",
                success=False,
                conflict_with=task.checkout_agent_session_id,
            )

            raise TaskCheckoutConflict(
                f"Task {task_id} is checked out by {task.checkout_agent_session_id} "
                f"until {task.checkout_lease_until}"
            )

        # Check blocking dependencies
        if not await self._can_checkout_dependencies(task_id):
            raise TaskCheckoutBlocked(
                f"Task {task_id} has incomplete blocking dependencies"
            )

        # Checkout parent if subtask
        if checkout_parent and task.parent_id:
            try:
                await self._checkout_task_in_transaction(
                    task_id=task.parent_id,
                    agent_session_id=agent_session_id,
                    lease_seconds=lease_seconds,
                    checkout_actor_id=checkout_actor_id,
                    force=force,
                    checkout_parent=True,
                )
            except TaskCheckoutConflict, TaskCheckoutBlocked:
                raise TaskCheckoutBlocked(
                    f"Cannot checkout task {task_id}: parent not available"
                )

        # Perform checkout with optimistic locking
        old_version = task.checkout_version
        task.checkout(
            agent_session_id,
            lease_seconds,
            actor_id=checkout_actor_id,
        )

        # Update with version check (prevents race conditions)
        assert task.checked_out_at is not None
        assert task.checkout_lease_until is not None
        result = await self.db.execute(
            """
            UPDATE tasks SET
                checkout_agent_session_id = ?,
                checkout_actor_id = ?,
                checked_out_at = ?,
                checkout_lease_until = ?,
                checkout_version = ?,
                updated_at = ?
            WHERE id = ? AND checkout_version = ?
            """,
            (
                task.checkout_agent_session_id,
                task.checkout_actor_id,
                task.checked_out_at.isoformat(),
                task.checkout_lease_until.isoformat(),
                task.checkout_version,
                task.updated_at.isoformat(),
                task_id,
                old_version,
            ),
        )

        if result.rowcount == 0:
            raise TaskCheckoutConflict(
                f"Concurrent checkout detected for task {task_id}"
            )

        # Log successful checkout
        await self._log_checkout_action(
            task_id=task_id,
            agent_session_id=agent_session_id,
            action="checkout",
            success=True,
            lease_seconds=lease_seconds,
            checkout_actor_id=task.checkout_actor_id,
        )

        # Emit checkout event
        await self.events.append(
            DomainEvent(
                event_type=EventType.TASK_CHECKED_OUT,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={
                    "agent_session_id": agent_session_id,
                    "checkout_actor_id": task.checkout_actor_id,
                    "lease_seconds": lease_seconds,
                    "checkout_version": task.checkout_version,
                },
                metadata=self._context.to_metadata(),
            )
        )

        return task

    async def _renew_checkout_in_transaction(
        self,
        *,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        checkout_actor_id: str | None = None,
    ) -> Task | None:
        """Renew checkout assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_renew_checkout_in_transaction")
        from pms.exceptions.base import TaskCheckoutConflict

        task = await self.get_by_id(task_id)
        if not task:
            return None

        if task.checkout_agent_session_id != agent_session_id:
            raise TaskCheckoutConflict(
                f"Task {task_id} not checked out by {agent_session_id}"
            )

        old_lease = task.checkout_lease_until
        task.renew_checkout(
            agent_session_id,
            lease_seconds,
            actor_id=checkout_actor_id,
        )

        assert task.checkout_lease_until is not None
        await self.db.execute(
            """
            UPDATE tasks SET
                checkout_actor_id = ?,
                checkout_lease_until = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                task.checkout_actor_id,
                task.checkout_lease_until.isoformat(),
                task.updated_at.isoformat(),
                task_id,
            ),
        )

        await self._log_checkout_action(
            task_id=task_id,
            agent_session_id=agent_session_id,
            action="renew",
            success=True,
            lease_seconds=lease_seconds,
            checkout_actor_id=task.checkout_actor_id,
        )

        await self.events.append(
            DomainEvent(
                event_type=EventType.TASK_CHECKOUT_RENEWED,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={
                    "agent_session_id": agent_session_id,
                    "checkout_actor_id": task.checkout_actor_id,
                    "new_lease_seconds": lease_seconds,
                    "previous_lease_until": old_lease.isoformat()
                    if old_lease
                    else None,
                },
                metadata=self._context.to_metadata(),
            )
        )

        return task

    async def renew_checkout(
        self,
        task_id: str,
        agent_session_id: str,
        lease_seconds: int = 300,
        checkout_actor_id: str | None = None,
    ) -> Task | None:
        """Renew checkout lease (heartbeat mechanism)."""

        async def _renew() -> Task | None:
            return await self._renew_checkout_in_transaction(
                task_id=task_id,
                agent_session_id=agent_session_id,
                lease_seconds=lease_seconds,
                checkout_actor_id=checkout_actor_id,
            )

        return await self._run_in_owned_transaction(
            _renew,
            operation_name="renew_checkout",
        )

    async def release_checkout(
        self,
        task_id: str,
        agent_session_id: str,
        work_completed: bool = True,
    ) -> Task | None:
        """Release checkout lock."""

        async def _release() -> Task | None:
            return await self._release_checkout_in_transaction(
                task_id=task_id,
                agent_session_id=agent_session_id,
                work_completed=work_completed,
            )

        return await self._run_in_owned_transaction(
            _release,
            operation_name="release_checkout",
        )

    async def _release_checkout_in_transaction(
        self,
        *,
        task_id: str,
        agent_session_id: str,
        work_completed: bool = True,
    ) -> Task | None:
        """Release checkout assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_release_checkout_in_transaction")
        from pms.exceptions.base import TaskCheckoutConflict

        task = await self.get_by_id(task_id)
        if not task:
            return None

        if task.checkout_agent_session_id != agent_session_id:
            raise TaskCheckoutConflict(
                f"Task {task_id} not checked out by {agent_session_id}"
            )

        duration = (
            (now_utc() - task.checked_out_at).total_seconds()
            if task.checked_out_at
            else 0
        )

        task.release_checkout(agent_session_id)

        await self.db.execute(
            """
            UPDATE tasks SET
                checkout_agent_session_id = NULL,
                checkout_actor_id = NULL,
                checked_out_at = NULL,
                checkout_lease_until = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (task.updated_at.isoformat(), task_id),
        )

        await self._log_checkout_action(
            task_id=task_id,
            agent_session_id=agent_session_id,
            action="release",
            success=True,
            checkout_actor_id=None,
        )

        await self.events.append(
            DomainEvent(
                event_type=EventType.TASK_CHECKOUT_RELEASED,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={
                    "agent_session_id": agent_session_id,
                    "checkout_actor_id": None,
                    "duration_seconds": duration,
                    "work_completed": work_completed,
                },
                metadata=self._context.to_metadata(),
            )
        )

        return task

    async def force_release_checkout(
        self,
        task_id: str,
        released_by: str | None = None,
        reason: str | None = None,
    ) -> Task | None:
        """Force release a checkout without requiring the original agent."""

        async def _force_release() -> Task | None:
            return await self._force_release_checkout_in_transaction(
                task_id=task_id,
                released_by=released_by,
                reason=reason,
            )

        return await self._run_in_owned_transaction(
            _force_release,
            operation_name="force_release_checkout",
        )

    async def _force_release_checkout_in_transaction(
        self,
        *,
        task_id: str,
        released_by: str | None = None,
        reason: str | None = None,
    ) -> Task | None:
        """Force release checkout assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_force_release_checkout_in_transaction")
        task = await self.get_by_id(task_id)
        if not task:
            return None

        if task.checkout_agent_session_id is None:
            return task

        previous_agent = task.checkout_agent_session_id
        previous_checkout_actor_id = task.checkout_actor_id
        task.checkout_agent_session_id = None
        task.checkout_actor_id = None
        task.checked_out_at = None
        task.checkout_lease_until = None
        task.touch()

        await self.db.execute(
            """
            UPDATE tasks SET
                checkout_agent_session_id = NULL,
                checkout_actor_id = NULL,
                checked_out_at = NULL,
                checkout_lease_until = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (task.updated_at.isoformat(), task_id),
        )

        await self._log_checkout_action(
            task_id=task_id,
            agent_session_id=released_by or "system",
            action="force_release",
            success=True,
            conflict_with=previous_agent,
            error_message=reason,
            checkout_actor_id=previous_checkout_actor_id,
        )

        await self.events.append(
            DomainEvent(
                event_type=EventType.TASK_CHECKOUT_RELEASED,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={
                    "agent_session_id": previous_agent,
                    "checkout_actor_id": previous_checkout_actor_id,
                    "released_by": released_by or "system",
                    "forced": True,
                    "reason": reason,
                },
                metadata=self._context.to_metadata(),
            )
        )

        return task

    async def cleanup_expired_checkouts(self, dry_run: bool = False) -> list[str]:
        """
        Clean up tasks with expired checkout leases.

        Should be called periodically (e.g., every minute).

        Args:
            dry_run: If True, only report expired checkouts

        Returns:
            List of task IDs that were (or would be) cleaned up
        """
        now = now_utc()

        rows = await self.db.fetch_all(
            """
            SELECT id, checkout_agent_session_id, checkout_lease_until, checkout_actor_id
            FROM tasks
            WHERE checkout_agent_session_id IS NOT NULL
              AND checkout_lease_until IS NOT NULL
              AND checkout_lease_until < ?
            """,
            (now.isoformat(),),
        )

        expired_task_ids = []

        for row in rows:
            task_id = row["id"]
            agent_session_id = row["checkout_agent_session_id"]
            checkout_actor_id = row["checkout_actor_id"]
            expired_task_ids.append(task_id)

            if dry_run:
                continue

            async def _expire() -> None:
                await self._expire_checkout_in_transaction(
                    task_id=task_id,
                    agent_session_id=agent_session_id,
                    checkout_actor_id=checkout_actor_id,
                    lease_expired_at=row["checkout_lease_until"],
                    updated_at=now.isoformat(),
                )

            await self._run_in_owned_transaction(
                _expire,
                operation_name="expire_checkout",
            )

        return expired_task_ids

    async def _expire_checkout_in_transaction(
        self,
        *,
        task_id: str,
        agent_session_id: str,
        checkout_actor_id: str | None,
        lease_expired_at: str,
        updated_at: str,
    ) -> None:
        """Expire a checkout assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_expire_checkout_in_transaction")
        await self.db.execute(
            """
            UPDATE tasks SET
                checkout_agent_session_id = NULL,
                checkout_actor_id = NULL,
                checked_out_at = NULL,
                checkout_lease_until = NULL,
                updated_at = ?
            WHERE id = ?
            """,
            (updated_at, task_id),
        )

        await self._log_checkout_action(
            task_id=task_id,
            agent_session_id=agent_session_id,
            action="expire",
            success=True,
            checkout_actor_id=checkout_actor_id,
        )

        await self.events.append(
            DomainEvent(
                event_type=EventType.TASK_CHECKOUT_EXPIRED,
                aggregate_type="task",
                aggregate_id=task_id,
                payload={
                    "agent_session_id": agent_session_id,
                    "checkout_actor_id": checkout_actor_id,
                    "lease_expired_at": lease_expired_at,
                    "auto_released": True,
                },
                metadata=self._context.to_metadata(),
            )
        )

    async def get_available_tasks(
        self,
        project_id: str | None = None,
        status: TaskStatus | None = None,
        exclude_checked_out: bool = True,
        limit: int = 100,
    ) -> list[Task]:
        """Get tasks available for checkout."""
        where_clauses = []
        params: list[Any] = []

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if status:
            where_clauses.append("status = ?")
            params.append(status.value)
        else:
            # Exclude terminal statuses
            where_clauses.append("status NOT IN (?, ?)")
            params.extend([TaskStatus.DONE.value, TaskStatus.CANCELLED.value])

        if exclude_checked_out:
            now = now_utc()
            where_clauses.append(
                "(checkout_agent_session_id IS NULL OR checkout_lease_until < ?)"
            )
            params.append(now.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            ORDER BY priority DESC, created_at ASC
            LIMIT ?
            """,
            (*params, limit),
        )

        return [self._model_from_row(row) for row in rows]

    async def get_ready_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        exclude_checked_out: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """Get tasks ready to start (no blocking dependencies)."""
        where_clauses = []
        params: list[Any] = []

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if statuses:
            placeholders = ", ".join("?" * len(statuses))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend([status.value for status in statuses])
        else:
            where_clauses.append("status = ?")
            params.append(TaskStatus.TODO.value)

        if exclude_checked_out:
            now = now_utc()
            where_clauses.append(
                "(checkout_agent_session_id IS NULL OR checkout_lease_until < ?)"
            )
            params.append(now.isoformat())

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            ORDER BY priority DESC, updated_at DESC
            """,
            tuple(params),
        )

        ready_tasks: list[Task] = []
        for row in rows:
            task = self._model_from_row(row)
            if await self._can_checkout_dependencies(task.id):
                ready_tasks.append(task)

        total = len(ready_tasks)
        items = ready_tasks[offset : offset + limit]

        return QueryResult(
            items=items,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_stale_tasks(
        self,
        project_id: str | None = None,
        statuses: list[TaskStatus] | None = None,
        stale_after_days: int = 14,
        updated_before: datetime | None = None,
        include_terminal: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """Get tasks with no recent updates."""
        threshold = updated_before
        if threshold is None:
            threshold = now_utc() - timedelta(days=stale_after_days)

        where_clauses = ["updated_at <= ?"]
        params: list[Any] = [threshold.isoformat()]

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if statuses:
            placeholders = ", ".join("?" * len(statuses))
            where_clauses.append(f"status IN ({placeholders})")
            params.extend([status.value for status in statuses])
        elif not include_terminal:
            where_clauses.append("status NOT IN (?, ?)")
            params.extend([TaskStatus.DONE.value, TaskStatus.CANCELLED.value])

        where_sql = " AND ".join(where_clauses)

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM tasks WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            ORDER BY updated_at ASC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_agent_checkouts(
        self,
        agent_session_id: str,
        include_expired: bool = False,
    ) -> list[Task]:
        """Get all tasks currently checked out by an agent."""
        now = now_utc()

        params: tuple[Any, ...]
        if include_expired:
            where_clause = "checkout_agent_session_id = ?"
            params = (agent_session_id,)
        else:
            where_clause = "checkout_agent_session_id = ? AND checkout_lease_until >= ?"
            params = (agent_session_id, now.isoformat())

        rows = await self.db.fetch_all(
            f"SELECT * FROM tasks WHERE {where_clause}",
            params,
        )

        return [self._model_from_row(row) for row in rows]

    async def get_checkouts_by_actor(
        self,
        *,
        checkout_actor_ids: list[str],
        project_id: str | None = None,
        include_expired: bool = True,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Task]:
        """List tasks checked out by the given canonical checkout actor ids."""
        if not checkout_actor_ids:
            return QueryResult(items=[], total_count=0, offset=offset, limit=limit)

        now = now_utc().isoformat()
        placeholders = ", ".join("?" * len(checkout_actor_ids))
        where_clauses = [
            "checkout_agent_session_id IS NOT NULL",
            f"checkout_actor_id IN ({placeholders})",
        ]
        params: list[Any] = list(checkout_actor_ids)

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if not include_expired:
            where_clauses.append("checkout_lease_until >= ?")
            params.append(now)

        where_sql = " AND ".join(where_clauses)
        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM tasks WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM tasks
            WHERE {where_sql}
            ORDER BY
                CASE
                    WHEN checkout_lease_until IS NOT NULL AND checkout_lease_until >= ? THEN 0
                    ELSE 1
                END,
                checkout_lease_until ASC,
                updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, now, limit, offset),
        )
        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_checkout_rollup(
        self,
        *,
        checkout_actor_ids: list[str],
        project_id: str | None = None,
        include_expired: bool = True,
    ) -> dict[str, int]:
        """Return checkout rollups for canonical checkout actors."""
        if not checkout_actor_ids:
            return {
                "total_checkouts": 0,
                "active_checkouts": 0,
                "expired_checkouts": 0,
                "distinct_agents": 0,
            }

        now = now_utc().isoformat()
        placeholders = ", ".join("?" * len(checkout_actor_ids))
        where_clauses = [
            "checkout_agent_session_id IS NOT NULL",
            f"checkout_actor_id IN ({placeholders})",
        ]
        params: list[Any] = [now, now, *checkout_actor_ids]

        if project_id:
            where_clauses.append("project_id = ?")
            params.append(project_id)

        if not include_expired:
            where_clauses.append("checkout_lease_until >= ?")
            params.append(now)

        where_sql = " AND ".join(where_clauses)
        row = await self.db.fetch_one(
            f"""
            SELECT
                COUNT(*) AS total_checkouts,
                SUM(
                    CASE
                        WHEN checkout_lease_until IS NOT NULL AND checkout_lease_until >= ?
                        THEN 1 ELSE 0
                    END
                ) AS active_checkouts,
                SUM(
                    CASE
                        WHEN checkout_lease_until IS NOT NULL AND checkout_lease_until < ?
                        THEN 1 ELSE 0
                    END
                ) AS expired_checkouts,
                COUNT(DISTINCT checkout_agent_session_id) AS distinct_agents
            FROM tasks
            WHERE {where_sql}
            """,
            tuple(params),
        )
        if row is None:
            return {
                "total_checkouts": 0,
                "active_checkouts": 0,
                "expired_checkouts": 0,
                "distinct_agents": 0,
            }
        return {
            "total_checkouts": int(row["total_checkouts"] or 0),
            "active_checkouts": int(row["active_checkouts"] or 0),
            "expired_checkouts": int(row["expired_checkouts"] or 0),
            "distinct_agents": int(row["distinct_agents"] or 0),
        }

    async def get_checkout_rollup_by_project(
        self,
        *,
        checkout_actor_ids: list[str],
        include_expired: bool = True,
    ) -> list[dict[str, Any]]:
        """Return checkout rollups grouped by project for canonical checkout actors."""
        if not checkout_actor_ids:
            return []

        now = now_utc().isoformat()
        placeholders = ", ".join("?" * len(checkout_actor_ids))
        where_clauses = [
            "checkout_agent_session_id IS NOT NULL",
            f"checkout_actor_id IN ({placeholders})",
        ]
        params: list[Any] = [now, now, *checkout_actor_ids]

        if not include_expired:
            where_clauses.append("checkout_lease_until >= ?")
            params.append(now)

        where_sql = " AND ".join(where_clauses)
        rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) AS total_checkouts,
                SUM(
                    CASE
                        WHEN checkout_lease_until IS NOT NULL AND checkout_lease_until >= ?
                        THEN 1 ELSE 0
                    END
                ) AS active_checkouts,
                SUM(
                    CASE
                        WHEN checkout_lease_until IS NOT NULL AND checkout_lease_until < ?
                        THEN 1 ELSE 0
                    END
                ) AS expired_checkouts,
                COUNT(DISTINCT checkout_agent_session_id) AS distinct_agents
            FROM tasks
            WHERE {where_sql}
            GROUP BY project_id
            ORDER BY total_checkouts DESC, project_id
            """,
            tuple(params),
        )
        return [{key: row[key] for key in row} for row in rows]

    async def get_checkout_log(
        self,
        task_id: str | None = None,
        agent_session_id: str | None = None,
        action: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
        include_metadata: bool = False,
    ) -> list[dict[str, Any]]:
        """Fetch checkout log entries with optional filters."""
        where_clauses = []
        params: list[Any] = []

        if task_id:
            where_clauses.append("task_id = ?")
            params.append(task_id)
        if agent_session_id:
            where_clauses.append("agent_session_id = ?")
            params.append(agent_session_id)
        if action:
            where_clauses.append("action = ?")
            params.append(action)
        if success is not None:
            where_clauses.append("success = ?")
            params.append(1 if success else 0)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        rows = await self.db.fetch_all(
            f"""
            SELECT id, task_id, agent_session_id, action, lease_seconds,
                   success, conflict_with, error_message, timestamp, metadata
            FROM task_checkout_log
            WHERE {where_sql}
            ORDER BY timestamp DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )

        return [
            {
                "id": row["id"],
                "task_id": row["task_id"],
                "agent_session_id": row["agent_session_id"],
                "action": row["action"],
                "lease_seconds": row["lease_seconds"],
                "success": bool(row["success"]),
                "conflict_with": row["conflict_with"],
                "error_message": row["error_message"],
                "timestamp": row["timestamp"],
                "checkout_actor_id": (
                    json.loads(row["metadata"]).get("checkout_actor_id")
                    if row["metadata"]
                    else None
                ),
                "metadata": (
                    json.loads(row["metadata"])
                    if include_metadata and row["metadata"]
                    else None
                ),
            }
            for row in rows
        ]

    async def _can_checkout_dependencies(self, task_id: str) -> bool:
        """Check if all blocking dependencies are complete."""
        row = await self.db.fetch_one(
            """
            SELECT COUNT(*) as remaining
            FROM task_dependencies d
            INNER JOIN tasks t ON d.depends_on_id = t.id
            WHERE d.task_id = ?
              AND LOWER(d.dependency_type) = ?
              AND t.status NOT IN (?, ?)
            """,
            (
                task_id,
                DependencyType.BLOCKS.value,
                TaskStatus.DONE.value,
                TaskStatus.CANCELLED.value,
            ),
        )
        remaining = row["remaining"] if row else 0
        return remaining == 0

    async def _log_checkout_action(
        self,
        task_id: str,
        agent_session_id: str,
        action: str,
        success: bool,
        lease_seconds: int | None = None,
        conflict_with: str | None = None,
        error_message: str | None = None,
        checkout_actor_id: str | None = None,
    ) -> None:
        """Log checkout action to audit table."""
        self._assert_owned_transaction("_log_checkout_action")
        from pms.core.ids import EntityType, generate_id

        metadata = self._context.to_metadata().to_dict()
        if checkout_actor_id is not None:
            metadata["checkout_actor_id"] = checkout_actor_id

        await self.db.execute(
            """
            INSERT INTO task_checkout_log (
                id, task_id, agent_session_id, action,
                lease_seconds, success, conflict_with, error_message,
                timestamp, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_id(EntityType.EVENT),
                task_id,
                agent_session_id,
                action,
                lease_seconds,
                1 if success else 0,
                conflict_with,
                error_message,
                now_utc().isoformat(),
                json.dumps(metadata),
            ),
        )
