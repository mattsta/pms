"""Key result repository with event sourcing."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventType
from pms.models import GoalStatus, KeyResult
from pms.repositories.base import EventSourcedRepository, QueryResult
from pms.repositories.state_transition_repository import StateTransitionRepository

if TYPE_CHECKING:
    from pms.core.events import EventStore
    from pms.core.metrics import MetricsCollector
    from pms.core.revisions import RevisionStore
    from pms.db.connection import Database


class KeyResultRepository(EventSourcedRepository[KeyResult]):
    """Repository for KeyResult entities with full event sourcing."""

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
        return "key_result"

    @property
    def table_name(self) -> str:
        return "key_results"

    def _model_from_row(self, row: dict[str, Any]) -> KeyResult:
        """Convert database row to KeyResult."""
        tags_raw = row.get("tags", "[]")
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw

        return KeyResult(
            id=row["id"],
            objective_id=row["objective_id"],
            name=row["name"],
            description=row.get("description"),
            status=GoalStatus(row["status"]),
            current_value=row.get("current_value"),
            target_value=row.get("target_value"),
            unit=row.get("unit"),
            owner=row.get("owner"),
            owner_id=row.get("owner_id"),
            tags=tuple(tags),
            progress_percent=int(row.get("progress_percent", 0) or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _row_from_model(self, model: KeyResult) -> dict[str, Any]:
        """Convert KeyResult to database row."""
        return {
            "id": model.id,
            "objective_id": model.objective_id,
            "name": model.name,
            "description": model.description,
            "status": model.status.value,
            "current_value": model.current_value,
            "target_value": model.target_value,
            "unit": model.unit,
            "owner": model.owner,
            "owner_id": model.owner_id,
            "tags": json.dumps(list(model.tags)),
            "progress_percent": model.progress_percent,
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

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

    def _merge_activity(
        self,
        activity: dict[str, datetime | None],
        key_result_id: str,
        candidate: datetime | None,
    ) -> None:
        """Keep the freshest activity timestamp for one key result."""
        if candidate is None:
            return
        current = activity.get(key_result_id)
        if current is None or candidate > current:
            activity[key_result_id] = candidate

    async def get_last_activity_map(
        self,
        key_result_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return bubbled activity timestamps keyed by key result id."""
        if not key_result_ids:
            return {}

        unique_ids = list(dict.fromkeys(key_result_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        params = tuple(unique_ids)
        activity: dict[str, datetime | None] = {
            key_result_id: None for key_result_id in unique_ids
        }

        rows = await self.db.fetch_all(
            f"""
            SELECT id, updated_at
            FROM key_results
            WHERE id IN ({placeholders})
            """,
            params,
        )
        for row in rows:
            self._merge_activity(
                activity,
                row["id"],
                self._parse_timestamp(row.get("updated_at")),
            )

        custom_field_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as key_result_id, MAX(created_at) as ts
            FROM custom_field_values
            WHERE entity_type = 'key_result' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        for row in custom_field_rows:
            self._merge_activity(
                activity,
                row["key_result_id"],
                self._parse_timestamp(row.get("ts")),
            )

        comment_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as key_result_id, MAX(updated_at) as ts
            FROM comments
            WHERE entity_type = 'key_result' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        for row in comment_rows:
            self._merge_activity(
                activity,
                row["key_result_id"],
                self._parse_timestamp(row.get("ts")),
            )

        label_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as key_result_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM label_assignments
            WHERE entity_type = 'key_result' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        for row in label_rows:
            self._merge_activity(
                activity,
                row["key_result_id"],
                self._parse_timestamp(row.get("ts")),
            )

        watcher_rows = await self.db.fetch_all(
            f"""
            SELECT entity_id as key_result_id,
                   MAX(COALESCE(archived_at, updated_at, created_at)) as ts
            FROM entity_watchers
            WHERE entity_type = 'key_result' AND entity_id IN ({placeholders})
            GROUP BY entity_id
            """,
            params,
        )
        for row in watcher_rows:
            self._merge_activity(
                activity,
                row["key_result_id"],
                self._parse_timestamp(row.get("ts")),
            )

        transition_map = await self.get_last_transition_map(unique_ids)
        for key_result_id, transition_ts in transition_map.items():
            self._merge_activity(activity, key_result_id, transition_ts)

        return activity

    async def get_last_transition_map(
        self,
        key_result_ids: list[str],
    ) -> dict[str, datetime | None]:
        """Return the most recent lifecycle transition per key result."""
        if not key_result_ids:
            return {}

        unique_ids = list(dict.fromkeys(key_result_ids))
        state_repo = StateTransitionRepository(self.db)
        return await state_repo.get_last_transition_map(
            "key_result_status",
            unique_ids,
        )

    async def create(
        self,
        objective_id: str,
        name: str,
        description: str | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        tags: list[str] | None = None,
        progress_percent: int = 0,
        message: str | None = None,
    ) -> KeyResult:
        """Create a new key result."""
        key_result = KeyResult(
            objective_id=objective_id,
            name=name,
            description=description,
            current_value=current_value,
            target_value=target_value,
            unit=unit,
            owner=owner,
            owner_id=owner_id,
            tags=tuple(tags) if tags else (),
            progress_percent=progress_percent,
        )

        payload = {
            "objective_id": objective_id,
            "name": name,
            "description": description,
            "current_value": current_value,
            "target_value": target_value,
            "unit": unit,
            "owner": owner,
            "owner_id": owner_id,
            "tags": tags or [],
            "progress_percent": progress_percent,
        }

        return await self.save(
            key_result,
            EventType.KEY_RESULT_CREATED,
            payload,
            message=message or f"Created key result '{name}'",
        )

    async def update(
        self,
        key_result_id: str,
        name: str | None = None,
        description: str | None = None,
        status: GoalStatus | None = None,
        current_value: float | None = None,
        target_value: float | None = None,
        unit: str | None = None,
        owner: str | None = None,
        owner_id: str | None = None,
        clear_owner: bool = False,
        tags: list[str] | None = None,
        progress_percent: int | None = None,
        message: str | None = None,
    ) -> KeyResult | None:
        """Update an existing key result."""
        key_result = await self.get_by_id(key_result_id)
        if key_result is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != key_result.name:
            changes["name"] = (key_result.name, name)
            key_result.name = name
        if description is not None and description != key_result.description:
            changes["description"] = (key_result.description, description)
            key_result.description = description
        if status is not None and status != key_result.status:
            changes["status"] = (key_result.status.value, status.value)
            key_result.status = status
        if current_value is not None and current_value != key_result.current_value:
            changes["current_value"] = (key_result.current_value, current_value)
            key_result.current_value = current_value
        if target_value is not None and target_value != key_result.target_value:
            changes["target_value"] = (key_result.target_value, target_value)
            key_result.target_value = target_value
        if unit is not None and unit != key_result.unit:
            changes["unit"] = (key_result.unit, unit)
            key_result.unit = unit
        if clear_owner:
            if key_result.owner is not None or key_result.owner_id is not None:
                changes["owner"] = (key_result.owner, None)
                changes["owner_id"] = (key_result.owner_id, None)
                key_result.owner = None
                key_result.owner_id = None
        elif owner is not None and (
            owner != key_result.owner or owner_id != key_result.owner_id
        ):
            changes["owner"] = (key_result.owner, owner)
            changes["owner_id"] = (key_result.owner_id, owner_id)
            key_result.owner = owner
            key_result.owner_id = owner_id
        if tags is not None and tuple(tags) != key_result.tags:
            changes["tags"] = (list(key_result.tags), tags)
            key_result.tags = tuple(tags)
        if (
            progress_percent is not None
            and progress_percent != key_result.progress_percent
        ):
            changes["progress_percent"] = (
                key_result.progress_percent,
                progress_percent,
            )
            key_result.progress_percent = progress_percent

        if not changes:
            return key_result

        key_result.touch()

        return await self.save(
            key_result,
            EventType.KEY_RESULT_UPDATED,
            {"changes": changes},
            message=message,
        )

    async def archive(
        self,
        key_result_id: str,
        message: str | None = None,
    ) -> KeyResult | None:
        """Archive a key result."""
        key_result = await self.get_by_id(key_result_id)
        if key_result is None:
            return None

        old_status = key_result.status
        key_result.archive()

        return await self.save(
            key_result,
            EventType.KEY_RESULT_ARCHIVED,
            {"old_status": old_status.value, "new_status": key_result.status.value},
            message=message or "Key result archived",
        )

    async def complete(
        self,
        key_result_id: str,
        message: str | None = None,
    ) -> KeyResult | None:
        """Complete a key result."""
        key_result = await self.get_by_id(key_result_id)
        if key_result is None:
            return None

        key_result.complete()

        return await self.save(
            key_result,
            EventType.KEY_RESULT_COMPLETED,
            {
                "status": key_result.status.value,
                "progress_percent": key_result.progress_percent,
            },
            message=message or "Key result completed",
        )

    async def get_by_objective(
        self,
        objective_id: str,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[KeyResult]:
        """Get key results for an objective."""
        conditions = ["objective_id = ?"]
        params: list[Any] = [objective_id]
        if not include_archived:
            conditions.append("status != ?")
            params.append(GoalStatus.ARCHIVED.value)
        where_sql = " AND ".join(conditions)

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM key_results WHERE {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        params.extend([limit, offset])
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM key_results
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

    async def get_by_status(
        self,
        status: GoalStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[KeyResult]:
        """Get key results by status."""
        count_result = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM key_results WHERE status = ?",
            (status.value,),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            """
            SELECT * FROM key_results
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
        objective_id: str | None = None,
        status: GoalStatus | None = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[KeyResult]:
        """List key results with combined optional filters."""
        conditions: list[str] = []
        params: list[Any] = []

        if objective_id is not None:
            conditions.append("objective_id = ?")
            params.append(objective_id)
        if status is not None:
            conditions.append("status = ?")
            params.append(status.value)
        elif not include_archived:
            conditions.append("status != ?")
            params.append(GoalStatus.ARCHIVED.value)

        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        count_result = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM key_results {where_sql}",
            tuple(params),
        )
        total = count_result["count"] if count_result else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM key_results
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
    ) -> list[KeyResult]:
        """Search key results by name, description, or tags."""
        sql = """
            SELECT * FROM key_results
            WHERE (name LIKE ? OR description LIKE ?)
        """
        params: list[Any] = [f"%{query}%", f"%{query}%"]

        if status:
            sql += " AND status = ?"
            params.append(status.value)

        sql += " ORDER BY updated_at DESC LIMIT ?"
        params.append(limit)

        rows = await self.db.fetch_all(sql, tuple(params))
        key_results = [self._model_from_row(row) for row in rows]

        if tags:
            key_results = [k for k in key_results if any(tag in k.tags for tag in tags)]

        return key_results

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> KeyResult | None:
        """Rebuild key result state from events."""
        if not events:
            return None

        key_result = None

        for event in events:
            match event.event_type:
                case EventType.KEY_RESULT_CREATED:
                    payload = event.payload
                    key_result = KeyResult(
                        id=event.aggregate_id,
                        objective_id=payload.get("objective_id", ""),
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        status=GoalStatus.ACTIVE,
                        current_value=payload.get("current_value"),
                        target_value=payload.get("target_value"),
                        unit=payload.get("unit"),
                        owner=payload.get("owner"),
                        owner_id=payload.get("owner_id"),
                        tags=tuple(payload.get("tags", [])),
                        progress_percent=int(payload.get("progress_percent", 0) or 0),
                    )
                case EventType.KEY_RESULT_UPDATED if key_result:
                    payload = event.payload
                    changes = payload.get("changes", {})
                    for field, (_, new_val) in changes.items():
                        match field:
                            case "name":
                                key_result.name = new_val
                            case "description":
                                key_result.description = new_val
                            case "status":
                                key_result.status = GoalStatus(new_val)
                            case "current_value":
                                key_result.current_value = new_val
                            case "target_value":
                                key_result.target_value = new_val
                            case "unit":
                                key_result.unit = new_val
                            case "owner":
                                key_result.owner = new_val
                            case "owner_id":
                                key_result.owner_id = new_val
                            case "tags":
                                key_result.tags = tuple(new_val)
                            case "progress_percent":
                                key_result.progress_percent = int(new_val)
                            case _:
                                pass
                case EventType.KEY_RESULT_COMPLETED if key_result:
                    key_result.status = GoalStatus.COMPLETED
                    key_result.progress_percent = 100
                case EventType.KEY_RESULT_ARCHIVED if key_result:
                    key_result.status = GoalStatus.ARCHIVED

        return key_result
