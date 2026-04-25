"""Custom field models for extensible metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from pms.models.base import BaseModel
from pms.models.json_types import JsonObject, JsonValue, ModelObject


class CustomFieldType(StrEnum):
    """Supported custom field types."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ENUM = "enum"
    JSON = "json"
    URL = "url"


@dataclass
class CustomFieldDefinition(BaseModel):
    """Definition for a reusable custom field."""

    name: str = ""
    entity_type: str = ""
    field_type: CustomFieldType = CustomFieldType.TEXT
    description: str | None = None
    options: list[str] = field(default_factory=list)
    is_required: bool = False
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data.update(
            {
                "name": self.name,
                "entity_type": self.entity_type,
                "field_type": self.field_type.value,
                "description": self.description,
                "options": list(self.options),
                "is_required": self.is_required,
                "archived_at": self.archived_at.isoformat()
                if self.archived_at
                else None,
            }
        )
        return data


@dataclass
class CustomFieldValue(BaseModel):
    """Append-only value assignment for a custom field."""

    field_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    value: JsonValue = None
    created_by: str | None = None
    source: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data.update(
            {
                "field_id": self.field_id,
                "entity_type": self.entity_type,
                "entity_id": self.entity_id,
                "value": self.value,
                "created_by": self.created_by,
                "source": self.source,
                "metadata": self.metadata,
            }
        )
        return data
