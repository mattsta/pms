"""Milestone model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import MilestoneStatus
from pms.models.json_types import ModelObject

if TYPE_CHECKING:
    from pms.models.task import Task


@dataclass
class Milestone(BaseModel):
    """
    A milestone represents a significant point or phase in a project.

    Milestones group related tasks and have due dates for tracking progress.
    """

    project_id: str = ""
    name: str = ""
    description: str | None = None
    due_date: datetime | None = None
    status: MilestoneStatus = MilestoneStatus.PENDING
    sort_order: int = 0

    def start(self) -> Self:
        """Mark milestone as in progress."""
        if self.status in (MilestoneStatus.COMPLETED, MilestoneStatus.MISSED):
            raise ValueError(f"Cannot start milestone in {self.status} status")
        self.status = MilestoneStatus.IN_PROGRESS
        self.updated_at = now_utc()
        return self

    def complete(self) -> Self:
        """Mark milestone as completed."""
        self.status = MilestoneStatus.COMPLETED
        self.updated_at = now_utc()
        return self

    def mark_missed(self) -> Self:
        """Mark milestone as missed (past due date without completion)."""
        self.status = MilestoneStatus.MISSED
        self.updated_at = now_utc()
        return self

    def reopen(self) -> Self:
        """Reopen a completed or missed milestone."""
        if self.status == MilestoneStatus.PENDING:
            raise ValueError("Milestone is already pending")
        self.status = MilestoneStatus.PENDING
        self.updated_at = now_utc()
        return self

    @property
    def is_overdue(self) -> bool:
        """Check if milestone is past due date."""
        if self.due_date is None:
            return False
        if self.status == MilestoneStatus.COMPLETED:
            return False
        return now_utc() > self.due_date

    @property
    def days_until_due(self) -> int | None:
        """Calculate days until due date."""
        if self.due_date is None:
            return None
        delta = self.due_date - now_utc()
        return delta.days

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        if "status" in data and isinstance(data["status"], str):
            data["status"] = MilestoneStatus(data["status"])
        return super().from_dict(data)


@dataclass
class MilestoneStats:
    """Computed statistics for a milestone."""

    milestone_id: str
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    blocked_tasks: int = 0

    # Complexity tracking
    total_complexity_points: int = 0
    avg_complexity_per_task: float = 0
    total_duration_hours: float = 0
    avg_duration_per_task: float = 0

    @property
    def completion_percent(self) -> float:
        """Calculate completion percentage."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    @property
    def is_on_track(self) -> bool:
        """Check if milestone progress is on track."""
        # Simple heuristic: no blocked tasks and some progress
        return self.blocked_tasks == 0 and (
            self.completed_tasks > 0 or self.in_progress_tasks > 0
        )


@dataclass
class MilestoneWithTasks:
    """Milestone with its associated tasks for display."""

    milestone: Milestone
    stats: MilestoneStats
    tasks: list[Task] = field(default_factory=list)
