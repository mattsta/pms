"""Goal model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import GoalHorizon, GoalStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Goal(BaseModel):
    """
    A goal represents a strategic outcome over a time horizon.

    Goals can optionally be linked to a product or project and
    roll up progress from lower-level work.
    """

    name: str = ""
    description: str | None = None
    status: GoalStatus = GoalStatus.ACTIVE
    horizon: GoalHorizon = GoalHorizon.SHORT_TERM
    target_date: datetime | None = None
    owner: str | None = None
    owner_id: str | None = None
    product_id: str | None = None
    project_id: str | None = None
    tags: tuple[str, ...] = ()
    progress_percent: int = 0

    # Workflow/state machine integration
    workflow_id: str | None = None
    current_state: str | None = None
    workflow_metadata: JsonObject = field(default_factory=dict)  # State-specific data

    def complete(self) -> Self:
        """Mark goal as completed."""
        self.status = GoalStatus.COMPLETED
        self.updated_at = now_utc()
        self.progress_percent = 100
        return self

    def archive(self) -> Self:
        """Archive a goal."""
        self.status = GoalStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def put_on_hold(self) -> Self:
        """Put goal on hold."""
        self.status = GoalStatus.ON_HOLD
        self.updated_at = now_utc()
        return self

    def reactivate(self) -> Self:
        """Reactivate a goal."""
        self.status = GoalStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    # Workflow transition helpers
    def assign_workflow(self, workflow_id: str, initial_state: str) -> Self:
        """Assign a workflow to this goal."""
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
        data["horizon"] = self.horizon.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = GoalStatus(data["status"])
        if "horizon" in data and isinstance(data["horizon"], str):
            data["horizon"] = GoalHorizon(data["horizon"])
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)
