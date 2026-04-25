"""Task evidence model for audit and proof attachments."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pms.models.base import BaseModel
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class TaskEvidence(BaseModel):
    """Evidence linked to a task (manual or automated)."""

    task_id: str = ""
    evidence_type: str = ""
    reference: str = ""
    description: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_by: str = "system"

    def to_dict(self) -> ModelObject:
        """Convert to dictionary."""
        data = super().to_dict()
        data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        return super().from_dict(data)
