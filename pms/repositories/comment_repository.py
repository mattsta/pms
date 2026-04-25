"""Repository for comments."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.comment import Comment
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


class CommentRepository(EventSourcedRepository[Comment]):
    """Repository for append-only comments."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "comment"

    @property
    def table_name(self) -> str:
        return "comments"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        entity_type: str,
        entity_id: str,
        body: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> Comment:
        comment = Comment(
            entity_type=entity_type,
            entity_id=entity_id,
            body=body,
            created_by=created_by,
            metadata=metadata or {},
        )
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "body": body,
            "created_by": created_by,
            "metadata": metadata or {},
        }
        return await self.save(
            comment,
            EventType.COMMENT_CREATED,
            payload,
            message="Created comment",
        )

    async def _create_in_transaction(
        self,
        *,
        entity_type: str,
        entity_id: str,
        body: str,
        created_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> Comment:
        """Create a comment assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_create_in_transaction")
        comment = Comment(
            entity_type=entity_type,
            entity_id=entity_id,
            body=body,
            created_by=created_by,
            metadata=metadata or {},
        )
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "body": body,
            "created_by": created_by,
            "metadata": metadata or {},
        }
        return await self._save_in_transaction(
            model=comment,
            event_type=EventType.COMMENT_CREATED,
            payload=payload,
            message="Created comment",
        )

    async def get_by_id(
        self, comment_id: str, *, include_archived: bool = False
    ) -> Comment | None:
        if include_archived:
            row = await self.db.fetch_one(
                "SELECT * FROM comments WHERE id = ?",
                (comment_id,),
            )
        else:
            row = await self.db.fetch_one(
                "SELECT * FROM comments WHERE id = ? AND archived_at IS NULL",
                (comment_id,),
            )
        return self._row_to_model(row) if row else None

    async def list_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        *,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> QueryResult[Comment]:
        where_sql = "entity_type = ? AND entity_id = ?"
        params: list[Any] = [entity_type, entity_id]
        if not include_archived:
            where_sql += " AND archived_at IS NULL"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM comments WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0

        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM comments
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        items = [self._row_to_model(row) for row in rows]
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    def _row_to_model(self, row: dict[str, Any]) -> Comment:
        metadata = {}
        if row.get("metadata"):
            try:
                metadata = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata = {}
        return Comment(
            id=row["id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            body=row["body"],
            created_by=row["created_by"],
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            metadata=metadata,
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> Comment:
        return self._row_to_model(row)

    def _row_from_model(self, model: Comment) -> dict[str, Any]:
        return {
            "id": model.id,
            "entity_type": model.entity_type,
            "entity_id": model.entity_id,
            "body": model.body,
            "created_by": model.created_by,
            "metadata": json.dumps(model.metadata),
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Comment | None:
        if not events:
            return None

        comment: Comment | None = None
        for event in events:
            match event.event_type:
                case EventType.COMMENT_CREATED:
                    payload = event.payload
                    comment = Comment(
                        id=event.aggregate_id,
                        entity_type=payload.get("entity_type", ""),
                        entity_id=payload.get("entity_id", ""),
                        body=payload.get("body", ""),
                        created_by=payload.get("created_by", ""),
                        metadata=payload.get("metadata") or {},
                    )
                case EventType.COMMENT_DELETED if comment:
                    comment.archived_at = event.metadata.timestamp
                case EventType.COMMENT_RESTORED if comment:
                    comment.archived_at = None

        if comment:
            comment.last_event_sequence = events[-1].sequence_number
        return comment


def _parse_datetime_required(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)


def _parse_datetime_optional(value: Any) -> datetime | None:
    if value is None:
        return None
    return _parse_datetime_required(value, "archived_at")
