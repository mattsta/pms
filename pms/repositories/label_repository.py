"""Repository for labels."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.label import Label
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class LabelRepository(EventSourcedRepository[Label]):
    """Repository for labels."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "label"

    @property
    def table_name(self) -> str:
        return "labels"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        name: str,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool = False,
    ) -> Label:
        label = Label(
            name=name,
            description=description,
            category_id=category_id,
            color=color,
            is_system=is_system,
        )
        payload = {
            "name": name,
            "description": description,
            "category_id": category_id,
            "color": color,
            "is_system": is_system,
        }

        return await self.save(
            label,
            EventType.LABEL_CREATED,
            payload,
            message=f"Created label '{name}'",
        )

    async def get_by_id(self, label_id: str) -> Label | None:
        row = await self.db.fetch_one(
            "SELECT * FROM labels WHERE id = ? AND archived_at IS NULL",
            (label_id,),
        )
        return self._row_to_model(row) if row else None

    async def get_by_name(self, name: str) -> Label | None:
        row = await self.db.fetch_one(
            "SELECT * FROM labels WHERE name = ? AND archived_at IS NULL",
            (name,),
        )
        return self._row_to_model(row) if row else None

    async def list_all(
        self, category_id: str | None = None, *, include_archived: bool = False
    ) -> list[Label]:
        if category_id:
            if include_archived:
                rows = await self.db.fetch_all(
                    """
                    SELECT * FROM labels
                    WHERE category_id = ?
                    ORDER BY name
                    """,
                    (category_id,),
                )
            else:
                rows = await self.db.fetch_all(
                    """
                    SELECT * FROM labels
                    WHERE category_id = ? AND archived_at IS NULL
                    ORDER BY name
                    """,
                    (category_id,),
                )
        else:
            if include_archived:
                rows = await self.db.fetch_all("SELECT * FROM labels ORDER BY name")
            else:
                rows = await self.db.fetch_all(
                    "SELECT * FROM labels WHERE archived_at IS NULL ORDER BY name"
                )
        return [self._row_to_model(row) for row in rows]

    async def update(
        self,
        label_id: str,
        name: str | None = None,
        description: str | None = None,
        category_id: str | None = None,
        color: str | None = None,
        is_system: bool | None = None,
    ) -> Label | None:
        label = await self.get_by_id(label_id)
        if label is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != label.name:
            changes["name"] = (label.name, name)
            label.name = name
        if description is not None and description != label.description:
            changes["description"] = (label.description, description)
            label.description = description
        if category_id is not None and category_id != label.category_id:
            changes["category_id"] = (label.category_id, category_id)
            label.category_id = category_id
        if color is not None and color != label.color:
            changes["color"] = (label.color, color)
            label.color = color
        if is_system is not None and is_system != label.is_system:
            changes["is_system"] = (label.is_system, is_system)
            label.is_system = is_system

        if not changes:
            return label

        label.touch()
        payload = {"changes": changes}

        return await self.save(
            label,
            EventType.LABEL_UPDATED,
            payload,
            message="Updated label",
        )

    async def delete(
        self,
        label_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            label_id,
            soft_delete=soft_delete,
            message=message or "Deleted label",
        )

    def _row_to_model(self, row: dict[str, Any]) -> Label:
        return Label(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            category_id=row.get("category_id"),
            color=row.get("color"),
            is_system=bool(row.get("is_system", 0)),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> Label:
        return self._row_to_model(row)

    def _row_from_model(self, model: Label) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "category_id": model.category_id,
            "color": model.color,
            "is_system": 1 if model.is_system else 0,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> Label | None:
        if not events:
            return None

        label: Label | None = None
        for event in events:
            match event.event_type:
                case EventType.LABEL_CREATED:
                    payload = event.payload
                    label = Label(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        category_id=payload.get("category_id"),
                        color=payload.get("color"),
                        is_system=bool(payload.get("is_system", False)),
                    )
                case EventType.LABEL_UPDATED if label:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                label.name = new_val
                            case "description":
                                label.description = new_val
                            case "category_id":
                                label.category_id = new_val
                            case "color":
                                label.color = new_val
                            case "is_system":
                                label.is_system = bool(new_val)
                case EventType.LABEL_DELETED:
                    label = None
                case EventType.LABEL_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    content.setdefault("id", event.aggregate_id)
                    label = Label.from_dict(content)

        return label


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
