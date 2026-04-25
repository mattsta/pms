"""Service for custom field definitions and values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from pms.core.entity_type_contract import entity_table_for_type, validate_entity_type
from pms.core.metrics import MetricsCollector
from pms.models.custom_field import (
    CustomFieldDefinition,
    CustomFieldType,
    CustomFieldValue,
)
from pms.models.json_types import JsonObject, JsonValue, ModelObject
from pms.repositories.custom_field_repository import CustomFieldRepository
from pms.repositories.custom_field_value_repository import CustomFieldValueRepository

if TYPE_CHECKING:
    from pms.db.connection import Database

type CustomFieldInputValue = JsonValue | date | datetime
type CustomFieldStoredValue = JsonValue


def _coerce_json_value(value: JsonValue) -> JsonValue:
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


@dataclass
class CustomFieldValueItem:
    """Custom field value with its definition."""

    definition: CustomFieldDefinition | None
    value: CustomFieldValue

    def to_dict(self) -> ModelObject:
        return {
            "definition": self.definition.to_dict() if self.definition else None,
            "value": self.value.to_dict(),
        }


@dataclass
class CustomFieldValuePage:
    """Paginated custom field value results."""

    items: list[CustomFieldValueItem]
    total_count: int
    offset: int
    limit: int


class CustomFieldService:
    """Service for custom field management and value validation."""

    def __init__(self, db: Database, metrics: MetricsCollector) -> None:
        self.db = db
        self.metrics = metrics
        self._definitions = CustomFieldRepository(db)
        self._values = CustomFieldValueRepository(db)

    def _normalize_entity_type(self, entity_type: str) -> str:
        return validate_entity_type(entity_type)

    def _validate_entity_type(self, entity_type: str) -> None:
        validate_entity_type(entity_type)

    async def _ensure_entity_exists(self, entity_type: str, entity_id: str) -> None:
        table = entity_table_for_type(entity_type)
        if not table:
            return
        row = await self.db.fetch_one(
            f"SELECT id FROM {table} WHERE id = ?",
            (entity_id,),
        )
        if row is None:
            raise ValueError(f"{entity_type} '{entity_id}' not found")

    def _coerce_value(
        self,
        field: CustomFieldDefinition,
        value: CustomFieldInputValue,
    ) -> CustomFieldStoredValue:
        if value is None:
            if field.is_required:
                raise ValueError(f"Field '{field.name}' requires a value")
            return None

        match field.field_type:
            case CustomFieldType.TEXT | CustomFieldType.URL:
                if isinstance(value, (dict, list)):
                    return json.dumps(value)
                return str(value)
            case CustomFieldType.NUMBER:
                if isinstance(value, bool):
                    raise ValueError("Boolean values are not valid numbers")
                if isinstance(value, (int, float)):
                    return value
                try:
                    return float(str(value))
                except ValueError as exc:
                    raise ValueError("Expected a numeric value") from exc
            case CustomFieldType.BOOLEAN:
                if isinstance(value, bool):
                    return value
                if isinstance(value, str):
                    lowered = value.strip().lower()
                    if lowered in {"true", "yes", "1"}:
                        return True
                    if lowered in {"false", "no", "0"}:
                        return False
                raise ValueError("Expected a boolean value")
            case CustomFieldType.DATE:
                if isinstance(value, date) and not isinstance(value, datetime):
                    return value.isoformat()
                if isinstance(value, datetime):
                    return value.date().isoformat()
                if isinstance(value, str):
                    try:
                        return date.fromisoformat(value).isoformat()
                    except ValueError as exc:
                        raise ValueError("Expected ISO date (YYYY-MM-DD)") from exc
                raise ValueError("Expected a date value")
            case CustomFieldType.DATETIME:
                if isinstance(value, datetime):
                    return value.isoformat()
                if isinstance(value, str):
                    try:
                        return datetime.fromisoformat(value).isoformat()
                    except ValueError as exc:
                        raise ValueError(
                            "Expected ISO datetime (YYYY-MM-DDTHH:MM:SS)"
                        ) from exc
                raise ValueError("Expected a datetime value")
            case CustomFieldType.ENUM:
                if not field.options:
                    raise ValueError("Enum fields require options")
                if isinstance(value, str):
                    if value not in field.options:
                        raise ValueError(
                            f"Value '{value}' not in options {field.options}"
                        )
                    return value
                raise ValueError("Expected a string value for enum")
            case CustomFieldType.JSON:
                if isinstance(value, str):
                    try:
                        loaded = json.loads(value)
                        return _coerce_json_value(loaded)
                    except json.JSONDecodeError as exc:
                        raise ValueError("Expected JSON value") from exc
                if isinstance(value, (dict, list)):
                    return value
                if isinstance(value, (int, float, bool)) or value is None:
                    return value
                return str(value)
            case _:
                return str(value)

    async def create_definition(
        self,
        name: str,
        entity_type: str,
        field_type: CustomFieldType,
        description: str | None = None,
        options: list[str] | None = None,
        is_required: bool = False,
    ) -> CustomFieldDefinition:
        entity_type = self._normalize_entity_type(entity_type)
        self._validate_entity_type(entity_type)
        if field_type == CustomFieldType.ENUM and not options:
            raise ValueError("Enum fields require non-empty options")
        async with self.db.transaction():
            definition = await self._definitions.create(
                name=name,
                entity_type=entity_type,
                field_type=field_type,
                description=description,
                options=options,
                is_required=is_required,
            )
            await self.metrics.record_counter(
                "custom_field.created",
                labels={"entity_type": entity_type, "field": name},
            )
            await self.metrics.flush()
        return definition

    async def list_definitions(
        self,
        *,
        entity_type: str | None = None,
        include_archived: bool = False,
    ) -> list[CustomFieldDefinition]:
        normalized = self._normalize_entity_type(entity_type) if entity_type else None
        return await self._definitions.list_all(
            entity_type=normalized, include_archived=include_archived
        )

    async def get_definition(
        self, field_id: str, *, include_archived: bool = False
    ) -> CustomFieldDefinition | None:
        return await self._definitions.get_by_id(
            field_id, include_archived=include_archived
        )

    async def get_definition_by_name(
        self,
        name: str,
        entity_type: str,
        *,
        include_archived: bool = False,
    ) -> CustomFieldDefinition | None:
        normalized = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized)
        return await self._definitions.get_by_name(
            name, normalized, include_archived=include_archived
        )

    async def update_definition(
        self,
        field_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        field_type: CustomFieldType | None = None,
        options: list[str] | None = None,
        is_required: bool | None = None,
    ) -> CustomFieldDefinition | None:
        if field_type == CustomFieldType.ENUM and not options:
            raise ValueError("Enum fields require non-empty options")
        return await self._definitions.update(
            field_id,
            name=name,
            description=description,
            field_type=field_type,
            options=options,
            is_required=is_required,
        )

    async def delete_definition(self, field_id: str) -> bool:
        return await self._definitions.delete(field_id)

    async def restore_definition(self, field_id: str) -> CustomFieldDefinition | None:
        return await self._definitions.restore(field_id)

    async def set_value(
        self,
        field_ref: str,
        *,
        entity_type: str,
        entity_id: str,
        value: CustomFieldInputValue,
        created_by: str | None = None,
        source: str | None = None,
        metadata: JsonObject | None = None,
    ) -> CustomFieldValueItem:
        normalized_type = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized_type)
        await self._ensure_entity_exists(normalized_type, entity_id)

        definition = await self._definitions.get_by_id(field_ref)
        if definition is None:
            definition = await self._definitions.get_by_name(field_ref, normalized_type)
        if definition is None:
            raise ValueError(f"Custom field '{field_ref}' not found")
        if definition.entity_type != normalized_type:
            raise ValueError(
                f"Field '{definition.name}' belongs to '{definition.entity_type}'"
            )

        coerced = self._coerce_value(definition, value)
        async with self.db.transaction():
            field_value = await self._values.create(
                field_id=definition.id,
                entity_type=normalized_type,
                entity_id=entity_id,
                value=coerced,
                created_by=created_by,
                source=source,
                metadata=metadata,
            )
            await self.metrics.record_counter(
                "custom_field.value_set",
                labels={"entity_type": normalized_type, "field": definition.name},
            )
            await self.metrics.flush()
        return CustomFieldValueItem(definition=definition, value=field_value)

    async def list_values_for_entity(
        self,
        *,
        entity_type: str,
        entity_id: str,
        include_history: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> CustomFieldValuePage:
        normalized_type = self._normalize_entity_type(entity_type)
        self._validate_entity_type(normalized_type)
        await self._ensure_entity_exists(normalized_type, entity_id)

        value_page = await self._values.list_for_entity(
            normalized_type,
            entity_id,
            include_history=include_history,
            limit=limit,
            offset=offset,
        )
        definitions = await self._definitions.list_all(
            entity_type=normalized_type, include_archived=True
        )
        definition_map = {definition.id: definition for definition in definitions}
        items = [
            CustomFieldValueItem(
                definition=definition_map.get(value.field_id),
                value=value,
            )
            for value in value_page.items
        ]
        return CustomFieldValuePage(
            items=items,
            total_count=value_page.total_count,
            offset=value_page.offset,
            limit=value_page.limit,
        )

    async def list_values_for_field(
        self,
        field_id: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> CustomFieldValuePage:
        definition = await self._definitions.get_by_id(field_id, include_archived=True)
        value_page = await self._values.list_for_field(
            field_id, limit=limit, offset=offset
        )
        items = [
            CustomFieldValueItem(definition=definition, value=value)
            for value in value_page.items
        ]
        return CustomFieldValuePage(
            items=items,
            total_count=value_page.total_count,
            offset=value_page.offset,
            limit=value_page.limit,
        )
