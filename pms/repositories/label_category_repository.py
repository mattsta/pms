"""Repository for label categories."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.label import LabelCategory
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class LabelCategoryRepository(EventSourcedRepository[LabelCategory]):
    """Repository for label categories."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "label_category"

    @property
    def table_name(self) -> str:
        return "label_categories"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        name: str,
        description: str | None = None,
        is_exclusive: bool = False,
        sort_order: int = 0,
    ) -> LabelCategory:
        category = LabelCategory(
            name=name,
            description=description,
            is_exclusive=is_exclusive,
            sort_order=sort_order,
        )
        payload = {
            "name": name,
            "description": description,
            "is_exclusive": is_exclusive,
            "sort_order": sort_order,
        }

        return await self.save(
            category,
            EventType.LABEL_CATEGORY_CREATED,
            payload,
            message=f"Created label category '{name}'",
        )

    async def get_by_id(self, category_id: str) -> LabelCategory | None:
        row = await self.db.fetch_one(
            "SELECT * FROM label_categories WHERE id = ? AND archived_at IS NULL",
            (category_id,),
        )
        return self._row_to_model(row) if row else None

    async def get_by_name(self, name: str) -> LabelCategory | None:
        row = await self.db.fetch_one(
            "SELECT * FROM label_categories WHERE name = ? AND archived_at IS NULL",
            (name,),
        )
        return self._row_to_model(row) if row else None

    async def list_all(self, include_archived: bool = False) -> list[LabelCategory]:
        if include_archived:
            rows = await self.db.fetch_all(
                """
                SELECT * FROM label_categories
                ORDER BY sort_order, name
                """,
            )
        else:
            rows = await self.db.fetch_all(
                """
                SELECT * FROM label_categories
                WHERE archived_at IS NULL
                ORDER BY sort_order, name
                """,
            )
        return [self._row_to_model(row) for row in rows]

    async def update(
        self,
        category_id: str,
        name: str | None = None,
        description: str | None = None,
        is_exclusive: bool | None = None,
        sort_order: int | None = None,
    ) -> LabelCategory | None:
        category = await self.get_by_id(category_id)
        if category is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != category.name:
            changes["name"] = (category.name, name)
            category.name = name
        if description is not None and description != category.description:
            changes["description"] = (category.description, description)
            category.description = description
        if is_exclusive is not None and is_exclusive != category.is_exclusive:
            changes["is_exclusive"] = (category.is_exclusive, is_exclusive)
            category.is_exclusive = is_exclusive
        if sort_order is not None and sort_order != category.sort_order:
            changes["sort_order"] = (category.sort_order, sort_order)
            category.sort_order = sort_order

        if not changes:
            return category

        category.touch()
        payload = {"changes": changes}

        return await self.save(
            category,
            EventType.LABEL_CATEGORY_UPDATED,
            payload,
            message="Updated label category",
        )

    async def delete(
        self,
        category_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            category_id,
            soft_delete=soft_delete,
            message=message or "Deleted label category",
        )

    def _row_to_model(self, row: dict[str, Any]) -> LabelCategory:
        return LabelCategory(
            id=row["id"],
            name=row["name"],
            description=row.get("description"),
            is_exclusive=bool(row.get("is_exclusive", 0)),
            sort_order=row.get("sort_order", 0),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> LabelCategory:
        return self._row_to_model(row)

    def _row_from_model(self, model: LabelCategory) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "description": model.description,
            "is_exclusive": 1 if model.is_exclusive else 0,
            "sort_order": model.sort_order,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> LabelCategory | None:
        if not events:
            return None

        category: LabelCategory | None = None
        for event in events:
            match event.event_type:
                case EventType.LABEL_CATEGORY_CREATED:
                    payload = event.payload
                    category = LabelCategory(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        description=payload.get("description"),
                        is_exclusive=bool(payload.get("is_exclusive", False)),
                        sort_order=payload.get("sort_order", 0),
                    )
                case EventType.LABEL_CATEGORY_UPDATED if category:
                    changes = event.payload.get("changes", {})
                    for field, (old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                category.name = new_val
                            case "description":
                                category.description = new_val
                            case "is_exclusive":
                                category.is_exclusive = bool(new_val)
                            case "sort_order":
                                category.sort_order = new_val
                case EventType.LABEL_CATEGORY_DELETED:
                    category = None
                case EventType.LABEL_CATEGORY_RESTORED:
                    payload = event.payload
                    content = payload.get("content") or {}
                    content.setdefault("id", event.aggregate_id)
                    category = LabelCategory.from_dict(content)

        return category


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
