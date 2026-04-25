"""Objective repository with event sourcing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import GoalStatus, Objective
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class ObjectiveRepository(EventSourcedRepository[Objective]):
    """Repository for Objective entities with full event sourcing."""

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
        return "objective"

    @property
    def table_name(self) -> str:
        return "objectives"

    def _model_from_row(self, row: dict[str, Any]) -> Objective:
        """Convert database row to Objective."""
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

        return Objective(
            id=row["id"],
            goal_id=row["goal_id"],
            name=row["name"],
            description=row.get("description"),
            status=GoalStatus(row["status"]),
            target_date=target_date,
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
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

    def _row_from_model(self, model: Objective) -> dict[str, Any]:
        """Convert Objective to database row."""
        return {
            "id": model.id,
            "goal_id": model.goal_id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "target_date": model.target_date.isoformat()
            if model.target_date and hasattr(model.target_date, "isoformat")
            else model.target_date,
            "owner": model.owner,
            "owner_id": model.owner_id,
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
        goal_id: str,
        name: str,
        description: str | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
        message: str | None = None,
    ) -> Objective:
        """Create a new objective."""
        objective = Objective(
            goal_id=goal_id,
            name=name,
            description=description,
            target_date=target_date,
            owner=owner,
            owner_id=owner_id,
            tags=tuple(tags) if tags else (),
            progress_percent=progress_percent,
        )

        payload = {
            "goal_id": goal_id,
            "name": name,
            "description": description,
            "target_date": target_date.isoformat() if target_date else None,
            "owner": owner,
            "owner_id": owner_id,
            "tags": tags or [],
            "progress_percent": progress_percent,
        }

        return await self.save(
            objective,
            EventType.OBJECTIVE_CREATED,
            payload,
            message=message or f"Created objective '{name}'",
        )

    async def update(
        self,
        objective_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        target_date: datetime | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
        workflow_id: str | None = None,
        current_state: str | None = None,
        workflow_metadata: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> Objective | None:
        """Update an existing objective."""
        objective = await self.get_by_id(objective_id)
        if objective is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != objective.name:
            changes["name"] = (objective.name, name)
            objective.name = name
        if description is not None and description != objective.description:
            changes["description"] = (objective.description, description)
            objective.description = description
        if status is not None and status != objective.status:
            changes["status"] = (objective.status.value, status.value)
            objective.status = status
        if target_date is not None and target_date != objective.target_date:
            changes["target_date"] = (
                objective.target_date.isoformat() if objective.target_date else None,
                target_date.isoformat() if target_date else None,
            )
            objective.target_date = target_date
        if clear_owner:
            if objective.owner is not None or objective.owner_id is not None:
                changes["owner"] = (objective.owner, None)
                changes["owner_id"] = (objective.owner_id, None)
                objective.owner = None
                objective.owner_id = None
        elif owner is not None and (
            owner != objective.owner or owner_id != objective.owner_id
        ):
            changes["owner"] = (objective.owner, owner)
            changes["owner_id"] = (objective.owner_id, owner_id)
            objective.owner = owner
            objective.owner_id = owner_id
        if tags is not None and tuple(tags) != objective.tags:
            changes["tags"] = (list(objective.tags), tags)
            objective.tags = tuple(tags)
        if (
            progress_percent is not None
            and progress_percent != objective.progress_percent
        ):
            changes["progress_percent"] = (
                objective.progress_percent,
                progress_percent,
            )
            objective.progress_percent = progress_percent
        if workflow_id is not None and workflow_id != objective.workflow_id:
            changes["workflow_id"] = (objective.workflow_id, workflow_id)
            objective.workflow_id = workflow_id
        if current_state is not None and current_state != objective.current_state:
            changes["current_state"] = (objective.current_state, current_state)
            objective.current_state = current_state
        if (
            workflow_metadata is not None
            and workflow_metadata != objective.workflow_metadata
        ):
            changes["workflow_metadata"] = (
                objective.workflow_metadata,
                workflow_metadata,
            )
            objective.workflow_metadata = workflow_metadata

        if not changes:
            return objective

        objective.touch()

        return await self.save(
            objective,
            EventType.OBJECTIVE_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self,
        objective_id: str,
        message: str | None = None,
    ) -> Objective | None:
        """Archive an objective."""
        objective = await self.get_by_id(objective_id)
        if objective is None:
            return None

        old_status = objective.status
        objective.archive()

        return await self.save(
            objective,
            EventType.OBJECTIVE_ARCHIVED,
            {"old_status": old_status.value, "new_status": objective.status.value},
            message=message or "Objective archived",
        )

    async def complete(
        self,
        objective_id: str,
        message: str | None = None,
    ) -> Objective | None:
        """Complete an objective."""
        objective = await self.get_by_id(objective_id)
        if objective is None:
            return None

        objective.complete()

        return await self.save(
            objective,
            EventType.OBJECTIVE_COMPLETED,
            {
                "status": objective.status.value,
                "progress_percent": objective.progress_percent,
            },
            message=message or "Objective completed",
        )

    async def get_by_goal(
        self,
        goal_id: str,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Objective]:
        """Get objectives for a goal."""
        conditions = ["goal_id = ?"]
        params: list[Any] = [goal_id]
        if not include_archived:
            conditions.append("status != ?")
            params.append(GoalStatus.ARCHIVED.value)
        where_sql = " AND ".join(conditions)

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM objectives WHERE {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        params.extend([limit, offset])
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM objectives
            WHERE {where_sql}
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            tuple(params),
        )

        return QueryResult(
            items=[self._model_from_row(row) for row in rows],
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def get_by_name(self, name: str) -> Objective | None:
        """Get objective by name."""
        row = await self.db.fetch_one(
            "SELECT * FROM objectives WHERE name = ?",
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
    ) -> QueryResult[Objective]:
        """Get objectives by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM objectives WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM objectives
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
        goal_id: str | None = None,
        status: GoalStatus | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Objective]:
        """List objectives with combined optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if goal_id is not None:
            conditions.append("goal_id = ?")
            params.append(goal_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        elif not include_archived:
            conditions.append("status != ?")
            params.append(GoalStatus.ARCHIVED.value)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM objectives {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM objectives
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

    async def search(
        self,
        query: str,
        status: GoalStatus | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[Objective]:
        """Search objectives by name, description, or tags."""
        sql = """
            SELECT * FROM objectives
            WHERE (name LIKE ? OR description LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        objectives = [self._model_from_row(row) for row in rows]

        if tags:
            objectives = [o for o in objectives if any(tag in o.tags for tag in tags)]

        return objectives

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Objective | None:
        """Rebuild objective state from events."""
        if not events:
            return None

        objective = None

        for event in events:
            match event.event_type:
                case EventType.OBJECTIVE_CREATED:
                    payload = event.payload
                    target_date_value = payload.get("target_date")
                    target_date = (
                        datetime.fromisoformat(target_date_value)
                        if isinstance(target_date_value, str)
                        else target_date_value
                    )
                    objective = Objective(
                        id=event.aggregate_id,
                        goal_id=payload.get("goal_id", ""),
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=GoalStatus.ACTIVE,
                        target_date=target_date,
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        tags=tuple(payload.get("tags", [])),
                        progress_percent=int(payload.get("progress_percent", 0) or 0),
                    )
                case EventType.OBJECTIVE_UPDATED if objective:
                    payload = event.payload
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                objective.name = new_val
                            case "description":
                                objective.description = new_val
                            case "status":
                                objective.status = GoalStatus(new_val)
                            case "target_date":
                                if isinstance(new_val, str):
                                    objective.target_date = datetime.fromisoformat(
                                        new_val
                                    )
                                else:
                                    objective.target_date = new_val
                            case "owner":
                                objective.owner = new_val
                            case "owner_id":
                                objective.owner_id = new_val
                            case "tags":
                                objective.tags = tuple(new_val)
                            case "progress_percent":
                                objective.progress_percent = int(new_val)
                            case "workflow_id":
                                objective.workflow_id = new_val
                            case "current_state":
                                objective.current_state = new_val
                            case "workflow_metadata":
                                objective.workflow_metadata = new_val
                            case _:
                                pass
                case EventType.OBJECTIVE_COMPLETED if objective:
                    objective.status = GoalStatus.COMPLETED
                    objective.progress_percent = 100
                case EventType.OBJECTIVE_ARCHIVED if objective:
                    objective.status = GoalStatus.ARCHIVED

        return objective
