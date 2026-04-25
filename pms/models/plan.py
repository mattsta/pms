"""Plan model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import PlanFormat, PlanStatus
from pms.models.json_types import ModelObject


@dataclass
class Plan(BaseModel):
    """
    A plan artifact representing structured execution intent.

    Plans store JSON/YAML content and link to projects, goals, or tasks
    without duplicating task definitions.
    """

    name: str = ""
    description: str | None = None
    status: PlanStatus = PlanStatus.DRAFT
    format: PlanFormat = PlanFormat.JSON
    content: str = ""
    product_id: str | None = None
    project_id: str | None = None
    goal_id: str | None = None
    objective_id: str | None = None
    task_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def activate(self) -> Self:
        """Mark plan as active."""
        self.status = PlanStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    def complete(self) -> Self:
        """Mark plan as completed."""
        self.status = PlanStatus.COMPLETED
        self.updated_at = now_utc()
        return self

    def archive(self) -> Self:
        """Archive plan."""
        self.status = PlanStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["format"] = self.format.value
        data["task_ids"] = list(self.task_ids)
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = PlanStatus(data["status"])
        if "format" in data and isinstance(data["format"], str):
            data["format"] = PlanFormat(data["format"])
        if "task_ids" in data and isinstance(data["task_ids"], list):
            data["task_ids"] = tuple(data["task_ids"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)
