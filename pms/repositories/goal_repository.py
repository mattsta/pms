"""Goal repository with event sourcing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import Goal, GoalHorizon, GoalStatus
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class GoalRepository(EventSourcedRepository[Goal]):
    """Repository for Goal entities with full event sourcing."""

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
        return "goal"

    @property
    def table_name(self) -> str:
        return "goals"

    def _model_from_row(self, row: dict[str, Any]) -> Goal:
        """Convert database row to Goal."""
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        target_date = None
        if row.get("target_date"):
            target_date = (
                datetime.fromisoformat(row["target_date"])
                if isinstance(row["target_date"], str)
                else row["target_date"]
            )

        workflow_metadata_raw = row.get("workflow_metadata", "{}")
        workflow_metadata = (
            json.loads(workflow_metadata_raw)
            if isinstance(workflow_metadata_raw, str)
            else workflow_metadata_raw
        )

        return Goal(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            status=GoalStatus(row["status"]),
            horizon=GoalHorizon(row["horizon"]),
            target_date=target_date,
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            product_id=row.get("product_id"),
            project_id=row.get("project_id"),
            tags=tuple(tags),
            progress_percent=int(row.get("progress_percent", 0) or 0),
            workflow_id=row.get("workflow_id"),
            current_state=row.get("current_state"),
            workflow_metadata=workflow_metadata or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: Goal) -> dict[str, Any]:
        """Convert Goal to database row."""
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "horizon": model.horizon.value,
            "target_date": model.target_date.isoformat()
            if model.target_date and hasattr(model.target_date, "isoformat")
            else model.target_date,
            "owner": model.owner,
            "owner_id": model.owner_id,
            "product_id": model.product_id,
            "project_id": model.project_id,
            "tags": json.dumps(list(model.tags)),
            "progress_percent": model.progress_percent,
            "workflow_id": model.workflow_id,
            "current_state": model.current_state,
            "workflow_metadata": json.dumps(model.workflow_metadata or {}),
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
        horizon: GoalHorizon = GoalHorizon.SHORT_TERM,
        target_date: datetime | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
        message: str | None = None,
    ) -> Goal:
        """Create a new goal."""
        goal = Goal(
            name=name,
            description=description,
            horizon=horizon,
            target_date=target_date,
            owner=owner,
            owner_id=owner_id,
            product_id=product_id,
            project_id=project_id,
            tags=tuple(tags) if tags else (),
            progress_percent=progress_percent,
        )

        payload = {
            "name": name,
            "description": description,
            "horizon": horizon.value,
            "target_date": target_date.isoformat() if target_date else None,
            "owner": owner,
            "owner_id": owner_id,
            "product_id": product_id,
            "project_id": project_id,
            "tags": tags or [],
            "progress_percent": progress_percent,
        }

        return await self.save(
            goal,
            EventType.GOAL_CREATED,
            payload,
            message=message or f"Created goal '{name}'",
        )

    async def update(
        self,
        goal_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        product_id: str | None = None,
        project_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
        workflow_id: str | None = None,
        current_state: str | None = None,
        workflow_metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> Goal | None:
        """Update an existing goal."""
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != goal.name:
            changes["name"] = (goal.name, name)
            goal.name = name
        if description is not None and description != goal.description:
            changes["description"] = (goal.description, description)
            goal.description = description
        if status is not None and status != goal.status:
            changes["status"] = (goal.status.value, status.value)
            goal.status = status
        if horizon is not None and horizon != goal.horizon:
            changes["horizon"] = (goal.horizon.value, horizon.value)
            goal.horizon = horizon
        if target_date is not None and target_date != goal.target_date:
            changes["target_date"] = (
                goal.target_date.isoformat() if goal.target_date else None,
                target_date.isoformat() if target_date else None,
            )
            goal.target_date = target_date
        if clear_owner:
            if goal.owner is not None or goal.owner_id is not None:
                changes["owner"] = (goal.owner, None)
                changes["owner_id"] = (goal.owner_id, None)
                goal.owner = None
                goal.owner_id = None
        elif owner is not None and (owner != goal.owner or owner_id != goal.owner_id):
            changes["owner"] = (goal.owner, owner)
            changes["owner_id"] = (goal.owner_id, owner_id)
            goal.owner = owner
            goal.owner_id = owner_id
        if product_id is not None and product_id != goal.product_id:
            changes["product_id"] = (goal.product_id, product_id)
            goal.product_id = product_id
        if project_id is not None and project_id != goal.project_id:
            changes["project_id"] = (goal.project_id, project_id)
            goal.project_id = project_id
        if tags is not None and tuple(tags) != goal.tags:
            changes["tags"] = (list(goal.tags), tags)
            goal.tags = tuple(tags)
        if progress_percent is not None and progress_percent != goal.progress_percent:
            changes["progress_percent"] = (goal.progress_percent, progress_percent)
            goal.progress_percent = progress_percent
        if workflow_id is not None and workflow_id != goal.workflow_id:
            changes["workflow_id"] = (goal.workflow_id, workflow_id)
            goal.workflow_id = workflow_id
        if current_state is not None and current_state != goal.current_state:
            changes["current_state"] = (goal.current_state, current_state)
            goal.current_state = current_state
        if (
            workflow_metadata is not None
            and workflow_metadata != goal.workflow_metadata
        ):
            changes["workflow_metadata"] = (
                goal.workflow_metadata,
                workflow_metadata,
            )
            goal.workflow_metadata = workflow_metadata

        if not changes:
            return goal

        goal.touch()

        return await self.save(
            goal,
            EventType.GOAL_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self,
        goal_id: str,
        message: str | None = None,
    ) -> Goal | None:
        """Archive a goal."""
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None

        old_status = goal.status
        goal.archive()

        return await self.save(
            goal,
            EventType.GOAL_ARCHIVED,
            {"old_status": old_status.value, "new_status": goal.status.value},
            message=message or "Goal archived",
        )

    async def complete(
        self,
        goal_id: str,
        message: str | None = None,
    ) -> Goal | None:
        """Complete a goal."""
        goal = await self.get_by_id(goal_id)
        if goal is None:
            return None

        goal.complete()

        return await self.save(
            goal,
            EventType.GOAL_COMPLETED,
            {"status": goal.status.value, "progress_percent": goal.progress_percent},
            message=message or "Goal completed",
        )

    async def get_by_name(self, name: str) -> Goal | None:
        """Get goal by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM goals WHERE name = ?",
            (name,),
        )
        if row is None:
            return None
        return self._model_from_row(row)

    async def get_by_status(
        self,
        status: GoalStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """Get goals by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM goals WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM goals
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

    async def list_filtered(
        self,
        *,
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        product_id: str | None = None,
        project_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """List goals with combined optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        if horizon is not None:
            conditions.append("horizon = ?")
            params.append(horizon.value)
        if product_id is not None:
            conditions.append("product_id = ?")
            params.append(product_id)
        if project_id is not None:
            conditions.append("project_id = ?")
            params.append(project_id)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM goals {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM goals
            {where_sql}
            ORDER BY updated_at DESC
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

    async def get_by_horizon(
        self,
        horizon: GoalHorizon,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """Get goals by horizon."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM goals WHERE horizon = ?",
            (horizon.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM goals
            WHERE horizon = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (horizon.value, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_by_product(
        self,
        product_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """Get goals for a specific product."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM goals WHERE product_id = ?",
            (product_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM goals
            WHERE product_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (product_id, limit, offset),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_by_project(
        self,
        project_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Goal]:
        """Get goals for a specific project."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM goals WHERE project_id = ?",
            (project_id,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM goals
            WHERE project_id = ?
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (project_id, limit, offset),
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
        status: GoalStatus | None = None,
        horizon: GoalHorizon | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Goal]:
        """Search goals by name, description, or tags."""
        sql = """
            SELECT * FROM goals
            WHERE (name LIKE ? OR description LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        if horizon:
            sql += " AND horizon = ?"
            params.append(horizon.value)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        goals = [self._model_from_row(row) for row in rows]

        if tags:
            goals = [g for g in goals if any(tag in g.tags for tag in tags)]

        return goals

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Goal | None:
        """Rebuild goal state from events."""
        if not events:
            return None

        goal = None

        for event in events:
            match event.event_type:
                case EventType.GOAL_CREATED:
                    payload = event.payload
                    horizon_value = payload.get("horizon", GoalHorizon.SHORT_TERM.value)
                    target_date_value = payload.get("target_date")
                    target_date = (
                        datetime.fromisoformat(target_date_value)
                        if isinstance(target_date_value, str)
                        else target_date_value
                    )
                    goal = Goal(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=GoalStatus.ACTIVE,
                        horizon=GoalHorizon(horizon_value),
                        target_date=target_date,
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        product_id=payload.get("product_id"),
                        project_id=payload.get("project_id"),
                        tags=tuple(payload.get("tags", [])),
                        progress_percent=int(payload.get("progress_percent", 0) or 0),
                    )
                case EventType.GOAL_UPDATED if goal:
                    payload = event.payload
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                goal.name = new_val
                            case "description":
                                goal.description = new_val
                            case "status":
                                goal.status = GoalStatus(new_val)
                            case "horizon":
                                goal.horizon = GoalHorizon(new_val)
                            case "target_date":
                                if isinstance(new_val, str):
                                    goal.target_date = datetime.fromisoformat(new_val)
                                else:
                                    goal.target_date = new_val
                            case "owner":
                                goal.owner = new_val
                            case "owner_id":
                                goal.owner_id = new_val
                            case "product_id":
                                goal.product_id = new_val
                            case "project_id":
                                goal.project_id = new_val
                            case "tags":
                                goal.tags = tuple(new_val)
                            case "progress_percent":
                                goal.progress_percent = int(new_val)
                            case "workflow_id":
                                goal.workflow_id = new_val
                            case "current_state":
                                goal.current_state = new_val
                            case "workflow_metadata":
                                goal.workflow_metadata = new_val
                            case _:
                                pass
                case EventType.GOAL_COMPLETED if goal:
                    goal.status = GoalStatus.COMPLETED
                    goal.progress_percent = 100
                case EventType.GOAL_ARCHIVED if goal:
                    goal.status = GoalStatus.ARCHIVED

        return goal
