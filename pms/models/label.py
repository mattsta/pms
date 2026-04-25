"""Label models for structured categorization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pms.models.base import BaseModel
from pms.models.json_types import ModelObject


@dataclass
class LabelCategory(BaseModel):
    """Category for grouping labels."""

    name: str = ""
    description: str | None = None
    is_exclusive: bool = False
    sort_order: int = 0
    archived_at: datetime | None = None


@dataclass
class Label(BaseModel):
    """Structured label with optional category."""

    name: str = ""
    description: str | None = None
    category_id: str | None = None
    color: str | None = None
    is_system: bool = False
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        data = super().to_dict()
        data["is_system"] = self.is_system
        return data
