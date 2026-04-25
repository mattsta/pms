"""Objective model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import GoalStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Objective(BaseModel):
    """
    An objective represents a measurable outcome within a goal.

    Objectives group key results and roll up their progress.
    """

    goal_id: str = ""
    name: str = ""
    description: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    target_date: datetime | None = None
    owner: str | None = None
    owner_id: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0

    # Workflow/state machine integration
    workflow_id: str | None = None
    current_state: str | None = None
    workflow_metadata: JsonObject = field(default_factory=dict)

    def complete(self) -> Self:
        """Mark objective as completed."""
        self.status = GoalStatus.COMPLETED
        self.progress_percent = 100
        self.updated_at = now_utc()
        return self

    def archive(self) -> Self:
        """Archive an objective."""
        self.status = GoalStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def put_on_hold(self) -> Self:
        """Put objective on hold."""
        self.status = GoalStatus.ON_HOLD
        self.updated_at = now_utc()
        return self

    def reactivate(self) -> Self:
        """Reactivate an objective."""
        self.status = GoalStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    # Workflow transition helpers
    def assign_workflow(self, workflow_id: str, initial_state: str) -> Self:
        """Assign a workflow to this objective."""
        self.workflow_id = workflow_id
        self.current_state = initial_state
        self.touch()
        return self

    def transition_to(
        self, new_state: str, triggered_by: str, reason: str | None = None
    ) -> Self:
        """Transition to a new workflow state."""
        _ = triggered_by
        _ = reason
        self.current_state = new_state
        self.touch()
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
