"""Product model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Self

from pms.models.base import BaseModel, now_utc
from pms.models.enums import ProductStatus
from pms.models.json_types import JsonObject, ModelObject

if TYPE_CHECKING:
    from pms.models.project import Project

type ProductActivityEntry = ModelObject


@dataclass
class Product(BaseModel):
    """
    A product is the top-level strategic container in PMS.

    Products represent long-lived entities:
    - Services/applications
    - Codebases/repositories
    - Product lines
    - Business initiatives

    Products contain time-bounded projects that deliver iterations and features.
    State changes are tracked via events and revisions.
    """

    name: str = ""
    description: str | None = None
    status: ProductStatus = ProductStatus.ACTIVE

    # Strategic metadata
    vision: str | None = None  # Long-term vision/purpose
    repository_url: str | None = None
    service_urls: tuple[str, ...] = ()  # Production, staging URLs

    # Organizational
    owner: str | None = None  # Product owner/lead
    owner_id: str | None = None
    team: tuple[str, ...] = ()  # Descriptive team labels, not Team entity refs
    tags: tuple[str, ...] = ()

    # Categorization
    product_type: str = "service"  # Descriptive category; intentionally open.

    # Workflow/state machine integration
    workflow_id: str | None = None
    current_state: str | None = None
    workflow_metadata: JsonObject = field(default_factory=dict)

    def archive(self) -> Self:
        """Mark product as archived."""
        self.status = ProductStatus.ARCHIVED
        self.updated_at = now_utc()
        return self

    def sunset(self) -> Self:
        """Mark product for end-of-life/sunset."""
        self.status = ProductStatus.SUNSET
        self.updated_at = now_utc()
        return self

    def mark_mature(self) -> Self:
        """Mark product as mature (stable, maintenance mode)."""
        self.status = ProductStatus.MATURE
        self.updated_at = now_utc()
        return self

    def reactivate(self) -> Self:
        """Reactivate an archived product."""
        self.status = ProductStatus.ACTIVE
        self.updated_at = now_utc()
        return self

    def add_team_member(self, member: str) -> Self:
        """Add a team member to the product."""
        if member not in self.team:
            self.team = (*self.team, member)
            self.updated_at = now_utc()
        return self

    def remove_team_member(self, member: str) -> Self:
        """Remove a team member from the product."""
        self.team = tuple(m for m in self.team if m != member)
        self.updated_at = now_utc()
        return self

    def add_tag(self, tag: str) -> Self:
        """Add a tag to the product."""
        if tag not in self.tags:
            self.tags = (*self.tags, tag)
            self.updated_at = now_utc()
        return self

    def remove_tag(self, tag: str) -> Self:
        """Remove a tag from the product."""
        self.tags = tuple(t for t in self.tags if t != tag)
        self.updated_at = now_utc()
        return self

    def add_service_url(self, url: str) -> Self:
        """Add a service URL (production, staging, etc.)."""
        if url not in self.service_urls:
            self.service_urls = (*self.service_urls, url)
            self.updated_at = now_utc()
        return self

    def remove_service_url(self, url: str) -> Self:
        """Remove a service URL."""
        self.service_urls = tuple(u for u in self.service_urls if u != url)
        self.updated_at = now_utc()
        return self

    @property
    def is_active(self) -> bool:
        """Check if product is active."""
        return self.status == ProductStatus.ACTIVE

    @property
    def is_planning(self) -> bool:
        """Check if product is in planning phase."""
        return self.status == ProductStatus.PLANNING

    def to_dict(self) -> ModelObject:
        """Convert to dictionary with enum serialization."""
        data = super().to_dict()
        data["status"] = self.status.value
        data["tags"] = list(self.tags)
        data["team"] = list(self.team)
        data["service_urls"] = list(self.service_urls)
        return data

    @classmethod
    def from_dict(cls, data: ModelObject) -> Self:
        """Create from dictionary."""
        # Convert status string to enum
        if "status" in data and isinstance(data["status"], str):
            data["status"] = ProductStatus(data["status"])
        # Convert lists to tuples
        if "tags" in data and isinstance(data["tags"], list):
            data["tags"] = tuple(data["tags"])
        if "team" in data and isinstance(data["team"], list):
            data["team"] = tuple(data["team"])
        if "service_urls" in data and isinstance(data["service_urls"], list):
            data["service_urls"] = tuple(data["service_urls"])
        return super().from_dict(data)


@dataclass
class ProductStats:
    """Computed statistics for a product aggregated across all projects."""

    product_id: str
    total_projects: int = 0
    active_projects: int = 0
    completed_projects: int = 0

    # Aggregated task metrics
    total_tasks: int = 0
    completed_tasks: int = 0
    in_progress_tasks: int = 0
    blocked_tasks: int = 0

    # Complexity tracking
    total_complexity_points: int = 0
    avg_complexity_per_task: float = 0
    total_duration_hours: float = 0
    avg_efficiency_score: float = 0

    # Financial tracking
    total_aws_cost: float = 0

    # Goal tracking
    total_goals: int = 0
    completed_goals: int = 0
    avg_goal_progress: float = 0.0

    @property
    def completion_rate(self) -> float:
        """Overall completion rate across all projects."""
        if self.total_tasks == 0:
            return 0.0
        return (self.completed_tasks / self.total_tasks) * 100

    @property
    def project_completion_rate(self) -> float:
        """Project-level completion rate."""
        if self.total_projects == 0:
            return 0.0
        return (self.completed_projects / self.total_projects) * 100

    @property
    def health_score(self) -> float:
        """
        Calculate product health score (0-100).

        Weighted by:
        - Task completion rate (40%)
        - Project completion rate (30%)
        - Blocked task ratio (20%)
        - Active project ratio (10%)
        """
        if self.total_tasks == 0:
            return 100.0

        task_completion_factor = self.completion_rate * 0.4
        project_completion_factor = self.project_completion_rate * 0.3

        blocked_ratio = (
            self.blocked_tasks / self.total_tasks if self.total_tasks > 0 else 0
        )
        blocked_penalty = blocked_ratio * 20

        active_ratio = (
            self.active_projects / self.total_projects if self.total_projects > 0 else 1
        )
        active_factor = active_ratio * 10

        score = (
            task_completion_factor
            + project_completion_factor
            - blocked_penalty
            + active_factor
        )
        return max(0, min(100, score))

    def to_dict(self) -> ModelObject:
        """Serialize stats for JSON outputs."""
        return {
            "product_id": self.product_id,
            "total_projects": self.total_projects,
            "active_projects": self.active_projects,
            "completed_projects": self.completed_projects,
            "total_tasks": self.total_tasks,
            "completed_tasks": self.completed_tasks,
            "in_progress_tasks": self.in_progress_tasks,
            "blocked_tasks": self.blocked_tasks,
            "total_complexity_points": self.total_complexity_points,
            "avg_complexity_per_task": self.avg_complexity_per_task,
            "total_duration_hours": self.total_duration_hours,
            "avg_efficiency_score": self.avg_efficiency_score,
            "total_aws_cost": self.total_aws_cost,
            "total_goals": self.total_goals,
            "completed_goals": self.completed_goals,
            "avg_goal_progress": self.avg_goal_progress,
            "completion_rate": self.completion_rate,
            "project_completion_rate": self.project_completion_rate,
            "health_score": self.health_score,
        }


@dataclass
class ProductSummary:
    """Product with computed statistics and related data."""

    product: Product
    stats: ProductStats
    projects: list[Project] = field(default_factory=list)


@dataclass
class ProductDashboard:
    """Dashboard view for a product showing all key metrics."""

    product: Product
    stats: ProductStats
    active_projects: list[Project] = field(default_factory=list)
    completed_projects: list[Project] = field(default_factory=list)
    recent_activity: list[ProductActivityEntry] = field(default_factory=list)
