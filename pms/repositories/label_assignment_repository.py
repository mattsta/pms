"""Repository for label assignments."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, TypedDict

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import Revision, RevisionStore
from pms.models.label_assignment import LabelAssignment
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class LabelAssignmentRevisionContent(TypedDict, total=False):
    """Structured revision content for label assignment history."""

    id: str
    entity_type: str
    entity_id: str
    label_id: str
    applied_by: str | None
    applied_at: str
    created_at: str
    updated_at: str
    archived_at: str | None
    last_event_sequence: int
    last_revision_number: int


type LabelAssignmentRowValue = str | int | datetime | None
type LabelAssignmentRow = dict[str, LabelAssignmentRowValue]
type LabelAssignmentEventPayloadValue = str | LabelAssignmentRevisionContent | None
type LabelAssignmentEventPayload = dict[str, LabelAssignmentEventPayloadValue]
type DateTimeInput = datetime | str | int | LabelAssignmentRevisionContent | None
type LabelAssignmentRevisionInputContent = LabelAssignmentRevisionContent


class LabelAssignmentRepository(EventSourcedRepository[LabelAssignment]):
    """Repository for label assignments."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "label_assignment"

    @property
    def table_name(self) -> str:
        return "label_assignments"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def assign(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
        applied_by: str | None = None,
    ) -> LabelAssignment:
        async def _assign() -> LabelAssignment:
            return await self._assign_in_transaction(
                entity_type=entity_type,
                entity_id=entity_id,
                label_id=label_id,
                applied_by=applied_by,
            )

        return await self._run_in_owned_transaction(
            _assign,
            operation_name="assign",
        )

    async def _assign_in_transaction(
        self,
        *,
        entity_type: str,
        entity_id: str,
        label_id: str,
        applied_by: str | None = None,
    ) -> LabelAssignment:
        """Assign a label assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_assign_in_transaction")
        existing = await self._get_by_entity_label(
            entity_type=entity_type,
            entity_id=entity_id,
            label_id=label_id,
        )
        if existing is not None:
            return existing

        assignment = LabelAssignment(
            entity_type=entity_type,
            entity_id=entity_id,
            label_id=label_id,
            applied_by=applied_by,
        )

        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "label_id": label_id,
            "applied_by": applied_by,
            "applied_at": assignment.applied_at.isoformat(),
        }

        return await self._save_in_transaction(
            model=assignment,
            event_type=EventType.LABEL_ASSIGNMENT_CREATED,
            payload=payload,
            message="Assigned label",
        )

    async def remove(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
    ) -> bool:
        async def _remove() -> bool:
            return await self._remove_in_transaction(
                entity_type=entity_type,
                entity_id=entity_id,
                label_id=label_id,
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
        label_id: str,
    ) -> bool:
        """Remove a label assignment assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_remove_in_transaction")
        assignment = await self._get_by_entity_label(
            entity_type=entity_type,
            entity_id=entity_id,
            label_id=label_id,
        )
        if assignment is None:
            return False
        return await self._delete_in_transaction(
            entity_id=assignment.id,
            message="Removed label assignment",
        )

    async def remove_by_category(
        self,
        entity_type: str,
        entity_id: str,
        category_id: str,
    ) -> int:
        async def _remove_by_category() -> int:
            return await self._remove_by_category_in_transaction(
                entity_type=entity_type,
                entity_id=entity_id,
                category_id=category_id,
            )

        return await self._run_in_owned_transaction(
            _remove_by_category,
            operation_name="remove_by_category",
        )

    async def _remove_by_category_in_transaction(
        self,
        *,
        entity_type: str,
        entity_id: str,
        category_id: str,
    ) -> int:
        """Remove category assignments assuming the caller already owns the transaction."""
        self._assert_owned_transaction("_remove_by_category_in_transaction")
        rows = await self.db.fetch_all(
            """
            SELECT la.id
            FROM label_assignments la
            INNER JOIN labels l ON la.label_id = l.id
            WHERE la.entity_type = ?
              AND la.entity_id = ?
              AND l.category_id = ?
              AND la.archived_at IS NULL
            """,
            (entity_type, entity_id, category_id),
        )
        removed = 0
        for row in rows:
            if await self._delete_in_transaction(
                entity_id=row["id"],
                message="Removed label assignment",
            ):
                removed += 1
        return removed

    async def list_for_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> list[LabelAssignment]:
        rows = await self.db.fetch_all(
            """
            SELECT * FROM label_assignments
            WHERE entity_type = ? AND entity_id = ? AND archived_at IS NULL
            ORDER BY applied_at DESC
            """,
            (entity_type, entity_id),
        )
        return [self._row_to_model(row) for row in rows]

    async def list_for_entities(
        self,
        entity_type: str,
        entity_ids: list[str],
    ) -> list[LabelAssignment]:
        if not entity_ids:
            return []
        unique_ids = list(dict.fromkeys(entity_ids))
        placeholders = ", ".join("?" * len(unique_ids))
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM label_assignments
            WHERE entity_type = ? AND entity_id IN ({placeholders})
              AND archived_at IS NULL
            """,
            (entity_type, *unique_ids),
        )
        return [self._row_to_model(row) for row in rows]

    async def get_assignment_history(
        self,
        assignment_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Revision[LabelAssignmentRevisionContent]]:
        """Get revision history for a label assignment."""
        history = await self.revisions.get_history(
            self.entity_type,
            assignment_id,
            limit=limit,
            offset=offset,
        )
        return [_coerce_assignment_revision(revision) for revision in history]

    async def get_history_count(self, assignment_id: str) -> int:
        """Get total revision count for a label assignment."""
        return await self.revisions.get_revision_count(self.entity_type, assignment_id)

    def _row_to_model(self, row: LabelAssignmentRow) -> LabelAssignment:
        return LabelAssignment(
            id=str(row["id"]),
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
            label_id=str(row["label_id"]),
            applied_by=_optional_str(row.get("applied_by")),
            applied_at=_parse_datetime_required(row.get("applied_at"), "applied_at"),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            last_event_sequence=int(row.get("last_event_sequence", 0)),
            last_revision_number=int(row.get("last_revision_number", 0)),
        )

    def _model_from_row(self, row: LabelAssignmentRow) -> LabelAssignment:
        return self._row_to_model(row)

    def _row_from_model(self, model: LabelAssignment) -> LabelAssignmentRow:
        return {
            "id": model.id,
            "entity_type": model.entity_type,
            "entity_id": model.entity_id,
            "label_id": model.label_id,
            "applied_by": model.applied_by,
            "applied_at": model.applied_at.isoformat()
            if hasattr(model.applied_at, "isoformat")
            else model.applied_at,
            "created_at": model.created_at.isoformat()
            if hasattr(model.created_at, "isoformat")
            else model.created_at,
            "updated_at": model.updated_at.isoformat()
            if hasattr(model.updated_at, "isoformat")
            else model.updated_at,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[LabelAssignmentEventPayload]]
    ) -> LabelAssignment | None:
        if not events:
            return None

        assignment: LabelAssignment | None = None
        for event in events:
            match event.event_type:
                case EventType.LABEL_ASSIGNMENT_CREATED:
                    payload = event.payload
                    assignment = LabelAssignment(
                        id=event.aggregate_id,
                        entity_type=_payload_str(payload.get("entity_type"), ""),
                        entity_id=_payload_str(payload.get("entity_id"), ""),
                        label_id=_payload_str(payload.get("label_id"), ""),
                        applied_by=_optional_str(payload.get("applied_by")),
                        applied_at=_parse_datetime_required(
                            payload.get("applied_at"), "applied_at"
                        ),
                    )
                case EventType.LABEL_ASSIGNMENT_DELETED:
                    assignment = None
                case EventType.LABEL_ASSIGNMENT_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    content_data = (
                        content
                        if isinstance(content, dict)
                        else LabelAssignmentRevisionContent()
                    )
                    assignment = LabelAssignment(
                        id=_payload_str(content_data.get("id"), event.aggregate_id),
                        entity_type=_payload_str(content_data.get("entity_type"), ""),
                        entity_id=_payload_str(content_data.get("entity_id"), ""),
                        label_id=_payload_str(content_data.get("label_id"), ""),
                        applied_by=_optional_str(content_data.get("applied_by")),
                        applied_at=_parse_datetime_required(
                            content_data.get("applied_at"), "applied_at"
                        ),
                    )

        return assignment

    async def _get_by_entity_label(
        self,
        entity_type: str,
        entity_id: str,
        label_id: str,
    ) -> LabelAssignment | None:
        row = await self.db.fetch_one(
            """
            SELECT * FROM label_assignments
            WHERE entity_type = ?
              AND entity_id = ?
              AND label_id = ?
              AND archived_at IS NULL
            """,
            (entity_type, entity_id, label_id),
        )
        return self._row_to_model(row) if row else None


def _parse_datetime_required(value: DateTimeInput, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    msg = f"Invalid datetime value for {field_name}: {value!r}"
    raise ValueError(msg)


def _optional_str(
    value: LabelAssignmentEventPayloadValue | LabelAssignmentRowValue,
) -> str | None:
    return value if isinstance(value, str) else None


def _payload_str(value: LabelAssignmentEventPayloadValue, default: str) -> str:
    return value if isinstance(value, str) else default


def _coerce_assignment_revision(
    revision: Revision[LabelAssignmentRevisionInputContent],
) -> Revision[LabelAssignmentRevisionContent]:
    return Revision(
        revision_id=revision.revision_id,
        entity_type=revision.entity_type,
        entity_id=revision.entity_id,
        revision_number=revision.revision_number,
        parent_revision_id=revision.parent_revision_id,
        content=revision.content,
        content_hash=revision.content_hash,
        changes=revision.changes,
        change_type=revision.change_type,
        created_at=revision.created_at,
        created_by=revision.created_by,
        message=revision.message,
        metadata=revision.metadata,
    )
