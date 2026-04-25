"""Work snapshot review model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from pms.models.json_types import JsonObject, ModelObject


@dataclass
class WorkSnapshotReview:
    """Recorded review checkpoint for work snapshots."""

    id: str = field(default_factory=lambda: str(uuid4()))
    scope_type: str = "project"
    scope_id: str = ""
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    reviewed_by: str | None = None
    note: str | None = None
    metadata: JsonObject = field(default_factory=dict)

    def to_dict(self) -> ModelObject:
        """Serialize review to dictionary."""
        return {
            "id": self.id,
            "scope_type": self.scope_type,
            "scope_id": self.scope_id,
            "reviewed_at": self.reviewed_at.isoformat(),
            "reviewed_by": self.reviewed_by,
            "note": self.note,
            "metadata": self.metadata,
        }
