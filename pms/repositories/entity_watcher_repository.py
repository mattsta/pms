"""Repository for entity watchers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import Change, ChangeType, Revision, RevisionStore
from pms.models.comment import EntityWatcher
from pms.repositories.base import EventSourcedRepository, QueryResult

if TYPE_CHECKING:
    from pms.db.connection import Database


class EntityWatcherRepository(EventSourcedRepository[EntityWatcher]):
    """Repository for entity watcher subscriptions."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "entity_watcher"

    @property
    def table_name(self) -> str:
        return "entity_watchers"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def add(
        self,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> EntityWatcher:
        async def _add() -> EntityWatcher:
            return await self._add_in_transaction(
                entity_type=entity_type,
                entity_id=entity_id,
                watcher=watcher,
            )

        return await self._run_in_owned_transaction(
            _add,
            operation_name="add",
        )

    async def _add_in_transaction(
        self,
        *,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> EntityWatcher:
        """Add a watcher assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_add_in_transaction")
        existing = await self.get_by_entity(entity_type, entity_id, watcher)
        if existing:
            return existing
        model = EntityWatcher(
            entity_type=entity_type,
            entity_id=entity_id,
            watcher=watcher,
        )
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "watcher": watcher,
        }
        return await self._save_in_transaction(
            model=model,
            event_type=EventType.WATCHER_ADDED,
            payload=payload,
            message="Added watcher",
        )

    async def get_by_entity(
        self, entity_type: str, entity_id: str, watcher: str
    ) -> EntityWatcher | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM entity_watchers
            WHERE entity_type = ? AND entity_id = ? AND watcher = ?
              AND archived_at IS NULL
            """,
            (entity_type, entity_id, watcher),
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
    ) -> QueryResult[EntityWatcher]:
        where_sql = "entity_type = ? AND entity_id = ?"
        params: list[Any] = [entity_type, entity_id]
        if not include_archived:
            where_sql += " AND archived_at IS NULL"

        count_row = await self.db.fetch_one(
            f"SELECT COUNT(*) as count FROM entity_watchers WHERE {where_sql}",
            tuple(params),
        )
        total = count_row["count"] if count_row else 0
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM entity_watchers
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (*params, limit, offset),
        )
        items = [self._row_to_model(row) for row in rows]
        return QueryResult(items=items, total_count=total, offset=offset, limit=limit)

    async def remove(self, entity_type: str, entity_id: str, watcher: str) -> bool:
        async def _remove() -> bool:
            return await self._remove_in_transaction(
                entity_type=entity_type,
                entity_id=entity_id,
                watcher=watcher,
            )

        return await self._run_in_owned_transaction(
            _remove,
            operation_name="remove",
        )

    async def _remove_in_transaction(
        self,
        *,
        entity_type: str,
        entity_id: str,
        watcher: str,
    ) -> bool:
        """Remove a watcher assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_remove_in_transaction")
        existing = await self.get_by_entity(entity_type, entity_id, watcher)
        if existing is None:
            return False

        event = DomainEvent(
            event_type=EventType.WATCHER_REMOVED,
            aggregate_type=self.entity_type,
            aggregate_id=existing.id,
            payload={
                "entity_type": existing.entity_type,
                "entity_id": existing.entity_id,
                "watcher": existing.watcher,
            },
            metadata=self._context.to_metadata(),
        )
        await self.events.append(event)

        archived_at = datetime.now(UTC)
        prev_revision = await self.revisions.get_revision(self.entity_type, existing.id)
        if prev_revision:
            revision = Revision(
                revision_id=str(uuid4()),
                entity_type=self.entity_type,
                entity_id=existing.id,
                revision_number=prev_revision.revision_number + 1,
                parent_revision_id=prev_revision.revision_id,
                content={
                    "deleted": True,
                    "archived_at": archived_at.isoformat(),
                    "previous": prev_revision.content,
                },
                content_hash="",
                changes=(
                    Change(
                        field_name=self.archive_column or "archived_at",
                        old_value=None,
                        new_value=archived_at.isoformat(),
                        change_type=ChangeType.DELETE,
                    ),
                ),
                change_type=ChangeType.DELETE,
                created_at=archived_at,
                created_by=self._context.user_id,
                message="Removed watcher",
            )
            await self.revisions.save_revision(revision)

        await self.db.execute(
            """
            UPDATE entity_watchers
            SET archived_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (archived_at.isoformat(), archived_at.isoformat(), existing.id),
        )
        return True

    async def restore(
        self,
        entity_id: str,
        message: str | None = None,
    ) -> EntityWatcher | None:
        async def _restore() -> EntityWatcher | None:
            return await self._restore_in_transaction(
                entity_id=entity_id,
                message=message,
            )

        return await self._run_in_owned_transaction(
            _restore,
            operation_name="restore",
        )

    async def _restore_in_transaction(
        self,
        *,
        entity_id: str,
        message: str | None = None,
    ) -> EntityWatcher | None:
        """Restore a watcher assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_restore_in_transaction")
        row = await self.db.fetch_one(
            "SELECT * FROM entity_watchers WHERE id = ?",
            (entity_id,),
        )
        if row is None:
            return None

        archived_value = row.get(self.archive_column)
        if archived_value is None:
            return self._model_from_row(row)

        model = self._model_from_row(row)
        event = DomainEvent(
            event_type=EventType.WATCHER_RESTORED,
            aggregate_type=self.entity_type,
            aggregate_id=entity_id,
            payload={
                "entity_type": model.entity_type,
                "entity_id": model.entity_id,
                "watcher": model.watcher,
            },
            metadata=self._context.to_metadata(),
        )
        await self.events.append(event)

        restored_at = datetime.now(UTC)
        prev_revision = await self.revisions.get_revision(self.entity_type, entity_id)
        if prev_revision:
            revision = Revision(
                revision_id=str(uuid4()),
                entity_type=self.entity_type,
                entity_id=entity_id,
                revision_number=prev_revision.revision_number + 1,
                parent_revision_id=prev_revision.revision_id,
                content={
                    "restored": True,
                    "restored_at": restored_at.isoformat(),
                    "previous": prev_revision.content,
                },
                content_hash="",
                changes=(
                    Change(
                        field_name=self.archive_column or "archived_at",
                        old_value=str(archived_value),
                        new_value=None,
                        change_type=ChangeType.RESTORE,
                    ),
                ),
                change_type=ChangeType.RESTORE,
                created_at=restored_at,
                created_by=self._context.user_id,
                message=message or "Restored watcher",
            )
            await self.revisions.save_revision(revision)

        await self.db.execute(
            """
            UPDATE entity_watchers
            SET archived_at = NULL, updated_at = ?
            WHERE id = ?
            """,
            (restored_at.isoformat(), entity_id),
        )

        row = await self.db.fetch_one(
            "SELECT * FROM entity_watchers WHERE id = ?",
            (entity_id,),
        )
        return self._model_from_row(row) if row else model

    def _row_to_model(self, row: dict[str, Any]) -> EntityWatcher:
        return EntityWatcher(
            id=row["id"],
            entity_type=row["entity_type"],
            entity_id=row["entity_id"],
            watcher=row["watcher"],
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> EntityWatcher:
        return self._row_to_model(row)

    def _row_from_model(self, model: EntityWatcher) -> dict[str, Any]:
        return {
            "id": model.id,
            "entity_type": model.entity_type,
            "entity_id": model.entity_id,
            "watcher": model.watcher,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> EntityWatcher | None:
        if not events:
            return None

        watcher: EntityWatcher | None = None
        for event in events:
            match event.event_type:
                case EventType.WATCHER_ADDED:
                    payload = event.payload
                    watcher = EntityWatcher(
                        id=event.aggregate_id,
                        entity_type=payload.get("entity_type", ""),
                        entity_id=payload.get("entity_id", ""),
                        watcher=payload.get("watcher", ""),
                    )
                case EventType.WATCHER_REMOVED if watcher:
                    watcher.archived_at = event.metadata.timestamp
                case EventType.WATCHER_RESTORED if watcher:
                    watcher.archived_at = None

        if watcher:
            watcher.last_event_sequence = events[-1].sequence_number
        return watcher


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
