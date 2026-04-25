"""Saved search query model for task queues."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from pms.models.base import BaseModel
from pms.models.json_types import JsonObject, ModelObject
from pms.models.value_contracts import SortDirection


@dataclass
class SavedSearch(BaseModel):
    """Saved search configuration for task queues."""

    name: str = ""
    description: str | None = None
    owner: str | None = None
    owner_id: str | None = None
    scope_type: str = "global"
    scope_id: str | None = None
    filters: JsonObject = field(default_factory=dict)
    sort_by: str | None = None
    sort_dir: SortDirection = "desc"
    archived_at: datetime | None = None

    def to_dict(self) -> ModelObject:
        """Serialize saved search to a dictionary."""
        data = super().to_dict()
        data.update(
            {
                "name": self.name,
                "description": self.description,
                "owner": self.owner,
                "owner_id": self.owner_id,
                "scope_type": self.scope_type,
                "scope_id": self.scope_id,
                "filters": self.filters,
                "sort_by": self.sort_by,
                "sort_dir": self.sort_dir,
            }
        )
        return data
