"""Repository for custom field definitions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from pms.core.events import DomainEvent, EventStore, EventType
from pms.core.metrics import MetricsCollector
from pms.core.revisions import RevisionStore
from pms.models.custom_field import CustomFieldDefinition, CustomFieldType
from pms.repositories.base import EventSourcedRepository

if TYPE_CHECKING:
    from pms.db.connection import Database


class CustomFieldRepository(EventSourcedRepository[CustomFieldDefinition]):
    """Repository for custom field definitions."""

    def __init__(self, db: Database) -> None:
        super().__init__(
            db,
            EventStore(db),
            RevisionStore(db),
            MetricsCollector(db),
        )

    @property
    def entity_type(self) -> str:
        return "custom_field"

    @property
    def table_name(self) -> str:
        return "custom_field_definitions"

    @property
    def archive_column(self) -> str | None:
        return "archived_at"

    async def create(
        self,
        name: str,
        entity_type: str,
        field_type: CustomFieldType,
        description: str | None = None,
        options: list[str] | None = None,
        is_required: bool = False,
    ) -> CustomFieldDefinition:
        definition = CustomFieldDefinition(
            name=name,
            entity_type=entity_type,
            field_type=field_type,
            description=description,
            options=options or [],
            is_required=is_required,
        )
        payload = {
            "name": name,
            "entity_type": entity_type,
            "field_type": field_type.value,
            "description": description,
            "options": options or [],
            "is_required": is_required,
        }
        return await self.save(
            definition,
            EventType.CUSTOM_FIELD_CREATED,
            payload,
            message=f"Created custom field '{name}'",
        )

    async def get_by_id(
        self, field_id: str, *, include_archived: bool = False
    ) -> CustomFieldDefinition | None:
        if include_archived:
            row = await self.db.fetch_one(
                "SELECT * FROM custom_field_definitions WHERE id = ?",
                (field_id,),
            )
        else:
            row = await self.db.fetch_one(
                """
                SELECT * FROM custom_field_definitions
                WHERE id = ? AND archived_at IS NULL
                """,
                (field_id,),
            )
        return self._row_to_model(row) if row else None

    async def get_by_name(
        self,
        name: str,
        entity_type: str,
        *,
        include_archived: bool = False,
    ) -> CustomFieldDefinition | None:
        if include_archived:
            row = await self.db.fetch_one(
                """
                SELECT * FROM custom_field_definitions
                WHERE name = ? AND entity_type = ?
                """,
                (name, entity_type),
            )
        else:
            row = await self.db.fetch_one(
                """
                SELECT * FROM custom_field_definitions
                WHERE name = ? AND entity_type = ? AND archived_at IS NULL
                """,
                (name, entity_type),
            )
        return self._row_to_model(row) if row else None

    async def list_all(
        self,
        *,
        entity_type: str | None = None,
        include_archived: bool = False,
    ) -> list[CustomFieldDefinition]:
        conditions: list[str] = []
        params: list[Any] = []
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if not include_archived:
            conditions.append("archived_at IS NULL")
        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)
        rows = await self.db.fetch_all(
            f"""
            SELECT * FROM custom_field_definitions
            {where_sql}
            ORDER BY entity_type, name
            """,
            tuple(params),
        )
        return [self._row_to_model(row) for row in rows]

    async def update(
        self,
        field_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        field_type: CustomFieldType | None = None,
        options: list[str] | None = None,
        is_required: bool | None = None,
    ) -> CustomFieldDefinition | None:
        definition = await self.get_by_id(field_id)
        if definition is None:
            return None

        changes: dict[str, Any] = {}
        if name is not None and name != definition.name:
            changes["name"] = (definition.name, name)
            definition.name = name
        if description is not None and description != definition.description:
            changes["description"] = (definition.description, description)
            definition.description = description
        if field_type is not None and field_type != definition.field_type:
            changes["field_type"] = (definition.field_type.value, field_type.value)
            definition.field_type = field_type
        if options is not None and options != definition.options:
            changes["options"] = (definition.options, options)
            definition.options = options
        if is_required is not None and is_required != definition.is_required:
            changes["is_required"] = (definition.is_required, is_required)
            definition.is_required = is_required

        if not changes:
            return definition

        definition.touch()
        payload = {"changes": changes}
        return await self.save(
            definition,
            EventType.CUSTOM_FIELD_UPDATED,
            payload,
            message="Updated custom field",
        )

    async def delete(
        self,
        field_id: str,
        soft_delete: bool = True,
        message: str | None = None,
    ) -> bool:
        return await super().delete(
            field_id,
            soft_delete=soft_delete,
            message=message or "Archived custom field",
        )

    def _row_to_model(self, row: dict[str, Any]) -> CustomFieldDefinition:
        options = []
        if row.get("options_json"):
            try:
                options = json.loads(row["options_json"])
            except json.JSONDecodeError:
                options = []
        field_type_value = row.get("field_type", CustomFieldType.TEXT)
        try:
            field_type = CustomFieldType(field_type_value)
        except ValueError:
            field_type = CustomFieldType.TEXT
        return CustomFieldDefinition(
            id=row["id"],
            name=row["name"],
            entity_type=row["entity_type"],
            field_type=field_type,
            description=row.get("description"),
            options=options,
            is_required=bool(row.get("is_required", 0)),
            created_at=_parse_datetime_required(row.get("created_at"), "created_at"),
            updated_at=_parse_datetime_required(row.get("updated_at"), "updated_at"),
            archived_at=_parse_datetime_optional(row.get("archived_at")),
            last_event_sequence=row.get("last_event_sequence", 0),
            last_revision_number=row.get("last_revision_number", 0),
        )

    def _model_from_row(self, row: dict[str, Any]) -> CustomFieldDefinition:
        return self._row_to_model(row)

    def _row_from_model(self, model: CustomFieldDefinition) -> dict[str, Any]:
        return {
            "id": model.id,
            "name": model.name,
            "entity_type": model.entity_type,
            "field_type": model.field_type.value,
            "description": model.description,
            "options_json": json.dumps(model.options),
            "is_required": 1 if model.is_required else 0,
            "created_at": model.created_at.isoformat(),
            "updated_at": model.updated_at.isoformat(),
            "archived_at": model.archived_at.isoformat() if model.archived_at else None,
            "last_event_sequence": model.last_event_sequence,
            "last_revision_number": model.last_revision_number,
        }

    async def _apply_events(
        self, events: list[DomainEvent[dict[str, Any]]]
    ) -> CustomFieldDefinition | None:
        if not events:
            return None

        definition: CustomFieldDefinition | None = None
        for event in events:
            match event.event_type:
                case EventType.CUSTOM_FIELD_CREATED:
                    payload = event.payload
                    definition = CustomFieldDefinition(
                        id=event.aggregate_id,
                        name=payload.get("name", ""),
                        entity_type=payload.get("entity_type", ""),
                        field_type=CustomFieldType(
                            payload.get("field_type", CustomFieldType.TEXT)
                        ),
                        description=payload.get("description"),
                        options=payload.get("options") or [],
                        is_required=bool(payload.get("is_required", False)),
                    )
                case EventType.CUSTOM_FIELD_UPDATED if definition:
                    changes = event.payload.get("changes", {})
                    for field, (_old_val, new_val) in changes.items():
                        match field:
                            case "name":
                                definition.name = new_val
                            case "description":
                                definition.description = new_val
                            case "field_type":
                                definition.field_type = CustomFieldType(new_val)
                            case "options":
                                definition.options = new_val or []
                            case "is_required":
                                definition.is_required = bool(new_val)
                case EventType.CUSTOM_FIELD_DELETED if definition:
                    definition.archived_at = event.metadata.timestamp
                case EventType.CUSTOM_FIELD_RESTORED if definition:
                    definition.archived_at = None

        if definition:
            definition.last_event_sequence = events[-1].sequence_number
        return definition


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
