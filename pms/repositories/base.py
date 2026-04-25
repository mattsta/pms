"""Base repository with event-sourcing and revision tracking."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeVar

from pms.core.events import DomainEvent, EventMetadata, EventStore, EventType
from pms.core.metrics import MetricLabel, MetricsCollector
from pms.core.revisions import Change, ChangeType, Revision, RevisionStore, Snapshot
from pms.exceptions.base import DatabaseError
from pms.models.base import BaseModel
from pms.models.json_types import ModelObject
from pms.repositories.state_transition_repository import StateTransitionRepository

if TYPE_CHECKING:
    from pms.db.connection import Database

T = TypeVar("T", bound=BaseModel)
Q = TypeVar("Q")
R = TypeVar("R")


@dataclass
class QueryResult[Q]:
    """Result of a repository query with pagination info."""

    items: list[Q]
    total_count: int
    offset: int
    limit: int

    @property
    def has_more(self) -> bool:
        """Check if there are more items."""
        return self.offset + len(self.items) < self.total_count

    @property
    def page_count(self) -> int:
        """Calculate total pages."""
        if self.limit == 0:
            return 1
        return (self.total_count + self.limit - 1) // self.limit


@dataclass
class RepositoryContext:
    """Context for repository operations."""

    user_id: str | None = None
    session_id: str | None = None
    correlation_id: str | None = None

    def to_metadata(self) -> EventMetadata:
        """Create event metadata from context."""
        return EventMetadata(
            user_id=self.user_id,
            session_id=self.session_id,
            correlation_id=self.correlation_id,
        )


class OwnedTransactionRepository:
    """Shared runtime contract for repositories that own multi-step writes."""

    db: Database

    async def _run_in_owned_transaction(
        self,
        operation: Callable[[], Awaitable[R]],
        *,
        operation_name: str,
    ) -> R:
        """Run a repository-owned write operation inside one explicit transaction."""
        async with self.db.transaction():
            return await operation()

    def _assert_owned_transaction(self, helper_name: str) -> None:
        """Fail loudly when an internal write helper is called without ownership."""
        if self.db.transaction_active:
            return
        msg = (
            f"{self.__class__.__name__}.{helper_name} requires an active transaction "
            "owned by the current task; use a public self-transactional repository "
            "method or wrap the call in one outer service db.transaction()."
        )
        raise RuntimeError(msg)


class EventSourcedRepository[T: BaseModel](OwnedTransactionRepository, ABC):
    """
    Base repository implementing event sourcing pattern.

    All state changes are:
    1. Recorded as events (append-only)
    2. Tracked as revisions (version history)
    3. Measured with metrics
    4. Projected to current state table

    State is always reconstructable from events.
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
        self._context: RepositoryContext = RepositoryContext()

    def with_context(self, context: RepositoryContext) -> EventSourcedRepository[T]:
        """Set context for subsequent operations."""
        self._context = context
        return self

    @property
    @abstractmethod
    def entity_type(self) -> str:
        """Return the entity type name (e.g., 'project', 'task')."""
        ...

    @property
    @abstractmethod
    def table_name(self) -> str:
        """Return the projection table name."""
        ...

    @property
    def archive_column(self) -> str | None:
        """Return archive column name if projection supports soft-archive."""
        return None

    @abstractmethod
    def _model_from_row(self, row: dict[str, Any]) -> T:
        """Convert database row to model instance."""
        ...

    @abstractmethod
    def _row_from_model(self, model: T) -> dict[str, Any]:
        """Convert model instance to database row."""
        ...

    async def save(
        self,
        model: T,
        event_type: EventType,
        payload: dict[str, Any],
        message: str | None = None,
    ) -> T:
        """
        Save a model with full event sourcing.

        1. Records event
        2. Creates revision
        3. Updates projection
        4. Records metrics
        """
        with self.metrics.time_operation(
            f"{self.entity_type}.save",
            labels=[MetricLabel("event_type", event_type.value)],
        ):

            async def _save() -> T:
                return await self._save_in_transaction(
                    model=model,
                    event_type=event_type,
                    payload=payload,
                    message=message,
                )

            return await self._run_in_owned_transaction(
                _save,
                operation_name="save",
            )

    async def _save_in_transaction(
        self,
        *,
        model: T,
        event_type: EventType,
        payload: dict[str, Any],
        message: str | None = None,
    ) -> T:
        """Persist a model assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_save_in_transaction")
        # Check if this is a create or update
        existing = await self.get_by_id(model.id)
        is_create = existing is None

        # 1. Record event
        event = DomainEvent(
            event_type=event_type,
            aggregate_type=self.entity_type,
            aggregate_id=model.id,
            payload=payload,
            metadata=self._context.to_metadata(),
        )
        saved_event = await self.events.append(event)

        # 2. Create revision
        model_dict = model.to_dict()
        revision = await self._build_and_save_revision(
            model=model,
            model_dict=model_dict,
            is_create=is_create,
            message=message,
        )

        # 3. Record status/state transitions
        await self._record_status_transition(
            existing,
            model,
            message=message,
            payload=payload,
        )
        await self._record_workflow_assignment(
            existing,
            model,
            message=message,
            payload=payload,
        )

        # 4. Update projection
        model.last_event_sequence = saved_event.sequence_number
        model.last_revision_number = revision.revision_number
        await self._update_projection(model, is_create)

        return model

    async def _build_and_save_revision(
        self,
        *,
        model: T,
        model_dict: ModelObject,
        is_create: bool,
        message: str | None,
    ) -> Revision[ModelObject]:
        """Build and persist a revision, retrying when another writer wins first."""
        max_attempts = 3
        for attempt in range(max_attempts):
            revision = await self._build_revision(
                model=model,
                model_dict=model_dict,
                is_create=is_create,
                message=message,
            )
            try:
                await self.revisions.save_revision(revision)
                return revision
            except DatabaseError as exc:
                if is_create or not self.revisions.is_revision_conflict_error(exc):
                    raise
                if attempt + 1 >= max_attempts:
                    raise

        raise RuntimeError("Revision save retry loop exhausted unexpectedly")

    async def _build_revision(
        self,
        *,
        model: T,
        model_dict: ModelObject,
        is_create: bool,
        message: str | None,
    ) -> Revision[ModelObject]:
        """Build a revision for the current model state."""
        if is_create:
            return Revision.create_initial(
                entity_type=self.entity_type,
                entity_id=model.id,
                content=model_dict,
                created_by=self._context.user_id,
                message=message or f"Created {self.entity_type}",
            )

        prev_revision = await self.revisions.get_revision(self.entity_type, model.id)
        if prev_revision is None:
            return Revision.create_initial(
                entity_type=self.entity_type,
                entity_id=model.id,
                content=model_dict,
                created_by=self._context.user_id,
                message=message,
            )

        changes = self._compute_changes(prev_revision.content, model_dict)
        return Revision.create_from_parent(
            parent=prev_revision,
            new_content=model_dict,
            changes=changes,
            created_by=self._context.user_id,
            message=message,
        )

    async def _record_status_transition(
        self,
        existing: T | None,
        model: T,
        *,
        message: str | None,
        payload: dict[str, Any],
    ) -> None:
        if not hasattr(model, "status"):
            return
        old_status = getattr(existing, "status", None) if existing else None
        new_status = getattr(model, "status", None)

        old_value = self._normalize_transition_value(old_status)
        new_value = self._normalize_transition_value(new_status)

        if new_value is None or old_value == new_value:
            return

        state_repo = StateTransitionRepository(self.db)
        await state_repo.record_transition(
            entity_type=f"{self.entity_type}_status",
            entity_id=model.id,
            from_state=old_value,
            to_state=new_value,
            triggered_by=self._context.user_id or "system",
            reason=message or payload.get("reason"),
            metadata={"transition_kind": "status"},
        )

    async def _record_workflow_assignment(
        self,
        existing: T | None,
        model: T,
        *,
        message: str | None,
        payload: dict[str, Any],
    ) -> None:
        if not hasattr(model, "current_state"):
            return

        # Avoid duplicating explicit state machine transitions.
        if payload.get("state_transition"):
            return

        old_state = getattr(existing, "current_state", None) if existing else None
        new_state = getattr(model, "current_state", None)
        if new_state is None or old_state == new_state:
            return
        to_state = self._normalize_transition_value(new_state)
        if to_state is None:
            return

        state_repo = StateTransitionRepository(self.db)
        await state_repo.record_transition(
            entity_type=f"{self.entity_type}_workflow",
            entity_id=model.id,
            from_state=self._normalize_transition_value(old_state),
            to_state=to_state,
            triggered_by=self._context.user_id or "system",
            reason=message or payload.get("reason"),
            metadata={"transition_kind": "workflow"},
        )

    @staticmethod
    def _normalize_transition_value(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "value"):
            return str(value.value)
        return str(value)

    async def _update_projection(self, model: T, is_create: bool) -> None:
        """Update the projection table with current state."""
        row = self._row_from_model(model)

        if is_create:
            columns = ", ".join(row.keys())
            placeholders = ", ".join("?" * len(row))
            await self.db.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
                tuple(row.values()),
            )
        else:
            set_clause = ", ".join(f"{k} = ?" for k in row if k != "id")
            values = [v for k, v in row.items() if k != "id"]
            values.append(model.id)
            await self.db.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?",
                tuple(values),
            )

    async def get_by_id(self, entity_id: str) -> T | None:
        """Get entity by ID from projection."""
        with self.metrics.time_operation(f"{self.entity_type}.get_by_id"):
            sql = f"SELECT * FROM {self.table_name} WHERE id = ?"
            params: list[Any] = [entity_id]
            if self.archive_column:
                sql += f" AND {self.archive_column} IS NULL"
            row = await self.db.fetch_one(sql, tuple(params))
            if row is None:
                return None
            return self._model_from_row(row)

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "created_at",
        order_desc: bool = True,
    ) -> QueryResult[T]:
        """Get all entities with pagination."""
        with self.metrics.time_operation(f"{self.entity_type}.get_all"):
            # Get total count
            count_sql = f"SELECT COUNT(*) as count FROM {self.table_name}"
            if self.archive_column:
                count_sql += f" WHERE {self.archive_column} IS NULL"
            count_result = await self.db.fetch_one(count_sql)
            total = count_result["count"] if count_result else 0

            # Get items
            order_dir = "DESC" if order_desc else "ASC"
            select_sql = f"SELECT * FROM {self.table_name}"
            params: list[Any] = []
            if self.archive_column:
                select_sql += f" WHERE {self.archive_column} IS NULL"
            select_sql += f" ORDER BY {order_by} {order_dir} LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = await self.db.fetch_all(select_sql, tuple(params))

            items = [self._model_from_row(row) for row in rows]

            return QueryResult(
                items=items,
                total_count=total,
                offset=offset,
                limit=limit,
            )

    async def delete(
        self,
        entity_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        """
        Delete an entity.

        With soft_delete=True (default), marks as deleted but preserves history.
        With soft_delete=False, removes from projection but events/revisions remain.
        """
        with self.metrics.time_operation(f"{self.entity_type}.delete"):

            async def _delete() -> bool:
                return await self._delete_in_transaction(
                    entity_id=entity_id,
                    soft_delete=soft_delete,
                    message=message,
                )

            return await self._run_in_owned_transaction(
                _delete,
                operation_name="delete",
            )

    async def _delete_in_transaction(
        self,
        *,
        entity_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        """Delete an entity assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_delete_in_transaction")
        existing = await self.get_by_id(entity_id)
        if existing is None:
            return False

        # Record deletion event
        event = DomainEvent(
            event_type=EventType(f"{self.entity_type}.deleted"),
            aggregate_type=self.entity_type,
            aggregate_id=entity_id,
            payload={"soft_delete": soft_delete},
            metadata=self._context.to_metadata(),
        )
        await self.events.append(event)

        # Create deletion revision
        archived_at = datetime.now(UTC)
        prev_revision = await self.revisions.get_revision(self.entity_type, entity_id)
        if prev_revision:
            revision = Revision(
                revision_id=str(__import__("uuid").uuid4()),
                entity_type=self.entity_type,
                entity_id=entity_id,
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
                        field_name=self.archive_column or "status",
                        old_value=None,
                        new_value=(
                            archived_at.isoformat()
                            if self.archive_column
                            else "deleted"
                        ),
                        change_type=ChangeType.DELETE,
                    ),
                ),
                change_type=ChangeType.DELETE,
                created_at=archived_at,
                created_by=self._context.user_id,
                message=message or f"Deleted {self.entity_type}",
            )
            await self.revisions.save_revision(revision)

        # Archive from projection (events/revisions preserved)
        if soft_delete and self.archive_column:
            await self.db.execute(
                f"""
                UPDATE {self.table_name}
                SET {self.archive_column} = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    archived_at.isoformat(),
                    archived_at.isoformat(),
                    entity_id,
                ),
            )
        else:
            await self.db.execute(
                f"DELETE FROM {self.table_name} WHERE id = ?",
                (entity_id,),
            )

        return True

    async def restore(
        self,
        entity_id: str,
        message: str | None = None,
    ) -> T | None:
        """Restore a soft-archived entity back into the projection."""
        if not self.archive_column:
            return None

        with self.metrics.time_operation(f"{self.entity_type}.restore"):

            async def _restore() -> T | None:
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
    ) -> T | None:
        """Restore an entity assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_restore_in_transaction")
        row = await self.db.fetch_one(
            f"SELECT * FROM {self.table_name} WHERE id = ?",
            (entity_id,),
        )
        if row is None:
            return None

        archived_value = row.get(self.archive_column)
        if archived_value is None:
            return self._model_from_row(row)

        model = self._model_from_row(row)

        event = DomainEvent(
            event_type=EventType(f"{self.entity_type}.restored"),
            aggregate_type=self.entity_type,
            aggregate_id=entity_id,
            payload={"content": model.to_dict()},
            metadata=self._context.to_metadata(),
        )
        await self.events.append(event)

        restored_at = datetime.now(UTC)
        prev_revision = await self.revisions.get_revision(self.entity_type, entity_id)
        if prev_revision:
            revision = Revision(
                revision_id=str(__import__("uuid").uuid4()),
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
                        field_name=self.archive_column,
                        old_value=str(archived_value),
                        new_value=None,
                        change_type=ChangeType.RESTORE,
                    ),
                ),
                change_type=ChangeType.RESTORE,
                created_at=restored_at,
                created_by=self._context.user_id,
                message=message or f"Restored {self.entity_type}",
            )
            await self.revisions.save_revision(revision)

        await self.db.execute(
            f"""
            UPDATE {self.table_name}
            SET {self.archive_column} = NULL, updated_at = ?
            WHERE id = ?
            """,
            (restored_at.isoformat(), entity_id),
        )

        row = await self.db.fetch_one(
            f"SELECT * FROM {self.table_name} WHERE id = ?",
            (entity_id,),
        )
        return self._model_from_row(row) if row else model

    async def get_history(
        self,
        entity_id: str,
        limit: int = 50,
    ) -> list[Revision[T]]:
        """Get revision history for an entity."""
        return await self.revisions.get_history(
            self.entity_type, entity_id, limit=limit
        )

    async def get_at_revision(
        self,
        entity_id: str,
        revision_number: int,
    ) -> T | None:
        """Get entity state at a specific revision."""
        revision = await self.revisions.get_revision(
            self.entity_type, entity_id, revision_number
        )
        if revision is None:
            return None

        # Reconstruct from revision content
        return self._model_from_row(revision.content)

    async def get_events(
        self,
        entity_id: str,
        from_sequence: int = 0,
    ) -> list[DomainEvent[dict[str, Any]]]:
        """Get events for an entity."""
        return await self.events.get_events(self.entity_type, entity_id, from_sequence)

    async def rebuild_from_events(self, entity_id: str) -> T | None:
        """
        Rebuild entity state by replaying all events.

        Useful for verification or corruption recovery.
        """
        events = await self.events.get_events(self.entity_type, entity_id)
        if not events:
            return None

        # Start with empty state and apply events
        state = await self._apply_events(events)
        return state

    @abstractmethod
    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> T | None:
        """Apply a sequence of events to reconstruct state."""
        ...

    def _compute_changes(
        self,
        old_content: dict[str, Any],
        new_content: dict[str, Any],
    ) -> list[Change]:
        """Compute list of changes between two states."""
        changes = []

        all_keys = set(old_content.keys()) | set(new_content.keys())
        for key in all_keys:
            old_val = old_content.get(key)
            new_val = new_content.get(key)

            if old_val != new_val:
                # Determine change type
                if old_val is None:
                    change_type = ChangeType.CREATE
                elif new_val is None:
                    change_type = ChangeType.DELETE
                else:
                    change_type = ChangeType.UPDATE

                changes.append(
                    Change(
                        field_name=key,
                        old_value=json.dumps(old_val) if old_val is not None else None,
                        new_value=json.dumps(new_val) if new_val is not None else None,
                        change_type=change_type,
                    )
                )

        return changes

    async def create_snapshot(self, entity_id: str) -> Snapshot[ModelObject] | None:
        """Create a snapshot of current state for performance optimization."""
        model = await self.get_by_id(entity_id)
        if model is None:
            return None

        snapshot = Snapshot.create(
            entity_type=self.entity_type,
            entity_id=entity_id,
            state=model.to_dict(),
            last_event_sequence=model.last_event_sequence,
            last_revision_number=model.last_revision_number,
        )

        await self.revisions.save_snapshot(snapshot)
        return snapshot
