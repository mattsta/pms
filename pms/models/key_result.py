"""Key result model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import GoalStatus
from pms.models.json_types import ModelObject


@dataclass
class KeyResult(BaseModel):
    """
    A key result is a measurable indicator for an objective.

    Progress can be tracked via current/target values or direct percent.
    """

    objective_id: str = ""
    name: str = ""
    description: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    current_value: float | None = None
    target_value: float | None = None
    unit: str | None = None
    owner: str | None = None
    owner_id: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0

    def complete(self) -> Self:
        """Mark key result as completed."""
        self.status = GoalStatus.COMPLETED
        self.progress_percent = 100
        self.updated_at = now_utc()
        return self

    def archive(self) -> Self:
        """Archive a key result."""
        self.status = GoalStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def put_on_hold(self) -> Self:
        """Put key result on hold."""
        self.status = GoalStatus.ON_HOLD
        self.updated_at = now_utc()
        return self

    def reactivate(self) -> Self:
        """Reactivate a key result."""
        self.status = GoalStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = GoalStatus(data["status"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)
