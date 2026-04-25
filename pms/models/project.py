"""Project model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import ProjectStatus
from pms.models.json_types import JsonObject, ModelObject


@dataclass
class Project(BaseModel):
    """
    A project is a time-bounded initiative within a product.

    Projects contain milestones and tasks, and track overall progress.
    State changes are tracked via events and revisions.
    """

    name: str = ""
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    tags: tuple[str, ...] = ()

    # Org/portfolio/program relationships for rollups and dashboards
    org_id: str | None = None
    portfolio_id: str | None = None
    program_id: str | None = None

    # Product relationship
    product_id: str | None = None

    # Workflow/state machine integration
    workflow_id: str | None = None
    current_state: str | None = None
    workflow_metadata: JsonObject = field(default_factory=dict)

    def archive(self) -> Self:
        """Mark project as archived."""
        self.status = ProjectStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def complete(self) -> Self:
        """Mark project as completed."""
        self.status = ProjectStatus.COMPLETED
        self.updated_at = now_utc()
        return self

    def reactivate(self) -> Self:
        """Reactivate an archived/on-hold project."""
        self.status = ProjectStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    def put_on_hold(self) -> Self:
        """Put project on hold."""
        self.status = ProjectStatus.ON_HOLD
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the project."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the project."""
        self.tags = tuple(t for t in self.tags if t != tag)
        self.updated_at = now_utc()
        return self

    @property
    def is_active(self) -> bool:
        """Check if project is active."""
        return self.status == ProjectStatus.ACTIVE

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["tags"] = list(self.tags)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        # Convert status string to enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = ProjectStatus(data["status"])
        # Convert tags list to tuple
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        return super().from_dict(data)


@dataclass
class ProjectStats:
    """Computed statistics for a project."""

    project_id: str
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    blocked_tasks: int = 0
    total_milestones: int = 0
    completed_milestones: int = 0

    # Complexity tracking
    total_complexity_points: int = 0
    avg_complexity_per_task: float = 0
    total_duration_hours: float = 0
    avg_duration_per_task: float = 0
    avg_efficiency_score: float = 0  # complexity/hour

    overdue_tasks: int = 0

    # Goal tracking
    total_goals: int = 0
    completed_goals: int = 0
    avg_goal_progress: float = 0.0

    @property
    def completion_percent(self) -> float:
        """Calculate completion percentage."""
        total_tasks = self.total_tasks or 0
        completed_tasks = self.completed_tasks or 0
        if total_tasks == 0:
            return 0.0
        return (completed_tasks / total_tasks) * 100

    @property
    def complexity_velocity(self) -> float:
        """Calculate complexity points completed per hour."""
        total_duration = self.total_duration_hours or 0
        total_complexity = self.total_complexity_points or 0
        if total_duration == 0:
            return 0.0
        completed_complexity = total_complexity * self.completion_percent / 100
        return completed_complexity / total_duration

    @property
    def health_score(self) -> float:
        """
        Calculate project health score (0-100).

        Factors:
        - Completion rate (40%)
        - Blocked task ratio (20%)
        - Overdue task ratio (20%)
        - Efficiency score (20%)
        """
        total_tasks = self.total_tasks or 0
        blocked_tasks = self.blocked_tasks or 0
        overdue_tasks = self.overdue_tasks or 0
        if total_tasks == 0:
            return 100.0

        completion_factor = self.completion_percent * 0.4
        blocked_penalty = (blocked_tasks / total_tasks) * 20
        overdue_penalty = (overdue_tasks / total_tasks) * 20

        # Efficiency score (normalize to 1-20 complexity/hour range)
        efficiency_factor = 0.0
        avg_efficiency = self.avg_efficiency_score or 0.0
        if avg_efficiency > 0:
            normalized_efficiency = min(avg_efficiency / 20.0, 1.0)
            efficiency_factor = normalized_efficiency * 20

        score = (
            completion_factor - blocked_penalty - overdue_penalty + efficiency_factor
        )
        return max(0, min(100, score))

    def to_dict(self) -> ModelObject:
        """Serialize stats for JSON outputs."""
        return {
            "project_id": self.project_id,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "in_progress_tasks": self.in_progress_tasks,
            "blocked_tasks": self.blocked_tasks,
            "total_milestones": self.total_milestones,
            "completed_milestones": self.completed_milestones,
            "total_complexity_points": self.total_complexity_points,
            "avg_complexity_per_task": self.avg_complexity_per_task,
            "total_duration_hours": self.total_duration_hours,
            "avg_duration_per_task": self.avg_duration_per_task,
            "avg_efficiency_score": self.avg_efficiency_score,
            "overdue_tasks": self.overdue_tasks,
            "total_goals": self.total_goals,
            "completed_goals": self.completed_goals,
            "avg_goal_progress": self.avg_goal_progress,
            "completion_percent": self.completion_percent,
            "complexity_velocity": self.complexity_velocity,
            "health_score": self.health_score,
        }
