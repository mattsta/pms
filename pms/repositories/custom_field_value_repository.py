"""Repository for custom field values (append-only)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.custom_field import CustomFieldValue
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


class CustomFieldValueRepository(EventSourcedRepository[CustomFieldValue]):
    """Repository for custom field values."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "custom_field_value"

    @property
    def table_name(self) -> str:
        return "custom_field_values"

    async def create(
        self,
        field_id: str,
        entity_type: str,
        entity_id: str,
        value: Any,
        created_by: str | None = None,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CustomFieldValue:
        field_value = CustomFieldValue(
            field_id=field_id,
            entity_type=entity_type,
            entity_id=entity_id,
            value=value,
            created_by=created_by,
            source=source,
            metadata=metadata or {},
        )
        payload = {
            "field_id": field_id,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "value": value,
            "created_by": created_by,
            "source": source,
            "metadata": metadata or {},
        }
        return await self.save(
            field_value,
            EventType.CUSTOM_FIELD_VALUE_SET,
            payload,
            message="Set custom field value",
        )

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        include_history: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[CustomFieldValue]:
        if include_history:
            count_row = await self.db.fetch_one(
                """
                SELECT COUNT(*) as count
                FROM custom_field_values
                WHERE entity_type = ? AND entity_id = ?
                """,
                (entity_type, entity_id),
            )
            total = count_row["count"] if count_row else 0
            rows = await self.db.fetch_all(
                """
                SELECT * FROM custom_field_values
                WHERE entity_type = ? AND entity_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (entity_type, entity_id, limit, offset),
            )
            items = [self._row_to_model(row) for row in rows]
            return QueryResult(
                items=items, total_count=total, offset=offset, limit=limit
            )

        rows = await self.db.fetch_all(
            """
            SELECT * FROM custom_field_values
            WHERE entity_type = ? AND entity_id = ?
            ORDER BY created_at DESC
            """,
            (entity_type, entity_id),
        )
        seen: set[str] = set()
        current_items: list[CustomFieldValue] = []
        for row in rows:
            field_id = row["field_id"]
            if field_id in seen:
                continue
            seen.add(field_id)
            current_items.append(self._row_to_model(row))

        total = len(current_items)
        if limit > 0:
            view_items = current_items[offset : offset + limit]
        else:
            view_items = current_items[offset:]
        return QueryResult(
            items=view_items,
            total_count=total,
            offset=offset,
            limit=limit,
        )

    async def list_for_field(
        self,
        field_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[CustomFieldValue]:
        count_row = await self.db.fetch_one(
            "SELECT COUNT(*) as count FROM custom_field_values WHERE field_id = ?",
            (field_id,),
        )
        total = count_row["count"] if count_row else 0
        rows = await self.db.fetch_all(
            """
            SELECT * FROM custom_field_values
            WHERE field_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (field_id, limit, offset),
        )
        items = [self._row_to_model(row) for row in rows]
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    def _row_to_model(self, row: dict[str, Any]) -> CustomFieldValue:
        value = None
        if row.get("value_json") is not None:
            try:
                value = json.loads(row["value_json"])
            except json.JSONDecodeError:
                value = row["value_json"]
        metadata = {}
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return CustomFieldValue(
            id=row["id"],
            field_id=row["field_id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            value=value,
            created_by=row.get("created_by"),
            source=row.get("source"),
            metadata=metadata,
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> CustomFieldValue:
        return self._row_to_model(row)

    def _row_from_model(self, model: CustomFieldValue) -> dict[str, Any]:
        return {
            "id": model.id,
            "field_id": model.field_id,
            "entity_type": model.entity_type,
            "entity_id": model.entity_id,
            "value_json": json.dumps(model.value),
            "created_by": model.created_by,
            "source": model.source,
            "metadata": json.dumps(model.metadata),
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> CustomFieldValue | None:
        if not events:
            return None

        value: CustomFieldValue | None = None
        for event in events:
            match event.event_type:
                case EventType.CUSTOM_FIELD_VALUE_SET:
                    payload = event.payload
                    value = CustomFieldValue(
                        id=event.aggregate_id,
                        field_id=payload.get("field_id", ""),
                        entity_type=payload.get("entity_type", ""),
                        entity_id=payload.get("entity_id", ""),
                        value=payload.get("value"),
                        created_by=payload.get("created_by"),
                        source=payload.get("source"),
                        metadata=payload.get("metadata") or {},
                    )

        if value:
            value.last_event_sequence = events[-1].sequence_number
        return value


def _parse_datetime_required(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)
