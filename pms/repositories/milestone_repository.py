"""Milestone repository with event sourcing."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.config.logging import logger
from pms.core import EventType
from pms.exceptions import NotFoundError
from pms.models.enums import MilestoneStatus
from pms.models.milestone import Milestone, MilestoneStats, MilestoneWithTasks
from pms.repositories.base import EventSourcedRepository, RepositoryContext

if TYPE_CHECKING:
    from pms.core import EventStore, MetricsCollector, RevisionStore
    from pms.db.connection import Database


class MilestoneRepository(EventSourcedRepository[Milestone]):
    """Repository for milestone persistence with event sourcing."""

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
        return "milestone"

    @property
    def table_name(self) -> str:
        return "milestones"

    # =============================================================================
    # CRUD Operations
    # =============================================================================

    async def create(
        self,
        project_id: str,
        name: str,
        description: str | None = None,
        due_date: datetime | None = None,
        sort_order: int = 0,
        context: RepositoryContext | None = None,
    ) -> Milestone:
        """
        Create a new milestone.

        Args:
            project_id: Parent project ID
            name: Milestone name
            description: Optional description
            due_date: Optional due date
            sort_order: Display order
            context: Repository context

        Returns:
            Created milestone
        """
        milestone = Milestone(
            project_id=project_id,
            name=name,
            description=description,
            due_date=due_date,
            sort_order=sort_order,
            status=MilestoneStatus.PENDING,
        )

        # Event sourcing: save with CREATED event
        await self.save(
            milestone,
            EventType.MILESTONE_CREATED,
            {
                "project_id": project_id,
                "name": name,
                "description": description,
                "due_date": due_date.isoformat() if due_date else None,
                "sort_order": sort_order,
            },
        )

        logger.info(
            "Milestone created",
            milestone_id=milestone.id,
            name=name,
            project_id=project_id,
        )
        return milestone

    async def update_status(
        self,
        milestone_id: str,
        status: MilestoneStatus,
        context: RepositoryContext | None = None,
    ) -> Milestone:
        """
        Update milestone status.

        Args:
            milestone_id: Milestone ID
            status: New status
            context: Repository context

        Returns:
            Updated milestone
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            raise NotFoundError(milestone_id, f"Milestone {milestone_id} not found")

        old_status = milestone.status
        milestone.status = status

        await self.save(
            milestone,
            EventType.MILESTONE_STATUS_CHANGED,
            {
                "old_status": old_status.value,
                "new_status": status.value,
            },
        )

        logger.info(
            "Milestone status updated",
            milestone_id=milestone_id,
            old_status=old_status.value,
            new_status=status.value,
        )
        return milestone

    async def update(
        self,
        milestone_id: str,
        name: str | None = None,
        description: str | None = None,
        due_date: datetime | None = None,
        sort_order: int | None = None,
        context: RepositoryContext | None = None,
    ) -> Milestone:
        """
        Update milestone fields.

        Args:
            milestone_id: Milestone ID
            name: New name (if provided)
            description: New description (if provided)
            due_date: New due date (if provided)
            sort_order: New sort order (if provided)
            context: Repository context

        Returns:
            Updated milestone
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            raise NotFoundError(milestone_id, f"Milestone {milestone_id} not found")

        changes: dict[str, dict[str, Any]] = {}
        if name is not None:
            changes["name"] = {"old": milestone.name, "new": name}
            milestone.name = name
        if description is not None:
            changes["description"] = {"old": milestone.description, "new": description}
            milestone.description = description
        if due_date is not None:
            changes["due_date"] = {
                "old": milestone.due_date.isoformat() if milestone.due_date else None,
                "new": due_date.isoformat(),
            }
            milestone.due_date = due_date
        if sort_order is not None:
            changes["sort_order"] = {"old": milestone.sort_order, "new": sort_order}
            milestone.sort_order = sort_order

        if not changes:
            return milestone  # No changes

        await self.save(
            milestone,
            EventType.MILESTONE_UPDATED,
            {"changes": changes},
        )

        logger.info(
            "Milestone updated", milestone_id=milestone_id, changes=list(changes.keys())
        )
        return milestone

    async def complete(
        self,
        milestone_id: str,
        context: RepositoryContext | None = None,
    ) -> Milestone:
        """
        Mark milestone as completed.

        Args:
            milestone_id: Milestone ID
            context: Repository context

        Returns:
            Updated milestone
        """
        return await self.update_status(
            milestone_id, MilestoneStatus.COMPLETED, context
        )

    # =============================================================================
    # Query Methods
    # =============================================================================

    async def get_by_project(
        self,
        project_id: str,
        status: MilestoneStatus | None = None,
    ) -> list[Milestone]:
        """
        Get all milestones for a project.

        Args:
            project_id: Project ID
            status: Optional status filter

        Returns:
            List of milestones
        """
        query = "SELECT * FROM milestones WHERE project_id = ?"
        params: list[Any] = [project_id]

        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY sort_order, due_date NULLS LAST, created_at"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_entity(row) for row in rows]

    async def get_overdue(self, project_id: str | None = None) -> list[Milestone]:
        """
        Get overdue milestones.

        Args:
            project_id: Optional project filter

        Returns:
            List of overdue milestones
        """
        query = """
            SELECT * FROM milestones
            WHERE due_date < datetime('now')
            AND status != ?
        """
        params: list[Any] = [MilestoneStatus.COMPLETED.value]

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY due_date"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_entity(row) for row in rows]

    async def get_upcoming(
        self,
        project_id: str | None = None,
        days: int = 30,
    ) -> list[Milestone]:
        """
        Get upcoming milestones within specified days.

        Args:
            project_id: Optional project filter
            days: Number of days to look ahead

        Returns:
            List of upcoming milestones
        """
        query = """
            SELECT * FROM milestones
            WHERE due_date >= datetime('now')
            AND due_date <= datetime('now', '+' || ? || ' days')
            AND status != ?
        """
        params: list[Any] = [days, MilestoneStatus.COMPLETED.value]

        if project_id:
            query += " AND project_id = ?"
            params.append(project_id)

        query += " ORDER BY due_date"

        rows = await self.db.fetch_all(query, tuple(params))
        return [self._row_to_entity(row) for row in rows]

    async def get_stats(self, milestone_id: str) -> MilestoneStats:
        """
        Get statistics for a milestone from its tasks.

        Args:
            milestone_id: Milestone ID

        Returns:
            Milestone statistics
        """
        query = """
            SELECT
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as completed_tasks,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked_tasks
            FROM tasks
            WHERE milestone_id = ?
        """

        row = await self.db.fetch_one(query, (milestone_id,))

        if row is None:
            return MilestoneStats(
                milestone_id=milestone_id,
                total_tasks=0,
                completed_tasks=0,
                in_progress_tasks=0,
                blocked_tasks=0,
            )

        return MilestoneStats(
            milestone_id=milestone_id,
            total_tasks=row["total_tasks"] or 0,
            completed_tasks=row["completed_tasks"] or 0,
            in_progress_tasks=row["in_progress_tasks"] or 0,
            blocked_tasks=row["blocked_tasks"] or 0,
        )

    async def get_with_tasks(
        self,
        milestone_id: str,
    ) -> MilestoneWithTasks:
        """
        Get milestone with its tasks and statistics.

        Args:
            milestone_id: Milestone ID

        Returns:
            Milestone with tasks and stats
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            raise NotFoundError(milestone_id, f"Milestone {milestone_id} not found")

        stats = await self.get_stats(milestone_id)

        # Get tasks for this milestone
        tasks_query = """
            SELECT * FROM tasks
            WHERE milestone_id = ?
            ORDER BY sort_order, created_at
        """
        task_rows = await self.db.fetch_all(tasks_query, (milestone_id,))

        # Import Task model locally to avoid circular import
        from pms.models.task import Task

        tasks = [Task.from_dict(dict(row)) for row in task_rows]

        return MilestoneWithTasks(
            milestone=milestone,
            stats=stats,
            tasks=tasks,
        )

    async def auto_update_status(
        self,
        milestone_id: str,
        context: RepositoryContext | None = None,
    ) -> Milestone | None:
        """
        Automatically update milestone status based on task completion.

        Args:
            milestone_id: Milestone ID
            context: Repository context

        Returns:
            Updated milestone if status changed, None otherwise
        """
        milestone = await self.get_by_id(milestone_id)
        if milestone is None:
            return None

        stats = await self.get_stats(milestone_id)

        # Determine new status based on task stats
        new_status = None

        if stats.total_tasks == 0:
            # No tasks - keep as pending
            if milestone.status != MilestoneStatus.PENDING:
                new_status = MilestoneStatus.PENDING

        elif stats.completed_tasks == stats.total_tasks:
            # All tasks done - mark complete
            if milestone.status != MilestoneStatus.COMPLETED:
                new_status = MilestoneStatus.COMPLETED

        elif stats.in_progress_tasks > 0:
            # Tasks in progress - mark as in progress
            if milestone.status == MilestoneStatus.PENDING:
                new_status = MilestoneStatus.IN_PROGRESS

        elif milestone.is_overdue and milestone.status not in (
            MilestoneStatus.COMPLETED,
            MilestoneStatus.MISSED,
        ):
            # Overdue - mark as missed
            new_status = MilestoneStatus.MISSED

        # Update if status should change
        if new_status:
            return await self.update_status(milestone_id, new_status, context)

        return None  # No update needed

    # =============================================================================
    # Event Sourcing Implementation
    # =============================================================================

    async def _apply_events(self, events: list[Any]) -> Milestone | None:
        """
        Apply events to rebuild milestone state.

        Args:
            events: List of events to apply

        Returns:
            Milestone with events applied
        """
        if not events:
            return None

        milestone = None

        for event in events:
            event_type = EventType(event["event_type"])
            data = event.get("event_data", {})

            match event_type:
                case EventType.MILESTONE_CREATED:
                    payload = event.get("payload", {})
                    milestone = Milestone(
                        id=event.get("aggregate_id"),
                        project_id=payload.get("project_id"),
                        name=payload.get("name"),
                        description=payload.get("description"),
                        due_date=datetime.fromisoformat(payload["due_date"])
                        if payload.get("due_date")
                        else None,
                        sort_order=payload.get("sort_order", 0),
                        status=MilestoneStatus.PENDING,
                    )
                case EventType.MILESTONE_UPDATED if milestone:
                    changes = data.get("changes", {})
                    for field, change in changes.items():
                        match field:
                            case "name":
                                milestone.name = change["new"]
                            case "description":
                                milestone.description = change["new"]
                            case "due_date":
                                milestone.due_date = (
                                    datetime.fromisoformat(change["new"])
                                    if change["new"]
                                    else None
                                )
                            case "sort_order":
                                milestone.sort_order = change["new"]
                            case _:
                                pass
                case EventType.MILESTONE_STATUS_CHANGED if milestone:
                    milestone.status = MilestoneStatus(data["new_status"])
                case _:
                    pass

        return milestone

    def _model_from_row(self, row: dict[str, Any]) -> Milestone:
        """Convert database row to Milestone entity."""
        return Milestone.from_dict(dict(row))

    def _row_from_model(self, entity: Milestone) -> dict[str, Any]:
        """Convert Milestone entity to database row."""
        return entity.to_dict()

    def _row_to_entity(self, row: dict[str, Any]) -> Milestone:
        """Convert database row to Milestone entity."""
        return Milestone.from_dict(dict(row))

    def _entity_to_row(self, entity: Milestone) -> dict[str, Any]:
        """Convert Milestone entity to database row."""
        return entity.to_dict()

    async def _update_projection(self, model: Milestone, is_create: bool) -> None:
        """
        Update the milestones projection table.

        Args:
            model: Milestone to update
            is_create: Whether this is a create operation
        """
        data = self._row_from_model(model)

        # Upsert milestone
        await self.db.execute(
            f"""
            INSERT INTO {self.table_name} (
                id, project_id, name, description, due_date, status,
                sort_order, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                due_date = excluded.due_date,
                status = excluded.status,
                sort_order = excluded.sort_order,
                updated_at = excluded.updated_at
            """,
            (
                data["id"],
                data["project_id"],
                data["name"],
                data.get("description"),
                data.get("due_date"),
                data["status"],
                data["sort_order"],
                data["created_at"],
                data["updated_at"],
            ),
        )
