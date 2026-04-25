"""Project repository with event sourcing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import Project, ProjectStats, ProjectStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ProjectRepository(EventSourcedRepository[Project]):
    """Repository for Project entities with full event sourcing."""

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
        return "project"

    @property
    def table_name(self) -> str:
        return "projects"

    def _model_from_row(self, row: dict[str, Any]) -> Project:
        """Convert database row to Project."""
        tags_raw = row.get("tags", "[]")
        # Handle both JSON string (from DB) and already-decoded list (from revision content)
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
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

        return Project(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=ProjectStatus(row["status"]),
            tags=tuple(tags),
            org_id=row.get("org_id"),
            portfolio_id=row.get("portfolio_id"),
            program_id=row.get("program_id"),
            product_id=row.get("product_id"),
            workflow_id=row.get("workflow_id"),
            current_state=row.get("current_state"),
            workflow_metadata=workflow_metadata,
            created_at=created_at,
            updated_at=updated_at,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Project) -> dict[str, Any]:
        """Convert Project to database row."""
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "tags": json.dumps(list(model.tags)),
            "org_id": model.org_id,
            "portfolio_id": model.portfolio_id,
            "program_id": model.program_id,
            "product_id": model.product_id,
            "workflow_id": model.workflow_id,
            "current_state": model.current_state,
            "workflow_metadata": json.dumps(model.workflow_metadata),
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def create(
        self,
        name: str,
        description: str | None = None,
        tags: list[str] | None = None,
        org_id: str | None = None,
        portfolio_id: str | None = None,
        program_id: str | None = None,
        product_id: str | None = None,
        message: str | None = None,
    ) -> Project:
        """Create a new project."""
        project = Project(
            name=name,
            description=description,
            tags=tuple(tags) if tags else (),
            org_id=org_id,
            portfolio_id=portfolio_id,
            program_id=program_id,
            product_id=product_id,
        )

        payload = {
            "name": name,
            "description": description,
            "tags": tags or [],
            "org_id": org_id,
            "portfolio_id": portfolio_id,
            "program_id": program_id,
            "product_id": product_id,
        }

        return await self.save(
            project,
            EventType.PROJECT_CREATED,
            payload,
            message=message or f"Created project '{name}'",
        )

    async def update(
        self,
        project_id: str,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
        tags: list[str] | None = None,
        message: str | None = None,
    ) -> Project | None:
        """Update an existing project."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != project.name:
            changes["name"] = (project.name, name)
            project.name = name
        if description is not None and description != project.description:
            changes["description"] = (project.description, description)
            project.description = description
        if status is not None and status != project.status:
            changes["status"] = (project.status.value, status.value)
            project.status = status
        if tags is not None and tuple(tags) != project.tags:
            changes["tags"] = (list(project.tags), tags)
            project.tags = tuple(tags)

        if not changes:
            return project  # No changes

        project.touch()

        return await self.save(
            project,
            EventType.PROJECT_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self, project_id: str, message: str | None = None
    ) -> Project | None:
        """Archive a project."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_status = project.status
        project.archive()

        return await self.save(
            project,
            EventType.PROJECT_ARCHIVED,
            {"old_status": old_status.value, "new_status": project.status.value},
            message=message or "Project archived",
        )

    async def complete(
        self, project_id: str, message: str | None = None
    ) -> Project | None:
        """Mark a project as completed."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_status = project.status
        project.complete()

        return await self.save(
            project,
            EventType.PROJECT_UPDATED,
            {"changes": {"status": (old_status.value, project.status.value)}},
            message=message or "Project completed",
        )

    async def get_global_rollup(self) -> dict[str, int]:
        """Return project counts across the retained non-archived population."""
        row = await self.db.fetch_one(
            """
            SELECT COUNT(*) AS total_projects
            FROM projects
            WHERE status != 'archived'
            """
        )
        return {
            "total_projects": int(row["total_projects"] or 0) if row else 0,
        }

    async def reactivate(
        self, project_id: str, message: str | None = None
    ) -> Project | None:
        """Reactivate a completed project."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_status = project.status
        project.reactivate()

        return await self.save(
            project,
            EventType.PROJECT_UPDATED,
            {"changes": {"status": (old_status.value, project.status.value)}},
            message=message or "Project reactivated",
        )

    async def assign_to_product(
        self,
        project_id: str,
        product_id: str,
        message: str | None = None,
    ) -> Project | None:
        """Assign a project to a product."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_product_id = project.product_id
        project.product_id = product_id
        project.touch()

        return await self.save(
            project,
            EventType.PROJECT_ASSIGNED_TO_PRODUCT,
            {
                "old_product_id": old_product_id,
                "new_product_id": product_id,
            },
            message=message or f"Assigned to product {product_id}",
        )

    async def assign_to_org(
        self,
        project_id: str,
        org_id: str | None,
        message: str | None = None,
    ) -> Project | None:
        """Assign a project to an organization."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_org_id = project.org_id
        if old_org_id == org_id:
            return project

        project.org_id = org_id
        project.touch()

        return await self.save(
            project,
            EventType.PROJECT_ASSIGNED_TO_ORG,
            {
                "old_org_id": old_org_id,
                "new_org_id": org_id,
            },
            message=message or f"Assigned to org {org_id or '-'}",
        )

    async def assign_to_portfolio(
        self,
        project_id: str,
        portfolio_id: str | None,
        message: str | None = None,
    ) -> Project | None:
        """Assign a project to a portfolio."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_portfolio_id = project.portfolio_id
        if old_portfolio_id == portfolio_id:
            return project

        project.portfolio_id = portfolio_id
        project.touch()

        return await self.save(
            project,
            EventType.PROJECT_ASSIGNED_TO_PORTFOLIO,
            {
                "old_portfolio_id": old_portfolio_id,
                "new_portfolio_id": portfolio_id,
            },
            message=message or f"Assigned to portfolio {portfolio_id or '-'}",
        )

    async def assign_to_program(
        self,
        project_id: str,
        program_id: str | None,
        message: str | None = None,
    ) -> Project | None:
        """Assign a project to a program."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        old_program_id = project.program_id
        if old_program_id == program_id:
            return project

        project.program_id = program_id
        project.touch()

        return await self.save(
            project,
            EventType.PROJECT_ASSIGNED_TO_PROGRAM,
            {
                "old_program_id": old_program_id,
                "new_program_id": program_id,
            },
            message=message or f"Assigned to program {program_id or '-'}",
        )

    async def get_by_product(
        self,
        product_id: str,
        status: ProjectStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Project]:
        """Get projects for a specific product."""
        sql = "SELECT * FROM projects WHERE product_id = ?"
        params: list[Any] = [product_id]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        # Count query
        count_sql = sql.replace("SELECT *", "SELECT COUNT(*) as count")
        count_result = await self.db.fetch_one(count_sql, tuple(params))
        total = count_result["count"] if count_result else 0

        # Data query
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = await self.db.fetch_all(sql, tuple(params))

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_by_ids(self, project_ids: list[str]) -> list[Project]:
        """Fetch projects by ID list."""
        if not project_ids:
            return []
        placeholders = ", ".join("?" for _ in project_ids)
        rows = await self.db.fetch_all(
            f"SELECT * FROM projects WHERE id IN ({placeholders})",
            tuple(project_ids),
        )
        return [self._model_from_row(row) for row in rows]

    async def get_by_name(self, name: str) -> Project | None:
        """Get project by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM projects WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        return self._model_from_row(row)

    async def get_by_status(
        self,
        status: ProjectStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Project]:
        """Get projects by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM projects WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM projects
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (status.value, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def search(
        self,
        query: str,
        status: ProjectStatus | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Project]:
        """Search projects by name, description, or tags."""
        sql = """
            SELECT * FROM projects
            WHERE (name LIKE ? OR description LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        projects = [self._model_from_row(row) for row in rows]

        # Filter by tags if specified
        if tags:
            projects = [p for p in projects if any(tag in p.tags for tag in tags)]

        return projects

    async def get_stats(self, project_id: str) -> ProjectStats | None:
        """Get computed statistics for a project."""
        project = await self.get_by_id(project_id)
        if project is None:
            return None

        # Query task statistics with complexity tracking
        stats_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END) as completed_tasks,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked_tasks,
                SUM(COALESCE(complexity_points, 0)) as total_complexity_points,
                AVG(COALESCE(complexity_points, 0)) as avg_complexity_per_task,
                SUM(CASE WHEN due_date < datetime('now') AND status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END) as overdue_tasks
            FROM tasks
            WHERE project_id = ?
            """,
            (project_id,),
        )

        # Calculate total duration from state transitions
        duration_row = await self.db.fetch_one(
            """
            SELECT
                SUM(COALESCE(duration_in_state_seconds, 0)) / 3600.0 as total_duration_hours,
                AVG(COALESCE(duration_in_state_seconds, 0)) / 3600.0 as avg_duration_per_task
            FROM task_state_transitions tst
            INNER JOIN tasks t ON tst.task_id = t.id
            WHERE t.project_id = ?
            AND tst.from_state IN ('in_progress', 'in_review', 'blocked')
            """,
            (project_id,),
        )

        # Calculate efficiency score from state transitions
        efficiency_row = await self.db.fetch_one(
            """
            SELECT
                AVG(
                    CASE
                        WHEN total_duration > 0 AND complexity_points > 0
                        THEN CAST(complexity_points AS REAL) / total_duration
                        ELSE NULL
                    END
                ) as avg_efficiency_score
            FROM (
                SELECT
                    t.id,
                    t.complexity_points,
                    SUM(COALESCE(tst.duration_in_state_seconds, 0)) / 3600.0 as total_duration
                FROM tasks t
                LEFT JOIN task_state_transitions tst ON t.id = tst.task_id
                WHERE t.project_id = ?
                  AND t.status = 'done'
                  AND tst.from_state IN ('in_progress', 'in_review')
                GROUP BY t.id, t.complexity_points
            )
            """,
            (project_id,),
        )

        # Goal statistics
        goal_stats_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_goals,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_goals,
                AVG(COALESCE(progress_percent, 0)) as avg_goal_progress
            FROM goals
            WHERE project_id = ?
            """,
            (project_id,),
        )

        milestone_row = await self.db.fetch_one(
            """
            SELECT
                COUNT(*) as total_milestones,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_milestones
            FROM milestones
            WHERE project_id = ?
            """,
            (project_id,),
        )

        return ProjectStats(
            project_id=project_id,
            total_tasks=(stats_row["total_tasks"] if stats_row else 0) or 0,
            completed_tasks=(stats_row["completed_tasks"] if stats_row else 0) or 0,
            in_progress_tasks=(stats_row["in_progress_tasks"] if stats_row else 0) or 0,
            blocked_tasks=(stats_row["blocked_tasks"] if stats_row else 0) or 0,
            total_milestones=(milestone_row["total_milestones"] if milestone_row else 0)
            or 0,
            completed_milestones=(
                milestone_row["completed_milestones"] if milestone_row else 0
            )
            or 0,
            total_complexity_points=stats_row["total_complexity_points"]
            if stats_row and stats_row["total_complexity_points"] is not None
            else 0,
            avg_complexity_per_task=stats_row["avg_complexity_per_task"]
            if stats_row and stats_row["avg_complexity_per_task"] is not None
            else 0.0,
            total_duration_hours=duration_row["total_duration_hours"]
            if duration_row and duration_row["total_duration_hours"] is not None
            else 0.0,
            avg_duration_per_task=duration_row["avg_duration_per_task"]
            if duration_row and duration_row["avg_duration_per_task"] is not None
            else 0.0,
            avg_efficiency_score=efficiency_row["avg_efficiency_score"]
            if efficiency_row and efficiency_row["avg_efficiency_score"] is not None
            else 0.0,
            overdue_tasks=(stats_row["overdue_tasks"] if stats_row else 0) or 0,
            total_goals=(goal_stats_row["total_goals"] if goal_stats_row else 0) or 0,
            completed_goals=goal_stats_row["completed_goals"]
            if goal_stats_row and goal_stats_row["completed_goals"] is not None
            else 0,
            avg_goal_progress=goal_stats_row["avg_goal_progress"]
            if goal_stats_row and goal_stats_row["avg_goal_progress"] is not None
            else 0.0,
        )

    async def get_stats_bulk(self, project_ids: list[str]) -> dict[str, ProjectStats]:
        """Get computed statistics for multiple projects."""
        if not project_ids:
            return {}

        unique_ids = list(dict.fromkeys(project_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)

        stats_map = {
            project_id: ProjectStats(project_id=project_id) for project_id in unique_ids
        }

        task_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) as total_tasks,
                SUM(CASE WHEN status IN ('done', 'cancelled') THEN 1 ELSE 0 END) as completed_tasks,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress_tasks,
                SUM(CASE WHEN status = 'blocked' THEN 1 ELSE 0 END) as blocked_tasks,
                SUM(COALESCE(complexity_points, 0)) as total_complexity_points,
                AVG(COALESCE(complexity_points, 0)) as avg_complexity_per_task,
                SUM(CASE WHEN due_date < datetime('now') AND status NOT IN ('done', 'cancelled') THEN 1 ELSE 0 END) as overdue_tasks
            FROM tasks
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        for row in task_rows:
            stats = stats_map[row["project_id"]]
            stats.total_tasks = row["total_tasks"] or 0
            stats.completed_tasks = row["completed_tasks"] or 0
            stats.in_progress_tasks = row["in_progress_tasks"] or 0
            stats.blocked_tasks = row["blocked_tasks"] or 0
            stats.total_complexity_points = row["total_complexity_points"] or 0
            stats.avg_complexity_per_task = float(row["avg_complexity_per_task"] or 0.0)
            stats.overdue_tasks = row["overdue_tasks"] or 0

        duration_rows = await self.db.fetch_all(
            f"""
            SELECT
                t.project_id as project_id,
                SUM(COALESCE(tst.duration_in_state_seconds, 0)) / 3600.0 as total_duration_hours,
                AVG(COALESCE(tst.duration_in_state_seconds, 0)) / 3600.0 as avg_duration_per_task
            FROM task_state_transitions tst
            INNER JOIN tasks t ON tst.task_id = t.id
            WHERE t.project_id IN ({placeholders})
              AND tst.from_state IN ('in_progress', 'in_review', 'blocked')
            GROUP BY t.project_id
            """,
            params,
        )
        for row in duration_rows:
            stats = stats_map[row["project_id"]]
            stats.total_duration_hours = float(row["total_duration_hours"] or 0.0)
            stats.avg_duration_per_task = float(row["avg_duration_per_task"] or 0.0)

        efficiency_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                AVG(
                    CASE
                        WHEN total_duration > 0 AND complexity_points > 0
                        THEN CAST(complexity_points AS REAL) / total_duration
                        ELSE NULL
                    END
                ) as avg_efficiency_score
            FROM (
                SELECT
                    t.project_id as project_id,
                    t.complexity_points as complexity_points,
                    SUM(COALESCE(tst.duration_in_state_seconds, 0)) / 3600.0 as total_duration
                FROM tasks t
                LEFT JOIN task_state_transitions tst
                    ON t.id = tst.task_id
                    AND tst.from_state IN ('in_progress', 'in_review')
                WHERE t.project_id IN ({placeholders})
                  AND t.status = 'done'
                GROUP BY t.id, t.project_id, t.complexity_points
            )
            GROUP BY project_id
            """,
            params,
        )
        for row in efficiency_rows:
            stats = stats_map[row["project_id"]]
            stats.avg_efficiency_score = float(row["avg_efficiency_score"] or 0.0)

        goal_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) as total_goals,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_goals,
                AVG(COALESCE(progress_percent, 0)) as avg_goal_progress
            FROM goals
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        for row in goal_rows:
            stats = stats_map[row["project_id"]]
            stats.total_goals = row["total_goals"] or 0
            stats.completed_goals = row["completed_goals"] or 0
            stats.avg_goal_progress = float(row["avg_goal_progress"] or 0.0)

        milestone_rows = await self.db.fetch_all(
            f"""
            SELECT
                project_id,
                COUNT(*) as total_milestones,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_milestones
            FROM milestones
            WHERE project_id IN ({placeholders})
            GROUP BY project_id
            """,
            params,
        )
        for row in milestone_rows:
            stats = stats_map[row["project_id"]]
            stats.total_milestones = row["total_milestones"] or 0
            stats.completed_milestones = row["completed_milestones"] or 0

        return stats_map

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Project | None:
        """Rebuild project state from events."""
        if not events:
            return None

        project = None

        for event in events:
            match event.event_type:
                case EventType.PROJECT_CREATED:
                    p = event.payload
                    project = Project(
                        id=event.aggregate_id,
                        name=p.get("name", ""),
                        description=p.get("description"),
                        tags=tuple(p.get("tags", [])),
                        org_id=p.get("org_id"),
                        portfolio_id=p.get("portfolio_id"),
                        program_id=p.get("program_id"),
                        product_id=p.get("product_id"),
                    )
                case EventType.PROJECT_UPDATED if project:
                    p2 = event.payload
                    changes = p2.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                project.name = new_val
                            case "description":
                                project.description = new_val
                            case "status":
                                project.status = ProjectStatus(new_val)
                            case "tags":
                                project.tags = tuple(new_val)
                            case "product_id":
                                project.product_id = new_val
                            case "org_id":
                                project.org_id = new_val
                            case "portfolio_id":
                                project.portfolio_id = new_val
                            case "program_id":
                                project.program_id = new_val
                            case _:
                                pass
                case EventType.PROJECT_ARCHIVED if project:
                    project.status = ProjectStatus.ARCHIVED
                case EventType.PROJECT_ASSIGNED_TO_PRODUCT if project:
                    p3 = event.payload
                    project.product_id = p3.get("new_product_id", project.product_id)
                case EventType.PROJECT_ASSIGNED_TO_ORG if project:
                    p4 = event.payload
                    project.org_id = p4.get("new_org_id", project.org_id)
                case EventType.PROJECT_ASSIGNED_TO_PORTFOLIO if project:
                    p5 = event.payload
                    project.portfolio_id = p5.get(
                        "new_portfolio_id", project.portfolio_id
                    )
                case EventType.PROJECT_ASSIGNED_TO_PROGRAM if project:
                    p6 = event.payload
                    project.program_id = p6.get("new_program_id", project.program_id)

        return project
